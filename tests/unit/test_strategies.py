import pandas as pd
import pytest

from bot.broker.models import Tick
from bot.strategies.macd_trend import MACDTrendStrategy
from bot.strategies.registry import StrategyRegistry
from bot.strategies.rsi_mean_reversion import RSIMeanReversionStrategy


class TestRSIMeanReversion:
    def setup_method(self):
        self.strategy = RSIMeanReversionStrategy({
            "epics": ["CS.D.EURUSD.TODAY.IP"],
            "rsi_period": 14,
            "oversold": 30,
            "overbought": 70,
            "ema_period": 50,
            "resolution": "HOUR",
            "history_bars": 100,
        })

    def test_init(self):
        assert self.strategy.name == "rsi_mean_reversion"
        assert self.strategy.enabled is True

    def test_required_epics(self):
        assert "CS.D.EURUSD.TODAY.IP" in self.strategy.get_required_epics()

    def test_required_resolution(self):
        assert self.strategy.get_required_resolution() == "HOUR"

    def test_on_tick_returns_none(self, sample_tick):
        result = self.strategy.on_tick(sample_tick)
        assert result is None

    def test_on_bar_insufficient_data(self):
        df = pd.DataFrame({
            "open": [1.0, 1.1],
            "high": [1.1, 1.2],
            "low": [0.9, 1.0],
            "close": [1.05, 1.15],
            "volume": [100, 200],
        })
        result = self.strategy.on_bar("CS.D.EURUSD.TODAY.IP", df)
        assert result is None

    def test_on_bar_with_data(self, sample_ohlcv_df):
        result = self.strategy.on_bar("CS.D.EURUSD.TODAY.IP", sample_ohlcv_df)
        assert result is not None
        assert result.signal_type in ("BUY", "SELL", "HOLD")
        assert result.epic == "CS.D.EURUSD.TODAY.IP"
        assert "rsi" in result.indicators

    def test_config_schema(self):
        schema = self.strategy.get_config_schema()
        assert "rsi_period" in schema
        assert "oversold" in schema

    def test_update_config(self):
        self.strategy.update_config({"oversold": 25})
        assert self.strategy.config["oversold"] == 25


class TestMACDTrend:
    def setup_method(self):
        self.strategy = MACDTrendStrategy({
            "epics": ["IX.D.FTSE.DAILY.IP"],
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
        })

    def test_init(self):
        assert self.strategy.name == "macd_trend"

    def test_on_bar_with_data(self, sample_ohlcv_df):
        result = self.strategy.on_bar("IX.D.FTSE.DAILY.IP", sample_ohlcv_df)
        assert result is not None
        assert result.signal_type in ("BUY", "SELL", "HOLD")
        assert "macd" in result.indicators
        assert "atr" in result.indicators


class TestStrategyRegistry:
    def setup_method(self):
        self.registry = StrategyRegistry()

    def test_register(self):
        strategy = RSIMeanReversionStrategy({"epics": ["TEST"]})
        self.registry.register(strategy)
        assert self.registry.get("rsi_mean_reversion") is strategy

    def test_unregister(self):
        strategy = RSIMeanReversionStrategy({"epics": ["TEST"]})
        self.registry.register(strategy)
        self.registry.unregister("rsi_mean_reversion")
        assert self.registry.get("rsi_mean_reversion") is None

    def test_get_enabled(self):
        s1 = RSIMeanReversionStrategy({"epics": ["A"]})
        s2 = MACDTrendStrategy({"epics": ["B"]})
        s2.enabled = False
        self.registry.register(s1)
        self.registry.register(s2)
        enabled = self.registry.get_enabled()
        assert len(enabled) == 1
        assert enabled[0].name == "rsi_mean_reversion"

    def test_get_all_required_epics(self):
        s1 = RSIMeanReversionStrategy({"epics": ["A", "B"]})
        s2 = MACDTrendStrategy({"epics": ["B", "C"]})
        self.registry.register(s1)
        self.registry.register(s2)
        epics = self.registry.get_all_required_epics()
        assert epics == {"A", "B", "C"}

    def test_enable_disable(self):
        strategy = RSIMeanReversionStrategy({"epics": ["TEST"]})
        self.registry.register(strategy)
        self.registry.disable("rsi_mean_reversion")
        assert strategy.enabled is False
        self.registry.enable("rsi_mean_reversion")
        assert strategy.enabled is True
