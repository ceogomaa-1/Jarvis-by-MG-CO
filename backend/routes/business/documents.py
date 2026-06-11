from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.lib.business.document_store import load_document

router = APIRouter()


@router.get("/business/documents/{doc_id}")
async def get_business_document(doc_id: str):
    result = load_document(doc_id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found or expired")
    content, filename, content_type = result
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
