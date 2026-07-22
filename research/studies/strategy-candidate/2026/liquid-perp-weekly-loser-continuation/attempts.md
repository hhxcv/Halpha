# 实际尝试与失败记录

## 2026-07-22 开题

- 在问题一低量日级反转 `DOES_NOT_SUPPORT`、问题二 TRX 永续一次性适配 `INSUFFICIENT_EVIDENCE` 后，重新扫描本地 predictive、trend、carry、cross-sectional、calendar 和相关性研究，排除相同机制调参。
- 联网查阅短期 crypto momentum 的同行评审研究、size/liquidity 分层工作论文、JOF crypto factor 研究、季节性反证和 Binance/VectorBT 官方文档。
- 选择“高流动固定六币 bottom-1 short 一周”，因为外部证据明确把大币周动量定位到 short loser 腿，它与当前一次性计划的 instrument/direction/amount 人工固定流程相容；没有因容易或预期指标漂亮而选。
- 在获取本题原始数据或结果前固定对象、0.25 倍、7/7 日、成本、funding 压力、市场基准、相对选择统计和顺序门。

## 2026-07-22 获取与数据质量

- 通过 Binance USD-M 公开接口获取六个固定合约的日线、settled funding 和官方 8 小时 mark-price kline；没有使用凭据、产品数据库或运行配置。
- 六币各保留 1,654 根连续日线与 4,962 条 funding 记录。原 funding 响应中缺少的 mark price 均按 `fundingTime` 与官方 8 小时 mark close 匹配，最大时间误差 48 ms；质量门通过后才允许查看经济结果。
- Git 外缓存固定为 `D:/projects/Codex/CodexHome/research-data/halpha/liquid-perp-weekly-loser-continuation/2026-07-22-v1/`，共 66 个原始文件、7,669,925 bytes。`source_manifest.json` 保存 URL 参数、时间边界、SHA-256 和本地身份。

## 2026-07-22 开发阶段

- 主规则生成 104 个互不重叠的周计划、2,184 个 funding 事件；选择次数为 BTC 10、ETH 7、BNB 13、XRP 19、DOGE 30、ADA 25。
- 手算逐计划收益与 VectorBT 固定数量 short 复核，最大差异 `6.94e-17`。
- favorable/base/stress 复合收益分别为 -15.04%/-19.38%/-29.00%；base 最大日级回撤 -41.82%。即使较有利成本也亏损，失败不能归因于单一保守滑点假设。
- 开发期 gross short 价格腿复合 -21.46%；实际 funding 的算术贡献 +10.70%，只能减轻、不能逆转价格腿亏损。base 的价格与显式交易成本算术合计 -26.76%，加入 funding 后仍为 -16.06%。
- 2021 base -35.74%，2022 +25.46%，显示其更接近方向性熊市 short，而不是跨 regime 的长期候选。
- 相对六币等权 short 的 gross selection return 平均 +0.434%/周，但 4 周 bootstrap 95% 区间为 [-0.138%, +1.114%]，不能排除零。等权 short base -50.50%，所以排名确实改善相对结果，却没有形成可交易的绝对净收益。
- 预注册诊断均未救回：14 日 formation base -19.45%，bottom-2 base -24.28%；固定 BTC short 虽 base +3.38%，stress -6.75%、扣 4% 年化门槛后 -4.40%，且不属于选币 Alpha。
- 开发门失败后严格停止，没有读取 evaluation/confirmation 经济结果，也没有换方向、币种、持有期或成本追参。结论固定为 `DOES_NOT_SUPPORT`。

## 2026-07-22 重演与封存

- 重复运行 development analyze/gate，稳定交易 CSV SHA-256 为 `5364f5d672da25e0a0c75f888d69d774d14c97bfbb649a9c05a4b5d8502a4ed0`。
- 固定赢家/输家多腿市场中性表达没有从本题结果中事后派生；它改变产品闭环、同步执行和资金占用，若以后研究必须作为独立问题重新预注册。
