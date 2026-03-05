"""
Backtesting engine for evaluating strategies on historical data.

Usage:
    from bot.backtesting.engine import BacktestEngine
    from bot.strategies.macd_trend import MACDTrendStrategy

    engine = BacktestEngine(initial_balance=10000, spread=1.0)
    strategy = MACDTrendStrategy({"epics": ["IX.D.DAX.DAILY.IP"], "resolution": "HOUR"})
    report = await engine.run(strategy, df)
    print(report.summary())
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from bot.data.indicators import add_all_indicators
from bot.strategies.base import AbstractStrategy


@dataclass
class BacktestTrade:
    """A single trade during backtesting."""
    entry_time: datetime
    exit_time: datetime | None = None
    epic: str = ""
    direction: str = "BUY"
    size: float = 1.0
    entry_price: float = 0.0
    exit_price: float = 0.0
    stop_distance: float = 0.0
    limit_distance: float = 0.0
    profit: float = 0.0
    status: str = "OPEN"
    reason: str = ""


@dataclass
class BacktestReport:
    """Results of a backtesting run."""
    strategy_name: str
    epic: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    initial_balance: float = 10000.0
    final_balance: float = 10000.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    sharpe_ratio: float = 0.0
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "strategy": self.strategy_name,
            "epic": self.epic,
            "period": f"{self.start_date} to {self.end_date}",
            "initial_balance": self.initial_balance,
            "final_balance": round(self.final_balance, 2),
            "total_return_pct": round((self.final_balance / self.initial_balance - 1) * 100, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate * 100, 1),
            "profit_factor": round(self.profit_factor, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
        }


class BacktestEngine:
    """
    Simulates strategy execution on historical OHLCV data.

    Processes bars sequentially, evaluates strategy signals,
    and simulates order fills at bar close prices.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        spread: float = 1.0,
        commission: float = 0.0,
        max_open_positions: int = 3,
    ):
        self.initial_balance = initial_balance
        self.spread = spread
        self.commission = commission
        self.max_open_positions = max_open_positions

    def run(self, strategy: AbstractStrategy, df: pd.DataFrame, epic: str = "") -> BacktestReport:
        """
        Run a backtest on the given OHLCV DataFrame.

        df must have columns: time, open, high, low, close, volume
        """
        if df.empty or len(df) < 50:
            return BacktestReport(strategy_name=strategy.name, epic=epic)

        # Add indicators
        df = add_all_indicators(df.copy())

        balance = self.initial_balance
        open_trades: list[BacktestTrade] = []
        closed_trades: list[BacktestTrade] = []
        equity_curve: list[dict] = []
        peak_equity = balance

        # Process each bar using a growing window
        warmup = strategy.get_required_history()
        for i in range(warmup, len(df)):
            bar = df.iloc[i]
            current_time = bar.name if isinstance(bar.name, datetime) else bar.get("time", datetime.now())
            current_price = float(bar["close"])
            current_high = float(bar["high"])
            current_low = float(bar["low"])

            # Check stops and limits for open trades
            trades_to_close = []
            for trade in open_trades:
                if trade.direction == "BUY":
                    # Check stop (price went below stop level)
                    stop_level = trade.entry_price - trade.stop_distance
                    limit_level = trade.entry_price + trade.limit_distance
                    if trade.stop_distance > 0 and current_low <= stop_level:
                        trade.exit_price = stop_level
                        trade.reason = "stop_hit"
                        trades_to_close.append(trade)
                    elif trade.limit_distance > 0 and current_high >= limit_level:
                        trade.exit_price = limit_level
                        trade.reason = "limit_hit"
                        trades_to_close.append(trade)
                else:  # SELL
                    stop_level = trade.entry_price + trade.stop_distance
                    limit_level = trade.entry_price - trade.limit_distance
                    if trade.stop_distance > 0 and current_high >= stop_level:
                        trade.exit_price = stop_level
                        trade.reason = "stop_hit"
                        trades_to_close.append(trade)
                    elif trade.limit_distance > 0 and current_low <= limit_level:
                        trade.exit_price = limit_level
                        trade.reason = "limit_hit"
                        trades_to_close.append(trade)

            # Close trades that hit stop/limit
            for trade in trades_to_close:
                trade.exit_time = current_time
                trade.status = "CLOSED"
                if trade.direction == "BUY":
                    trade.profit = (trade.exit_price - trade.entry_price) * trade.size - self.commission
                else:
                    trade.profit = (trade.entry_price - trade.exit_price) * trade.size - self.commission
                balance += trade.profit
                open_trades.remove(trade)
                closed_trades.append(trade)

            # Evaluate strategy on the current slice of data
            history = df.iloc[:i + 1]
            signal = strategy.on_bar(epic or "BACKTEST", history)

            if signal and signal.signal_type in ("BUY", "SELL"):
                if len(open_trades) < self.max_open_positions:
                    entry_price = current_price + (self.spread / 2 if signal.signal_type == "BUY" else -self.spread / 2)
                    trade = BacktestTrade(
                        entry_time=current_time,
                        epic=epic,
                        direction=signal.signal_type,
                        size=signal.size or 1.0,
                        entry_price=entry_price,
                        stop_distance=signal.stop_distance or 0,
                        limit_distance=signal.limit_distance or 0,
                    )
                    open_trades.append(trade)

            # Calculate unrealized P&L
            unrealized = 0.0
            for trade in open_trades:
                if trade.direction == "BUY":
                    unrealized += (current_price - trade.entry_price) * trade.size
                else:
                    unrealized += (trade.entry_price - current_price) * trade.size

            equity = balance + unrealized
            peak_equity = max(peak_equity, equity)

            equity_curve.append({
                "time": str(current_time),
                "equity": round(equity, 2),
                "balance": round(balance, 2),
                "drawdown": round(peak_equity - equity, 2),
            })

        # Close remaining open trades at last price
        last_price = float(df.iloc[-1]["close"])
        last_time = df.index[-1] if isinstance(df.index[-1], datetime) else datetime.now()
        for trade in open_trades:
            trade.exit_time = last_time
            trade.exit_price = last_price
            trade.status = "CLOSED"
            trade.reason = "end_of_data"
            if trade.direction == "BUY":
                trade.profit = (trade.exit_price - trade.entry_price) * trade.size
            else:
                trade.profit = (trade.entry_price - trade.exit_price) * trade.size
            balance += trade.profit
            closed_trades.append(trade)

        # Calculate report metrics
        return self._build_report(strategy.name, epic, df, closed_trades, equity_curve, balance)

    def _build_report(
        self,
        strategy_name: str,
        epic: str,
        df: pd.DataFrame,
        trades: list[BacktestTrade],
        equity_curve: list[dict],
        final_balance: float,
    ) -> BacktestReport:
        report = BacktestReport(
            strategy_name=strategy_name,
            epic=epic,
            initial_balance=self.initial_balance,
            final_balance=final_balance,
            total_trades=len(trades),
            trades=trades,
            equity_curve=equity_curve,
        )

        if df.index.dtype == "datetime64[ns]":
            report.start_date = df.index[0]
            report.end_date = df.index[-1]

        if not trades:
            return report

        wins = [t for t in trades if t.profit > 0]
        losses = [t for t in trades if t.profit <= 0]
        report.winning_trades = len(wins)
        report.losing_trades = len(losses)
        report.win_rate = len(wins) / len(trades) if trades else 0
        report.total_profit = sum(t.profit for t in trades)

        gross_profit = sum(t.profit for t in wins) if wins else 0
        gross_loss = abs(sum(t.profit for t in losses)) if losses else 0
        report.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        report.avg_win = gross_profit / len(wins) if wins else 0
        report.avg_loss = gross_loss / len(losses) if losses else 0

        # Max drawdown
        if equity_curve:
            peak = 0.0
            max_dd = 0.0
            max_dd_pct = 0.0
            for point in equity_curve:
                eq = point["equity"]
                if eq > peak:
                    peak = eq
                dd = peak - eq
                if dd > max_dd:
                    max_dd = dd
                    max_dd_pct = (dd / peak * 100) if peak > 0 else 0
            report.max_drawdown = max_dd
            report.max_drawdown_pct = max_dd_pct

        # Sharpe ratio (simplified, using daily returns)
        if len(equity_curve) > 1:
            equities = [p["equity"] for p in equity_curve]
            returns = [(equities[i] - equities[i - 1]) / equities[i - 1]
                       for i in range(1, len(equities)) if equities[i - 1] > 0]
            if returns:
                import statistics
                mean_r = statistics.mean(returns)
                std_r = statistics.stdev(returns) if len(returns) > 1 else 1
                report.sharpe_ratio = (mean_r / std_r) * (252 ** 0.5) if std_r > 0 else 0

        return report
