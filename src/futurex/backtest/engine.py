"""Backtest Engine - 回测引擎核心"""
from typing import List, Optional
from pathlib import Path
import pandas as pd
from collections import deque

from .matcher import OrderMatcher, Position
from .performance import PerformanceAnalyzer, Trade, BacktestResult
from ..indicators.engine import IndicatorEngine
from ..indicators.registry import build_default_registry
from ..strategy.signal_scorer import SignalScorer
from ..core.constants import Side
from ..core.logging import get_logger

log = get_logger("futurex.backtest.engine")

# 策略参数（与 live_trader.py 对齐）
SL_MULTIPLIER = 1.5
TP_MULTIPLIER = 3.0


class BacktestEngine:
    """回测引擎 - 事件驱动回放"""
    
    def __init__(
        self,
        strategy_config,
        initial_capital: float = 10000,
        match_mode: str = "pessimistic"
    ):
        self.initial_capital = initial_capital
        self.strategy_config = strategy_config
        
        # 初始化组件
        registry = build_default_registry(
            ema_fast=strategy_config.ema_fast,
            ema_medium=strategy_config.ema_medium,
            ema_slow=strategy_config.ema_slow,
            rsi_period=strategy_config.rsi_period,
            bb_period=strategy_config.bb_period,
            bb_std=strategy_config.bb_std,
            atr_period=14,
        )
        self.indicator_engine = IndicatorEngine(registry)
        self.scorer = SignalScorer(strategy_config)
        self.matcher = OrderMatcher(match_mode)
        self.performance = PerformanceAnalyzer(initial_capital)
        
        # 状态
        self.equity = initial_capital
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.kline_buffer = deque(maxlen=500)
    
    def run(
        self,
        symbol: str,
        data_path: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> BacktestResult:
        """
        运行回测
        
        Args:
            symbol: 交易对
            data_path: 数据文件路径 (Parquet)
            start_date: 开始日期 (可选)
            end_date: 结束日期 (可选)
        """
        log.info("backtest_start", symbol=symbol, initial_capital=self.initial_capital)
        
        # 1. 加载数据
        df = self._load_data(data_path, start_date, end_date)
        log.info("data_loaded", rows=len(df))
        
        # 2. 预热指标（前 300 根）
        warmup_size = min(300, len(df) // 2)
        for i in range(warmup_size):
            kline = self._df_row_to_kline(df.iloc[i])
            self.kline_buffer.append(kline)
        
        log.info("warmup_complete", candles=warmup_size)
        
        # 3. 逐根 K 线回放
        for i in range(warmup_size, len(df)):
            kline = self._df_row_to_kline(df.iloc[i])
            self._process_kline(kline, symbol)
        
        # 4. 计算性能指标
        result = self.performance.analyze(self.trades)
        log.info("backtest_complete", trades=result.total_trades, win_rate=f"{result.win_rate:.2%}")
        
        return result
    
    def _process_kline(self, kline: dict, symbol: str):
        """处理单根 K 线"""
        
        # 1. 检查是否触发止损/止盈
        if self.position:
            exit_type, exit_price = self.matcher.check_exit(kline, self.position)
            
            if exit_type:
                self._close_position(kline, exit_type, exit_price)
        
        # 2. 添加到缓冲区
        self.kline_buffer.append(kline)
        
        # 3. 计算指标
        df = pd.DataFrame(self.kline_buffer)
        self.indicator_engine.compute(symbol, "4h", df)
        snap = self.indicator_engine.get_latest(symbol, "4h")
        
        if not snap or not snap.values:
            return
        
        # 4. 生成信号（仅在无持仓时）
        if not self.position:
            price = kline["close"]
            indicators = {"1h": snap, "4h": snap}
            signal = self.scorer.score(symbol, indicators, price)
            
            if signal:
                atr = snap.get("atr")
                if atr and atr > 0:
                    self._open_position(kline, signal, atr)
    
    def _open_position(self, kline: dict, signal, atr: float):
        """开仓"""
        price = kline["close"]
        
        # 计算仓位（与 live_trader.py 对齐）
        abs_score = abs(signal.score)
        risk_pct = 0.02 if abs_score >= 60 else 0.01
        risk_amount = self.equity * risk_pct
        stop_distance = atr * SL_MULTIPLIER
        quantity = risk_amount / stop_distance
        
        # 计算止损/止盈
        if signal.direction == Side.LONG:
            sl_price = price - stop_distance
            tp_price = price + (atr * TP_MULTIPLIER)
            side = "LONG"
        else:
            sl_price = price + stop_distance
            tp_price = price - (atr * TP_MULTIPLIER)
            side = "SHORT"
        
        # 记录持仓
        self.position = Position(
            side=side,
            entry_price=price,
            quantity=quantity,
            stop_loss=sl_price,
            take_profit=tp_price,
            entry_time=kline["timestamp"]  # 添加开仓时间戳
        )
        
        log.debug("position_opened", 
                 side=side, 
                 price=price, 
                 sl=sl_price, 
                 tp=tp_price,
                 qty=quantity)
    
    def _close_position(self, kline: dict, exit_type: str, exit_price: float):
        """平仓"""
        if not self.position:
            return
        
        # 计算盈亏
        if self.position.side == "LONG":
            pnl = (exit_price - self.position.entry_price) * self.position.quantity
        else:  # SHORT
            pnl = (self.position.entry_price - exit_price) * self.position.quantity
        
        # 扣除手续费（0.15% * 2）
        fee = (self.position.entry_price + exit_price) * self.position.quantity * 0.0015
        pnl -= fee
        
        # 更新权益
        self.equity += pnl
        
        # 计算收益率
        return_pct = pnl / (self.position.entry_price * self.position.quantity)
        
        # 记录交易
        trade = Trade(
            entry_time=self.position.entry_time,  # 使用持仓的开仓时间
            exit_time=kline["timestamp"],
            side=self.position.side,
            entry_price=self.position.entry_price,
            exit_price=exit_price,
            quantity=self.position.quantity,
            pnl=pnl,
            exit_type=exit_type,
            return_pct=return_pct
        )
        self.trades.append(trade)
        
        log.debug("position_closed",
                 exit_type=exit_type,
                 exit_price=exit_price,
                 pnl=f"{pnl:+.2f}",
                 equity=f"{self.equity:.2f}")
        
        # 清空持仓
        self.position = None
    
    def _load_data(
        self,
        data_path: str,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> pd.DataFrame:
        """加载数据"""
        df = pd.read_parquet(data_path)
        
        # 过滤日期
        if start_date:
            df = df[df['timestamp'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['timestamp'] <= pd.to_datetime(end_date)]
        
        return df.reset_index(drop=True)
    
    def _df_row_to_kline(self, row) -> dict:
        """DataFrame 行转 K 线字典"""
        return {
            "timestamp": int(row['timestamp'].timestamp() * 1000),
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close']),
            "volume": float(row['volume']),
        }
