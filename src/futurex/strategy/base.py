from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core.constants import Side, SignalStrength
from ..indicators.engine import IndicatorSnapshot


@dataclass
class TradeSignal:
    symbol: str
    direction: Side
    score: float
    strength: SignalStrength
    components: dict[str, float] = field(default_factory=dict)
    timeframe_alignment: dict[str, str] = field(default_factory=dict)
    requires_ai_review: bool = False


class BaseStrategy(ABC):
    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        indicators: dict[str, IndicatorSnapshot],
        current_price: float,
    ) -> TradeSignal | None:
        ...
