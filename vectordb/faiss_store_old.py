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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _content_hash(doc: Document) -> str:
    """MD5 of page_content — used for deduplication."""
    return hashlib.md5(doc.page_content.encode()).hexdigest()


def _get_user_dir(user_id: int) -> str:
    user_dir = os.path.join(FAISS_INDEX_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def _get_hash_file(user_id: int) -> str:
    return os.path.join(_get_user_dir(user_id), "chunk_hashes.json")

def _load_hashes(user_id: int) -> set[str]:
    """Load persisted chunk hashes from disk."""
    hf = _get_hash_file(user_id)
    if os.path.exists(hf):
        with open(hf, "r") as f:
            return set(json.load(f))
    return set()

def _save_hashes(user_id: int, hashes: set[str]) -> None:
    """Persist updated chunk hashes to disk."""
    with open(_get_hash_file(user_id), "w") as f:
        json.dump(list(hashes), f)


def _deduplicate(chunks: list[Document], user_id: int) -> tuple[list[Document], int]:
    """
    Remove chunks whose content is already in the index.

    Returns:
        (new_chunks, skipped_count)
    """
    existing = _load_hashes(user_id)
    new_chunks, new_hashes = [], set()

    for chunk in chunks:
        h = _content_hash(chunk)
        if h not in existing and h not in new_hashes:
            new_chunks.append(chunk)
            new_hashes.add(h)

    _save_hashes(user_id, existing | new_hashes)
    return new_chunks, len(chunks) - len(new_chunks)


# ── Public API ─────────────────────────────────────────────────────────────────

def create_or_update_vector_store(chunks: list[Document], user_id: int) -> dict:
    """
    Add chunks to the FAISS index, creating it if it doesn't exist.
    Duplicate chunks (by content hash) are silently skipped.

    Args:
        chunks: List of Document objects to embed and index.
        user_id: ID of the user.

    Returns:
        dict with keys: added, skipped, total
    """
    unique_chunks, skipped = _deduplicate(chunks, user_id)

    if not unique_chunks:
        return {"added": 0, "skipped": skipped, "total": skipped}

    with _write_lock:
        user_dir = _get_user_dir(user_id)
        if os.path.exists(os.path.join(user_dir, "index.faiss")):
            db = FAISS.load_local(
                user_dir,
                _embeddings,
                allow_dangerous_deserialization=True,
            )
            db.add_documents(unique_chunks)
        else:
            db = FAISS.from_documents(unique_chunks, _embeddings)

        db.save_local(user_dir)

    return {
        "added":   len(unique_chunks),
        "skipped": skipped,
        "total":   len(unique_chunks) + skipped,
    }


# Alias for CLI scripts that call create_vector_store
def create_vector_store(chunks: list[Document], user_id: int) -> dict:
    """Alias for create_or_update_vector_store (used by ingest.py)."""
    return create_or_update_vector_store(chunks, user_id)


_cached_indices = {}
_cached_mtimes = {}

def get_vector_store(user_id: int) -> FAISS:
    """
    Load the FAISS index from disk (read-only).
    Raises FileNotFoundError if no index has been built yet.
    """
    user_dir = os.path.join(FAISS_INDEX_DIR, str(user_id))
    index_file = os.path.join(user_dir, "index.faiss")
    
    if not os.path.exists(index_file):
        raise FileNotFoundError(
            "No FAISS index found. Upload a PDF first or run `python ingest.py`."
        )

    current_mtime = os.path.getmtime(index_file)
    
    if user_id not in _cached_indices or current_mtime > _cached_mtimes.get(user_id, 0.0):
        _cached_indices[user_id] = FAISS.load_local(
            user_dir,
            _embeddings,
            allow_dangerous_deserialization=True,
        )
        _cached_mtimes[user_id] = current_mtime

    return _cached_indices[user_id]


def delete_document_from_index(filename: str, user_id: int):
    """
    Remove all chunks originating from a specific filename from the FAISS index.
    Also recalculates chunk_hashes to ensure complete cleanup.
    """
    user_dir = _get_user_dir(user_id)
    index_file = os.path.join(user_dir, "index.faiss")
    
    if not os.path.exists(index_file):
        return  # Nothing to delete
        
    with _write_lock:
        db = FAISS.load_local(
            user_dir,
            _embeddings,
            allow_dangerous_deserialization=True,
        )
        
        # Find chunks belonging to this document
        to_delete_ids = []
        for doc_id, doc in db.docstore._dict.items():
            if doc.metadata.get("source") == filename:
                to_delete_ids.append(doc_id)
                
        if to_delete_ids:
            # Delete from FAISS
            db.delete(to_delete_ids)
            db.save_local(user_dir)
            
            # Remove deleted hashes from cache
            # Instead of manually trying to reverse hash the deleted docs (since we only saved MD5s),
            # we can just recalculate the valid hashes by rehashing everything currently in the docstore.
            valid_hashes = set()
            for doc in db.docstore._dict.values():
                valid_hashes.add(_content_hash(doc))
            
            _save_hashes(user_id, valid_hashes)
