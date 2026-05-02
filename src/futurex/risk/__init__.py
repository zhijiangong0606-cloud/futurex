from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.constants import Side, OrderType


@dataclass
class Position:
    symbol: str
    side: Side
    entry_price: float
    quantity: float
    leverage: int
    unrealized_pnl: float = 0.0
    stop_order_id: int | None = None
    stop_price: float = 0.0
    trailing_activated: bool = False
    entry_time: float = 0.0

    @property
    def notional(self) -> float:
        return abs(self.quantity * self.entry_price)


@dataclass
class AccountState:
    equity: float = 0.0
    available_balance: float = 0.0
    total_unrealized_pnl: float = 0.0
    open_positions: list[Position] = field(default_factory=list)

    def position_for(self, symbol: str) -> Position | None:
        for p in self.open_positions:
            if p.symbol == symbol:
                return p
        return None


@dataclass
class OrderRequest:
    symbol: str
    side: Side
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    time_in_force: str | None = None
    reduce_only: bool = False
    close_position: bool = False


@dataclass
class RiskVerdict:
    approved: bool
    order: OrderRequest | None = None
    rejections: list[str] = field(default_factory=list)
    position_size: float = 0.0
    stop_loss: float = 0.0
    take_profit: float | None = None
    risk_amount: float = 0.0


@dataclass
class RiskCheckResult:
    passed: bool
    reason: str = ""
    adjustment: dict[str, Any] = field(default_factory=dict)


@dataclass
class SizingResult:
    position_size: float
    stop_loss: float
    stop_distance: float
    risk_amount: float
    kelly_fraction: float
    risk_per_trade: float


@dataclass
class TradeRecord:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    duration_seconds: float
    entry_time: float
    exit_time: float
