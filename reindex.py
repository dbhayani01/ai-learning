"""
CLI re-indexing script — wipes the FAISS index and rebuilds from scratch.

Usage:
    python reindex.py
    python reindex.py --strategy semantic
    python reindex.py --confirm   (skips the confirmation prompt)
"""
import os
import sys
import shutil
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Wipe and rebuild the FAISS index.")
    parser.add_argument("--strategy", choices=["recursive","semantic"], default="recursive")
    parser.add_argument("--docs-dir", default="documents")
    parser.add_argument("--confirm",  action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    from app.config import FAISS_INDEX_DIR

    if not args.confirm:
        answer = input(
            f"⚠ This will DELETE '{FAISS_INDEX_DIR}' and rebuild. Continue? [y/N] "
        ).strip().lower()
        if answer != "y":
            logger.info("Aborted.")
            sys.exit(0)

    # Wipe old index + hash file
    if os.path.exists(FAISS_INDEX_DIR):
        shutil.rmtree(FAISS_INDEX_DIR)
        logger.info("Removed old index at '%s'.", FAISS_INDEX_DIR)

    from langchain_community.document_loaders import PyPDFDirectoryLoader
    from chunking.factory import get_chunks
    from vectordb.faiss_store import create_or_update_vector_store

    logger.info("Loading PDFs from '%s'…", args.docs_dir)
    loader    = PyPDFDirectoryLoader(args.docs_dir)
    documents = loader.load()

    if not documents:
        logger.warning("No PDFs found. Exiting.")
        sys.exit(0)

    logger.info("Loaded %d pages. Chunking with strategy='%s'…", len(documents), args.strategy)
    chunks = get_chunks(documents, strategy=args.strategy)
    logger.info("Created %d chunks.", len(chunks))

    logger.info("Rebuilding index…")
    stats = create_or_update_vector_store(chunks)

    logger.info(
        "Re-indexing complete. added=%d skipped=%d total=%d",
        stats["added"], stats["skipped"], stats["total"],
    )


if __name__ == "__main__":
    main()
