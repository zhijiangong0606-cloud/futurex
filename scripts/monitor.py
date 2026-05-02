#!/usr/bin/env python
"""
实时监控脚本 - 每分钟检查交易机器人状态
"""
import time
from datetime import datetime
from pathlib import Path

log_file = Path("logs/live_trader.log")
last_size = 0

print("开始监控交易机器人...")
print("日志文件:", log_file)
print("按 Ctrl+C 停止监控\n")

try:
    while True:
        if log_file.exists():
            current_size = log_file.stat().st_size
            if current_size > last_size:
                # 有新日志
                with open(log_file, 'r', encoding='utf-8') as f:
                    f.seek(last_size)
                    new_content = f.read()
                    if new_content.strip():
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 新日志:")
                        print(new_content)
                last_size = current_size
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 运行中，无新日志", end='\r')
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待日志文件...", end='\r')

        time.sleep(60)  # 每分钟检查一次
except KeyboardInterrupt:
    print("\n\n监控已停止")
