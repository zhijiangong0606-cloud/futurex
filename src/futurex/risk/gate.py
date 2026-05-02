from __future__ import annotations

from datetime import datetime

from ..core.config import RiskConfig
from ..core.constants import OrderType, Side, SignalStrength
from ..core.logging import get_logger
from . import (
    AccountState,
    OrderRequest,
    RiskVerdict,
)
from .correlation import CorrelationExposure
from .daily_limits import DailyLossLimit
from .drawdown import DrawdownCircuitBreaker
from .exposure import MaxPositionCheck
from .position_sizer import PositionSizer

log = get_logger("futurex.risk.gate")


class RiskGate:
    """Master risk gatekeeper. ALL checks must pass for trade approval."""

    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self.drawdown = DrawdownCircuitBreaker(config)
        self.daily_loss = DailyLossLimit(config.daily_loss_limit)
        self.max_positions = MaxPositionCheck(config.max_concurrent_positions)
        self.correlation = CorrelationExposure(config.correlated_exposure_limit)
        self.sizer = PositionSizer(config)

    def evaluate(
        self,
        symbol: str,
        side: Side,
        signal_score: float,
        signal_strength: SignalStrength,
        entry_price: float,
        atr: float,
        account: AccountState,
        as_of: datetime | None = None,
    ) -> RiskVerdict:
        rejections: list[str] = []
        size_multiplier = 1.0

        # Check 1: Drawdown circuit breaker
        dd_result = self.drawdown.check(account)
        if not dd_result.passed:
            rejections.append(dd_result.reason)
            log.warning("risk_rejected", check="drawdown", reason=dd_result.reason)
            return RiskVerdict(approved=False, rejections=rejections)
        if dd_result.adjustment.get("size_multiplier"):
            size_multiplier *= dd_result.adjustment["size_multiplier"]

        # Check 2: Daily loss limit
        daily_result = self.daily_loss.check(account, as_of=as_of)
        if not daily_result.passed:
            rejections.append(daily_result.reason)
            log.warning("risk_rejected", check="daily_loss", reason=daily_result.reason)
            return RiskVerdict(approved=False, rejections=rejections)

        # Check 3: Max concurrent positions
        pos_result = self.max_positions.check(account)
        if not pos_result.passed:
            rejections.append(pos_result.reason)
            log.warning("risk_rejected", check="max_positions", reason=pos_result.reason)
            return RiskVerdict(approved=False, rejections=rejections)

        # Check 4: Correlation exposure
        corr_result = self.correlation.check(symbol, account)
        if not corr_result.passed:
            rejections.append(corr_result.reason)
            log.warning("risk_rejected", check="correlation", reason=corr_result.reason)
            return RiskVerdict(approved=False, rejections=rejections)

        # Check 5: Position sizing (fixed fractional based on signal score)
        # Note: size_multiplier from drawdown tier adjustments still applies
        sizing = self.sizer.compute(side, entry_price, atr, account, signal_score, size_multiplier)

        if sizing.position_size <= 0:
            rejections.append("Computed position size is zero or negative")
            return RiskVerdict(approved=False, rejections=rejections)

        order = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=sizing.position_size,
        )

        log.info(
            "risk_approved",
            symbol=symbol,
            side=side.value,
            score=signal_score,
            strength=signal_strength.value,
            size=sizing.position_size,
            stop=sizing.stop_loss,
            risk_amount=sizing.risk_amount,
            risk_pct=f"{sizing.risk_per_trade:.2%}",
        )

        return RiskVerdict(
            approved=True,
            order=order,
            position_size=sizing.position_size,
            stop_loss=sizing.stop_loss,
            risk_amount=sizing.risk_amount,
        )
