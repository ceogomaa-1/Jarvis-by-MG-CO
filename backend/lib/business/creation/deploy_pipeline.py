"""
Deterministic deploy pipeline for Jarvis OS1 — Batch 1.

Replaces the LLM-driven deployment_phase.py for website builds.
Called directly from create.py after site_generator produces the file set.

Steps:
  1. Preflight — verify GitHub + Vercel connectors active.
  2. GitHub — create_repo → push_files (up to 60 files).
  3. Supabase (optional) — reuse existing project, run migration, fetch keys.
  4. Vercel — create_project → set_env (if Supabase) → deploy_files directly.
  5. Emit deployment_pending with the Vercel deployment ID and close the SSE stream.

Yields SSE event dicts throughout (same format as deployment_phase.py).
"""
import asyncio
from typing import AsyncIterator

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.connectors.registry import get_connector_for_user
from backend.lib.business.creation.website_quality import validate_deployable_site

_EXTERNAL_STATUS_INTERVAL = 8.0
_EXTERNAL_CALL_TIMEOUT = 90.0


async def run_deploy_pipeline(
    user_id: str,
    site: dict,
    user_message: str = "",
    creation_id: str | None = None,
) -> AsyncIterator[dict]:
    """
    Async generator yielding SSE event dicts.
    `site` is the dict returned by site_generator.generate_site().
    """
    validation_errors = validate_deployable_site(site, user_message)
    if validation_errors:
        yield {
            "type": "deployment_error",
            "value": (
                "The generated project failed the deploy quality gate, so no repository or "
                "Vercel project was created. "
                + "; ".join(validation_errors[:5])
            ),
            "stage": "validation",
        }
        return

    # ── 0. Preflight ──────────────────────────────────────────────────────────
    # A REAL preflight: not just "is a connector row present", but "can these tokens
    # actually create a repo + deploy". Catches expired/under-scoped tokens up front with
    # a precise, actionable message instead of failing three API calls deep.
    gh = await get_connector_for_user(user_id, "github")
    vc = await get_connector_for_user(user_id, "vercel")

    if not gh:
        yield {
            "type": "deployment_error",
            "value": "GitHub connector not connected. Add it in Settings → Connections, then say 'deploy the last project' to retry.",
            "stage": "preflight",
        }
        return
    if not vc:
        yield {
            "type": "deployment_error",
            "value": "Vercel connector not connected. Add it in Settings → Connections, then say 'deploy the last project' to retry.",
            "stage": "preflight",
        }
        return

    yield {"type": "deployment_status", "message": "Verifying GitHub + Vercel access…"}
    gh_check = await gh.preflight()
    if not gh_check.ok:
        yield {"type": "deployment_error", "value": gh_check.error, "stage": "preflight"}
        return
    vc_check = await vc.preflight()
    if not vc_check.ok:
        yield {"type": "deployment_error", "value": vc_check.error, "stage": "preflight"}
        return

    yield {"type": "deployment_started"}

    project_name = site["project_name"]
    files = site.get("files", [])
    needs_db = site.get("needs_database", False)
    db_plan = site.get("db_plan") or {}

    # ── 1. GitHub: create repo ────────────────────────────────────────────────
    # On a 422 "name already exists" collision, try up to 3 suffixed names before failing.
    yield {"type": "deployment_status", "message": "Creating GitHub repository…"}
    repo_res = None
    _repo_candidates = [project_name, f"{project_name}-v2", f"{project_name}-v3", f"{project_name}-v4"]
    for _candidate in _repo_candidates:
        _is_retry = _candidate != project_name
        if _is_retry:
            yield {"type": "deployment_status", "message": f"Repository '{_candidate[:-3]}' already exists — trying '{_candidate}'…"}
        async for event in _await_connector_call(
            gh.create_repo(
                name=_candidate,
                description=site.get("summary", "")[:160] or "Production website",
                private=False,
            ),
            f"Still creating the GitHub repository ({_candidate})…",
            "GitHub repo creation timed out",
        ):
            if event.get("type") == "_connector_result":
                repo_res = event["result"]
            else:
                yield event
        if repo_res and repo_res.ok:
            break
        # Only retry on name-collision (422); any other error is terminal
        if repo_res and "422" not in str(repo_res.error) and "already exists" not in str(repo_res.error).lower():
            break

    if not repo_res or not repo_res.ok:
        yield {
            "type": "deployment_error",
            "value": f"GitHub repo creation failed: {repo_res.error if repo_res else 'unknown error'}. Say 'deploy the last project' to retry.",
            "stage": "github_create",
        }
        return

    full_name: str = repo_res.data["full_name"]  # "owner/repo-name"
    repo_url: str = repo_res.data["url"]
    # Use the actual name GitHub accepted (may differ if we suffixed on collision)
    project_name = repo_res.data.get("name", project_name)

    # ── 2. GitHub: push all files ─────────────────────────────────────────────
    yield {"type": "deployment_status", "message": f"Pushing {len(files)} files to GitHub…"}
    push_res = None
    async for event in _await_connector_call(
        gh.push_files(
            repo=full_name,
            files=files,
            message="Initial website build",
            branch="main",
        ),
        "Still pushing files to GitHub…",
        "GitHub push timed out",
        timeout=120.0,
    ):
        if event.get("type") == "_connector_result":
            push_res = event["result"]
        else:
            yield event
    if not push_res.ok:
        yield {
            "type": "deployment_error",
            "value": f"GitHub push failed: {push_res.error}. Say 'deploy the last project' to retry.",
            "stage": "github_push",
        }
        return

    pushed_count = push_res.data.get("files_pushed", len(files))
    yield {"type": "deployment_status", "message": f"Pushed {pushed_count} files to GitHub ✓"}

    # ── 3. Supabase (optional) ────────────────────────────────────────────────
    env_vars: dict[str, str] = {}
    db_url: str | None = None

    if needs_db:
        sb = await get_connector_for_user(user_id, "supabase_project")
        if not sb:
            yield {
                "type": "deployment_status",
                "message": "⚠️ Supabase connector not found — DB features will need manual setup.",
            }
        else:
            yield {"type": "deployment_status", "message": "Connecting to Supabase project…"}
            projects_res = await sb.list_projects()
            project_id: str | None = None

            if projects_res.ok and projects_res.data.get("projects"):
                # Reuse first active project
                for p in projects_res.data["projects"]:
                    if p.get("status", "").lower() in ("active_healthy", "active", ""):
                        project_id = p["id"]
                        db_url = f"https://{project_id}.supabase.co"
                        break

            if project_id:
                migration_sql = db_plan.get("migration_sql", "")
                if migration_sql:
                    yield {"type": "deployment_status", "message": "Running database migration…"}
                    sql_res = await sb.run_sql(project_id, migration_sql)
                    if not sql_res.ok:
                        yield {
                            "type": "deployment_status",
                            "message": f"⚠️ Migration warning: {sql_res.error[:120]}",
                        }

                yield {"type": "deployment_status", "message": "Fetching Supabase keys for env injection…"}
                keys_res = await sb.get_project_keys_internal(project_id)
                if keys_res.ok:
                    env_vars["NEXT_PUBLIC_SUPABASE_URL"] = f"https://{project_id}.supabase.co"
                    env_vars["NEXT_PUBLIC_SUPABASE_ANON_KEY"] = keys_res.data["anon_key"]
                else:
                    yield {
                        "type": "deployment_status",
                        "message": "⚠️ Could not fetch Supabase keys — set them manually in Vercel.",
                    }
            else:
                yield {
                    "type": "deployment_status",
                    "message": "⚠️ No active Supabase project found — set env vars manually after deploy.",
                }

    # ── 4. Vercel: create project ─────────────────────────────────────────────
    yield {"type": "deployment_status", "message": "Creating Vercel project…"}
    proj_res = None
    async for event in _await_connector_call(
        vc.create_project(
            name=project_name,
            github_repo=full_name,
            framework="nextjs",
        ),
        "Still creating the Vercel project…",
        "Vercel project creation timed out",
    ):
        if event.get("type") == "_connector_result":
            proj_res = event["result"]
        else:
            yield event
    # Non-fatal if project already existed — we'll still deploy
    vercel_project_name = project_name
    if proj_res.ok:
        vercel_project_name = proj_res.data.get("name", project_name)

    # ── 5. Vercel: set env vars ───────────────────────────────────────────────
    if env_vars:
        yield {"type": "deployment_status", "message": "Setting environment variables on Vercel…"}
        for key, value in env_vars.items():
            await vc.set_env(vercel_project_name, key, value)

    # ── 6. Vercel: deploy files directly ─────────────────────────────────────
    yield {"type": "deployment_status", "message": "Uploading project to Vercel and triggering build…"}
    deploy_res = None
    async for event in _await_connector_call(
        vc.deploy_files(
            project_name=vercel_project_name,
            files=files,
            env=env_vars if env_vars else None,
            framework="nextjs",
        ),
        "Still uploading project to Vercel…",
        "Vercel deployment trigger timed out",
        timeout=120.0,
    ):
        if event.get("type") == "_connector_result":
            deploy_res = event["result"]
        else:
            yield event
    if not deploy_res.ok:
        yield {
            "type": "deployment_error",
            "value": f"Vercel deployment failed: {deploy_res.error}. Say 'deploy the last project' to retry.",
            "stage": "vercel_deploy",
        }
        return

    deployment_id: str = deploy_res.data.get("deployment_id", "")
    initial_url: str = deploy_res.data.get("url", "")

    if not deployment_id:
        yield {
            "type": "deployment_error",
            "value": "Vercel returned no deployment ID. Say 'deploy the last project' to retry.",
            "stage": "vercel_deploy",
        }
        return

    expected_url = _normalise_url(initial_url) or f"https://{vercel_project_name}.vercel.app"
    yield {"type": "deployment_status", "message": "Build triggered — polling Vercel status…"}
    yield {
        "type": "deployment_pending",
        "deployment_id": deployment_id,
        "creation_id": creation_id,
        "expected_url": expected_url,
        "repo_url": repo_url,
        "db_url": db_url,
        "message": "Build is running on Vercel. I'll keep this card updated.",
    }


