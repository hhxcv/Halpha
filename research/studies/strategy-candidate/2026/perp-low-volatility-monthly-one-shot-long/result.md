# 结果：低波动永续单腿有线索但未达到资格门

## 结论

`INSUFFICIENT_EVIDENCE`

在 2022–2023 development 中，`VOL90 / bottom3 / monthly / 0.25x LONG` 的 base 与 stress 月度日期队列扣 4% 全资本门均值分别为 +0.3198% 和 +0.1245%，目标路径风险也受控；但 stress 三月块区间跨零、2022 为负、官方 mark 缺口导致排除比例过高，而且无条件月频 LONG 明显更高。development gate 失败，2024 与 2025–2026H1 未打开，不生成 handoff，不修改产品或交易状态。

结果支持“低波对象相对高波对象更好”这一弱横截面线索，却不支持“低波筛选为用户固定单腿创造胜过简单市场多头的可用 Alpha”。

## 方法与数据

- 基准提交 `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP` 只作背景。
- 25 个当前流动 USD-M 目标；90 个完整日对数收益的年化样本波动率升序，最低三名才触发；至少 20 个目标可排名且 30 日成交额中位数不低于 10m USDT。
- 月首 open 入场 0.25x LONG，下月月首 open 退出；同目标不能连续月份重新激活。
- 实际 settled funding；favorable/base/stress 每边分别为 6/16/26 bp fee+spread/slippage，stress 放大 funding 支出、削减 funding 收益；按实际月长扣 4% 年化全计划资本门。
- 三个 entry-month 循环块、5,000 次 bootstrap；VOL60、VOL120、bottom5 邻域和 HIGHVOL90、MOM90、SCHEDULED_LONG 对照全部保留。
- 运行环境：独立 `research/.venv`，Python 3.13.14、VectorBT 1.1.0；checkpoint 同时锁定环境与方法文件。

manifest 引用 74 个较长暖启动日线页、600 个 funding 月归档、600 个 8h mark 月归档和 57 个 gap-only 1m mark 月归档，连同 checksum 共 2,588 文件、56,511,943 bytes。Git 外共享官方缓存现共 2,835 文件、70,601,364 bytes：

`D:/projects/Codex/CodexHome/research-data/halpha/category-momentum-gated-one-shot-long/2026-07-22-v1/`

关键身份：checkpoint `5db477a87791683afa77ae1c356b3c5211fa33b548fa7451b55858a3b369457d`；source manifest `033504dcebaab0a36efff9038f53db837d38124c1dc8390daba8702d079c79d1`；PASS data quality `a30210187cf850ca7f39f9ea47e36e2050e34a285c0dfcfec0816bdf6517b8a9`；最终 results `18f0f1a7831ef07449008973b8a3b387e8b3fceb6d7266952930cb3b431d118b`。

## 主要证据

| 证据 | 结果 |
|---|---:|
| 交易 / entry months / 目标 / 类别 | 37 / 21 / 7 / 4 |
| 缺失 funding mark 排除 | 4 / 41 = 9.756%（超过 5% 门） |
| favorable / base / stress 日期队列均值 | +0.3703% / +0.3198% / +0.1245% |
| base 95% 区间 | [-0.8886%, +1.5595%] |
| stress 95% 区间 | [-1.0836%, +1.3568%] |
| base 单笔扣门均值 / 胜率 / 中位数 | +0.3761% / 54.05% / +0.8171% |
| 毛价格 / 实际 funding 单笔均值 | +0.6861% / +0.1019% |
| 2022 / 2023 base 日期队列 | -0.9745% / +1.4964% |
| 正目标比例 / 正类别 | 66.67% / 3 |
| 目标中位 / 最差最大回撤 | -4.46% / -18.52% |

低波筛选确实强于两个特征对照：HIGHVOL90 base 为 -0.6173%，MOM90 为 +0.0274%；主低波与高波相差约 +0.9371%/月。VOL60、VOL120 和 bottom5 的 stress 均值也分别为 +0.3535%、+0.3358%、+0.9559%，说明符号不是单一 90 日点估计造成。

但最简单解释更强：SCHEDULED_LONG base/stress 为 +0.8070%/+0.5989%，均高于主规则。低波选择减少风险并避开高波输家，却同时放弃了 development 中更大的普通市场多头收益；不能把正绝对收益全部归因于低波 Alpha。bottom5 事后更高也只是不可择优诊断，不能替换主配置。

## 反证、限制与剩余未知

- stress 区间下界为 -1.0836%/月，样本不能排除负均值；2022/2023 符号相反。
- 四笔跨官方 mark 缺口的计划被整笔排除，比例 9.756%；不对其未知收益作有利填补。
- 目标集中在七个低波对象；虽通过事前 40% 正贡献和回撤门，仍不能代表全部 25 个当前目标。
- 外部论文的关键证据是 spot low-minus-high 多腿组合；本题 long-only 低波单腿仍保留市场 beta，且有 funding 与合约风险。
- 当前幸存者名单不是 point-in-time universe；日线与成本带不包含历史盘口、队列、部分成交、保证金、强平/ADL、人工延迟和场所故障。
- 后段未打开，不能根据 2023 转正或 bottom5 诊断推断未来长期盈利。

本题不能交给核心资格验证。若未来研究低波，应把“相对 high-vol 的横截面差”与“用户单腿绝对收益”明确分开；多腿 low-minus-high 会改变当前单计划产品语义，必须另题授权。
