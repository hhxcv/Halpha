# Halpha 单场所交易环境事实能力契约

**文档编号：** HALPHA-DAT-002  
**版本：** v0.8.0  
**文档状态：** ACCEPTED  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** DAT  
**语言版本：** zh-CN  
**批准人：** Halpha 项目所有者  
**接受时间：** 2026-07-18T07:01:20+08:00  
**替代版本：** HALPHA-DAT-002@v0.7.0  
**上位文档或条款：** HALPHA-DAT-001 v2.4.0  
**直接依赖：** 无；DAT 只生产事实，不反向依赖消费者决定  
**直接消费者：** HALPHA-ALP-002 v0.5.0、HALPHA-TRADEPLAN-002 v0.10.0、HALPHA-CAP-002 v1.2.0、HALPHA-EXE-002 v1.2.0、HALPHA-OUT-002 v0.8.0、HALPHA-UX-002 v0.11.0  
**适用纵向约束：** HALPHA-SYS-001 v1.6.0、HALPHA-ENG-001 v1.6.0  
**本文档负责：** 单场所交易所模拟盘与真实资金环境实际使用的闭合 K 线、标记价格、最优报价、工具规则、账户、订单、成交、手续费、资金费和持仓事实；事实来源、环境、时间、截止点、摘要、ExecutionAction/激活归属、缺失结果、追加与恢复契约  
**本文档不负责：** 形成信号、条件结论、资金授权、动作决定、复盘评价；保存全量行情或框架内部状态；规定当前场所、账户、工具、采样、阈值、保留期、NautilusTrader 精确版本或适配器配置  

---

# 0. 设计结论【DAT-RT-SUM-001】

DAT 只保留一个追加式 `VenueFact` 持久记录族。NautilusTrader 负责数据订阅、历史读取、K 线交付、协议解析、工具模型、订单事件和连接恢复；Halpha 不设计或平行实现这些内部能力。

Halpha 只保存已经被持久计划决定、环境限定 CAP 检查/`ExecutionAction`、最大损失计算、保护、闭环或复盘实际引用的事实，以及必须闭合的订单、成交、费用与持仓事实。未被使用的行情留在框架进程内，不建设行情仓库。

不存在 `Observation`、`FactWindow`、`FactUnknown`、`FactCorrection` 或 `IngestionCheckpoint`。输入集合、未知原因和恢复游标由实际消费者写入 `PlanActivation`、`PlanEvent` 或 `ExecutionAction`；不得把被删除对象换名放进子表或框架存储。

---

# 1. `VenueFact` 记录族【DAT-RT-FACT-001】

## 1.1 支持事实【DAT-RT-FACT-001-REQ】

`VenueFact.kind` 只支持以下有直接消费者的类型：

| kind | 最小业务载荷 | 主要用途 |
|---|---|---|
| `CLOSED_BAR` | bar type、区间、OHLCV、`ts_event`、闭合标志 | 代码策略和计划条件 |
| `MARK_PRICE` | 标记价格、事件时间 | 未实现盈亏、增险前估值和风险减少 |
| `TOP_OF_BOOK` | 同一更新的买一价量、卖一价量、事件时间 | 动作量化和提交前检查 |
| `INSTRUMENT_RULES` | 工具状态、价格/数量步长、最小数量与名义值、精度 | CAP 与 OrderFactory 输入 |
| `ACCOUNT_STATE` | 余额、场所报告的账户/持仓模式，以及可选的按工具 margin mode、实际 leverage、实际 maker/taker 费率与同一查询截止点 | 激活、提交前验证和保守 sizing |
| `ORDER_STATE` | 普通或条件订单身份、客户端身份、条款、状态和累计成交量 | 动作结果、保护和闭环 |
| `FILL` | 成交、订单与客户端身份、价格、数量、已实现盈亏和时间 | 持仓、最大损失和复盘 |
| `COMMISSION` | 实际手续费金额、资产、关联成交/订单和时间 | 本激活最大损失与复盘 |
| `FUNDING` | 实际资金费收入或支出、资产、工具、结算时间 | 本激活最大损失与复盘 |
| `POSITION_STATE` | 工具、方向、数量、入场/标记价格、未实现盈亏和查询截止点 | 风险减少、闭环和额度释放 |

