import io
import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from supabase import create_client

router = APIRouter()

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def _sb():
    url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def _extract_text(content_bytes: bytes, mime_type: str, filename: str) -> str:
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise HTTPException(400, "pypdf not installed — cannot parse PDF")
        except Exception as e:
            raise HTTPException(400, f"Could not parse PDF: {e}")
    if mime_type.startswith("text/") or filename.lower().endswith((".txt", ".md", ".csv")):
        return content_bytes.decode("utf-8", errors="ignore")
    raise HTTPException(400, f"Unsupported file type for text extraction: {mime_type or filename}")


def _chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


async def _embed(texts: list[str]) -> list[list[float]] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=api_key)
        resp = await client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [item.embedding for item in resp.data]
    except Exception as e:
        print(f"DOCS: embedding failed — {e}")
        return None


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), user_id: str = Form(...)):
    content_bytes = await file.read()
    filename = file.filename or "document"
    mime_type = file.content_type or ""

    text = _extract_text(content_bytes, mime_type, filename)
    if not text.strip():
        raise HTTPException(400, "No text could be extracted from this file")

    chunks = _chunk_text(text)
    if not chunks:
        raise HTTPException(400, "File appears to be empty after extraction")

    embeddings = await _embed(chunks)

    sb = _sb()
    if not sb:
        raise HTTPException(500, "Database not configured")

    doc_res = sb.table("user_documents").insert({
        "user_id": user_id,
        "filename": filename,
        "file_type": mime_type or "unknown",
        "file_size": len(content_bytes),
        "chunk_count": len(chunks),
    }).execute()
    doc_id = doc_res.data[0]["id"]

    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = []
        for j, chunk in enumerate(chunks[i:i + batch_size]):
            row = {
                "document_id": doc_id,
                "user_id": user_id,
                "chunk_index": i + j,
                "content": chunk,
            }
            if embeddings:
                row["embedding"] = embeddings[i + j]
            batch.append(row)
        sb.table("document_chunks").insert(batch).execute()

    print(f"DOCS: stored {len(chunks)} chunks for '{filename}' (user={user_id})")
    return JSONResponse({
        "document_id": doc_id,
        "filename": filename,
        "chunk_count": len(chunks),
        "file_type": mime_type,
        "file_size": len(content_bytes),
    })


async def search_user_documents(user_id: str, query: str, top_k: int = 5) -> str:
    """Return relevant document chunks for this query. Empty string if nothing found."""
    sb = _sb()
    if not sb:
        return ""

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=api_key)
            resp = await client.embeddings.create(model="text-embedding-3-small", input=[query])
            q_emb = resp.data[0].embedding
            res = sb.rpc("search_document_chunks", {
                "p_user_id": user_id,
                "p_embedding": q_emb,
                "p_top_k": top_k,
            }).execute()
            if res.data:
                return "\n\n---\n\n".join(r["content"] for r in res.data)
        except Exception as e:
            print(f"DOCS: vector search failed — {e}")

    # Keyword fallback when no OpenAI key or vector search fails
    try:
        res = sb.table("document_chunks").select("content").eq("user_id", user_id).execute()
        if not res.data:
            return ""
        words = [w for w in query.lower().split() if len(w) > 3]
        if not words:
            return ""
        scored = []
        for row in res.data:
            score = sum(1 for w in words if w in row["content"].lower())
            if score > 0:
                scored.append((score, row["content"]))
        scored.sort(reverse=True)
        return "\n\n---\n\n".join(c for _, c in scored[:top_k])
    except Exception as e:
        print(f"DOCS: keyword search failed — {e}")
        return ""
