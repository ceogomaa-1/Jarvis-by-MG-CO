"""
Lightweight on-disk store for documents Rue generates or receives mid-chat
(offer PDFs, decks, uploaded forms to be filled, etc). Each document gets a
doc_id and is served back via GET /api/business/documents/{doc_id}.

Files live in the OS temp dir and are not guaranteed to survive a process
restart — generated documents are meant to be downloaded shortly after creation.
"""
import base64
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


def resolve_attachments(attachments: list[dict] | None) -> tuple[list[dict], str | None]:
    """Resolve [{doc_id, filename?, content_type?}, ...] into MIME-ready
    [{filename, content_type, content_b64}, ...] for Gmail attachments.

    Returns (resolved, error) — error is set (and resolved is []) if any
    referenced doc_id is missing or expired, so the caller can report the
    real failure instead of silently sending without the attachment.
    """
    resolved = []
    for att in attachments or []:
        doc_id = att.get("doc_id")
        if not doc_id:
            continue
        loaded = load_document(doc_id)
        if not loaded:
            return [], f"Attachment '{att.get('filename', doc_id)}' is no longer available (expired)."
        content, filename, content_type = loaded
        resolved.append({
            "filename": att.get("filename") or filename,
            "content_type": att.get("content_type") or content_type,
            "content_b64": base64.b64encode(content).decode(),
        })
    return resolved, None
