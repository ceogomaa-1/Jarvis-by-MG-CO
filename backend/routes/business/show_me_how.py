import asyncio
import json

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from backend.lib.business.walkthrough_generator import generate_walkthrough
from backend.lib.business.system_prompt_builder import get_industry_context_note

router = APIRouter()


class ShowMeHowRequest(BaseModel):
    query: str
    user_id: str = ""


class PDFRequest(BaseModel):
    walkthrough: dict


@router.post("/business/show-me-how")
async def show_me_how(request: ShowMeHowRequest):
    """Stream a step-by-step walkthrough with inline SVG illustrations."""

    async def generate():
        try:
            # Immediate thinking signal — arrives before generate_walkthrough blocks (3-5s)
            yield f"data: {json.dumps({'type': 'status', 'value': 'thinking'})}\n\n"

            industry_note = get_industry_context_note(request.user_id)
            enriched_query = f"{request.query}\n\n{industry_note}" if industry_note else request.query
            walkthrough = await generate_walkthrough(enriched_query)

            yield f"data: {json.dumps({'type': 'title', 'value': walkthrough.get('title', '')})}\n\n"
            yield f"data: {json.dumps({'type': 'intro', 'value': walkthrough.get('intro', '')})}\n\n"

            for step in walkthrough.get("steps", []):
                event = {
                    "type": "step",
                    "step_number": step.get("step_number"),
                    "instruction": step.get("instruction", ""),
                    "detail": step.get("detail", ""),
                    "needs_visual": step.get("needs_visual", False),
                    "visual": step.get("visual") if step.get("needs_visual") else None,
                }
                svg_len = len((event.get("visual") or {}).get("svg_content", ""))
                print(f"SHOW_ME_HOW: Step {event['step_number']} needs_visual={event['needs_visual']} svg_len={svg_len}")
                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0.05)

            yield f"data: {json.dumps({'type': 'complete', 'walkthrough': walkthrough, 'sources': walkthrough.get('sources', [])})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            import traceback
            print(f"SHOW_ME_HOW: Fatal error: {e}")
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'value': 'Could not generate walkthrough. Please try again.'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/business/proxy-image")
async def proxy_image(url: str = Query(...)):
    """Proxy external images server-side to bypass CORS."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Jarvis/1.0)"},
                timeout=10.0,
                follow_redirects=True,
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=404)
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/business/show-me-how/pdf")
async def show_me_how_pdf(request: PDFRequest):
    try:
        from backend.lib.business.pdf_export import generate_pdf
        pdf_bytes = generate_pdf(request.walkthrough)
        raw_title = request.walkthrough.get("title", "walkthrough")
        safe = "".join(c if c.isalnum() or c in " -_" else "" for c in raw_title)[:40].strip()
        filename = f"{safe or 'walkthrough'}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="PDF generation requires reportlab")
    except Exception as e:
        print(f"PDF: Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
