from __future__ import annotations

from abc import ABC, abstractmethod

from bot.broker.models import MarketInfo, OHLCV, OrderRequest, OrderResult, Position, Tick


class BrokerClient(ABC):
    """Abstract broker client interface."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection and authenticate."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up and close connection."""

    @abstractmethod
    async def search_markets(self, term: str) -> list[MarketInfo]:
        """Search for markets by keyword."""

    @abstractmethod
    async def get_market_info(self, epic: str) -> MarketInfo:
        """Get detailed market info for a specific epic."""

    @abstractmethod
    async def get_historical_prices(
        self, epic: str, resolution: str, num_points: int
    ) -> list[OHLCV]:
        """Fetch historical OHLCV data."""

    @abstractmethod
    async def get_open_positions(self) -> list[Position]:
        """Get all currently open positions."""

    @abstractmethod
    async def open_position(self, order: OrderRequest) -> OrderResult:
        """Open a new position."""

    @abstractmethod
    async def close_position(self, deal_id: str, direction: str, size: float) -> OrderResult:
        """Close an existing position."""

    @abstractmethod
    async def amend_position(
        self, deal_id: str, stop_level: float | None = None, limit_level: float | None = None
    ) -> OrderResult:
        """Amend stop/limit on an existing position."""

    @abstractmethod
    async def get_account_balance(self) -> dict:
        """Get account balance and funds info."""
