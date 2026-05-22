import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from backend.lib.business.annotation_overlay import generate_annotation_svg
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
    """Stream a step-by-step walkthrough for the given query."""

    async def generate():
        try:
            walkthrough = await generate_walkthrough(request.query)

            yield f"data: {json.dumps({'type': 'title', 'value': walkthrough.get('title', '')})}\n\n"
            yield f"data: {json.dumps({'type': 'intro', 'value': walkthrough.get('intro', '')})}\n\n"

            for step in walkthrough.get("steps", []):
                step_data = {
                    "type": "step",
                    "step_number": step.get("step_number"),
                    "instruction": step.get("instruction", ""),
                    "detail": step.get("detail", ""),
                    "image_url": None,
                    "annotation_svg": "",
                }

                # Try to find a real screenshot
                sq = step.get("screenshot_query") or request.query
                image_url = await find_screenshot(sq)
                if image_url:
                    step_data["image_url"] = image_url

                # Generate SVG annotation overlay
                annotation = step.get("annotation")
                if annotation:
                    step_data["annotation_svg"] = generate_annotation_svg(annotation)

                yield f"data: {json.dumps(step_data)}\n\n"
                await asyncio.sleep(0.05)

            # Send full data for PDF generation
            yield f"data: {json.dumps({'type': 'complete', 'walkthrough': walkthrough})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            print(f"SHOW_ME_HOW: Error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'value': 'Could not generate walkthrough. Please try again.'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/business/show-me-how/pdf")
async def show_me_how_pdf(request: PDFRequest):
    """Generate a downloadable PDF for the given walkthrough."""
    try:
        from backend.lib.business.pdf_export import generate_pdf
        pdf_bytes = generate_pdf(request.walkthrough)
        safe_title = request.walkthrough.get("title", "walkthrough")
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in safe_title)[:40].strip()
        filename = f"{safe_title or 'walkthrough'}.pdf"
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
