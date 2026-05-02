from __future__ import annotations

from collections import deque
from typing import Any

import pandas as pd

from ..core.events import EventBus, KlineClose
from ..core.logging import get_logger

log = get_logger("futurex.data.kline_aggregator")


class KlineAggregator:
    def __init__(self, event_bus: EventBus, buffer_size: int = 500) -> None:
        self._event_bus = event_bus
        self._buffer_size = buffer_size
        self._buffers: dict[tuple[str, str], deque[dict[str, float]]] = {}
        self._current: dict[tuple[str, str], dict[str, float]] = {}

    def initialize_buffer(
        self, symbol: str, interval: str, candles: list[dict[str, Any]]
    ) -> None:
        key = (symbol, interval)
        buf: deque[dict[str, float]] = deque(maxlen=self._buffer_size)
        for c in candles:
            buf.append(
                {
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": float(c["volume"]),
                    "timestamp": float(c.get("timestamp", c.get("open_time", 0))),
                }
            )
        self._buffers[key] = buf
        log.info(
            "kline_buffer_initialized",
            symbol=symbol,
            interval=interval,
            count=len(buf),
        )

    async def on_kline(self, data: dict[str, Any]) -> None:
        k = data.get("k", data)
        symbol = str(k.get("s", "")).upper()
        interval = str(k.get("i", ""))
        is_closed = k.get("x", False)
        key = (symbol, interval)

        candle = {
            "open": float(k.get("o", 0)),
            "high": float(k.get("h", 0)),
            "low": float(k.get("l", 0)),
            "close": float(k.get("c", 0)),
            "volume": float(k.get("v", 0)),
            "timestamp": float(k.get("t", 0)),
        }

        self._current[key] = candle

        if is_closed:
            if key not in self._buffers:
                self._buffers[key] = deque(maxlen=self._buffer_size)
            self._buffers[key].append(candle)

            event = KlineClose(
                symbol=symbol,
                interval=interval,
                open=candle["open"],
                high=candle["high"],
                low=candle["low"],
                close=candle["close"],
                volume=candle["volume"],
            )
            await self._event_bus.publish(event)

    def get_candles(
        self, symbol: str, interval: str, count: int | None = None
    ) -> pd.DataFrame:
        key = (symbol, interval)
        buf = self._buffers.get(key, deque())
        if not buf:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "timestamp"])

        data = list(buf)
        if count:
            data = data[-count:]

        return pd.DataFrame(data)

    def get_current_candle(
        self, symbol: str, interval: str
    ) -> dict[str, float] | None:
        return self._current.get((symbol, interval))
