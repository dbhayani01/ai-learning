"""
Upload routes — /upload endpoint.
"""
import os
import uuid
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.config import DOCUMENTS_DIR
from app.services.queue_manager import document_queue, set_job

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

ALLOWED_EXTENSIONS = {".pdf"}
MAX_FILE_SIZE_MB   = 50


from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.routes.auth import get_current_user

@router.post("/upload", summary="Upload a PDF for ingestion")
async def upload_pdf(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """
    Accept a PDF file, save it to disk, enqueue for background ingestion.

    Returns:
        job_id to poll via GET /job/{job_id}
    """
    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Only PDF files accepted (got {ext})")

    content = await file.read()

    size_mb = len(content) / 1024 / 1024
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Max is {MAX_FILE_SIZE_MB} MB.",
        )

    # Check limits based on role
    user_docs_dir = os.path.join(DOCUMENTS_DIR, str(user["id"]))
    os.makedirs(user_docs_dir, exist_ok=True)
    
    existing_files = [f for f in os.listdir(user_docs_dir) if f.endswith(".pdf")]
    max_files = 3 if user.get("role") == "guest" else 10
    
    if len(existing_files) >= max_files:
        raise HTTPException(
            status_code=403,
            detail="LIMIT_REACHED: You have reached the maximum number of PDF uploads."
        )

    # Save to disk
    safe_name = os.path.basename(file.filename)
    file_path = os.path.join(user_docs_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    # Register job and enqueue
    job_id = str(uuid.uuid4())
    set_job(job_id, {
        "status":   "queued",
        "filename": safe_name,
        "size_mb":  round(size_mb, 2),
    })
    document_queue.put((job_id, file_path, user["id"]))

    logger.info("Uploaded %s (%.1f MB) → job %s for user %s", safe_name, size_mb, job_id, user["id"])

    return {
        "message":  "File uploaded and queued for processing.",
        "job_id":   job_id,
        "filename": safe_name,
        "size_mb":  round(size_mb, 2),
        "status":   "queued",
    }


@router.get("/documents", summary="List uploaded documents and limits")
def list_documents(user: dict = Depends(get_current_user)):
    user_docs_dir = os.path.join(DOCUMENTS_DIR, str(user["id"]))
    
    existing_files = []
    if os.path.exists(user_docs_dir):
        existing_files = [f for f in os.listdir(user_docs_dir) if f.endswith(".pdf")]
        
    max_files = 3 if user.get("role") == "guest" else 10
    
    return {
        "documents": existing_files,
        "usage": len(existing_files),
        "limit": max_files
    }


from vectordb.faiss_store import delete_document_from_index

@router.delete("/documents/{filename}", summary="Delete a document and its FAISS index")
def delete_document(filename: str, user: dict = Depends(get_current_user)):
    user_docs_dir = os.path.join(DOCUMENTS_DIR, str(user["id"]))
    safe_name = os.path.basename(filename)
    file_path = os.path.join(user_docs_dir, safe_name)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Document not found.")
        
    # Delete the physical file
    os.remove(file_path)
    
    # Delete from FAISS
    try:
        delete_document_from_index(safe_name, user["id"])
    except Exception as e:
        logger.error(f"Error deleting document from FAISS: {e}")
        # We continue even if FAISS deletion fails, since the file is already gone
    
    return {"message": f"Deleted {safe_name}"}
