import time
import uuid
import psutil

from langchain_community.document_loaders import PyPDFLoader

from queue_manager import document_queue, jobs
from chunking.recursive import get_chunks
from vectordb.faiss_store import create_or_update_vector_store


def process_documents():

    while True:

        job_id, file_path = document_queue.get()

        jobs[job_id]["status"] = "processing"

        try:

            while (
                psutil.virtual_memory().available
                < 200 * 1024 * 1024
            ):
                time.sleep(10)

            loader = PyPDFLoader(file_path)

            documents = loader.load()

            chunks = get_chunks(documents)

            create_or_update_vector_store(chunks)

            jobs[job_id]["status"] = "completed"
            jobs[job_id]["pages"] = len(documents)
            jobs[job_id]["chunks"] = len(chunks)

        except Exception as e:

            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)

        finally:

            document_queue.task_done()
