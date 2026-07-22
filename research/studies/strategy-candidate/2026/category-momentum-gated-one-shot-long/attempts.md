# 实际尝试与失败记录

## 2026-07-22 开题前

1. 读取当前 L2/L3/L4、`research/README.md`、`research/studies/README.md`、`research-halpha` 全部指引和当前 40 个研究问题。
2. 发现前一项季度时点 1m 订单不平衡研究与已有 predictive 问题重复；本题因此先按机制、对象、时期、问题和结论做全库查重，不建立新的全局注册表。
3. funding + trend 交互虽未被原样运行，但与已经失败的下一 funding 单腿和多个趋势家族相邻，且原始论文主要支持 basis/carry 或解释关系，未提供该拼接的独立收益依据，淘汰。
4. 外部检索发现 Luo 的 Binance 永续类别动量研究；进一步阅读 249 页论文的方法和数据段，确认原结果依赖 30 个分散类别、价值加权和 top/bottom 多腿，不能直接交付当前产品。
5. 选择“类别共同成分能否转成用户固定单币 LONG one-shot”作为新问题。它的主要价值正是可被否定：若多腿横截面选择是收益来源，固定单币适配应在零售成本、funding、自身动量基准和论文后留出中失败。
6. 冻结 `research/market-universe/universe.csv` SHA-256 `1f24adfb64b7a52a170b730ee7517916b2da8ab45785779dee6be991762186cc`；按事前规则得到七类 74 个成员。当前分类不是历史分类，幸存者偏差进入结论边界。
7. 此时尚未下载或查看本题任何价格、funding 或策略结果。下一步先生成绑定代码、预注册、来源和环境版本的 checkpoint，再仅打开 development。

## 2026-07-22 development 取数中断与允许修复

