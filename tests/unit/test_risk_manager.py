import pytest
from unittest.mock import AsyncMock, MagicMock

from bot.broker.models import Direction, Position
from bot.risk.manager import RiskManager
from bot.risk.models import RiskConfig
from bot.strategies.base import SignalResult


@pytest.fixture
def mock_broker():
    broker = AsyncMock()
    broker.get_open_positions.return_value = []
    broker.get_account_balance.return_value = {
        "balance": 10000.0,
        "deposit": 500.0,
        "profit_loss": 50.0,
        "available": 9500.0,
    }
    return broker


@pytest.fixture
def risk_manager(mock_broker):
    config = RiskConfig(
        max_daily_loss=500.0,
        max_position_size=10.0,
        max_open_positions=5,
        max_positions_per_epic=1,
    )
    return RiskManager(mock_broker, config)


@pytest.mark.asyncio
async def test_validate_valid_signal(risk_manager):
    signal = SignalResult(
        signal_type="BUY",
        epic="CS.D.EURUSD.TODAY.IP",
        confidence=0.8,
        stop_distance=20,
        limit_distance=40,
        size=1.0,
    )
    order = await risk_manager.validate_signal(signal)
    assert order is not None
    assert order.direction == Direction.BUY
    assert order.epic == "CS.D.EURUSD.TODAY.IP"
    assert order.size == 1.0


@pytest.mark.asyncio
async def test_reject_max_positions(risk_manager, mock_broker):
    mock_broker.get_open_positions.return_value = [
        Position(deal_id=f"D{i}", epic=f"EPIC{i}", direction=Direction.BUY, size=1.0, open_level=100.0)
        for i in range(5)
    ]
    signal = SignalResult(signal_type="BUY", epic="NEW.EPIC", size=1.0)
    order = await risk_manager.validate_signal(signal)
    assert order is None


@pytest.mark.asyncio
async def test_reject_max_per_epic(risk_manager, mock_broker):
    mock_broker.get_open_positions.return_value = [
        Position(deal_id="D1", epic="CS.D.EURUSD.TODAY.IP", direction=Direction.BUY, size=1.0, open_level=100.0)
    ]
    signal = SignalResult(signal_type="BUY", epic="CS.D.EURUSD.TODAY.IP", size=1.0)
    order = await risk_manager.validate_signal(signal)
    assert order is None


@pytest.mark.asyncio
async def test_reject_daily_loss_exceeded(risk_manager):
    risk_manager._daily_pnl = -600.0  # exceeds 500 limit
    signal = SignalResult(signal_type="BUY", epic="CS.D.EURUSD.TODAY.IP", size=1.0)
    order = await risk_manager.validate_signal(signal)
    assert order is None


@pytest.mark.asyncio
async def test_reject_opposite_direction(risk_manager, mock_broker):
    mock_broker.get_open_positions.return_value = [
        Position(deal_id="D1", epic="CS.D.EURUSD.TODAY.IP", direction=Direction.SELL, size=1.0, open_level=100.0)
    ]
    signal = SignalResult(signal_type="BUY", epic="CS.D.EURUSD.TODAY.IP", size=1.0)
    order = await risk_manager.validate_signal(signal)
    assert order is None


@pytest.mark.asyncio
async def test_cap_position_size(risk_manager):
    signal = SignalResult(signal_type="BUY", epic="TEST", size=50.0, stop_distance=20)
    order = await risk_manager.validate_signal(signal)
    assert order is not None
    assert order.size == 10.0  # capped to max_position_size


def test_update_daily_pnl(risk_manager):
    risk_manager.update_daily_pnl(100.0)
    assert risk_manager._daily_pnl == 100.0
    risk_manager.update_daily_pnl(-50.0)
    assert risk_manager._daily_pnl == 50.0
