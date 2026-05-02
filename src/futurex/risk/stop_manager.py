from __future__ import annotations

from ..core.constants import Side
from ..core.logging import get_logger
from . import Position

log = get_logger("futurex.risk.stop_manager")


class StopManager:
    def __init__(self, atr_multiplier: float = 2.0) -> None:
        self._atr_multiplier = atr_multiplier

    def compute_initial_stop(
        self, side: Side, entry_price: float, atr: float
    ) -> float:
        distance = atr * self._atr_multiplier
        if side == Side.LONG:
            return max(entry_price - distance, 0.0)
        else:
            return entry_price + distance

    def compute_trailing_stop(
        self,
        position: Position,
        current_price: float,
        current_atr: float,
        multiplier_override: float | None = None,
    ) -> float | None:
        mult = multiplier_override or self._atr_multiplier
        trail_distance = current_atr * mult

        if position.side == Side.LONG:
            profit = current_price - position.entry_price
            if profit < current_atr:
                return None

            new_stop = current_price - trail_distance
            if new_stop > position.stop_price:
                log.info(
                    "trailing_stop_updated",
                    symbol=position.symbol,
                    old_stop=position.stop_price,
                    new_stop=new_stop,
                    current_price=current_price,
                )
                return new_stop
        else:
            profit = position.entry_price - current_price
            if profit < current_atr:
                return None

            new_stop = current_price + trail_distance
            if new_stop < position.stop_price or position.stop_price == 0:
                log.info(
                    "trailing_stop_updated",
                    symbol=position.symbol,
                    old_stop=position.stop_price,
                    new_stop=new_stop,
                    current_price=current_price,
                )
                return new_stop

        return None
