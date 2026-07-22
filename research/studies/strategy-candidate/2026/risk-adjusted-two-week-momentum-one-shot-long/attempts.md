# 尝试与失败记录

## 2026-07-22 开题前筛选

- 查重覆盖 legacy 与当前四类研究。累计动量、MAX、高/低波、类别动量、UP–UP winner、CTREND、funding/premium、BTC lead-lag/residual reversal 和 15 分钟边界订单流均已有结果；不再重开这些近邻。
- 对照 2024 正式 RMOM 因子论文、2026 anomaly 压缩、2025 momentum 反证和 2024 size/volume 异质性研究。RMOM2 是少数仍有直接原始方法、只需基础数据且能明确击败 raw momentum/low-vol 才有项目价值的候选。
- 公开会议 PDF 已保存到 Git 外来源缓存并核对 SHA-256；没有查看任何 Halpha RMOM2 排名、交易或收益。
- 只注册一个主配置。`RMOM7`、`RMOM21`、top3、raw MOM14、LOWVOL14、定时做多和市场仅为不可选择反证。

后续 prepare、运行失败、任何 amendment、逐笔结果、门控和重演均在此追加，不覆盖旧记录。

## 2026-07-22 prepare 首次失败与 Amendment 001

- checkpoint 后首次 `prepare --stage development` 为 FAIL；当时尚未计算 RMOM2 排名、交易或收益。
- 所有 25 个标的均显示 397 行和恰好 7 个尾端“缺日”，OHLC、重复和 funding 均正常。核对计划时序发现，最后一个 development 入场为 2023-12-25，七日退出只需要 2024-01-01；完整性检查却误要求至 2024-01-08。
- Amendment 001 只把 DQ 必需终点从 2024-01-08 改为真实最后退出日 2024-01-01，并允许检查点验证该编号修订。它不改变 development 入口、信号、目标、排名、成本、funding、冷却、比较或结论门。

## 2026-07-22 analyze 首次失败与 Amendment 002

- 首次 `analyze --stage development` 在八份逐笔交易 CSV 已写出、但 `development.json` 和任何汇总/门控尚未生成时失败；因此逐笔结果已暴露，不能再称运行前状态。
- 失败是 `LOWVOL14` 在 2023-09-11 因预注册的一日冷却规则没有任何计划，而主规则当天有计划；复用比较函数要求基准在主规则每个入场日都存在，抛出 `baseline missing a main entry date`。
- 预注册已经固定“冷却中输出零个提议”。Amendment 002 将这种基准无行动日按全计划现金收益 0 对齐，同时保留共同日期均值和无行动日期数量；同一规则对 MOM14、LOWVOL14 和 SCHEDULED_LONG 全部使用，不删除主规则日期、不改信号、成本、冷却或通过门。
- Amendment 002 同时把检查点验证改成编号修订链，要求每个 amendment 的原始/修订代码 hash 连续、经济规则未变且最终代码 hash 精确匹配。

## 2026-07-22 development 结果与失败门

- Amendment 002 后首次完整成功运行产生 171 笔计划、51 个入场日、25 个实际入选标的。base / stress 扣除 4% 全计划资本周门槛后的日期组合均值为 `+0.897120% / +0.718402%`。
- 结果触发 `DOES_NOT_SUPPORT`，因为 RMOM2 相对 MOM14 的 base 均值差为 `-0.076820%`；两者每周横截面 Spearman 中位数 `0.9130`，说明风险调整在当前名单上大多只是同一动量排序的近邻，且没有增量经济价值。
- stress 四周 block-bootstrap 95% 区间为 `[-0.746390%, +2.431882%]`，下界不正；gross 相对同周等权市场差 `+0.191784%`，但区间 `[-0.652815%, +1.269705%]` 同样跨零。
- base 日期组合最大回撤 `-26.420936%`，超过 -20% 门；2023 上半/下半扣门均值分别为 `-0.098471% / +1.854419%`，时间一致性失败；最大正 PnL 标的贡献 `23.8467%`，超过 20%。
- 有利诊断完整保留：RMOM7、RMOM21、top3 的 stress 扣门均值分别为 `+0.094995% / +0.978088% / +0.449938%`；主规则优于 LOWVOL14 和 SCHEDULED_LONG。它们不可被改选，且不能推翻主规则不胜 MOM14、置信区间和风险门失败。
- 六个失败门为：`stress_bootstrap_lower_positive`、`both_halves_base_positive`、`date_portfolio_drawdown_above_minus_20pct`、`base_beats_mom14`、`gross_excess_bootstrap_lower_positive`、`largest_positive_pnl_share_at_most_20pct`。
- development 失败后没有打开 evaluation/confirmation，也没有生成策略 handoff。

## 2026-07-22 完整重演

- 使用同一 checkpoint、Amendment 001/002、复用数据身份和命令完整重跑；171 笔计划、所有关键数值及稳定 development 摘要 `4655fbf7ebfe31c53e8d0d6d9cebe0f8267b93453f2456db5c968ab0a25d8cd1` 完全一致。
- 八份逐笔交易 CSV 的 SHA-256 全部与首次成功运行一致；逐文件哈希保存在 `development.json`。
- 本题的新 stable digest 明确排除 `created_at_utc`/`validated_at_utc`，因此重跑摘要不再因生成时间漂移；经济内容仍逐字段纳入摘要。
- 重跑 gate 的六个失败门完全一致；`validate` 通过 6 个 JSON 稳定摘要、8 个交易 CSV、检查点、连续 amendment 链和“无后续阶段产物”检查。
