#!/usr/bin/env python
"""
检查交易系统状态
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from dotenv import load_dotenv
load_dotenv()

from live_trader import BinanceTestnetClient
from futurex.storage.duckdb_store import DuckDBStore

async def check_status():
    print("=" * 60)
    print("Futurex 交易系统状态检查")
    print("=" * 60)

    # 1. 检查 API 连接
    print("\n[1] API 连接状态")
    try:
        client = BinanceTestnetClient(
            os.getenv('BINANCE_API_KEY'),
            os.getenv('BINANCE_API_SECRET'),
            os.getenv('PROXY_URL', '')
        )
        account = await client.get_account()
        print(f"  [OK] REST API 连接正常")
        print(f"  账户余额: {account.get('totalWalletBalance', 'N/A')} USDT")
        print(f"  可用余额: {account.get('availableBalance', 'N/A')} USDT")

        # 检查持仓
        positions = [p for p in account.get('positions', []) if float(p.get('positionAmt', 0)) != 0]
        if positions:
            print(f"  当前持仓: {len(positions)} 个")
            for pos in positions:
                print(f"    - {pos['symbol']}: {pos['positionAmt']} @ {pos['entryPrice']}")
        else:
            print(f"  当前持仓: 无")

    except Exception as e:
        print(f"  [FAIL] API 连接失败: {e}")

    # 2. 检查数据库
    print("\n[2] 数据库状态")
    try:
        db = DuckDBStore("data/futurex.db")
        stats = db.get_trade_stats(last_n=1000)
        print(f"  [OK] 数据库连接正常")
        print(f"  历史交易: {stats.get('total', 0)} 笔")
        if stats.get('total', 0) > 0:
            print(f"  胜率: {stats.get('win_rate', 0) * 100:.1f}%")
            print(f"  总盈亏: ${stats.get('total_pnl', 0):.2f}")
    except Exception as e:
        print(f"  [FAIL] 数据库连接失败: {e}")

    # 3. 检查下一个 K 线收盘时间
    print("\n[3] 下一个信号检测时间")
    try:
        klines = await client.get_klines('ETHUSDT', '4h', 1)
        close_time = klines[0][6]
        close_dt = datetime.fromtimestamp(close_time / 1000, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        remaining = (close_dt - now).total_seconds() / 60
        print(f"  当前 4h K 线收盘时间: {close_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  剩余时间: {remaining:.1f} 分钟 ({remaining/60:.1f} 小时)")
    except Exception as e:
        print(f"  ✗ 无法获取 K 线数据: {e}")

    # 4. 检查日志文件
    print("\n[4] 日志文件")
    log_file = Path("logs/live_trader.log")
    if log_file.exists():
        size_kb = log_file.stat().st_size / 1024
        print(f"  [OK] 日志文件存在: {log_file}")
        print(f"  文件大小: {size_kb:.1f} KB")
        print(f"  最后 5 行:")
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-5:]:
                print(f"    {line.rstrip()}")
    else:
        print(f"  [FAIL] 日志文件不存在")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(check_status())
