"""
Knowledge Base — paste text, drop URLs, or upload files (pdf, image,
txt/md/csv, docx, zip) and have Jarvis extract durable facts straight into
business_user_memories (category='knowledge_base'). Each ingestion is
tracked as a row in business_knowledge_sources for the "What Jarvis knows"
tab (source, date, fact count, delete-per-entry).

Everything stored here flows through the same memory pool the chat system
prompt reads, and counts toward readiness checkpoints (five_memories /
deep_knowledge).
"""
import base64
import io
import json
import os
import zipfile

import httpx

from backend.lib.business.mind.ingest import process_new_memory
from backend.tools.url_fetch import fetch_url_content

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

HAIKU = "claude-haiku-4-5-20251001"

MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_CONTENT_CHARS = 12000


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers() -> dict:
    return {**_read_headers(), "Content-Type": "application/json", "Prefer": "return=representation"}


_EXTRACTION_PROMPT = """\
The business owner just fed Jarvis (their AI operator) a piece of source material to learn from. \
Extract durable, useful facts Jarvis should remember — pricing, policies, procedures, contacts, \
numbers, dates, product/service details, processes, anything operationally useful for running \
the business.

SOURCE: {label}
CONTENT:
{content}

Return a JSON array of fact strings. Each fact must stand alone (understandable without the \
source) and be specific/concrete — not generic filler. If there's nothing operationally useful, \
return [].
Return ONLY a valid JSON array, nothing else."""

_IMAGE_EXTRACTION_PROMPT = """\
The business owner just fed Jarvis (their AI operator) the attached image ("{label}") to learn \
from. It might be a screenshot of pricing, a menu, an invoice, a dashboard, a price list, a \
flyer, a contract, a spreadsheet, etc.

Extract durable, useful facts Jarvis should remember from what's shown — pricing, numbers, \
names, dates, policies, products/services, anything operationally useful for running the \
business.

Return a JSON array of fact strings. Each fact must stand alone (understandable without seeing \
the image) and be specific/concrete. If there's nothing operationally useful in the image, \
return [].
Return ONLY a valid JSON array, nothing else."""


def _parse_fact_array(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        raw = "\n".join(inner).strip()
    try:
        facts = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(facts, list):
        return []
    return [f.strip() for f in facts if isinstance(f, str) and len(f.strip()) >= 8]


async def _extract_facts(client: httpx.AsyncClient, content: str, label: str) -> list[str]:
    if not ANTHROPIC_API_KEY or not content.strip():
        return []
    prompt = _EXTRACTION_PROMPT.format(label=label, content=content[:MAX_CONTENT_CHARS])
    try:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": HAIKU, "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]},
            timeout=45.0,
        )
        if resp.status_code != 200:
            print(f"KB: extraction API error {resp.status_code}: {resp.text[:200]}")
            return []
        raw = resp.json().get("content", [{}])[0].get("text", "")
        return _parse_fact_array(raw)
    except Exception as e:
        print(f"KB: extraction error: {e}")
        return []


async def _extract_facts_from_image(client: httpx.AsyncClient, content_b64: str, media_type: str, label: str) -> list[str]:
    if not ANTHROPIC_API_KEY:
        return []
    try:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": HAIKU,
                "max_tokens": 1000,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": content_b64}},
                        {"type": "text", "text": _IMAGE_EXTRACTION_PROMPT.format(label=label)},
                    ],
                }],
            },
            timeout=60.0,
        )
        if resp.status_code != 200:
            print(f"KB: image extraction API error {resp.status_code}: {resp.text[:200]}")
            return []
        raw = resp.json().get("content", [{}])[0].get("text", "")
        return _parse_fact_array(raw)
    except Exception as e:
        print(f"KB: image extraction error: {e}")
        return []


async def _create_source(client: httpx.AsyncClient, user_uuid: str, label: str, source_type: str) -> str | None:
    try:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/business_knowledge_sources",
            headers=_write_headers(),
            json={"user_id": user_uuid, "label": label[:200], "source_type": source_type},
            timeout=10.0,
        )
        if resp.status_code in (200, 201):
            rows = resp.json()
            return rows[0]["id"] if rows else None
        print(f"KB: create source failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"KB: create source error: {e}")
    return None


async def _store_facts(client: httpx.AsyncClient, user_uuid: str, source_id: str | None, facts: list[str]) -> int:
    stored = 0
    for fact in facts:
        try:
            existing = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_user_memories",
                headers=_read_headers(),
                params={"select": "id", "user_id": f"eq.{user_uuid}", "memory": f"eq.{fact}"},
                timeout=10.0,
            )
            if existing.status_code == 200 and existing.json():
                continue
            payload = {"user_id": user_uuid, "memory": fact, "category": "knowledge_base"}
            if source_id:
                payload["knowledge_source_id"] = source_id
            ins = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_user_memories",
                headers=_write_headers(),
                json=payload,
                timeout=10.0,
            )
            if ins.status_code in (200, 201, 204):
                stored += 1
                rows = ins.json() if ins.status_code in (200, 201) else []
                if rows:
                    await process_new_memory(user_uuid, rows[0]["id"], fact)
        except Exception as e:
            print(f"KB: store fact error: {e}")
    return stored


async def _update_fact_count(client: httpx.AsyncClient, source_id: str, fact_count: int) -> None:
    try:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/business_knowledge_sources",
            headers={**_write_headers(), "Prefer": "return=minimal"},
            params={"id": f"eq.{source_id}"},
            json={"fact_count": fact_count},
            timeout=10.0,
        )
    except Exception as e:
        print(f"KB: update fact count error: {e}")


