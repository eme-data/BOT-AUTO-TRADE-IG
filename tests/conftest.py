import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


@pytest.fixture
def sample_ohlcv_df():
    """Generate a sample OHLCV DataFrame for testing."""
    dates = pd.date_range(start="2024-01-01", periods=300, freq="h")
    np.random.seed(42)

    price = 100.0
    data = []
    for dt in dates:
        change = np.random.normal(0, 1)
        open_price = price
        high = open_price + abs(np.random.normal(0, 0.5))
        low = open_price - abs(np.random.normal(0, 0.5))
        close = open_price + change
        price = close
        data.append({
            "time": dt,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": int(np.random.uniform(1000, 10000)),
        })

    df = pd.DataFrame(data)
    df.set_index("time", inplace=True)
    return df


@pytest.fixture
def sample_tick():
    from bot.broker.models import Tick
    return Tick(
        epic="CS.D.EURUSD.TODAY.IP",
        bid=1.0850,
        offer=1.0852,
        time=datetime.now(),
    )
