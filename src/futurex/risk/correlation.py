from __future__ import annotations

import numpy as np

from ..core.logging import get_logger
from . import AccountState, Position, RiskCheckResult

log = get_logger("futurex.risk.correlation")


class CorrelationExposure:
    def __init__(self, max_correlated_exposure_pct: float = 0.08) -> None:
        self._max_pct = max_correlated_exposure_pct
        self._correlations: dict[tuple[str, str], float] = {}

    def update_correlations(self, returns: dict[str, list[float]]) -> None:
        symbols = list(returns.keys())
        if len(symbols) < 2:
            return

        for i, s1 in enumerate(symbols):
            for s2 in symbols[i + 1 :]:
                r1 = np.array(returns[s1])
                r2 = np.array(returns[s2])
                min_len = min(len(r1), len(r2))
                if min_len < 20:
                    continue
                r1 = r1[-min_len:]
                r2 = r2[-min_len:]
                corr = float(np.corrcoef(r1, r2)[0, 1])
                self._correlations[(s1, s2)] = corr
                self._correlations[(s2, s1)] = corr

    def check(
        self, new_symbol: str, account: AccountState
    ) -> RiskCheckResult:
        if not account.open_positions:
            return RiskCheckResult(passed=True)

        if account.equity <= 0:
            return RiskCheckResult(passed=True)

        correlated_exposure = 0.0
        for pos in account.open_positions:
            corr = self._get_correlation(new_symbol, pos.symbol)
            if corr > 0.7:
                correlated_exposure += pos.notional

        exposure_pct = correlated_exposure / account.equity

        if exposure_pct >= self._max_pct:
            return RiskCheckResult(
                passed=False,
                reason=f"Correlated exposure too high: {exposure_pct:.2%} >= {self._max_pct:.2%}",
            )

        return RiskCheckResult(passed=True)

    def _get_correlation(self, s1: str, s2: str) -> float:
        if s1 == s2:
            return 1.0
        return self._correlations.get((s1, s2), 0.0)
