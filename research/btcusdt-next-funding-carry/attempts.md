# 实际尝试与失败记录

所有时间为 Asia/Shanghai（UTC+08:00），数据事件时间仍为 UTC。任何评价区间一旦运行即视为已暴露，不因删除文件恢复“未查看”。

## 2026-07-20 基准与现有材料

- 完整读取 `AGENTS.md`、`research-halpha/SKILL.md`、条件参考 `research-method-and-evidence.md`、当前 `HALPHA-ALP-001/002/003` 和 L4 current plan；另读取 DAT/CAP 相关语义。
- 仅读取正式策略 registry、纯逻辑、bar evaluator、保护/止盈转换和相关测试以固定比较对象，没有修改产品路径、启动运行时或读取产品业务数据。
- 固定 detached worktree 提交 `de6b3052f28fe547730e89e58186d4ab397884b1`；工作树起始无改动，`research/**` 起始不存在。
- 系统 Python 3.11.9 可用；确认 `numpy 2.4.6`、`pandas 2.3.3`、`scipy 1.17.1` 存在，但为减小环境和依赖面，最终脚本只使用标准库。
- 尝试从系统 Python 导入 `nautilus_trader` 以核对 ATR 行为，得到 `ModuleNotFoundError`。没有安装依赖、没有改产品锁；正式策略比较因此明确降为 EMA-ATR 代理，并把差异写入限制。

## 2026-07-20 先行调研与选题

- 检索并记录 Binance 官方数据/API/funding 规则、perpetual 定价与 funding 原始论文、funding 一步预测论文、Bitcoin 中频反转论文、成熟时间序列动量论文。
- 初选四个方向；选择下一结算裸 funding carry。原因不是新颖或容易，而是它直接回答 L4 已知缺口（正式历史模型未含 funding），与趋势突破的机制不同，可用官方公开数据证伪，而且文献中的对冲结论不能直接覆盖单腿 Halpha 候选。按用户补充边界，它还满足个人小资金、单一工具、相邻 funding 周期即可反馈；依赖大资金容量、跨场所库存或长期验证的方向不选。
- 对 `2021-01` 的官方 1m 和 15m 月档案做只读 HEAD，均返回 200；1m 压缩档约 2.06 MB。公开 funding API 在 2021-01 返回 93 条升序记录，早期 `markPrice` 为空。这导致研究预先固定“结算分钟同场所 kline open 作为 funding 名义代理”，而不是猜造 mark。
- 尚未运行任何开发、评价或确认收益指标。

## 命令与结果

缓存根：`D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry/`。最终 67 个文件约 124,911,997 bytes；66 个 kline zip 和一个 funding JSON，均在 Git 外。

### 取数（逐批实际执行）

```powershell
python research/btcusdt-next-funding-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --start-month 2021-01 --end-month 2021-12 --manifest research/btcusdt-next-funding-carry/source_manifest.json
python research/btcusdt-next-funding-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --start-month 2022-01 --end-month 2022-12 --manifest research/btcusdt-next-funding-carry/source_manifest.json
python research/btcusdt-next-funding-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --start-month 2023-01 --end-month 2023-12 --manifest research/btcusdt-next-funding-carry/source_manifest.json
```

- 三批 36 个档案均通过相邻官方 `.CHECKSUM`；随后复制为 `source_manifest_development.json`，再进行开发选择。
- 开发期 quality：1,576,800 个 1m bar，等于理论数量；0 gap、0 duplicate、0 out-of-order、0 invalid OHLC。

开发命令：

```powershell
python research/btcusdt-next-funding-carry/study.py inspect --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --start 2021-01-01T00:00:00Z --end 2024-01-01T00:00:00Z --output research/btcusdt-next-funding-carry/data_quality_development.json
python research/btcusdt-next-funding-carry/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --manifest research/btcusdt-next-funding-carry/source_manifest_development.json --phase development --output research/btcusdt-next-funding-carry/development.json
python research/btcusdt-next-funding-carry/study.py select --development research/btcusdt-next-funding-carry/development.json --output research/btcusdt-next-funding-carry/selection.json
```

