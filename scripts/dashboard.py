"""
Futurex 交易监控面板
实时显示测试网交易数据
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from futurex.storage.duckdb_store import DuckDBStore
from futurex.indicators.engine import IndicatorEngine
from futurex.indicators.registry import build_default_registry
from futurex.regime import RegimeDetector


# ============================================================================
# 数据加载接口（真实数据源）
# ============================================================================

@st.cache_resource
def get_db():
    """获取 DuckDB 连接（缓存，只读模式）"""
    db_path = Path(__file__).parent.parent / "data" / "futurex.db"
    return DuckDBStore(str(db_path), read_only=True)


@st.cache_resource
def get_indicator_engine():
    """获取指标计算引擎（缓存）"""
    # 使用默认配置创建 registry
    registry = build_default_registry(
        ema_fast=20,
        ema_medium=50,
        ema_slow=200,
        rsi_period=14,
        bb_period=20,
        bb_std=2.0,
        atr_period=14,
    )
    return IndicatorEngine(registry)


def load_account_data() -> dict:
    """加载账户核心指标"""
    db = get_db()
    stats = db.get_trade_stats(last_n=1000)

    if stats["total"] == 0:
        return {
            "total_equity": 10_000.00,
            "initial_equity": 10_000.00,
            "today_pnl": 0.0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "running_days": 0,
        }

    # 计算总权益
    initial_equity = 10_000.00
    total_pnl = stats["total_pnl"]
    total_equity = initial_equity + total_pnl

    # 获取今日交易
    today_trades = db._conn.execute("""
        SELECT SUM(pnl) as today_pnl
        FROM trades
        WHERE DATE(created_at) = CURRENT_DATE
    """).fetchone()
    today_pnl = today_trades[0] if today_trades and today_trades[0] else 0.0

    # 计算运行天数
    first_trade = db._conn.execute("""
        SELECT MIN(entry_time) FROM trades
    """).fetchone()
    if first_trade and first_trade[0]:
        running_days = max(1, int((datetime.now().timestamp() - first_trade[0]) / 86400))
    else:
        running_days = 0

    return {
        "total_equity": total_equity,
        "initial_equity": initial_equity,
        "today_pnl": today_pnl,
        "total_pnl": total_pnl,
        "win_rate": stats["win_rate"],
        "total_trades": stats["total"],
        "running_days": running_days,
    }


def load_kline_data(symbol: str = "ETHUSDT", interval: str = "4h", limit: int = 200) -> pd.DataFrame:
    """加载 K 线数据 + 技术指标"""
    db = get_db()
    engine = get_indicator_engine()

    # 从 DuckDB 读取 K 线
    candles = db.get_klines(symbol, interval, limit)

    if not candles:
        # 如果没有数据，返回空 DataFrame
        return pd.DataFrame()

    # 转换为 DataFrame
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

    # 计算技术指标
    engine.compute(symbol, interval, df)

    # 为每一行添加指标
    df["atr"] = 0.0
    df["ema200"] = df["close"]
    df["kc_upper"] = df["close"] * 1.02
    df["kc_lower"] = df["close"] * 0.98

    for idx, row in df.iterrows():
        snap = engine.get_latest(symbol, interval)
        if snap and snap.values:
            df.at[idx, "atr"] = snap.get("atr", 0)
            df.at[idx, "ema200"] = snap.get("ema200", row["close"])
            df.at[idx, "kc_upper"] = snap.get("kc_upper", row["close"] * 1.02)
            df.at[idx, "kc_lower"] = snap.get("kc_lower", row["close"] * 0.98)

    return df


def load_regime_data(symbol: str = "BTCUSDT") -> dict:
    """加载市场状态机数据"""
    db = get_db()

    # 从 DuckDB 读取 1D K 线（最近 300 天）
    candles_1d = db.get_klines(symbol, "1d", 300)

    if not candles_1d or len(candles_1d) < 252:
        return {
            "regime": "UNKNOWN",
            "vol_percentile": 0.0,
            "adx": 0.0,
            "vol_state": "UNKNOWN",
            "trend_strength": "UNKNOWN",
            "trend_direction": "UNKNOWN",
            "available": False
        }

    # 转换为 DataFrame
    df_1d = pd.DataFrame(candles_1d)
    df_1d["timestamp"] = pd.to_datetime(df_1d["timestamp"], unit="ms")

    # 初始化状态机
    detector = RegimeDetector(
        lookback_period=252,
        vol_thresholds=(30, 70),
        adx_thresholds=(20, 30)
    )

    # 检测当前状态
    current_regime = detector.detect(df_1d)

    # 计算详细指标
    vol_state = detector._classify_volatility(df_1d)
    trend_strength = detector._classify_trend_strength(df_1d)
    trend_direction = detector._classify_trend_direction(df_1d)

    adx = detector._calculate_adx(df_1d, period=14).iloc[-1]
    atr = detector._calculate_atr(df_1d, period=14)
    atr_pct = (atr / df_1d['close']) * 100
    vol_percentile = detector._percentile_rank(
        atr_pct.iloc[-1],
        atr_pct.iloc[-252:]
    )

    return {
        "regime": current_regime.value,
        "vol_percentile": vol_percentile,
        "adx": adx,
        "vol_state": vol_state.value,
        "trend_strength": trend_strength.value,
        "trend_direction": trend_direction.value,
        "available": True
    }


def load_trade_history(limit: int = 20) -> pd.DataFrame:
    """加载历史交易记录"""
    db = get_db()
    result = db._conn.execute("""
        SELECT
            entry_time,
            exit_time,
            symbol,
            side,
            entry_price,
            exit_price,
            quantity,
            pnl,
            duration_seconds
        FROM trades
        ORDER BY exit_time DESC
        LIMIT ?
    """, (limit,)).fetchall()

    if not result:
        return pd.DataFrame()

    trades = []
    for row in result:
        trades.append({
            "entry_time": datetime.fromtimestamp(row[0]) if row[0] else None,
            "exit_time": datetime.fromtimestamp(row[1]) if row[1] else None,
            "symbol": row[2],
            "side": row[3],
            "entry_price": row[4],
            "exit_price": row[5],
            "quantity": row[6],
            "pnl": row[7],
            "duration_hours": row[8] / 3600 if row[8] else 0,
        })

    return pd.DataFrame(trades)


def load_active_positions() -> pd.DataFrame:
    """加载当前持仓（暂时返回空，需要对接实时 API）"""
    # TODO: 对接 Binance Testnet API 获取实时持仓
    return pd.DataFrame()


def load_trade_markers(df_kline: pd.DataFrame) -> pd.DataFrame:
    """从历史交易生成图表标记点"""
    db = get_db()

    if df_kline.empty:
        return pd.DataFrame()

    # 获取时间范围内的交易
    start_ts = df_kline["timestamp"].min().timestamp()
    end_ts = df_kline["timestamp"].max().timestamp()

    result = db._conn.execute("""
        SELECT entry_time, entry_price, exit_time, exit_price, side, pnl
        FROM trades
        WHERE entry_time >= ? AND entry_time <= ?
        ORDER BY entry_time
    """, (start_ts, end_ts)).fetchall()

    if not result:
        return pd.DataFrame()

    markers = []
    for row in result:
        entry_time = datetime.fromtimestamp(row[0])
        entry_price = row[1]
        exit_time = datetime.fromtimestamp(row[2])
        exit_price = row[3]
        side = row[4]
        pnl = row[5]

        # 开仓标记
        marker_type = "ENTRY_LONG" if side == "LONG" else "ENTRY_SHORT"
        markers.append({
            "timestamp": entry_time,
            "price": entry_price,
            "type": marker_type,
        })

        # 平仓标记（根据盈亏判断是止盈还是止损）
        exit_type = "TP" if pnl > 0 else "SL"
        markers.append({
            "timestamp": exit_time,
            "price": exit_price,
            "type": exit_type,
        })

    return pd.DataFrame(markers)


# ============================================================================
# 图表绘制函数
# ============================================================================

def plot_kline_chart(df_kline: pd.DataFrame, df_markers: pd.DataFrame, symbol: str) -> go.Figure:
    """绘制 K 线图 + Keltner Channel + EMA200 + 交易标记"""
    fig = go.Figure()

    if df_kline.empty:
        fig.add_annotation(
            text="暂无数据，请先运行回测或实盘交易",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=20, color="gray")
        )
        fig.update_layout(template="plotly_dark", height=600)
        return fig

    # 1. K 线主图
    fig.add_trace(go.Candlestick(
        x=df_kline["timestamp"],
        open=df_kline["open"],
        high=df_kline["high"],
        low=df_kline["low"],
        close=df_kline["close"],
        name="价格",
        increasing_line_color="#00ff88",
        decreasing_line_color="#ff4444",
    ))

    # 2. Keltner Channel 上下轨
    if "kc_upper" in df_kline.columns:
        fig.add_trace(go.Scatter(
            x=df_kline["timestamp"],
            y=df_kline["kc_upper"],
            mode="lines",
            name="KC 上轨",
            line=dict(color="#888888", width=1, dash="dot"),
        ))
        fig.add_trace(go.Scatter(
            x=df_kline["timestamp"],
            y=df_kline["kc_lower"],
            mode="lines",
            name="KC 下轨",
            line=dict(color="#888888", width=1, dash="dot"),
            fill="tonexty",
            fillcolor="rgba(136, 136, 136, 0.1)",
        ))

    # 3. EMA200 趋势线
    if "ema200" in df_kline.columns:
        fig.add_trace(go.Scatter(
            x=df_kline["timestamp"],
            y=df_kline["ema200"],
            mode="lines",
            name="EMA200",
            line=dict(color="#ffaa00", width=2),
        ))

    # 4. 交易标记点
    if not df_markers.empty:
        marker_config = {
            "ENTRY_LONG": {"color": "#00ff88", "symbol": "triangle-up", "size": 12, "name": "开多"},
            "ENTRY_SHORT": {"color": "#ff4444", "symbol": "triangle-down", "size": 12, "name": "开空"},
            "TP": {"color": "#00ddff", "symbol": "star", "size": 10, "name": "止盈"},
            "SL": {"color": "#ff8800", "symbol": "x", "size": 10, "name": "止损"},
        }

        for marker_type, config in marker_config.items():
            df_filtered = df_markers[df_markers["type"] == marker_type]
            if not df_filtered.empty:
                fig.add_trace(go.Scatter(
                    x=df_filtered["timestamp"],
                    y=df_filtered["price"],
                    mode="markers",
                    name=config["name"],
                    marker=dict(
                        color=config["color"],
                        symbol=config["symbol"],
                        size=config["size"],
                        line=dict(color="white", width=1),
                    ),
                ))

    # 5. 图表样式（暗色主题）
    fig.update_layout(
        template="plotly_dark",
        title=f"{symbol} 4H K线图",
        xaxis_title="",
        yaxis_title="价格 (USDT)",
        height=600,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        margin=dict(l=50, r=50, t=80, b=50),
    )

    return fig


# ============================================================================
# Streamlit 主布局
# ============================================================================

def main():
    # 页面配置
    st.set_page_config(
        page_title="Futurex 交易监控",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # 自定义 CSS（强化暗色主题）
    st.markdown("""
        <style>
        .stApp {
            background-color: #0e1117;
        }
        </style>
    """, unsafe_allow_html=True)

    # 标题
    st.title("📊 Futurex 交易监控面板")
    st.markdown("---")

    # 交易对选择
    symbol = st.selectbox("选择交易对", ["ETHUSDT", "BTCUSDT", "SOLUSDT"], index=0)

    # ========================================================================
    # 顶部：核心指标区
    # ========================================================================
    account = load_account_data()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="总权益",
            value=f"${account['total_equity']:,.2f}",
            delta=f"{account['total_pnl']:+,.2f}",
        )

    with col2:
        pnl_color = "normal" if account['today_pnl'] >= 0 else "inverse"
        st.metric(
            label="今日盈亏",
            value=f"${account['today_pnl']:+,.2f}",
            delta=f"{account['today_pnl'] / account['initial_equity'] * 100:+.2f}%",
            delta_color=pnl_color,
        )

    with col3:
        st.metric(
            label="胜率",
            value=f"{account['win_rate'] * 100:.1f}%",
            delta=f"{account['total_trades']} 笔交易",
        )

    with col4:
        trades_per_day = account['total_trades'] / account['running_days'] if account['running_days'] > 0 else 0
        st.metric(
            label="运行天数",
            value=f"{account['running_days']} 天",
            delta=f"{trades_per_day:.2f} 笔/天",
        )

    st.markdown("---")

    # ========================================================================
    # 市场状态机面板
    # ========================================================================
    st.subheader("🎯 市场状态机 (Regime Detector)")

    regime_data = load_regime_data(symbol=symbol)

    if regime_data["available"]:
        # 状态指示器
        regime_colors = {
            "TREND_BULL": "🟢",
            "TREND_BEAR": "🔴",
            "VOLATILE_CHOP": "🟡",
            "RANGE_BOUND": "🟠",
            "DEAD_CHOP": "⚫",
            "UNKNOWN": "⚪"
        }

        regime_status = {
            "TREND_BULL": "允许交易 ✅",
            "TREND_BEAR": "允许交易 ✅",
            "VOLATILE_CHOP": "拦截信号 🚫",
            "RANGE_BOUND": "拦截信号 🚫",
            "DEAD_CHOP": "拦截信号 🚫",
            "UNKNOWN": "未知状态"
        }

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            regime_icon = regime_colors.get(regime_data["regime"], "⚪")
            st.metric(
                label="当前状态",
                value=f"{regime_icon} {regime_data['regime']}",
                delta=regime_status.get(regime_data["regime"], "")
            )

        with col2:
            vol_color = "🔴" if regime_data["vol_percentile"] < 30 else "🟢" if regime_data["vol_percentile"] > 70 else "🟡"
            st.metric(
                label="波动率分位数",
                value=f"{vol_color} {regime_data['vol_percentile']:.1f}%",
                delta=regime_data["vol_state"]
            )

        with col3:
            adx_color = "🟢" if regime_data["adx"] > 30 else "🟡" if regime_data["adx"] > 20 else "🔴"
            st.metric(
                label="ADX 趋势强度",
                value=f"{adx_color} {regime_data['adx']:.1f}",
                delta=regime_data["trend_strength"]
            )

        with col4:
            direction_icon = "📈" if regime_data["trend_direction"] == "BULL" else "📉" if regime_data["trend_direction"] == "BEAR" else "↔️"
            st.metric(
                label="趋势方向",
                value=f"{direction_icon} {regime_data['trend_direction']}",
                delta=""
            )

        # 状态说明
        st.info(
            f"**状态机说明**: 当前市场处于 `{regime_data['regime']}` 状态。"
            f"{'✅ 允许开仓交易' if regime_data['regime'] in ['TREND_BULL', 'TREND_BEAR'] else '🚫 拦截所有开仓信号，避免在不利环境中交易'}"
        )
    else:
        st.warning("⚠️ 市场状态机数据不足（需要至少 252 根 1D K 线）")

    st.markdown("---")

    # ========================================================================
    # 中部：主图表区
    # ========================================================================
    df_kline = load_kline_data(symbol=symbol, interval="4h", limit=200)
    df_markers = load_trade_markers(df_kline)
    fig = plot_kline_chart(df_kline, df_markers, symbol)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ========================================================================
    # 底部：双列表区
    # ========================================================================
    col_left, col_right = st.columns([0.4, 0.6])

    with col_left:
        st.subheader("🔥 当前持仓")
        df_positions = load_active_positions()

        if df_positions.empty:
            st.info("暂无持仓")
        else:
            # 格式化显示
            df_display = df_positions.copy()
            df_display["开仓价"] = df_display["entry_price"].apply(lambda x: f"${x:,.2f}")
            df_display["当前价"] = df_display["current_price"].apply(lambda x: f"${x:,.2f}")
            df_display["盈亏"] = df_display["unrealized_pnl"].apply(
                lambda x: f"${x:+,.2f}" if x >= 0 else f"${x:,.2f}"
            )
            df_display["数量"] = df_display["quantity"].apply(lambda x: f"{x:.3f}")

            st.dataframe(
                df_display[["symbol", "side", "开仓价", "当前价", "数量", "盈亏"]],
                use_container_width=True,
                hide_index=True,
            )

    with col_right:
        st.subheader("📜 历史交易")
        df_trades = load_trade_history(limit=15)

        if df_trades.empty:
            st.info("暂无交易记录")
        else:
            # 格式化显示
            df_display = df_trades.copy()
            df_display["平仓时间"] = df_display["exit_time"].dt.strftime("%m-%d %H:%M")
            df_display["方向"] = df_display["side"].map({"LONG": "做多", "SHORT": "做空"})
            df_display["开仓价"] = df_display["entry_price"].apply(lambda x: f"${x:,.0f}")
            df_display["平仓价"] = df_display["exit_price"].apply(lambda x: f"${x:,.0f}")
            df_display["盈亏"] = df_display["pnl"].apply(
                lambda x: f"${x:+,.2f}" if x >= 0 else f"${x:,.2f}"
            )
            df_display["持仓时长"] = df_display["duration_hours"].apply(lambda x: f"{x:.1f}h")

            st.dataframe(
                df_display[["平仓时间", "方向", "开仓价", "平仓价", "盈亏", "持仓时长"]],
                use_container_width=True,
                hide_index=True,
            )

    # 刷新提示
    st.markdown("---")
    st.caption("💡 提示：刷新页面更新数据")


if __name__ == "__main__":
    main()
