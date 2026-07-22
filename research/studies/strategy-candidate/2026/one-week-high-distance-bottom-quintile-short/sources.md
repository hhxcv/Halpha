# 来源、访问时间与适用边界

访问日期均为 2026-07-22。

1. Milan Fičura, *Impact of size and volume on cryptocurrency momentum and reversal*, FFA Working Paper 3/2023（2024 修订），[官方工作论文 PDF](https://wp.ffu.vse.cz/pdfs/wps/2023/01/03.pdf)，SSRN 4378429。
   - 原方法：`hmom(t,h)=ln(C_t/H_t,h)`，`H` 为过去 h 周最高盘中价；周末排序、下一周收益；point-in-time 市值和成交额区分大/流动与小/不流动币。
   - 与本题直接相关：2017-06 至 2022-12 的大且流动组，`HMOM1W` Q1/Q5/Q5-Q1 下一周均值为 `-0.70%/+1.98%/+2.68%`；多空 t 值 `4.93`。Q1 的 BTC CAPM/三因子 alpha 为 `-1.95%/-1.79%`，t 值 `-2.72/-3.32`；论文明确称利用主要依赖做空 Q1。
   - 未覆盖：交易成本、永续 funding、Binance 单场所、当前幸存名单、one-shot 冷却、保证金与真实 SHORT 尾部。工作论文不是独立复现，不能当作 Halpha 收益证明。
   - Git 外身份：`D:/projects/Codex/CodexHome/research-data/halpha/_sources/impact-size-volume-crypto-momentum-reversal-ffa-2023.pdf`，1,119,244 bytes，SHA-256 `9ab18a94116097711fd68c243784df4b70d048421bb03bd433589c19ae232417`。
2. George & Hwang, *The 52-Week High and Momentum Investing*, Journal of Finance 59(5), 2004，[DOI](https://doi.org/10.1111/j.1540-6261.2004.00695.x)。这是 high-price anchoring 的原始传统资产方法来源；股票、52 周周期和交易制度不等同于 crypto 一周尺度。
3. Zaremba et al., *Up or down? Short-term reversal, momentum, and liquidity effects in cryptocurrency markets*, IRFA 78 (2021) 101908，[DOI/开放页面](https://doi.org/10.1016/j.irfa.2021.101908)。报告大而可交易币更接近日频 momentum、小而不流动币更接近反转，支持把流动性作为方向边界；不提供本题 HMOM 周规则或永续成本。
4. Liu, Tsyvinski & Wu, *Common Risk Factors in Cryptocurrency*, Journal of Finance 77(2), 2022，[NBER 工作论文](https://www.nber.org/papers/w25882)。报告 market、size、momentum 因子解释横截面收益，并显示 1–4 周 momentum；要求本题比较普通 MOM 与市场，而非把所有 short 盈利称为独立 alpha。
5. Binance Developer Docs，[USD-M Kline/Candlestick Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data) 与 [Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)。官方定义 Kline open time 和 funding history 字段；本题复用已校验公开缓存，不使用账户或凭据。
6. Binance 官方 [binance-public-data](https://github.com/binance/binance-public-data)。说明公开归档、字段、checksum 和历史文件可能修订；manifest 必须保存 URL、bytes 和 SHA-256，重取时不得只凭文件名判断同一输入。
7. VectorBT 官方 [Portfolio.from_orders 文档](https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders)。仅用于固定两单 SHORT 的费用/滑点重演；信号、funding、计划冷却和资格门由最小研究代码补充，不代表 NautilusTrader 或真实撮合。

资金费率结算后方向反转候选另查阅了 He et al. *Fundamentals of Perpetual Futures*（arXiv:2212.06888）与 Binance funding 机制资料。它们支持 funding 对 perp-spot basis 的锚定，不直接证明单腿结算后方向收益；结合本地既有失败研究与人工计划频率，本轮未选择。

