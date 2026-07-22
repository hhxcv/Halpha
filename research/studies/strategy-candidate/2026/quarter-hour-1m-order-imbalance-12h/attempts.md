# 实际尝试与失败记录

## 2026-07-22 选题与预注册

- 在三项新策略题均未达到交付门槛后，扫描本地 predictive、trend、carry、cross-sectional 和 prior strategy families，停止继续 BTC lead-lag、日级 reversal、周级 loser 或 TRX 波动目标的近邻参数搜索。
- 联网核对 2026-07-16 的原始 quarter-hour 论文、Binance 官方公共 archive/字段/checksum、funding/mark 文档和 VectorBT 官方接口。
- 2025-01 的官方 archive HEAD 显示 BTC/ETH aggTrades 压缩包约 692/731 MB，而 BTC 1m Kline 约 1.92 MB。为符合个人长期维护和项目资源边界，选定可交付的 1m taker-volume 代理，不下载数十 GB 逐笔全样本；这一选择在经济结果前完成。
- 固定六币、两个非重叠时隙、60 观测四分位、12h、0.25 倍、成本/funding 压力、三个反证、全新时间段和顺序门。尚未获取或查看本题经济结果。

## 2026-07-22 获取与质量门

- 下载 2024-10 至 2026-06 的六币官方 USD-M 1m Kline 月包及逐包 `.CHECKSUM`，并通过公共 REST 获取 funding 与 8h mark-price kline。manifest 共 276 个文件、224,723,759 bytes，全部位于 Git 外缓存。
- 六币各得到 918,720 根连续分钟 bar；预定区间分钟缺口、额外分钟、OHLC 非法、taker-buy quote volume 越界均为 0。funding rate/mark 无缺失，最大 funding 间隔未越过质量门。
- 只在 manifest 哈希和 `data_quality.json=PASS` 后运行经济分析；没有读取产品数据、凭据、账户或运行配置。

## 2026-07-22 开发阶段

- 固定主规则产生 1,464 笔：741 LONG、723 SHORT、2,217 个持仓内 funding 事件。VectorBT 与独立手算最大差异 `8.85e-17`。
- gross 时隙均值为 -0.00161%，8 日 block-bootstrap 95% `[-0.03057%, +0.02685%]`；gross 复合收益 -1.02%。方向本身没有显示正预测价值。
- favorable/base/stress 复合收益 -8.03%/-18.60%/-28.21%；base 最大时隙权益回撤 -18.99%。六币 base 全负，八个月 base 也全负。
- 算术归因按六个等权 sleeve：gross -0.76%，实际 funding -0.02%，favorable/base/stress 的价格与显式交易成本为 -8.08%/-20.28%/-32.49%。高换手成本很大，但 gross 本身也不是正的。
- 主规则相对 +7 分钟伪边界的 base 时隙均值差为 +0.00801%，相对 6h 价格动量为 +0.00136%；两者 bootstrap 区间均跨零，不能证明 quarter-hour 特异增量。
- 额外等待 5 分钟的 favorable/base/stress 为 -9.10%/-19.54%/-29.04%，没有隐藏的可执行延迟余量。
- 开发门失败后严格停止；未打开 2025H2 evaluation 或 2026H1 confirmation，未选择币、月份、分钟、阈值或持有期救回。结论为 `DOES_NOT_SUPPORT`。

## 2026-07-22 事后全库查重与流程纠正

- 封存前扩大检索到全部 `research/studies/**`，发现 07:37 已存在、未跟踪的 `predictive/2026/quarter-hour-kline-order-flow-predictability/`。该题用 BNB/LINK/UNI/FIL 的 2021–2022 development、完整四个 quarter-hour 和回归控制，已经得到 `DOES_NOT_SUPPORT`，并明确不建议进入策略层成本计算。
- 本题 09:25 才创建。开题时“扫描本地 predictive”的记录不完整：只依赖了旧 BTC predictive 审计与 strategy-candidate 搜索，没有列举这个新目录。这违反避免重复研究的流程目标，但不改变本题固定数据、实现或数值结果。
- 本题与父预测题仍有增量差异：对象改为论文六币，时间为论文结束后的 2024-11 至 2025-06，固定两个非重叠时隙，并加入实际 funding、三档成本、VectorBT、唯一组合权益和计划语义。因此保留全部数据与结果作为依赖性策略层反证，不删除、不伪装成独立问题。
- 后续选题必须在联网调研前后各运行一次全库问题指纹查重，至少覆盖 research kind、信号数据、formation/decision/entry/hold、对象、机制、父子证据和结论；未跟踪目录同样纳入。相同机制只有存在预先说明的决策增量才允许作为依赖性复核。
