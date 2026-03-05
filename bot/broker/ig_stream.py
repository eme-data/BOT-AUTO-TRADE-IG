from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Callable

import structlog
from trading_ig import IGService, IGStreamService
from trading_ig.lightstreamer import Subscription

from bot.broker.models import Tick
from bot.config import settings
from bot.metrics import STREAM_RECONNECTS

logger = structlog.get_logger()

MAX_RECONNECT_ATTEMPTS = 50
RECONNECT_BASE_DELAY = 5  # seconds
KEEPALIVE_INTERVAL = 30  # seconds


class IGStreamClient:
    """IG Markets Lightstreamer streaming client with robust auto-reconnect."""

    def __init__(self, ig_service: IGService, redis_url: str | None = None):
        self._ig = ig_service
        self._stream: IGStreamService | None = None
        self._subscriptions: list[dict] = []
        self._on_tick: Callable[[Tick], None] | None = None
        self._on_trade: Callable[[dict], None] | None = None
        self._on_account: Callable[[dict], None] | None = None
        self._redis_url = redis_url
        self._redis = None
        self._running = False
        self._reconnect_count = 0
        self._last_tick_time: datetime | None = None

    async def connect(self) -> None:
        """Initialize streaming connection."""
        if self._redis_url:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url)

        self._stream = IGStreamService(self._ig)
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._stream.create_session(version="2")
        )
        self._running = True
        self._reconnect_count = 0
        logger.info("ig_stream_connected")

    async def disconnect(self) -> None:
        """Disconnect streaming."""
        self._running = False
        if self._stream:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._stream.disconnect
                )
            except Exception:
                pass
            self._stream = None
        if self._redis:
            await self._redis.aclose()
        logger.info("ig_stream_disconnected")

    def on_tick(self, callback: Callable[[Tick], None]) -> None:
        self._on_tick = callback

    def on_trade(self, callback: Callable[[dict], None]) -> None:
        self._on_trade = callback

    def on_account(self, callback: Callable[[dict], None]) -> None:
        self._on_account = callback

    async def subscribe_market(self, epics: list[str]) -> None:
        """Subscribe to market price updates for given epics."""
        items = [f"MARKET:{epic}" for epic in epics]
        fields = ["UPDATE_TIME", "BID", "OFFER", "HIGH", "LOW", "CHANGE", "CHANGE_PCT", "MARKET_STATE"]

        sub_info = {"mode": "MERGE", "items": items, "fields": fields, "type": "market"}
        self._subscriptions.append(sub_info)

        sub = Subscription(mode="MERGE", items=items, fields=fields)
        sub.addlistener(self._on_market_update)

        await asyncio.get_event_loop().run_in_executor(
            None, self._stream.ls_client.subscribe, sub
        )
        logger.info("subscribed_markets", epics=epics)

    async def subscribe_trades(self) -> None:
        """Subscribe to trade confirmations and position updates."""
        acc_id = settings.ig.acc_number
        items = [f"TRADE:{acc_id}"]
        fields = ["CONFIRMS", "OPU", "WOU"]

        sub = Subscription(mode="DISTINCT", items=items, fields=fields)
        sub.addlistener(self._on_trade_update)

        await asyncio.get_event_loop().run_in_executor(
            None, self._stream.ls_client.subscribe, sub
        )
        logger.info("subscribed_trades", account=acc_id)

    async def subscribe_account(self) -> None:
        """Subscribe to account balance updates."""
        acc_id = settings.ig.acc_number
        items = [f"ACCOUNT:{acc_id}"]
        fields = ["FUNDS", "PNL", "DEPOSIT", "AVAILABLE_TO_DEAL", "EQUITY"]

        sub = Subscription(mode="MERGE", items=items, fields=fields)
        sub.addlistener(self._on_account_update)

        await asyncio.get_event_loop().run_in_executor(
            None, self._stream.ls_client.subscribe, sub
        )
        logger.info("subscribed_account", account=acc_id)

    def _on_market_update(self, item: dict) -> None:
        """Handle incoming market price update (called from Lightstreamer thread)."""
        try:
            values = item.get("values", {})
            item_name = item.get("name", "")
            epic = item_name.replace("MARKET:", "") if item_name.startswith("MARKET:") else item_name

            bid = values.get("BID")
            offer = values.get("OFFER")
            if bid is None or offer is None:
                return

            tick = Tick(
                epic=epic,
                bid=float(bid),
                offer=float(offer),
                time=datetime.now(),
            )

            self._last_tick_time = tick.time

            if self._on_tick:
                self._on_tick(tick)

            # Publish to Redis if available
            if self._redis:
                asyncio.run_coroutine_threadsafe(
                    self._publish_tick(tick), asyncio.get_event_loop()
                )
        except Exception as e:
            logger.error("market_update_error", error=str(e))

    def _on_trade_update(self, item: dict) -> None:
        """Handle trade confirmation/position update."""
        try:
            values = item.get("values", {})
            if self._on_trade:
                self._on_trade(values)

            if self._redis:
                asyncio.run_coroutine_threadsafe(
                    self._publish_event("bot:trades", values), asyncio.get_event_loop()
                )
        except Exception as e:
            logger.error("trade_update_error", error=str(e))

    def _on_account_update(self, item: dict) -> None:
        """Handle account balance update."""
        try:
            values = item.get("values", {})
            if self._on_account:
                self._on_account(values)

            if self._redis:
                asyncio.run_coroutine_threadsafe(
                    self._publish_event("bot:account", values), asyncio.get_event_loop()
                )
        except Exception as e:
            logger.error("account_update_error", error=str(e))

    async def _publish_tick(self, tick: Tick) -> None:
        """Publish tick to Redis pub/sub."""
        if self._redis:
            data = json.dumps({
                "type": "tick",
                "epic": tick.epic,
                "bid": tick.bid,
                "offer": tick.offer,
                "spread": tick.spread,
                "mid": tick.mid,
                "time": tick.time.isoformat(),
            })
            await self._redis.publish("bot:ticks", data)

    async def _publish_event(self, channel: str, data: dict) -> None:
        """Publish event to Redis."""
        if self._redis:
            await self._redis.publish(channel, json.dumps(data, default=str))

    async def _check_stale_connection(self) -> bool:
        """Check if the stream appears stale (no ticks for too long)."""
        if self._last_tick_time is None:
            return False
        elapsed = (datetime.now() - self._last_tick_time).total_seconds()
        # If no ticks for 5 minutes during market hours, connection is probably stale
        return elapsed > 300

    async def _reconnect(self) -> None:
        """Perform a full reconnection with re-subscription."""
        self._reconnect_count += 1
        STREAM_RECONNECTS.inc()
        delay = min(RECONNECT_BASE_DELAY * (2 ** min(self._reconnect_count, 6)), 300)
        logger.warning(
            "stream_reconnecting",
            attempt=self._reconnect_count,
            delay=delay,
        )
        await asyncio.sleep(delay)

        # Disconnect old stream
        if self._stream:
            try:
                await asyncio.get_event_loop().run_in_executor(None, self._stream.disconnect)
            except Exception:
                pass

        # Reconnect
        self._stream = IGStreamService(self._ig)
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._stream.create_session(version="2")
        )

        # Re-subscribe to all previous subscriptions
        for sub_info in self._subscriptions:
            if sub_info["type"] == "market":
                epics = [item.replace("MARKET:", "") for item in sub_info["items"]]
                await self.subscribe_market(epics)
        await self.subscribe_trades()
        await self.subscribe_account()
        self._reconnect_count = 0
        logger.info("stream_reconnected")

    async def run_with_reconnect(self) -> None:
        """Run streaming with automatic reconnection on disconnect."""
        while self._running and self._reconnect_count < MAX_RECONNECT_ATTEMPTS:
            try:
                while self._running:
                    await asyncio.sleep(KEEPALIVE_INTERVAL)

                    # Check for stale connection
                    if await self._check_stale_connection():
                        logger.warning("stream_stale_connection_detected")
                        await self._reconnect()

            except Exception as e:
                if not self._running:
                    break
                logger.error("stream_error", error=str(e))
                try:
                    await self._reconnect()
                except Exception as reconnect_error:
                    logger.error("reconnect_failed", error=str(reconnect_error))

        if self._reconnect_count >= MAX_RECONNECT_ATTEMPTS:
            logger.critical("max_reconnect_attempts_reached")
