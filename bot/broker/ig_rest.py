from __future__ import annotations

import asyncio
import time
from datetime import datetime
from functools import partial, wraps
from typing import TypeVar, Callable, Any

import structlog
from trading_ig import IGService

from bot.broker.base import BrokerClient
from bot.broker.models import (
    Direction,
    MarketInfo,
    OHLCV,
    OrderRequest,
    OrderResult,
    Position,
)
from bot.config import settings

logger = structlog.get_logger()

T = TypeVar("T")


def auto_retry(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that retries broker calls on session errors with auto-reconnect."""

    @wraps(fn)
    async def wrapper(self: IGRestClient, *args: Any, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return await fn(self, *args, **kwargs)
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                # Quota/allowance errors are NOT retryable — raise immediately
                if "exceeded" in err_str or "allowance" in err_str:
                    raise
                is_session_error = any(
                    kw in err_str
                    for kw in ("invalid session", "not logged in", "unauthorized",
                               "client token", "security token", "401")
                )
                if is_session_error and attempt < self.MAX_RETRIES - 1:
                    logger.warning("ig_session_error_retrying", attempt=attempt + 1, error=str(e))
                    await asyncio.sleep(self.RETRY_DELAY)
                    await self.reconnect()
                else:
                    raise
        raise last_error  # type: ignore[misc]

    return wrapper


class IGRestClient(BrokerClient):
    """IG Markets REST API client wrapping trading_ig with auto-reconnect."""

    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds
    RECONNECT_COOLDOWN = 30  # minimum seconds between reconnections

    def __init__(self):
        self._ig: IGService | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = False
        self._last_reconnect: float = 0  # timestamp of last reconnect
        self._reconnect_count: int = 0

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous trading_ig call in a thread executor with timeout."""
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            self._loop.run_in_executor(None, partial(func, *args, **kwargs)),
            timeout=30,  # 30s timeout to prevent hanging on IG API
        )

    async def connect(self) -> None:
        self._ig = IGService(
            settings.ig.username,
            settings.ig.password,
            settings.ig.api_key,
            settings.ig.acc_type,
            use_rate_limiter=True,
        )
        await self._run_sync(self._ig.create_session, version="2")
        self._connected = True
        logger.info("ig_connected", acc_type=settings.ig.acc_type)

    async def reconnect(self) -> None:
        """Re-establish the IG session after expiry or error (with cooldown)."""
        now = time.monotonic()
        if now - self._last_reconnect < self.RECONNECT_COOLDOWN:
            logger.debug("ig_reconnect_cooldown", wait=int(self.RECONNECT_COOLDOWN - (now - self._last_reconnect)))
            return  # skip, too soon since last reconnect
        self._last_reconnect = now
        self._reconnect_count += 1
        logger.info("ig_reconnecting", attempt=self._reconnect_count)
        self._connected = False
        try:
            if self._ig:
                await self._run_sync(self._ig.logout)
        except Exception:
            pass
        await self.connect()
        # Notify via Telegram on reconnection
        try:
            from bot.notifications import send_message
            await send_message(
                f"\U0001f504 <b>IG Session Reconnected</b>\n"
                f"Reconnection #{self._reconnect_count}"
            )
        except Exception:
            pass

    async def heartbeat(self) -> bool:
        """Check if the IG session is alive. Returns True if healthy, reconnects if not."""
        if not self._connected or not self._ig:
            return False
        try:
            await self._run_sync(self._ig.fetch_accounts)
            return True
        except Exception as e:
            logger.warning("ig_heartbeat_failed", error=str(e))
            try:
                await self.reconnect()
                return self._connected
            except Exception:
                return False

    async def disconnect(self) -> None:
        self._connected = False
        if self._ig:
            try:
                await self._run_sync(self._ig.logout)
            except Exception:
                pass
            self._ig = None
            logger.info("ig_disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ig is not None

    @auto_retry
    async def search_markets(self, term: str) -> list[MarketInfo]:
        result = await self._run_sync(self._ig.search_markets, term)
        markets = []
        for _, row in result.iterrows():
            markets.append(
                MarketInfo(
                    epic=row["epic"],
                    instrument_name=row.get("instrumentName", ""),
                    instrument_type=row.get("instrumentType", ""),
                    expiry=row.get("expiry", "-"),
                    bid=float(row.get("bid", 0)),
                    offer=float(row.get("offer", 0)),
                    high=float(row.get("high", 0)),
                    low=float(row.get("low", 0)),
                    percentage_change=float(row.get("percentageChange", 0)),
                    market_status=row.get("marketStatus", ""),
                )
            )
        return markets

    @auto_retry
    async def get_market_info(self, epic: str) -> MarketInfo:
        result = await self._run_sync(self._ig.fetch_market_by_epic, epic)
        inst = result["instrument"]
        snap = result["snapshot"]
        dealing = result["dealingRules"]
        return MarketInfo(
            epic=epic,
            instrument_name=inst.get("name", ""),
            instrument_type=inst.get("type", ""),
            expiry=inst.get("expiry", "-"),
            bid=float(snap.get("bid", 0)),
            offer=float(snap.get("offer", 0)),
            high=float(snap.get("high", 0)),
            low=float(snap.get("low", 0)),
            percentage_change=float(snap.get("percentageChange", 0)),
            market_status=snap.get("marketStatus", ""),
            min_deal_size=float(dealing.get("minDealSize", {}).get("value", 0)),
            currency=inst.get("currencies", [{}])[0].get("code", "EUR") if inst.get("currencies") else "EUR",
            lot_size=float(inst.get("lotSize", 1)),
            scaling_factor=float(inst.get("scalingFactor", 1)),
        )

    @auto_retry
    async def get_historical_prices(
        self, epic: str, resolution: str, num_points: int
    ) -> list[OHLCV]:
        # Use direct REST API call (trading_ig's DataFrame path breaks with pandas 2.2+)
        raw = await self._run_sync(
            self._fetch_prices_raw, epic, resolution, num_points
        )
        return self._parse_prices_json(raw)

    def _parse_prices_df(self, prices) -> list[OHLCV]:
        """Parse prices from a trading_ig DataFrame."""
        bars = []
        for _, row in prices.iterrows():
            bars.append(
                OHLCV(
                    time=row.name if isinstance(row.name, datetime) else datetime.now(),
                    open=float(row.get(("mid", "Open"), row.get(("bid", "Open"), 0))),
                    high=float(row.get(("mid", "High"), row.get(("bid", "High"), 0))),
                    low=float(row.get(("mid", "Low"), row.get(("bid", "Low"), 0))),
                    close=float(row.get(("mid", "Close"), row.get(("bid", "Close"), 0))),
                    volume=int(row.get(("last", "Volume"), 0)),
                )
            )
        return bars

    def _fetch_prices_raw(self, epic: str, resolution: str, num_points: int) -> list[dict]:
        """Fetch historical prices directly from IG REST API (bypasses trading_ig DataFrame)."""
        # IG REST API v3: GET /prices/{epic}?resolution=X&max=N&pageSize=0
        url = f"/prices/{epic}"
        params = {"resolution": resolution, "max": num_points, "pageSize": 0}
        session = self._ig.session
        base_url = self._ig.BASE_URL
        old_version = session.headers.get("VERSION")
        session.headers["VERSION"] = "3"
        try:
            response = session.get(f"{base_url}{url}", params=params)
            if response.status_code in (401, 403):
                body = response.text[:200]
                raise Exception(f"IG API error ({response.status_code}): {body}")
            response.raise_for_status()
            data = response.json()
            return data.get("prices", [])
        finally:
            if old_version:
                session.headers["VERSION"] = old_version
            else:
                session.headers.pop("VERSION", None)

    @staticmethod
    def _parse_prices_json(prices: list[dict]) -> list[OHLCV]:
        """Parse raw JSON price data from IG REST API into OHLCV objects."""
        bars = []
        for p in prices:
            snap_time = p.get("snapshotTime", "")
            try:
                dt = datetime.strptime(snap_time, "%Y/%m/%d %H:%M:%S")
            except (ValueError, TypeError):
                try:
                    dt = datetime.strptime(snap_time, "%Y-%m-%dT%H:%M:%S")
                except (ValueError, TypeError):
                    dt = datetime.now()

            mid = p.get("closePrice") or p.get("openPrice") or {}
            bid = mid  # fallback
            high_p = p.get("highPrice") or {}
            low_p = p.get("lowPrice") or {}
            open_p = p.get("openPrice") or {}
            close_p = p.get("closePrice") or {}

            bars.append(
                OHLCV(
                    time=dt,
                    open=float(open_p.get("mid") or open_p.get("bid") or 0),
                    high=float(high_p.get("mid") or high_p.get("bid") or 0),
                    low=float(low_p.get("mid") or low_p.get("bid") or 0),
                    close=float(close_p.get("mid") or close_p.get("bid") or 0),
                    volume=int(p.get("lastTradedVolume", 0)),
                )
            )
        return bars

    @auto_retry
    async def get_client_sentiment(self, market_id: str) -> dict:
        """Fetch client sentiment for a market (% long vs short)."""
        raw = await self._run_sync(self._fetch_sentiment_raw, market_id)
        return raw

    def _fetch_sentiment_raw(self, market_id: str) -> dict:
        """Direct REST call to /clientsentiment/{marketId}."""
        session = self._ig.session
        base_url = self._ig.BASE_URL
        old_version = session.headers.get("VERSION")
        session.headers["VERSION"] = "1"
        try:
            response = session.get(f"{base_url}/clientsentiment/{market_id}")
            response.raise_for_status()
            data = response.json()
            return {
                "market_id": data.get("marketId", market_id),
                "long_pct": float(data.get("longPositionPercentage", 0)),
                "short_pct": float(data.get("shortPositionPercentage", 0)),
            }
        except Exception:
            return {"market_id": market_id, "long_pct": 0, "short_pct": 0}
        finally:
            if old_version:
                session.headers["VERSION"] = old_version
            else:
                session.headers.pop("VERSION", None)

    @auto_retry
    async def get_open_positions(self) -> list[Position]:
        result = await self._run_sync(self._ig.fetch_open_positions)
        positions = []
        for _, row in result.iterrows():
            positions.append(
                Position(
                    deal_id=row.get("dealId", ""),
                    epic=row.get("epic", ""),
                    direction=Direction(row.get("direction", "BUY")),
                    size=float(row.get("dealSize", row.get("size", 0))),
                    open_level=float(row.get("openLevel", row.get("level", 0))),
                    stop_level=float(row["stopLevel"]) if row.get("stopLevel") else None,
                    limit_level=float(row["limitLevel"]) if row.get("limitLevel") else None,
                    currency=row.get("currency", "EUR"),
                    profit=float(row.get("profit", 0)),
                )
            )
        return positions

    @auto_retry
    async def open_position(self, order: OrderRequest) -> OrderResult:
        result = await self._run_sync(
            self._ig.create_open_position,
            currency_code=order.currency,
            direction=order.direction.value,
            epic=order.epic,
            order_type=order.order_type.value,
            expiry=order.expiry,
            force_open=order.force_open,
            guaranteed_stop=order.guaranteed_stop,
            size=order.size,
            stop_distance=order.stop_distance,
            limit_distance=order.limit_distance,
            level=order.level,
            limit_level=None,
            quote_id=None,
            stop_level=None,
            trailing_stop=False,
            trailing_stop_increment=None,
        )
        deal_ref = result.get("dealReference", "")
        logger.info("position_opened", epic=order.epic, direction=order.direction.value, size=order.size, deal_ref=deal_ref)

        # Confirm the deal
        confirm = await self._run_sync(self._ig.fetch_deal_by_deal_reference, deal_ref)
        return OrderResult(
            deal_reference=deal_ref,
            deal_id=confirm.get("dealId"),
            status=confirm.get("dealStatus", "UNKNOWN"),
            reason=confirm.get("reason", ""),
            affected_deals=confirm.get("affectedDeals", []),
        )

    @auto_retry
    async def close_position(self, deal_id: str, direction: str, size: float) -> OrderResult:
        close_direction = "SELL" if direction == "BUY" else "BUY"
        result = await self._run_sync(
            self._ig.close_open_position,
            deal_id=deal_id,
            direction=close_direction,
            order_type="MARKET",
            size=size,
        )
        deal_ref = result.get("dealReference", "")
        logger.info("position_closed", deal_id=deal_id, deal_ref=deal_ref)

        confirm = await self._run_sync(self._ig.fetch_deal_by_deal_reference, deal_ref)
        return OrderResult(
            deal_reference=deal_ref,
            deal_id=confirm.get("dealId"),
            status=confirm.get("dealStatus", "UNKNOWN"),
            reason=confirm.get("reason", ""),
        )

    @auto_retry
    async def amend_position(
        self, deal_id: str, stop_level: float | None = None, limit_level: float | None = None
    ) -> OrderResult:
        result = await self._run_sync(
            self._ig.update_open_position,
            deal_id=deal_id,
            stop_level=stop_level,
            limit_level=limit_level,
        )
        deal_ref = result.get("dealReference", "")
        return OrderResult(deal_reference=deal_ref, status="AMENDED")

    @auto_retry
    async def get_account_balance(self) -> dict:
        accounts = await self._run_sync(self._ig.fetch_accounts)
        for _, acc in accounts.iterrows():
            if acc.get("accountId") == settings.ig.acc_number or acc.get("preferred", False):
                return {
                    "balance": float(acc.get("balance", 0)),
                    "deposit": float(acc.get("deposit", 0)),
                    "profit_loss": float(acc.get("profitLoss", 0)),
                    "available": float(acc.get("available", 0)),
                    "currency": acc.get("currency", "EUR"),
                }
        return {}
