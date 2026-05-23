import asyncio
import json

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from backend.lib.business.screenshot_fetcher import find_screenshot
from backend.lib.business.walkthrough_generator import generate_walkthrough

router = APIRouter()


class ShowMeHowRequest(BaseModel):
    query: str
    user_id: str = ""


class PDFRequest(BaseModel):
    walkthrough: dict


@router.post("/business/show-me-how")
async def show_me_how(request: ShowMeHowRequest):
    """Stream a step-by-step walkthrough as SSE events."""

    async def generate():
        try:
            walkthrough = await generate_walkthrough(request.query)

            yield f"data: {json.dumps({'type': 'title', 'value': walkthrough.get('title', '')})}\n\n"
            yield f"data: {json.dumps({'type': 'intro', 'value': walkthrough.get('intro', '')})}\n\n"

            for step in walkthrough.get("steps", []):
                # Fetch screenshot (real or fallback SVG)
                sq = step.get("screenshot_query") or request.query
                screenshot_result = await find_screenshot(sq)

                event = {
                    "type": "step",
                    "step_number": step.get("step_number"),
                    "instruction": step.get("instruction", ""),
                    "detail": step.get("detail", ""),
                    "screenshot_url": screenshot_result.get("url"),
                    "screenshot_fallback": screenshot_result.get("svg_data_url"),
                    "is_fallback": screenshot_result.get("is_fallback", True),
                    "annotations": step.get("annotations", []),
                }

                print(f"SHOW_ME_HOW: Step {event['step_number']} event:")
                print(f"  instruction: {event['instruction'][:80]}")
                print(f"  screenshot_url: {str(event['screenshot_url'])[:80]}")
                print(f"  is_fallback: {event['is_fallback']}")
                print(f"  annotations: {json.dumps(event['annotations'])[:120]}")

                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0.05)

            complete_event = {
                "type": "complete",
                "walkthrough": {
                    **walkthrough,
                    "steps": [
                        {**s, "screenshot_url": None, "screenshot_fallback": None}
                        for s in walkthrough.get("steps", [])
                    ],
                },
                "sources": walkthrough.get("sources", []),
            }
            yield f"data: {json.dumps(complete_event)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            print(f"SHOW_ME_HOW: Fatal error: {e}")
            import traceback; traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'value': 'Could not generate walkthrough. Please try again.'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/business/proxy-image")
async def proxy_image(url: str = Query(...)):
    """
    Proxy external images server-side to avoid CORS issues on the frontend.
    Frontend calls /api/business/proxy-image?url=<encoded_url>.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Jarvis/1.0)"},
                timeout=10.0,
                follow_redirects=True,
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Image not found")
        content_type = resp.headers.get("content-type", "image/jpeg")
        return Response(
            content=resp.content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"PROXY_IMAGE: Error fetching {url[:80]}: {e}")
        raise HTTPException(status_code=502, detail="Could not fetch image")


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
