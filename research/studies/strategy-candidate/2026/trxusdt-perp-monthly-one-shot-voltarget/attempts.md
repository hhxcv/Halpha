# 实际尝试与失败记录

## 2026-07-22 选题与预注册

- 完整读取当前 AGENTS、`research-halpha` skill、其研究证据参考、当前 ALP/TRADEPLAN L2/L3 与 L4 current plan。
- 扫描现有 TRX 波动目标、TRX 趋势、carry、predictive、BTC Donchian 外部缓存和上一题低相对成交量反转；没有把已经否定的邻近问题换币或换阈值重跑。
- 联网核对波动管理原始支持与反证、永续定价/资金费原始研究、Binance 官方 funding/exchange information 和 VectorBT 官方接口。
- 在查看本题 TRXUSDT 永续结果前固定主规则、成本、funding 压力、阶段和否定门。父现货路径已经暴露，故只把本题定义为合约/计划可移植性，不冒充新价格时间证据。

后续每次数据获取、解析修复、门结果、重演和失败均追加到本文件。

## 首次数据质量失败与输入修复

- checkpoint 后获取 2 页日线、7 页 funding 和 1 份 exchange information。2,100 根日线连续、OHLC 合法；6,298 次 funding 连续，最大间隔约 8 小时。
- 首次 `inspect` 明确失败：官方 funding history 的 6,298 条记录中 3,376 条历史记录没有 `markPrice`。此时没有运行任何收益分析。
- 不用入场价或日收盘猜填。按 Binance 官方 mark-price-kline 接口新增 8h mark price 原始页；以 funding 时间一分钟内最近的 8h mark close 填充官方响应缺失项，保留原字段覆盖数、填充数和最大时间差。
- 这是数据获取/完整性修复，不改变信号、仓位、成本、funding rate、阶段或经济门。代码变更后重新生成 checkpoint 和 source manifest，再运行数据质量检查。
- 第二次检查只剩研究暖启动边界 `2020-10-01 00:00Z` 的第一条 funding 无 mark 匹配，因为首个 8h mark 请求也从同一时点开始；该记录不进入 2021 年后的计划，但仍不放宽质量门。将 mark 请求向前扩一根至 `2020-09-30 16:00Z` 并使用新原始目录，避免覆盖第一次响应；仍未运行收益分析。

## 数据通过、开发结果与顺序停止

- 第三次 checkpoint/source manifest 后质量通过：2,100 根连续日线、6,298 次 funding；2,922 个 mark 来自 funding 响应，3,376 个来自官方 8h mark kline，最大边界匹配时间差 48ms，最终无缺失。
- 运行固定 development：24 个 2021–2022 月度计划、2,191 次持仓内 funding；主 8% 的平均名义比例 0.1064，范围 0.0402–0.2598。
- base +7.63%，日级最大回撤 -9.89%；stress +4.00%，但扣 4% 年化资本门后 -3.85%。唯一失败门为 `stress_after_hurdle_positive`，开发门 `FAIL`。
- 严格停止：未运行 evaluation 和 confirmation；未查看事后 10% 目标作为替代选择，未修改成本、funding 压力、月度强制闭环或门槛。
- 从固定缓存重跑 development/gate 两次，24 个计划、base +7.6263858102%、回撤 -9.8852053056% 和失败项一致；逐计划 CSV SHA-256 两次均为 `8bc1b7407e51b57d77f1ef1bbbcd52f0fc0f1d6a9af15606c4c33bde5c76a3ec`。
- VectorBT 逐计划固定数量订单与独立线性合约价格/成本计算最大误差 `4.16e-17`。当前 manifest 引用 15 个 Git 外文件、2,623,255 bytes；包含两次失败输入尝试的完整缓存共 22 文件、5,390,133 bytes，均保留以解释修复历史。
