"""
Shared in-memory queue and job registry.
Thread-safe via Queue's built-in lock; jobs dict protected by RLock.
"""
import threading
from queue import Queue

# Document processing queue — tuples of (job_id, file_path)
document_queue: Queue = Queue()

# Job registry — keyed by job_id UUID string
jobs: dict = {}
_jobs_lock = threading.RLock()


def set_job(job_id: str, data: dict) -> None:
    with _jobs_lock:
        jobs[job_id] = data


def update_job(job_id: str, updates: dict) -> None:
    with _jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(updates)


def get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        return jobs.get(job_id)
