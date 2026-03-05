from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bot.backtesting.engine import BacktestEngine
from bot.data.historical import load_from_db
from bot.data.indicators import add_all_indicators
from bot.db.models import AdminUser
from bot.strategies.macd_trend import MACDTrendStrategy
from bot.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_STRATEGIES = {
    "macd_trend": MACDTrendStrategy,
    "rsi_mean_reversion": RSIMeanReversionStrategy,
}


class BacktestRequest(BaseModel):
    strategy: str
    epic: str
    resolution: str = "HOUR"
    history_bars: int = 500
    initial_balance: float = 10000.0
    spread: float = 1.0
    config: dict = {}


@router.post("")
async def run_backtest(
    req: BacktestRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Run a backtest on historical data stored in the database."""
    strategy_cls = _STRATEGIES.get(req.strategy)
    if not strategy_cls:
        raise HTTPException(400, f"Unknown strategy: {req.strategy}. Available: {list(_STRATEGIES.keys())}")

    # Load historical data from DB
    df = await load_from_db(db, req.epic, req.resolution, limit=req.history_bars)
    if df.empty or len(df) < 50:
        raise HTTPException(400, f"Not enough historical data for {req.epic}. Need at least 50 bars, got {len(df)}.")

    # Create strategy instance with config
    config = {
        "epics": [req.epic],
        "resolution": req.resolution,
        **req.config,
    }
    strategy = strategy_cls(config)

    # Run backtest
    engine = BacktestEngine(
        initial_balance=req.initial_balance,
        spread=req.spread,
    )
    report = engine.run(strategy, df, epic=req.epic)

    return {
        "summary": report.summary(),
        "equity_curve": report.equity_curve[-200:],  # Last 200 points for charting
        "trades": [
            {
                "entry_time": str(t.entry_time),
                "exit_time": str(t.exit_time),
                "direction": t.direction,
                "size": t.size,
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "profit": round(t.profit, 2),
                "reason": t.reason,
            }
            for t in report.trades[-100:]  # Last 100 trades
        ],
    }
