# 结果：15 分钟 realized variance 与下一周收益

## 结论

`DOES_NOT_SUPPORT`

development predictive gate failed; later stages and strategy conversion sealed。本题不生成交易核心 handoff，不修改正式策略、产品代码、L4、资金或真实账户。

## development 证据

- 有效周 / panel 行：`58 / 1398`。
- RV28 high-minus-low：`-0.103937%/周`，四周 block-bootstrap 95% 区间 `[-1.547735%, 1.552344%]`。
- rank IC：`-0.099271`，负向单侧 HAC p=`0.010887`。
- 控制日线波动、MOM、MAX、beta、volume 后 RV28 系数：`0.600563%`，负向单侧 HAC p=`0.860349`。
- 高 RV 单目标 SHORT 压力成本与完整资本门后粗代理：`-0.408450%/周`，95% 区间 `[-1.571756%, 0.509944%]`。
- 相对日线 DVOL28 高波 SHORT 增量：`-0.373716%/周`，95% 区间 `[-1.142010%, 0.214505%]`。
- 失败硬门：`spread_bootstrap_upper_negative, spread_negative_fraction, controlled_rv_negative, controlled_rv_negative_significant, proxy_mean_positive, proxy_bootstrap_lower_positive, increment_vs_dvol_positive, increment_vs_dvol_bootstrap_lower_positive, both_halves_positive, all_calendar_years_positive, all_neighbors_directional`。

## 解释边界

论文中的 100 个 spot、含小型/低流动币的宽组合结果不能直接代表当前 25 个成熟永续。预测题的粗代理没有 funding、盘口、排队、部分成交、保证金和人工激活路径；即使方向为正，也不能据此称为 Alpha 或长期盈利。后段是否开放严格由顺序 gate 决定。

## 复现

命令见 `README.md`。数据使用 Binance 官方公开 archive；development 复用 Git 外缓存并逐文件验证官方 checksum、本地 SHA-256 与字节数。`validation.json` 保存冻结文件、结果和 CSV 身份校验。
