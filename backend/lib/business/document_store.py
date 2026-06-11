"""
Lightweight on-disk store for documents Jarvis generates or receives mid-chat
(offer PDFs, decks, uploaded forms to be filled, etc). Each document gets a
doc_id and is served back via GET /api/business/documents/{doc_id}.

Files live in the OS temp dir and are not guaranteed to survive a process
restart — generated documents are meant to be downloaded shortly after creation.
"""
import json
import os
import tempfile
import uuid

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "https://jarvis-backend-4oz6.onrender.com")

_STORE_DIR = os.path.join(tempfile.gettempdir(), "jarvis_business_documents")
os.makedirs(_STORE_DIR, exist_ok=True)


def save_document(content: bytes, filename: str, content_type: str) -> dict:
    """Persist a document and return {doc_id, filename, download_url}."""
    doc_id = uuid.uuid4().hex
    doc_dir = os.path.join(_STORE_DIR, doc_id)
    os.makedirs(doc_dir, exist_ok=True)

    with open(os.path.join(doc_dir, "content"), "wb") as f:
        f.write(content)
    with open(os.path.join(doc_dir, "meta.json"), "w") as f:
        json.dump({"filename": filename, "content_type": content_type}, f)

    return {
        "doc_id": doc_id,
        "filename": filename,
        "download_url": f"{BACKEND_BASE_URL}/api/business/documents/{doc_id}",
    }


def load_document(doc_id: str) -> tuple[bytes, str, str] | None:
    """Return (content, filename, content_type) or None if not found/expired."""
    doc_dir = os.path.join(_STORE_DIR, doc_id)
    meta_path = os.path.join(doc_dir, "meta.json")
    content_path = os.path.join(doc_dir, "content")
    if not os.path.exists(meta_path) or not os.path.exists(content_path):
        return None

    with open(meta_path) as f:
        meta = json.load(f)
    with open(content_path, "rb") as f:
        content = f.read()

    return content, meta["filename"], meta["content_type"]
