from __future__ import annotations

from datetime import datetime

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.broker.base import BrokerClient
from bot.broker.models import OHLCV

logger = structlog.get_logger()


async def fetch_and_store_historical(
    broker: BrokerClient,
    session: AsyncSession,
    epic: str,
    resolution: str,
    num_points: int,
) -> pd.DataFrame:
    """Fetch historical prices from broker and store in TimescaleDB."""
    bars = await broker.get_historical_prices(epic, resolution, num_points)

    if not bars:
        logger.warning("no_historical_data", epic=epic, resolution=resolution)
        return pd.DataFrame()

    # Store in DB
    for bar in bars:
        await session.execute(
            text("""
                INSERT INTO ohlcv (time, epic, resolution, open, high, low, close, volume)
                VALUES (:time, :epic, :resolution, :open, :high, :low, :close, :volume)
                ON CONFLICT DO NOTHING
            """),
            {
                "time": bar.time,
                "epic": epic,
                "resolution": resolution,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            },
        )
    await session.commit()
    logger.info("historical_stored", epic=epic, resolution=resolution, bars=len(bars))

    return bars_to_dataframe(bars)


async def load_from_db(
    session: AsyncSession,
    epic: str,
    resolution: str,
    limit: int = 500,
) -> pd.DataFrame:
    """Load historical OHLCV data from TimescaleDB."""
    result = await session.execute(
        text("""
            SELECT time, open, high, low, close, volume
            FROM ohlcv
            WHERE epic = :epic AND resolution = :resolution
            ORDER BY time DESC
            LIMIT :limit
        """),
        {"epic": epic, "resolution": resolution, "limit": limit},
    )
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df = df.sort_values("time").reset_index(drop=True)
    df.set_index("time", inplace=True)
    return df


def bars_to_dataframe(bars: list[OHLCV]) -> pd.DataFrame:
    """Convert list of OHLCV bars to pandas DataFrame."""
    if not bars:
        return pd.DataFrame()

    data = [
        {
            "time": bar.time,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]
    df = pd.DataFrame(data)
    df.set_index("time", inplace=True)
    df.sort_index(inplace=True)
    return df
