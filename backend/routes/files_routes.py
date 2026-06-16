import base64
import io
import os

import httpx
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(...),
):
    content_bytes = await file.read()
    filename = file.filename or "file"
    mime_type = file.content_type or "application/octet-stream"
    extracted_content = ""

    if mime_type.startswith("image/"):
        b64 = base64.standard_b64encode(content_bytes).decode()
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 1024,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": b64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": "Describe this image in detail. If there is text, transcribe all of it exactly.",
                                },
                            ],
                        }],
                    },
                    timeout=30.0,
                )
            result = resp.json()
            extracted_content = result.get("content", [{}])[0].get("text", "Could not read image")
        except Exception as e:
            print(f"FILES: image description failed: {e}")
            extracted_content = f"Image '{filename}' received ({len(content_bytes)} bytes), but I couldn't analyze it right now. Try again in a moment."

    elif mime_type == "application/pdf" or filename.endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            extracted_content = text[:5000]
        except ImportError:
            extracted_content = f"PDF file received ({len(content_bytes)} bytes) but PDF parsing library not available."
        except Exception as e:
            extracted_content = f"Could not parse PDF: {str(e)}"

    elif mime_type.startswith("text/") or filename.endswith((".txt", ".md", ".csv")):
        try:
            extracted_content = content_bytes.decode("utf-8", errors="ignore")[:5000]
        except Exception:
            extracted_content = "Could not read text file."

    else:
        extracted_content = f"File '{filename}' received ({mime_type}, {len(content_bytes)} bytes). I can read images, PDFs, and text files."

    return JSONResponse({
        "filename": filename,
        "mime_type": mime_type,
        "content": extracted_content,
    })