资金费率、预计手续费和框架估值不能替代已结算 `FUNDING`、已发生 `COMMISSION` 或 `POSITION_STATE` 的实际场所事实。`ACCOUNT_STATE` 中的逐工具 margin mode、leverage 和当前账户费率只在其查询截止点内用于提交前校验与 sizing，不能冒充持仓、已发生手续费或其他工具事实；三者缺失、过期或工具不匹配时不得新增风险。所有资本数值使用 Decimal，并保存币种、单位、方向和来源精度；场所公开十进制文本直接解析，NautilusTrader `Price/Quantity/Money` 使用 canonical string 与 precision 转换，指标 double 不得写成 Halpha 资本权威事实。

## 1.2 共同字段与身份【DAT-RT-ID-001-REQ】

每条 `VenueFact` 至少包含：

| 字段 | 约束 |
|---|---|
| `venue_fact_id` | 由环境、kind、规范化场所对象身份/事件身份、来源版本和内容摘要稳定派生 |
| `environment_id`、`venue_ref` | 隔离模拟与真实记录环境；不得以显示名代替稳定身份 |
| `account_ref`、`instrument_ref` | 按 kind 必填；不适用为空，不造默认值 |
| `source_class` | `VENUE_QUERY | VENUE_STREAM | FRAMEWORK_DERIVED | EXTERNAL_UNCLAIMED` |
| `source_object_id`、`source_sequence` | 场所或框架公开身份与可用顺序证据；缺失必须显式为空 |
| `source_time`、`received_at`、`cutoff` | 分别保存来源时间、本机接收时间和查询/消费截止点，不互相回填 |
| `schema_version`、`content_digest` | 固定解释版本与规范化业务内容；本地重试时间不进入摘要 |
| `payload` | 对应 kind 的 Decimal 业务值和公开身份；不保存秘密 |
| `activation_ref`、`action_ref`、`attribution_digest` | 只有第 2 节证明 Halpha ExecutionAction 归属或用户接管范围匹配时才填写；action_ref 必须引用同一环境的 ExecutionAction |
| `attribution_class`、`handover_command_ref` | `HALPHA_EXECUTION | USER_TAKEOVER`；前者同时适用于 DEMO/LIVE 并由 environment_id 区分，接管活动必须引用已冻结命令；来源仍由 `source_class` 原样保存 |
| `supersedes_ref`、`correction_reason`、`correction_evidence_refs` | 仅修正时引用被替代事实、理由和证据；不得覆盖原事实 |
| `correction_effective_time`、`impact_scope`、`affected_reference_refs` | 仅修正时声明有效时间、影响账户/工具/用途及需重新评价的稳定宿主引用 |

同一来源对象的完全重复内容返回同一事实。来源后来给出不同版本或查询状态时追加新事实，不覆盖旧事实；历史消费者继续引用原 `venue_fact_id` 与摘要。修正版必须填写上述修正元数据，并由引用它的现有 HalphaCoordinator/拥有领域按 `affected_reference_refs` 重评，不建立 FactCorrection 身份、传播 worker 或以迟到事实追溯生成增险动作。

供 TRADEPLAN 去重的场所来源身份由 `environment + source_class + source_object_id + source_sequence/version + rule_id` 构成，不含 `content_digest`；内容摘要单列。同一来源身份出现不同摘要进入冲突/UNKNOWN，不能因修正版 `venue_fact_id` 改变而生成第二动作。

---

# 2. 来源与激活归属【DAT-RT-ATTR-001】

## 2.1 来源等级【DAT-RT-SRC-001-REQ】

`VENUE_QUERY` 与带场所稳定对象身份的 `VENUE_STREAM` 可以证明场所当时报告的状态。`FRAMEWORK_DERIVED` 可以作为已资格化的 K 线、指标输入或技术提示，但框架合成订单/成交事件本身不能证明场所已受理、实际手续费、资金费、持仓归零或责任闭合。`EXTERNAL_UNCLAIMED` 只能证明存在未归属外部活动。

框架 cache、portfolio、risk、内部 order 状态和 reconciliation 结果只是寻找或比较事实的技术投影。只有被规范化为 VenueFact 且保留权威来源、时间与 cutoff 的内容可以进入 Halpha 持久决定。

## 2.2 激活归属【DAT-RT-ATTR-001-REQ】

DEMO 与 LIVE 环境中的 Halpha 订单、成交、费用、持仓和保护只有在场所普通/条件客户端身份能够精确映射到同一环境已持久 `ExecutionAction` UUID32，并且账户、工具、方向和时间范围一致时，才可填写 `action_ref` 与 `attribution_class=HALPHA_EXECUTION`。DEMO 事实不得引用 LIVE 凭据、授权、PlanAllocation 或 ExecutionAction；LIVE 事实也不得引用 DEMO 动作。资金费只有在场所实际流水明确工具与结算时间，且同账户工具在该区间只有一个可归属的活动持仓责任时，才可归属；否则为未知或外部活动。

