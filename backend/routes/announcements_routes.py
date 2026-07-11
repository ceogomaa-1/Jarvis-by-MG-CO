"""
Batch 56 — "What's New" feature announcements.

A single shared system surfaced in both Rue Personal and Rue OS1:

  USER endpoints (any signed-in user, keyed by user_id in the path):
    GET  /api/announcements/{user_id}        -> published announcements + unread_count
    POST /api/announcements/{user_id}/seen   -> {announcement_id} | {all:true}

  ADMIN endpoints (gated by is_admin / ADMIN_USER_IDS):
    POST   /api/admin/announcements          -> create (+ publish + email blast)
    PATCH  /api/admin/announcements/{id}      -> edit (publishing fires the blast)
    DELETE /api/admin/announcements/{id}

On publish, every user gets exactly one branded email. Idempotency is enforced
by claiming a row in `announcement_email_log` (PK = announcement_id) BEFORE
sending — a second publish/re-run finds the claim and sends nothing.
"""

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.agent import _SUPABASE_KEY, _SUPABASE_URL
from backend.lib.announcement_mailer import send_announcement_email
from backend.usage_limits import is_admin

router = APIRouter()

_VALID_TAGS = {"New Feature", "Improvement", "Fix"}
# Resend allows ~10 requests/sec on the default plan; stay well under it.
_EMAIL_BATCH_SIZE = 8
_EMAIL_BATCH_PAUSE = 1.1  # seconds between batches


def _headers(prefer: str | None = None) -> dict:
    h = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _require_supabase():
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise HTTPException(503, "Announcements storage is not configured")


def _require_admin(user_id: str | None):
    if not user_id or not is_admin(user_id):
        raise HTTPException(403, "Admin access required")


# ════════════════════════════════════════════════════════════════════
# Models
# ════════════════════════════════════════════════════════════════════
class SeenRequest(BaseModel):
    announcement_id: str | None = None
    all: bool = False


class AnnouncementCreate(BaseModel):
    admin_user_id: str
    title: str
    body: str
    tag: str = "New Feature"
    media_url: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    is_published: bool = False


class AnnouncementPatch(BaseModel):
    admin_user_id: str
    title: str | None = None
    body: str | None = None
    tag: str | None = None
    media_url: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    is_published: bool | None = None


# ════════════════════════════════════════════════════════════════════
# USER endpoints
# ════════════════════════════════════════════════════════════════════
@router.get("/announcements/{user_id}")
async def list_announcements(user_id: str):
    """Published announcements (newest first) + unread_count for this user."""
    _require_supabase()
    async with httpx.AsyncClient(timeout=10.0) as client:
        ann_resp, seen_resp = await asyncio.gather(
            client.get(
                f"{_SUPABASE_URL}/rest/v1/announcements",
                headers=_headers(),
                params={
                    "is_published": "eq.true",
                    "select": "id,title,body,tag,media_url,cta_label,cta_url,published_at,created_at",
                    "order": "published_at.desc.nullslast,created_at.desc",
                },
            ),
            client.get(
                f"{_SUPABASE_URL}/rest/v1/user_announcements_seen",
                headers=_headers(),
                params={"user_id": f"eq.{user_id}", "select": "announcement_id"},
            ),
        )

    announcements = ann_resp.json() if ann_resp.status_code == 200 else []
    seen_rows = seen_resp.json() if seen_resp.status_code == 200 else []
    seen_ids = {r["announcement_id"] for r in seen_rows}

    for a in announcements:
        a["seen"] = a["id"] in seen_ids

    unread_count = sum(1 for a in announcements if not a["seen"])
    return {
        "user_id": user_id,
        "count": len(announcements),
        "unread_count": unread_count,
        "announcements": announcements,
    }


