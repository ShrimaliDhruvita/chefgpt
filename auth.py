from fastapi import HTTPException, Cookie, Response
from typing import Optional, Dict, Any
from .database import db

def get_current_user(session_token: Optional[str] = Cookie(None)) -> Optional[Dict[str, Any]]:
    if not session_token:
        return None
    return db.get_user_by_session(session_token)

def require_auth(session_token: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

def login_user(response: Response, email: str, password: str) -> Dict[str, Any]:
    user = db.verify_user(email, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    session_token = db.create_session(user["id"])
    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=7*24*60*60,  # 7 days
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )
    return user

def logout_user(response: Response, session_token: Optional[str] = Cookie(None)):
    if session_token:
        db.delete_session(session_token)
    response.delete_cookie("session_token")