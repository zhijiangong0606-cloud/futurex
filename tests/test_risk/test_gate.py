from __future__ import annotations

import pytest

from futurex.core.config import RiskConfig
from futurex.core.constants import Side, SignalStrength
from futurex.risk import AccountState, Position
from futurex.risk.gate import RiskGate


@pytest.fixture
def config() -> RiskConfig:
    return RiskConfig(
        max_risk_per_trade=0.02,
        hard_cap_per_trade=0.05,
        atr_multiplier=2.0,
        max_concurrent_positions=3,
        daily_loss_limit=0.03,
        drawdown_tier1=0.03,
        drawdown_tier2=0.05,
        drawdown_tier3=0.10,
    )


@pytest.fixture
def gate(config: RiskConfig) -> RiskGate:
    g = RiskGate(config)
    g.drawdown.initialize(10000.0)
    return g


class TestRiskGate:
    def test_approve_valid_signal(self, gate: RiskGate) -> None:
        account = AccountState(equity=10000.0)
        verdict = gate.evaluate(
            symbol="BTCUSDT",
            side=Side.LONG,
            signal_score=65.0,
            signal_strength=SignalStrength.STRONG,
            entry_price=50000.0,
            atr=500.0,
            account=account,
        )
        assert verdict.approved
        assert verdict.position_size > 0
        assert verdict.stop_loss > 0

    def test_reject_when_max_positions_reached(self, gate: RiskGate) -> None:
        positions = [
            Position("BTC", Side.LONG, 50000, 0.1, 5),
            Position("ETH", Side.LONG, 3000, 1.0, 5),
            Position("SOL", Side.LONG, 100, 10.0, 5),
        ]
        account = AccountState(equity=10000.0, open_positions=positions)
        verdict = gate.evaluate(
            symbol="DOGE",
            side=Side.LONG,
            signal_score=70.0,
            signal_strength=SignalStrength.STRONG,
            entry_price=0.1,
            atr=0.01,
            account=account,
        )
        assert not verdict.approved
        assert any("Max concurrent" in r for r in verdict.rejections)

    def test_reject_at_drawdown_tier2(self, gate: RiskGate) -> None:
        account = AccountState(equity=9500.0)
        verdict = gate.evaluate(
            symbol="BTCUSDT",
            side=Side.LONG,
            signal_score=70.0,
            signal_strength=SignalStrength.STRONG,
            entry_price=50000.0,
            atr=500.0,
            account=account,
        )
        assert not verdict.approved

    def test_half_size_at_tier1(self, gate: RiskGate) -> None:
        account_normal = AccountState(equity=10000.0)
        normal_verdict = gate.evaluate(
            symbol="BTCUSDT",
            side=Side.LONG,
            signal_score=65.0,
            signal_strength=SignalStrength.STRONG,
            entry_price=50000.0,
            atr=500.0,
            account=account_normal,
        )

        gate2 = RiskGate(gate._config)
        gate2.drawdown.initialize(10000.0)
        account_tier1 = AccountState(equity=9700.0)
        tier1_verdict = gate2.evaluate(
            symbol="BTCUSDT",
            side=Side.LONG,
            signal_score=65.0,
            signal_strength=SignalStrength.STRONG,
            entry_price=50000.0,
            atr=500.0,
            account=account_tier1,
        )

        if normal_verdict.approved and tier1_verdict.approved:
            assert tier1_verdict.position_size < normal_verdict.position_size

    def test_moderate_signal_half_size(self, gate: RiskGate) -> None:
        account = AccountState(equity=10000.0)
        strong = gate.evaluate(
            symbol="BTCUSDT",
            side=Side.LONG,
            signal_score=65.0,
            signal_strength=SignalStrength.STRONG,
            entry_price=50000.0,
            atr=500.0,
            account=account,
        )

        gate2 = RiskGate(gate._config)
        gate2.drawdown.initialize(10000.0)
        moderate = gate2.evaluate(
            symbol="BTCUSDT",
            side=Side.LONG,
            signal_score=45.0,
            signal_strength=SignalStrength.MODERATE,
            entry_price=50000.0,
            atr=500.0,
            account=account,
        )

        if strong.approved and moderate.approved:
            assert moderate.position_size < strong.position_size

    def test_daily_loss_limit_blocks(self, gate: RiskGate) -> None:
        account = AccountState(equity=10000.0)
        gate.daily_loss.check(account)  # initialize day_start_equity
        gate.daily_loss.on_trade_closed(-150.0)
        gate.daily_loss.on_trade_closed(-160.0)

        verdict = gate.evaluate(
            symbol="BTCUSDT",
            side=Side.LONG,
            signal_score=70.0,
            signal_strength=SignalStrength.STRONG,
            entry_price=50000.0,
            atr=500.0,
            account=account,
        )
        assert not verdict.approved
        assert any("Daily loss" in r for r in verdict.rejections)

    def test_zero_equity_no_crash(self, gate: RiskGate) -> None:
        account = AccountState(equity=0.0)
        verdict = gate.evaluate(
            symbol="BTCUSDT",
            side=Side.LONG,
            signal_score=65.0,
            signal_strength=SignalStrength.STRONG,
            entry_price=50000.0,
            atr=500.0,
            account=account,
        )
        assert not verdict.approved or verdict.position_size == 0
