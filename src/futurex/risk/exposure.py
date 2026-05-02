from __future__ import annotations

from ..core.logging import get_logger
from . import AccountState, RiskCheckResult

log = get_logger("futurex.risk.exposure")


class MaxPositionCheck:
    def __init__(self, max_positions: int = 3) -> None:
        self._max = max_positions

    def check(self, account: AccountState) -> RiskCheckResult:
        open_count = len(account.open_positions)
        if open_count >= self._max:
            return RiskCheckResult(
                passed=False,
                reason=f"Max concurrent positions reached: {open_count}/{self._max}",
            )
        return RiskCheckResult(passed=True)
