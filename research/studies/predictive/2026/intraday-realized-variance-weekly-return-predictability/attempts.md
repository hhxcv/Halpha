# 尝试与失败日志

## 2026-07-22：选题与冻结前检查

- 审计 6 个现有 `INSUFFICIENT_EVIDENCE` 策略候选：PPC 只能冻结前向观察；CTREND、日线高波 SHORT、日线低波 LONG、UP–UP winner 和 TRX 波动目标均没有可合法补跑或事后简化为新候选的独立空间。
- 联网核对 JFQA 同行评审全文。论文明确比较日线波动率与 15 分钟 realized variance：前者不显著，后者对下一周收益为负；因此本题不是在日线高/低波失败后换 60/90/120 日窗口。
- 查重本地 IVOL、MAX、RSJ、普通高低波和动量研究。本题只固定 total realized variance，不先引入 jump detector，避免在一个问题中同时搜索分解方法。
- development 复用 `relative-signed-jump-next-day-predictability` 已下载的 425 个官方 15 分钟 archive（约 50.8 MB）；只读取公开缓存，不读取产品数据。

## 2026-07-22：development 与停止

- checkpoint digest：`bf0041aa1539c1db701f0cfba83941bbc011f4fa3bafae468b2f5c4982477bd1`；数据质量 `PASS`。65 个预定 decision weeks 中形成 58 个至少 20 标的的有效周，panel 共 1,329 行。
- `RV28` high-minus-low 为 `-0.103937%/周`，但四周 block-bootstrap 95% 区间 `[-1.547735%, +1.552344%]`；负向周比例 `51.7241%`，未过 `52%` 门。
- rank IC 均值为 `-0.099271`，负向单侧 HAC p=`0.010887`，说明排序存在方向信息；但控制 `DVOL28/MOM28/MAX28/BETA84/volume` 后，RV28 系数反而为 `+0.600563%`，负向单侧 p=`0.860349`，没有独立增量。
- 最高 RV 单目标 `0.25x SHORT` 在 52bp 标的往返压力成本和 `4%/52` 完整资本门后为 `-0.408450%/周`，区间 `[-1.571756%, +0.509944%]`；同口径日线 DVOL28 高波 SHORT 为 `-0.034735%/周`，RV 相对增量反而为 `-0.373716%/周`。
- 前后半段主代理均为负：`-0.138665%/-0.678236%`；2022/2023 为 `-0.005629%/-0.940175%`。RV21/RV35 的 spread 仍为负，但单目标 SHORT 代理分别为 `-0.366941%/-0.097551%`，邻域不能形成可交易平台。
- 广度并非主要失败：最高 RV 选择覆盖 10 个 symbol，重复出现标的中 75% 的均值为正，最大正贡献占 34.62%；然而总体均值、控制增量、时期与基准均失败，不能用广度掩盖经济反证。
- development gate `FAIL`，最终结论 `DOES_NOT_SUPPORT`。evaluation、confirmation、positive-jump/jump-robust 分解和策略转换全部封存；不筛选事后表现较好的 symbol 或年份。

## 2026-07-22：确定性复现

- 完整重跑 `analyze --stage development`；关键数值和失败门完全一致。
- 四个 CSV 的 SHA-256 在两次运行间逐一一致：panel `7fffbbc7e571978bafafb58bd6d1f90d814c21217e36a55cc081b7f1facade94`、weekly `30d32a8a120046faa238fcedfa00f2c94427a58bfc6a7d30e2e82e8ee1ae8654`、selected `d07cd02fbf16876c909094a15675d64aaa5cde93c8dd52d53e260aeaa548e5ff`、Fama–MacBeth weekly `518edd0a47d4aa70df0db865e6469a520808e7998dfb9ac1f01624d634b68ba7`。
- 最终 `validate` 为 `PASS`；结果文件包含时间戳，所以复现身份以冻结 checkpoint、数据 manifest 和确定性 CSV 哈希为准。
