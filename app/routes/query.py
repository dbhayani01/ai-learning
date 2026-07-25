"""
Query routes — /ask and /job/{job_id} endpoints.
"""
import logging

import psutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import MIN_FREE_MB_QUERY
from fastapi.responses import StreamingResponse
from app.services.rag import answer_question_stream
from app.services.queue_manager import get_job

logger = logging.getLogger(__name__)
router = APIRouter(tags=["query"])


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, description="Question to ask")
    session_id: str = Field(..., description="Unique session ID for chat history")


@router.post("/ask", summary="Ask a question against ingested documents")
def ask(request: QuestionRequest):
    """
    Run the RAG pipeline and return an answer with source attribution.

    Memory guard: returns 503 if the server is memory-constrained.
    """
    free_mb = psutil.virtual_memory().available / 1024 / 1024
    if free_mb < MIN_FREE_MB_QUERY:
        raise HTTPException(
            status_code=503,
            detail=f"Server is busy (only {free_mb:.0f} MB free). Try again shortly.",
        )

    try:
        return StreamingResponse(
            answer_question_stream(request.question, request.session_id), 
            media_type="text/event-stream"
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("RAG pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail="An internal error occurred.")


@router.get("/job/{job_id}", summary="Check processing status of an uploaded document")
def job_status(job_id: str):
    """
    Poll the status of a document ingestion job.

    Status values: queued → processing → completed | failed
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


from app.services.history import get_history, clear_history

@router.get("/history/{session_id}", summary="Get chat history for a session")
def get_chat_history(session_id: str):
    """Retrieve chat history for the given session ID."""
    history = get_history(session_id)
    return {"messages": history}

@router.delete("/history/{session_id}", summary="Clear chat history")
def delete_chat_history(session_id: str):
    """Delete all chat history for the given session ID."""
    clear_history(session_id)
    return {"status": "cleared"}
