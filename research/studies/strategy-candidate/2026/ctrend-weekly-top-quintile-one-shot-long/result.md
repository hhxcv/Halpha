# 结果：CTREND 单腿 one-shot 转换未通过开发门

## 结论

`INSUFFICIENT_EVIDENCE`

固定的 28 信号、52 周 CS-C-ENet、顶部五分位、`0.5x LONG / 7d` 转换在 2023 development 没有通过全部现实成本、统计、基准、稳健性、广度与风险门。它不进入 evaluation/confirmation，不生成交易核心 handoff，也不修改正式策略、产品代码、资金或真实账户。

## 关键数值

- 交易 / entry dates / 目标：`153 / 42 / 24`。
- base / stress 扣 4% 全计划资本周门槛均值：`1.283615% / 1.114626%`。
- stress 四周 block-bootstrap 95% 区间：`[-0.469088%, 2.893281%]`。
- base date-portfolio 最大回撤：`-17.908274%`。
- gross 相对同周等权市场均值：`0.761091%`；95% 区间 `[0.025969%, 1.721565%]`。
- 每周入选特征中位数：`12.0`；模型失败比例 `19.231%`。
- 失败门：`minimum_45_entry_dates, model_failure_fraction_at_most_5pct, stress_bootstrap_lower_positive, largest_positive_pnl_share_at_most_20pct`。

## 解释边界

本结果只判断 Halpha 的当前幸存永续、成交额代理权重、固定单目标、零售成本和 one-shot 转换；不推翻原论文的全市场、多币、市值加权 long-short 因子。正收益也不会证明长期 Alpha；如果主要收益能由 MOM21、单均线或市场 beta 解释，就没有相对正式 Donchian 的独立项目价值。

evaluation 和 confirmation 未打开。所有模型元数据、交易 CSV、数据身份、失败门和尝试均保留，禁止从诊断中事后挑选新的主规则。
