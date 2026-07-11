"""
Post-Creation deployment phase for Rue OS1.

After Creation 1.0 generates code, this phase:
1. Checks that GitHub + Vercel are both connected
2. Detects whether the artifact contains deployable code
3. Runs a separate Claude API call with deploy-only tools
4. Yields SSE event dicts: deployment_started → deployment_status × N → deployment_complete|deployment_error
"""
import json
import os
import re
from typing import AsyncIterator

import httpx

from backend.lib.business.connectors.registry import list_user_connections
from backend.lib.business.model_router import SONNET as DEPLOYMENT_MODEL
from backend.lib.business.tool_builder import build_tools_for_user
from backend.lib.business.tool_executor import execute_tool

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEPLOYMENT_TIMEOUT = 40.0

_CODE_INDICATORS = [
    "<!DOCTYPE", "<html", "export default function", "export default class",
    "from 'react'", 'from "react"', "import React",
    "const ", "function ", "<style>", "module.exports",
    "package.json", "tsconfig", "tailwind", "next.config",
]

_TOOL_LABELS: dict[str, str] = {
    "github__create_repo": "Creating GitHub repository...",
    "github__push_files": "Pushing project files to GitHub...",
    "vercel__create_project": "Creating Vercel project...",
    "vercel__trigger_deploy": "Triggering production deployment...",
    "vercel__get_deployment": "Checking deployment status...",
}

_DEPLOYMENT_SYSTEM = """\
You are the Deployment Agent for Rue OS1.

You have been given the output of a Creation 1.0 session that produced website/project code.
Your job is to deploy it to GitHub and Vercel right now.

Steps (in order):
1. Call github__create_repo — pick a clean project name: lowercase letters and hyphens only, derived from the content, max 40 chars.
2. Assemble the files to push. Rules:
   - SINGLE-FILE HTML project: push these 3 files:
       • index.html  — the full generated HTML
       • package.json  — {"name":"[project-name]","scripts":{"build":"echo done"},"dependencies":{}}
       • vercel.json  — {"buildCommand":"","outputDirectory":"."}
   - NEXT.JS / MULTI-FILE project: push ALL generated files (package.json, tsconfig.json, next.config.js, tailwind.config.ts, app/layout.tsx, app/page.tsx, app/globals.css, components/, etc.)
3. Call github__push_files with ALL files in one atomic commit. Message: "Initial website build".
4. Call vercel__create_project — set framework to "nextjs" for Next.js projects, "other" for plain HTML. Link it to the GitHub repo you just created.

After all tools complete, respond with exactly ONE sentence:
🚀 Live at **https://[project-name].vercel.app** · Repo: **https://github.com/[owner]/[project-name]**

Do NOT paste any code in your response. Use tools only, then that one sentence."""


async def deploy_project_after_creation(
    user_id: str,
    artifact_markdown: str,
    user_message: str = "",
) -> AsyncIterator[dict]:
    """
    Async generator yielding SSE event dicts for the deployment phase.
    Yields nothing if conditions aren't met (no code, connectors missing).
    """
    # Must contain code
    has_code = any(ind in artifact_markdown for ind in _CODE_INDICATORS)
    if not has_code:
        return

    # GitHub + Vercel must both be active
    connections = await list_user_connections(user_id)
    active_types = {c["connector_type"] for c in connections if c.get("status") == "active"}
    if "github" not in active_types or "vercel" not in active_types:
        return

    # Build deploy-only tools (GitHub + Vercel subset)
    all_tools = await build_tools_for_user(user_id)
    deploy_tools = [
        t for t in all_tools
        if t["name"].startswith("github__") or t["name"].startswith("vercel__")
    ]
    if not deploy_tools:
        return

    yield {"type": "deployment_started"}

    user_content = artifact_markdown
    if user_message:
        user_content = f"Original request: {user_message}\n\n{artifact_markdown}"

    messages: list[dict] = [
        {"role": "user", "content": user_content}
    ]

    final_text = ""
    max_rounds = 8

    for _ in range(max_rounds):
        try:
            async with httpx.AsyncClient(timeout=DEPLOYMENT_TIMEOUT) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": DEPLOYMENT_MODEL,
                        "max_tokens": 4096,
                        "system": _DEPLOYMENT_SYSTEM,
                        "messages": messages,
                        "tools": deploy_tools,
                    },
                )
        except Exception as e:
            yield {"type": "deployment_error", "value": f"Deployment API call failed: {e}"}
            return

        if resp.status_code != 200:
            yield {"type": "deployment_error", "value": f"Deployment API error {resp.status_code}: {resp.text[:200]}"}
            return

        response_data = resp.json()
        content_blocks: list[dict] = response_data.get("content", [])
        stop_reason: str = response_data.get("stop_reason", "end_turn")

        # Accumulate final text
        for block in content_blocks:
            if block.get("type") == "text":
                final_text += block.get("text", "")

        tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]

        if not tool_use_blocks:
            break

        # Execute each tool and feed results back
        tool_results = []
        for tool_block in tool_use_blocks:
            tool_name = tool_block.get("name", "")
            tool_input = tool_block.get("input", {})
            tool_id = tool_block.get("id", "")

            yield {
                "type": "deployment_status",
                "message": _TOOL_LABELS.get(tool_name, f"Running {tool_name}..."),
            }

            try:
                result_str = await execute_tool(tool_name, tool_input, user_id)
            except Exception as e:
                result_str = json.dumps({"error": str(e)})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_str,
            })

        messages.append({"role": "assistant", "content": content_blocks})
        messages.append({"role": "user", "content": tool_results})

        if stop_reason == "end_turn":
            break

    # Parse live URL and repo URL out of the final text
    url: str | None = None
    repo_url: str | None = None
    url_match = re.search(r"https://[a-z0-9][a-z0-9-]+\.vercel\.app", final_text)
    repo_match = re.search(r"https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", final_text)
    if url_match:
        url = url_match.group(0)
    if repo_match:
        repo_url = repo_match.group(0).rstrip("*])")

    yield {
        "type": "deployment_complete",
        "message": final_text.strip(),
        "url": url,
        "repo_url": repo_url,
    }
