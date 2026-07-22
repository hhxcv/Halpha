# 实际尝试、失败与重放记录

日期均为 2026-07-22。本文只追加研究过程证据；冻结的经济问题、规则与门槛由 `checkpoint.json`、`preregistration.md` 和 `study.py` 的摘要链约束。

## 开题前检索与候选筛选

1. 先查重既有 funding settlement、premium、carry、日内反转、周频 momentum/MAX/CTREND/RMOM 研究。资金费结算后分钟级方向反转没有足够原始证据，而且需要一天多次准点执行，不符合当前半自动策略计划节奏，因此没有开题。
2. 阅读 Fičura 官方全文，核对 `hmom(t,h)=ln(C_t/H_t,h)`、大且流动组的 Q1 风险调整负 alpha，以及论文所说的实际利用依赖做空 Q1；由此选择 `HMOM7` bottom-quintile SHORT 作为唯一主问题。
3. 官方 FFA PDF 保存到 Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/_sources/impact-size-volume-crypto-momentum-reversal-ffa-2023.pdf`，1,119,244 bytes，SHA-256 `9ab18a94116097711fd68c243784df4b70d048421bb03bd433589c19ae232417`。SSRN 直接下载遇到 Cloudflare challenge，未持久化不完整响应；改用作者机构官方 PDF。
4. 复用既有、已冻结身份的官方 Binance 公开缓存，不复制大型输入进 Git。`source_reuse_manifest.json` 递归引用父研究的公开 OHLCV、funding、mark-price 清单、代码与校验身份。

## 冻结前实现检查

实际运行：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' self-test
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' checkpoint
```

结果：

- HMOM 定义/排序自测 PASS。
- SHORT 的 VectorBT 固定两单与手工现金流自测 PASS，误差约 `2.08e-17`。
- checkpoint digest：`7f8290b894b72a1fb94c7df0d1d6c9268490a276d122f358bca5c02c15b0b1df`。
- checkpoint 前未查看 25 个目标的 HMOM 排名、计划交易或收益结果。

## 首次数据质量失败与 amendment-001

首次运行：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' prepare --stage development
```

首次 `data_quality_development.json` 为 FAIL。完整性代码错误地要求每个目标覆盖到 `2024-01-08`，导致 25 个目标各报七个尾部缺失日；但 development 最后入场是 `2023-12-25`，最后退出已经是 `2024-01-01`。OHLC 校验、funding 数量和经济输入未显示失败；当时没有运行 `analyze`，也没有 HMOM score、trade、return、comparison 或 gate 输出。

保留失败身份并创建 `amendment-001.json`：

- 原 `study.py` SHA-256：`dda1a8dce0ff5c86fc1248a8f395603b459e5023768f065ecd179812039e262b`；
- 修正后 SHA-256：`b83913aad0a6874fde39e22760f7d5c178faa75b428935ded0fdd95736d53a5b`；
- 首次失败 DQ digest：`4e72f764f71a1a9a735143faf7e3fcf018a5393d23496bb3e79285d3bd083622`；
- amendment content digest：`26c1329e8fec3cb9c4675f860777649cb2a4abeb5d2253fd19deb92c341093d2`。

修正仅把 DQ required end 改成实际最后退出日。信号、名单、交易、成本、funding、统计、门和结论逻辑均未改变。

## 顺序运行与停止

修正后的实际命令：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' prepare --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' analyze --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' gate --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' validate
```

结果：

- DQ PASS：25 个目标；
- development：193 trades，base/stress 扣门日期均值 `-0.946533%/-1.123430%`；
- gate FAIL：13 个门失败；
- conclusion：`DOES_NOT_SUPPORT`；
- validate PASS：6 个稳定 JSON、7 个 trade CSV、0 个 evaluation/confirmation/handoff 文件。

按照预注册顺序停止，没有打开 2024 evaluation 或 2025–2026H1 confirmation，也没有查看或挑选诊断配置作为替代主策略。

## 缓存重放

完成结果解释后，使用同一四条 prepare/analyze/gate/validate 命令从冻结缓存重放。重放耗时约 36 秒，输出仍为：25 个目标 DQ PASS、193 trades、相同 base/stress 均值、相同 13 个失败门、`DOES_NOT_SUPPORT`、validation PASS。

稳定 JSON digests：

| 文件 | content digest |
|---|---|
| `source_reuse_manifest.json` | `72f16af5bc422c4a3e31d68db36afb16cf6fb19600d2e2eb61749dc18bde6518` |
| `data_quality_development.json` | `6d8de7640453579ebc3f3c6fc9b60f80367ff0a2e73ac3d2f518f3759d630bd9` |
| `development.json` | `657eb4dc17cd1a214c13b2bdf7d56ffb8cc0052f6affc9fc7ff21e5f2b10b624` |
| `development_gate.json` | `27fad77be1d366101a97e4274beec1811fb026de48aba89b4c6e920b47b019e2` |
| `results.json` | `dda5426841c1a9021acc6d19429966808cbacd5fc2a76a84c661d8355e8829dd` |
| `validation.json` | `2b75b4ff9e555292e264dfb90e81dfe8720f2f9b92bdd09a123772e8d91e0356` |

逐笔 CSV SHA-256：

| 文件 | SHA-256 |
|---|---|
| `development_main_trades.csv` | `c2ecc246813f7452433b997f99d3b148332965ab046baa8251bbbdcaa6866093` |
| `development_hmom14_trades.csv` | `586085cf871edb20e468ca65231245e203e8aae39207315c85abf4c653087fbb` |
| `development_hmom28_trades.csv` | `8c1e22e40b4a6793449b25230da429c4adca2fb9c16685906e642f7090aec9f8` |
| `development_bottom3_trades.csv` | `265e244e20a444e84153b4f29fb89fb80c2e99c836813951f2e51debe1a150a2` |
| `development_mom7_trades.csv` | `0b8ee30cb6313136f4b0002819c7c10a1e6a7c3c31447be86fe46609ffd4dd7e` |
| `development_scheduled_short_trades.csv` | `97ff7070926ecf42d489f29a5457b15de6df1c219af2394e0f4a6be0de07f447` |
| `development_market_short_trades.csv` | `fa46cf5ff108bf8159dd6cb65f3037210ab5653ced1a24883e5ba7d381ea7eb3` |

时间戳不进入稳定 digest；重放后全部摘要与 CSV 哈希保持不变。

## 不能用于救援主问题的观察

- gross 相对市场 short 有 `+0.220104%` 的点估计，但区间跨零，且绝对净收益显著为负；不能只保留相对结果。
- 胜率 `50.259%`、中位数为正，但均值和复利为负；这提示空头挤压尾部，而不是可用的高胜率策略。
- HMOM7 与 MOM7 排序相关不完全，但没有胜过 MOM7；“特征不同”不能替代经济增量。
- 三个预注册邻域均为负；不得另选窗口、bottom 数量、目标名单或后续年份继续优化本题。

任何后续相似研究必须先明确新的经济机制、为何能改变这里暴露的绝对 short、尾部和成本问题，并作为独立问题承担新的多重研究与未见期要求。
