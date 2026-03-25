from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import sys
import time
from collections import deque

import pandas as pd
import redis.asyncio as aioredis
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.broker.ig_rest import IGRestClient
from bot.broker.ig_stream import IGStreamClient
from bot.broker.models import Direction, OrderRequest, Tick
from bot.config import load_settings_from_db, settings
from bot.data.calendar import EconomicCalendar
from bot.data.historical import fetch_and_store_historical
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
from bot.notifications import (
    load_telegram_settings,
    notify_ai_decision,
    notify_bot_status,
    notify_drawdown_warning,
    notify_trade_opened,
    notify_trailing_stop_breakeven,
)
from bot.ai.analyzer import ClaudeAnalyzer
from bot.ai.models import AIVerdict
from bot.db.repository import AIAnalysisRepository
from bot.reports.weekly import generate_weekly_report
from bot.risk.manager import RiskManager
from bot.risk.models import RiskConfig
from bot.risk.trading_sessions import is_market_open
from bot.risk.trailing_stop import TrailingStopManager
from bot.autopilot.manager import AutoPilotManager
from bot.autopilot.models import AutoPilotConfig
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
            getattr(logging, settings.bot.log_level, logging.INFO)
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
        self.autopilot: AutoPilotManager | None = None
        self.ai_analyzer = ClaudeAnalyzer()
        self._bar_cache: dict[str, tuple] = {}  # {epic:resolution -> (datetime, DataFrame)}

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
            # TTL of 90s — the periodic account metrics job (every 60s) refreshes it.
            # If the bot crashes, the key expires and the dashboard resumes direct IG calls.
            await r.set("bot:current_status", status, ex=90)
        except Exception as e:
            logger.warning("redis_status_publish_error", error=str(e))

    async def _publish_log(self, level: str, message: str, **extra) -> None:
        """Publish a log entry to Redis for the live logs page."""
        entry = {
            "time": _dt.datetime.now(_dt.timezone.utc).isoformat(),
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
                    elif command == "autopilot_toggle":
                        enabled = data.get("enabled", False)
                        if enabled:
                            await self._enable_autopilot()
                        else:
                            await self._disable_autopilot()
                    elif command == "autopilot_scan_now":
                        if self.autopilot:
                            await self._publish_log("INFO", "Auto-Pilot: manual scan triggered")
                            await self.autopilot.run_scan_cycle()
                except json.JSONDecodeError:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("command_listener_error", error=str(e))

    async def start(self) -> None:
        """Start the trading bot."""
        # Capture event loop for use in Lightstreamer thread callbacks
        self._loop = asyncio.get_running_loop()

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
        self.scheduler.add_job(self._heartbeat_ig, "interval", minutes=5, id="ig_heartbeat")
        # Weekly report: every Sunday at 20:00 UTC
        self.scheduler.add_job(generate_weekly_report, "cron", day_of_week="sun", hour=20, minute=0, id="weekly_report")
        self.scheduler.start()

        # Initialize Auto-Pilot if enabled
        await self._init_autopilot()

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
        if self.autopilot:
            await self.autopilot.deactivate_all()
            self.autopilot = None
        if self._command_task and not self._command_task.done():
            self._command_task.cancel()
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass
        if self.stream:
            await self.stream.disconnect()
        await self.broker.disconnect()
        await self._publish_status("stopped")
        await self._publish_log("INFO", "Bot stopped")
        await self.ai_analyzer.close()
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        logger.info("bot_stopped")

    async def _init_autopilot(self) -> None:
        """Initialize autopilot if enabled in settings."""
        if settings.autopilot.enabled:
            await self._enable_autopilot()

    async def _enable_autopilot(self) -> None:
        """Enable autopilot mode."""
        r = await self._get_redis()
        ap_config = AutoPilotConfig(
            enabled=True,
            scan_interval_minutes=settings.autopilot.scan_interval_minutes,
            max_active_markets=settings.autopilot.max_active_markets,
            min_score_threshold=settings.autopilot.min_score_threshold,
            universe_mode=settings.autopilot.universe_mode,
            search_terms=[t.strip() for t in settings.autopilot.search_terms.split(",") if t.strip()],
            api_budget_per_cycle=settings.autopilot.api_budget_per_cycle,
        )
        self.autopilot = AutoPilotManager(self.broker, self.registry, ap_config, r, stream=self.stream)

        # Schedule scan job
        if self.scheduler.get_job("autopilot_scan"):
            self.scheduler.remove_job("autopilot_scan")
        self.scheduler.add_job(
            self.autopilot.run_scan_cycle,
            "interval",
            minutes=ap_config.scan_interval_minutes,
            id="autopilot_scan",
        )
        # Run first scan immediately
        asyncio.create_task(self.autopilot.run_scan_cycle())
        await self._publish_log("INFO", f"Auto-Pilot enabled (scan every {ap_config.scan_interval_minutes}min, max {ap_config.max_active_markets} markets)")

    async def _disable_autopilot(self) -> None:
        """Disable autopilot mode."""
        if self.autopilot:
            await self.autopilot.deactivate_all()
            self.autopilot = None
        if self.scheduler.get_job("autopilot_scan"):
            self.scheduler.remove_job("autopilot_scan")
        await self._publish_log("INFO", "Auto-Pilot disabled, all autopilot strategies removed")

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

        # Update trailing stops and check for partial exits
        updates, partial_exits = self.trailing_stop.on_tick(tick)
        if updates:
            asyncio.run_coroutine_threadsafe(
                self.trailing_stop.amend_positions(updates),
                self._loop,
            )
            # Notify breakeven activations via Telegram
            for u in updates:
                if u.breakeven_activated and u.current_stop == u.entry_price:
                    asyncio.run_coroutine_threadsafe(
                        notify_trailing_stop_breakeven(u.deal_id, u.epic),
                        self._loop,
                    )
        if partial_exits:
            asyncio.run_coroutine_threadsafe(
                self.trailing_stop.execute_partial_exits(partial_exits),
                self._loop,
            )

        signals = self.registry.on_tick(tick)
        for strategy_name, signal in signals:
            SIGNALS_GENERATED.labels(strategy=strategy_name, signal_type=signal.signal_type).inc()
            # Schedule async signal processing
            asyncio.run_coroutine_threadsafe(
                self._process_signal(strategy_name, signal),
                self._loop,
            )

    async def _process_signal(self, strategy_name: str, signal) -> None:
        """Process a trading signal through risk management and execution."""
        # Check economic calendar
        if self.calendar.is_paused:
            ORDERS_REJECTED.labels(reason="calendar_pause").inc()
            await self._publish_log("WARNING", f"Signal skipped: economic event pause", strategy=strategy_name)
            return

        # Check trading session hours
        if not is_market_open(signal.epic):
            ORDERS_REJECTED.labels(reason="outside_session").inc()
            await self._publish_log("INFO", f"Signal skipped: outside trading session", strategy=strategy_name, epic=signal.epic)
            return

        order = await self.risk_manager.validate_signal(signal)
        if not order:
            ORDERS_REJECTED.labels(reason="risk_check").inc()
            return

        # AI pre-trade validation
        if self.ai_analyzer.is_enabled:
            try:
                positions = await self.broker.get_open_positions()
                pos_list = [
                    {"epic": p.epic, "direction": p.direction, "size": p.size, "entry_price": p.level}
                    for p in positions
                ]
                balance_info = await self.broker.get_account_balance()
                balance = balance_info.get("balance", 0.0)

                bars = await self.broker.get_historical_prices(signal.epic, "HOUR", 10)
                recent_bars = [
                    {"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
                    for b in (bars or [])
                ]

                ai_result = await self.ai_analyzer.validate_signal(
                    pair=signal.epic,
                    direction=signal.signal_type,
                    strategy=strategy_name,
                    confidence=signal.confidence,
                    indicators=signal.indicators,
                    recent_bars=recent_bars,
                    open_positions=pos_list,
                    account_balance=balance,
                )

                # Persist AI analysis
                async with async_session_factory() as session:
                    ai_repo = AIAnalysisRepository(session)
                    await ai_repo.save(
                        epic=signal.epic,
                        mode="pre_trade",
                        verdict=ai_result.verdict.value,
                        confidence=ai_result.confidence,
                        reasoning=ai_result.reasoning,
                        market_summary=ai_result.market_summary,
                        risk_warnings=ai_result.risk_warnings,
                        suggested_adjustments=ai_result.suggested_adjustments,
                        signal_direction=signal.signal_type,
                        signal_strategy=strategy_name,
                        model_used=ai_result.model_used,
                        latency_ms=ai_result.latency_ms,
                    )

                # Telegram notification for AI decisions
                await notify_ai_decision(
                    epic=signal.epic,
                    verdict=ai_result.verdict.value,
                    reasoning=ai_result.reasoning,
                    strategy=strategy_name,
                )

                if ai_result.verdict == AIVerdict.REJECT:
                    ORDERS_REJECTED.labels(reason="ai_rejected").inc()
                    await self._publish_log(
                        "WARNING",
                        f"AI rejected: {ai_result.reasoning}",
                        strategy=strategy_name,
                        epic=signal.epic,
                    )
                    return

                if ai_result.verdict == AIVerdict.ADJUST:
                    adj = ai_result.suggested_adjustments
                    if adj.get("size_factor"):
                        order.size = round(order.size * float(adj["size_factor"]), 2)
                    if adj.get("stop_loss_distance"):
                        order.stop_distance = float(adj["stop_loss_distance"])
                    if adj.get("limit_distance"):
                        order.limit_distance = float(adj["limit_distance"])
                    await self._publish_log(
                        "INFO",
                        f"AI adjusted: {ai_result.reasoning}",
                        strategy=strategy_name,
                        epic=signal.epic,
                    )
            except Exception as exc:
                logger.warning("ai_validation_error", error=str(exc), epic=signal.epic)

        # Shadow mode: autopilot strategies log signals without executing
        is_autopilot = strategy_name.startswith("ap_")
        if is_autopilot and settings.autopilot.shadow_mode:
            await self._record_shadow_trade(strategy_name, signal, order)
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

                    # Build metadata for autopilot trades (score, regime, etc.)
                    trade_meta = {}
                    if strategy_name.startswith("ap_"):
                        strategy_obj = self.registry.get(strategy_name)
                        if strategy_obj:
                            trade_meta = {
                                "autopilot": True,
                                "score": strategy_obj.config.get("score"),
                                "size_factor": strategy_obj.config.get("size_factor"),
                                "confidence": signal.confidence,
                            }

                    trade = Trade(
                        deal_id=result.deal_id or result.deal_reference,
                        deal_reference=result.deal_reference,
                        epic=order.epic,
                        direction=order.direction.value,
                        size=order.size,
                        strategy_name=strategy_name,
                        status="OPEN",
                        metadata_=trade_meta,
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

                # Register trailing stop tracking (ATR-based when available)
                if signal.stop_distance:
                    self.trailing_stop.track_position(
                        deal_id=result.deal_id or result.deal_reference,
                        epic=order.epic,
                        direction=order.direction,
                        entry_price=signal.indicators.get("price", 0),
                        size=order.size,
                        trail_distance=signal.stop_distance,
                        atr=signal.indicators.get("atr"),
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

    async def _record_shadow_trade(self, strategy_name: str, signal, order) -> None:
        """Record a paper trade without executing on the broker."""
        import uuid

        shadow_id = f"SHADOW-{uuid.uuid4().hex[:12]}"
        SIGNALS_GENERATED.labels(strategy=strategy_name, signal_type=signal.signal_type).inc()

        async with async_session_factory() as session:
            trade_repo = TradeRepository(session)
            signal_repo = SignalRepository(session)

            strategy_obj = self.registry.get(strategy_name)
            trade_meta = {
                "autopilot": True,
                "shadow": True,
                "score": strategy_obj.config.get("score") if strategy_obj else None,
                "size_factor": strategy_obj.config.get("size_factor") if strategy_obj else None,
                "confidence": signal.confidence,
            }

            trade = Trade(
                deal_id=shadow_id,
                deal_reference=shadow_id,
                epic=order.epic,
                direction=order.direction.value,
                size=order.size,
                strategy_name=strategy_name,
                status="SHADOW",
                open_price=signal.indicators.get("price"),
                metadata_=trade_meta,
            )
            await trade_repo.create(trade)

            sig = Signal(
                epic=signal.epic,
                strategy_name=strategy_name,
                signal_type=signal.signal_type,
                confidence=signal.confidence,
                indicators=signal.indicators,
                executed=False,
                deal_id=shadow_id,
            )
            await signal_repo.create(sig)

        await self._publish_log(
            "INFO",
            f"[SHADOW] {order.direction.value} {order.size} {order.epic} (score: {signal.confidence:.0%})",
            strategy=strategy_name,
        )
        logger.info(
            "shadow_trade_recorded",
            epic=order.epic,
            direction=order.direction.value,
            size=order.size,
            strategy=strategy_name,
        )

    async def _update_bars(self) -> None:
        """Periodically fetch fresh bars from IG and run bar-based strategy evaluation.

        Uses a bar cache to avoid exhausting IG API quota.  Bars are only
        re-fetched from the API once per hour per epic; in between, the cached
        DataFrame is reused for strategy evaluation.
        """
        now = _dt.datetime.utcnow()

        enabled = self.registry.get_enabled()
        all_epics = [e for s in enabled for e in s.get_required_epics()]
        logger.info("bar_update_cycle", strategies=len(enabled), epics=len(all_epics),
                     names=[s.name for s in enabled])

        for strategy in enabled:
            for epic in strategy.get_required_epics():
                try:
                    resolution = strategy.get_required_resolution()
                    cache_key = f"{epic}:{resolution}"

                    # Check cache — only refetch every 60 minutes
                    cached = self._bar_cache.get(cache_key)
                    if cached:
                        cached_at, cached_df = cached
                        age_minutes = (now - cached_at).total_seconds() / 60
                        if age_minutes < 60:
                            # Reuse cached bars — still run strategy evaluation
                            result = strategy.on_bar(epic, cached_df)
                            if result and result.signal_type != "HOLD":
                                SIGNALS_GENERATED.labels(strategy=strategy.name, signal_type=result.signal_type).inc()
                                logger.info(
                                    "bar_signal_cached",
                                    epic=epic,
                                    strategy=strategy.name,
                                    signal=result.signal_type,
                                    confidence=result.confidence,
                                    reason=result.reason,
                                )
                                await self._process_signal(strategy.name, result)
                            elif result:
                                logger.debug(
                                    "bar_hold_cached",
                                    epic=epic,
                                    strategy=strategy.name,
                                    indicators=result.indicators,
                                )
                            continue

                    num_bars = strategy.get_required_history()

                    # Fetch fresh OHLCV data from IG API
                    # If epic returns 404 (Mini variants), try standard CFD epic
                    try:
                        bars = await self.broker.get_historical_prices(epic, resolution, num_bars)
                    except Exception as fetch_err:
                        if "404" in str(fetch_err):
                            # Try standard CFD variant: CS.D.EURUSD.CEFM.IP -> CS.D.EURUSD.CFD.IP
                            parts = epic.split(".")
                            if len(parts) >= 4:
                                std_epic = f"{parts[0]}.{parts[1]}.{parts[2]}.CFD.IP"
                                logger.warning("bar_fallback_standard", original=epic, fallback=std_epic)
                                bars = await self.broker.get_historical_prices(std_epic, resolution, num_bars)
                            else:
                                raise
                        else:
                            raise
                    if not bars or len(bars) < 30:
                        logger.debug("bar_update_insufficient", epic=epic, bars=len(bars) if bars else 0)
                        continue

                    # Build DataFrame from raw bars
                    data = []
                    for b in bars:
                        data.append({
                            "time": b.time,
                            "open": b.open,
                            "high": b.high,
                            "low": b.low,
                            "close": b.close,
                            "volume": b.volume,
                        })
                    df = pd.DataFrame(data)
                    if df.empty:
                        continue
                    df.set_index("time", inplace=True)
                    df.sort_index(inplace=True)

                    df = add_all_indicators(df)

                    # Cache the processed DataFrame
                    self._bar_cache[cache_key] = (now, df)
                    # Diagnostic: log price range and ATR to debug zero-ATR issue
                    last_row = df.iloc[-1]
                    atr_val = last_row.get("ATRr_14", None) if "ATRr_14" in df.columns else None
                    logger.info(
                        "bar_update_fresh",
                        epic=epic,
                        resolution=resolution,
                        bars=len(df),
                        last_open=round(float(last_row["open"]), 5),
                        last_high=round(float(last_row["high"]), 5),
                        last_low=round(float(last_row["low"]), 5),
                        last_close=round(float(last_row["close"]), 5),
                        atr_14=round(float(atr_val), 6) if atr_val is not None and not pd.isna(atr_val) else "NaN",
                    )

                    result = strategy.on_bar(epic, df)
                    if result and result.signal_type != "HOLD":
                        SIGNALS_GENERATED.labels(strategy=strategy.name, signal_type=result.signal_type).inc()
                        logger.info(
                            "bar_signal",
                            epic=epic,
                            strategy=strategy.name,
                            signal=result.signal_type,
                            confidence=result.confidence,
                            reason=result.reason,
                        )
                        await self._process_signal(strategy.name, result)
                    elif result:
                        logger.info(
                            "bar_hold",
                            epic=epic,
                            strategy=strategy.name,
                            indicators=result.indicators,
                        )

                    # Rate limit: 2.5s between API calls
                    await asyncio.sleep(2.5)

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
        """Update account balance metrics, check drawdown, and publish to Redis."""
        try:
            balance = await self.broker.get_account_balance()
            ACCOUNT_BALANCE.set(balance.get("balance", 0))
            daily_pnl = balance.get("profit_loss", 0)
            DAILY_PNL.set(daily_pnl)

            # Drawdown warnings at 50% and 80% of daily limit
            if daily_pnl < 0 and self.risk_manager.config.max_daily_loss > 0:
                pct_used = abs(daily_pnl) / self.risk_manager.config.max_daily_loss * 100
                drawdown_key = f"drawdown_warned_{int(pct_used // 50) * 50}"
                r = await self._get_redis()
                already_warned = await r.get(drawdown_key)
                if pct_used >= 50 and not already_warned:
                    await notify_drawdown_warning(daily_pnl, self.risk_manager.config.max_daily_loss, pct_used)
                    await r.set(drawdown_key, "1", ex=86400)  # warn once per day

            # Drawdown auto-disable: shut down trading if daily loss exceeds limit
            if (
                self.risk_manager.config.drawdown_auto_disable
                and daily_pnl <= -self.risk_manager.config.max_daily_loss
                and self._running
            ):
                logger.warning(
                    "drawdown_auto_disable",
                    daily_pnl=daily_pnl,
                    limit=self.risk_manager.config.max_daily_loss,
                )
                await self._publish_log(
                    "ERROR",
                    f"DRAWDOWN LIMIT: Daily loss {daily_pnl:.2f} exceeds -{self.risk_manager.config.max_daily_loss:.0f}. "
                    f"Auto-pilot disabled, all positions flagged.",
                )
                # Disable autopilot to stop new trades
                if self.autopilot:
                    await self._disable_autopilot()
                # Close all open positions
                closed = await self.risk_manager.check_and_close_losing_positions()
                if closed:
                    await self._publish_log("WARNING", f"Emergency closed {len(closed)} positions")
                # Notify via Telegram
                from bot.notifications import send_message
                await send_message(
                    f"\U0001f6a8 <b>DRAWDOWN LIMIT REACHED</b>\n"
                    f"Daily P&L: <b>{daily_pnl:.2f}</b>\n"
                    f"Limit: -{self.risk_manager.config.max_daily_loss:.0f}\n"
                    f"Auto-pilot disabled, {len(closed)} positions closed."
                )

            # Publish to Redis so the dashboard doesn't need its own IG session
            r = await self._get_redis()
            await r.set("ig:account_info", json.dumps(balance, default=str), ex=120)
            await r.set("ig:account_balance", str(balance.get("balance", 0)), ex=120)
            # Refresh the "bot is alive" heartbeat
            await r.set("bot:current_status", "running", ex=90)

            # Publish calendar status for dashboard
            try:
                cal_status = self.calendar.get_status()
                # Add upcoming events list
                import datetime as _dt
                _now = _dt.datetime.utcnow()
                upcoming = [
                    {"name": e.name, "time": e.time.isoformat(), "impact": e.impact, "currency": e.currency}
                    for e in sorted(self.calendar._events, key=lambda e: e.time)
                    if e.time > _now
                ][:10]
                cal_status["upcoming_events"] = upcoming
                await r.set("calendar:status", json.dumps(cal_status), ex=120)
            except Exception as ce:
                logger.debug("calendar_publish_error", error=str(ce))

            # Publish VIX data for dashboard
            try:
                vix_mult = await self.risk_manager.vix_monitor.get_adjustment()
                vix_data = {
                    "level": self.risk_manager.vix_monitor.vix_level,
                    "regime": self.risk_manager.vix_monitor.vix_regime,
                    "multiplier": vix_mult,
                }
                await r.set("risk:vix", json.dumps(vix_data), ex=7200)
            except Exception as ve:
                logger.debug("vix_publish_error", error=str(ve))
        except Exception as e:
            logger.error("account_metrics_error", error=str(e))

    async def _heartbeat_ig(self) -> None:
        """Periodic IG session health check with auto-reconnect."""
        try:
            healthy = await self.broker.heartbeat()
            if not healthy:
                await self._publish_log("WARNING", "IG session lost — reconnection attempted")
        except Exception as e:
            logger.error("heartbeat_error", error=str(e))

    async def _refresh_calendar(self) -> None:
        """Refresh economic calendar events."""
        try:
            self.calendar.clear_past_events()
            await self.calendar.fetch_events()
        except Exception as e:
            logger.error("calendar_refresh_error", error=str(e))


async def main() -> None:
    configure_logging()

    max_retries = 10
    for attempt in range(1, max_retries + 1):
        bot = TradingBot()
        try:
            await bot.start()
            # start() blocks until stream ends — clean exit
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error("bot_fatal_error", error=str(e), attempt=attempt)
        finally:
            try:
                await bot.stop()
            except Exception:
                pass

        if attempt >= max_retries:
            logger.critical("max_startup_retries_reached")
            break

        # Exponential backoff: 30s, 60s, 120s, ... max 300s
        delay = min(30 * (2 ** (attempt - 1)), 300)
        logger.info("bot_retry_in", seconds=delay, attempt=attempt)
        await asyncio.sleep(delay)
