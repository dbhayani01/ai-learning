"""
Chunking strategy factory — selects the right splitter based on config or hint.

Usage:
    from chunking.factory import get_chunks
    chunks = get_chunks(documents)                      # uses CHUNK_STRATEGY from .env
    chunks = get_chunks(documents, strategy="semantic") # override
"""
from langchain_core.documents import Document
from app.config import CHUNK_STRATEGY
from chunking.recursive import get_recursive_chunks


def get_chunks(
    documents: list[Document],
    strategy: str | None = None,
) -> list[Document]:
    """
    Route documents to the appropriate chunking strategy.

    Args:
        documents: Raw loaded Document objects.
        strategy:  "recursive" | "semantic"
                   If None, falls back to CHUNK_STRATEGY from .env (default: "recursive").

    Returns:
        List of chunk Document objects ready for embedding.
    """
    chosen = (strategy or CHUNK_STRATEGY).lower().strip()

    if chosen == "semantic":
        # Lazy import — only loads sentence-transformers when actually used
        from chunking.semantic import get_semantic_chunks
        return get_semantic_chunks(documents)

    # Default — recursive (fast, reliable, zero extra dependencies)
    return get_recursive_chunks(documents)
