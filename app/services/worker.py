"""
Background document processing worker.

Runs as a daemon thread. Continuously drains the document_queue,
loads PDFs, chunks them, and upserts into the FAISS index.
Memory-guards prevent OOM when system RAM is low.
"""
import time
import logging

import psutil
from langchain_community.document_loaders import PyPDFLoader

from app.config import MIN_FREE_MB_WORKER
from app.services.queue_manager import document_queue, update_job

logger = logging.getLogger(__name__)


def _wait_for_memory() -> None:
    """Block until at least MIN_FREE_MB_WORKER of RAM is available."""
    while True:
        free_mb = psutil.virtual_memory().available / 1024 / 1024
        if free_mb >= MIN_FREE_MB_WORKER:
            return
        logger.warning(
            "Low memory (%.0f MB free). Waiting 10s before processing…", free_mb
        )
        time.sleep(10)


def process_documents() -> None:
    """
    Infinite loop — worker entry point.
    Call this in a daemon Thread so it exits when the main process exits.
    """
    logger.info("Document processing worker started.")

    while True:
        job_id, file_path = document_queue.get()
        logger.info("Processing job %s: %s", job_id, file_path)

        update_job(job_id, {"status": "processing"})

        try:
            _wait_for_memory()

            # Load PDF pages
            loader    = PyPDFLoader(file_path)
            documents = loader.load()

            # Chunk — strategy from config/.env
            from chunking.factory import get_chunks
            chunks = get_chunks(documents)

            # Embed & upsert (with dedup)
            from vectordb.faiss_store import create_or_update_vector_store
            stats = create_or_update_vector_store(chunks)

            update_job(job_id, {
                "status":  "completed",
                "pages":   len(documents),
                "chunks":  stats["added"],
                "skipped": stats["skipped"],
            })

            logger.info(
                "Job %s done — pages=%d added=%d skipped=%d",
                job_id, len(documents), stats["added"], stats["skipped"],
            )

        except Exception as exc:
            logger.exception("Job %s failed: %s", job_id, exc)
            update_job(job_id, {"status": "failed", "error": str(exc)})

        finally:
            document_queue.task_done()
