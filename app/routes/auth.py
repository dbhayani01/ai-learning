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

def get_current_user(authorization: str = Header(None)):
    """Dependency to get the current authenticated user from Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = authorization.split(" ")[1]
    user = get_user_from_token(token)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    return user

@router.post("/signup", summary="Register a new user")
def signup(request: AuthRequest):
    user_id = create_user(request.username, request.password)
    if not user_id:
        raise HTTPException(status_code=400, detail="Username already exists")
        
    token = create_session(user_id)
    return {"token": token, "username": request.username}

@router.post("/login", summary="Login a user")
def login(request: AuthRequest):
    user_id = verify_user(request.username, request.password)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
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
