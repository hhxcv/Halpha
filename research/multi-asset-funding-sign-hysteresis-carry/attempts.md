# 实际尝试与失败记录

## 2026-07-20 预注册

- 先读取两项既有 carry 的盈利与样本集中反证，再联网核对原始定价/basis/predictability 研究和 Binance 官方 settled funding 数据边界。
- 固定 sign-only 两正入场/两非正退出、宇宙、两单位资本、成本、三阶段和样本门；未先运行新规则或下载父研究封存数据。
- 代码通过 `python -m py_compile`；启封前 SHA-256 `eb42537a6c7e2f7f354388a6393eb81f12be73b2def0dc6b81101a70cabbffba`。
- 从父研究修复后 manifest 运行开发：84 episodes、3,131 active、base/stress +40.98%/+27.54%，但 episode 中位数 -0.219%、胜率 13.10%、最大回撤 -11.94%；`qualify-development` 输出 `FAILED_DEVELOPMENT_GATE_STOP`。没有下载 evaluation/confirmation。
- 重跑到外部 `repro-development.json` / `repro-selection.json`，两项内容摘要与保留结果一致。
