from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import time


@dataclass(frozen=True)
class Event:
    timestamp: float = field(default_factory=time.time)
    event_type: str = "base"


@dataclass(frozen=True)
class KlineClose(Event):
    symbol: str = ""
    interval: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    event_type: str = "kline_close"


@dataclass(frozen=True)
class BookTickerUpdate(Event):
    symbol: str = ""
    best_bid: float = 0.0
    best_bid_qty: float = 0.0
    best_ask: float = 0.0
    best_ask_qty: float = 0.0
    event_type: str = "book_ticker"


@dataclass(frozen=True)
class DepthUpdate(Event):
    symbol: str = ""
    bids: tuple[tuple[float, float], ...] = ()
    asks: tuple[tuple[float, float], ...] = ()
    event_type: str = "depth_update"


@dataclass(frozen=True)
class AccountUpdate(Event):
    balances: dict[str, float] = field(default_factory=dict)
    positions: list[dict[str, Any]] = field(default_factory=list)
    event_type: str = "account_update"


@dataclass(frozen=True)
class OrderUpdate(Event):
    symbol: str = ""
    order_id: int = 0
    client_order_id: str = ""
    side: str = ""
    order_type: str = ""
    status: str = ""
    price: float = 0.0
    avg_price: float = 0.0
    quantity: float = 0.0
    filled_qty: float = 0.0
    realized_pnl: float = 0.0
    commission: float = 0.0
    event_type: str = "order_update"


@dataclass(frozen=True)
class TradeSignalEvent(Event):
    symbol: str = ""
    direction: str = ""
    score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    requires_ai_review: bool = False
    event_type: str = "trade_signal"


@dataclass(frozen=True)
class RiskAlertEvent(Event):
    tier: str = ""
    message: str = ""
    event_type: str = "risk_alert"


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[Event]]] = defaultdict(list)

    def subscribe(self, event_type: str) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=1000)
        self._subscribers[event_type].append(queue)
        return queue

    async def publish(self, event: Event) -> None:
        for queue in self._subscribers.get(event.event_type, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(event)

    def unsubscribe(self, event_type: str, queue: asyncio.Queue[Event]) -> None:
        subs = self._subscribers.get(event_type, [])
        if queue in subs:
            subs.remove(queue)
