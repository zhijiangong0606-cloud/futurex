"""
下载历史 K 线数据到 DuckDB
用于市场状态机和仪表板显示
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from futurex.storage.duckdb_store import DuckDBStore
import httpx
import structlog

log = structlog.get_logger()


async def download_klines(symbol: str, interval: str, days: int = 365):
    """
    从 Binance 下载历史 K 线数据

    Args:
        symbol: 交易对（如 BTCUSDT）
        interval: 时间周期（1d, 4h, 1h）
        days: 下载天数
    """
    # 计算时间范围
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    # Binance API
    url = "https://fapi.binance.com/fapi/v1/klines"

    all_klines = []
    current_start = start_time

    log.info("downloading_klines", symbol=symbol, interval=interval, days=days)

    async with httpx.AsyncClient(timeout=30.0) as client:
        while current_start < end_time:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current_start,
                "endTime": end_time,
                "limit": 1500  # Binance 最大限制
            }

            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                klines = resp.json()

                if not klines:
                    break

                all_klines.extend(klines)

                # 更新起始时间为最后一根 K 线的时间
                current_start = klines[-1][0] + 1

                log.info("batch_downloaded", count=len(klines), total=len(all_klines))

                # 避免请求过快
                await asyncio.sleep(0.5)

            except Exception as e:
                log.error("download_failed", error=str(e))
                break

    log.info("download_complete", symbol=symbol, interval=interval, total=len(all_klines))
    return all_klines


async def save_to_db(symbol: str, interval: str, klines: list):
    """保存 K 线数据到 DuckDB"""
    db_path = Path(__file__).parent.parent / "data" / "futurex.db"
    db = DuckDBStore(str(db_path))

    log.info("saving_to_db", symbol=symbol, interval=interval, count=len(klines))

    # 转换为字典格式
    candles = []
    for k in klines:
        candles.append({
            "timestamp": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5])
        })

    # 批量插入
    saved_count = db.insert_klines(symbol, interval, candles)
    log.info("save_complete", saved=saved_count)


async def main():
    """主函数"""
    print("=" * 80)
    print("Futurex Historical Data Downloader")
    print("=" * 80)
    print()

    # 配置
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    intervals = [
        ("1d", 365),   # 1 年日线数据
        ("4h", 180),   # 6 个月 4h 数据
    ]

    for symbol in symbols:
        print(f"\n[*] Downloading {symbol} data...")

        for interval, days in intervals:
            print(f"  [+] {interval} klines ({days} days)...")

            # 下载数据
            klines = await download_klines(symbol, interval, days)

            if klines:
                # 保存到数据库
                await save_to_db(symbol, interval, klines)
                print(f"  [OK] Complete: {len(klines)} klines")
            else:
                print(f"  [FAIL] No data")

    print()
    print("=" * 80)
    print("[SUCCESS] All data downloaded!")
    print()
    print("Next steps:")
    print("  1. Refresh dashboard to see regime detector")
    print("  2. Start live trading")
    print("  3. Run backtest analysis")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
