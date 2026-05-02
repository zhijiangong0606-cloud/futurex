from __future__ import annotations

from futurex.core.config import AIConfig
from futurex.core.constants import Side, SignalStrength
from futurex.strategy.ai_filter import AIFilter
from futurex.strategy.base import TradeSignal


def _signal(strength: SignalStrength) -> TradeSignal:
    return TradeSignal(
        symbol="BTCUSDT",
        direction=Side.LONG,
        score=45.0,
        strength=strength,
        requires_ai_review=True,
    )


class TestAIFilterReviewMode:
    def test_moderate_mode_allows_moderate_signal(self) -> None:
        ai_filter = AIFilter(AIConfig(enabled=True, review_mode="moderate"))

        assert ai_filter.should_call(_signal(SignalStrength.MODERATE))

    def test_moderate_mode_skips_strong_signal(self) -> None:
        ai_filter = AIFilter(AIConfig(enabled=True, review_mode="moderate"))

        assert not ai_filter.should_call(_signal(SignalStrength.STRONG))

    def test_disabled_mode_skips_all_signals(self) -> None:
        ai_filter = AIFilter(AIConfig(enabled=True, review_mode="off"))

        assert not ai_filter.should_call(_signal(SignalStrength.MODERATE))
