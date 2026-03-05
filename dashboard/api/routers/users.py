from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser
from dashboard.api.auth.jwt import get_current_user, hash_password
from dashboard.api.deps import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


class UserListItem(BaseModel):
    id: int
    username: str
    created_at: datetime | None = None


class CreateUserRequest(BaseModel):
    username: str
    password: str


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.get("", response_model=list[UserListItem])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """List all admin users."""
    result = await db.execute(
        select(AdminUser).order_by(AdminUser.created_at)
    )
    users = result.scalars().all()
    return [
        UserListItem(id=u.id, username=u.username, created_at=u.created_at)
        for u in users
    ]


@router.post("", response_model=UserListItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Create a new admin user."""
    if len(req.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )

    # Check duplicate username
    existing = await db.execute(
        select(AdminUser).where(AdminUser.username == req.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{req.username}' already exists",
        )

    user = AdminUser(
        username=req.username,
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserListItem(id=user.id, username=user.username, created_at=user.created_at)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Delete an admin user. Cannot delete yourself or the last admin."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400, detail="Cannot delete your own account"
        )

    # Check it's not the last user
    count_result = await db.execute(select(func.count(AdminUser.id)))
    if count_result.scalar_one() <= 1:
        raise HTTPException(
            status_code=400, detail="Cannot delete the last admin account"
        )

    target = await db.get(AdminUser, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(target)
    await db.commit()
    return {"message": f"User '{target.username}' deleted"}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Reset another user's password."""
    if len(req.new_password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )

    target = await db.get(AdminUser, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.hashed_password = hash_password(req.new_password)
    await db.commit()
    return {"message": f"Password reset for '{target.username}'"}
