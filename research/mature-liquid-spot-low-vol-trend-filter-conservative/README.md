# 保守仓位的成熟流动币低波动 + 正趋势研究

问题：固定 13 个 Binance 现货成熟流动币中，每月选择 90 日已实现波动最低的 3 个、仅持有自身 90 日收益为正者，每币 0.1、总仓位最多 0.3，能否在顺序隔离的评估与确认阶段，在 16bp 基准及 26bp 压力成本下取得正收益，并把风险控制在面向个人小资金的预注册边界内？

- 稳定基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`。
- 正式策略身份：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0`、`BTCUSDT-PERP`；仅是固定背景，未做不可比的多资产现货 activation replay。
- 候选身份：`RESEARCH_MATURE_LIQUID_SPOT_LOW_VOL_POSITIVE_TREND_90D_0P3X`。
- 范围：研究候选，不改产品策略、L4、资金或真实账户。

数据、命令、实际开窗、结果、限制与重演信息会随顺序门运行追加。本目录保留未来避免重复研究所需的规则身份、来源、数据身份、代码、所有门和重要结果；大型公开数据放在 `D:/projects/Codex/CodexHome/research-data/halpha/mature-liquid-spot-low-vol-trend-filter-conservative/`。

## 结果

结论：`INSUFFICIENT_EVIDENCE`。

开发校准虽有 +95.88% base 收益、+95.19% stress 收益和 -21.27% 最大回撤，但相对同仓位无趋势版本仅改善 1.7088pp，未达到预注册 2pp，因此在获取任何新 holdout 前停止。正收益不能抵消风险差异门失败，也不能证明 Alpha；当前证据不支持把该仓位缩放版本列为已通过候选。

开发 manifest SHA-256 为 `b8ab9b7b7d2573865026185ab7ed00d484d538df3de6e658b14562bc5538b7ed`，内容身份为 `ddbef4626a3ef10340ce9e352f3bd08a447c3591ec1bb4f418549148ebcc5799`。开发/门内容摘要为 `9543d3d8a5f8ae91503d80bd0becb35ef37d08cb1d05dfec95a3fb7d8d7fbc21` / `95679446d621944becd988c18bed2f3ca97eddb2b2431e818e674f43ec438e12`。Git 外重演目录 `D:/projects/Codex/CodexHome/research-data/halpha/mature-liquid-spot-low-vol-trend-filter-conservative-repro/` 有 2 文件、22,759 bytes，摘要全部一致。
