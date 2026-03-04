from __future__ import annotations

import logging
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class IGSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IG_")

    api_key: str = ""
    username: str = ""
    password: str = ""
    acc_type: str = Field(default="DEMO", pattern="^(DEMO|LIVE)$")
    acc_number: str = ""


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "timescaledb"
    port: int = 5432
    name: str = "trading_db"
    user: str = "trader"
    password: str = ""

    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = "redis"
    port: int = 6379
    password: str = ""

    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/0"


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BOT_")

    log_level: str = "INFO"
    max_daily_loss: float = 500.0
    max_position_size: float = 10.0
    max_open_positions: int = 5
    max_positions_per_epic: int = 1
    max_risk_per_trade_pct: float = 2.0
    default_stop_distance: int = 20
    default_limit_distance: int = 40


class DashboardSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DASHBOARD_")

    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = "change-me"


class Settings(BaseSettings):
    ig: IGSettings = IGSettings()
    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    bot: BotSettings = BotSettings()
    dashboard: DashboardSettings = DashboardSettings()


settings = Settings()


# ---------------------------------------------------------------------------
# Load runtime settings from the database (app_settings table)
# ---------------------------------------------------------------------------

# Mapping: DB key -> (settings sub-object attr, field name, type cast)
_DB_KEY_MAP: dict[str, tuple[str, str, type]] = {
    "ig_api_key": ("ig", "api_key", str),
    "ig_username": ("ig", "username", str),
    "ig_password": ("ig", "password", str),
    "ig_acc_type": ("ig", "acc_type", str),
    "ig_acc_number": ("ig", "acc_number", str),
    "bot_max_daily_loss": ("bot", "max_daily_loss", float),
    "bot_max_position_size": ("bot", "max_position_size", float),
    "bot_max_open_positions": ("bot", "max_open_positions", int),
    "bot_max_positions_per_epic": ("bot", "max_positions_per_epic", int),
    "bot_max_risk_per_trade_pct": ("bot", "max_risk_per_trade_pct", float),
    "bot_default_stop_distance": ("bot", "default_stop_distance", int),
    "bot_default_limit_distance": ("bot", "default_limit_distance", int),
    "bot_log_level": ("bot", "log_level", str),
}


async def load_settings_from_db() -> None:
    """Load IG and bot settings from the app_settings DB table.

    Encrypted values (IG credentials) are decrypted transparently.
    This must be called after the async engine is available.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from bot.db.models import AppSetting
    from bot.db.session import async_session_factory
    from dashboard.api.auth.crypto import decrypt

    async with async_session_factory() as session:
        result = await session.execute(select(AppSetting))
        rows: list[AppSetting] = list(result.scalars().all())

    applied = 0
    for row in rows:
        mapping = _DB_KEY_MAP.get(row.key)
        if mapping is None:
            continue

        section_attr, field_name, cast_fn = mapping
        raw_value = row.value
        if not raw_value:
            continue

        # Decrypt if needed
        if row.encrypted:
            try:
                raw_value = decrypt(raw_value)
            except Exception:
                log.warning("Failed to decrypt setting %s, skipping", row.key)
                continue

        try:
            section = getattr(settings, section_attr)
            setattr(section, field_name, cast_fn(raw_value))
            applied += 1
        except Exception as exc:
            log.warning("Failed to apply DB setting %s: %s", row.key, exc)

    log.info("Loaded %d settings from database", applied)
