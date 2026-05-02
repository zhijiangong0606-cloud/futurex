"""Performance Analyzer - 性能分析器"""
from dataclasses import dataclass
from typing import List
import numpy as np


@dataclass
class Trade:
    """单笔交易记录"""
    entry_time: int
    exit_time: int
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    exit_type: str  # STOP_LOSS / TAKE_PROFIT
    return_pct: float


@dataclass
class BacktestResult:
    """回测结果"""
    total_trades: int
    win_rate: float
    total_return: float
    total_pnl: float
    net_ev: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    sharpe_ratio: float
    equity_curve: List[float]
    trades: List[Trade]
    
    def print_summary(self):
        """打印回测摘要"""
        print("=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print(f"Total Trades:    {self.total_trades}")
        print(f"Win Rate:        {self.win_rate:.2%}")
        print(f"Total Return:    {self.total_return:+.2%}")
        print(f"Total PnL:       ${self.total_pnl:+,.2f}")
        print(f"Net EV/Trade:    ${self.net_ev:+,.2f}")
        print(f"Avg Win:         ${self.avg_win:,.2f}")
        print(f"Avg Loss:        ${self.avg_loss:,.2f}")
        print(f"Max Drawdown:    {self.max_drawdown:.2%}")
        print(f"Sharpe Ratio:    {self.sharpe_ratio:.2f}")
        print("=" * 60)


class PerformanceAnalyzer:
    """性能分析器"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
    
    def analyze(self, trades: List[Trade]) -> BacktestResult:
        """计算标准化性能指标"""
        
        if not trades:
            return self._empty_result()
        
        # 1. 基础统计
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        
        # 2. 盈亏统计
        total_pnl = sum(t.pnl for t in trades)
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0
        
        # 3. 净期望值
        net_ev = total_pnl / total_trades if total_trades > 0 else 0
        
        # 4. 权益曲线
        equity_curve = self._build_equity_curve(trades)
        
        # 5. 最大回撤
        max_drawdown = self._calculate_max_drawdown(equity_curve)
        
        # 6. 夏普比率
        returns = self._calculate_returns(equity_curve)
        sharpe_ratio = self._calculate_sharpe(returns)
        
        # 7. 总收益率
        final_capital = self.initial_capital + total_pnl
        total_return = (final_capital - self.initial_capital) / self.initial_capital
        
        return BacktestResult(
            total_trades=total_trades,
            win_rate=win_rate,
            total_return=total_return,
            total_pnl=total_pnl,
            net_ev=net_ev,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            equity_curve=equity_curve,
            trades=trades
        )
    
    def _build_equity_curve(self, trades: List[Trade]) -> List[float]:
        """构建权益曲线"""
        equity = self.initial_capital
        curve = [equity]
        
        for trade in trades:
            equity += trade.pnl
            curve.append(equity)
        
        return curve
    
    def _calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        """计算最大回撤"""
        if len(equity_curve) < 2:
            return 0.0
        
        peak = equity_curve[0]
        max_dd = 0.0
        
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            
            dd = (peak - equity) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        
        return max_dd
    
    def _calculate_returns(self, equity_curve: List[float]) -> np.ndarray:
        """计算收益率序列"""
        if len(equity_curve) < 2:
            return np.array([])
        
        returns = []
        for i in range(1, len(equity_curve)):
            ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            returns.append(ret)
        
        return np.array(returns)
    
    def _calculate_sharpe(self, returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
        """计算夏普比率（年化）"""
        if len(returns) < 2:
            return 0.0
        
        excess_returns = returns - risk_free_rate
        if np.std(excess_returns) == 0:
            return 0.0
        
        # 假设每笔交易间隔约 4 天（4h 策略）
        # 年化因子 = sqrt(365 / 4) ≈ sqrt(91) ≈ 9.5
        annualization_factor = np.sqrt(91)
        
        return np.mean(excess_returns) / np.std(excess_returns) * annualization_factor
    
    def _empty_result(self) -> BacktestResult:
        """空结果"""
        return BacktestResult(
            total_trades=0,
            win_rate=0.0,
            total_return=0.0,
            total_pnl=0.0,
            net_ev=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            equity_curve=[self.initial_capital],
            trades=[]
        )
