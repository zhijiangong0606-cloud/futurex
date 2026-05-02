from __future__ import annotations

import pytest

from futurex.core.config import RiskConfig
from futurex.core.constants import DrawdownTier
from futurex.risk import AccountState
from futurex.risk.drawdown import DrawdownCircuitBreaker


@pytest.fixture
def config() -> RiskConfig:
    return RiskConfig(
        drawdown_tier1=0.03,
        drawdown_tier2=0.05,
        drawdown_tier3=0.10,
        cooldown_hours=24,
    )


@pytest.fixture
def breaker(config: RiskConfig) -> DrawdownCircuitBreaker:
    cb = DrawdownCircuitBreaker(config)
    cb.initialize(10000.0)
    return cb


class TestDrawdownCircuitBreaker:
    def test_normal_state(self, breaker: DrawdownCircuitBreaker) -> None:
        tier = breaker.update(10000.0)
        assert tier == DrawdownTier.NORMAL

    def test_tier1_at_3_percent(self, breaker: DrawdownCircuitBreaker) -> None:
        tier = breaker.update(9700.0)
        assert tier == DrawdownTier.TIER_1

    def test_tier2_at_5_percent(self, breaker: DrawdownCircuitBreaker) -> None:
        tier = breaker.update(9500.0)
        assert tier == DrawdownTier.TIER_2

    def test_tier3_at_10_percent(self, breaker: DrawdownCircuitBreaker) -> None:
        tier = breaker.update(9000.0)
        assert tier == DrawdownTier.TIER_3

    def test_peak_tracking(self, breaker: DrawdownCircuitBreaker) -> None:
        breaker.update(10500.0)
        assert breaker.peak_equity == 10500.0
        breaker.update(10200.0)
        assert breaker.peak_equity == 10500.0  # peak should not decrease

    def test_check_blocks_at_tier2(self, breaker: DrawdownCircuitBreaker) -> None:
        account = AccountState(equity=9500.0)
        result = breaker.check(account)
        assert not result.passed

    def test_check_allows_with_adjustment_at_tier1(
        self, breaker: DrawdownCircuitBreaker
    ) -> None:
        account = AccountState(equity=9700.0)
        result = breaker.check(account)
        assert result.passed
        assert result.adjustment.get("size_multiplier") == 0.5

    def test_check_allows_in_normal(self, breaker: DrawdownCircuitBreaker) -> None:
        account = AccountState(equity=10000.0)
        result = breaker.check(account)
        assert result.passed

    def test_needs_emergency_flatten(self, breaker: DrawdownCircuitBreaker) -> None:
        breaker.update(9000.0)
        assert breaker.needs_emergency_flatten()

    def test_no_emergency_flatten_normal(self, breaker: DrawdownCircuitBreaker) -> None:
        breaker.update(10000.0)
        assert not breaker.needs_emergency_flatten()

    def test_recovery_from_drawdown(self, breaker: DrawdownCircuitBreaker) -> None:
        breaker.update(9700.0)
        assert breaker.tier == DrawdownTier.TIER_1
        breaker.update(10000.0)
        assert breaker.tier == DrawdownTier.NORMAL
