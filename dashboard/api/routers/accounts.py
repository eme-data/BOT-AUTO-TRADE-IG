"""Multi-account IG management API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser, IGAccount
from dashboard.api.auth.crypto import decrypt, encrypt
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db, get_redis

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    label: str
    api_key: str
    username: str
    password: str
    acc_type: str = "LIVE"
    acc_number: str = ""


class AccountResponse(BaseModel):
    id: int
    label: str
    username: str
    acc_type: str
    acc_number: str
    is_active: bool


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """List all configured IG accounts."""
    result = await db.execute(select(IGAccount).order_by(IGAccount.created_at))
    accounts = result.scalars().all()
    return [
        AccountResponse(
            id=a.id,
            label=a.label,
            username=a.username,
            acc_type=a.acc_type,
            acc_number=a.acc_number,
            is_active=a.is_active,
        )
        for a in accounts
    ]


@router.post("", response_model=AccountResponse)
async def create_account(
    body: AccountCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Add a new IG account."""
    account = IGAccount(
        label=body.label,
        api_key=encrypt(body.api_key),
        username=body.username,
        password=encrypt(body.password),
        acc_type=body.acc_type,
        acc_number=body.acc_number,
        is_active=False,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return AccountResponse(
        id=account.id,
        label=account.label,
        username=account.username,
        acc_type=account.acc_type,
        acc_number=account.acc_number,
        is_active=account.is_active,
    )


@router.post("/{account_id}/activate")
async def activate_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Activate an account (deactivates all others) and update IG settings."""
    # Verify account exists
    result = await db.execute(select(IGAccount).where(IGAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Deactivate all, then activate this one
    await db.execute(update(IGAccount).values(is_active=False))
    account.is_active = True

    # Update app_settings with this account's credentials
    from bot.db.models import AppSetting

    settings_map = {
        "ig_api_key": (decrypt(account.api_key), True),
        "ig_username": (account.username, False),
        "ig_password": (account.password, True),  # already encrypted
        "ig_acc_type": (account.acc_type, False),
        "ig_acc_number": (account.acc_number, False),
    }

    for key, (value, is_encrypted) in settings_map.items():
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            if is_encrypted and key == "ig_api_key":
                existing.value = encrypt(value)
                existing.encrypted = True
            elif is_encrypted:
                existing.value = value  # already encrypted
                existing.encrypted = True
            else:
                existing.value = value
        else:
            db.add(AppSetting(
                key=key,
                value=encrypt(value) if is_encrypted and key == "ig_api_key" else value,
                encrypted=is_encrypted,
                category="ig",
            ))

    await db.commit()

    # Signal the bot to reload settings
    try:
        r = await get_redis()
        import json
        await r.publish("bot:commands", json.dumps({"command": "reload_settings"}))
    except Exception:
        pass

    return {"status": "activated", "label": account.label, "message": "Bot will reload settings automatically."}


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Delete an IG account."""
    result = await db.execute(select(IGAccount).where(IGAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.is_active:
        raise HTTPException(status_code=400, detail="Cannot delete the active account. Activate another account first.")
    await db.delete(account)
    await db.commit()
    return {"status": "deleted"}
