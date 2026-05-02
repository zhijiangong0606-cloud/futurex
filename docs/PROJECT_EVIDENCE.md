# Project Evidence

This file gives reviewers a compact map from project claims to concrete files.

## Implementation Scope

- 11 source modules under `src/futurex`: `core`, `data`, `indicators`, `strategy`, `regime`, `risk`, `execution`, `state`, `storage`, `notify`, and `backtest`.
- Research and operations scripts under `scripts`.
- Tests under `tests`, currently focused on risk-management behavior.
- Secure examples and default testnet configuration under `.env.example` and `config`.

## AI Integration

The trading system contains an optional direct Claude API sentiment filter. It is designed as an adjustment layer, not an uncontrolled trading agent.

- `src/futurex/strategy/ai_filter.py`: builds the Claude prompt, calls the API, parses JSON sentiment, caps the adjustment, and fails closed to neutral sentiment on errors.
- `src/futurex/strategy/signal_scorer.py`: marks moderate-confidence signals for AI review.
- `src/futurex/core/config.py`: defines AI configuration.
- `config/default.toml`: enables AI review with daily call limits and cooldown controls.

## Research And Validation

- `scripts/run_backtest_full.py`: in-sample and out-of-sample backtesting.
- `scripts/walkforward_analysis.py`: 25 stop/take-profit parameter combinations across rolling train/test windows and two symbols, producing 850+ validation runs.
- `scripts/forensic_final_v2.py`: failure attribution across execution matching, EMA200 whipsaw, and stop-loss lifespan.
- `scripts/regime_analysis.py`: market regime analysis.

## Defensive Trading Architecture

- `src/futurex/regime/detector.py`: classifies market state using ATR percentile rank, ADX strength, and EMA trend alignment.
- `src/futurex/regime/kill_switch.py`: blocks new entries in hostile regimes with debounce.
- `src/futurex/risk/gate.py`: master risk gate that requires all checks to pass before order construction.
- `src/futurex/risk/drawdown.py`: drawdown circuit breaker.
- `src/futurex/risk/daily_limits.py`: daily realized loss limit.
- `src/futurex/risk/position_sizer.py`: fixed-fractional sizing with signal-aware risk.

## Production Readiness

- `scripts/live_trader.py`: testnet live trader entry point.
- `src/futurex/data/ws_manager.py`: WebSocket lifecycle management.
- `src/futurex/data/rest_client.py`: Binance REST integration.
- `src/futurex/execution/order_manager.py`: order placement and execution flow.
- `src/futurex/state/persistence.py`: SQLite state recovery.
- `src/futurex/storage/duckdb_store.py`: historical kline storage.
- `src/futurex/notify/telegram.py`: Telegram notifications.
- `scripts/dashboard.py`: Streamlit dashboard.

## Security Hygiene

- `.env` is ignored.
- Mainnet credential config is ignored.
- Local databases, downloaded historical datasets, logs, caches, and virtual environments are ignored.
- `.env.example` contains placeholders only.
