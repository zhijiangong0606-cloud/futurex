from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
import pandas_ta  # noqa: F401 — registers .ta accessor on DataFrame


@dataclass
class IndicatorDef:
    name: str
    compute: Callable[[pd.DataFrame], pd.Series]
    params: dict[str, int | float] = field(default_factory=dict)


class IndicatorRegistry:
    def __init__(self) -> None:
        self._indicators: list[IndicatorDef] = []

    def register(self, indicator: IndicatorDef) -> None:
        self._indicators.append(indicator)

    @property
    def indicators(self) -> list[IndicatorDef]:
        return self._indicators


def build_default_registry(
    ema_fast: int = 20,
    ema_medium: int = 50,
    ema_slow: int = 200,
    rsi_period: int = 14,
    bb_period: int = 20,
    bb_std: float = 2.0,
    atr_period: int = 14,
    vol_period: int = 20,
    kc_period: int = 20,
    kc_atr_mult: float = 2.0,
    adx_period: int = 14,
) -> IndicatorRegistry:
    registry = IndicatorRegistry()

    registry.register(
        IndicatorDef(
            name=f"ema_{ema_fast}",
            compute=lambda df, p=ema_fast: df.ta.ema(length=p),
        )
    )
    registry.register(
        IndicatorDef(
            name=f"ema_{ema_medium}",
            compute=lambda df, p=ema_medium: df.ta.ema(length=p),
        )
    )
    registry.register(
        IndicatorDef(
            name=f"ema_{ema_slow}",
            compute=lambda df, p=ema_slow: df.ta.ema(length=p),
        )
    )
    registry.register(
        IndicatorDef(
            name="rsi",
            compute=lambda df, p=rsi_period: df.ta.rsi(length=p),
        )
    )
    registry.register(
        IndicatorDef(
            name="atr",
            compute=lambda df, p=atr_period: df.ta.atr(length=p),
        )
    )
    registry.register(
        IndicatorDef(
            name="volume_sma",
            compute=lambda df, p=vol_period: df["volume"].rolling(p).mean(),
        )
    )
    registry.register(
        IndicatorDef(
            name="volume",
            compute=lambda df: df["volume"],
        )
    )

    # Keltner Channel indicators
    def compute_kc_upper(df: pd.DataFrame) -> pd.Series:
        kc = df.ta.kc(length=kc_period, scalar=kc_atr_mult)
        if kc is not None and not kc.empty:
            return kc.iloc[:, 0]  # Upper band
        return pd.Series(dtype=float)

    def compute_kc_basis(df: pd.DataFrame) -> pd.Series:
        kc = df.ta.kc(length=kc_period, scalar=kc_atr_mult)
        if kc is not None and not kc.empty:
            return kc.iloc[:, 1]  # Basis (EMA)
        return pd.Series(dtype=float)

    def compute_kc_lower(df: pd.DataFrame) -> pd.Series:
        kc = df.ta.kc(length=kc_period, scalar=kc_atr_mult)
        if kc is not None and not kc.empty:
            return kc.iloc[:, 2]  # Lower band
        return pd.Series(dtype=float)

    registry.register(IndicatorDef(name="kc_upper", compute=compute_kc_upper))
    registry.register(IndicatorDef(name="kc_basis", compute=compute_kc_basis))
    registry.register(IndicatorDef(name="kc_lower", compute=compute_kc_lower))

    # ADX indicator
    def compute_adx(df: pd.DataFrame) -> pd.Series:
        adx_df = df.ta.adx(length=adx_period)
        if adx_df is not None and not adx_df.empty:
            return adx_df.iloc[:, 0]  # ADX column
        return pd.Series(dtype=float)

    registry.register(IndicatorDef(name="adx", compute=compute_adx))

    def compute_macd(df: pd.DataFrame) -> pd.Series:
        macd_df = df.ta.macd(fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            return macd_df.iloc[:, 0]
        return pd.Series(dtype=float)

    def compute_macd_signal(df: pd.DataFrame) -> pd.Series:
        macd_df = df.ta.macd(fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            return macd_df.iloc[:, 1]
        return pd.Series(dtype=float)

    def compute_macd_hist(df: pd.DataFrame) -> pd.Series:
        macd_df = df.ta.macd(fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            return macd_df.iloc[:, 2]
        return pd.Series(dtype=float)

    registry.register(IndicatorDef(name="macd", compute=compute_macd))
    registry.register(IndicatorDef(name="macd_signal", compute=compute_macd_signal))
    registry.register(IndicatorDef(name="macd_hist", compute=compute_macd_hist))

    def compute_bb_lower(df: pd.DataFrame) -> pd.Series:
        bb = df.ta.bbands(length=bb_period, std=bb_std)
        if bb is not None and not bb.empty:
            return bb.iloc[:, 0]
        return pd.Series(dtype=float)

    def compute_bb_mid(df: pd.DataFrame) -> pd.Series:
        bb = df.ta.bbands(length=bb_period, std=bb_std)
        if bb is not None and not bb.empty:
            return bb.iloc[:, 1]
        return pd.Series(dtype=float)

    def compute_bb_upper(df: pd.DataFrame) -> pd.Series:
        bb = df.ta.bbands(length=bb_period, std=bb_std)
        if bb is not None and not bb.empty:
            return bb.iloc[:, 2]
        return pd.Series(dtype=float)

    def compute_bb_width(df: pd.DataFrame) -> pd.Series:
        bb = df.ta.bbands(length=bb_period, std=bb_std)
        if bb is not None and not bb.empty and bb.shape[1] >= 5:
            return bb.iloc[:, 4]
        upper = compute_bb_upper(df)
        lower = compute_bb_lower(df)
        mid = compute_bb_mid(df)
        return (upper - lower) / mid

    registry.register(IndicatorDef(name="bb_lower", compute=compute_bb_lower))
    registry.register(IndicatorDef(name="bb_mid", compute=compute_bb_mid))
    registry.register(IndicatorDef(name="bb_upper", compute=compute_bb_upper))
    registry.register(IndicatorDef(name="bb_width", compute=compute_bb_width))

    return registry
