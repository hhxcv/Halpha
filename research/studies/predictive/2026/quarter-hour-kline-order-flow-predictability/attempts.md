# 实际尝试与失败记录

开题前只进行了产品语义、已有研究、公开来源和研究环境的只读检查；未下载或查看本题 1m 结果。

后续每次命令、下载重试、校验失败、允许的实现修复和阶段启封决定均追加在此，不删除失败记录。

## 2026-07-22 事前冻结

- `python -m py_compile .../study.py`：通过。
- `python .../study.py self-test`：通过 15 分钟相位、订单失衡重建、下一可行动目标、statsmodels OLS、4 日 block-bootstrap 充分统计量重估五项合成测试。
- 数据下载前固定 `study.py` SHA-256：`81fa8145ae1a50aaeeae25adcb656f02601bce4537dd2f9543295c28fa165b1e`。
- 此时未下载 development/evaluation/confirmation 的任何本题 Kline 文件，未查看方向或收益输出。

## development 数据完整性中断与事前修复

- 首次 `prepare --phase development --workers 4`：96 个月文件全部通过官方 checksum，共 154,519,690 bytes。
- 首次 `run --phase development` 在任何回归或收益输出前中断：`FILUSDT-1m-2022-02.zip` 只有 36,000 行，少于完整月 40,320 行。
- 仅检查时间戳后确认月文件连续覆盖 2022-02-01 00:00 至 2022-02-25 23:59 UTC，恰缺 2 月 26–28 日 4,320 根；没有读取或汇总价格、订单失衡、方向或未来收益。
- Binance 官方日归档中的对应三份文件与 `.CHECKSUM` 均返回 200。完整性请求只核对 HTTP 状态、字节数和 checksum 文本，没有持久化或解析结果字段。
- 在结果仍未暴露时，把这三份官方日文件登记为唯一修复；合并后必须严格匹配完整月网格，不插值、不前向填充、不改研究对象或门槛。
- 修复实现重新通过编译与同一五项合成自测；在 manifest 来源描述同步后，最终重新冻结 `study.py` SHA-256：`9b59cf509a20e54e8058d7b29e90ab2a83ffe9e3f01a39c9b83a60600458ca75`。旧 hash 与首次失败均保留在本文件。

第二次运行同样在回归或收益输出前中断，原因是完整性修复分支在另一个 FIL 月份遇到空列表。随后对 96 个月文件执行了一次**只读 open-time 扫描**：除已知 2022-02 外，仅 `FILUSDT-1m-2022-04.zip` 缺 2022-04-01 至 04-02 的 2,880 根；其余 94 个月分钟网格完整。对应两份官方日文件与 checksum 可用，故在仍无结果暴露时一并登记。修复分支也改为先按月份筛选登记日，避免空列表错误。编译和五项合成自测再次通过，最终代码 hash 更新为 `db13443403c90d51a2bc812b34e596ed230eb3a57f05dcf48466d663dfe09ec3`。

## development 最终运行与门禁

- 最终 `prepare --phase development --workers 4`：96 月文件 + 5 日修复文件全部通过官方 checksum；manifest 101 个文件、154,786,463 bytes。
- `run --phase development`：数据质量 `PASS`；四资产各 1,051,200 根，合计 280,091 个有效边界观察。
- 主效应 −3.108 bp/IQR，bootstrap 95% CI [−6.631, +0.413]；真边界减固定伪边界 −2.160 bp，CI [−5.868, +1.616]。固定开发门失败，结论 `DOES_NOT_SUPPORT`，`release_next_phase=false`。
- 第二次完整运行复算结果；忽略生成时间后的 canonical JSON hash 前后均为 `3eb770e8a696f85499b0bfaed3015d249b2adef4776dfdbace287f309c459f28`。
- 尝试 `prepare --phase evaluation --workers 2` 被预注册门禁在下载前拒绝：`evaluation is sealed because the prior phase did not release it`。外部缓存未出现 2023/2024 文件。

最终命令、全部逐币/逐年/伪边界/稳健性数值及解释见 `result.md` 与 `development.json`。没有修改研究问题、资产、相位、控制项、目标、门槛或成本线。
