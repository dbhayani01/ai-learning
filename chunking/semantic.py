"""
Semantic Chunker — topic-boundary-aware chunking strategy.

Best for:
  - Long-form essays, books, research papers
  - Documents where topic shifts matter more than character counts
  - Cases where semantic coherence is critical for retrieval quality

Strategy:
  Uses sentence embeddings to detect points where semantic similarity
  between adjacent sentences drops sharply. Each chunk is a semantically
  coherent passage rather than an arbitrary character slice.

Requirements:
  pip install langchain-experimental sentence-transformers
"""
from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_core.documents import Document


def get_semantic_chunks(
    documents: list[Document],
    breakpoint_threshold_type: str = "percentile",
    breakpoint_threshold_amount: float = 90.0,
) -> list[Document]:
    """
    Split documents at semantic topic boundaries using embedding similarity.

    Args:
        documents: List of LangChain Document objects.
        breakpoint_threshold_type:
            "percentile"  — split at the top N% of similarity drops (default)
            "standard_deviation" — split where drop > mean + N std devs
            "interquartile"      — split using IQR of similarity distribution
        breakpoint_threshold_amount:
            Numeric threshold for the chosen method (default 90 = 90th percentile).

    Returns:
        List of semantically chunked Document objects.
    """
    embeddings = FastEmbedEmbeddings()

    splitter = SemanticChunker(
        embeddings=embeddings,
        breakpoint_threshold_type=breakpoint_threshold_type,
        breakpoint_threshold_amount=breakpoint_threshold_amount,
    )

    chunks = splitter.split_documents(documents)

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"]       = i
        chunk.metadata["chunk_strategy"] = "semantic"

    return chunks
