"""
Telegram 告警通知模块
轻量级同步实现，不干扰异步事件循环
"""
from __future__ import annotations

import httpx
from typing import Optional

from ..core.logging import get_logger

log = get_logger("futurex.notify.telegram")


class TelegramNotifier:
    """Telegram Bot 通知器（同步实现）"""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._enabled = enabled and bot_token and chat_id
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

        if not self._enabled:
            log.warning("telegram_disabled", reason="missing_credentials")

    def send_message(
        self,
        text: str,
        parse_mode: str = "Markdown",
        disable_notification: bool = False,
    ) -> bool:
        """
        发送消息到 Telegram

        Args:
            text: 消息内容（支持 Markdown 格式）
            parse_mode: 解析模式（Markdown 或 HTML）
            disable_notification: 是否静默发送（不推送通知）

        Returns:
            是否发送成功
        """
        if not self._enabled:
            return False

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self._base_url}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "disable_notification": disable_notification,
                    },
                )
                response.raise_for_status()
                log.info("telegram_sent", length=len(text))
                return True

        except httpx.HTTPError as e:
            log.error("telegram_failed", error=str(e))
            return False
        except Exception as e:
            log.error("telegram_error", error=str(e))
            return False

    def send_startup(self, symbol: str, interval: str) -> None:
        """发送启动通知"""
        text = f"🚀 *交易机器人已启动*\n\n监听: `{symbol}` ({interval})"
        self.send_message(text)

    def send_order_opened(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
        risk_pct: float,
    ) -> None:
        """发送开仓通知"""
        direction = "做多 📈" if side == "LONG" else "做空 📉"
        text = f"""
🎯 *开仓执行成功*

交易对: `{symbol}`
方向: {direction}
开仓价: `${entry_price:,.2f}`
数量: `{quantity:.4f}`
止损价: `${stop_loss:,.2f}`
止盈价: `${take_profit:,.2f}`
风险敞口: `{risk_pct:.2f}%`
        """.strip()
        self.send_message(text)

    def send_order_closed(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        reason: str,
    ) -> None:
        """发送平仓通知"""
        direction = "做多" if side == "LONG" else "做空"
        emoji = "✅" if pnl > 0 else "❌"
        text = f"""
{emoji} *平仓执行*

交易对: `{symbol}`
方向: {direction}
开仓价: `${entry_price:,.2f}`
平仓价: `${exit_price:,.2f}`
盈亏: `${pnl:+,.2f}` ({pnl_pct:+.2f}%)
原因: {reason}
        """.strip()
        self.send_message(text)

    def send_error(self, error_type: str, details: str) -> None:
        """发送错误告警"""
        text = f"""
🚨 *系统异常告警*

类型: `{error_type}`
详情: {details}
        """.strip()
        self.send_message(text, disable_notification=False)

    def send_reconnect_warning(self, attempt: int, max_attempts: int = 3) -> None:
        """发送重连警告"""
        if attempt >= max_attempts:
            text = f"""
🚨 *WebSocket 重连异常*

已重连 `{attempt}` 次，连接不稳定
请检查网络状态
            """.strip()
            self.send_message(text)
