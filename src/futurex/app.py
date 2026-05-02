from __future__ import annotations

import asyncio
import signal
from typing import Any

from .core.config import AppConfig, Secrets, load_config
from .core.constants import Side, SignalStrength, DrawdownTier
from .core.events import EventBus, KlineClose, OrderUpdate, AccountUpdate
from .core.logging import get_logger, setup_logging
from .data.kline_aggregator import KlineAggregator
from .data.orderbook import OrderBookCache
from .data.rest_client import RESTClient
from .data.stream_router import StreamRouter
from .data.user_stream import UserStreamManager
from .data.ws_manager import WSManager
from .execution.fill_tracker import FillTracker
from .execution.order_manager import OrderManager
from .indicators.engine import IndicatorEngine
from .indicators.registry import build_default_registry
from .notify.telegram import TelegramNotifier
from .risk import AccountState, Position
from .risk.gate import RiskGate
from .risk.stop_manager import StopManager
from .storage.duckdb_store import DuckDBStore
from .strategy.ai_filter import AIFilter
from .strategy.signal_scorer import SignalScorer

log = get_logger("futurex.app")


class TradingApp:
    def __init__(self, config: AppConfig, secrets: Secrets) -> None:
        self._config = config
        self._secrets = secrets
        self._running = False

        self._event_bus = EventBus()
        self._account = AccountState()

        self._rest = RESTClient(
            base_url=config.exchange.base_url,
            api_key=secrets.binance_api_key,
            api_secret=secrets.binance_api_secret,
            proxy_url=secrets.proxy_url,
        )

        self._ws_market = WSManager(
            base_ws_url=config.exchange.ws_url,
        )

        self._router = StreamRouter()
        self._kline_agg = KlineAggregator(self._event_bus)
        self._orderbook = OrderBookCache(self._event_bus)

        self._user_stream = UserStreamManager(
            event_bus=self._event_bus,
            rest_client=self._rest,
            ws_manager_factory=lambda on_message: WSManager(
                base_ws_url=config.exchange.ws_url,
                on_message=on_message,
            ),
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
        self._ai_filter = AIFilter(config.ai)

        self._risk_gate = RiskGate(config.risk)
        self._stop_manager = StopManager(config.risk.atr_multiplier)

        self._order_manager = OrderManager(self._rest, self._event_bus)
        self._fill_tracker = FillTracker(self._event_bus)

        self._db = DuckDBStore(config.storage.duckdb_path)

        self._notifier = TelegramNotifier(
            bot_token=secrets.telegram_bot_token,
            chat_id=secrets.telegram_chat_id,
        )

    async def start(self) -> None:
        self._running = True
        log.info("app_starting", testnet=self._config.exchange.testnet)

        for symbol in self._config.exchange.symbols:
            try:
                await self._rest.set_leverage(symbol, self._config.exchange.leverage)
                await self._rest.set_margin_type(symbol, self._config.exchange.margin_type)
            except Exception as e:
                log.warning("setup_error", symbol=symbol, error=str(e))

        account_data = await self._rest.get_account()
        self._update_account_from_rest(account_data)
        self._risk_gate.drawdown.initialize(self._account.equity)

        for symbol in self._config.exchange.symbols:
            for tf in self._config.exchange.timeframes:
                try:
                    candles = await self._rest.get_klines(symbol, tf, 500)
                    self._kline_agg.initialize_buffer(symbol, tf, candles)
                    self._db.insert_klines(symbol, tf, candles)
                except Exception as e:
                    log.error("kline_init_error", symbol=symbol, tf=tf, error=str(e))

        self._router.register("kline", self._kline_agg.on_kline)
        self._router.register("bookTicker", self._orderbook.on_book_ticker)
        self._router.register("depth", self._orderbook.on_depth)
        self._ws_market.set_message_handler(self._router.dispatch)

        streams = self._build_stream_list()
        await self._ws_market.start(streams)

        await self._user_stream.start()

        asyncio.create_task(self._main_loop())
        asyncio.create_task(self._account_update_loop())

        await self._notifier.notify_system(
            f"Bot started ({'TESTNET' if self._config.exchange.testnet else 'MAINNET'})"
        )

        log.info("app_started", symbols=self._config.exchange.symbols)

    async def stop(self) -> None:
        self._running = False
        log.info("app_stopping")

        await self._ws_market.stop()
        await self._user_stream.stop()
        await self._rest.close()
        self._db.close()
        await self._notifier.notify_system("Bot stopped")
        await self._notifier.close()

        log.info("app_stopped")

    async def _main_loop(self) -> None:
        kline_queue = self._event_bus.subscribe("kline_close")

        while self._running:
            try:
                event = await asyncio.wait_for(kline_queue.get(), timeout=60)
                if not isinstance(event, KlineClose):
                    continue

                candles = self._kline_agg.get_candles(event.symbol, event.interval)
                self._indicator_engine.compute(event.symbol, event.interval, candles)

                if event.interval not in ("1h", "4h"):
                    continue

                indicators = {}
                for tf in self._config.exchange.timeframes:
                    snap = self._indicator_engine.get_latest(event.symbol, tf)
                    if snap.values:
                        indicators[tf] = snap

                if not indicators:
                    continue

                current_price = event.close
                signal = self._scorer.score(event.symbol, indicators, current_price)

                if signal is None:
                    continue

                if signal.requires_ai_review and self._ai_filter.should_call(signal):
                    indicator_summary = {
                        tf: snap.values for tf, snap in indicators.items()
                    }
                    sentiment = await self._ai_filter.evaluate(signal, indicator_summary)
                    signal.score = signal.score * (1 + sentiment)

                    abs_score = abs(signal.score)
                    if abs_score >= self._config.strategy.entry_threshold:
                        signal.strength = SignalStrength.STRONG
                    elif abs_score >= self._config.strategy.partial_threshold:
                        signal.strength = SignalStrength.MODERATE
                    else:
                        continue

                atr = indicators.get("1h", indicators.get("4h"))
                atr_value = atr.get("atr") if atr else 0
                if atr_value <= 0:
                    continue

                verdict = self._risk_gate.evaluate(
                    symbol=signal.symbol,
                    side=signal.direction,
                    signal_score=signal.score,
                    signal_strength=signal.strength,
                    entry_price=current_price,
                    atr=atr_value,
                    account=self._account,
                )

                if verdict.approved:
                    result = await self._order_manager.execute_signal(verdict)
                    if result:
                        await self._notifier.notify_trade_open(
                            symbol=signal.symbol,
                            side=signal.direction.value,
                            quantity=verdict.position_size,
                            entry_price=current_price,
                            stop_loss=verdict.stop_loss,
                            risk_amount=verdict.risk_amount,
                        )
                else:
                    log.info(
                        "signal_rejected",
                        symbol=signal.symbol,
                        rejections=verdict.rejections,
                    )

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("main_loop_error", error=str(e))
                await asyncio.sleep(1)

    async def _account_update_loop(self) -> None:
        account_queue = self._event_bus.subscribe("account_update")
        order_queue = self._event_bus.subscribe("order_update")

        while self._running:
            try:
                done, _ = await asyncio.wait(
                    [
                        asyncio.create_task(account_queue.get()),
                        asyncio.create_task(order_queue.get()),
                    ],
                    timeout=30,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in done:
                    event = task.result()

                    if isinstance(event, AccountUpdate):
                        usdt_balance = event.balances.get("USDT", 0)
                        if usdt_balance > 0:
                            self._account.equity = usdt_balance

                        self._account.open_positions = []
                        for p in event.positions:
                            if abs(float(p.get("amount", 0))) > 0:
                                side = Side.LONG if float(p["amount"]) > 0 else Side.SHORT
                                self._account.open_positions.append(
                                    Position(
                                        symbol=p["symbol"],
                                        side=side,
                                        entry_price=float(p["entry_price"]),
                                        quantity=abs(float(p["amount"])),
                                        leverage=self._config.exchange.leverage,
                                        unrealized_pnl=float(p.get("unrealized_pnl", 0)),
                                    )
                                )

                        tier = self._risk_gate.drawdown.update(self._account.equity)
                        if tier == DrawdownTier.TIER_3:
                            await asyncio.shield(
                                self._order_manager.emergency_flatten_all(
                                    self._account.open_positions
                                )
                            )
                            await self._notifier.notify_risk_alert(
                                "TIER_3",
                                f"EMERGENCY FLATTEN - Drawdown exceeded {self._config.risk.drawdown_tier3:.0%}",
                            )
                        elif tier != DrawdownTier.NORMAL:
                            await self._notifier.notify_risk_alert(
                                tier.value,
                                f"Drawdown: {self._risk_gate.drawdown.current_drawdown:.2%}",
                            )

                    elif isinstance(event, OrderUpdate):
                        record = self._fill_tracker.on_order_update(event, self._account)
                        if record:
                            self._risk_gate.daily_loss.on_trade_closed(record.pnl)
                            self._risk_gate.sizer.add_trade(record)
                            self._db.insert_trade(
                                {
                                    "symbol": record.symbol,
                                    "side": record.side,
                                    "entry_price": record.entry_price,
                                    "exit_price": record.exit_price,
                                    "quantity": record.quantity,
                                    "pnl": record.pnl,
                                    "duration_seconds": record.duration_seconds,
                                    "entry_time": record.entry_time,
                                    "exit_time": record.exit_time,
                                }
                            )
                            await self._notifier.notify_trade_close(
                                symbol=record.symbol,
                                pnl=record.pnl,
                                exit_price=record.exit_price,
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("account_loop_error", error=str(e))
                await asyncio.sleep(1)

    def _build_stream_list(self) -> list[str]:
        streams = []
        for symbol in self._config.exchange.symbols:
            s = symbol.lower()
            for tf in self._config.exchange.timeframes:
                streams.append(f"{s}@kline_{tf}")
            streams.append(f"{s}@bookTicker")
            streams.append(f"{s}@depth10@500ms")
        return streams

    def _update_account_from_rest(self, data: dict[str, Any]) -> None:
        for asset in data.get("assets", []):
            if asset.get("asset") == "USDT":
                self._account.equity = float(asset.get("walletBalance", 0))
                self._account.available_balance = float(asset.get("availableBalance", 0))
                break

        self._account.open_positions = []
        for p in data.get("positions", []):
            amt = float(p.get("positionAmt", 0))
            if abs(amt) > 0:
                side = Side.LONG if amt > 0 else Side.SHORT
                self._account.open_positions.append(
                    Position(
                        symbol=p["symbol"],
                        side=side,
                        entry_price=float(p.get("entryPrice", 0)),
                        quantity=abs(amt),
                        leverage=int(p.get("leverage", 1)),
                        unrealized_pnl=float(p.get("unrealizedProfit", 0)),
                    )
                )


async def run(profile: str = "default") -> None:
    setup_logging()
    config = load_config(profile=profile)
    secrets = Secrets()

    app = TradingApp(config, secrets)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(app.stop()))
        except NotImplementedError:
            pass

    try:
        await app.start()
        while app._running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await app.stop()
