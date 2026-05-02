"""State Persistence Module"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from ..core.logging import get_logger

log = get_logger("futurex.state.persistence")

@dataclass
class Position:
    id: Optional[int]
    symbol: str
    side: str
    entry_price: float
    quantity: float
    entry_time: int
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    status: str = "OPEN"

@dataclass
class Order:
    id: Optional[int]
    position_id: int
    order_id: str
    symbol: str
    order_type: str
    side: str
    price: Optional[float]
    quantity: float
    status: str = "NEW"

@dataclass
class RecoveryResult:
    success: bool
    position: Optional[Position] = None
    orders: List[Order] = None
    message: str = ""
    def __post_init__(self):
        if self.orders is None:
            self.orders = []

class StateManager:
    def __init__(self, db_path: str = "data/state.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_database()
    
    def _init_database(self):
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        self._conn.commit()
        log.info("state_db_initialized", path=str(self._db_path))
    
    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL, side TEXT NOT NULL,
                entry_price REAL NOT NULL, quantity REAL NOT NULL,
                entry_time INTEGER NOT NULL, stop_loss_price REAL,
                take_profit_price REAL, status TEXT DEFAULT 'OPEN',
                created_at INTEGER DEFAULT (strftime('%s','now')*1000),
                updated_at INTEGER DEFAULT (strftime('%s','now')*1000));
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER NOT NULL, order_id TEXT UNIQUE NOT NULL,
                symbol TEXT NOT NULL, order_type TEXT NOT NULL,
                side TEXT NOT NULL, price REAL, quantity REAL,
                status TEXT DEFAULT 'NEW',
                created_at INTEGER DEFAULT (strftime('%s','now')*1000),
                updated_at INTEGER DEFAULT (strftime('%s','now')*1000),
                FOREIGN KEY (position_id) REFERENCES positions(id));
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY, value TEXT,
                updated_at INTEGER DEFAULT (strftime('%s','now')*1000));
            CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
            CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
            CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
            INSERT OR IGNORE INTO system_state VALUES ('is_trading','false',0);
            INSERT OR IGNORE INTO system_state VALUES ('last_kline_timestamp','0',0);
        """)
    
    def save_position(self, position: Position) -> int:
        cursor = self._conn.execute(
            "INSERT INTO positions (symbol,side,entry_price,quantity,entry_time,stop_loss_price,take_profit_price,status) VALUES (?,?,?,?,?,?,?,?)",
            (position.symbol, position.side, position.entry_price, position.quantity,
             position.entry_time, position.stop_loss_price, position.take_profit_price, position.status))
        self._conn.commit()
        log.info("position_saved", position_id=cursor.lastrowid, symbol=position.symbol)
        return cursor.lastrowid
    
    def save_order(self, order: Order) -> int:
        cursor = self._conn.execute(
            "INSERT INTO orders (position_id,order_id,symbol,order_type,side,price,quantity,status) VALUES (?,?,?,?,?,?,?,?)",
            (order.position_id, order.order_id, order.symbol, order.order_type,
             order.side, order.price, order.quantity, order.status))
        self._conn.commit()
        log.info("order_saved", order_id=order.order_id)
        return cursor.lastrowid
    
    def update_position_status(self, position_id: int, status: str):
        self._conn.execute("UPDATE positions SET status=?, updated_at=strftime('%s','now')*1000 WHERE id=?", (status, position_id))
        self._conn.commit()
        log.info("position_status_updated", position_id=position_id, status=status)
    
    def get_open_position(self) -> Optional[Position]:
        row = self._conn.execute("SELECT * FROM positions WHERE status='OPEN' ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:
            return None
        return Position(id=row["id"], symbol=row["symbol"], side=row["side"],
                       entry_price=row["entry_price"], quantity=row["quantity"],
                       entry_time=row["entry_time"], stop_loss_price=row["stop_loss_price"],
                       take_profit_price=row["take_profit_price"], status=row["status"])
    
    def get_orders_by_position(self, position_id: int) -> List[Order]:
        rows = self._conn.execute("SELECT * FROM orders WHERE position_id=? AND status='NEW' ORDER BY created_at", (position_id,)).fetchall()
        return [Order(id=r["id"], position_id=r["position_id"], order_id=r["order_id"],
                     symbol=r["symbol"], order_type=r["order_type"], side=r["side"],
                     price=r["price"], quantity=r["quantity"], status=r["status"]) for r in rows]
    
    def set_system_state(self, key: str, value: str):
        self._conn.execute("INSERT OR REPLACE INTO system_state (key,value,updated_at) VALUES (?,?,strftime('%s','now')*1000)", (key, value))
        self._conn.commit()
    
    def get_system_state(self, key: str) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM system_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None
    
    def recover(self) -> RecoveryResult:
        log.info("recovering_state")
        position = self.get_open_position()
        if not position:
            log.info("no_open_position_found")
            return RecoveryResult(success=True, message="No open position to recover")
        orders = self.get_orders_by_position(position.id)
        log.info("state_recovered", position_id=position.id, symbol=position.symbol, orders_count=len(orders))
        return RecoveryResult(success=True, position=position, orders=orders,
                            message=f"Recovered position {position.symbol} {position.side} with {len(orders)} orders")
    
    def clear_position(self, position_id: int):
        self.update_position_status(position_id, "CLOSED")
        self._conn.execute("UPDATE orders SET status='CANCELED', updated_at=strftime('%s','now')*1000 WHERE position_id=? AND status='NEW'", (position_id,))
        self._conn.commit()
        log.info("position_cleared", position_id=position_id)
    
    def close(self):
        if self._conn:
            self._conn.close()
            log.info("state_db_closed")
