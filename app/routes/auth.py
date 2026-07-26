"""
Authentication routes — /signup, /login, /me, /logout endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field

from app.services.history import create_user, verify_user, create_session, get_user_from_token, delete_session

router = APIRouter(tags=["auth"])

class AuthRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)

import uuid

def get_current_user(authorization: str = Header(None)):
    """Dependency to get the current authenticated user from Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = authorization.split(" ")[1]
    
    # Stateless guest token
    if token.startswith("guest_"):
        guest_id = token.split("_")[1]
        return {"id": guest_id, "username": "Guest", "role": "guest"}
        
    user = get_user_from_token(token)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    user["role"] = "user"
    return user

@router.post("/guest", summary="Get a guest token")
def guest_login():
    """Generates a stateless guest token so users can try the app without signing up."""
    guest_id = uuid.uuid4().hex
    return {"token": f"guest_{guest_id}", "username": "Guest", "role": "guest"}

from app.services.history import migrate_chat_sessions
from app.config import DOCUMENTS_DIR
from app.services.queue_manager import document_queue, set_job
import os
import shutil

def _migrate_guest(authorization: str, user_id: int):
    if not authorization or not authorization.startswith("Bearer guest_"):
        return
        
    guest_id = authorization.split(" ")[1].split("_")[1]
    
    # 1. Migrate Chat History
    migrate_chat_sessions(guest_id, user_id)
    
    # 2. Migrate Documents
    guest_dir = os.path.join(DOCUMENTS_DIR, str(guest_id))
    user_dir = os.path.join(DOCUMENTS_DIR, str(user_id))
    
    if os.path.exists(guest_dir):
        os.makedirs(user_dir, exist_ok=True)
        for filename in os.listdir(guest_dir):
            if filename.endswith(".pdf"):
                src = os.path.join(guest_dir, filename)
                dst = os.path.join(user_dir, filename)
                shutil.move(src, dst)
                
                # Re-queue for indexing since FAISS index is abandoned
                job_id = str(uuid.uuid4())
                size_mb = os.path.getsize(dst) / 1024 / 1024
                set_job(job_id, {
                    "status": "queued",
                    "filename": filename,
                    "size_mb": round(size_mb, 2),
                })
                document_queue.put((job_id, dst, user_id))
        
        # Clean up old guest dir (abandons FAISS index)
        shutil.rmtree(guest_dir, ignore_errors=True)

@router.post("/signup", summary="Register a new user")
def signup(request: AuthRequest, authorization: str = Header(None)):
    user_id = create_user(request.username, request.password)
    if not user_id:
        raise HTTPException(status_code=400, detail="Username already exists")
        
    _migrate_guest(authorization, user_id)
        
    token = create_session(user_id)
    return {"token": token, "username": request.username}

@router.post("/login", summary="Login a user")
def login(request: AuthRequest, authorization: str = Header(None)):
    user_id = verify_user(request.username, request.password)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
    _migrate_guest(authorization, user_id)
        
    token = create_session(user_id)
    return {"token": token, "username": request.username}

@router.get("/me", summary="Get current user details")
def me(user: dict = Depends(get_current_user)):
    return user

@router.post("/logout", summary="Logout user")
def logout(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        delete_session(token)
    return {"status": "logged out"}
