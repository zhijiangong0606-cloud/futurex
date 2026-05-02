# Futurex - Xiaomi MiMo Token Grant Application Notes

This document is written as a reviewer-facing summary for the Xiaomi MiMo token grant application. It explains what the project does, how AI was used, why the work required substantial model assistance, and where the proof can be found in the repository.

## Recommended Form Answers

### Agent Used

Claude Code

### Model Used

Claude Opus 4.6 for architecture, research, diagnosis, code generation, and iterative debugging.

The runtime project also includes a configurable Claude API sentiment filter for trade review:

- `src/futurex/strategy/ai_filter.py`
- `src/futurex/strategy/signal_scorer.py`
- `src/futurex/core/config.py`
- `config/default.toml`

### API Type

Direct API integration.

### GitHub Repository

https://github.com/zhijiangong0606-cloud/futurex

Repository status: Public.

Security status: no API keys, bot tokens, chat IDs, live databases, or log files are committed. Secrets are represented only by placeholders in `.env.example`.

## Project Description

Futurex is an adaptive quantitative trading system for cryptocurrency futures markets, focused on Binance USDT-M perpetual contracts. It combines a deterministic trading pipeline with an optional Claude-powered sentiment and context filter, then places every candidate trade behind a multi-layer risk gate.

The core innovation is a Market Regime State Machine. Instead of trading every technical breakout, the system classifies the market using 252-day volatility percentiles, ADX trend strength, and EMA trend alignment. It allows new entries only in trend-friendly regimes and blocks entries during dead-chop, range-bound, or volatile-chop conditions. Existing positions continue to be managed through server-side stop-loss and take-profit orders.

The project was built through AI-assisted quantitative research rather than simple code generation. Claude Code was used across strategy design, event-driven backtesting, walk-forward validation, forensic failure analysis, regime detection, risk architecture, and production monitoring. The result is a research-backed trading framework with testnet execution, Telegram alerting, Streamlit monitoring, DuckDB/SQLite persistence, and reproducible validation scripts.

## Why This Should Qualify For A High Token Allocation

Futurex is not a demo wrapper around an API call. It is a full trading research and execution system with multiple interacting subsystems:

- Market data ingestion through Binance REST and WebSocket clients.
- Technical indicator calculation across multiple timeframes.
- Keltner Channel breakout signal scoring with ADX, volume, and EMA filters.
- Claude API sentiment adjustment for moderate-confidence signals.
- Market regime kill switch using volatility percentiles, trend strength, and trend direction.
- Event-driven backtesting with pessimistic intra-bar matching.
- Walk-forward parameter sensitivity analysis across symbols and rolling windows.
- Forensic diagnostics that isolate execution-model, EMA-filter, and stop-loss-lifespan failure modes.
- Six-layer risk gate covering drawdown, daily loss, max positions, correlation exposure, position sizing, and stop management.
- Testnet-ready live trader, Telegram alerts, Streamlit dashboard, structured logging, and state recovery.

The project required long-context reasoning because the useful work was not only producing files, but repeatedly testing assumptions. The research process found that an apparently profitable in-sample strategy was overfit, identified the likely cause, and redesigned the system around defensive regime filtering instead of parameter curve fitting.

## Evidence Map For Reviewers

| Claim | Evidence in Repository |
|---|---|
| Market regime state machine | `src/futurex/regime/detector.py`, `src/futurex/regime/kill_switch.py`, `src/futurex/regime/states.py` |
| AI-assisted sentiment filter | `src/futurex/strategy/ai_filter.py`, `src/futurex/strategy/signal_scorer.py`, `config/default.toml` |
| Event-driven backtesting | `src/futurex/backtest/engine.py`, `src/futurex/backtest/matcher.py`, `src/futurex/backtest/performance.py` |
| Walk-forward validation | `scripts/walkforward_analysis.py` |
| Forensic diagnostics | `scripts/forensic_final_v2.py` |
| Six-layer risk management | `src/futurex/risk/gate.py`, `src/futurex/risk/drawdown.py`, `src/futurex/risk/daily_limits.py`, `src/futurex/risk/position_sizer.py` |
| Live testnet execution | `scripts/live_trader.py`, `src/futurex/execution/order_manager.py` |
| Monitoring and alerts | `scripts/dashboard.py`, `scripts/monitor.py`, `src/futurex/notify/telegram.py` |
| Safety hygiene | `.gitignore`, `.env.example`, `config/testnet.toml` |

## Strong Short Description For The Form

An AI-assisted adaptive quantitative trading system for Binance USDT-M futures. Futurex uses Claude Code for research, architecture, forensic strategy diagnosis, and implementation, and includes a direct Claude API sentiment filter inside the trading pipeline. Its main innovation is a Market Regime State Machine that uses 252-day volatility percentiles, ADX trend strength, and EMA alignment to classify market conditions and block new trades in hostile regimes. The system includes 850+ walk-forward backtests, pessimistic execution modeling, forensic failure attribution, six-layer risk control, Binance testnet execution, Telegram alerts, Streamlit monitoring, and secure configuration hygiene.

## Longer Application Description

Futurex is a production-oriented research and execution framework for cryptocurrency futures trading. It was developed through extensive Claude Code sessions covering system architecture, quantitative strategy research, code generation, testing, and failure diagnosis. The project began with a Keltner Channel breakout strategy that looked profitable in-sample, then used Claude-assisted walk-forward validation and forensic diagnostics to prove that the original edge was unstable out-of-sample.

Instead of hiding the failure through parameter tuning, the project evolved into a defensive adaptive system. A Market Regime State Machine classifies daily market conditions with volatility percentile rank, ADX trend strength, and EMA alignment. It enables new entries only during strong trend regimes and blocks dead-chop, range-bound, and volatile-chop environments. Moderate-confidence signals can be reviewed by a Claude API sentiment filter, while all approved candidates must pass a six-layer risk gate before execution.

The repository contains the complete implementation: data ingestion, indicators, strategy scoring, Claude API filtering, regime detection, risk checks, order management, state persistence, backtesting, walk-forward analysis, forensic diagnostics, Telegram notifications, and a Streamlit dashboard. Sensitive credentials are excluded and represented only by placeholders.

## Suggested Proof Screenshot Checklist

When submitting the form, include screenshots that show:

- The public GitHub repository page.
- The repository file tree with `src/futurex`, `scripts`, `tests`, and `docs`.
- `src/futurex/strategy/ai_filter.py` showing the direct Claude API integration.
- `scripts/walkforward_analysis.py` showing the walk-forward validation grid.
- `src/futurex/regime/detector.py` showing the market regime detector.
- Any Claude Code conversation/session evidence available to you.

## One-Sentence Value Proposition

Futurex shows high-value AI-assisted engineering because Claude was used not just to write code, but to conduct a full research loop: generate a strategy, invalidate it with rigorous testing, diagnose the failure, and rebuild the system around adaptive market-regime risk control.
