from __future__ import annotations

from typing import Any, Callable, Awaitable

from ..core.logging import get_logger

log = get_logger("futurex.data.stream_router")


class StreamRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}

    def register(
        self, stream_type: str, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        self._handlers[stream_type] = handler

    async def dispatch(self, raw_msg: dict[str, Any]) -> None:
        if "stream" in raw_msg and "data" in raw_msg:
            stream_name: str = raw_msg["stream"]
            data = raw_msg["data"]

            if "@kline_" in stream_name:
                handler = self._handlers.get("kline")
            elif stream_name.endswith("@bookTicker"):
                handler = self._handlers.get("bookTicker")
            elif "@depth" in stream_name:
                handler = self._handlers.get("depth")
            elif stream_name.endswith("@aggTrade"):
                handler = self._handlers.get("aggTrade")
            elif stream_name.endswith("@markPrice"):
                handler = self._handlers.get("markPrice")
            else:
                handler = self._handlers.get(stream_name)

            if handler:
                await handler(data)
        elif "e" in raw_msg:
            event_type = raw_msg["e"]
            handler = self._handlers.get(event_type)
            if handler:
                await handler(raw_msg)
