"""Market Regime Analysis - Simplified"""
import sys
from pathlib import Path
from typing import Dict
import pandas as pd
import numpy as np

IS_START = "2020-01-01"
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]


class RegimeAnalyzer:
    def __init__(self):
        self.results = {}

    def analyze_all(self):
        print("=" * 80)
        print("MARKET REGIME ANALYSIS & ATTRIBUTION")
        print("=" * 80)

        for symbol in SYMBOLS:
            print(f"\n{'='*80}")
            print(f"Analyzing {symbol}")
            print(f"{'='*80}")

            df = self._load_data(symbol)
            df_is = df[(df['timestamp'] >= IS_START) & (df['timestamp'] <= IS_END)].copy()
            df_oos = df[df['timestamp'] >= OOS_START].copy()

            print(f"\n[IN-SAMPLE: {IS_START} to {IS_END}]")
            is_m = self._analyze_regime(df_is)

            print(f"\n[OUT-OF-SAMPLE: {OOS_START} to Now]")
            oos_m = self._analyze_regime(df_oos)

            print(f"\n[REGIME SHIFT ANALYSIS]")
            self._compare(is_m, oos_m)

            self.results[symbol] = {"IS": is_m, "OOS": oos_m}

        print(f"\n\n{'='*80}")
        print("ATTRIBUTION ANALYSIS")
        print(f"{'='*80}")
        self._attribution()

    def _load_data(self, symbol: str) -> pd.DataFrame:
        return pd.read_parquet(f"data/historical/{symbol}_4h.parquet")

    def _analyze_regime(self, df: pd.DataFrame) -> Dict:
        # Calculate ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(14).mean()
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        avg_atr_pct = df['atr_pct'].mean()

        # Calculate ADX (simplified)
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift(1))
        df['low_close'] = abs(df['low'] - df['close'].shift(1))
        df['tr_adx'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)

        df['dm_plus'] = np.where((df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
                                 np.maximum(df['high'] - df['high'].shift(1), 0), 0)
        df['dm_minus'] = np.where((df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
                                  np.maximum(df['low'].shift(1) - df['low'], 0), 0)

        df['di_plus'] = 100 * (df['dm_plus'].rolling(14).mean() / df['tr_adx'].rolling(14).mean())
        df['di_minus'] = 100 * (df['dm_minus'].rolling(14).mean() / df['tr_adx'].rolling(14).mean())
        df['dx'] = 100 * abs(df['di_plus'] - df['di_minus']) / (df['di_plus'] + df['di_minus'])
        df['adx'] = df['dx'].rolling(14).mean()

        trend_pct = (df['adx'] > 25).sum() / len(df) * 100

        # Calculate KC (simplified)
        df['ema20'] = df['close'].ewm(span=20).mean()
        df['kc_upper'] = df['ema20'] + (df['atr'] * 2.0)
        df['kc_middle'] = df['ema20']
        df['kc_lower'] = df['ema20'] - (df['atr'] * 2.0)

        fb_rate = self._calc_fb_rate(df)

        df['return'] = df['close'].pct_change()
        avg_return = df['return'].mean() * 100
        volatility = df['return'].std() * 100

        print(f"  Candles:              {len(df)}")
        print(f"  Avg ATR %:            {avg_atr_pct:.2f}%")
        print(f"  Trend Coherence:      {trend_pct:.2f}% (ADX > 25)")
        print(f"  False Breakout Rate:  {fb_rate:.2f}%")
        print(f"  Avg Return:           {avg_return:.4f}%")
        print(f"  Volatility:           {volatility:.2f}%")

        return {
            "candles": len(df),
            "avg_atr_pct": avg_atr_pct,
            "trend_coherence": trend_pct,
            "false_breakout_rate": fb_rate,
            "avg_return": avg_return,
            "volatility": volatility
        }

    def _calc_fb_rate(self, df: pd.DataFrame) -> float:
        false_breakouts = 0
        total_breakouts = 0

        for i in range(len(df) - 3):
            if pd.isna(df.iloc[i]['kc_upper']):
                continue

            close = df.iloc[i]['close']
            kc_upper = df.iloc[i]['kc_upper']
            kc_lower = df.iloc[i]['kc_lower']
            kc_middle = df.iloc[i]['kc_middle']

            # Check upper breakout
            if close > kc_upper:
                total_breakouts += 1
                for j in range(1, 4):
                    if i + j < len(df):
                        future_close = df.iloc[i + j]['close']
                        if future_close < kc_middle:
                            false_breakouts += 1
                            break

            # Check lower breakout
            elif close < kc_lower:
                total_breakouts += 1
                for j in range(1, 4):
                    if i + j < len(df):
                        future_close = df.iloc[i + j]['close']
                        if future_close > kc_middle:
                            false_breakouts += 1
                            break

        return (false_breakouts / total_breakouts * 100) if total_breakouts > 0 else 0.0

    def _compare(self, is_m: Dict, oos_m: Dict):
        atr_chg = ((oos_m['avg_atr_pct'] - is_m['avg_atr_pct']) / is_m['avg_atr_pct'] * 100)
        trend_chg = oos_m['trend_coherence'] - is_m['trend_coherence']
        fb_chg = oos_m['false_breakout_rate'] - is_m['false_breakout_rate']

        print(f"  ATR % Change:         {atr_chg:+.2f}%")
        print(f"  Trend Coherence Δ:    {trend_chg:+.2f}pp")
        print(f"  False Breakout Δ:     {fb_chg:+.2f}pp")

        if abs(atr_chg) > 20:
            print(f"  [WARNING] Significant volatility change!")
        if abs(trend_chg) > 10:
            print(f"  [WARNING] Significant trend coherence change!")
        if abs(fb_chg) > 10:
            print(f"  [WARNING] Significant false breakout rate change!")

    def _attribution(self):
        print("\n1. ETHUSDT Survival Attribution")
        print("-" * 80)

        eth_is = self.results["ETHUSDT"]["IS"]
        eth_oos = self.results["ETHUSDT"]["OOS"]

        print(f"ETHUSDT maintained positive returns in OOS (+11.85%)\n")

        trend_stable = abs(eth_oos['trend_coherence'] - eth_is['trend_coherence']) < 5
        fb_improved = eth_oos['false_breakout_rate'] < eth_is['false_breakout_rate']

        if trend_stable:
            print(f"  [OK] Trend coherence remained stable")
            print(f"    IS:  {eth_is['trend_coherence']:.1f}%")
            print(f"    OOS: {eth_oos['trend_coherence']:.1f}%")

        if fb_improved:
            print(f"  [OK] False breakout rate improved")
            print(f"    IS:  {eth_is['false_breakout_rate']:.1f}%")
            print(f"    OOS: {eth_oos['false_breakout_rate']:.1f}%")

        vol_chg = ((eth_oos['avg_atr_pct'] - eth_is['avg_atr_pct']) / eth_is['avg_atr_pct'] * 100)
        print(f"  - Volatility change: {vol_chg:+.2f}%")

        print("\n2. BTCUSDT Failure Attribution")
        print("-" * 80)

        btc_is = self.results["BTCUSDT"]["IS"]
        btc_oos = self.results["BTCUSDT"]["OOS"]

        print(f"BTCUSDT suffered severe losses in OOS (-18.14%)\n")

        trend_deg = btc_oos['trend_coherence'] < btc_is['trend_coherence']
        fb_worse = btc_oos['false_breakout_rate'] > btc_is['false_breakout_rate']

        if trend_deg:
            delta = btc_oos['trend_coherence'] - btc_is['trend_coherence']
            print(f"  [FAIL] Trend coherence degraded")
            print(f"    IS:  {btc_is['trend_coherence']:.1f}%")
            print(f"    OOS: {btc_oos['trend_coherence']:.1f}%")
            print(f"    Delta:   {delta:.1f}pp")

        if fb_worse:
            delta = btc_oos['false_breakout_rate'] - btc_is['false_breakout_rate']
            print(f"  [FAIL] False breakout rate increased")
            print(f"    IS:  {btc_is['false_breakout_rate']:.1f}%")
            print(f"    OOS: {btc_oos['false_breakout_rate']:.1f}%")
            print(f"    Delta:   {delta:.1f}pp")

        vol_chg = ((btc_oos['avg_atr_pct'] - btc_is['avg_atr_pct']) / btc_is['avg_atr_pct'] * 100)
        print(f"  - Volatility change: {vol_chg:+.2f}%")

        print("\n3. Core Failure Indicator")
        print("-" * 80)

        trend_delta = abs(btc_oos['trend_coherence'] - btc_is['trend_coherence'])
        fb_delta = abs(btc_oos['false_breakout_rate'] - btc_is['false_breakout_rate'])
        vol_delta = abs(vol_chg)

        if fb_delta > trend_delta and fb_delta > vol_delta:
            print(f"[WARNING] PRIMARY FAILURE CAUSE: False Breakout Rate")
            print(f"    Increased by {fb_delta:.1f}pp in OOS")
            print(f"    KC breakout strategy fails in high false-breakout environments")
        elif trend_delta > fb_delta and trend_delta > vol_delta:
            print(f"[WARNING] PRIMARY FAILURE CAUSE: Trend Coherence Loss")
            print(f"    Decreased by {trend_delta:.1f}pp in OOS")
            print(f"    Strategy requires sustained trends to profit")
        else:
            print(f"[WARNING] PRIMARY FAILURE CAUSE: Volatility Regime Shift")
            print(f"    Changed by {vol_chg:+.1f}% in OOS")
            print(f"    Fixed SL/TP ratios misaligned with new volatility")


def main():
    analyzer = RegimeAnalyzer()
    analyzer.analyze_all()


if __name__ == "__main__":
    main()
