# 先行调研与数据来源

访问时间均为 `2026-07-22`。优先记录原始论文、作者/学校页面、交易场所官方资料和框架官方文档；无法取得全文的 2026 工作论文只按摘要使用，不补猜方法细节。

## 直接方法先验

1. Victoria Dobrynskaya, *Cryptocurrency Momentum and Reversal*, Journal of Alternative Investments 26(1), 65–76 (2023), DOI `10.3905/jai.2023.1.189`。
   - HSE 正式出版记录：https://publications.hse.ru/en/articles/811744977
   - HSE 作者会议全文：https://conference.hse.ru/files/download_file_ex?hash=FAE0AB2DC7A67656E89A0B1CB27D8C7D&id=3B5EE9A5-0B18-458A-9458-B4ED0F6C6664
   - Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/_sources/cryptocurrency-momentum-reversal-dobrynskaya-hse.pdf`
   - 缓存身份：547,976 bytes；SHA-256 `a97eeda242f1ba863ed4006a7f0854d5356cf80d84adda697ae1eeb183d839b6`。
   - 论文边界：2014–2020，约 2,000 个市值超过 100 万美元的加密资产，CoinMarketCap 聚合周数据；按过去 J 周收益把底部/顶部 30% 组成市值加权 loser/winner 组合，持有 K 周，K>1 时使用重叠组合。
   - 与本题相关：短期 1–4 周较像动量，较长形成期转为反转；J/1 在约 10–12 周附近出现负 winner-minus-loser，长期反转主要由 past loser 长腿上升推动。论文的广泛、point-in-time、组合分散和市值权重均未被本题复制。

2. Patrick Kiefer and Michael Nowotny, *Reversal in Cryptocurrency Returns*, SSRN `6703978`, posted 2026-05-03, revised 2026-06-01。
   - 原始摘要页：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6703978
   - 摘要称使用 Binance USDT spot 2021–2026、mark-to-next delisting accounting，在 8–10 周形成期发现 loser-minus-winner 反转，并报告高波动/去大币、不同分组、skip、inverse-vol、时间子样本和 circular block bootstrap 稳健性。
   - 限制：工作论文、非同行评审；本次无法可靠取得完整 PDF，未用摘要之外的持有期、成本或实现细节决定主规则。它只把 10 周设为外部先验之一，不能充当本题独立验证。

3. Steven Kozlowski, Michael Puleo, Jizhou Zhou, *Cryptocurrency Return Reversals*, Applied Economics Letters 28(11), 887–893 (2021), SSRN `4256709`。
   - 原始作者稿摘要页：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4256709
   - 200 个币、2015–2019，报告日/周/月再平衡反转，并检验 size、turnover、illiquidity 与子样本；提示反转可能与流动性补偿和小币有关。
   - 适用性：支持“反转不是只在一篇论文出现”的先验，但其全市场小币、现货和旧时期与当前固定高流动性永续名单差异很大。

## 反证和不一致证据

- Halpha 已完成的短周期输家 continuation/reversal、低量日反转、MAX、premium/funding、低/高波动与 CTREND 研究并未产生可直接替代当前核心的稳健候选；因此本题不能把“反转文献”当作自动成立。
- 2026 工作论文的结果与旧论文同方向，但时间样本与本研究 2022–2025 重叠；这里的“顺序证据”是 Halpha 规则内部未查看的阶段，不是文献发表后的全新市场样本。
- 固定 current-survivor 名单可能高估 past losers 的回升，因为失败/退市资产不在历史横截面。只允许把结果解释为当前固定名单的条件资格证据。

## 市场数据

- Binance USD-M 公共 REST 日 K 线和 Binance Data Collection 官方 monthly funding/markPriceKlines archives；无 API key、无账户、无下单端点。
- 官方开发者入口：https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/Introduction
- 官方公开数据站：https://data.binance.vision/
- 本题复用三个既有、带 SHA-256 的 Git 外公开缓存清单；`source_reuse_manifest.json` 在 checkpoint 时绑定清单、数据质量文件、加载器和论文缓存身份。加载时逐文件核对 bytes/SHA-256，重复区间还核对 OHLCV 一致性。

未使用：产品数据库、账户数据、真实成交、L2、OI、liquidation、新闻/情绪、链上、点时市值/退市历史。它们并非“发现 Alpha 的必要充分条件”，但本题因此不能识别机制、盘口可成交性或全市场退市偏差。

## 研究框架

- VectorBT `Portfolio.from_orders`：https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders
- pandas/numpy 负责确定性面板、分组和 bootstrap；无参数优化器、研究数据库、服务或调度器。
- 价格成本由 VectorBT 与独立逐笔公式双算；funding 以官方事件/mark cash flow 单独加入。框架只负责计算，不替代经济规则、时间封印或结论门。