def _normalise_url(url: str) -> str:
    if not url:
        return url
    if not url.startswith("http"):
        return f"https://{url}"
    return url


async def _await_connector_call(
    coro,
    waiting_message: str,
    timeout_message: str,
    *,
    interval: float | None = None,
    timeout: float | None = None,
) -> AsyncIterator[dict]:
    if interval is None:
        interval = _EXTERNAL_STATUS_INTERVAL
    if timeout is None:
        timeout = _EXTERNAL_CALL_TIMEOUT

    task = asyncio.create_task(coro)
    elapsed = 0.0

    try:
        while not task.done():
            remaining = timeout - elapsed
            if remaining <= 0:
                task.cancel()
                return_result = ConnectorResult(ok=False, error=f"{timeout_message} after {int(timeout)}s")
                yield {"type": "_connector_result", "result": return_result}
                return

            await asyncio.sleep(min(interval, remaining))
            elapsed += min(interval, remaining)
            if not task.done():
                yield {
                    # Keep-alive progress replaces the current UI state; it is not a new
                    # deployment milestone and must never create an elapsed-time row.
                    "type": "deployment_progress",
                    "message": waiting_message,
                }

        yield {"type": "_connector_result", "result": await task}

    except Exception as exc:
        if not task.done():
            task.cancel()
        yield {"type": "_connector_result", "result": ConnectorResult(ok=False, error=str(exc))}
