from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskConfig:
    max_daily_loss: float = 500.0
    max_position_size: float = 10.0
    max_open_positions: int = 5
    max_positions_per_epic: int = 1
    max_risk_per_trade_pct: float = 2.0  # % of account balance
    default_stop_distance: int = 20
    default_limit_distance: int = 40
    drawdown_auto_disable: bool = True  # auto-disable bot on max daily loss
