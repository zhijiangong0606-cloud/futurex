-- Futurex State Database Schema
-- 用于持久化交易状态，确保崩溃后可恢复

-- 持仓表
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,                    -- LONG / SHORT
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    entry_time INTEGER NOT NULL,           -- Unix timestamp (ms)
    stop_loss_price REAL,
    take_profit_price REAL,
    status TEXT DEFAULT 'OPEN',            -- OPEN / CLOSED
    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
);

-- 订单表（记录挂在币安的止损/止盈订单）
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL,
    order_id TEXT UNIQUE NOT NULL,         -- 币安订单 ID
    symbol TEXT NOT NULL,
    order_type TEXT NOT NULL,              -- STOP_MARKET / TAKE_PROFIT_MARKET
    side TEXT NOT NULL,                    -- BUY / SELL
    price REAL,
    quantity REAL,
    status TEXT DEFAULT 'NEW',             -- NEW / FILLED / CANCELED
    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    FOREIGN KEY (position_id) REFERENCES positions(id)
);

-- 系统状态表（key-value 存储）
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_position_id ON orders(position_id);

-- 初始化系统状态
INSERT OR IGNORE INTO system_state (key, value) VALUES ('is_trading', 'false');
INSERT OR IGNORE INTO system_state (key, value) VALUES ('last_kline_timestamp', '0');
INSERT OR IGNORE INTO system_state (key, value) VALUES ('reconnect_count', '0');
