from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..core.logging import get_logger
from .registry import IndicatorRegistry

log = get_logger("futurex.indicators.engine")


@dataclass
class IndicatorSnapshot:
    values: dict[str, float] = field(default_factory=dict)

    def get(self, name: str, default: float = 0.0) -> float:
        return self.values.get(name, default)


class IndicatorEngine:
    def __init__(self, registry: IndicatorRegistry) -> None:
        self._registry = registry
        self._cache: dict[tuple[str, str], dict[str, pd.Series]] = {}

    def compute(
        self, symbol: str, interval: str, candles: pd.DataFrame
    ) -> IndicatorSnapshot:
        if candles.empty or len(candles) < 5:
            return IndicatorSnapshot()

        key = (symbol, interval)
        results: dict[str, pd.Series] = {}

        for indicator in self._registry.indicators:
            try:
                series = indicator.compute(candles)
                if series is not None and not series.empty:
                    results[indicator.name] = series
            except Exception as e:
                log.warning(
                    "indicator_compute_error",
                    name=indicator.name,
                    symbol=symbol,
                    interval=interval,
                    error=str(e),
                )

        self._cache[key] = results

        snapshot = IndicatorSnapshot()
        for name, series in results.items():
            if len(series) > 0:
                last_val = series.iloc[-1]
                # 处理可能是 Series 的情况
                if isinstance(last_val, pd.Series):
                    last_val = last_val.iloc[0] if len(last_val) > 0 else None
                if pd.notna(last_val):
                    snapshot.values[name] = float(last_val)

        return snapshot

    def get_latest(self, symbol: str, interval: str) -> IndicatorSnapshot:
        key = (symbol, interval)
        cached = self._cache.get(key, {})
        snapshot = IndicatorSnapshot()
        for name, series in cached.items():
            if len(series) > 0:
                last_val = series.iloc[-1]
                # 处理可能是 Series 的情况
                if isinstance(last_val, pd.Series):
                    last_val = last_val.iloc[0] if len(last_val) > 0 else None
                if pd.notna(last_val):
                    snapshot.values[name] = float(last_val)
        return snapshot

    def get_series(
        self, symbol: str, interval: str, indicator_name: str
    ) -> pd.Series | None:
        key = (symbol, interval)
        cached = self._cache.get(key, {})
        return cached.get(indicator_name)

    def get_previous(
        self, symbol: str, interval: str, indicator_name: str, n: int = 1
    ) -> float | None:
        series = self.get_series(symbol, interval, indicator_name)
        if series is not None and len(series) > n:
            val = series.iloc[-(n + 1)]
            return float(val) if pd.notna(val) else None
        return None
