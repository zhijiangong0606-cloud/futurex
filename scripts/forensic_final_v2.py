"""Forensic Diagnostic - Final Fixed Version"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from futurex.backtest.engine import BacktestEngine
from futurex.core.config import load_config

def forensic_analysis(symbol, start, end):
    print(f"\n{'='*80}")
    print(f"FORENSIC DIAGNOSTIC: {symbol}")
    print(f"{'='*80}\n")

    # Run backtest
    config = load_config()
    engine = BacktestEngine(
        strategy_config=config.strategy,
        initial_capital=10000,
        match_mode="pessimistic"
    )

    result = engine.run(
        symbol=symbol,
        data_path=f"data/historical/{symbol}_4h.parquet",
        start_date=start,
        end_date=end
    )

    trades = result.trades
    losing_trades = [t for t in trades if t.pnl < 0 and t.exit_type == 'STOP_LOSS']

    print(f"Performance: Trades={len(trades)}, WinRate={result.win_rate:.2%}, "
          f"Return={result.total_return:+.2%}, Sharpe={result.sharpe_ratio:.2f}\n")

    # Load data
    df = pd.read_parquet(f"data/historical/{symbol}_4h.parquet")
    df = df[(df['timestamp'] >= start) & (df['timestamp'] <= end)].copy()
    df['ema200'] = df['close'].ewm(span=200).mean()

    # DIMENSION 1
    print("DIMENSION 1: Pessimistic Execution Audit")
    print("-" * 80)

    single_bar_count = 0
    dual_penetration_count = 0
    total_analyzed = 0

    for trade in losing_trades:
        try:
            # Convert int timestamp to pandas Timestamp
            entry_time = pd.to_datetime(trade.entry_time, unit='ms')
            exit_time = pd.to_datetime(trade.exit_time, unit='ms')

            entry_bar = df[df['timestamp'] == entry_time]
            exit_bar = df[df['timestamp'] == exit_time]

            if len(entry_bar) > 0 and len(exit_bar) > 0:
                entry_idx = entry_bar.index[0]
                exit_idx = exit_bar.index[0]
                bars_held = exit_idx - entry_idx

                if bars_held <= 1:
                    single_bar_count += 1

                    if bars_held == 0:
                        bar = entry_bar.iloc[0]
                        if trade.side == 'LONG':
                            hit_sl = bar['low'] <= trade.entry_price * 0.98
                            hit_tp = bar['high'] >= trade.entry_price * 1.04
                        else:
                            hit_sl = bar['high'] >= trade.entry_price * 1.02
                            hit_tp = bar['low'] <= trade.entry_price * 0.96

                        if hit_sl and hit_tp:
                            dual_penetration_count += 1

                total_analyzed += 1
        except Exception as e:
            continue

    if total_analyzed > 0:
        single_bar_rate = (single_bar_count / total_analyzed) * 100.0
        dual_pen_rate = (dual_penetration_count / total_analyzed) * 100.0

        print(f"Single-Bar SL: {single_bar_count}/{total_analyzed} ({single_bar_rate:.2f}%)")
        print(f"Dual Penetration: {dual_penetration_count}/{total_analyzed} ({dual_pen_rate:.2f}%)")

        if dual_pen_rate > 30:
            print(f"[CRITICAL] High dual penetration")
        elif dual_pen_rate > 15:
            print(f"[WARNING] Moderate dual penetration")
        else:
            print(f"[OK] Low dual penetration")

    # DIMENSION 2
    print(f"\nDIMENSION 2: EMA200 Whipsaw Audit")
    print("-" * 80)

    df_2024 = df[df['timestamp'] >= '2024-01-01'].copy()

    if len(df_2024) > 0:
        df_2024['above_ema'] = df_2024['close'] > df_2024['ema200']
        df_2024['ema_cross'] = df_2024['above_ema'] != df_2024['above_ema'].shift(1)
        cross_count = int(df_2024['ema_cross'].sum())
        cross_freq = (cross_count / len(df_2024)) * 100.0

        entry_deviations = []
        matched_count = 0

        for trade in trades:
            try:
                entry_time = pd.to_datetime(trade.entry_time, unit='ms')
                entry_bar = df[df['timestamp'] == entry_time]

                if len(entry_bar) > 0:
                    entry_bar = entry_bar.iloc[0]

                    if not pd.isna(entry_bar['ema200']) and entry_bar['ema200'] > 0:
                        deviation = float(abs(entry_bar['close'] - entry_bar['ema200']) / entry_bar['ema200'] * 100.0)
                        entry_deviations.append(deviation)
                        matched_count += 1
            except Exception as e:
                continue

        avg_deviation = float(np.mean(entry_deviations)) if entry_deviations else 0.0
        median_deviation = float(np.median(entry_deviations)) if entry_deviations else 0.0

        print(f"EMA200 Crosses: {cross_count} ({cross_freq:.2f}% of bars)")
        print(f"Matched Trades: {matched_count}/{len(trades)}")
        print(f"Avg Entry Deviation: {avg_deviation:.4f}%")
        print(f"Median Entry Deviation: {median_deviation:.4f}%")

        if cross_freq > 10:
            print(f"[CRITICAL] High whipsaw")
        elif cross_freq > 5:
            print(f"[WARNING] Moderate whipsaw")
        else:
            print(f"[OK] Low whipsaw")

        if avg_deviation < 2.0:
            print(f"[CRITICAL] Entries too close to EMA200")
        elif avg_deviation < 5.0:
            print(f"[WARNING] Moderately close to EMA200")
        else:
            print(f"[OK] Good separation from EMA200")

    # DIMENSION 3
    print(f"\nDIMENSION 3: Stop-Loss Lifespan")
    print("-" * 80)

    bars_held_list = []
    for trade in losing_trades:
        try:
            entry_time = pd.to_datetime(trade.entry_time, unit='ms')
            exit_time = pd.to_datetime(trade.exit_time, unit='ms')

            entry_bar = df[df['timestamp'] == entry_time]
            exit_bar = df[df['timestamp'] == exit_time]

            if len(entry_bar) > 0 and len(exit_bar) > 0:
                entry_idx = entry_bar.index[0]
                exit_idx = exit_bar.index[0]
                bars_held = exit_idx - entry_idx

                if bars_held > 0:
                    bars_held_list.append(bars_held)
        except:
            continue

    if bars_held_list:
        avg_bars = float(np.mean(bars_held_list))
        median_bars = float(np.median(bars_held_list))

        quick_sl = sum(1 for b in bars_held_list if b <= 2)
        medium_sl = sum(1 for b in bars_held_list if 3 <= b <= 10)
        slow_sl = sum(1 for b in bars_held_list if b > 10)

        quick_pct = (quick_sl / len(bars_held_list)) * 100.0
        medium_pct = (medium_sl / len(bars_held_list)) * 100.0
        slow_pct = (slow_sl / len(bars_held_list)) * 100.0

        print(f"Avg Bars Held: {avg_bars:.2f}")
        print(f"Median Bars Held: {median_bars:.1f}")
        print(f"Quick (1-2 bars): {quick_sl}/{len(bars_held_list)} ({quick_pct:.2f}%)")
        print(f"Medium (3-10 bars): {medium_sl}/{len(bars_held_list)} ({medium_pct:.2f}%)")
        print(f"Slow (10+ bars): {slow_sl}/{len(bars_held_list)} ({slow_pct:.2f}%)")

        if quick_pct > 50:
            print(f"[CRITICAL] Liquidity hunting")
        elif quick_pct > 30:
            print(f"[WARNING] High quick SL rate")
        else:
            print(f"[OK] Reasonable lifespan")

    print(f"\n{'='*80}\n")

forensic_analysis('BTCUSDT', '2024-01-01', '2025-05-01')
forensic_analysis('ETHUSDT', '2024-01-01', '2025-05-01')
