# 实际尝试与失败

## 开题前

- 完整读取 `AGENTS.md`、`research-halpha` 及其方法参考、当前 ALP-001/002/003、L4 plan、research 两级 README。
- 全库查重后确认 BTC lead-lag、BTC-neutral residual reversal、类别 momentum、无条件 survivor momentum、周 loser continuation、低波/高波、premium/funding 与 15 分钟边界 1m order-flow 已有答案。
- 联网核对持续 UP–UP momentum 的原论文口径、survivor momentum 反证、size/liquidity 异质性、dispersion 状态研究和 Binance/VectorBT 官方资料。
- 没有查看本题任何收益输出；规则、成本、基准、阶段、门和数据复用身份先写入 `preregistration.md` 与 `sources.md`。

后续每个命令、结果影响修复、失败和启封决定追加于此；不得删除失败或只保留最佳配置。

## 检查点与数据质量

1. `python -m py_compile .../study.py` 通过；只检查语法，没有计算市场结果。
2. `study.py checkpoint` 在任何收益输出前完成：checkpoint digest `8b500f595e1f280c75fb83ce1eefb809cac228d366cc4625b27fd2db7257461f`。
3. source reuse 固定父 manifest SHA-256 `23566d464f3b57eca11288160d8331610862210e20ec0b04c08306ee21e33fe0`，引用 66 个公开缓存文件、7,669,925 bytes；reuse digest `3fa987d1f7893d12a7f999d144bb91d9ede3b62e38580dace324f44f878d2bba`。
4. `study.py inspect` 逐文件重算 bytes/SHA-256，并重新解析六币 1d Kline、funding 与 mark。六币都无日线 gap、非法 OHLC 或缺失 funding mark，`data_quality=PASS`；digest `1b37716345bdc6da26b3feef213313c0e4f5ea46d97af848470b30cfa910fe7a`。

至此仍未运行 `analyze`，development/evaluation/confirmation 收益均未查看。

## Amendment 001：状态邻域暖启动覆盖

- 首次 `analyze --stage development` 在任何 CSV/JSON 结果生成前失败。traceback 为 `KeyError: 2020-12-13`；主配置构造状态时已需要父缓存起点之前的周 close，最宽 `state6` 邻域还需要更多暖启动。
- 这是开题时对“最初五周暖启动”的覆盖计算错误，不是市场结果。检查确认目录中没有任何 `development*.csv`、`development.json` 或 `results.json`。
- 不改变 signal、状态定义、参数、成本、门或数据源；只把 development 起点从 `2021-01-04` 顺延到 `2021-02-15`，使固定最宽邻域的最早底层周收益落在 2020-12-20 之后。顺延会减少约六个周样本，不是结果驱动选择。
- `study.py` 与 `preregistration.md` 已同步；旧 checkpoint digest `8b500f...461f` 继续由本记录保留。随后必须重跑 checkpoint 与 inspect，再允许第二次 analyze。
- 修复后目录仍无任何 development 输出；语法检查通过。新 checkpoint digest `b3fceeca0ae873df19b7c1374881e70dac7d35c63df768effc034c125e12354f`，锁定 study SHA-256 `c64b560cab5af525cf54e922778fa8a565f5f3a643fe28e3e620ea8798081d8e` 与 preregistration SHA-256 `449fa05f7df5112e0b26b12007ee3204a428a1169076d5e03abde29246b98ff4`。
- 重跑 inspect 仍为 `PASS`，新 data-quality digest `0f9fe2677b8dc7123f4fd2296961bb68aeae22d72a45f4727be51687bf46ec2a`。现在才允许第二次 development analyze。

## 首次成功 development 与 Amendment 002：空年份汇总

- 第二次 `analyze --stage development` 首次生成结果：31 个 eligible 周，base/stress 复合 `+7.4107%/+2.1296%`，相对同状态六币市场 gross excess 均值 `-0.27196%/周`。
- 首次结果 digest `054ac0d721405eb378279d19cfc02ec55435d6d834b016e836e4030b7d2474b0`；首次 gate digest `e1b05d2a77192bc95f63274c1460221d6d99a80cbfcb90c3bd9bd4e0b3f21fb5`。gate 为 FAIL，并已显示多项与结论直接相关的失败。
- 审计发现 `summarize` 按阶段端点枚举年份，因 development 结束于 2023-01-02，把 0 个入场的 2023 也加入历年门，额外产生 `each_full_year_at_least_8_weeks` 失败。该空年份不是研究对象，也不应计作历年反证。
- 修复为只汇总实际有入场的历年；同步把预注册文字澄清为“每个有入场的历年”。不改变任何 trade、收益、成本、状态、bootstrap、基准或其他门。已查看结果后只允许这个确定性汇总修复，不能借机改经济规则。
- 修复前的主反证仍成立：stress 扣门为负、gross excess 为负、落后六币市场、2022 为负、bootstrap 下界为负、回撤超限、邻域不足且盈利高度集中。修复不可能把 gate 改为 PASS。

## 来源标识更正

- 完成结果复核时通过 ScienceDirect/RePEc 再核对，状态转换论文 DOI 应为 `10.1016/j.frl.2025.108356`，开题资料误写成 `...107958`。只更正链接，不改变论文、方法或解释；随后重新生成 checkpoint/source reuse identity 并重跑 inspect。

## 最终运行、门与复现

最终顺序命令：

```powershell
research/.venv/Scripts/python.exe .../study.py checkpoint
research/.venv/Scripts/python.exe .../study.py inspect
research/.venv/Scripts/python.exe .../study.py analyze --stage development
research/.venv/Scripts/python.exe .../study.py gate --stage development
```

- 最终 checkpoint digest `344dedd90b2d9baf04ea924989f8fce85fe44538f1c0e331d5819c04981706a0`；source reuse 66 files / 7,669,925 bytes；data quality `PASS`。
- development：31 周；favorable/base/stress `+9.10%/+7.41%/+2.13%`；stress 扣门 `-5.13%`；2021/2022 base `+17.17%/-8.33%`；base MDD `-26.69%`。
- 相对同状态六币 market 的 gross excess `-0.2720%/周`，区间跨零；同状态 market base/stress `+16.45%/+10.67%`。
- gate `FAIL`：资本门、市场增量/基准、历年、bootstrap、回撤、邻域和集中度共九项失败。按预注册，结论 `INSUFFICIENT_EVIDENCE`，evaluation/confirmation 未打开。
- 完整重复 analyze/gate 后，8 个 trade CSV 哈希、gate status 和失败项集合均一致；详见 `validation.json`。
