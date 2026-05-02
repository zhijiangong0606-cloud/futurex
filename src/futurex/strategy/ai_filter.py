from __future__ import annotations

import time
from typing import Any

from ..core.config import AIConfig
from ..core.constants import SignalStrength
from ..core.logging import get_logger
from .base import TradeSignal

log = get_logger("futurex.strategy.ai_filter")

_SYSTEM_PROMPT = """You are a crypto market sentiment analyzer for a futures trading bot.
Given technical indicator data for a trading signal, provide a sentiment adjustment.

Respond ONLY with JSON: {"sentiment": <float between -0.3 and 0.3>, "reason": "<one sentence>"}

Positive sentiment: indicators suggest the signal direction is supported by broader market context.
Negative: indicators suggest caution. Zero: neutral/no strong opinion.

You are NOT making a trading decision. You provide a small adjustment to an existing mathematical signal."""


class AIFilter:
    def __init__(self, config: AIConfig) -> None:
        self._config = config
        self._daily_call_count = 0
        self._last_reset_day: str = ""
        self._cooldowns: dict[str, float] = {}
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic()
        return self._client

    def should_call(self, signal: TradeSignal) -> bool:
        if not self._config.enabled:
            return False

        review_mode = self._config.review_mode.lower()
        if review_mode in {"off", "disabled", "none"}:
            return False
        if review_mode == "moderate" and signal.strength != SignalStrength.MODERATE:
            return False

        today = time.strftime("%Y-%m-%d")
        if self._last_reset_day != today:
            self._daily_call_count = 0
            self._last_reset_day = today

        if self._daily_call_count >= self._config.max_daily_calls:
            return False

        if not signal.requires_ai_review:
            return False

        cooldown_key = f"{signal.symbol}_{signal.direction.value}"
        last_call = self._cooldowns.get(cooldown_key, 0)
        if time.time() - last_call < self._config.cooldown_hours * 3600:
            return False

        return True

    async def evaluate(
        self,
        signal: TradeSignal,
        indicator_summary: dict[str, Any],
    ) -> float:
        if not self.should_call(signal):
            return 0.0

        user_msg = self._build_user_message(signal, indicator_summary)

        try:
            client = await self._get_client()
            response = await client.messages.create(
                model=self._config.model,
                max_tokens=100,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_msg}],
            )

            self._daily_call_count += 1
            cooldown_key = f"{signal.symbol}_{signal.direction.value}"
            self._cooldowns[cooldown_key] = time.time()

            text = response.content[0].text
            import json

            result = json.loads(text)
            sentiment = float(result.get("sentiment", 0.0))

            sentiment = max(
                -self._config.max_sentiment_adjustment,
                min(self._config.max_sentiment_adjustment, sentiment),
            )

            log.info(
                "ai_sentiment",
                symbol=signal.symbol,
                sentiment=sentiment,
                reason=result.get("reason", ""),
                daily_calls=self._daily_call_count,
            )

            return sentiment

        except Exception as e:
            log.error("ai_filter_error", error=str(e))
            return 0.0

    def _build_user_message(
        self, signal: TradeSignal, indicators: dict[str, Any]
    ) -> str:
        lines = [
            f"Symbol: {signal.symbol}, Signal: {signal.direction.value} (score: {signal.score:.0f})",
            f"Components: {signal.components}",
            "",
        ]

        for tf, values in indicators.items():
            parts = [f"{k}={v:.2f}" for k, v in values.items() if isinstance(v, (int, float))]
            lines.append(f"{tf}: {', '.join(parts)}")

        return "\n".join(lines)
