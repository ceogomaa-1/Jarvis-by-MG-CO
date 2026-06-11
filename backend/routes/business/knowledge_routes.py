"""
Knowledge Base routes.

  POST   /business/knowledge/ingest   — multipart: user_id, text?, files[]?  (SSE progress stream)
  GET    /business/knowledge          — list sources for "What Jarvis knows"
  DELETE /business/knowledge/{id}     — delete a source (cascades to its memories)
"""
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.lib.business import knowledge_base as kb
from backend.tools.url_fetch import extract_urls

router = APIRouter()

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
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return {"sources": await kb.list_sources(user_id)}


@router.delete("/business/knowledge/{source_id}")
async def delete_knowledge(source_id: str, user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    ok = await kb.delete_source(user_id, source_id)
    return {"ok": ok}
