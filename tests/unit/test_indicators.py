import pytest
import pandas as pd

from bot.data.indicators import add_atr, add_bollinger_bands, add_ema, add_macd, add_rsi


def test_add_rsi(sample_ohlcv_df):
    df = add_rsi(sample_ohlcv_df, length=14)
    assert "rsi_14" in df.columns
    # RSI should be between 0 and 100 (where not NaN)
    valid = df["rsi_14"].dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_add_macd(sample_ohlcv_df):
    df = add_macd(sample_ohlcv_df, fast=12, slow=26, signal=9)
    assert any("MACD" in col for col in df.columns)


def test_add_bollinger_bands(sample_ohlcv_df):
    df = add_bollinger_bands(sample_ohlcv_df, length=20, std=2.0)
    assert any("BBL" in col for col in df.columns)
    assert any("BBU" in col for col in df.columns)


def test_add_ema(sample_ohlcv_df):
    df = add_ema(sample_ohlcv_df, length=50)
    assert "ema_50" in df.columns
    valid = df["ema_50"].dropna()
    assert len(valid) > 0


def test_add_atr(sample_ohlcv_df):
    df = add_atr(sample_ohlcv_df, length=14)
    assert "atr_14" in df.columns
    valid = df["atr_14"].dropna()
    assert (valid >= 0).all()
