from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.events import BookTickerUpdate, DepthUpdate, EventBus
from ..core.logging import get_logger

log = get_logger("futurex.data.orderbook")


@dataclass
class BookTicker:
    symbol: str = ""
    best_bid: float = 0.0
    best_bid_qty: float = 0.0
    best_ask: float = 0.0
    best_ask_qty: float = 0.0

    @property
    def spread(self) -> float:
        if self.best_ask > 0 and self.best_bid > 0:
            return self.best_ask - self.best_bid
        return 0.0

    @property
    def mid_price(self) -> float:
        if self.best_ask > 0 and self.best_bid > 0:
            return (self.best_ask + self.best_bid) / 2
        return 0.0


class OrderBookCache:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._tickers: dict[str, BookTicker] = {}
        self._depth: dict[str, dict[str, list[list[float]]]] = {}

    async def on_book_ticker(self, data: dict[str, Any]) -> None:
        symbol = str(data.get("s", "")).upper()
        ticker = BookTicker(
            symbol=symbol,
            best_bid=float(data.get("b", 0)),
            best_bid_qty=float(data.get("B", 0)),
            best_ask=float(data.get("a", 0)),
            best_ask_qty=float(data.get("A", 0)),
        )
        self._tickers[symbol] = ticker

        event = BookTickerUpdate(
            symbol=symbol,
            best_bid=ticker.best_bid,
            best_bid_qty=ticker.best_bid_qty,
            best_ask=ticker.best_ask,
            best_ask_qty=ticker.best_ask_qty,
        )
        await self._event_bus.publish(event)

    async def on_depth(self, data: dict[str, Any]) -> None:
        symbol = str(data.get("s", "")).upper()
        bids = [[float(p), float(q)] for p, q in data.get("b", [])]
        asks = [[float(p), float(q)] for p, q in data.get("a", [])]
        self._depth[symbol] = {"bids": bids, "asks": asks}

        event = DepthUpdate(
            symbol=symbol,
            bids=tuple(tuple(b) for b in bids),  # type: ignore[arg-type]
            asks=tuple(tuple(a) for a in asks),  # type: ignore[arg-type]
        )
        await self._event_bus.publish(event)

    def get_ticker(self, symbol: str) -> BookTicker | None:
        return self._tickers.get(symbol)

    def get_depth(self, symbol: str) -> dict[str, list[list[float]]] | None:
        return self._depth.get(symbol)

    def get_mid_price(self, symbol: str) -> float:
        ticker = self._tickers.get(symbol)
        return ticker.mid_price if ticker else 0.0
