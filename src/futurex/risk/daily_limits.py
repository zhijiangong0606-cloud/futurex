from __future__ import annotations

from datetime import date, datetime, timezone

from ..core.logging import get_logger
from . import AccountState, RiskCheckResult

log = get_logger("futurex.risk.daily_limits")


class DailyLossLimit:
    def __init__(self, max_daily_loss_pct: float = 0.03) -> None:
        self._max_pct = max_daily_loss_pct
        self._day_start_equity: float = 0.0
        self._realized_loss_today: float = 0.0
        self._current_day: date | None = None

    def on_trade_closed(self, pnl: float, as_of: datetime | None = None) -> None:
        self._ensure_day(as_of=as_of)
        if pnl < 0:
            self._realized_loss_today += abs(pnl)
            log.info(
                "daily_loss_accumulated",
                loss_this_trade=pnl,
                total_loss_today=self._realized_loss_today,
                limit=self._day_start_equity * self._max_pct,
            )

    def check(self, account: AccountState, as_of: datetime | None = None) -> RiskCheckResult:
        self._ensure_day(equity=account.equity, as_of=as_of)

        if self._day_start_equity <= 0:
            return RiskCheckResult(passed=True)

        limit = self._day_start_equity * self._max_pct

        if self._realized_loss_today >= limit:
            return RiskCheckResult(
                passed=False,
                reason=f"Daily loss limit reached: "
                f"${self._realized_loss_today:.2f} / ${limit:.2f} "
                f"({self._max_pct:.0%} of day-start equity)",
            )

        return RiskCheckResult(passed=True)

    def _ensure_day(self, equity: float | None = None, as_of: datetime | None = None) -> None:
        if as_of is not None:
            today = as_of.date() if isinstance(as_of, datetime) else as_of
        else:
            today = datetime.now(timezone.utc).date()
        if self._current_day != today:
            self._current_day = today
            self._realized_loss_today = 0.0
            if equity is not None:
                self._day_start_equity = equity
            log.info(
                "daily_loss_reset",
                date=str(today),
                day_start_equity=self._day_start_equity,
            )
