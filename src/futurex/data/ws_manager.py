from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Callable, Awaitable

import websockets
from websockets.client import WebSocketClientProtocol

from ..core.logging import get_logger

log = get_logger("futurex.data.ws_manager")


class WSManager:
    def __init__(
        self,
        base_ws_url: str,
        on_message: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._base_url = base_ws_url.rstrip("/")
        self._on_message = on_message
        self._ws: WebSocketClientProtocol | None = None
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._stable_since: float = 0.0
        self._tasks: list[asyncio.Task[Any]] = []

    async def start(self, streams: list[str]) -> None:
        self._running = True
        stream_path = "/".join(streams)
        self._url = f"{self._base_url}/stream?streams={stream_path}"
        log.info("ws_connecting", url=self._url, stream_count=len(streams))
        self._tasks.append(asyncio.create_task(self._connection_loop()))

    async def start_single(self, path: str) -> None:
        self._running = True
        self._url = f"{self._base_url}/ws/{path}"
        log.info("ws_connecting_single", url=self._url)
        self._tasks.append(asyncio.create_task(self._connection_loop()))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        log.info("ws_stopped")

    def set_message_handler(
        self, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        self._on_message = handler

    async def _connection_loop(self) -> None:
        while self._running:
            try:
                async with websockets.connect(
                    self._url,
                    ping_interval=None,
                    max_size=2**22,
                    open_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    self._stable_since = time.monotonic()
                    self._reconnect_delay = 1.0
                    log.info("ws_connected", url=self._url)

                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
                    try:
                        await self._receive_loop(ws)
                    finally:
                        heartbeat_task.cancel()

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                jitter = random.uniform(0, self._reconnect_delay * 0.1)
                delay = self._reconnect_delay + jitter
                log.warning(
                    "ws_disconnected",
                    error=str(e),
                    reconnect_in=f"{delay:.1f}s",
                )
                await asyncio.sleep(delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )

    async def _receive_loop(self, ws: WebSocketClientProtocol) -> None:
        async for raw_msg in ws:
            if not self._running:
                break
            try:
                data = json.loads(raw_msg)
                if self._on_message:
                    await self._on_message(data)
            except json.JSONDecodeError:
                log.warning("ws_invalid_json", raw=str(raw_msg)[:200])
            except Exception as e:
                log.error("ws_handler_error", error=str(e))

    async def _heartbeat_loop(self, ws: WebSocketClientProtocol) -> None:
        while self._running:
            try:
                await asyncio.sleep(300)  # 5 minutes
                pong = await ws.ping()
                await asyncio.wait_for(pong, timeout=10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("ws_heartbeat_failed", error=str(e))
                break
