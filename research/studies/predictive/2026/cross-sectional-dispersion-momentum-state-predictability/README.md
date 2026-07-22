# 横截面分散度能否事前识别加密动量失效

## 状态与范围

- 主要类型：`PREDICTIVE`
- 稳定产品基准：Git `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`
- 当前结论：尚未运行 development；checkpoint 前不得计算本题条件结果。

问题：在固定成熟 Binance USD-M 目标中，决策日前一天的横截面日收益分散度相对其历史扩展中位数升高时，20 日横截面动量的下一周 top-minus-bottom 收益是否显著变弱；低分散状态能否提供足以进入现实成本策略研究的单腿 top-long 毛空间？

本题只做预测交互门。通过才允许另开策略题，用 VectorBT、实际 funding、fee、spread/slippage、计划金额、冷却和框架无关决策轨迹验证。它不会因为状态变量使局部均值变好就直接生成 handoff。

## 与已有研究的差异

- `persistent-up-state-weekly-winner-long` 检验市场连续上涨状态；本题使用跨币“同一天彼此分化程度”，并在回归中控制等权市场波动和平均相关性。
- `risk-adjusted-two-week-momentum-one-shot-long`、`category-momentum-gated-one-shot-long` 和短周期 RMOM 已失败；本题不改变它们的信号方向来救结果，只检验 2026 年外部研究提出的独立失效状态。
- 来源论文使用动态 CoinGecko top-500、日频 long-short、多资产权重；本题是固定当前成熟永续、周频、未来可能映射为 top-long 半自动计划的透明适配，不声称复现论文业绩。

## 数据与留存

- development：2022–2023；evaluation：2024，仅 development 全门通过才解封。
- Git 外原始数据不复制；复用身份由 `source_reuse_manifest.json` 和父研究 manifest 链固定。
- Git 内保留每日状态、逐周排序结果、逐币 panel、JSON 结果、gate、尝试和所有 SHA-256。

不读取产品业务数据、数据库、凭据或运行配置，不启动产品运行时，不调用交易所变更端点，不产生真实交易动作。
