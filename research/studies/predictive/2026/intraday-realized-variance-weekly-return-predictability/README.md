# 15 分钟 realized variance 与下一周收益

本目录回答一个固定的 `PREDICTIVE` 问题：前 28 个完整 UTC 日的 15 分钟 realized total variance，能否在 25 个成熟 Binance USD-M 永续中负向预测下一周收益，并且相对日线波动率仍有增量，达到另开策略候选题的最低经济空间？

本题不是策略、正式策略替代或交易授权。只有 development、evaluation、confirmation 三段顺序证据全部通过，才允许另开独立的 `STRATEGY_CANDIDATE` 题；本目录不会生成核心交易对象，也不会修改产品、L4、资金或真实账户。

## 项目边界

- 产品基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式策略身份仅作固定背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。
- 数据：Binance 官方公开 USD-M 15 分钟 K 线，以及既有公开日线缓存；不读取产品数据库、凭据或运行配置。
- development 复用已经按官方 `.CHECKSUM` 绑定的 Git 外缓存；后段只有前段 `PASS` 才允许下载。
- 研究频率：周频；周六 `00:00 UTC` 截止信号，周一 `00:00 UTC` 才开始目标收益，保留 48 小时人工计划间隔。

## 文件

- `sources.md`：原始研究、官方数据资料、适用性和差异。
- `preregistration.md`：固定问题、主定义、门槛、阶段和停止规则。
- `study.py`：checkpoint、数据身份、分析、gate、结论和复现校验。
- `attempts.md`：所有重要尝试、错误与失败。
- `source_reuse_manifest.json`：development 复用数据的上游文件身份。
- `checkpoint.json`：结果生成前冻结的方法和环境身份。
- `data_quality_<stage>.json`、`<stage>.json`、`<stage>_gate.json`：顺序证据。
- `results.json`、`result.md`、`validation.json`：最终判断与复现证据。

## 复现命令

从仓库根目录运行：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/study.py' checkpoint
& 'research/.venv/Scripts/python.exe' 'research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/study.py' prepare --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/study.py' analyze --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/study.py' gate --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/study.py' conclude
& 'research/.venv/Scripts/python.exe' 'research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/study.py' validate
```

若某阶段失败，后续阶段命令必须拒绝执行；不得改成 5/30/60 分钟、改变 28 日窗口、换分位数、筛选事后赢家或改变方向。
