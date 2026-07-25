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
from fastapi import Depends
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["query"])


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, description="Question to ask")
    session_id: str | None = Field(None, description="Optional chat session ID")

@router.post("/ask", summary="Ask a question against ingested documents")
def ask(request: QuestionRequest, user: dict = Depends(get_current_user)):
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
        from app.services.history import create_chat_session
        
        # Auto-create session if None
        session_id = request.session_id
        if not session_id:
            title = " ".join(request.question.split()[:4]) + "..."
            session_id = create_chat_session(user["id"], title)

        return StreamingResponse(
            answer_question_stream(request.question, user["id"], session_id), 
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


from app.services.history import get_history, delete_chat_session, get_chat_sessions

@router.get("/sessions", summary="Get chat sessions for current user")
def get_sessions(user: dict = Depends(get_current_user)):
    """Retrieve all chat sessions for the logged-in user."""
    return {"sessions": get_chat_sessions(user["id"])}

@router.get("/history", summary="Get chat history for a session")
def get_chat_history(session_id: str, user: dict = Depends(get_current_user)):
    """Retrieve chat history for a specific session."""
    history = get_history(session_id)
    return {"messages": history}

@router.delete("/history", summary="Delete a chat session")
def delete_chat_history(session_id: str, user: dict = Depends(get_current_user)):
    """Delete a specific chat session."""
    delete_chat_session(session_id)
    return {"status": "cleared"}
