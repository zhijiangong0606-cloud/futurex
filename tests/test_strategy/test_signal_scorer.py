from __future__ import annotations

from futurex.core.config import StrategyConfig
from futurex.core.constants import SignalStrength
from futurex.indicators.engine import IndicatorSnapshot
from futurex.strategy.signal_scorer import SignalScorer


def _snapshot(values: dict[str, float]) -> IndicatorSnapshot:
    return IndicatorSnapshot(values=values)


class TestSignalScorerAIReview:
    def test_moderate_signal_requires_ai_review(self) -> None:
        scorer = SignalScorer(StrategyConfig())
        indicators = {
            "1h": _snapshot(
                {
                    "kc_upper": 100.0,
                    "kc_lower": 80.0,
                    "volume": 160.0,
                    "volume_sma": 100.0,
                    "adx": 30.0,
                }
            ),
            "4h": _snapshot({"ema_200": 90.0}),
        }

        signal = scorer.score("BTCUSDT", indicators, current_price=101.0)

        assert signal is not None
        assert signal.strength == SignalStrength.MODERATE
        assert signal.requires_ai_review

    def test_strong_signal_skips_ai_review(self) -> None:
        scorer = SignalScorer(StrategyConfig())
        indicators = {
            "1h": _snapshot(
                {
                    "kc_upper": 100.0,
                    "kc_lower": 80.0,
                    "volume": 320.0,
                    "volume_sma": 100.0,
                    "adx": 60.0,
                }
            ),
            "4h": _snapshot({"ema_200": 90.0}),
        }

        signal = scorer.score("BTCUSDT", indicators, current_price=105.0)

        assert signal is not None
        assert signal.strength == SignalStrength.STRONG
        assert not signal.requires_ai_review
