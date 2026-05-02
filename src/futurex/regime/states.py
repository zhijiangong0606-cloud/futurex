"""Market Regime States - 市场状态枚举"""
from enum import Enum


class RegimeState(Enum):
    """市场状态"""
    TREND_BULL = "TREND_BULL"           # 多头趋势
    TREND_BEAR = "TREND_BEAR"           # 空头趋势
    VOLATILE_CHOP = "VOLATILE_CHOP"     # 高波震荡
    RANGE_BOUND = "RANGE_BOUND"         # 区间震荡
    DEAD_CHOP = "DEAD_CHOP"             # 低波死寂


class VolatilityState(Enum):
    """波动率状态"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TrendStrength(Enum):
    """趋势强度"""
    NONE = "NONE"
    WEAK = "WEAK"
    STRONG = "STRONG"


class TrendDirection(Enum):
    """趋势方向"""
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"
