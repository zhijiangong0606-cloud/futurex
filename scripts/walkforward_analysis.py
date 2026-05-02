"""Walk-Forward Parameter Sensitivity Analysis"""
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from itertools import product

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from futurex.backtest.engine import BacktestEngine
from futurex.core.config import load_config

# Parameter grid
SL_MULTIPLIERS = [1.0, 1.25, 1.5, 1.75, 2.0]
TP_MULTIPLIERS = [2.0, 2.5, 3.0, 3.5, 4.0]

# Walk-forward settings
TRAIN_MONTHS = 12
TEST_MONTHS = 3
STEP_MONTHS = 3

SYMBOLS = ["BTCUSDT", "ETHUSDT"]


class WalkForwardAnalyzer:
    def __init__(self):
        self.config = load_config()
        self.results = []

    def run_analysis(self):
        print("=" * 80)
        print("WALK-FORWARD PARAMETER SENSITIVITY ANALYSIS")
        print("=" * 80)
        print(f"Parameter Grid:")
        print(f"  Stop-Loss:   {SL_MULTIPLIERS}")
        print(f"  Take-Profit: {TP_MULTIPLIERS}")
        print(f"  Total Combinations: {len(SL_MULTIPLIERS) * len(TP_MULTIPLIERS)}")
        print(f"\nWalk-Forward Settings:")
        print(f"  Train Window: {TRAIN_MONTHS} months")
        print(f"  Test Window:  {TEST_MONTHS} months")
        print(f"  Step Size:    {STEP_MONTHS} months")
        print("=" * 80)

        for symbol in SYMBOLS:
            print(f"\n{'='*80}")
            print(f"Analyzing {symbol}")
            print(f"{'='*80}")

            self._analyze_symbol(symbol)

        self._generate_report()

    def _analyze_symbol(self, symbol: str):
        # Load data
        df = pd.read_parquet(f"data/historical/{symbol}_4h.parquet")

        # Generate walk-forward windows
        windows = self._generate_windows(df)
        print(f"\nGenerated {len(windows)} walk-forward windows")

        # Test each parameter combination
        param_results = {}

        for sl_mult, tp_mult in product(SL_MULTIPLIERS, TP_MULTIPLIERS):
            print(f"\nTesting SL={sl_mult:.2f}x, TP={tp_mult:.2f}x")

            window_results = []

            for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
                # Run backtest on test window
                result = self._run_backtest(
                    symbol, sl_mult, tp_mult,
                    test_start, test_end
                )

                if result:
                    window_results.append(result)
                    print(f"  Window {i+1}: Sharpe={result['sharpe']:.2f}, "
                          f"Return={result['return']:.2%}, Trades={result['trades']}")

            # Aggregate results
            if window_results:
                param_results[(sl_mult, tp_mult)] = self._aggregate_results(window_results)

        # Save results
        self.results.append({
            'symbol': symbol,
            'param_results': param_results
        })

    def _generate_windows(self, df: pd.DataFrame) -> List[Tuple]:
        windows = []
        start_date = df['timestamp'].min()
        end_date = df['timestamp'].max()

        current_date = start_date

        while True:
            train_start = current_date
            train_end = train_start + pd.DateOffset(months=TRAIN_MONTHS)
            test_start = train_end
            test_end = test_start + pd.DateOffset(months=TEST_MONTHS)

            if test_end > end_date:
                break

            windows.append((
                train_start.strftime("%Y-%m-%d"),
                train_end.strftime("%Y-%m-%d"),
                test_start.strftime("%Y-%m-%d"),
                test_end.strftime("%Y-%m-%d")
            ))

            current_date += pd.DateOffset(months=STEP_MONTHS)

        return windows

    def _run_backtest(self, symbol: str, sl_mult: float, tp_mult: float,
                     start_date: str, end_date: str) -> Dict:
        try:
            # Create modified config
            config = self.config

            # Create engine with custom parameters
            engine = BacktestEngine(
                strategy_config=config.strategy,
                initial_capital=10000,
                match_mode="pessimistic"
            )

            # Monkey patch the multipliers
            import futurex.backtest.engine as engine_module
            original_sl = engine_module.SL_MULTIPLIER
            original_tp = engine_module.TP_MULTIPLIER

            engine_module.SL_MULTIPLIER = sl_mult
            engine_module.TP_MULTIPLIER = tp_mult

            # Run backtest
            result = engine.run(
                symbol=symbol,
                data_path=f"data/historical/{symbol}_4h.parquet",
                start_date=start_date,
                end_date=end_date
            )

            # Restore original values
            engine_module.SL_MULTIPLIER = original_sl
            engine_module.TP_MULTIPLIER = original_tp

            return {
                'sharpe': result.sharpe_ratio,
                'return': result.total_return,
                'trades': result.total_trades,
                'win_rate': result.win_rate,
                'max_dd': result.max_drawdown
            }

        except Exception as e:
            print(f"    Error: {e}")
            return None

    def _aggregate_results(self, window_results: List[Dict]) -> Dict:
        sharpes = [r['sharpe'] for r in window_results]
        returns = [r['return'] for r in window_results]

        return {
            'avg_sharpe': np.mean(sharpes),
            'std_sharpe': np.std(sharpes),
            'avg_return': np.mean(returns),
            'std_return': np.std(returns),
            'num_windows': len(window_results),
            'stability': np.mean(sharpes) / (np.std(sharpes) + 0.01)  # Stability score
        }

    def _generate_report(self):
        print(f"\n\n{'='*80}")
        print("WALK-FORWARD ANALYSIS RESULTS")
        print(f"{'='*80}")

        for result in self.results:
            symbol = result['symbol']
            param_results = result['param_results']

            print(f"\n{symbol} - Parameter Performance Matrix")
            print("-" * 80)

            # Find best parameters by different metrics
            best_sharpe = max(param_results.items(), key=lambda x: x[1]['avg_sharpe'])
            best_return = max(param_results.items(), key=lambda x: x[1]['avg_return'])
            best_stability = max(param_results.items(), key=lambda x: x[1]['stability'])

            print(f"\nBest by Sharpe Ratio:")
            print(f"  SL={best_sharpe[0][0]:.2f}x, TP={best_sharpe[0][1]:.2f}x")
            print(f"  Avg Sharpe: {best_sharpe[1]['avg_sharpe']:.2f}")
            print(f"  Avg Return: {best_sharpe[1]['avg_return']:.2%}")
            print(f"  Stability:  {best_sharpe[1]['stability']:.2f}")

            print(f"\nBest by Return:")
            print(f"  SL={best_return[0][0]:.2f}x, TP={best_return[0][1]:.2f}x")
            print(f"  Avg Sharpe: {best_return[1]['avg_sharpe']:.2f}")
            print(f"  Avg Return: {best_return[1]['avg_return']:.2%}")
            print(f"  Stability:  {best_return[1]['stability']:.2f}")

            print(f"\nBest by Stability:")
            print(f"  SL={best_stability[0][0]:.2f}x, TP={best_stability[0][1]:.2f}x")
            print(f"  Avg Sharpe: {best_stability[1]['avg_sharpe']:.2f}")
            print(f"  Avg Return: {best_stability[1]['avg_return']:.2%}")
            print(f"  Stability:  {best_stability[1]['stability']:.2f}")

            # Identify robust parameter cluster
            print(f"\nRobust Parameter Cluster (Sharpe > 0.3, Stability > 1.0):")
            robust_params = [
                (params, metrics) for params, metrics in param_results.items()
                if metrics['avg_sharpe'] > 0.3 and metrics['stability'] > 1.0
            ]

            if robust_params:
                for params, metrics in sorted(robust_params, key=lambda x: x[1]['avg_sharpe'], reverse=True):
                    print(f"  SL={params[0]:.2f}x, TP={params[1]:.2f}x: "
                          f"Sharpe={metrics['avg_sharpe']:.2f}, "
                          f"Return={metrics['avg_return']:.2%}, "
                          f"Stability={metrics['stability']:.2f}")
            else:
                print("  No parameters meet robust criteria")

        print(f"\n{'='*80}")
        print("RECOMMENDATION")
        print(f"{'='*80}")
        self._generate_recommendation()

    def _generate_recommendation(self):
        print("\nBased on Walk-Forward analysis:")
        print("\n1. Parameter Clusters:")
        print("   - Identify parameters that perform well across multiple windows")
        print("   - Avoid single 'optimal' parameters that may be overfit")

        print("\n2. Volatility-Adaptive Strategy:")
        print("   - High Volatility (ATR% > 2.0%): Use larger multipliers")
        print("   - Low Volatility (ATR% < 1.8%): Use smaller multipliers")

        print("\n3. Next Steps:")
        print("   - Implement DynamicRiskManager with regime detection")
        print("   - Use parameter cluster ranges, not fixed values")
        print("   - Monitor real-time ATR% for regime switching")


def main():
    analyzer = WalkForwardAnalyzer()
    analyzer.run_analysis()


if __name__ == "__main__":
    main()
