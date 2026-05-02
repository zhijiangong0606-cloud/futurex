from __future__ import annotations

import asyncio
from typing import Any

from ..core.constants import OrderType, Side
from ..core.events import EventBus
from ..core.logging import get_logger
from ..data.rest_client import RESTClient
from ..risk import OrderRequest, RiskVerdict

log = get_logger("futurex.execution.order_manager")


class OrderManager:
    def __init__(self, rest_client: RESTClient, event_bus: EventBus) -> None:
        self._rest = rest_client
        self._event_bus = event_bus

    async def execute_signal(self, verdict: RiskVerdict) -> dict[str, Any] | None:
        if not verdict.approved or verdict.order is None:
            log.warning("order_rejected", rejections=verdict.rejections)
            return None

        order = verdict.order

        entry_result = await self._rest.place_order(
            symbol=order.symbol,
            side=order.side.value,
            order_type=order.order_type.value,
            quantity=order.quantity,
        )

        if not entry_result:
            return None

        if verdict.stop_loss > 0:
            close_side = order.side.close_side
            try:
                await self._rest.place_order(
                    symbol=order.symbol,
                    side=close_side.value,
                    order_type=OrderType.STOP_MARKET.value,
                    quantity=order.quantity,
                    stop_price=verdict.stop_loss,
                    reduce_only=True,
                )
                log.info(
                    "stop_order_placed",
                    symbol=order.symbol,
                    stop_price=verdict.stop_loss,
                )
            except Exception as e:
                log.error(
                    "stop_order_failed",
                    symbol=order.symbol,
                    error=str(e),
                )

        return entry_result

    async def close_position(
        self,
        symbol: str,
        side: Side,
        quantity: float,
    ) -> dict[str, Any] | None:
        close_side = side.close_side
        try:
            result = await self._rest.place_order(
                symbol=symbol,
                side=close_side.value,
                order_type=OrderType.MARKET.value,
                quantity=quantity,
                reduce_only=True,
            )
            log.info(
                "position_closed",
                symbol=symbol,
                side=close_side.value,
                quantity=quantity,
            )
            return result
        except Exception as e:
            log.error("close_position_failed", symbol=symbol, error=str(e))
            return None

    async def emergency_flatten_all(
        self, positions: list[Any]
    ) -> None:
        log.critical("emergency_flatten", position_count=len(positions))
        tasks = []
        for pos in positions:
            tasks.append(
                self.close_position(pos.symbol, pos.side, abs(pos.quantity))
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error(
                    "flatten_failed",
                    symbol=positions[i].symbol,
                    error=str(result),
                )

    async def update_stop_order(
        self,
        symbol: str,
        old_order_id: int | None,
        side: Side,
        quantity: float,
        new_stop_price: float,
    ) -> dict[str, Any] | None:
        if old_order_id:
            try:
                await self._rest.cancel_order(symbol, old_order_id)
            except Exception:
                pass

        close_side = side.close_side
        try:
            result = await self._rest.place_order(
                symbol=symbol,
                side=close_side.value,
                order_type=OrderType.STOP_MARKET.value,
                quantity=quantity,
                stop_price=new_stop_price,
                reduce_only=True,
            )
            return result
        except Exception as e:
            log.error(
                "stop_update_failed",
                symbol=symbol,
                error=str(e),
            )
            return None
