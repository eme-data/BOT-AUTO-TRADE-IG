from prometheus_client import Counter, Gauge, Histogram, start_http_server

ORDERS_PLACED = Counter("bot_orders_total", "Total orders placed", ["strategy", "direction", "epic"])
ORDERS_REJECTED = Counter("bot_orders_rejected_total", "Orders rejected by risk manager", ["reason"])
SIGNALS_GENERATED = Counter("bot_signals_total", "Signals generated", ["strategy", "signal_type"])
OPEN_POSITIONS = Gauge("bot_open_positions", "Current open positions count")
DAILY_PNL = Gauge("bot_daily_pnl", "Daily P&L")
ACCOUNT_BALANCE = Gauge("bot_account_balance", "Account balance")
ORDER_LATENCY = Histogram("bot_order_latency_seconds", "Order execution latency", buckets=[0.1, 0.25, 0.5, 1, 2, 5, 10])
TICK_RATE = Counter("bot_ticks_total", "Total ticks received", ["epic"])
STREAM_RECONNECTS = Counter("bot_stream_reconnects_total", "Stream reconnection attempts")


def start_metrics_server(port: int = 8001) -> None:
    start_http_server(port)
