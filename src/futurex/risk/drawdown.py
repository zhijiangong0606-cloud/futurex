from __future__ import annotations

from datetime import datetime, timezone

from ..core.config import RiskConfig
from ..core.constants import DrawdownTier
from ..core.logging import get_logger
from . import AccountState, RiskCheckResult

log = get_logger("futurex.risk.drawdown")


class DrawdownCircuitBreaker:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self._peak_equity: float = 0.0
        self._tier: DrawdownTier = DrawdownTier.NORMAL
        self._cooldown_until: datetime | None = None

    @property
    def tier(self) -> DrawdownTier:
        return self._tier

    @property
    def peak_equity(self) -> float:
        return self._peak_equity

    @property
    def current_drawdown(self) -> float:
        if self._peak_equity <= 0:
            return 0.0
        return (self._peak_equity - self._last_equity) / self._peak_equity

    def initialize(self, equity: float, saved_peak: float | None = None) -> None:
        self._last_equity = equity
        self._peak_equity = saved_peak if saved_peak and saved_peak > equity else equity

    def update(self, current_equity: float) -> DrawdownTier:
        self._last_equity = current_equity

        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

        if self._peak_equity <= 0:
            return DrawdownTier.NORMAL

        drawdown = (self._peak_equity - current_equity) / self._peak_equity

        previous_tier = self._tier

        if drawdown >= self._config.drawdown_tier3:
            self._tier = DrawdownTier.TIER_3
        elif drawdown >= self._config.drawdown_tier2:
            self._tier = DrawdownTier.TIER_2
        elif drawdown >= self._config.drawdown_tier1:
            self._tier = DrawdownTier.TIER_1
        else:
            self._tier = DrawdownTier.NORMAL

        if self._tier != previous_tier:
            log.warning(
                "drawdown_tier_change",
                previous=previous_tier.value,
                current=self._tier.value,
                drawdown=f"{drawdown:.2%}",
                peak=self._peak_equity,
                current_equity=current_equity,
            )

        return self._tier

    def check(self, account: AccountState) -> RiskCheckResult:
        if self._cooldown_until:
            now = datetime.now(timezone.utc)
            if now < self._cooldown_until:
                remaining = (self._cooldown_until - now).total_seconds() / 3600
                return RiskCheckResult(
                    passed=False,
                    reason=f"TIER_3 cooldown active, {remaining:.1f}h remaining",
                )
            else:
                self._cooldown_until = None
                self._peak_equity = account.equity
                log.info("cooldown_expired", new_peak=account.equity)

        self.update(account.equity)

        if self._tier == DrawdownTier.TIER_3:
            from datetime import timedelta

            self._cooldown_until = datetime.now(timezone.utc) + timedelta(
                hours=self._config.cooldown_hours
            )
            return RiskCheckResult(
                passed=False,
                reason=f"TIER_3 triggered: drawdown {self.current_drawdown:.2%}, "
                f"cooldown {self._config.cooldown_hours}h",
            )

        if self._tier == DrawdownTier.TIER_2:
            return RiskCheckResult(
                passed=False,
                reason=f"TIER_2: drawdown {self.current_drawdown:.2%}, new entries blocked",
            )

        if self._tier == DrawdownTier.TIER_1:
            return RiskCheckResult(
                passed=True,
                reason=f"TIER_1: drawdown {self.current_drawdown:.2%}, position size halved",
                adjustment={"size_multiplier": 0.5},
            )

        return RiskCheckResult(passed=True)

    def needs_emergency_flatten(self) -> bool:
        return self._tier == DrawdownTier.TIER_3

    def get_stop_multiplier_override(self) -> float | None:
        if self._tier == DrawdownTier.TIER_2:
            return 1.5
        return None
