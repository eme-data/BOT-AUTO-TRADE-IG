from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser
from dashboard.api.auth.jwt import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from dashboard.api.deps import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---- Rate limiting for login ----
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300  # 5 minutes
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str) -> None:
    """Raise 429 if too many login attempts from this IP."""
    now = time.monotonic()
    attempts = _login_attempts[client_ip]
    _login_attempts[client_ip] = [t for t in attempts if now - t < _WINDOW_SECONDS]
    if len(_login_attempts[client_ip]) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {_WINDOW_SECONDS // 60} minutes.",
        )


def _record_attempt(client_ip: str) -> None:
    _login_attempts[client_ip].append(time.monotonic())


def _clear_attempts(client_ip: str) -> None:
    _login_attempts.pop(client_ip, None)


class SetupRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    username: str
    needs_setup: bool = False


@router.get("/status")
async def auth_status(db: AsyncSession = Depends(get_db)):
    """Check if initial setup is needed (no admin user exists)."""
    result = await db.execute(select(func.count(AdminUser.id)))
    count = result.scalar_one()
    return {"needs_setup": count == 0}


@router.post("/setup", response_model=TokenResponse)
async def setup(req: SetupRequest, db: AsyncSession = Depends(get_db)):
    """Create the initial admin account. Only works if no admin exists."""
    result = await db.execute(select(func.count(AdminUser.id)))
    if result.scalar_one() > 0:
        raise HTTPException(status_code=400, detail="Admin account already exists")

    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = AdminUser(username=req.username, hashed_password=hash_password(req.password))
    db.add(user)
    await db.commit()

    token = create_access_token(req.username)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login with username/password, returns JWT token. Rate limited."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    result = await db.execute(select(AdminUser).where(AdminUser.username == form.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.hashed_password):
        _record_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _clear_attempts(client_ip)
    token = create_access_token(user.username)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(user: AdminUser = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserResponse(username=user.username)


@router.post("/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change admin password."""
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    user.hashed_password = hash_password(new_password)
    await db.commit()
    return {"message": "Password changed successfully"}