@router.post("/announcements/{user_id}/seen")
async def mark_seen(user_id: str, body: SeenRequest):
    """Mark one announcement (announcement_id) or all published ones (all=true)
    as seen for this user. Upserts on (user_id, announcement_id) so it's safe to
    call repeatedly."""
    _require_supabase()

    target_ids: list[str] = []
    if body.all:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/announcements",
                headers=_headers(),
                params={"is_published": "eq.true", "select": "id"},
            )
        target_ids = [r["id"] for r in (resp.json() if resp.status_code == 200 else [])]
    elif body.announcement_id:
        target_ids = [body.announcement_id]
    else:
        raise HTTPException(400, "Provide announcement_id or all=true")

    if not target_ids:
        return {"status": "ok", "marked": 0}

    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [
        {"user_id": user_id, "announcement_id": aid, "seen_at": now_iso}
        for aid in target_ids
    ]
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/rest/v1/user_announcements_seen",
            headers=_headers("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "user_id,announcement_id"},
            json=rows,
        )
    if resp.status_code not in (200, 201, 204):
        print(f"ANNOUNCE: mark_seen failed ({resp.status_code}): {resp.text[:200]}")
        raise HTTPException(502, "Failed to record seen state")
    return {"status": "ok", "marked": len(target_ids)}


# ════════════════════════════════════════════════════════════════════
# ADMIN endpoints
# ════════════════════════════════════════════════════════════════════
@router.post("/admin/announcements")
async def create_announcement(body: AnnouncementCreate, background_tasks: BackgroundTasks):
    _require_supabase()
    _require_admin(body.admin_user_id)

    tag = body.tag if body.tag in _VALID_TAGS else "New Feature"
    now_iso = datetime.now(timezone.utc).isoformat()
    row = {
        "title": body.title.strip(),
        "body": body.body,
        "tag": tag,
        "media_url": body.media_url,
        "cta_label": body.cta_label,
        "cta_url": body.cta_url,
        "is_published": body.is_published,
        "published_at": now_iso if body.is_published else None,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/rest/v1/announcements",
            headers=_headers("return=representation"),
            json=row,
        )
    if resp.status_code not in (200, 201):
        print(f"ANNOUNCE: create failed ({resp.status_code}): {resp.text[:200]}")
        raise HTTPException(502, "Failed to create announcement")

    created = resp.json()[0]
    if created.get("is_published"):
        background_tasks.add_task(_blast_announcement_email, created["id"])
    return {"status": "ok", "announcement": created}


@router.patch("/admin/announcements/{announcement_id}")
async def patch_announcement(
    announcement_id: str, body: AnnouncementPatch, background_tasks: BackgroundTasks
):
    _require_supabase()
    _require_admin(body.admin_user_id)

    updates: dict = {}
    for field in ("title", "body", "media_url", "cta_label", "cta_url"):
        val = getattr(body, field)
        if val is not None:
            updates[field] = val
    if body.tag is not None:
        updates["tag"] = body.tag if body.tag in _VALID_TAGS else "New Feature"

    publishing_now = False
    if body.is_published is not None:
        updates["is_published"] = body.is_published
        if body.is_published:
            # Stamp published_at only on the transition to published.
            updates["published_at"] = datetime.now(timezone.utc).isoformat()
            publishing_now = True

    if not updates:
        raise HTTPException(400, "No fields to update")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(
            f"{_SUPABASE_URL}/rest/v1/announcements",
            headers=_headers("return=representation"),
            params={"id": f"eq.{announcement_id}"},
            json=updates,
        )
    if resp.status_code not in (200, 204):
        print(f"ANNOUNCE: patch failed ({resp.status_code}): {resp.text[:200]}")
        raise HTTPException(502, "Failed to update announcement")

    rows = resp.json() if resp.status_code == 200 else []
    if not rows:
        raise HTTPException(404, "Announcement not found")

    # Fire the blast whenever the row ends up published — the email-log guard
    # makes a second publish a no-op, so this is safe even if it was already sent.
    if publishing_now or rows[0].get("is_published"):
        background_tasks.add_task(_blast_announcement_email, announcement_id)
    return {"status": "ok", "announcement": rows[0]}


