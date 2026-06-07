"""
Deterministic deploy pipeline for Jarvis OS1 — Batch 1.

Replaces the LLM-driven deployment_phase.py for website builds.
Called directly from create.py after site_generator produces the file set.

Steps:
  1. Preflight — verify GitHub + Vercel connectors active.
  2. GitHub — create_repo → push_files (up to 60 files).
  3. Supabase (optional) — reuse existing project, run migration, fetch keys.
  4. Vercel — create_project → set_env (if Supabase) → deploy_files directly.
  5. Poll Vercel until readyState == READY (max 180 s, every 5 s).
  6. Verify URL is reachable; emit deployment_complete with real URL.

Yields SSE event dicts throughout (same format as deployment_phase.py).
"""
import asyncio
import re
from typing import AsyncIterator

import httpx

from backend.lib.business.connectors.registry import get_connector_for_user


async def run_deploy_pipeline(
    user_id: str,
    site: dict,
    user_message: str = "",
) -> AsyncIterator[dict]:
    """
    Async generator yielding SSE event dicts.
    `site` is the dict returned by site_generator.generate_site().
    """
    # ── 0. Preflight ──────────────────────────────────────────────────────────
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

    yield {"type": "deployment_started"}

    project_name = site["project_name"]
    files = site.get("files", [])
    needs_db = site.get("needs_database", False)
    db_plan = site.get("db_plan") or {}

    # ── 1. GitHub: create repo ────────────────────────────────────────────────
    yield {"type": "deployment_status", "message": "Creating GitHub repository…"}
    repo_res = await gh.create_repo(
        name=project_name,
        description=f"Built with Jarvis OS1 — {site.get('summary', '')[:120]}",
        private=False,
    )
    if not repo_res.ok:
        yield {
            "type": "deployment_error",
            "value": f"GitHub repo creation failed: {repo_res.error}. Say 'deploy the last project' to retry.",
            "stage": "github_create",
        }
        return

    full_name: str = repo_res.data["full_name"]  # "owner/repo-name"
    repo_url: str = repo_res.data["url"]

    # ── 2. GitHub: push all files ─────────────────────────────────────────────
    yield {"type": "deployment_status", "message": f"Pushing {len(files)} files to GitHub…"}
    push_res = await gh.push_files(
        repo=full_name,
        files=files,
        message="Initial commit — shipped by Jarvis OS1",
        branch="main",
    )
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
    proj_res = await vc.create_project(
        name=project_name,
        github_repo=full_name,
        framework="nextjs",
    )
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
    deploy_res = await vc.deploy_files(
        project_name=vercel_project_name,
        files=files,
        env=env_vars if env_vars else None,
        framework="nextjs",
    )
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

    # ── 7. Poll until READY ───────────────────────────────────────────────────
    yield {"type": "deployment_status", "message": "Building… Next.js builds typically take 60–120 s"}

    final_url: str | None = None
    poll_seconds = 0
    max_poll = 180

    for tick in range(max_poll // 5):
        await asyncio.sleep(5)
        poll_seconds += 5

        status_res = await vc.get_deployment(deployment_id)
        if not status_res.ok:
            # Transient polling error — keep going
            continue

        state = status_res.data.get("readyState", "")
        alias = status_res.data.get("alias") or status_res.data.get("url") or initial_url

        if state == "READY":
            final_url = _normalise_url(alias or initial_url)
            break

        if state in ("ERROR", "CANCELED", "FAILED"):
            logs = await vc.get_deployment_build_logs(deployment_id)
            yield {
                "type": "deployment_error",
                "value": f"Build failed ({state}): {logs} — Say 'deploy the last project' to retry.",
                "stage": "vercel_build",
            }
            return

        # Periodic progress update every 30 s
        if poll_seconds % 30 == 0:
            yield {
                "type": "deployment_status",
                "message": f"Still building… ({poll_seconds}s elapsed, state: {state or 'BUILDING'})",
            }

    if not final_url:
        yield {
            "type": "deployment_error",
            "value": "Deployment timed out after 180 s. The code is on GitHub — say 'deploy the last project' to retry.",
            "stage": "timeout",
        }
        return

    # ── 8. Best-effort reachability check ────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            check = await client.get(final_url, follow_redirects=True)
            if check.status_code >= 500:
                yield {
                    "type": "deployment_status",
                    "message": f"⚠️ URL responded {check.status_code} — may still be warming up.",
                }
    except Exception:
        pass  # best-effort only

    yield {
        "type": "deployment_complete",
        "url": final_url,
        "repo_url": repo_url,
        "db_url": db_url,
        "message": (
            f"🚀 Live at **{final_url}**\n"
            f"Repo: **{repo_url}**"
            + (f"\nSupabase: **{db_url}**" if db_url else "")
        ),
    }


def _normalise_url(url: str) -> str:
    if not url:
        return url
    if not url.startswith("http"):
        return f"https://{url}"
    return url
