"""
CLI re-indexing script — wipes a specific user's FAISS index and rebuilds from their documents.

Usage:
    python reindex.py --user-id 1
    python reindex.py --user-id 1 --strategy semantic
    python reindex.py --user-id 1 --confirm   (skips the confirmation prompt)
"""
import os
import sys
import shutil
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Wipe and rebuild a user's FAISS index.")
    parser.add_argument("--user-id", type=int, required=True, help="The ID of the user to reindex")
    parser.add_argument("--strategy", choices=["recursive","semantic"], default="recursive")
    parser.add_argument("--docs-dir", help="Override the user's default documents directory")
    parser.add_argument("--confirm",  action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    from app.config import FAISS_INDEX_DIR, DOCUMENTS_DIR
    
    user_docs = args.docs_dir or os.path.join(DOCUMENTS_DIR, str(args.user_id))
    user_faiss = os.path.join(FAISS_INDEX_DIR, str(args.user_id))

    if not args.confirm:
        answer = input(
            f"⚠ This will DELETE '{user_faiss}' and rebuild from '{user_docs}'. Continue? [y/N] "
        ).strip().lower()
        if answer != "y":
            logger.info("Aborted.")
            sys.exit(0)

    # Wipe old index + hash file
    if os.path.exists(user_faiss):
        shutil.rmtree(user_faiss)
        logger.info("Removed old index at '%s'.", user_faiss)

    from langchain_community.document_loaders import PyPDFDirectoryLoader
    from chunking.factory import get_chunks
    from vectordb.faiss_store import create_or_update_vector_store

    logger.info("Loading PDFs from '%s'…", user_docs)
    if not os.path.exists(user_docs):
        logger.warning("Documents directory '%s' does not exist. Exiting.", user_docs)
        sys.exit(0)
    loader    = PyPDFDirectoryLoader(user_docs)
    documents = loader.load()

    if not documents:
        logger.warning("No PDFs found in '%s'. Exiting.", user_docs)
        sys.exit(0)

    logger.info("Loaded %d pages. Chunking with strategy='%s'…", len(documents), args.strategy)
    chunks = get_chunks(documents, strategy=args.strategy)
    logger.info("Created %d chunks.", len(chunks))

    logger.info("Rebuilding index for user %s…", args.user_id)
    stats = create_or_update_vector_store(chunks, args.user_id)

    logger.info(
        "Re-indexing complete. added=%d skipped=%d total=%d",
        stats["added"], stats["skipped"], stats["total"],
    )


if __name__ == "__main__":
    main()