async def ingest_text(user_id: str, text: str, label: str = "Pasted text", source_type: str = "text") -> dict:
    """Extract facts from a text blob and store them. Returns a progress-line result dict."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"label": label, "status": "error", "fact_count": 0, "error": "Supabase not configured"}
    if not text or not text.strip():
        return {"label": label, "status": "skipped", "fact_count": 0, "error": "empty"}

    user_uuid = _user_id_to_uuid(user_id)
    async with httpx.AsyncClient() as client:
        facts = await _extract_facts(client, text, label)
        if not facts:
            return {"label": label, "status": "skipped", "fact_count": 0, "error": "nothing useful found"}
        source_id = await _create_source(client, user_uuid, label, source_type)
        stored = await _store_facts(client, user_uuid, source_id, facts)
        if source_id:
            await _update_fact_count(client, source_id, stored)
        return {"label": label, "status": "learned", "fact_count": stored, "source_id": source_id}


async def ingest_url(user_id: str, url: str) -> dict:
    result = await fetch_url_content(url)
    if result.get("error"):
        return {"label": url, "status": "error", "fact_count": 0, "error": result["error"]}
    title = result.get("title") or url
    label = f"{title} ({url})" if title != url else url
    return await ingest_text(user_id, result["content"], label=label, source_type="url")


def _pdf_text(content: bytes) -> str:
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


async def ingest_pdf(user_id: str, content: bytes, filename: str) -> dict:
    try:
        text = _pdf_text(content)
    except Exception as e:
        return {"label": filename, "status": "error", "fact_count": 0, "error": f"could not parse PDF: {e}"}
    if not text.strip():
        return {"label": filename, "status": "skipped", "fact_count": 0, "error": "no extractable text"}
    return await ingest_text(user_id, text, label=filename, source_type="pdf")


def _docx_text(content: bytes) -> str:
    import docx
    doc = docx.Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


async def ingest_docx(user_id: str, content: bytes, filename: str) -> dict:
    try:
        text = _docx_text(content)
    except Exception as e:
        return {"label": filename, "status": "error", "fact_count": 0, "error": f"could not parse DOCX: {e}"}
    if not text.strip():
        return {"label": filename, "status": "skipped", "fact_count": 0, "error": "no extractable text"}
    return await ingest_text(user_id, text, label=filename, source_type="docx")


async def ingest_image(user_id: str, content: bytes, media_type: str, filename: str) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"label": filename, "status": "error", "fact_count": 0, "error": "Supabase not configured"}

    user_uuid = _user_id_to_uuid(user_id)
    b64 = base64.b64encode(content).decode("ascii")
    async with httpx.AsyncClient() as client:
        facts = await _extract_facts_from_image(client, b64, media_type, filename)
        if not facts:
            return {"label": filename, "status": "skipped", "fact_count": 0, "error": "nothing useful found"}
        source_id = await _create_source(client, user_uuid, filename, "image")
        stored = await _store_facts(client, user_uuid, source_id, facts)
        if source_id:
            await _update_fact_count(client, source_id, stored)
        return {"label": filename, "status": "learned", "fact_count": stored, "source_id": source_id}


_ZIP_KIND = {
    ".pdf": "pdf", ".docx": "docx", ".txt": "text", ".md": "text", ".csv": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
}


async def ingest_zip(user_id: str, content: bytes, filename: str) -> list[dict]:
    """Safely unpack a zip (25MB cap, depth 1) and route each member through the matching ingester."""
    if len(content) > MAX_ZIP_BYTES:
        return [{"label": filename, "status": "error", "fact_count": 0, "error": "zip exceeds 25MB limit"}]
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except Exception as e:
        return [{"label": filename, "status": "error", "fact_count": 0, "error": f"could not open zip: {e}"}]

    results = []
    total_bytes = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        if name.startswith("__MACOSX/") or os.path.basename(name).startswith("."):
            continue
        if "/" in name.strip("/") or "\\" in name:
            results.append({"label": name, "status": "skipped", "fact_count": 0, "error": "nested folders not supported"})
            continue
        ext = os.path.splitext(name)[1].lower()
        kind = _ZIP_KIND.get(ext)
        if not kind:
            results.append({"label": name, "status": "skipped", "fact_count": 0, "error": "unsupported file type"})
            continue
        if total_bytes + info.file_size > MAX_ZIP_BYTES:
            results.append({"label": name, "status": "skipped", "fact_count": 0, "error": "zip size cap reached"})
            continue
        total_bytes += info.file_size
        member_bytes = zf.read(info)

        if kind == "pdf":
            results.append(await ingest_pdf(user_id, member_bytes, name))
        elif kind == "docx":
            results.append(await ingest_docx(user_id, member_bytes, name))
        elif kind == "text":
            results.append(await ingest_text(user_id, member_bytes.decode("utf-8", errors="ignore"), label=name, source_type="text"))
        elif kind == "image":
            media_type = "image/png" if ext == ".png" else "image/jpeg"
            results.append(await ingest_image(user_id, member_bytes, media_type, name))

    return results


async def list_sources(user_id: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    user_uuid = _user_id_to_uuid(user_id)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_knowledge_sources",
                headers=_read_headers(),
                params={"select": "*", "user_id": f"eq.{user_uuid}", "order": "created_at.desc"},
                timeout=10.0,
            )
        return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        print(f"KB: list sources error: {e}")
        return []


async def delete_source(user_id: str, source_id: str) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    user_uuid = _user_id_to_uuid(user_id)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{SUPABASE_URL}/rest/v1/business_knowledge_sources",
                headers={**_write_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{source_id}", "user_id": f"eq.{user_uuid}"},
                timeout=10.0,
            )
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"KB: delete source error: {e}")
        return False
