from __future__ import annotations

from ..core.config import StrategyConfig
from ..core.constants import Side, SignalStrength
from ..core.logging import get_logger
from ..indicators.engine import IndicatorSnapshot
from .base import TradeSignal

log = get_logger("futurex.strategy.signal_scorer")


class SignalScorer:
    """
    Refactored signal scorer based on market structure and volume confirmation.

    Strategy:
    1. Trend filter: 4h EMA200 - only long above, only short below
    2. Entry trigger: Keltner Channel breakout with volume confirmation
    3. Volatility filter: ADX > 25 to avoid choppy markets
    """

    def __init__(self, config: StrategyConfig) -> None:
        self._config = config
        self._adx_threshold = 25.0
        self._volume_multiplier = 1.5

    def score(
        self,
        symbol: str,
        indicators: dict[str, IndicatorSnapshot],
        current_price: float,
    ) -> TradeSignal | None:
        """
        Generate trade signal based on Keltner Channel breakout + volume + ADX.

        Returns None if:
        - No 4h data available
        - ADX < 25 (choppy market)
        - No Keltner breakout
        - Volume not confirmed
        - Against 4h EMA200 trend
        """
        snap_1h = indicators.get("1h")
        snap_4h = indicators.get("4h")

        if not snap_1h or not snap_1h.values:
            return None

        # Get 1h indicators
        kc_upper = snap_1h.get("kc_upper")
        kc_lower = snap_1h.get("kc_lower")
        volume = snap_1h.get("volume")
        volume_sma = snap_1h.get("volume_sma")
        adx = snap_1h.get("adx")

        # Check if all required indicators are available
        if None in [kc_upper, kc_lower, volume, volume_sma, adx]:
            return None

        # Filter 1: ADX must be > 25 (trending market)
        if adx < self._adx_threshold:
            return None

        # Filter 2: Volume confirmation (current volume > 1.5x average)
        if volume < volume_sma * self._volume_multiplier:
            return None

        # Filter 3: Keltner Channel breakout
        long_breakout = current_price > kc_upper
        short_breakout = current_price < kc_lower

        if not long_breakout and not short_breakout:
            return None

        # Determine direction
        direction = Side.LONG if long_breakout else Side.SHORT

        # Filter 4: 4h EMA200 trend alignment (hard filter)
        if snap_4h and snap_4h.values:
            ema_200_4h = snap_4h.get("ema_200")
            if ema_200_4h:
                if direction == Side.LONG and current_price < ema_200_4h:
                    log.info(
                        "signal_filtered_trend",
                        symbol=symbol,
                        reason="Price below 4h EMA200, rejecting LONG",
                        price=current_price,
                        ema200=ema_200_4h,
                    )
                    return None
                elif direction == Side.SHORT and current_price > ema_200_4h:
                    log.info(
                        "signal_filtered_trend",
                        symbol=symbol,
                        reason="Price above 4h EMA200, rejecting SHORT",
                        price=current_price,
                        ema200=ema_200_4h,
                    )
                    return None

        # Calculate signal score based on strength of breakout and ADX
        breakout_distance = (
            (current_price - kc_upper) / kc_upper * 100
            if direction == Side.LONG
            else (kc_lower - current_price) / kc_lower * 100
        )
        volume_ratio = volume / volume_sma if volume_sma > 0 else 0

        # Score components
        breakout_score = min(breakout_distance * 10, 40.0)  # Max 40 points
        adx_score = min((adx - 25) / 25 * 30, 30.0)  # Max 30 points
        volume_score = min((volume_ratio - 1.5) / 1.5 * 30, 30.0)  # Max 30 points

        total_score = breakout_score + adx_score + volume_score
        if direction == Side.SHORT:
            total_score = -total_score

        # Determine strength
        abs_score = abs(total_score)
        if abs_score >= 60:
            strength = SignalStrength.STRONG
        else:
            strength = SignalStrength.MODERATE

        # Build components for logging
        components = {
            "breakout": breakout_score if direction == Side.LONG else -breakout_score,
            "adx": adx_score if direction == Side.LONG else -adx_score,
            "volume": volume_score if direction == Side.LONG else -volume_score,
        }

        # Moderate signals are useful enough to consider, but ambiguous enough to
        # benefit from the optional AI sentiment filter before risking capital.
        requires_ai = strength == SignalStrength.MODERATE

        signal = TradeSignal(
            symbol=symbol,
            direction=direction,
            score=total_score,
            strength=strength,
            components=components,
            timeframe_alignment={"4h": "ALIGNED"},
            requires_ai_review=requires_ai,
        )

        log.info(
            "signal_generated",
            symbol=symbol,
            direction=direction.value,
            score=f"{total_score:.1f}",
            strength=strength.value,
            adx=f"{adx:.1f}",
            volume_ratio=f"{volume_ratio:.2f}",
            breakout_pct=f"{breakout_distance:.2f}%",
            components=components,
            requires_ai=requires_ai,
        )

        return signal
