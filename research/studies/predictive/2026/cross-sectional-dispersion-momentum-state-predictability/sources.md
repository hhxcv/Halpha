# 先行调研与候选选择

检索日期：2026-07-22。

## 主要原始研究

1. Zhang & Makgolo (2026), *Cross-Sectional Dispersion and the State Dependence of Cryptocurrency Momentum*, SSRN 6648082。
   - 作者页面：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6648082
   - 使用 contemporaneous CoinGecko top-500 重建动态、存续偏差感知样本；摘要报告 lagged dispersion 在控制 BTC realized volatility 和平均相关后预测后续动量减弱，非线性主要位于高分散尾部。
   - 适用：确定“分散度是动量失效状态而非另一个排名信号”的问题方向。
   - 差异：工作论文、尚非同行评审；动态大样本、市值/成交筛选、日频多资产 long-short 与 Halpha 固定 25 个当前永续、周频单腿目标不同。

2. 论文的公开 QuantConnect/Quantpedia 独立实现说明及源码：
   - https://www.quantconnect.com/terminal/cache/embedded_backtest_c423206646f74c75097459ef437d9b67.html
   - 明确 20 日累计 log return；当日日收益的横截面标准差；`median(dispersion history)/current dispersion`、范围 `[0.10,1.00]` 的 exposure overlay；信号与状态均滞后一日。
   - 只用于核对可见公式和时间顺序。该实现 18,292 笔订单、每日再平衡、2x leverage 和极低 fee，不可移植业绩，也不是原论文作者代码。

3. Han, Kang & Ryu (2024，2026 修订), *Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions*, SSRN 4675565。
   - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565
   - 报告现实约束下横截面动量证据接近不存在，均值不能替代厚尾、清算与净盈利检查。
   - 用作强反证：本题必须同时通过不确定性、经济量级、分期和简单无条件动量基准，不能只报告状态回归显著。

4. Zhang et al. (2025), *State transitions and momentum effect in cryptocurrency market*, Finance Research Letters 86A, 108356。
   - https://www.sciencedirect.com/science/article/pii/S1544612325016101
   - 报告动量集中于 UP–UP 状态。这与本项目已完成的 persistent-up 路线接近，因此不作为新题；它只证明状态依赖有多种竞争解释，本题必须控制共同市场状态。

## 候选比较

- 日历效应：2024 更新研究报告加密季节性不稳、早期效应消失；不选。
- BTC/ETH 配对均值回归：两腿、动态 hedge 和退出校准复杂，且已有小时级 BTC-neutral residual 反转否定；保留但优先级低。
- 分散度状态：只需基础日线，能直接解释当前动量家族跨阶段失败，单次研究成本低，若通过可转为“是否创建计划/金额缩放”的半自动决策，因此选中。

## 解释上限

固定幸存目标缺少动态上市/退市和点时市值；等权市场波动替代论文 BTC 波动；周频 top-long 不是日频 long-short。任何通过只支持 Halpha 适配的预测关系，不证明论文复现、可交易 Alpha或长期盈利。
