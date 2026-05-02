from __future__ import annotations

import asyncio
from typing import Any

from ..core.events import AccountUpdate, EventBus, OrderUpdate
from ..core.logging import get_logger

log = get_logger("futurex.data.user_stream")


class UserStreamManager:
    def __init__(
        self,
        event_bus: EventBus,
        rest_client: Any,
        ws_manager_factory: Any,
    ) -> None:
        self._event_bus = event_bus
        self._rest = rest_client
        self._ws_factory = ws_manager_factory
        self._ws: Any = None
        self._listen_key: str = ""
        self._renewal_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._listen_key = await self._rest.create_listen_key()
        log.info("listen_key_created", key=self._listen_key[:8] + "...")

        self._ws = self._ws_factory(on_message=self._on_message)
        await self._ws.start_single(self._listen_key)
        self._renewal_task = asyncio.create_task(self._renewal_loop())

    async def stop(self) -> None:
        self._running = False
        if self._renewal_task:
            self._renewal_task.cancel()
        if self._ws:
            await self._ws.stop()

    async def _renewal_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(30 * 60)  # 30 minutes
                await self._rest.renew_listen_key()
                log.info("listen_key_renewed")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("listen_key_renewal_failed", error=str(e))
                try:
                    self._listen_key = await self._rest.create_listen_key()
                    log.info("listen_key_recreated")
                except Exception as e2:
                    log.error("listen_key_recreate_failed", error=str(e2))

    async def _on_message(self, data: dict[str, Any]) -> None:
        event_type = data.get("e", "")

        if event_type == "ACCOUNT_UPDATE":
            await self._handle_account_update(data)
        elif event_type == "ORDER_TRADE_UPDATE":
            await self._handle_order_update(data)
        elif event_type == "listenKeyExpired":
            log.warning("listen_key_expired")
            asyncio.create_task(self._reconnect())

    async def _handle_account_update(self, data: dict[str, Any]) -> None:
        account_data = data.get("a", {})

        balances: dict[str, float] = {}
        for b in account_data.get("B", []):
            asset = b.get("a", "")
            balance = float(b.get("wb", 0))
            balances[asset] = balance

        positions = []
        for p in account_data.get("P", []):
            positions.append(
                {
                    "symbol": p.get("s", ""),
                    "amount": float(p.get("pa", 0)),
                    "entry_price": float(p.get("ep", 0)),
                    "unrealized_pnl": float(p.get("up", 0)),
                    "margin_type": p.get("mt", ""),
                }
            )

        event = AccountUpdate(balances=balances, positions=positions)
        await self._event_bus.publish(event)

    async def _handle_order_update(self, data: dict[str, Any]) -> None:
        o = data.get("o", {})
        event = OrderUpdate(
            symbol=o.get("s", ""),
            order_id=int(o.get("i", 0)),
            client_order_id=o.get("c", ""),
            side=o.get("S", ""),
            order_type=o.get("o", ""),
            status=o.get("X", ""),
            price=float(o.get("p", 0)),
            avg_price=float(o.get("ap", 0)),
            quantity=float(o.get("q", 0)),
            filled_qty=float(o.get("z", 0)),
            realized_pnl=float(o.get("rp", 0)),
            commission=float(o.get("n", 0)),
        )
        await self._event_bus.publish(event)

    async def _reconnect(self) -> None:
        try:
            if self._ws:
                await self._ws.stop()
            self._listen_key = await self._rest.create_listen_key()
            self._ws = self._ws_factory(on_message=self._on_message)
            await self._ws.start_single(self._listen_key)
            log.info("user_stream_reconnected")
        except Exception as e:
            log.error("user_stream_reconnect_failed", error=str(e))