- `|funding| >= 1 bp`：1,846 笔，base 平均 -0.242701%，三个开发年均负，bootstrap 95% [-0.337182%, -0.145174%]。
- `>=3 bp`：356 笔，base 平均 -0.240048%，只有 2022 为正，区间跨零。
- `>=5 bp`：207 笔，base 平均 -0.266894%，只有 2022 为正，区间跨零。
- 无阈值通过预设开发门。按预设排序保留 1 bp，`selection_status=NO_VARIANT_PASSED_DEVELOPMENT_GATE_BEST_RETAINED_ONLY_FOR_FALSIFICATION`；没有根据评价期修改规则。

### 实现问题与修复

- 第一遍开发运行发现正式策略代理把 half-open 区间边界强平记为下一年（`end_ms` 恰为新年零点）。候选指标不受影响，但 baseline 年度表多出下一年一笔。
- 在下载或查看评价期前，把边界强平的记录时间改为 `end_ms - 1 ms`，封存开发 manifest，并重新生成 `development.json` 与 `selection.json`。修复后未再更改信号、阈值、成本、持有期或决定规则。
- 一个用于打印摘要的 PowerShell 管道有语法错误，未写文件；改用只读 Python 摘要。它不影响实验条件或结果。

### 评价、确认与结论（严格在 selection 后实际执行）

```powershell
python research/btcusdt-next-funding-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --start-month 2024-01 --end-month 2024-12 --manifest research/btcusdt-next-funding-carry/source_manifest.json
python research/btcusdt-next-funding-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --start-month 2025-01 --end-month 2025-12 --manifest research/btcusdt-next-funding-carry/source_manifest.json
python research/btcusdt-next-funding-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --start-month 2026-01 --end-month 2026-06 --manifest research/btcusdt-next-funding-carry/source_manifest.json
python research/btcusdt-next-funding-carry/study.py inspect --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --start 2021-01-01T00:00:00Z --end 2026-07-01T00:00:00Z --output research/btcusdt-next-funding-carry/data_quality.json
python research/btcusdt-next-funding-carry/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --manifest research/btcusdt-next-funding-carry/source_manifest.json --phase evaluation --selection research/btcusdt-next-funding-carry/selection.json --output research/btcusdt-next-funding-carry/evaluation.json
python research/btcusdt-next-funding-carry/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --manifest research/btcusdt-next-funding-carry/source_manifest.json --phase confirmation --selection research/btcusdt-next-funding-carry/selection.json --output research/btcusdt-next-funding-carry/confirmation.json
python research/btcusdt-next-funding-carry/study.py combine --development research/btcusdt-next-funding-carry/development.json --selection research/btcusdt-next-funding-carry/selection.json --evaluation research/btcusdt-next-funding-carry/evaluation.json --confirmation research/btcusdt-next-funding-carry/confirmation.json --output research/btcusdt-next-funding-carry/results.json
```

- 全期 2,890,080 个连续 1m bar、6,021 个 funding 事件；数据质量检查没有价格缺口、重复、乱序或无效 OHLC。66 个压缩档约 124 MB 总缓存（含约 0.8 MB funding JSON）。
- 评价期固定 1 bp：867 笔（863 short、4 long），funding 同号率 99.5386%；base 平均 -0.331579%，区间 [-0.428495%, -0.228637%]，2024/2025 均负。有利 12 bps 情景平均仍为 -0.131240%，区间仍全负。
- 确认期固定 1 bp：18 笔，base 平均 +0.039456%、中位数 -0.436253%，区间 [-0.740108%, +0.829802%]；样本小且不稳定，stress 成本平均 -0.160422%。
- `combine` 按预设规则输出唯一结论 `DOES_NOT_SUPPORT`。最强支持、反证、分期、成本和组件原始数值均保留在 JSON，不只保存结论。

### 复跑

完成全链路后，从外部缓存按相同开发→选择→评价→确认→合并顺序复跑到 Git 外的临时目录；将 `generated_at`、绝对临时路径和派生 artifact hash 排除后，候选、正式基准代理、选择、分期指标与结论逐字段一致。没有重新下载或修改输入。
