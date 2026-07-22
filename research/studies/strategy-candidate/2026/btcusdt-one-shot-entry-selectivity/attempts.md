# 实际尝试

- 2026-07-21：开题前扫描 `research/studies/**` 的 Donchian、breakout、BTCUSDT、正式策略和相关趋势问题。最接近的旧证据是 `btcusdt-next-funding-carry` 中的 1.0.0、20/2/0.5、最长 96×15m 比较代理；其评价期多空均为负，但退出期限和本问题不同。
- 2026-07-21：核对正式 1.0.1 的 registry、纯策略判断、Nautilus bar 边界和首笔成交冻结 R/两档止盈语义；记录四个源文件 SHA-256。
- 2026-07-21：核对 Git 外已有 Binance 官方缓存：2021-01 至 2026-06 共 66 个 BTCUSDT 1m 月档案及 funding history。尚未运行本问题的任何参数结果。
- 2026-07-21：完成先行来源核查并在查看结果前锁定 72 配置、固定退出、三阶段、成本、排序和停止门。
- 2026-07-21：按 `research/requirements.txt` 的哈希锁定依赖创建隔离 `research/.venv`；首次安装命令的 60 秒进程预算到期后，从已验证缓存继续同一安装并成功。`research/verify_vectorbt.py` 通过，VectorBT 1.1.0、pandas 3.0.3、NumPy 2.4.6、Numba 0.66.0 可用。
- 2026-07-21：研究脚本通过 `py_compile` 与 Ruff；在首次读取任何配置结果前封存 SHA-256 `b306946e84b6ab6d07d987238c99a153cf22f585048c2e3cab8e4afc3d711b4c`。
- 2026-07-21：首次开发运行在读取公开月档案时停止，尚未生成任何配置结果。原因是 Binance 较新的 CSV 含 `open_time` 表头，而较早档案无表头；按 checkpoint 允许的 parsing fix 增加逐档案表头检测，经济规则、搜索、时期、成本和门不变。
- 2026-07-21：表头修复后再次通过 `py_compile` 与 Ruff，并在首次配置结果前封存修订 SHA-256 `1450814102dd0fca73903c4221aae9797f0ae6eef11691fb23dea8eeb2eac0ec`。
- 2026-07-21：运行 development 完整 72 配置并保存全分布；数据连续且 OHLC 合法。开发选择门返回 0 个通过者、`evaluation_authorized=false`，因此未读取 evaluation 或 confirmation 结果。
- 2026-07-21：核对正式默认、历史激进基准、base 最佳与 favorable 最佳行；三个成本情景均无正均值配置。结论按预注册规则为 `DOES_NOT_SUPPORT`。
- 2026-07-22：逐行复核三个开发年度字段时发现初版 `results.json` 的反证摘要表述过强：70/72 配置三年均为负，另两组只在 2023 年小幅为正但整体仍为负。修正文案，不改变数值产物、门、结论或产品状态。
- 2026-07-22：在 Git 外独立目录重放 development 与选择门；`development.csv` SHA-256 完全一致，去除生成时间后 `development.json`、`selection.json` 语义完全一致，仍为 0 个通过者且 evaluation 未授权。
