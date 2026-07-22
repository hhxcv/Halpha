# 尝试与失败记录

## 2026-07-22 开题前筛选

- 核对正式 CTREND 论文、官方 online appendix、正式 DOI、样本、28 指标、52 周 CS-C-ENet、成本和大/流动币稳健性。
- 核对异常成交量、日历、salience 与 8–10 周反转候选。异常成交量机制在可做空后消失；日历收益缺少近期稳健性；salience 集中微盘；中盘高波反转不符合当前低风险单腿优先级。
- 本地 `rg` 查重未发现既有 CTREND/elastic-net 研究。既有 `category-momentum`、`MAX28`、premium、BTC lead-lag/residual 和 UP–UP winner 都未计算本题 28 信号聚合输出。
- 决定只注册一个主配置；26/78 周、无 volume 和 naive combination 仅为不可选择反证。

## 待追加

所有取数、解析、模型、运行时、门控失败和任何仅修复实现的 amendment 将在此按发生顺序追加，不覆盖旧记录。

## 2026-07-22 prepare 首次失败与 Amendment 001

- checkpoint 后首次 `prepare --stage development` 成功补取 25 个早期日线文件，但 `data_quality_development.json` 为 FAIL。
- 逐标的检查确认日线无内部缺日、OHLC 合法；失败只因所有 25 个标的在 `2023-02-24 00:00/08:00/16:00 UTC` 的 funding 记录缺少可匹配官方 mark，共每标的三项。
- 这是上游已留存研究也遇到的同源缺口。预注册明确要求“mark 缺失的整笔交易排除，排除机会比例不得超过 2%”，没有要求只要存在单个 mark 缺口就否决所有行情。
- 因此首次实现把 `missing_marks == 0` 放入数据质量 PASS 是实现错误。Amendment 001 只把 mark 缺口从 OHLCV 完整性 FAIL 条件移到既定交易排除与 2% gate；不插值、不按零、不用成交价替代，不改变信号、模型、对象、时间、成本或结论门。
- 首次失败发生在任何 CTREND 模型或收益输出之前；当时不存在 `development.json` 或交易 CSV。

## 2026-07-22 development 实际运行与失败门

- Amendment 001 后，`prepare --stage development` 通过：25 个标的的公开日线补充文件均可解析，28 个预注册指标及 41 个固定 ElasticNet alpha 可构造；缺失 mark 仍按预注册规则排除，不插值。
- 首次 `analyze --stage development` 用时 225.1 秒，产生 153 笔 one-shot 计划、42 个入场日、24 个实际入选标的。base / stress 扣除 4% 全计划资本周门槛后的入场日组合均值为 `1.283615% / 1.114626%`。
- `gate --stage development` 为 FAIL。四个失败门为：入场日少于 45；52 个候选周中 10 周未选出任何正预测分量，模型失败率 `19.231%` 高于 5%；stress 四周 block-bootstrap 95% 区间为 `[-0.469088%, 2.893281%]`，下界不为正；最大正 PnL 标的贡献占比 `23.415%` 高于 20%。
- 有利反证也完整保留：两个时间半段的 base 均值均为正；相对同周等权市场的 gross 均值差为 `0.761091%`，95% 区间 `[0.025969%, 1.721565%]`；主结果超过 MOM21、SMA20 和定时做多基准。这些证据不足以越过上述四个失败门。
- 因 development 未通过，未运行 evaluation 或 confirmation，未生成策略交接包。

## 2026-07-22 完整重演

- 使用同一 checkpoint、代码、公开数据身份和命令第二次完整运行 `analyze --stage development`，用时 229.3 秒。153 笔计划及 base/stress 关键数值与首次完全一致。
- 九份逐笔交易 CSV 的 SHA-256 全部与首次一致，覆盖 main、market、MOM21、SMA20、scheduled-long、26/78 周、no-volume 和 naive-all。
- `development.json` 的 `content_digest` 从 `df0d82cf…` 变为 `2e22b61e…`，定位为当前摘要把每次运行的 `created_at_utc` 纳入哈希；这不是逐笔交易或数值漂移。重演主证据因此以逐笔 CSV 哈希与关键数值一致为准，该元数据局限明确保留。
- 重跑 gate 后，四个失败门完全一致；`validate` 通过 6 个 JSON 内部摘要、9 个交易 CSV 哈希、checkpoint/amendment 链以及“无后续阶段产物”检查。
