from __future__ import annotations

import pytest

from futurex.core.config import RiskConfig
from futurex.core.constants import Side
from futurex.risk import AccountState, TradeRecord
from futurex.risk.position_sizer import PositionSizer


@pytest.fixture
def config() -> RiskConfig:
    return RiskConfig(
        max_risk_per_trade=0.02,
        hard_cap_per_trade=0.05,
        atr_multiplier=2.0,
    )


@pytest.fixture
def sizer(config: RiskConfig) -> PositionSizer:
    return PositionSizer(config)


class TestPositionSizer:
    def test_basic_sizing_long(self, sizer: PositionSizer) -> None:
        account = AccountState(equity=10000.0)
        result = sizer.compute(Side.LONG, 50000.0, 500.0, account)
        assert result.position_size > 0
        assert result.stop_loss < 50000.0
        assert result.stop_distance == 1000.0  # 500 * 2.0

    def test_basic_sizing_short(self, sizer: PositionSizer) -> None:
        account = AccountState(equity=10000.0)
        result = sizer.compute(Side.SHORT, 50000.0, 500.0, account)
        assert result.position_size > 0
        assert result.stop_loss > 50000.0

    def test_risk_amount_within_limits(self, sizer: PositionSizer) -> None:
        account = AccountState(equity=10000.0)
        result = sizer.compute(Side.LONG, 50000.0, 500.0, account)
        assert result.risk_amount <= 10000.0 * 0.05  # hard cap 5%

    def test_size_multiplier_reduces_position(self, sizer: PositionSizer) -> None:
        account = AccountState(equity=10000.0)
        full = sizer.compute(Side.LONG, 50000.0, 500.0, account, size_multiplier=1.0)
        half = sizer.compute(Side.LONG, 50000.0, 500.0, account, size_multiplier=0.5)
        assert half.position_size < full.position_size

    def test_zero_atr_returns_zero(self, sizer: PositionSizer) -> None:
        account = AccountState(equity=10000.0)
        result = sizer.compute(Side.LONG, 50000.0, 0.0, account)
        assert result.position_size == 0

    def test_notional_cap(self, sizer: PositionSizer) -> None:
        account = AccountState(equity=1000000.0)  # very large account
        result = sizer.compute(Side.LONG, 100.0, 1.0, account)
        assert result.position_size * 100.0 <= 50000.0  # max notional

    def test_kelly_with_trade_history(self, sizer: PositionSizer) -> None:
        for _ in range(15):
            sizer.add_trade(
                TradeRecord("BTC", "BUY", 50000, 51000, 0.1, 100, 3600, 0, 0)
            )
        for _ in range(10):
            sizer.add_trade(
                TradeRecord("BTC", "BUY", 50000, 49500, 0.1, -50, 3600, 0, 0)
            )
        # Still uses defaults (< 20 trades threshold)
        account = AccountState(equity=10000.0)
        result = sizer.compute(Side.LONG, 50000.0, 500.0, account)
        assert result.kelly_fraction > 0

    def test_kelly_with_enough_history(self, sizer: PositionSizer) -> None:
        for _ in range(15):
            sizer.add_trade(
                TradeRecord("BTC", "BUY", 50000, 51000, 0.1, 100, 3600, 0, 0)
            )
        for _ in range(10):
            sizer.add_trade(
                TradeRecord("BTC", "BUY", 50000, 49500, 0.1, -50, 3600, 0, 0)
            )
        account = AccountState(equity=10000.0)
        result = sizer.compute(Side.LONG, 50000.0, 500.0, account)
        assert result.position_size > 0
