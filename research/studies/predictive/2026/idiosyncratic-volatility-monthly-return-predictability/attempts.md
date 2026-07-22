# 尝试与失败日志

## 2026-07-22：选题

- 先查重已有总波动率、MAX、momentum、reversal、BTC 相对价值和 tokenized-gold 趋势研究；没有找到一项“IVOL 在控制 TVOL/MAX 后的当代成熟 perpetual 预测”问题。
- 早期广泛币种研究、MAX 解释研究和 2026 非微型币工作论文的结论相互冲突，因此固定为预测题，不在开题时直接选 LONG 或 SHORT 策略。
- 固定月频、90 日主规格、60/120 日邻域、MAX/TVOL/momentum/beta/volume 控制、一日冷却、封存评估期和强制经济余量门。
- 本题只复用已校验的官方公开缓存；不下载、读取或写入产品数据。

## 2026-07-22：checkpoint 前合成自检失败

- 首次 `study.py self-test` 在 pandas 3 解析合成字符串 `2022-01-01Z` 时报 `DateParseError`。失败发生在任何真实数据读取和 checkpoint 生成前。
- 只修复合成 fixture：改为 12 个明确 `T00:00:00Z` UTC 月份，同时让 HAC 自检具有月度时间维度；特征、目标、门和正式时期均未改变。

## 2026-07-22：development 完成并停止

- checkpoint `5ad3356fd2f0724d6e91f2ca8b80c15f77c54adcc1c4ea8e19521ba21777b4e1`。24/24 个月 ACTION，每月最少 21 标的，DQ `PASS`。
- IVOL90 low-minus-high 均值 `+0.949767%/月`，但 3 月 block-bootstrap 95% 区间 `[-5.389805%, +6.695842%]`；不能排除负均值。rank IC 均值 `-0.115377`，区间 `[-0.198869, -0.023633]`，保留为不等于可交易 Alpha 的预测线索。
- 无控制/完整控制 Fama–MacBeth IVOL 系数为 `-0.462469% / -0.336865%`，负向单侧 HAC p 为 `0.369365 / 0.488016`；总波动、MAX、momentum、beta 和 volume 控制后没有显著增量。
- IVOL90 与 TVOL90/MAX28 的月度横截面 Spearman 中位数为 `0.833919 / 0.583577`。TVOL-high 收益减 IVOL-high 收益均值 `-0.092414%`，即 IVOL 并未比简单总波动选出更差的下月对象。
- `0.25x` high-IVOL SHORT 在 52bp 标的层压力往返成本和 4% 全计划资本门后的粗代理为 `-0.515538%/月`。2022 代理 `+2.361057%`，2023 `-3.392133%`；时期外推失败。
- IVOL60/120 的 spread 方向为正、rank IC 方向为负，但 SHORT 代理仍为 `-0.456123%/-0.484199%`；邻域不支持策略转换。
- development gate 因 9 项失败得出 `DOES_NOT_SUPPORT`；2024 evaluation 继续封存，不从结果挑 2022、60 日窗口、ZEC/ZIL 或任何子组重开。
- `study.py validate` 通过：6 个内容摘要 JSON 和 7 个重要 CSV 的 SHA-256 已验证并保留。未新下载数据，全部复用父研究的 Binance 公开 Git 外缓存与身份链。
