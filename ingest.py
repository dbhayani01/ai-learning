"""
CLI ingestion script — load all PDFs from documents/ and build FAISS index.

Usage:
    python ingest.py
    python ingest.py --strategy semantic
"""
import sys
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Ingest all PDFs into the FAISS vector store.")
    parser.add_argument(
        "--strategy",
        choices=["recursive", "semantic"],
        default="recursive",
        help="Chunking strategy (default: recursive)",
    )
    parser.add_argument(
        "--docs-dir",
        default="documents",
        help="Directory containing PDF files (default: documents/)",
    )
    args = parser.parse_args()

    from langchain_community.document_loaders import PyPDFDirectoryLoader
    from chunking.factory import get_chunks
    from vectordb.faiss_store import create_or_update_vector_store

    logger.info("Loading PDFs from '%s'…", args.docs_dir)
    loader    = PyPDFDirectoryLoader(args.docs_dir)
    documents = loader.load()

    if not documents:
        logger.warning("No PDF pages found in '%s'. Exiting.", args.docs_dir)
        sys.exit(0)

    logger.info("Loaded %d pages. Chunking with strategy='%s'…", len(documents), args.strategy)
    chunks = get_chunks(documents, strategy=args.strategy)
    logger.info("Created %d chunks.", len(chunks))

    logger.info("Embedding and indexing…")
    stats = create_or_update_vector_store(chunks)

    logger.info(
        "Done. added=%d skipped=%d (duplicates) total=%d",
        stats["added"], stats["skipped"], stats["total"],
    )


if __name__ == "__main__":
    main()
