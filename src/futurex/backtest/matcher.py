"""Order Matcher - 订单撮合引擎"""
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class Position:
    """持仓信息"""
    side: str  # LONG / SHORT
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    entry_time: any = None  # 开仓时间戳


class OrderMatcher:
    """订单撮合引擎 - 处理 Intra-bar 止损/止盈"""
    
    def __init__(self, mode: str = "pessimistic"):
        """
        Args:
            mode: 撮合模式
                - pessimistic: 最悲观原则（默认）
                - precise: 次级别数据精确撮合（需要 1m 数据）
        """
        self.mode = mode
        self._1m_data_cache = {}
    
    def check_exit(
        self,
        kline: dict,
        position: Position
    ) -> Tuple[Optional[str], Optional[float]]:
        """
        检查是否触发止损/止盈
        
        Args:
            kline: 当前 K 线 {timestamp, open, high, low, close, volume}
            position: 当前持仓
        
        Returns:
            (exit_type, exit_price) 或 (None, None)
            exit_type: "STOP_LOSS" | "TAKE_PROFIT"
        """
        if self.mode == "pessimistic":
            return self._match_pessimistic(kline, position)
        elif self.mode == "precise":
            return self._match_precise(kline, position)
        else:
            raise ValueError(f"Unknown match mode: {self.mode}")
    
    def _match_pessimistic(
        self,
        kline: dict,
        position: Position
    ) -> Tuple[Optional[str], Optional[float]]:
        """
        最悲观原则：假设止损先触发
        
        逻辑：
        - 做多：先检查 Low（止损方向），再检查 High（止盈方向）
        - 做空：先检查 High（止损方向），再检查 Low（止盈方向）
        """
        if position.side == "LONG":
            # 做多：先检查止损
            if kline["low"] <= position.stop_loss:
                return "STOP_LOSS", position.stop_loss
            # 再检查止盈
            elif kline["high"] >= position.take_profit:
                return "TAKE_PROFIT", position.take_profit
        
        else:  # SHORT
            # 做空：先检查止损
            if kline["high"] >= position.stop_loss:
                return "STOP_LOSS", position.stop_loss
            # 再检查止盈
            elif kline["low"] <= position.take_profit:
                return "TAKE_PROFIT", position.take_profit
        
        return None, None
    
    def _match_precise(
        self,
        kline: dict,
        position: Position
    ) -> Tuple[Optional[str], Optional[float]]:
        """
        次级别数据精确撮合（需要 1m 数据）
        
        TODO: 实现次级别数据加载和逐根检查
        目前回退到最悲观原则
        """
        # 暂时回退到最悲观原则
        return self._match_pessimistic(kline, position)
