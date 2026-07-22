# 先行调研

访问日：2026-07-22。

1. [Binance Public Data 官方仓库](https://github.com/binance/binance-public-data)：USD-M Futures kline 来自 `/fapi/v1/klines`，第 6 列为总 base volume、第 10 列为 taker buy base asset volume；月档案带 checksum 且可能修订。它给出本题代理字段和输入身份，但不证明字段对未来收益有预测力。
2. Cont、Kukanov、Stoikov，[The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)（2010/2014）：在美股订单簿事件上发现短时价格变化与包含限价、撤单和市价事件的 OFI 关系更稳定，而只用成交量更噪声。它提供供需不平衡先验，也构成本题最强方法反证：K 线 taker volume 只是较弱交易流代理，不得称为完整 OFI。
3. Kim、Hansen，[The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures](https://arxiv.org/abs/2607.09426)（2026）：使用六个 Binance 永续逐笔数据，报告 quarter-hour 开始时订单流具有信息含量，符号替代定义结果方向相近，但主要预测跨度为 4–12 小时、在更细跨度较弱。它支持检查方向符号，也反对把两根 1m 聚合直接移植为强信号。
4. Vafin，[Order-Flow Imbalance and Short-Horizon Return Predictability in Cryptocurrency Markets](https://ssrn.com/abstract=6938742)（2026）：综述并明确区分同区间机械价格冲击与未来收益预测，要求样本外、现实成本和搜索披露；文章不报告新实证且作者披露相邻商业利益，因此只用于方法约束，不作为正向经验结果。

外部研究没有直接回答“当前固定 BTCUSDT Donchian/ATR 单次策略，使用两根确认 K 线的 taker-volume 符号过滤后是否成本后转正”。本题必须在 Halpha 固定代理、成本和时间门下自行证伪。
