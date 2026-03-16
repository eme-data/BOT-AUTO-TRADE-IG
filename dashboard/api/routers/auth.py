from __future__ import annotations

import base64
import io
import time
from collections import defaultdict

import pyotp
import qrcode
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
    mfa_required: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str = ""


class UserResponse(BaseModel):
    username: str
    role: str = "admin"
    needs_setup: bool = False
    mfa_enabled: bool = False


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
    """Login with username/password + optional TOTP code. Rate limited."""
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

    # MFA check
    if user.totp_secret:
        # TOTP code comes in the OAuth2 scopes field or we need a separate flow
        # For OAuth2 form compatibility, we accept the TOTP code in the 'client_secret' field
        totp_code = form.client_secret or ""
        if not totp_code:
            # Signal that MFA is required but credentials are valid
            _clear_attempts(client_ip)
            return TokenResponse(access_token="", mfa_required=True)

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(totp_code, valid_window=1):
            _record_attempt(client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TOTP code",
                headers={"WWW-Authenticate": "Bearer"},
            )

    _clear_attempts(client_ip)
    token = create_access_token(user.username, getattr(user, "role", "admin"))
    return TokenResponse(access_token=token)


@router.post("/login-mfa", response_model=TokenResponse)
async def login_mfa(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Login with username + password + TOTP code (JSON body)."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    result = await db.execute(select(AdminUser).where(AdminUser.username == req.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        _record_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if user.totp_secret:
        if not req.totp_code:
            return TokenResponse(access_token="", mfa_required=True)

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(req.totp_code, valid_window=1):
            _record_attempt(client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TOTP code",
            )

    _clear_attempts(client_ip)
    token = create_access_token(user.username, getattr(user, "role", "admin"))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(user: AdminUser = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserResponse(
        username=user.username,
        role=getattr(user, "role", "admin"),
        mfa_enabled=bool(user.totp_secret),
    )


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change admin password."""
    if not verify_password(req.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    user.hashed_password = hash_password(req.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}


# ---- MFA Setup Endpoints ----

@router.post("/mfa/setup")
async def mfa_setup(
    user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new TOTP secret and return QR code for authenticator app."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=user.username,
        issuer_name="Altior Trading Bot",
    )

    # Generate QR code as base64 PNG
    img = qrcode.make(provisioning_uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()

    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_b64}",
        "provisioning_uri": provisioning_uri,
    }


class MFAConfirmRequest(BaseModel):
    secret: str
    totp_code: str


@router.post("/mfa/confirm")
async def mfa_confirm(
    req: MFAConfirmRequest,
    user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm MFA setup by verifying a TOTP code, then persist the secret."""
    totp = pyotp.TOTP(req.secret)
    if not totp.verify(req.totp_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid TOTP code. Please try again.")

    user.totp_secret = req.secret
    await db.commit()
    return {"message": "MFA enabled successfully", "mfa_enabled": True}


@router.post("/mfa/disable")
async def mfa_disable(
    user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable MFA for current user."""
    user.totp_secret = None
    await db.commit()
    return {"message": "MFA disabled", "mfa_enabled": False}


@router.get("/mfa/status")
async def mfa_status(user: AdminUser = Depends(get_current_user)):
    """Check if MFA is enabled for current user."""
    return {"mfa_enabled": bool(user.totp_secret)}