用户接管命令生效后，TRADEPLAN 已冻结的环境、账户、instrument、切换 cutoff、当时持仓和已知订单责任构成唯一接管范围。来自场所查询或推送、发生于 cutoff 后且可证明只减少或关闭该范围既有风险的订单、成交和仓位事实，可以填写 `activation_ref`、`attribution_class=USER_TAKEOVER` 与 `handover_command_ref`；其 `source_class` 仍保持 `VENUE_QUERY | VENUE_STREAM`，不得伪装为 ExecutionAction 或 Halpha 策略执行。新增风险、反向持仓、超出冻结范围、身份冲突或无法证明风险方向的活动仍保持未归属外部活动。

仓位事实可以证明账户工具非零或归零。未接管时，只有与本激活同环境 ExecutionAction、成交、人工活动检查和客户端身份集合共同闭合时，才可证明本激活仓位与结果；接管后，匹配冻结范围的用户活动只可帮助证明场所净仓位归零和开放订单清理，无法精确归属的收益、费用或资金费保持 `UNKNOWN`，不阻止满足 EXE 接管关闭条件后的额度释放。其他人工订单、程序订单、框架 reconciliation 合成事件或身份不完整事实不得计入本激活成交、盈亏或最大损失，并持续阻止新增风险或关闭。

归属在写入 VenueFact 时随证据确定；证据不足时 `activation_ref` 必须为空。后来证据足以确定 Halpha 动作归属或接管范围匹配时，只能在同一 VenueFact 记录族追加一个引用原事实的新版本，原记录不变。相同事实与相同归属输入必须得到相同摘要；不同归属结论是冲突，不能后写覆盖，也不建立第二事实记录族。

---

# 3. 消费、未知与 cutoff【DAT-RT-USE-001】

消费者读取 DAT 时必须声明用途、账户/工具、所需 kind、时间范围与 cutoff。DAT 返回一个非持久查询结果值：事实引用的规范排序、输入摘要、覆盖范围和 `COMPLETE | UNKNOWN`。为 UNKNOWN 时还包含一个嵌入式 `FactUnknownValue`：适用范围、原因、开始时间、合理可能状态、受影响消费者、当前限制和解除所需证据。该值没有 identity、版本、claim 或恢复生命周期，因此不是 FactWindow 或 FactUnknown 记录。

消费者即将形成持久决定时，在同一逻辑提交中把事实引用、cutoff 与输入摘要嵌入自己的宿主记录：

- 例行无动作的当前 `ConditionJudgement`、最近 K 线游标和持续未知写入 `PlanActivation`；
- 会改变状态、动作或用户责任的判断，以及终止时的无入场原因写入 `PlanEvent`；
- 提交前事实、结果未知、保护和单动作闭合证据写入 `ExecutionAction`。

宿主记录在保存 UNKNOWN 时必须完整嵌入 `FactUnknownValue`，不能只保存理由码；后续恢复以宿主值和新 VenueFact 比较，解除时保留原未知范围及解除证据引用。

关键事实缺失、过期、来源冲突、时钟不可信、连续性无法证明或归属不明时，DAT 返回 `UNKNOWN` 和原因；不得沿用最近值、拼接不同 cutoff、用成交价替代标记价格、用预测费用替代实际费用或用框架组合状态冒充场所事实。消费者按自身规则停止增险、保持查询、退出或要求用户接管。

闭合 K 线只消费框架公开契约已经标记闭合的 bar；未闭合 bar 不进入 `CLOSED_BAR`。最优报价的四个价量值必须来自同一事件，缺边、交叉或过期即为未知。错过窗口后取得的新事实只支持新的当前判断、风险减少、核对或复盘，不补发历史增险。

---

# 4. NautilusTrader 与只读补充【DAT-RT-NT-001】

NautilusTrader Binance 适配器直接承担行情与账户连接、订阅、历史请求、K 线、工具/数值类型、公开事件和启动/连续 reconciliation。HalphaCoordinator 从这些公开输出中挑选实际使用事实并写入 VenueFact；不建立 DAT 摄取工作器、持久检查点或第二重连状态机。

Binance instrument provider 提供的工具费率和内部失败回退只是组件技术输入，不是 `COMMISSION` 或当前账户实际费率事实；只有带场所权威来源的成交手续费、账户流水或已资格化只读费率查询才能进入对应 VenueFact/提交前事实集合。

