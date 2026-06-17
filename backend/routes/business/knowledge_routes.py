"""
Knowledge Base routes.

  POST   /business/knowledge/ingest   — multipart: user_id, text?, files[]?  (SSE progress stream)
  GET    /business/knowledge          — list sources for "What Jarvis knows"
  DELETE /business/knowledge/{id}     — delete a source (cascades to its memories)
"""
import json

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.lib.business import jarvis_skills
from backend.lib.business import knowledge_base as kb
from backend.tools.url_fetch import extract_urls

router = APIRouter()


def _skill_as_source(s: dict) -> dict:
    """Map a jarvis_skills row into the shape the 'What Jarvis knows' list expects,
    while carrying the richer skill fields for the upgraded UI."""
    return {
        "id": s.get("id"),
        "label": s.get("name") or s.get("source_filename") or "Skill",
        "name": s.get("name"),
        "source_type": s.get("source_type", "text"),
        "skill_type": s.get("skill_type", "knowledge"),
        "description": s.get("description", ""),
        "enabled": s.get("enabled", True),
        "fact_count": 0,
        "created_at": s.get("created_at"),
        "kind": "skill",
    }

_EXT_KIND = {
    ".pdf": "pdf", ".docx": "docx", ".txt": "text", ".md": "text", ".csv": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".zip": "zip",
}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@router.post("/business/knowledge/ingest")
async def ingest_knowledge(
    user_id: str = Form(...),
    text: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    # Read all upload bytes up front — UploadFile streams can't be awaited from inside the SSE generator.
    file_payloads = []
    for f in files:
        content = await f.read()
        file_payloads.append((f.filename or "file", content))

    async def generate():
        total_facts = 0

        if text and text.strip():
            yield _sse({"type": "progress", "label": "pasted text", "status": "analyzing"})
            result = await kb.ingest_text(user_id, text, label="Pasted text")
            total_facts += result.get("fact_count", 0)
            yield _sse({"type": "progress", **result})

            for url in extract_urls(text, limit=5):
                yield _sse({"type": "progress", "label": url, "status": "analyzing"})
                result = await kb.ingest_url(user_id, url)
                total_facts += result.get("fact_count", 0)
                yield _sse({"type": "progress", **result})

        for filename, content in file_payloads:
            ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
            kind = _EXT_KIND.get(ext)
            yield _sse({"type": "progress", "label": filename, "status": "analyzing"})

            if kind == "pdf":
                result = await kb.ingest_pdf(user_id, content, filename)
                total_facts += result.get("fact_count", 0)
                yield _sse({"type": "progress", **result})
            elif kind == "docx":
                result = await kb.ingest_docx(user_id, content, filename)
                total_facts += result.get("fact_count", 0)
                yield _sse({"type": "progress", **result})
            elif kind == "text":
                result = await kb.ingest_text(user_id, content.decode("utf-8", errors="ignore"), label=filename, source_type="text")
                total_facts += result.get("fact_count", 0)
                yield _sse({"type": "progress", **result})
            elif kind == "image":
                media_type = "image/png" if ext == ".png" else "image/jpeg"
                result = await kb.ingest_image(user_id, content, media_type, filename)
                total_facts += result.get("fact_count", 0)
                yield _sse({"type": "progress", **result})
            elif kind == "zip":
                results = await kb.ingest_zip(user_id, content, filename)
                for r in results:
                    total_facts += r.get("fact_count", 0)
                    yield _sse({"type": "progress", "label": r.get("label"), "status": "analyzing"})
                    yield _sse({"type": "progress", **r})
            else:
                yield _sse({"type": "progress", "label": filename, "status": "skipped", "fact_count": 0, "error": "unsupported file type"})

        yield _sse({"type": "done", "total_facts": total_facts})
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/business/knowledge")
async def list_knowledge(user_id: str = ""):
    """Skills (new, lossless) first, then any legacy knowledge sources — so nothing the
    user previously fed Jarvis disappears from the 'What Jarvis knows' list."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    skills = [_skill_as_source(s) for s in await jarvis_skills.list_skills(user_id)]
    legacy = [{**s, "kind": "legacy"} for s in await kb.list_sources(user_id)]
    return {"sources": skills + legacy}


@router.delete("/business/knowledge/{source_id}")
async def delete_knowledge(source_id: str, user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    # New skills first; fall back to legacy knowledge sources.
    if await jarvis_skills.delete_skill(user_id, source_id):
        return {"ok": True}
    ok = await kb.delete_source(user_id, source_id)
    return {"ok": ok}


# ── Skills manager API (powers the upgraded Skills UI) ─────────────────────────

@router.get("/business/skills")
async def list_skills_route(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return {"skills": await jarvis_skills.list_skills(user_id)}


@router.get("/business/skills/{skill_id}")
async def get_skill_route(skill_id: str, user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    skill = await jarvis_skills.get_skill(user_id, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"skill": skill}


@router.patch("/business/skills/{skill_id}")
async def update_skill_route(skill_id: str, user_id: str = Body(...), fields: dict = Body(...)):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    updated = await jarvis_skills.update_skill(user_id, skill_id, fields or {})
    if not updated:
        raise HTTPException(status_code=404, detail="skill not found or update failed")
    return {"skill": updated}


@router.post("/business/skills/{skill_id}/toggle")
async def toggle_skill_route(skill_id: str, user_id: str = Body(...), enabled: bool = Body(...)):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    updated = await jarvis_skills.set_enabled(user_id, skill_id, enabled)
    if not updated:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"skill": updated}


@router.delete("/business/skills/{skill_id}")
async def delete_skill_route(skill_id: str, user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return {"ok": await jarvis_skills.delete_skill(user_id, skill_id)}
