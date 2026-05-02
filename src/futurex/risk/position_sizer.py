from __future__ import annotations

from ..core.config import RiskConfig
from ..core.constants import Side
from ..core.logging import get_logger
from . import AccountState, SizingResult, TradeRecord

log = get_logger("futurex.risk.position_sizer")


class PositionSizer:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self._trade_history: list[TradeRecord] = []

    def add_trade(self, trade: TradeRecord) -> None:
        """Keep trade history for potential future analysis, but not used for sizing."""
        self._trade_history.append(trade)
        if len(self._trade_history) > 200:
            self._trade_history = self._trade_history[-200:]

    def compute(
        self,
        side: Side,
        entry_price: float,
        atr: float,
        account: AccountState,
        signal_score: float,
        size_multiplier: float = 1.0,
    ) -> SizingResult:
        """
        Fixed fractional position sizing based on signal strength.

        Risk allocation:
        - Score 40-59 (MODERATE): 1% of equity at risk
        - Score 60-80 (STRONG): 2% of equity at risk

        Position size is calculated to ensure that if ATR stop is hit,
        the loss equals the allocated risk percentage.
        """
        abs_score = abs(signal_score)

        if abs_score >= 60:
            base_risk = 0.02  # 2% for STRONG signals
        elif abs_score >= 40:
            base_risk = 0.01  # 1% for MODERATE signals
        else:
            base_risk = 0.0  # Should not happen (filtered by scorer)

        risk_per_trade = min(base_risk, self._config.hard_cap_per_trade)
        risk_per_trade = min(risk_per_trade, self._config.max_risk_per_trade)
        risk_per_trade *= size_multiplier

        atr_mult = self._config.atr_multiplier
        stop_distance = atr * atr_mult

        if stop_distance <= 0 or entry_price <= 0:
            return SizingResult(
                position_size=0,
                stop_loss=0,
                stop_distance=0,
                risk_amount=0,
                kelly_fraction=0.0,
                risk_per_trade=risk_per_trade,
            )

        risk_amount = account.equity * risk_per_trade
        position_size = risk_amount / stop_distance

        max_notional = 50_000.0
        max_size_by_notional = max_notional / entry_price
        position_size = min(position_size, max_size_by_notional)

        if side == Side.LONG:
            stop_loss = entry_price - stop_distance
        else:
            stop_loss = entry_price + stop_distance

        stop_loss = max(stop_loss, 0.0)

        log.info(
            "position_sized",
            side=side.value,
            entry=entry_price,
            atr=atr,
            stop_distance=stop_distance,
            stop_loss=stop_loss,
            position_size=position_size,
            risk_amount=risk_amount,
            signal_score=signal_score,
            risk_pct=f"{risk_per_trade:.2%}",
        )

        return SizingResult(
            position_size=position_size,
            stop_loss=stop_loss,
            stop_distance=stop_distance,
            risk_amount=risk_amount,
            kelly_fraction=0.0,  # No longer used
            risk_per_trade=risk_per_trade,
        )
