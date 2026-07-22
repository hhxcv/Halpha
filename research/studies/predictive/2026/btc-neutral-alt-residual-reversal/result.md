# Development 结果摘要

## Answer first

`DOES_NOT_SUPPORT`

2024 年固定 1h BTC-neutral residual reversal 的事件均值为 `-10.61 bp`（95% ISO 周 cluster CI `[-34.80,+13.58] bp`），低于同事件 raw reversal `-2.97 bp`，也远低于 paired favorable/base 成本代理 `24.75/66.00 bp`。919 个事件小时虽有 53.86% 正 response 和 +25.78 bp 中位数，但巨大负尾使均值为负，不支持进入 2025 holdout。

## 失效形态

- 相对赢家不是回归而是继续：+residual 侧 reversal -33.74 bp，CI 完全低于零。
- 相对输家侧有 +33.61 bp 的探索性回归，但低于 base 双腿成本且由结果选方向，不能作为新策略结论。
- H1/H2 分别 +2.51/-21.41 bp；z=2 更稳定地反向。
- 1% 事件尾部 -1,437.55 bp，最差 -2,240.44 bp；主要来自 2024 春季和年末 alt 单边行情。
- 9 个固定扰动和 15 币 BY-FDR 没有给出稳健可推广的正结果。

## 数据与复现

- 0 新下载；复用并再校验父题 240 个 Binance 官方 5m ZIP。
- 16 标的各 10,992 个完整 1h bar；1,249 个资产事件。
- 代码 SHA-256：`40234191169a3d8b9a1d5411f885ee2acb3eb4892cd09669e39a2c3a94f502fb`。
- 结果 SHA-256：`cf3eb584e4addcd5b94e8675bef2a9d3725c6dfd774b82b43fba06ce09a46c83`。
- 复用 manifest SHA-256：`452e949107f9d4cc8d0b92d6df6bc2caaf7336472b173c87f5303865d775f663`。

这是预测/机制反证，不包含真实双腿成交、funding、保证金或清算模型，也不授权产品或资金动作。