8. 先生成 checkpoint，内容摘要 `607494f574e6eeaad50b1fea752b3bb04694569ed4fc4e54260c710cd2911a85`；随后执行 development fetch。
9. 第一次 fetch 在已报告完成 30/74、并已写入 HBARUSDT 三页 funding 后，于下一对象请求收到 Binance HTTP 403。进程在约 84 秒后失败；没有生成 source manifest、数据质量、策略结果或后段数据。已完成原始页保持不变。
10. 依据 Binance 官方 WAF/rate-limit 说明，只修复取数可靠性：分页优先复用已存在且可解析的原始页，新网络请求间隔从 0.06 秒提高到 0.30 秒，对 403/418/429 采用最长 45 秒退避。经济问题、固定名单、分类、时期、信号、参数、成本、统计与门均不变。因为代码 hash 改变，将在继续取数前重新生成 checkpoint；这一变更和旧摘要同时保留在本记录中。
11. 修复后 checkpoint 摘要为 `616a05e5f6af56af166ef0979bf91bd8f607ec7127eb74b72b04dd52dded8214`。第二次 fetch 仍在未生成 manifest 或结果前被同一 funding REST 403 阻断，说明不是简单的单请求间隔问题；停止继续打同一端点。
12. 核对 Binance 官方 public-data 仓库和真实 URL 后，确认 USD-M monthly `fundingRate` 与 `markPriceKlines/8h` 归档及 `.CHECKSUM` 可公开取得。内存检查 BTC 2022-01 样例显示 funding CSV 字段为 `calc_time,funding_interval_hours,last_funding_rate`，8h mark archive 提供完整 OHLC；不使用第三方聚合源。
13. 在尚未生成任何数据 manifest、质量或收益结果前，重新预注册取数实现：74 个 peer 只需要日线；目标工具事前固定为当前快照 A1/A2 且 spread ≤5 bp 的 26 个对象，仍须动态通过 30 日 10m quote-volume 门；只有这些目标下载 funding/mark 官方月归档。funding 名义使用事件时点最近 1 分钟的官方 8h mark open 代理。该变化减少无用途 funding 数据并替换被阻断的取得通道，但会改变 checkpoint，故再次生成新摘要后才继续。分类信号、方向、窗口、成本、阶段和结论门不变。
14. 该版 checkpoint 摘要为 `877201a0d2662fc30d8fca295bda06a02ce1df93d9f1a367d92ec5d9730da9d5`。归档任务执行到已报告 400/1248 后遇到一个官方 404；检查已存目录确认只有 `ICPUSDT` 的 fundingRate 缺 2022-01 至 2022-08，而其 mark archive 完整，其他 25 个目标的 development funding/mark 各 24 个月均已完整取得。进程仍未生成 manifest、质量或结果。
15. 不把缺失 funding 当作零，也不混入聚合源或事后代理。`ICPUSDT` 继续作为 Layer-1 peer 提供日线类别信号，但从目标名单移除；可交易目标变为 25 个，其他资格和最少 20 目标门不变。已下载的 ICP 原始归档保留为失败证据但不会被新 manifest 引用。再次生成 checkpoint 后继续。
16. 25 个目标版本的 checkpoint 摘要为 `d05ee01f7dc3cbdd953bede9b7fd57d9656df11c228bac7979a6561f23a6b01b`；development fetch 完成 74 个日线对象及 25 个目标的 1,200 个资金费/8h 标记价月归档校验，source manifest 摘要为 `27cdd339a83188b1fe0e57fdf3f9d7e6873a2a82e41f5b2bc0b96ec730586a64`。
17. 首次 inspect 在读取官方标记价归档时失败：部分月文件含 CSV 表头、部分不含，而读取器原先统一按无表头处理。失败发生在任何质量或收益结果生成前。仅修正输入解析为按首字段显式识别两种官方格式，并对含表头文件要求完整字段严格一致；信号、阈值、名单、成本和统计均不变。代码摘要改变，因此重建 checkpoint 和 manifest 后再检查。
18. 格式修复后的 checkpoint 摘要为 `933ae9074dbf2aeb1d9641372eb75051165b82197b1e703fba9f08e75187e96b`，重建 manifest 摘要为 `372ce2968ebe1d9d938a32e692ee343ba28b70c67dc1cba10ab1c40fd5838a4f`。首次完整 inspect 产生 `FAIL`：日线、OHLC、成交额和 funding 连续性均通过，但所有目标在 2022-10-02、2023-02-24 的官方 8h mark 序列缺整日；SOL 另有 2022-11-09 至 2022-11-18 非 8 小时 funding 时点。25 个目标共出现少量无法在 1 分钟内匹配的 funding 名义；未计算收益。
19. 核对 Binance 官方 public-data 仓库后确认 markPriceKlines 支持 1m 和 8h 月归档，并均提供 `.CHECKSUM`。在不查看收益的前提下增加确定性、同源的 gap-only 补足：先用 8h，只有 `funding × 8h` 无法在 1 分钟内匹配的目标月份才下载 1m mark 归档，并仍要求 1 分钟内最近 open。该修复解决粒度/归档缺口，不改变名单、价格信号、方向、持有期、成本或统计门；预注册正文不改写，修正规则以附录追加。下一步重建 checkpoint 和 manifest 后重新过质量门。
20. gap-only fetch 实际取得并校验 57 个 1m 月归档，新 manifest 摘要为 `bfa8f73d27fc7cf1136cbd8e784661a6a3bf92b138dc44d7f0ad215ac048a67c`。第二次完整 inspect 仍为 `FAIL`：1m 归档同样缺整日，25 个目标各余 5–8 个无法配对事件，单目标缺失率约 0.23%–0.37%。失败质量证据复制为 `data_quality_development_fail_unmatched_mark.json`，文件 SHA-256 `f207b53e30e69c849ab42a0fe82f55376c4cc58a10dae39498c4b99cd3ce6f8f`；仍未计算收益。
21. 对 AAVE 缺口窗口做一次只读 Funding Rate REST 核对，端点可达且返回 438 条，但相应事件的 `markPrice` 明确为空，说明无法从该官方接口恢复。停止继续扩展数据代理。最终固定缺失处理：每目标缺失 funding mark 比例最多 0.5%；任何跨缺口候选交易整笔排除且仍占用策略计划时间；主规则排除比例最多 2%，所有基准/邻域同步记录。不用零、插值或成交价。该规则在首次收益计算前加入 checkpoint。
22. 最终 checkpoint 摘要为 `5daae3b3faf810b2246f1a9296660d64b17076bf491d73768eb3567332ba3a38`，绑定 manifest 摘要为 `e4dc8ba124ddf6662b8f10624c22c53f61f548022f8aaed7b8855f3940a66dd7`，development 数据质量门通过。首次 analyze 进程在 124 秒调用上限被终止，只写出主规则与 `formation_14d` 中间 CSV，未生成 `development.json`，因此没有可用研究结果或阶段门判断。代码、数据、参数不变，随后用允许持续等待的执行方式从头重跑并覆盖中间文件。
23. 首次完整 analyze 用时 221.1 秒：主规则 821 笔，base/stress 扣门槛日期队列均值分别为 -0.3019%/-0.4639%。development gate 为 `FAIL`，13 项门失败；`results.json` 写出 `DOES_NOT_SUPPORT`，并明确后段 `NOT_OPENED_BY_SEQUENTIAL_GATE`、handoff `NOT_GENERATED`、product effects `NONE`。
24. 随后误调用仅供三阶段全部 PASS 后生成 handoff 的 `conclude`，它因不存在 `evaluation_gate.json` 而失败。检查代码确认 development `gate` 已经完成失败结论；缺少后段文件是预期封闭状态，不是实现缺陷。没有修改代码或伪造后段 gate。
25. 从固定外部缓存再次执行完整 analyze（226.4 秒）和 gate。主规则与五个诊断 CSV 的六个 SHA-256 均与首次完整运行逐字节一致；821 笔、base/stress 均值、结论与 13 项失败门一致。JSON 的生成时间和内容摘要随复算变化，不用整文件 hash 代替数值/交易身份核对。精确前后摘要见 `validation.json`。
