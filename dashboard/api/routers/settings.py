from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser, AppSetting
from dashboard.api.auth.crypto import decrypt, encrypt
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Keys that must be stored encrypted
ENCRYPTED_KEYS = {"ig_api_key", "ig_username", "ig_password"}


class SettingResponse(BaseModel):
    key: str
    value: str
    category: str
    encrypted: bool


class SettingsUpdateRequest(BaseModel):
    settings: dict[str, str]


class IGTestRequest(BaseModel):
    api_key: str = ""
    username: str = ""
    password: str = ""
    acc_type: str = "DEMO"


class IGTestResponse(BaseModel):
    success: bool
    message: str
    accounts: list[dict] = []


# ---- Read settings by category ----

@router.get("/{category}", response_model=list[SettingResponse])
async def get_settings_by_category(
    category: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get all settings in a category. Encrypted values are masked."""
    result = await db.execute(
        select(AppSetting).where(AppSetting.category == category)
    )
    settings_list = result.scalars().all()

    return [
        SettingResponse(
            key=s.key,
            value=_mask(s.value) if s.encrypted else s.value,
            category=s.category,
            encrypted=s.encrypted,
        )
        for s in settings_list
    ]


@router.get("", response_model=list[SettingResponse])
async def get_all_settings(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Get all settings. Encrypted values are masked."""
    result = await db.execute(select(AppSetting))
    settings_list = result.scalars().all()

    return [
        SettingResponse(
            key=s.key,
            value=_mask(s.value) if s.encrypted else s.value,
            category=s.category,
            encrypted=s.encrypted,
        )
        for s in settings_list
    ]


# ---- Update settings ----

@router.put("", response_model=list[SettingResponse])
async def update_settings(
    req: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Update multiple settings at once."""
    updated = []
    for key, value in req.settings.items():
        result = await db.execute(select(AppSetting).where(AppSetting.key == key))
        setting = result.scalar_one_or_none()

        if setting is None:
            # Auto-detect category from key prefix
            category = _category_from_key(key)
            is_encrypted = key in ENCRYPTED_KEYS
            setting = AppSetting(
                key=key,
                value=encrypt(value) if is_encrypted else value,
                encrypted=is_encrypted,
                category=category,
            )
            db.add(setting)
        else:
            # Don't overwrite encrypted value if sent masked
            if setting.encrypted and value.startswith("***"):
                continue
            setting.value = encrypt(value) if setting.encrypted else value

        updated.append(
            SettingResponse(
                key=setting.key,
                value=_mask(setting.value) if setting.encrypted else setting.value,
                category=setting.category,
                encrypted=setting.encrypted,
            )
        )

    await db.commit()
    return updated


# ---- Test IG connection ----

@router.post("/ig/test", response_model=IGTestResponse)
async def test_ig_connection(
    req: IGTestRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Test IG Markets connection with provided or stored credentials."""
    api_key = req.api_key
    username = req.username
    password = req.password
    acc_type = req.acc_type

    # If fields empty, load from stored settings
    if not api_key or not username or not password:
        stored = await _get_ig_credentials(db)
        api_key = api_key or stored.get("api_key", "")
        username = username or stored.get("username", "")
        password = password or stored.get("password", "")
        acc_type = acc_type or stored.get("acc_type", "DEMO")

    if not all([api_key, username, password]):
        return IGTestResponse(success=False, message="Missing credentials. Please fill in all IG fields.")

    try:
        from trading_ig import IGService

        ig = IGService(username, password, api_key, acc_type, use_rate_limiter=True)
        ig.create_session(version="2")
        accounts = ig.fetch_accounts()
        ig.logout()

        account_list = []
        for _, row in accounts.iterrows():
            account_list.append({
                "accountId": row.get("accountId", ""),
                "accountName": row.get("accountName", ""),
                "accountType": row.get("accountType", ""),
                "currency": row.get("currency", ""),
                "balance": float(row.get("balance", 0)),
                "preferred": bool(row.get("preferred", False)),
            })

        return IGTestResponse(
            success=True,
            message=f"Connected successfully. Found {len(account_list)} account(s).",
            accounts=account_list,
        )
    except Exception as e:
        return IGTestResponse(success=False, message=f"Connection failed: {str(e)}")


# ---- Helpers ----

async def _get_ig_credentials(db: AsyncSession) -> dict:
    """Load IG credentials from app_settings, decrypting as needed."""
    keys = ["ig_api_key", "ig_username", "ig_password", "ig_acc_type", "ig_acc_number"]
    result = await db.execute(select(AppSetting).where(AppSetting.key.in_(keys)))
    settings_map = {s.key: s for s in result.scalars().all()}

    return {
        "api_key": decrypt(settings_map["ig_api_key"].value) if "ig_api_key" in settings_map else "",
        "username": decrypt(settings_map["ig_username"].value) if "ig_username" in settings_map else "",
        "password": decrypt(settings_map["ig_password"].value) if "ig_password" in settings_map else "",
        "acc_type": settings_map.get("ig_acc_type", AppSetting(key="", value="DEMO", encrypted=False, category="ig")).value,
        "acc_number": settings_map.get("ig_acc_number", AppSetting(key="", value="", encrypted=False, category="ig")).value,
    }


async def get_ig_credentials(db: AsyncSession) -> dict:
    """Public helper for other modules to access IG credentials."""
    return await _get_ig_credentials(db)


def _mask(value: str) -> str:
    """Mask an encrypted value for display."""
    if not value:
        return ""
    return "***configured***"


def _category_from_key(key: str) -> str:
    if key.startswith("ig_"):
        return "ig"
    if key.startswith("bot_"):
        if "loss" in key or "size" in key or "risk" in key or "stop" in key or "limit" in key or "position" in key:
            return "risk"
        return "general"
    return "general"
