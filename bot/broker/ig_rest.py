from __future__ import annotations

import asyncio
from datetime import datetime
from functools import partial

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


class IGRestClient(BrokerClient):
    """IG Markets REST API client wrapping trading_ig."""

    def __init__(self):
        self._ig: IGService | None = None
        self._loop = asyncio.get_event_loop()

    def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous trading_ig call in a thread executor."""
        return self._loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def connect(self) -> None:
        self._ig = IGService(
            settings.ig.username,
            settings.ig.password,
            settings.ig.api_key,
            settings.ig.acc_type,
            use_rate_limiter=True,
        )
        await self._run_sync(self._ig.create_session, version="2")
        logger.info("ig_connected", acc_type=settings.ig.acc_type)

    async def disconnect(self) -> None:
        if self._ig:
            try:
                await self._run_sync(self._ig.logout)
            except Exception:
                pass
            self._ig = None
            logger.info("ig_disconnected")

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

    async def get_historical_prices(
        self, epic: str, resolution: str, num_points: int
    ) -> list[OHLCV]:
        result = await self._run_sync(
            self._ig.fetch_historical_prices_by_epic_and_num_points,
            epic,
            resolution,
            num_points,
        )
        prices = result["prices"]
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
