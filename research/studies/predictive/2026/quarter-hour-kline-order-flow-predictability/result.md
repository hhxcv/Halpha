# 结果与结论

## 结论

`DOES_NOT_SUPPORT`

在预先固定的 4 个论文外 Binance USD-M 永续、2021–2022 development、完整边界首分钟 Kline、下一分钟 open 与 12 小时目标下，1m taker-buy volume 订单失衡代理没有正向增量预测性，也没有达到最低 12 bp 经济相关线。开发门失败，2023 evaluation 与 2024 confirmation 保持未下载、未查看；本题不释放 `STRATEGY_CANDIDATE`，不制作产品交接包。

这是否定**低成本 1m Kline 代理实现**，不是对 Kim 与 Hansen 前 10 秒逐笔结果的精确复现或否定。它也不证明所有周期性订单流、逐笔 aggTrades 或其他资产都无效。

## 数据与完整性

- 对象：`BNBUSDT`、`LINKUSDT`、`UNIUSDT`、`FILUSDT`。
- 结果期：2021-01-01 至 2023-01-01（左闭右开），四资产各 1,051,200 根对齐 1m bar，共 4,204,800 根。
- 主回归事件：280,091 个资产-边界观察，覆盖 730 个 UTC 日。
- 来源：96 份官方月文件；因两个 checksum 有效的 FIL 月文件存在完整日缺口，另用 5 份已登记官方日文件补齐。最终 manifest 共 101 个文件、154,786,463 bytes，每个文件实际 SHA-256 等于官方 checksum。
- 质量：四资产均为完整 UTC 分钟网格，无缺失、重复或失衡越界；零成交量行分别为 BNB 123、LINK 123、UNI 170、FIL 235，按事前规则产生未知并丢弃。
- Git 外原始缓存：`D:/projects/Codex/CodexHome/research-data/halpha/quarter-hour-kline-order-flow-predictability/`；Git 内保留 `source_manifest_development.json` 的全部可重取身份。

## 主结果与反证

四资产等权 12h IQR effect 为 **−3.108 bp**，联合 4 日 moving-block bootstrap 95% 区间为 **[−6.631, +0.413] bp**。固定四个伪边界的平均效应为 −0.948 bp；真边界减伪边界为 **−2.160 bp**，bootstrap 区间 **[−5.868, +1.616] bp**。所以真边界既未显著为正，也没有比任意 15 分钟间隔的伪相位更强。

| 资产 | 主 IQR effect (bp) | HAC 双侧 p 值 | 判断 |
|---|---:|---:|---|
| BNBUSDT | +0.322 | 0.905 | 近零 |
| LINKUSDT | −6.748 | 0.0336 | 显著反向 |
| UNIUSDT | −5.750 | 0.0995 | 反向 |
| FILUSDT | −0.256 | 0.929 | 近零 |

年份不稳定：2021 为 −7.172 bp，2022 为 +1.839 bp。固定稳健性也没有恢复正向主张：

| 固定反证 | 四资产平均 IQR effect (bp) |
|---|---:|
| 8h 目标 | −1.733 |
| 延迟至第 5 分钟 open | −2.605 |
| 排除 top-of-hour | −2.424 |
| 排除 00:00/08:00/16:00 funding 开口 | −2.967 |
| 只用订单失衡符号 | −3.150 |

固定开发门中只有数据质量和最低样本数通过；主效应、bootstrap、相对伪边界、四资产一致性、两年一致性、延迟/整点/funding 反证和 12 bp 经济线全部失败。该失败不是“统计上略弱但可能可交易”，而是方向、相位特异性、稳定性和幅度同时不支持。

## 对论文与盈利机会的含义

来源论文用逐笔成交构造**前 10 秒**失衡；本题把整整 60 秒压成一个 Kline 代理，并延迟到下一分钟动作。结果说明这个更便宜、更适合个人长期维护的表达丢失了论文所述信息，或该关系没有泛化到四个论文外资产/本时期。两种解释都导向同一项目决定：**不应把 1m Kline quarter-hour imbalance 包装为高潜力策略，也不值得用 2023/2024 留出数据继续救它。**

精确 aggTrades 复现仍是未回答问题，但优先级降低：它需要更大逐笔数据管线，而论文已经表明 10 秒开盘预测毛幅度小于常规交易成本；只有未来存在明确的执行用途或更低成本条件时才值得另开题。本轮更合理的后续方向应离开该代理的近邻阈值优化，重新选择经济机制不同且能形成低换手单腿策略的问题。

## 复现与边界

研究代码 SHA-256：`db13443403c90d51a2bc812b34e596ed230eb3a57f05dcf48466d663dfe09ec3`。环境：Python 3.13、pandas 3.0.3、numpy 2.4.6、statsmodels 0.14.6、VectorBT 1.1.0。

```powershell
research\.venv\Scripts\python.exe research\studies\predictive\2026\quarter-hour-kline-order-flow-predictability\study.py verify-plan
research\.venv\Scripts\python.exe research\studies\predictive\2026\quarter-hour-kline-order-flow-predictability\study.py self-test
research\.venv\Scripts\python.exe research\studies\predictive\2026\quarter-hour-kline-order-flow-predictability\study.py prepare --phase development --workers 4
research\.venv\Scripts\python.exe research\studies\predictive\2026\quarter-hour-kline-order-flow-predictability\study.py run --phase development
```

同一缓存和种子下重复运行，排除 `generated_at_utc` 后的 canonical JSON SHA-256 两次均为 `3eb770e8a696f85499b0bfaed3015d249b2adef4776dfdbace287f309c459f28`。`prepare --phase evaluation` 被代码按门禁拒绝，且缓存中没有 2023/2024 文件。

本题没有模拟手续费、spread/slippage、funding、仓位重叠、成交、保证金或清算；由于预测门已失败，继续做这些策略层计算只会增加复杂度，不能把负面预测证据变成 Alpha。结果不改变产品策略、L4、资金或真实账户状态。
