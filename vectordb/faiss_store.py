"""
FAISS vector store — create, update, deduplicate, and retrieve.

Thread-safety:
  A threading.Lock guards all write operations so the background worker
  and any concurrent uploads don't corrupt the index.

Deduplication:
  Before adding chunks, we compute an MD5 hash of each chunk's content.
  Chunks already present in the store (by hash) are silently skipped.
  Hashes are persisted in a sidecar file alongside the FAISS index.
"""
import os
import json
import hashlib
import threading
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_core.documents import Document
from app.config import FAISS_INDEX_DIR

# ── Shared state ───────────────────────────────────────────────────────────────
_embeddings    = FastEmbedEmbeddings()
_write_lock    = threading.Lock()
_HASH_FILE     = os.path.join(FAISS_INDEX_DIR, "chunk_hashes.json")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _content_hash(doc: Document) -> str:
    """MD5 of page_content — used for deduplication."""
    return hashlib.md5(doc.page_content.encode()).hexdigest()


def _load_hashes() -> set[str]:
    """Load persisted chunk hashes from disk."""
    if os.path.exists(_HASH_FILE):
        with open(_HASH_FILE, "r") as f:
            return set(json.load(f))
    return set()


def _save_hashes(hashes: set[str]) -> None:
    """Persist updated chunk hashes to disk."""
    os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
    with open(_HASH_FILE, "w") as f:
        json.dump(list(hashes), f)


def _deduplicate(chunks: list[Document]) -> tuple[list[Document], int]:
    """
    Remove chunks whose content is already in the index.

    Returns:
        (new_chunks, skipped_count)
    """
    existing = _load_hashes()
    new_chunks, new_hashes = [], set()

    for chunk in chunks:
        h = _content_hash(chunk)
        if h not in existing and h not in new_hashes:
            new_chunks.append(chunk)
            new_hashes.add(h)

    _save_hashes(existing | new_hashes)
    return new_chunks, len(chunks) - len(new_chunks)


# ── Public API ─────────────────────────────────────────────────────────────────

def create_or_update_vector_store(chunks: list[Document]) -> dict:
    """
    Add chunks to the FAISS index, creating it if it doesn't exist.
    Duplicate chunks (by content hash) are silently skipped.

    Args:
        chunks: List of Document objects to embed and index.

    Returns:
        dict with keys: added, skipped, total
    """
    unique_chunks, skipped = _deduplicate(chunks)

    if not unique_chunks:
        return {"added": 0, "skipped": skipped, "total": skipped}

    with _write_lock:
        if os.path.exists(os.path.join(FAISS_INDEX_DIR, "index.faiss")):
            db = FAISS.load_local(
                FAISS_INDEX_DIR,
                _embeddings,
                allow_dangerous_deserialization=True,
            )
            db.add_documents(unique_chunks)
        else:
            db = FAISS.from_documents(unique_chunks, _embeddings)

        db.save_local(FAISS_INDEX_DIR)

    return {
        "added":   len(unique_chunks),
        "skipped": skipped,
        "total":   len(unique_chunks) + skipped,
    }


# Alias for CLI scripts that call create_vector_store
def create_vector_store(chunks: list[Document]) -> dict:
    """Alias for create_or_update_vector_store (used by ingest.py)."""
    return create_or_update_vector_store(chunks)


_cached_index = None
_cached_mtime = 0.0

def get_vector_store() -> FAISS:
    """
    Load the FAISS index from disk (read-only).
    Raises FileNotFoundError if no index has been built yet.
    """
    global _cached_index, _cached_mtime
    
    index_file = os.path.join(FAISS_INDEX_DIR, "index.faiss")
    if not os.path.exists(index_file):
        raise FileNotFoundError(
            "No FAISS index found. Upload a PDF first or run `python ingest.py`."
        )

    current_mtime = os.path.getmtime(index_file)
    
    if _cached_index is None or current_mtime > _cached_mtime:
        _cached_index = FAISS.load_local(
            FAISS_INDEX_DIR,
            _embeddings,
            allow_dangerous_deserialization=True,
        )
        _cached_mtime = current_mtime

    return _cached_index
