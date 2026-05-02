from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExchangeConfig(BaseModel):
    testnet: bool = True
    base_url: str = ""
    ws_url: str = ""
    symbols: list[str] = ["BTCUSDT"]
    timeframes: list[str] = ["1m", "5m", "15m", "1h", "4h"]
    leverage: int = 5
    margin_type: str = "ISOLATED"


class RiskConfig(BaseModel):
    max_risk_per_trade: float = 0.02
    hard_cap_per_trade: float = 0.05
    atr_multiplier: float = 2.0
    atr_period: int = 14
    max_concurrent_positions: int = 3
    daily_loss_limit: float = 0.03
    drawdown_tier1: float = 0.03
    drawdown_tier2: float = 0.05
    drawdown_tier3: float = 0.10
    cooldown_hours: int = 24
    correlated_exposure_limit: float = 0.08


class StrategyConfig(BaseModel):
    trend_weight: float = 0.40
    momentum_weight: float = 0.30
    pullback_weight: float = 0.20
    volume_weight: float = 0.10
    entry_threshold: float = 60.0
    partial_threshold: float = 40.0
    ema_fast: int = 20
    ema_medium: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0


class AIConfig(BaseModel):
    enabled: bool = True
    model: str = "claude-haiku-4-5-20251001"
    review_mode: str = "moderate"
    max_daily_calls: int = 20
    cooldown_hours: float = 4.0
    max_sentiment_adjustment: float = 0.3
    use_batch_api: bool = True


class StorageConfig(BaseModel):
    redis_url: str = "redis://localhost:6379/0"
    duckdb_path: str = "data/trading.duckdb"


class NotifyConfig(BaseModel):
    telegram_enabled: bool = True
    notify_on: list[str] = [
        "trade_open",
        "trade_close",
        "risk_alert",
        "system_error",
    ]


class AppConfig(BaseModel):
    exchange: ExchangeConfig = ExchangeConfig()
    risk: RiskConfig = RiskConfig()
    strategy: StrategyConfig = StrategyConfig()
    ai: AIConfig = AIConfig()
    storage: StorageConfig = StorageConfig()
    notify: NotifyConfig = NotifyConfig()


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    binance_api_key: str = ""
    binance_api_secret: str = ""
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    proxy_url: str = ""


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_dir: str | Path = "config", profile: str = "default") -> AppConfig:
    config_dir = Path(config_dir)
    default_path = config_dir / "default.toml"

    data: dict[str, Any] = {}
    if default_path.exists():
        with open(default_path, "rb") as f:
            data = tomllib.load(f)

    if profile != "default":
        profile_path = config_dir / f"{profile}.toml"
        if profile_path.exists():
            with open(profile_path, "rb") as f:
                override = tomllib.load(f)
            data = _deep_merge(data, override)

    config = AppConfig(**data)

    from .constants import (
        BINANCE_FUTURES_REST,
        BINANCE_FUTURES_WS,
        BINANCE_TESTNET_REST,
        BINANCE_TESTNET_WS,
    )

    if not config.exchange.base_url:
        config.exchange.base_url = (
            BINANCE_TESTNET_REST if config.exchange.testnet else BINANCE_FUTURES_REST
        )
    if not config.exchange.ws_url:
        config.exchange.ws_url = (
            BINANCE_TESTNET_WS if config.exchange.testnet else BINANCE_FUTURES_WS
        )

    return config
