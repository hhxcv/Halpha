# 实际尝试与失败记录

## 2026-07-20 预注册

- 确认正式策略为 BTCUSDT-PERP Donchian/ATR 后，选定 BTC/ETH 现货双动量作为候选比较，不把它描述为完全不同的方向风险。
- 联网核对 time-series momentum、现实 crypto momentum 与 momentum crash 原始研究；固定两币、90 日主规则、60/180 日邻域、0.5x、月频、成本、基准和三阶段门。未先运行规则。
- 代码通过 `python -m py_compile`；启封前 SHA-256 `eb0aedbed2b4fff7561b7f05e45c4de71b07eb43f1324aa07afddc4facbfcdae`。
- 获取 60 个 checksum 验证归档、0 补数；开发 90 日 base +31.22%、最大回撤 -42.64%，60 日 -4.61%，`qualify-development` 输出 `FAILED_DEVELOPMENT_GATE_STOP`。没有下载 evaluation/confirmation。
- 重跑到外部 `repro-development.json` / `repro-selection.json`，内容摘要分别一致：`e9211438687416670d8b4bb870ba3d86cff1158631151aac2de14328f66e50ef`、`a19460946bf0bcdef9988454f9b90375f3e239ccd3c86de29bbe5276861e0fa2`。
