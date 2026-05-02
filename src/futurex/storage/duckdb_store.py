from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from ..core.logging import get_logger

log = get_logger("futurex.storage.duckdb_store")


class DuckDBStore:
    def __init__(self, db_path: str = "data/trading.duckdb", read_only: bool = False) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(db_path, read_only=read_only)
        if not read_only:
            self._init_tables()

    def _init_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS klines (
                symbol VARCHAR,
                interval VARCHAR,
                timestamp BIGINT,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                PRIMARY KEY (symbol, interval, timestamp)
            )
        """)

        self._conn.execute("CREATE SEQUENCE IF NOT EXISTS trade_seq START 1")

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY DEFAULT (nextval('trade_seq')),
                symbol VARCHAR,
                side VARCHAR,
                entry_price DOUBLE,
                exit_price DOUBLE,
                quantity DOUBLE,
                pnl DOUBLE,
                duration_seconds DOUBLE,
                entry_time DOUBLE,
                exit_time DOUBLE,
                created_at TIMESTAMP DEFAULT current_timestamp
            )
        """)

    def insert_klines(
        self,
        symbol: str,
        interval: str,
        candles: list[dict[str, Any]],
    ) -> int:
        if not candles:
            return 0

        values = []
        for c in candles:
            values.append(
                (
                    symbol,
                    interval,
                    int(c.get("timestamp", c.get("open_time", 0))),
                    float(c.get("open", 0)),
                    float(c.get("high", 0)),
                    float(c.get("low", 0)),
                    float(c.get("close", 0)),
                    float(c.get("volume", 0)),
                )
            )

        self._conn.executemany(
            """
            INSERT OR REPLACE INTO klines
            (symbol, interval, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        return len(values)

    def insert_trade(self, trade: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO trades
            (symbol, side, entry_price, exit_price, quantity, pnl,
             duration_seconds, entry_time, exit_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade["symbol"],
                trade["side"],
                trade["entry_price"],
                trade["exit_price"],
                trade["quantity"],
                trade["pnl"],
                trade.get("duration_seconds", 0),
                trade.get("entry_time", 0),
                trade.get("exit_time", 0),
            ),
        )

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        result = self._conn.execute(
            """
            SELECT timestamp, open, high, low, close, volume
            FROM klines
            WHERE symbol = ? AND interval = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (symbol, interval, limit),
        ).fetchall()

        candles = []
        for row in reversed(result):
            candles.append(
                {
                    "timestamp": row[0],
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": row[4],
                    "volume": row[5],
                }
            )
        return candles

    def get_trade_stats(self, last_n: int = 100) -> dict[str, Any]:
        result = self._conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                AVG(CASE WHEN pnl <= 0 THEN ABS(pnl) END) as avg_loss,
                SUM(pnl) as total_pnl
            FROM (
                SELECT pnl FROM trades ORDER BY exit_time DESC LIMIT ?
            )
            """,
            (last_n,),
        ).fetchone()

        if not result or result[0] == 0:
            return {"total": 0}

        return {
            "total": result[0],
            "wins": result[1] or 0,
            "losses": result[2] or 0,
            "win_rate": (result[1] or 0) / result[0],
            "avg_win": result[3] or 0,
            "avg_loss": result[4] or 0,
            "total_pnl": result[5] or 0,
        }

    def close(self) -> None:
        self._conn.close()