@router.delete("/admin/announcements/{announcement_id}")
async def delete_announcement(announcement_id: str, admin_user_id: str):
    _require_supabase()
    _require_admin(admin_user_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(
            f"{_SUPABASE_URL}/rest/v1/announcements",
            headers=_headers("return=minimal"),
            params={"id": f"eq.{announcement_id}"},
        )
    if resp.status_code not in (200, 204):
        raise HTTPException(502, "Failed to delete announcement")
    return {"status": "ok"}


# ════════════════════════════════════════════════════════════════════
# Email blast — idempotent broadcast to all users
# ════════════════════════════════════════════════════════════════════
async def _claim_email_blast(announcement_id: str) -> bool:
    """Atomically claim the blast by inserting the announcement_email_log PK row.
    Returns True if we won the claim (no prior row), False if it was already sent
    (PK conflict) — so the email goes out exactly once per announcement."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/rest/v1/announcement_email_log",
            headers=_headers("return=minimal"),
            json={
                "announcement_id": announcement_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "recipients_count": 0,
            },
        )
    if resp.status_code in (200, 201, 204):
        return True
    if resp.status_code == 409:  # PK conflict — already claimed/sent
        print(f"ANNOUNCE: blast for {announcement_id} already sent — skipping")
        return False
    print(f"ANNOUNCE: could not claim blast for {announcement_id} ({resp.status_code}): {resp.text[:200]}")
    return False


async def _release_email_blast(announcement_id: str) -> None:
    """Undo the claim so a later re-publish can retry — used only when the blast
    couldn't actually start (e.g. failed to load the recipient list)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.delete(
                f"{_SUPABASE_URL}/rest/v1/announcement_email_log",
                headers=_headers("return=minimal"),
                params={"announcement_id": f"eq.{announcement_id}"},
            )
    except Exception as e:
        print(f"ANNOUNCE: failed to release blast claim {announcement_id}: {e}")


async def _record_recipients(announcement_id: str, count: int) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.patch(
                f"{_SUPABASE_URL}/rest/v1/announcement_email_log",
                headers=_headers("return=minimal"),
                params={"announcement_id": f"eq.{announcement_id}"},
                json={"recipients_count": count},
            )
    except Exception as e:
        print(f"ANNOUNCE: failed to record recipients for {announcement_id}: {e}")


async def _fetch_announcement(announcement_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{_SUPABASE_URL}/rest/v1/announcements",
            headers=_headers(),
            params={"id": f"eq.{announcement_id}", "limit": 1},
        )
    rows = resp.json() if resp.status_code == 200 else []
    return rows[0] if rows else None


async def _fetch_all_user_emails() -> list[str]:
    """All registered user emails, via the GoTrue admin list-users endpoint
    (paginated). De-duplicated, lowercased."""
    emails: set[str] = set()
    page = 1
    per_page = 1000
    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            resp = await client.get(
                f"{_SUPABASE_URL}/auth/v1/admin/users",
                headers={"apikey": _SUPABASE_KEY, "Authorization": f"Bearer {_SUPABASE_KEY}"},
                params={"page": page, "per_page": per_page},
            )
            if resp.status_code != 200:
                print(f"ANNOUNCE: admin list users failed ({resp.status_code}): {resp.text[:200]}")
                break
            data = resp.json()
            users = data.get("users", data) if isinstance(data, dict) else data
            if not users:
                break
            for u in users:
                email = (u.get("email") or "").strip().lower()
                if email:
                    emails.add(email)
            if len(users) < per_page:
                break
            page += 1
    return sorted(emails)


async def _blast_announcement_email(announcement_id: str) -> None:
    """Send the announcement to every user, exactly once. Claims the blast first
    so concurrent / repeated publishes can never double-send."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return

    if not await _claim_email_blast(announcement_id):
        return  # already sent (or claim failed) — nothing to do

    announcement = await _fetch_announcement(announcement_id)
    if not announcement or not announcement.get("is_published"):
        await _release_email_blast(announcement_id)
        return

    recipients = await _fetch_all_user_emails()
    if not recipients:
        # Couldn't load anyone — release the claim so a re-publish can retry.
        print(f"ANNOUNCE: no recipients found for {announcement_id} — releasing claim")
        await _release_email_blast(announcement_id)
        return

    sent = 0
    for i in range(0, len(recipients), _EMAIL_BATCH_SIZE):
        batch = recipients[i : i + _EMAIL_BATCH_SIZE]
        results = await asyncio.gather(
            *(
                send_announcement_email(
                    email,
                    announcement["title"],
                    announcement["body"],
                    tag=announcement.get("tag", "New Feature"),
                    media_url=announcement.get("media_url"),
                    cta_label=announcement.get("cta_label"),
                    cta_url=announcement.get("cta_url"),
                )
                for email in batch
            ),
            return_exceptions=True,
        )
        sent += sum(1 for r in results if r is True)
        if i + _EMAIL_BATCH_SIZE < len(recipients):
            await asyncio.sleep(_EMAIL_BATCH_PAUSE)

    await _record_recipients(announcement_id, sent)
    print(f"ANNOUNCE: blast for {announcement_id} sent to {sent}/{len(recipients)} recipients")
