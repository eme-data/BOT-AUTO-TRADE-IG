from __future__ import annotations

import pandas as pd
import pandas_ta as ta


def add_rsi(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    df[f"rsi_{length}"] = ta.rsi(df["close"], length=length)
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)
    return df


def add_bollinger_bands(df: pd.DataFrame, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    bbands = ta.bbands(df["close"], length=length, std=std)
    if bbands is not None:
        df = pd.concat([df, bbands], axis=1)
    return df


def add_ema(df: pd.DataFrame, length: int = 200) -> pd.DataFrame:
    df[f"ema_{length}"] = ta.ema(df["close"], length=length)
    return df


def add_atr(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    df[f"atr_{length}"] = ta.atr(df["high"], df["low"], df["close"], length=length)
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add a comprehensive set of indicators to OHLCV dataframe."""
    strategy = ta.Strategy(
        name="trading_bot",
        ta=[
            {"kind": "rsi", "length": 14},
            {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
            {"kind": "bbands", "length": 20, "std": 2},
            {"kind": "atr", "length": 14},
            {"kind": "ema", "length": 20},
            {"kind": "ema", "length": 50},
            {"kind": "ema", "length": 200},
            {"kind": "adx", "length": 14},
            {"kind": "stoch", "k": 14, "d": 3},
        ],
    )
    df.ta.strategy(strategy)
    return df
