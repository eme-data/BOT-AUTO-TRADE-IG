from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import deque

import redis.asyncio as aioredis
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.broker.ig_rest import IGRestClient
from bot.broker.ig_stream import IGStreamClient
from bot.broker.models import Direction, OrderRequest, Tick
from bot.config import load_settings_from_db, settings
from bot.data.calendar import EconomicCalendar
from bot.data.historical import fetch_and_store_historical, load_from_db
from bot.data.indicators import add_all_indicators
from bot.db.models import Signal, Trade
from bot.db.repository import SignalRepository, StrategyStateRepository, TradeRepository
from bot.db.session import async_session_factory
from bot.metrics import (
    ACCOUNT_BALANCE,
    DAILY_PNL,
    OPEN_POSITIONS,
    ORDER_LATENCY,
    ORDERS_PLACED,
    ORDERS_REJECTED,
    SIGNALS_GENERATED,
    TICK_RATE,
    start_metrics_server,
)
from bot.notifications import load_telegram_settings, notify_bot_status, notify_trade_opened
from bot.risk.manager import RiskManager
from bot.risk.models import RiskConfig
from bot.risk.trailing_stop import TrailingStopManager
from bot.strategies.macd_trend import MACDTrendStrategy
from bot.strategies.registry import StrategyRegistry
from bot.strategies.rsi_mean_reversion import RSIMeanReversionStrategy

logger = structlog.get_logger()


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, settings.bot.log_level, structlog.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    )


