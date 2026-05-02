"""Market Regime Detector - 市场状态识别器"""
import pandas as pd
import numpy as np
from typing import Tuple
from .states import (
    RegimeState, VolatilityState, TrendStrength, TrendDirection
)


class RegimeDetector:
    """市场状态识别器"""

    def __init__(
        self,
        lookback_period: int = 252,
        vol_thresholds: Tuple[float, float] = (30, 70),
        adx_thresholds: Tuple[float, float] = (20, 30)
    ):
        """
        Args:
            lookback_period: 波动率分位数回溯期（默认252天）
            vol_thresholds: 波动率分位数阈值 (低, 高)
            adx_thresholds: ADX 阈值 (弱趋势, 强趋势)
        """
        self.lookback_period = lookback_period
        self.vol_low_threshold = vol_thresholds[0]
        self.vol_high_threshold = vol_thresholds[1]
        self.adx_weak_threshold = adx_thresholds[0]
        self.adx_strong_threshold = adx_thresholds[1]

    def detect(self, df_1d: pd.DataFrame) -> RegimeState:
        """
        检测市场状态

        Args:
            df_1d: 1D K线数据（需要包含 high, low, close 列）

        Returns:
            RegimeState: 当前市场状态
        """
        if len(df_1d) < self.lookback_period:
            # 数据不足，默认返回 RANGE_BOUND
            return RegimeState.RANGE_BOUND

        # 1. 计算波动率分位数
        vol_state = self._classify_volatility(df_1d)

        # 2. 计算趋势强度
        trend_strength = self._classify_trend_strength(df_1d)

        # 3. 计算趋势方向
        trend_direction = self._classify_trend_direction(df_1d)

        # 4. 状态机映射
        regime = self._map_to_regime(vol_state, trend_strength, trend_direction)

        return regime

    def _classify_volatility(self, df: pd.DataFrame) -> VolatilityState:
        """分类波动率状态"""
        # 计算 ATR%
        atr = self._calculate_atr(df, period=14)
        atr_pct = (atr / df['close']) * 100

        # 计算分位数
        percentile = self._percentile_rank(
            atr_pct.iloc[-1],
            atr_pct.iloc[-self.lookback_period:]
        )

        # 分类
        if percentile < self.vol_low_threshold:
            return VolatilityState.LOW
        elif percentile < self.vol_high_threshold:
            return VolatilityState.MEDIUM
        else:
            return VolatilityState.HIGH

    def _classify_trend_strength(self, df: pd.DataFrame) -> TrendStrength:
        """分类趋势强度"""
        adx = self._calculate_adx(df, period=14)
        current_adx = adx.iloc[-1]

        if current_adx > self.adx_strong_threshold:
            return TrendStrength.STRONG
        elif current_adx > self.adx_weak_threshold:
            return TrendStrength.WEAK
        else:
            return TrendStrength.NONE

    def _classify_trend_direction(self, df: pd.DataFrame) -> TrendDirection:
        """分类趋势方向"""
        ema50 = df['close'].ewm(span=50, adjust=False).mean()
        ema200 = df['close'].ewm(span=200, adjust=False).mean()
        close = df['close'].iloc[-1]

        # 多头排列
        if close > ema50.iloc[-1] > ema200.iloc[-1]:
            return TrendDirection.BULL

        # 空头排列
        elif close < ema50.iloc[-1] < ema200.iloc[-1]:
            return TrendDirection.BEAR

        # 混乱排列
        else:
            return TrendDirection.NEUTRAL

    def _map_to_regime(
        self,
        vol: VolatilityState,
        strength: TrendStrength,
        direction: TrendDirection
    ) -> RegimeState:
        """状态机映射"""

        # 低波动 = 死寂（无论趋势如何）
        if vol == VolatilityState.LOW:
            return RegimeState.DEAD_CHOP

        # 强趋势 + 中高波动 = 趋势市
        if strength == TrendStrength.STRONG and vol >= VolatilityState.MEDIUM:
            if direction == TrendDirection.BULL:
                return RegimeState.TREND_BULL
            elif direction == TrendDirection.BEAR:
                return RegimeState.TREND_BEAR
            else:
                # 强趋势但方向不明
                return (RegimeState.VOLATILE_CHOP if vol == VolatilityState.HIGH
                       else RegimeState.RANGE_BOUND)

        # 高波动 + 弱/无趋势 = 高波震荡
        if vol == VolatilityState.HIGH:
            return RegimeState.VOLATILE_CHOP

        # 中等波动 + 弱/无趋势 = 区间震荡
        return RegimeState.RANGE_BOUND

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算 ATR"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(span=period, adjust=False).mean()

        return atr

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算 ADX"""
        high = df['high']
        low = df['low']
        close = df['close']

        # +DM and -DM
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Smoothed +DM, -DM, TR
        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)

        # DX and ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(span=period, adjust=False).mean()

        return adx

    def _percentile_rank(self, value: float, series: pd.Series) -> float:
        """计算分位数排名"""
        return (series < value).sum() / len(series) * 100
