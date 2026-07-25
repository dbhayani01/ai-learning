"""
Recursive Character Text Splitter — default chunking strategy.

Best for:
  - Technical documentation (AWS, LangGraph, FastAPI)
  - PDFs with mixed structure
  - Interview notes and articles

Strategy:
  Splits on paragraphs → sentences → words → characters (fallback).
  Keeps semantic units together as long as possible.
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from app.config import CHUNK_SIZE, CHUNK_OVERLAP

# Minimum chars a chunk must have to be indexed.
# Drops header stubs, page numbers, and empty table fragments.
_MIN_CHUNK_LEN = 80


def get_recursive_chunks(documents: list[Document]) -> list[Document]:
    """
    Split documents using recursive character splitting.

    Key decisions:
    - add_start_index=False: enabling this on short tabular PDFs causes the
      splitter to generate cumulative sliding-window chunks (each chunk = all
      previous rows + one new row), flooding the index with near-duplicates.
    - chunk_overlap=100: lower than the default 200 to prevent the snowball
      effect on dense table rows (~60 chars each).
    - Minimum length filter: drops tiny stubs (page numbers, headers, etc.)

    Args:
        documents: List of LangChain Document objects (from any loader).

    Returns:
        List of chunked Document objects with chunk_id metadata injected.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""],
        length_function=len,
        is_separator_regex=False,
        add_start_index=False,  # DO NOT enable — causes cumulative table chunks
    )

    raw_chunks = splitter.split_documents(documents)

    # Drop stubs that are too short to be meaningful
    chunks = [c for c in raw_chunks if len(c.page_content.strip()) >= _MIN_CHUNK_LEN]

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"]       = i
        chunk.metadata["chunk_strategy"] = "recursive"

    return chunks
