# 小米 MiMo Token 资助申请表填写稿

这份文档用于直接复制到申请表。建议优先使用“高强度中文项目描述”，如果输入框字数有限，再使用“精简版项目描述”。

## 使用的 Agent

Claude Code

## 使用的模型

Claude 系列 / Claude Opus 4.6

## API 类型

API 直调

## GitHub 仓库

https://github.com/zhijiangong0606-cloud/futurex

## 精简版项目描述

Futurex 是一个面向 Binance USDT-M 永续合约的 AI 辅助自适应量化交易系统。项目使用 Claude Code 完成策略研究、架构设计、回测引擎、Walk-Forward 验证、法医级失败诊断、市场状态机、风控系统和实盘测试网执行模块，并在运行时集成 Claude API 作为中等置信度交易信号的情绪/上下文过滤器。

核心创新是 Market Regime State Machine：使用 252 日波动率分位数、ADX 趋势强度和 EMA 趋势排列识别市场状态，只在趋势友好环境允许新开仓，在低波动死寂、区间震荡和高波动震荡环境自动阻断交易。系统还包含 850+ 次 Walk-Forward 回测、悲观撮合模型、三维度失败归因、六层风控、Binance 测试网执行、Telegram 告警、Streamlit 仪表盘和安全配置隔离。

## 高强度中文项目描述

Futurex 是一个面向加密货币永续合约市场的 AI 辅助量化交易研究与执行系统，目标交易场景是 Binance USDT-M Futures。它不是简单的交易 Bot，而是一个完整的研究闭环：Claude Code 参与了策略生成、系统架构、事件驱动回测、Walk-Forward 参数敏感性分析、Out-of-Sample 验证、法医级失败诊断、市场状态识别、风险管理和生产化监控的构建过程。

项目最重要的创新是 Market Regime State Machine。系统不会盲目执行所有技术信号，而是先用 252 日 ATR 波动率分位数、ADX 趋势强度和 EMA50/EMA200 趋势排列识别当前市场状态，将市场划分为 TREND_BULL、TREND_BEAR、DEAD_CHOP、RANGE_BOUND、VOLATILE_CHOP。只有趋势友好的状态才允许新开仓，低波动死寂、区间震荡和高波动震荡状态会触发 Regime Kill Switch，阻断新交易，但已有仓位仍由服务端止损/止盈继续保护。

Claude 的使用不是一次性生成代码，而是贯穿整个量化研究流程。项目先实现 Keltner Channel breakout 策略，并发现其在 2020-2023 样本内收益较高；随后通过 Claude 辅助的 850+ 次 Walk-Forward 回测和 2024-2025 样本外验证发现策略存在过拟合；再通过三维度法医诊断排除撮合引擎、EMA 过滤和止损寿命问题，最终把系统重构为自适应市场状态过滤 + 六层风控架构。

运行时系统还包含一个 Claude API 情绪/上下文过滤器：中等置信度交易信号会进入 AI review，Claude 只给出有上限的 sentiment adjustment，而不是直接决定交易，最终仍必须经过回撤熔断、日亏损限制、最大持仓、相关性暴露、仓位计算和止损管理等风险门控。项目同时实现了 Binance 测试网执行、Telegram 实时告警、Streamlit 仪表盘、DuckDB 历史数据存储、SQLite 状态恢复和安全配置隔离。

## 推荐强调点

- 这是完整项目，不是 API demo。
- Claude 被用于研究、诊断、架构和代码实现，而不仅是聊天问答。
- 项目体现了“发现策略失效并重构系统”的真实工程过程。
- GitHub 仓库包含可审查的代码、测试、回测脚本、诊断脚本和资助证明文档。
- `.env`、API key、Telegram token、数据库和日志均未提交，安全卫生良好。

## 可截图证明

- GitHub 首页第一屏：README 中的 Grant Review Materials。
- `docs/MI_TOKEN_GRANT_APPLICATION.md`：英文评审说明。
- `docs/PROJECT_EVIDENCE.md`：证据映射。
- `src/futurex/strategy/ai_filter.py`：Claude API 直调过滤器。
- `src/futurex/regime/detector.py`：市场状态机。
- `scripts/walkforward_analysis.py`：850+ Walk-Forward 验证逻辑。
- `src/futurex/risk/gate.py`：六层风控入口。
