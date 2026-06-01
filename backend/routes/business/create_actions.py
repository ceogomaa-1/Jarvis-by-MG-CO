import io
import json
import os
import re
from datetime import datetime

import httpx
from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from backend.lib.business.creation.persistence import get_creation_row, update_artifact

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
REFINE_MODEL = "claude-sonnet-4-6"

_REFINE_SYSTEM = """\
You are an expert content refiner for Jarvis Business by MG&CO Technologies.

You receive an existing business deliverable (Markdown) and a specific refinement instruction from the operator.

Your job:
- Apply the instruction precisely
- Keep everything that is good
- Only change what the instruction calls for
- Preserve the same Markdown structure and formatting

Output ONLY the refined artifact in Markdown. No preamble. No "Here is the refined version:". Just the artifact.
"""


class RefineRequest(BaseModel):
    instruction: str
    user_id: str = ""


@router.post("/business/create/{creation_id}/refine")
async def refine_creation(creation_id: str, request: RefineRequest):
    """Re-run Claude on the stored artifact with a refinement instruction."""
    row = await get_creation_row(creation_id)
    if not row:
        return Response(content="Not found", status_code=404)

    artifact = row.get("artifact_markdown") or ""
    if not artifact:
        return Response(content="No artifact to refine", status_code=400)

    user_message = f"Refinement instruction: {request.instruction.strip()}\n\nCurrent artifact:\n{artifact}"

    async def generate():
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": REFINE_MODEL,
                        "max_tokens": 4096,
                        "system": _REFINE_SYSTEM,
                        "messages": [{"role": "user", "content": user_message}],
                    },
                    timeout=90.0,
                )

            if resp.status_code != 200:
                yield f'data: {json.dumps({"type": "error", "value": f"API error {resp.status_code}"})}\n\n'
                yield "data: [DONE]\n\n"
                return

            refined = resp.json().get("content", [{}])[0].get("text", "")
            if refined:
                await update_artifact(creation_id, refined)
                yield f'data: {json.dumps({"type": "artifact", "content": refined})}\n\n'
            else:
                yield f'data: {json.dumps({"type": "error", "value": "Refinement returned empty result"})}\n\n'

            yield f'data: {json.dumps({"type": "complete"})}\n\n'
            yield "data: [DONE]\n\n"

        except Exception as e:
            print(f"REFINE: Error: {e}")
            yield f'data: {json.dumps({"type": "error", "value": "Refinement failed. Please try again."})}\n\n'
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/business/create/{creation_id}/pdf")
async def download_creation_pdf(creation_id: str):
    """Generate and stream a PDF of the creation artifact."""
    row = await get_creation_row(creation_id)
    if not row:
        return Response(content="Not found", status_code=404)

    artifact = row.get("artifact_markdown") or ""
    title = row.get("title") or "Jarvis Creation"

    if not artifact:
        return Response(content="No artifact to export", status_code=400)

    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

        from backend.routes.export import _build_styles, _make_callbacks, _md_to_story

        styles = _build_styles()
        callback = _make_callbacks(title)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=inch,
            rightMargin=inch,
            topMargin=inch,
            bottomMargin=inch,
            title=title,
            author="Jarvis by MG&CO",
        )

        title_style = ParagraphStyle(
            "DocTitle",
            fontSize=20,
            fontName="Helvetica-Bold",
            textColor=HexColor("#111111"),
            spaceAfter=6,
            leading=24,
        )
        date_style = ParagraphStyle(
            "DocDate",
            fontSize=9,
            fontName="Helvetica",
            textColor=HexColor("#888888"),
            spaceAfter=16,
        )

        story = []
        story.append(Paragraph(title, title_style))
        story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), date_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#dddddd")))
        story.append(Spacer(1, 12))
        story.extend(_md_to_story(artifact, styles))

        doc.build(story, onFirstPage=callback, onLaterPages=callback)

        safe_title = re.sub(r"[^\w\s-]", "", title)[:40].strip().replace(" ", "-").lower()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"jarvis-{safe_title or 'creation'}-{timestamp}.pdf"

        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except ImportError:
        return Response(content="PDF library not available on this server", status_code=503)