class TradingBot:
    """Main trading bot orchestrator."""

    def __init__(self):
        self.broker = IGRestClient()
        self.registry = StrategyRegistry()
        self.risk_manager = RiskManager(
            self.broker,
            RiskConfig(
                max_daily_loss=settings.bot.max_daily_loss,
                max_position_size=settings.bot.max_position_size,
                default_stop_distance=settings.bot.default_stop_distance,
                default_limit_distance=settings.bot.default_limit_distance,
            ),
        )
        self.trailing_stop = TrailingStopManager(
            self.broker,
            default_trail_distance=settings.bot.default_stop_distance,
        )
        self.calendar = EconomicCalendar(buffer_minutes=30)
        self.stream: IGStreamClient | None = None
        self.scheduler = AsyncIOScheduler()
        self._running = False
        self._redis: aioredis.Redis | None = None
        self._command_task: asyncio.Task | None = None
        self._log_buffer: deque[dict] = deque(maxlen=500)

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis.url, decode_responses=True)
        return self._redis

    async def _publish_status(self, status: str) -> None:
        """Publish bot status to Redis for dashboard consumption."""
        try:
            r = await self._get_redis()
            await r.publish("bot:status", json.dumps({"status": status}))
            # Also update the DB setting via Redis command channel
            await r.set("bot:current_status", status)
        except Exception as e:
            logger.warning("redis_status_publish_error", error=str(e))

    async def _publish_log(self, level: str, message: str, **extra) -> None:
        """Publish a log entry to Redis for the live logs page."""
        import datetime

        entry = {
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": level,
            "message": message,
            **extra,
        }
        self._log_buffer.append(entry)
        try:
            r = await self._get_redis()
            await r.publish("bot:logs", json.dumps(entry))
        except Exception:
            pass  # non-critical

    async def _listen_commands(self) -> None:
        """Listen for commands from the dashboard via Redis pub/sub."""
        try:
            r = await self._get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe("bot:commands")
            logger.info("redis_command_listener_started")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    command = data.get("command")
                    logger.info("received_command", command=command)

                    if command == "stop":
                        await self._publish_log("INFO", "Stop command received, shutting down...")
                        await self._publish_status("stopped")
                        await self.stop()
                        break
                    elif command == "restart":
                        await self._publish_log("INFO", "Restart command received...")
                        await self._publish_status("starting")
                        await self.stop()
                        # Re-load settings and restart
                        await load_settings_from_db()
                        await self.start()
                        break
                    elif command == "reload_settings":
                        await self._publish_log("INFO", "Reloading settings from DB...")
                        await load_settings_from_db()
                        await self._publish_log("INFO", "Settings reloaded")
                except json.JSONDecodeError:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("command_listener_error", error=str(e))

    async def start(self) -> None:
        """Start the trading bot."""
        # Load IG/bot settings from DB (overrides .env defaults)
        await load_settings_from_db()

        await self._publish_status("starting")
        await self._publish_log("INFO", "Bot starting...", acc_type=settings.ig.acc_type)
        logger.info("bot_starting", acc_type=settings.ig.acc_type)

        # Load Telegram notification settings
        await load_telegram_settings()

        # Start Prometheus metrics
        start_metrics_server(port=8001)

        # Connect to broker
        await self.broker.connect()
        await self._publish_log("INFO", "Connected to IG broker")

        # Load strategies from DB or defaults
        await self._load_strategies()

        # Fetch initial historical data for all strategies
        await self._warmup_historical_data()

        # Setup streaming
        self.stream = IGStreamClient(self.broker._ig, redis_url=settings.redis.url)
        await self.stream.connect()
        self.stream.on_tick(self._handle_tick_sync)

        # Subscribe to all required epics
        epics = list(self.registry.get_all_required_epics())
        if epics:
            await self.stream.subscribe_market(epics)
            await self._publish_log("INFO", f"Subscribed to {len(epics)} markets")
        await self.stream.subscribe_trades()
        await self.stream.subscribe_account()

        # Load economic calendar
        await self.calendar.fetch_events()

        # Schedule periodic tasks
        self.scheduler.add_job(self._update_bars, "interval", minutes=5, id="update_bars")
        self.scheduler.add_job(self._reconcile_positions, "interval", minutes=2, id="reconcile")
        self.scheduler.add_job(self._update_account_metrics, "interval", minutes=1, id="account_metrics")
        self.scheduler.add_job(self._refresh_calendar, "interval", hours=6, id="refresh_calendar")
        self.scheduler.start()

        self._running = True
        await self._publish_status("running")
        await self._publish_log("INFO", f"Bot started with {len(self.registry.get_enabled())} strategies, {len(epics)} epics")
        logger.info("bot_started", strategies=len(self.registry.get_enabled()), epics=len(epics))
        await notify_bot_status("running", f"{len(self.registry.get_enabled())} strategies, {len(epics)} epics")

        # Start Redis command listener in background
        self._command_task = asyncio.create_task(self._listen_commands())

        # Run streaming (blocks until stopped)
        await self.stream.run_with_reconnect()

    async def stop(self) -> None:
        """Stop the trading bot gracefully."""
        logger.info("bot_stopping")
        self._running = False
        if self._command_task and not self._command_task.done():
            self._command_task.cancel()
        self.scheduler.shutdown(wait=False)
        if self.stream:
            await self.stream.disconnect()
        await self.broker.disconnect()
        await self._publish_status("stopped")
        await self._publish_log("INFO", "Bot stopped")
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        logger.info("bot_stopped")

    async def _load_strategies(self) -> None:
        """Load strategies from database or register defaults."""
        async with async_session_factory() as session:
            repo = StrategyStateRepository(session)
            saved = await repo.get_all_enabled()

            if saved:
                for state in saved:
                    strategy = self._create_strategy(state.name, state.config)
                    if strategy:
                        strategy.enabled = state.enabled
                        self.registry.register(strategy)
            else:
                # Register default strategies (disabled, user must configure epics)
                logger.info("no_saved_strategies_loading_defaults")
                rsi = RSIMeanReversionStrategy({"epics": [], "resolution": "HOUR"})
                rsi.enabled = False
                self.registry.register(rsi)

                macd = MACDTrendStrategy({"epics": [], "resolution": "HOUR"})
                macd.enabled = False
                self.registry.register(macd)

    def _create_strategy(self, name: str, config: dict):
        """Factory method to create strategy by name."""
        strategies = {
            "rsi_mean_reversion": RSIMeanReversionStrategy,
            "macd_trend": MACDTrendStrategy,
        }
        cls = strategies.get(name)
        if cls:
            return cls(config)
        logger.warning("unknown_strategy", name=name)
        return None

    async def _warmup_historical_data(self) -> None:
        """Fetch historical data needed by strategies."""
        async with async_session_factory() as session:
            for strategy in self.registry.get_enabled():
                for epic in strategy.get_required_epics():
                    try:
                        await fetch_and_store_historical(
                            self.broker,
                            session,
                            epic,
                            strategy.get_required_resolution(),
                            strategy.get_required_history(),
                        )
                    except Exception as e:
                        logger.error("warmup_error", epic=epic, strategy=strategy.name, error=str(e))

    def _handle_tick_sync(self, tick: Tick) -> None:
        """Handle tick from streaming thread (synchronous callback)."""
        TICK_RATE.labels(epic=tick.epic).inc()

        # Update trailing stops
        updates = self.trailing_stop.on_tick(tick)
        if updates:
            asyncio.run_coroutine_threadsafe(
                self.trailing_stop.amend_positions(updates),
                asyncio.get_event_loop(),
            )

        signals = self.registry.on_tick(tick)
        for strategy_name, signal in signals:
            SIGNALS_GENERATED.labels(strategy=strategy_name, signal_type=signal.signal_type).inc()
            # Schedule async signal processing
            asyncio.run_coroutine_threadsafe(
                self._process_signal(strategy_name, signal),
                asyncio.get_event_loop(),
            )

    async def _process_signal(self, strategy_name: str, signal) -> None:
        """Process a trading signal through risk management and execution."""
        # Check economic calendar
        if self.calendar.is_paused:
            ORDERS_REJECTED.labels(reason="calendar_pause").inc()
            await self._publish_log("WARNING", f"Signal skipped: economic event pause", strategy=strategy_name)
            return

        order = await self.risk_manager.validate_signal(signal)
        if not order:
            ORDERS_REJECTED.labels(reason="risk_check").inc()
            return

        try:
            start = time.monotonic()
            result = await self.broker.open_position(order)
            latency = time.monotonic() - start
            ORDER_LATENCY.observe(latency)

            if result.status == "ACCEPTED":
                ORDERS_PLACED.labels(strategy=strategy_name, direction=order.direction.value, epic=order.epic).inc()

                # Record trade in DB
                async with async_session_factory() as session:
                    trade_repo = TradeRepository(session)
                    signal_repo = SignalRepository(session)

                    trade = Trade(
                        deal_id=result.deal_id or result.deal_reference,
                        deal_reference=result.deal_reference,
                        epic=order.epic,
                        direction=order.direction.value,
                        size=order.size,
                        strategy_name=strategy_name,
                        status="OPEN",
                    )
                    await trade_repo.create(trade)

                    sig = Signal(
                        epic=signal.epic,
                        strategy_name=strategy_name,
                        signal_type=signal.signal_type,
                        confidence=signal.confidence,
                        indicators=signal.indicators,
                        executed=True,
                        deal_id=result.deal_id,
                    )
                    await signal_repo.create(sig)

                # Register trailing stop tracking
                if signal.stop_distance:
                    self.trailing_stop.track_position(
                        deal_id=result.deal_id or result.deal_reference,
                        epic=order.epic,
                        direction=order.direction,
                        entry_price=signal.indicators.get("price", 0),
                        trail_distance=signal.stop_distance,
                    )

                # Telegram notification
                await notify_trade_opened(
                    epic=order.epic,
                    direction=order.direction.value,
                    size=order.size,
                    strategy=strategy_name,
                    deal_id=result.deal_id or result.deal_reference,
                )
                await self._publish_log(
                    "INFO",
                    f"Trade opened: {order.direction.value} {order.size} {order.epic}",
                    strategy=strategy_name,
                    deal_id=result.deal_id,
                )
            else:
                logger.warning("order_rejected_by_broker", status=result.status, reason=result.reason)
                ORDERS_REJECTED.labels(reason="broker_rejected").inc()

        except Exception as e:
            logger.error("order_execution_error", error=str(e), epic=order.epic)
            ORDERS_REJECTED.labels(reason="execution_error").inc()

    async def _update_bars(self) -> None:
        """Periodically update bar data and run bar-based strategy evaluation."""
        async with async_session_factory() as session:
            for strategy in self.registry.get_enabled():
                for epic in strategy.get_required_epics():
                    try:
                        df = await load_from_db(
                            session, epic, strategy.get_required_resolution(),
                            limit=strategy.get_required_history(),
                        )
                        if df.empty:
                            continue

                        df = add_all_indicators(df)
                        result = strategy.on_bar(epic, df)
                        if result and result.signal_type != "HOLD":
                            SIGNALS_GENERATED.labels(strategy=strategy.name, signal_type=result.signal_type).inc()
                            await self._process_signal(strategy.name, result)

                    except Exception as e:
                        logger.error("bar_update_error", epic=epic, strategy=strategy.name, error=str(e))

    async def _reconcile_positions(self) -> None:
        """Reconcile open positions with broker."""
        try:
            positions = await self.broker.get_open_positions()
            OPEN_POSITIONS.set(len(positions))
        except Exception as e:
            logger.error("reconcile_error", error=str(e))

    async def _update_account_metrics(self) -> None:
        """Update account balance metrics."""
        try:
            balance = await self.broker.get_account_balance()
            ACCOUNT_BALANCE.set(balance.get("balance", 0))
            DAILY_PNL.set(balance.get("profit_loss", 0))
        except Exception as e:
            logger.error("account_metrics_error", error=str(e))

    async def _refresh_calendar(self) -> None:
        """Refresh economic calendar events."""
        try:
            self.calendar.clear_past_events()
            await self.calendar.fetch_events()
        except Exception as e:
            logger.error("calendar_refresh_error", error=str(e))


async def main() -> None:
    configure_logging()
    bot = TradingBot()

    try:
        await bot.start()
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()
