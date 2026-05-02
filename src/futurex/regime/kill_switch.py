"""Regime Kill Switch - 市场状态熔断器"""
from typing import Tuple
from .detector import RegimeDetector
from .states import RegimeState
import structlog

log = structlog.get_logger()


class RegimeKillSwitch:
    """市场状态熔断器"""

    def __init__(
        self,
        detector: RegimeDetector,
        min_duration: int = 3
    ):
        """
        Args:
            detector: 市场状态检测器
            min_duration: 状态切换最小持续周期（防抖）
        """
        self.detector = detector
        self.min_duration = min_duration
        self.current_regime = None
        self.regime_duration = 0
        self.pending_regime = None

    def should_allow_entry(self, df_1d) -> Tuple[bool, str, RegimeState]:
        """
        判断是否允许开仓

        Args:
            df_1d: 1D K线数据

        Returns:
            (允许开仓, 原因, 当前状态)
        """
        # 检测当前市场状态
        detected_regime = self.detector.detect(df_1d)

        # 状态切换逻辑（带滞后防抖）
        if self.current_regime is None:
            # 首次检测
            self.current_regime = detected_regime
            self.regime_duration = 1
        elif detected_regime != self.current_regime:
            # 状态变化
            if self.pending_regime == detected_regime:
                # 持续检测到新状态
                self.regime_duration += 1
                if self.regime_duration >= self.min_duration:
                    # 确认切换
                    log.info("regime_changed",
                            old=self.current_regime.value,
                            new=detected_regime.value,
                            duration=self.regime_duration)
                    self.current_regime = detected_regime
                    self.regime_duration = 1
                    self.pending_regime = None
            else:
                # 新的待切换状态
                self.pending_regime = detected_regime
                self.regime_duration = 1
        else:
            # 状态稳定
            self.regime_duration += 1
            self.pending_regime = None

        # 熔断判定
        regime = self.current_regime

        if regime == RegimeState.DEAD_CHOP:
            return False, "Low volatility dead chop - no trading", regime

        if regime == RegimeState.RANGE_BOUND:
            return False, "Range-bound market - trend strategy disabled", regime

        if regime == RegimeState.VOLATILE_CHOP:
            return False, "High volatility chop - risky environment", regime

        # 允许交易的状态
        if regime in [RegimeState.TREND_BULL, RegimeState.TREND_BEAR]:
            return True, f"Trend detected ({regime.value}) - trading enabled", regime

        # 默认不允许
        return False, f"Unknown regime {regime.value}", regime
