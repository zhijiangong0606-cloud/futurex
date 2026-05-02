from __future__ import annotations

from enum import Enum


class Side(str, Enum):
    LONG = "BUY"
    SHORT = "SELL"

    @property
    def close_side(self) -> Side:
        return Side.SHORT if self is Side.LONG else Side.LONG


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTX = "GTX"


class MarginType(str, Enum):
    ISOLATED = "ISOLATED"
    CROSSED = "CROSSED"


class PositionSide(str, Enum):
    BOTH = "BOTH"
    LONG = "LONG"
    SHORT = "SHORT"


class DrawdownTier(str, Enum):
    NORMAL = "NORMAL"
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"


class SignalStrength(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    NONE = "NONE"


BINANCE_FUTURES_REST = "https://fapi.binance.com"
BINANCE_FUTURES_WS = "wss://fstream.binance.com"
BINANCE_TESTNET_REST = "https://testnet.binancefuture.com"
BINANCE_TESTNET_WS = "wss://stream.binancefuture.com"

LISTEN_KEY_RENEW_INTERVAL = 30 * 60  # 30 minutes
WS_HEARTBEAT_INTERVAL = 5 * 60  # 5 minutes (under 10min limit)
REST_WEIGHT_LIMIT = 2400  # per minute
REST_WEIGHT_WARN_THRESHOLD = 0.8  # 80% -> start throttling
