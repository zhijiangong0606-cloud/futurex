"""Live trader for Binance Futures Testnet.

Connects via WebSocket for 4h kline data, computes KC/ADX/Volume signals,
and places SL/TP orders via REST API.

Usage:
    python scripts/live_trader.py [BTCUSDT|ETHUSDT|SOLUSDT]
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

import httpx
import pandas as pd
import websockets

from futurex.core.config import load_config, Secrets
from futurex.core.constants import Side
from futurex.core.logging import get_logger
from futurex.indicators.engine import IndicatorEngine
from futurex.indicators.registry import build_default_registry
from futurex.strategy.signal_scorer import SignalScorer
from futurex.notify.telegram import TelegramNotifier
from futurex.state.persistence import StateManager, Position, Order
from futurex.regime import RegimeDetector, RegimeKillSwitch

log = get_logger("futurex.live_trader")

# Binance Futures Testnet endpoints
TESTNET_REST = "https://testnet.binancefuture.com"
TESTNET_WS = "wss://stream.binancefuture.com/ws"

# ATR multipliers (locked from backtest)
SL_MULTIPLIER = 1.5
TP_MULTIPLIER = 3.0
FRICTION_PCT = 0.0015


class BinanceTestnetClient:
    """Thin REST client for Binance Futures Testnet."""

    def __init__(self, api_key: str, api_secret: str, proxy: str = "") -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._proxy = proxy

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self._api_key}

    def _sign(self, params: dict) -> dict:
        import hashlib
        import hmac
        import urllib.parse

        params["timestamp"] = int(time.time() * 1000)
        query = urllib.parse.urlencode(params)
        signature = hmac.new(
            self._api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    async def _request(self, method: str, path: str, params: dict | None = None, signed: bool = False) -> dict:
        url = f"{TESTNET_REST}{path}"
        if params is None:
            params = {}
        if signed:
            params = self._sign(params)

        client_kwargs: dict = {"timeout": 30.0}
        if self._proxy:
            client_kwargs["proxy"] = self._proxy

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    if method == "GET":
                        resp = await client.get(url, params=params, headers=self._headers())
                    else:
                        resp = await client.post(url, params=params, headers=self._headers())
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.HTTPError, httpx.ConnectError) as e:
                log.warning("api_error", attempt=attempt + 1, error=str(e))
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise

    async def get_account(self) -> dict:
        return await self._request("GET", "/fapi/v2/account", signed=True)

    async def get_klines(self, symbol: str, interval: str = "4h", limit: int = 300) -> list:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        return await self._request("GET", "/fapi/v1/klines", params=params)

    async def place_order(
        self, symbol: str, side: str, quantity: float,
        order_type: str = "MARKET", **kwargs
    ) -> dict:
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": f"{quantity:.3f}",
            **kwargs,
        }
        log.info("placing_order", **params)
        return await self._request("POST", "/fapi/v1/order", params=params, signed=True)

    async def place_stop_market(self, symbol: str, side: str, stop_price: float, quantity: float) -> dict:
        return await self.place_order(
            symbol, side, quantity,
            order_type="STOP_MARKET",
            stopPrice=f"{stop_price:.2f}",
            closePosition="true",
        )

    async def place_take_profit_market(self, symbol: str, side: str, stop_price: float, quantity: float) -> dict:
        return await self.place_order(
            symbol, side, quantity,
            order_type="TAKE_PROFIT_MARKET",
            stopPrice=f"{stop_price:.2f}",
            closePosition="true",
        )

    async def cancel_all_orders(self, symbol: str) -> dict:
        return await self._request("DELETE", "/fapi/v1/allOpenOrders",
                                    params={"symbol": symbol}, signed=True)


class LiveTrader:
    """Main trading loop: WS kline stream -> signal -> order execution."""

    def __init__(self, symbol: str, config, secrets: Secrets) -> None:
        self._symbol = symbol
        self._config = config
        self._client = BinanceTestnetClient(
            secrets.binance_api_key,
            secrets.binance_api_secret,
            secrets.proxy_url,
        )

        registry = build_default_registry(
            ema_fast=config.strategy.ema_fast,
            ema_medium=config.strategy.ema_medium,
            ema_slow=config.strategy.ema_slow,
            rsi_period=config.strategy.rsi_period,
            bb_period=config.strategy.bb_period,
            bb_std=config.strategy.bb_std,
            atr_period=config.risk.atr_period,
        )
        self._indicator_engine = IndicatorEngine(registry)
        self._scorer = SignalScorer(config.strategy)
        self._kline_buffer: list[dict] = []
        self._in_position = False
        self._position_side: str | None = None
        self._position_id: int | None = None  # 数据库中的持仓 ID

        # 状态管理器
        self._state_manager = StateManager()

        # Telegram 通知器
        self._notifier = TelegramNotifier(
            bot_token=secrets.telegram_bot_token,
            chat_id=secrets.telegram_chat_id,
        )
        self._ws_reconnect_count = 0

        # 市场状态机（初始化为 None，在 initialize 中加载）
        self._regime_detector: RegimeDetector | None = None
        self._regime_kill_switch: RegimeKillSwitch | None = None
        self._df_1d: pd.DataFrame | None = None  # 1D K 线数据

    async def initialize(self) -> None:
        """Load historical klines to warm up indicators."""
        log.info("initializing", symbol=self._symbol)

        # 1. 首先尝试恢复状态
        recovery_result = self._state_manager.recover()
        if recovery_result.success and recovery_result.position:
            # 发现未平仓的持仓，恢复到内存
            pos = recovery_result.position
            self._in_position = True
            self._position_side = pos.side
            self._position_id = pos.id

            log.warning(
                "state_recovered",
                symbol=pos.symbol,
                side=pos.side,
                entry_price=pos.entry_price,
                quantity=pos.quantity,
                orders_count=len(recovery_result.orders)
            )

            # 发送 Telegram 通知
            self._notifier.send_message(
                f"⚠️ *状态恢复*\n\n"
                f"发现未平仓持仓:\n"
                f"交易对: `{pos.symbol}`\n"
                f"方向: {pos.side}\n"
                f"开仓价: `${pos.entry_price:,.2f}`\n"
                f"数量: `{pos.quantity:.4f}`\n"
                f"止损: `${pos.stop_loss_price:,.2f}`\n"
                f"止盈: `${pos.take_profit_price:,.2f}`\n"
                f"订单数: {len(recovery_result.orders)}"
            )
        else:
            log.info("no_position_to_recover")

        # 2. 加载历史 4h K 线预热指标
        raw_klines_4h = await self._client.get_klines(self._symbol, "4h", 300)

        for k in raw_klines_4h:
            self._kline_buffer.append({
                "timestamp": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })

        log.info("warmup_4h_complete", candles=len(self._kline_buffer))

        # 3. 加载历史 1D K 线用于市场状态机（至少 300 天）
        log.info("loading_1d_klines", symbol=self._symbol, days=300)
        raw_klines_1d = await self._client.get_klines(self._symbol, "1d", 300)

        klines_1d = []
        for k in raw_klines_1d:
            klines_1d.append({
                "timestamp": pd.to_datetime(k[0], unit='ms'),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })

        self._df_1d = pd.DataFrame(klines_1d)
        log.info("warmup_1d_complete", candles=len(self._df_1d))

        # 4. 初始化市场状态机
        self._regime_detector = RegimeDetector(
            lookback_period=252,
            vol_thresholds=(30, 70),
            adx_thresholds=(20, 30)
        )
        self._regime_kill_switch = RegimeKillSwitch(
            self._regime_detector,
            min_duration=3
        )

        # 5. 检测当前市场状态
        current_regime = self._regime_detector.detect(self._df_1d)
        log.info(
            "regime_initialized",
            regime=current_regime.value,
            lookback=252,
            vol_thresholds="(30%, 70%)",
            adx_thresholds="(20, 30)"
        )

        # 发送启动通知（包含市场状态）
        self._notifier.send_message(
            f"🚀 *交易机器人启动*\n\n"
            f"交易对: `{self._symbol}`\n"
            f"时间框架: `4h`\n"
            f"市场状态: `{current_regime.value}`\n"
            f"状态机: ✅ 已激活\n"
            f"防抖周期: 3 个 1D K 线"
        )

    async def _on_kline_close(self, kline: dict) -> None:
        """Process a closed 4h kline: compute indicators, generate signal, execute."""
        self._kline_buffer.append(kline)
        if len(self._kline_buffer) > 500:
            self._kline_buffer = self._kline_buffer[-500:]

        # 更新 1D 数据（每 6 个 4h K 线 = 1 天）
        await self._update_1d_data(kline)

        df = pd.DataFrame(self._kline_buffer)
        self._indicator_engine.compute(self._symbol, "4h", df)
        snap = self._indicator_engine.get_latest(self._symbol, "4h")

        if not snap or not snap.values:
            return

        price = kline["close"]
        indicators = {"1h": snap, "4h": snap}
        signal = self._scorer.score(self._symbol, indicators, price)

        if signal is None:
            log.info("no_signal", symbol=self._symbol, price=price)
            return

        if self._in_position:
            log.info("already_in_position", symbol=self._symbol)
            return

        # 市场状态机过滤
        if self._regime_kill_switch and self._df_1d is not None:
            allowed, reason, regime = self._regime_kill_switch.should_allow_entry(self._df_1d)

            if not allowed:
                # 计算当前指标用于日志
                vol_state = self._regime_detector._classify_volatility(self._df_1d)
                trend_strength = self._regime_detector._classify_trend_strength(self._df_1d)

                # 计算 ADX 和波动率分位数
                adx = self._regime_detector._calculate_adx(self._df_1d, period=14).iloc[-1]
                atr = self._regime_detector._calculate_atr(self._df_1d, period=14)
                atr_pct = (atr / self._df_1d['close']) * 100
                vol_percentile = self._regime_detector._percentile_rank(
                    atr_pct.iloc[-1],
                    atr_pct.iloc[-252:]
                )

                log.warning(
                    "signal_blocked_by_regime",
                    symbol=self._symbol,
                    signal_direction=signal.direction.value,
                    signal_score=f"{signal.score:.1f}",
                    regime=regime.value,
                    reason=reason,
                    vol_percentile=f"{vol_percentile:.1f}%",
                    adx=f"{adx:.1f}",
                    vol_state=vol_state.value,
                    trend_strength=trend_strength.value
                )

                # 发送 Telegram 通知
                self._notifier.send_message(
                    f"🚫 *信号被拦截*\n\n"
                    f"交易对: `{self._symbol}`\n"
                    f"信号方向: {signal.direction.value}\n"
                    f"信号强度: `{signal.score:.1f}`\n"
                    f"市场状态: `{regime.value}`\n"
                    f"波动率分位数: `{vol_percentile:.1f}%`\n"
                    f"ADX: `{adx:.1f}`\n"
                    f"原因: {reason}"
                )
                return

            # 允许交易，记录状态
            log.info(
                "regime_check_passed",
                regime=regime.value,
                signal_direction=signal.direction.value
            )

        atr = snap.get("atr")
        if not atr or atr <= 0:
            return

        # Calculate position size (1% risk for moderate, 2% for strong)
        account = await self._client.get_account()
        equity = float(account.get("totalWalletBalance", 10000))

        abs_score = abs(signal.score)
        risk_pct = 0.02 if abs_score >= 60 else 0.01
        risk_amount = equity * risk_pct
        stop_distance = atr * SL_MULTIPLIER
        quantity = risk_amount / stop_distance

        if signal.direction == Side.LONG:
            sl_price = price - stop_distance
            tp_price = price + (atr * TP_MULTIPLIER)
            order_side = "BUY"
            sl_side = "SELL"
        else:
            sl_price = price + stop_distance
            tp_price = price - (atr * TP_MULTIPLIER)
            order_side = "SELL"
            sl_side = "BUY"

        log.info(
            "executing_signal",
            symbol=self._symbol,
            direction=signal.direction.value,
            score=f"{signal.score:.1f}",
            price=price,
            sl=f"{sl_price:.2f}",
            tp=f"{tp_price:.2f}",
            qty=f"{quantity:.3f}",
            risk_pct=f"{risk_pct:.1%}",
        )

        try:
            # Place market entry order
            entry_order = await self._client.place_order(
                self._symbol, order_side, quantity
            )
            entry_order_id = entry_order.get("orderId")
            log.info("entry_filled", order_id=entry_order_id)

            # Place stop-loss order (server-side)
            sl_order = await self._client.place_stop_market(
                self._symbol, sl_side, sl_price, quantity
            )
            sl_order_id = sl_order.get("orderId")
            log.info("sl_placed", price=sl_price, order_id=sl_order_id)

            # Place take-profit order (server-side)
            tp_order = await self._client.place_take_profit_market(
                self._symbol, sl_side, tp_price, quantity
            )
            tp_order_id = tp_order.get("orderId")
            log.info("tp_placed", price=tp_price, order_id=tp_order_id)

            self._in_position = True
            self._position_side = order_side

            # 保存持仓状态到数据库
            position = Position(
                id=None,
                symbol=self._symbol,
                side=signal.direction.value,
                entry_price=price,
                quantity=quantity,
                entry_time=int(time.time() * 1000),
                stop_loss_price=sl_price,
                take_profit_price=tp_price,
            )
            self._position_id = self._state_manager.save_position(position)

            # 保存止损订单
            sl_order_obj = Order(
                id=None,
                position_id=self._position_id,
                order_id=str(sl_order_id),
                symbol=self._symbol,
                order_type="STOP_MARKET",
                side=sl_side,
                price=sl_price,
                quantity=quantity,
            )
            self._state_manager.save_order(sl_order_obj)

            # 保存止盈订单
            tp_order_obj = Order(
                id=None,
                position_id=self._position_id,
                order_id=str(tp_order_id),
                symbol=self._symbol,
                order_type="TAKE_PROFIT_MARKET",
                side=sl_side,
                price=tp_price,
                quantity=quantity,
            )
            self._state_manager.save_order(tp_order_obj)

            log.info("state_persisted", position_id=self._position_id)

            # 发送开仓通知
            self._notifier.send_order_opened(
                symbol=self._symbol,
                side=signal.direction.value,
                entry_price=price,
                quantity=quantity,
                stop_loss=sl_price,
                take_profit=tp_price,
                risk_pct=risk_pct * 100,
            )

        except Exception as e:
            log.error("order_failed", error=str(e))
            # 发送错误告警
            self._notifier.send_error("订单执行失败", str(e))
            await self._client.cancel_all_orders(self._symbol)

    async def _update_1d_data(self, kline_4h: dict) -> None:
        """更新 1D 数据（每 6 个 4h K 线检查一次）"""
        if self._df_1d is None:
            return

        # 检查是否需要更新（每天 00:00 UTC）
        kline_time = pd.to_datetime(kline_4h["timestamp"], unit='ms')
        last_1d_time = self._df_1d['timestamp'].iloc[-1]

        # 如果当前 K 线时间超过最后一个 1D K 线时间 + 1 天，则更新
        if (kline_time - last_1d_time).days >= 1:
            log.info("updating_1d_data", last_time=last_1d_time, current_time=kline_time)

            try:
                # 拉取最新的 1D K 线（只需要最近几根）
                raw_klines_1d = await self._client.get_klines(self._symbol, "1d", 10)

                new_klines = []
                for k in raw_klines_1d:
                    ts = pd.to_datetime(k[0], unit='ms')
                    # 只添加新的 K 线
                    if ts > last_1d_time:
                        new_klines.append({
                            "timestamp": ts,
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                        })

                if new_klines:
                    # 追加新数据
                    new_df = pd.DataFrame(new_klines)
                    self._df_1d = pd.concat([self._df_1d, new_df], ignore_index=True)

                    # 保持最近 300 根
                    if len(self._df_1d) > 300:
                        self._df_1d = self._df_1d.iloc[-300:].reset_index(drop=True)

                    log.info("1d_data_updated", new_candles=len(new_klines), total=len(self._df_1d))

                    # 重新检测市场状态
                    if self._regime_detector:
                        new_regime = self._regime_detector.detect(self._df_1d)
                        log.info("regime_updated", regime=new_regime.value)

            except Exception as e:
                log.error("1d_update_failed", error=str(e))

    async def _check_position_closed(self) -> None:
        """检查持仓是否已平仓（止损/止盈触发）"""
        if not self._in_position or self._position_id is None:
            return

        try:
            # 查询币安账户持仓
            account = await self._client.get_account()
            positions = account.get("positions", [])

            # 查找当前交易对的持仓
            current_position = None
            for pos in positions:
                if pos["symbol"] == self._symbol:
                    position_amt = float(pos.get("positionAmt", 0))
                    if abs(position_amt) > 0.0001:  # 有持仓
                        current_position = pos
                        break

            # 如果币安没有持仓，说明已平仓
            if current_position is None:
                log.info("position_closed_detected", symbol=self._symbol)

                # 清空数据库状态
                self._state_manager.clear_position(self._position_id)

                # 重置内存状态
                self._in_position = False
                self._position_side = None
                self._position_id = None

                log.info("state_cleared")

        except Exception as e:
            log.error("check_position_failed", error=str(e))

    async def run(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        await self.initialize()

        stream = f"{self._symbol.lower()}@kline_4h"
        ws_url = f"{TESTNET_WS}/{stream}"

        while True:
            try:
                log.info("ws_connecting", url=ws_url)
                async with websockets.connect(ws_url, ping_interval=30) as ws:
                    log.info("ws_connected", symbol=self._symbol)
                    self._ws_reconnect_count = 0  # 重置重连计数

                    async for msg in ws:
                        data = json.loads(msg)
                        k = data.get("k", {})

                        if not k.get("x"):  # Not a closed candle
                            continue

                        kline = {
                            "timestamp": k["t"],
                            "open": float(k["o"]),
                            "high": float(k["h"]),
                            "low": float(k["l"]),
                            "close": float(k["c"]),
                            "volume": float(k["v"]),
                        }

                        log.info(
                            "kline_closed",
                            symbol=self._symbol,
                            close=kline["close"],
                            time=datetime.fromtimestamp(
                                k["t"] / 1000, tz=timezone.utc
                            ).isoformat(),
                        )

                        # 心跳日志（包含市场状态）
                        if self._regime_detector and self._df_1d is not None:
                            current_regime = self._regime_detector.detect(self._df_1d)
                            adx = self._regime_detector._calculate_adx(self._df_1d, period=14).iloc[-1]
                            atr = self._regime_detector._calculate_atr(self._df_1d, period=14)
                            atr_pct = (atr / self._df_1d['close']) * 100
                            vol_percentile = self._regime_detector._percentile_rank(
                                atr_pct.iloc[-1],
                                atr_pct.iloc[-252:]
                            )

                            log.info(
                                "heartbeat",
                                symbol=self._symbol,
                                price=kline["close"],
                                in_position=self._in_position,
                                regime=current_regime.value,
                                vol_percentile=f"{vol_percentile:.1f}%",
                                adx=f"{adx:.1f}"
                            )

                        # 处理 K 线收盘
                        await self._on_kline_close(kline)

                        # 检查持仓是否已平仓
                        await self._check_position_closed()

            except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
                self._ws_reconnect_count += 1
                log.warning("ws_disconnected", error=str(e), attempt=self._ws_reconnect_count)

                # 发送重连警告
                self._notifier.send_reconnect_warning(self._ws_reconnect_count)

                await asyncio.sleep(5)
                log.info("ws_reconnecting")

            except Exception as e:
                log.error("ws_fatal_error", error=str(e))
                await asyncio.sleep(10)


async def main() -> None:
    config = load_config(profile="default")
    secrets = Secrets()

    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    print(f"Starting live trader for {symbol} on Binance Testnet...")
    print(f"Strategy: KC Breakout + ADX + Volume (4h)")
    print(f"Exit: SL={SL_MULTIPLIER}x ATR, TP={TP_MULTIPLIER}x ATR")
    print()

    trader = LiveTrader(symbol, config, secrets)
    await trader.run()


if __name__ == "__main__":
    asyncio.run(main())
