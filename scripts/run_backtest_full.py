"""
Full Backtest with In-Sample / Out-of-Sample Validation
"""
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from futurex.backtest.engine import BacktestEngine
from futurex.core.config import load_config
from futurex.core.logging import get_logger

log = get_logger("futurex.backtest.full")

IS_START = "2020-01-01"
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = None

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INITIAL_CAPITAL = 10000
MATCH_MODE = "pessimistic"


class BacktestRunner:
    def __init__(self):
        self.config = load_config()
        self.results: List[Dict] = []
    
    def run_all(self):
        print("=" * 80)
        print("FULL BACKTEST WITH IN-SAMPLE / OUT-OF-SAMPLE VALIDATION")
        print("=" * 80)
        print(f"Initial Capital: ${INITIAL_CAPITAL:,}")
        print(f"In-Sample:       {IS_START} to {IS_END}")
        print(f"Out-of-Sample:   {OOS_START} to {OOS_END or 'Now'}")
        print(f"Symbols:         {', '.join(SYMBOLS)}")
        print("=" * 80)
        print()
        
        for symbol in SYMBOLS:
            self._run_single(symbol, "IS", IS_START, IS_END)
            self._run_single(symbol, "OOS", OOS_START, OOS_END)
        
        self._print_comparison_matrix()
    
    def _run_single(self, symbol: str, dataset: str, start_date: str, end_date: str):
        data_path = f"data/historical/{symbol}_4h.parquet"
        
        if not Path(data_path).exists():
            print(f"[{symbol}] [{dataset}] SKIPPED - Data file not found")
            self.results.append({"symbol": symbol, "dataset": dataset, "status": "SKIPPED"})
            return
        
        print(f"[{symbol}] [{dataset}] Running backtest...")
        
        try:
            engine = BacktestEngine(
                strategy_config=self.config.strategy,
                initial_capital=INITIAL_CAPITAL,
                match_mode=MATCH_MODE
            )
            
            result = engine.run(symbol=symbol, data_path=data_path, 
                              start_date=start_date, end_date=end_date)
            
            self.results.append({
                "symbol": symbol, "dataset": dataset, "status": "SUCCESS",
                "total_trades": result.total_trades, "win_rate": result.win_rate,
                "total_return": result.total_return, "total_pnl": result.total_pnl,
                "net_ev": result.net_ev, "max_drawdown": result.max_drawdown,
                "sharpe_ratio": result.sharpe_ratio,
            })
            
            print(f"[{symbol}] [{dataset}] Completed - {result.total_trades} trades, "
                  f"{result.win_rate:.1%} win rate, {result.total_return:+.2%} return")
        
        except Exception as e:
            print(f"[{symbol}] [{dataset}] FAILED - {str(e)}")
            self.results.append({"symbol": symbol, "dataset": dataset, "status": "FAILED"})
    
    def _print_comparison_matrix(self):
        print()
        print("=" * 80)
        print("PERFORMANCE COMPARISON MATRIX")
        print("=" * 80)
        
        header = f"{'Symbol':<10} {'Dataset':<8} {'Trades':<8} {'Win Rate':<10} {'Return':<10} {'Net EV':<10} {'Max DD':<10} {'Sharpe':<8}"
        print(header)
        print("-" * 80)
        
        for r in self.results:
            if r["status"] == "SUCCESS":
                row = (f"{r['symbol']:<10} {r['dataset']:<8} {r['total_trades']:<8} "
                       f"{r['win_rate']:<10.2%} {r['total_return']:>+9.2%} "
                       f"${r['net_ev']:>+8.2f} {r['max_drawdown']:<10.2%} {r['sharpe_ratio']:<8.2f}")
                print(row)
            else:
                print(f"{r['symbol']:<10} {r['dataset']:<8} {r['status']}")
        
        print("=" * 80)
        self._print_summary()
    
    def _print_summary(self):
        print()
        print("SUMMARY STATISTICS")
        print("-" * 80)
        
        is_r = [r for r in self.results if r["dataset"] == "IS" and r["status"] == "SUCCESS"]
        oos_r = [r for r in self.results if r["dataset"] == "OOS" and r["status"] == "SUCCESS"]
        
        if is_r:
            print(f"In-Sample Average:")
            print(f"  Return:    {sum(r['total_return'] for r in is_r)/len(is_r):+.2%}")
            print(f"  Win Rate:  {sum(r['win_rate'] for r in is_r)/len(is_r):.2%}")
            print(f"  Sharpe:    {sum(r['sharpe_ratio'] for r in is_r)/len(is_r):.2f}")
        
        if oos_r:
            print(f"Out-of-Sample Average:")
            print(f"  Return:    {sum(r['total_return'] for r in oos_r)/len(oos_r):+.2%}")
            print(f"  Win Rate:  {sum(r['win_rate'] for r in oos_r)/len(oos_r):.2%}")
            print(f"  Sharpe:    {sum(r['sharpe_ratio'] for r in oos_r)/len(oos_r):.2f}")
        
        print("=" * 80)


def main():
    runner = BacktestRunner()
    runner.run_all()


if __name__ == "__main__":
    main()
