"""Regime Module - 市场状态识别模块"""
from .states import RegimeState, VolatilityState, TrendStrength, TrendDirection
from .detector import RegimeDetector
from .kill_switch import RegimeKillSwitch

__all__ = [
    'RegimeState',
    'VolatilityState',
    'TrendStrength',
    'TrendDirection',
    'RegimeDetector',
    'RegimeKillSwitch',
]