若所选框架高层事件缺少本契约必需的订单结果、实际手续费、资金费或账户流水字段，只允许在同一 Executor 内复用 NautilusTrader 同一发行包公开的 cached client factory 所返回 client，增加一个窄只读补充端口；不访问 execution client 私有字段，不另建 client，也不引入 Binance SDK 或第二账户连接栈。该端口必须满足：

- 只暴露查询方法，不包含下单、撤单、改模式或改杠杆方法；
- 与 TradingNode 使用同一环境、账户、工具和 cutoff；
- 输出只进入同一个 VenueFact 记录族，不建立自己的 cache、数据库、checkpoint 或恢复循环；
- 与框架输出冲突时保持 UNKNOWN，不静默择一；
- L4 已证明精确版本、字段、分页、限频、时间和许可证满足用途。

同包只读 client 仍不足或缺少这些资格条件时，实际手续费/资金费保持未知并阻止依赖它们的最大损失闭环；只能直接修订相应目标 L3 与 L4 组件选择并重新评审接受，不能在运行时退回 Binance SDK、自研写适配器或第二状态源。

---

# 5. 恢复与闭环输入【DAT-RT-REC-001】

重启后由 NautilusTrader 完成数据连接和启动 reconciliation；各消费者从自己拥有的游标、开放责任和 closure 需求向 DAT 重新请求必要事实，DAT 不反向读取或拥有 `PlanActivation` 或 `ExecutionAction`。连续性中断后的只读核对可以继续追加迟到场所事实和查询结果，但事实可用本身不得清除 PlanActivation 的运行暂停或触发新写。DAT 不尝试恢复完整行情历史，只补足仍有明确消费者的 bar、订单、成交、费用与持仓查询。

额度释放所需事实集合至少证明：当前权威 `POSITION_STATE` 为零；冻结范围内普通与条件 `ORDER_STATE` 均无开放责任；所属环境所有可能越过写入边界的 ExecutionAction 已明确且无在途/未知调用；不存在新增、增险、反向或身份冲突的外部活动。未接管时，相关成交、手续费和资金费还必须在声明 cutoff 内完整；已接管时，匹配 `handover_command_ref` 的用户风险减少/关闭事实可以证明净仓位和订单责任已清理，但不能补造精确激活损益。任一关闭条件未知时只能保存未知摘要并继续只读核对，不能形成闭环结论。

---

# 6. 验证契约【DAT-RT-TST-001-REQ】

接受前至少证明：

1. 十种 VenueFact 均保存稳定来源身份、来源时间、cutoff、Decimal、schema 与摘要，重复输入幂等、不同内容追加而不覆盖；
2. 未闭合 K 线、过期/缺边/交叉报价、缺失标记价格和时钟冲突返回 UNKNOWN，不使用最近值或替代价格；
3. 普通订单、条件订单、成交、手续费、实际资金费和持仓可以从已资格化公开输出或唯一只读补充形成事实；预测值不能冒充实际值；
4. 已持久 UUID32 可以把 Halpha 场所订单/成交/手续费归属到同环境 ExecutionAction 和激活；用户接管活动只有精确匹配冻结范围且只减少/关闭风险时可标为 `USER_TAKEOVER` 并帮助证明关闭，仍不冒充 ExecutionAction 或确定损益；其他人工、外部、框架合成或身份不完整事实阻止闭环；
5. 同一 cutoff 的查询结果摘要稳定，消费者把事实引用和未知写入自身宿主；数据库中不存在 FactWindow、FactUnknown、FactCorrection 或 IngestionCheckpoint；
6. 重启只按开放消费者补取事实，不补发历史增险，不依赖框架持久 cache、event store 或 DAT 摄取工作器；
7. 只读补充没有写方法、第二数据库、独立 checkpoint 或平行事实权威；字段不足时保持未知；
8. DEMO 与 LIVE 事实都只可归属同环境 `ExecutionAction`；action_ref、environment_id、账户、端点和 UUID32 任一冲突都必须拒绝，跨环境引用、复制或把 Demo 事实用于 Live 证据必须失败；
9. 模拟与真实环境、不同账户和工具的同名对象不能合并。

---

# 7. 明确不建设与 L4 边界【DAT-RT-NON-001-REQ】

不建设全量行情仓库、本地订单簿、通用指标仓库、自研协议泵、第二套账户账本、FactWindow/Unknown/Correction/Checkpoint 状态机、数据服务进程或与 NautilusTrader 平行的行情/账户适配器。

L4 只固定当前依赖和适配器版本、实际场所/账户/工具、订阅与查询配置、允许用途、时效与 cutoff、只读补充选择、保留期、平台资格和验收证据；本 L3 不声称这些当前已经可用。
