from __future__ import annotations

import time
from typing import Any

from ..core.constants import Side
from ..core.events import EventBus, OrderUpdate
from ..core.logging import get_logger
from ..risk import AccountState, Position, TradeRecord

log = get_logger("futurex.execution.fill_tracker")


class FillTracker:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._pending_entries: dict[str, dict[str, Any]] = {}
        self._trade_history: list[TradeRecord] = []

    def track_entry(self, symbol: str, side: Side, expected_qty: float) -> None:
        self._pending_entries[symbol] = {
            "side": side,
            "expected_qty": expected_qty,
            "filled_qty": 0.0,
            "avg_price": 0.0,
            "time": time.time(),
        }

    def on_order_update(
        self, update: OrderUpdate, account: AccountState
    ) -> TradeRecord | None:
        if update.status == "FILLED":
            if update.realized_pnl != 0:
                position = account.position_for(update.symbol)
                entry_price = position.entry_price if position else update.avg_price

                record = TradeRecord(
                    symbol=update.symbol,
                    side=update.side,
                    entry_price=entry_price,
                    exit_price=update.avg_price,
                    quantity=update.filled_qty,
                    pnl=update.realized_pnl,
                    duration_seconds=0.0,
                    entry_time=0.0,
                    exit_time=time.time(),
                )
                self._trade_history.append(record)

                log.info(
                    "trade_closed",
                    symbol=update.symbol,
                    pnl=update.realized_pnl,
                    exit_price=update.avg_price,
                )

                return record

        return None

    @property
    def trade_history(self) -> list[TradeRecord]:
        return self._trade_history
