# Halpha 机器授权的一次性交易计划功能契约

**文档编号：** HALPHA-TRADEPLAN-002  
**版本：** v0.10.0  
**文档状态：** ACCEPTED  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** TRADEPLAN  
**所属实现模块：** `planning` 的 TRADEPLAN 语义分区  
**语言版本：** zh-CN  
**批准人：** Halpha 项目所有者  
**接受时间：** 2026-07-18T07:01:20+08:00  
**替代版本：** HALPHA-TRADEPLAN-002@v0.9.0  
**上位文档或条款：** HALPHA-TRADEPLAN-001 v1.8.0；HALPHA-CON-001 v2.11.0、HALPHA-ARC-001 v1.9.0、HALPHA-DOC-001 v1.11.0、HALPHA-ENG-001 v1.6.0  
**直接依赖：** HALPHA-ALP-002 v0.5.0、HALPHA-DAT-002 v0.8.0  
**直接消费者：** HALPHA-CAP-002 v1.2.0、HALPHA-EXE-002 v1.2.0、HALPHA-OUT-002 v0.8.0、HALPHA-UX-002 v0.11.0（执行结果和用户命令作为反馈引用，不反转模块依赖）  
**适用纵向约束：** HALPHA-UX-001 v1.6.0；HALPHA-SYS-001 v1.6.0；HALPHA-ENG-001 v1.6.0  
**本文档负责：** 计划草稿与固定版本、一次激活一个交易周期、策略实例绑定、持久游标和截止点、计划事件、动作提议、三类用户控制、故障恢复、关闭与结果交付  
**本文档不负责：** 证明策略有效；分配资本；形成场所事实；向场所写入；设计页面；选择当前策略、参数、场所映射、组件版本或门槛  

---

# 0. 设计结论【TRADEPLAN-AUTO-SUM-001】

一次 `PlanActivation` 是用户明确激活的一次有界机器任务。用户在激活前固定代码策略版本、参数、环境、账户、工具、方向、目标暴露、有效期、失败行为、机器授权以及三个互斥额度。激活后，策略可在人离开后持续判断入场、撤单重挂、保护、止盈止损和退出条件，不再逐动作请求确认。

每次激活只运行一个交易周期。首次成交前，策略可以按固定逻辑等待、撤销或移动尚未成交的入场单；发生任何入场成交后，一旦该激活的场所责任被证明确已完全平仓并清理，激活永久结束，不自动重新开仓。再次交易必须由用户重新授权并建立新的 `PlanActivation`、机器授权决定和互斥额度；代码、参数、规则及其他计划内容未变时可以复用同一不可变 `TradePlanVersion`，只有内容变化才形成新版本。

NautilusTrader `Controller` 为每个运行中激活装载一个固定 `Strategy` 实例，并提供行情订阅、K 线、时钟、定时器及策略回调。该实例只生成不可变的瞬态 `StrategyProposal`；它不得直接提交、修改、撤销或平仓。Halpha 持久化计划身份、游标、决定和关闭证据，因此框架内存状态不是恢复权威。

TRADEPLAN 只新增四个自有持久记录族：`TradePlanDraft`、`TradePlanVersion`、`PlanActivation` 和 `PlanEvent`。条件输入、判断结果和动作提议嵌入 `PlanEvent`；游标、期限、恢复暂停和保护摘要嵌入 `PlanActivation`，最大损失锁存只由 CAP 的 `PlanAllocation` 拥有；不另建条件评估、工作窗口、定时任务或保护任务记录族。

TRADEPLAN 在 DEMO 与 LIVE 都只形成 `PlanEvent` 内的不可变 `ProposedAction`，不持久写入或推进执行动作。两个环境的 ProposedAction 都经同一 CAP→EXE 链，由 EXE 独占建立环境限定 `ExecutionAction`；不得按环境另立执行动作对象。从 DEMO 转入 LIVE 必须建立新的环境、激活、授权、额度和 ExecutionAction 身份，不能迁移任何动作状态。

---

# 1. 对象与身份【TRADEPLAN-AUTO-OBJ-001】

## 1.1 `TradePlanDraft`

`TradePlanDraft` 是唯一可修改对象，保存稳定 `plan_id`、草稿版本、内容摘要以及目标、依据、入场、退出、额度、时间、失败和结束决定。修改使用预期版本并发控制；草稿不是机器授权，也不能产生 `ExecutionAction`。

## 1.2 `TradePlanVersion`

固定版本至少保存：

| 内容 | 约束 |
|---|---|
| `plan_version_id`、`plan_id`、`fixed_at`、内容摘要 | 同一身份内容不同必须冲突；固定后不可修改 |
| `strategy_definition_ref`、代码构建身份、参数 schema 版本 | 指向 ALP 不可变代码策略定义 |
| 规范化参数及摘要 | 由策略 schema 校验；不得包含秘密 |
| 环境、账户、场所、instrument、方向和持仓模式要求 | 激活前必须可无歧义映射 |
| 目标暴露和单周期入场约束 | 不得超过 CAP 额度；不表示收益保证 |
| 入场、保护、止盈止损、时间退出和失败规则 | 引用稳定规则身份及所需事实种类 |
| `max_margin`、`max_notional`、`max_allowed_loss` 请求 | 作为不可变额度请求交给 CAP |
| 允许动作、有效期和恢复策略 | 作为机器授权请求交给 CAP |
| 策略证据选择与摘要 | 只证明达到选定资格门，不证明未来收益 |

任何交易逻辑或参数改变都形成新版本；不得就地修改已激活版本。

## 1.3 `PlanActivation`

`PlanActivation` 至少保存：

- 稳定 `activation_id`，固定计划、策略定义、额度和机器授权引用；
- 环境、账户、instrument、方向、框架 `StrategyId` 和目标暴露；
- 生命周期、是否已有入场成交、退出原因及责任所有者；
- CAP `PlanAllocation` 与当前 `StopStateVersion` 引用；是否可新增风险只从这些 CAP 权威与生命周期派生，不在 PlanActivation 另存开关或损失锁存；
- 与生命周期正交的 `run_state=ACTIVE | PAUSED`、可选 `pause_reason=WRITER_CONTINUITY_LOST`、暂停时间、恢复核对摘要和当前恢复命令引用；该状态只表达 `MANUAL_PLAN_RESUME` 的运行连续性暂停，不替代 CAP 停用、授权效力或用户接管；
- 每条规则最后已消费来源身份、输入摘要、事件截止点、固定 deadline 和当前嵌入式 `ConditionJudgement`；
- EXE 待定动作摘要和保护状态 `NONE | WORKING | UNKNOWN | GAP | CLOSED`；
- 用户接管时冻结的责任转移范围：`Command/Receipt` 引用、切换 cutoff、环境/账户/instrument、当时已知持仓方向与数量、已知开放普通/算法订单身份和责任摘要；非接管时为空。
- 最近已核对场所截止点、关闭证据摘要、结果引用和状态版本。

生命周期只使用 `RUNNING | EXITING | USER_TAKEOVER | COMPLETED | UNKNOWN`；`run_state` 单独表达当前是否因写入连续性中断而暂停。`EXITING` 仍允许减险、撤单、保护和核对；`USER_TAKEOVER` 表示自动责任已经移交，不表示场所已经平仓；`COMPLETED` 只表示闭合条件全部得到事实证明。确定失败不是平行终态：只有在 EXE 已证明没有持仓、开放/未知动作或保护责任后，才以 `COMPLETED` 和明确失败结果原因结束。

同一场所持仓若不能无歧义归属于一个激活，系统必须拒绝新激活，不得通过内部估算分摊。不同激活可以并发，但必须分别持有 CAP 互斥额度。

## 1.4 `PlanEvent` 与 `ProposedAction`

`ConditionJudgement` 是 TRADEPLAN 拥有的嵌入值，包含规则、来源身份、cutoff、输入摘要、`TRUE | FALSE | UNKNOWN | NOT_APPLICABLE | MISSED | INVALID`、理由和下一责任。例行无动作判断只以 CAS 更新 PlanActivation 中该规则的当前值和游标，不为每根 K 线建立事件；它没有独立 identity、claim 或生命周期。判断会改变激活状态、形成动作/用户责任，或激活以无入场结束时，最终判断值必须嵌入一个 `PlanEvent`，使恢复和 Review 能重建原因。

`PlanEvent` 是追加式业务决定记录，至少包含稳定事件身份、激活、规则、来源身份、来源截止点、输入摘要、理由码、可选 `ConditionJudgement`、可选 `ProposedAction` 或不动作原因、CAP 决定结果以及创建时间。EXE `ExecutionAction` 单向引用其来源 PlanEvent，PlanEvent 不保存反向动作引用。重复处理同一来源身份和相同输入摘要返回原事件；同一身份出现不同摘要时进入 `UNKNOWN`，禁止新增风险。

来源身份按事实类型稳定生成：

- K 线：`activation_id + rule_id + bar_type + bar.ts_event`；
- 时间：`activation_id + rule_id + persisted_deadline`；
- 成交或账户事件：`activation_id + rule_id + DAT source_class/source_object_id/source_sequence-or-version`；该身份不含 VenueFact content_digest，摘要另存，同一来源不同摘要必须冲突而不是形成第二动作；
- 用户控制：稳定 `command_id`。

`ProposedAction` 是 `PlanEvent` 内的不可变值，不是独立记录族。TRADEPLAN 从策略的 `StrategyProposal`、持久 deadline、场所事实或稳定用户 `Command` 规范化形成它；它包含不可变 `environment_id`、动作类别、instrument、方向、数量或 close-position 语义、订单类型、价格/触发价、有效期、reduce-only、来源责任和因果引用。它只表达尚待 CAP 检查的领域拟执行内容；CAP 批准并由 EXE 建立同环境 `ExecutionAction` 后才可能发生场所写入。

DEMO 与 LIVE 的 ProposedAction 使用完全相同的形成、去重、摘要和计划引用规则。差异只来自激活绑定的环境身份和经 CAP 验证的授权效力；TRADEPLAN 不根据环境分支到不同执行对象、repository 或状态函数。模拟盘的首要复盘目标是系统流程与机制，策略行为次之；该证据边界由 OUT 展示，不改变 ProposedAction 语义。

---

# 2. 策略组件使用契约【TRADEPLAN-AUTO-CMP-001】

## 2.1 装载与回调

Executor 内唯一 `TradingNode` 的 `Controller` 按运行中的 `PlanActivation` 动态装载同一代码构建中的 `HalphaStrategyAdapter`，并组合固定的纯策略逻辑类。每个激活一个 `StrategyId`；订阅、K 线聚合、指标更新和定时回调由 NautilusTrader 提供。Halpha 只把已核验参数、持久 deadline 和当前激活快照注入适配器/纯逻辑边界。

适配器 callback 必须显式把纯逻辑产生的零个或一个 `StrategyProposal` 送入 Halpha proposal sink；TRADEPLAN 才能把它规范化为 `ProposedAction`。生产代码静态检查和运行测试必须证明纯逻辑代码不能导入或调用任何 NautilusTrader 订单写入口，只有 EXE 调用适配器私有已持久动作门。

## 2.2 恢复

本契约定义 `MANUAL_PLAN_RESUME` 的稳定计划恢复行为，具体建设阶段是否选择该模式由 L4 记录。Executor 连续性中断或替换、主机重启，或者 PostgreSQL 写入连续性丢失时，所有未完成且未进入 `USER_TAKEOVER` 的 PlanActivation 必须在任何策略 callback、READY 动作领取或新场所写之前以 CAS 进入 `run_state=PAUSED`、`pause_reason=WRITER_CONTINUITY_LOST`。App、浏览器、SPA 静态资源或 NotificationDispatcher 单独重启不暂停仍连续运行的 Executor。

暂停后 Executor 先完成单实例门、读取权威状态、框架启动和只读场所核对，再从 `PlanActivation` 恢复游标、deadline 和原动作身份。允许保存迟到事实、查询原 UUID、推进只读核对和暴露保护缺口；在用户选择前不得恢复策略 callback，也不得新建保护、撤单、减仓、退出或增险场所写。场所已经存在的订单和原生保护继续由场所承担。框架缓存、timer 或 Strategy 内存字段不能单独证明某条件已消费、某动作已获授权或某激活已结束。

用户只能通过稳定命令选择：`RESUME_ACTIVATION` 在全部当前核对和原授权仍有效时清除本次连续性暂停并恢复同一激活；`EXIT_STRATEGY` 不先恢复增险判断，直接把计划推进到退出责任；`USER_TAKEOVER` 按既有接管规则冻结并移交。`RESUME_ACTIVATION` 不解除用户停用、CAP `ALL_WRITES`、最大损失、退出、授权撤销/到期或接管，也不创建新的 MachineAuthorizationVersion、PlanAllocation、PlanActivation、进程、worker 或数据库 epoch。

策略停止使用不管理场所订单的停止语义。正常结束仅在闭合证据成立后移除实例；用户接管先持久化责任转移，再停止实例，且不得由框架自动撤单或平仓。

## 2.3 可接受的组件妥协

通用指标、K 线边界、timer 和回调顺序采用经资格验证的 NautilusTrader 语义，不维持 Halpha 平行实现。只有框架缺失会破坏一次性周期、持久身份、额度、安全或恢复正确性时，才允许最薄的 gateway 补充；补充不得复制框架行情、订单或状态机。

---

# 3. 生命周期与不变量【TRADEPLAN-AUTO-LIF-001】

## 3.1 固定与激活

激活在一个本地事务中校验固定版本、策略可用性、事实新鲜度、场所映射、CAP 账户边界、互斥额度和机器授权，创建 `PlanActivation` 并记录激活事件。凡场所仓位不能原生区分激活，或计划允许作用于整个 instrument 的动作，TRADEPLAN 必须对 `(environment, account, instrument)` 建立活动范围唯一约束，从激活建立持续到闭合并释放额度；即使两个计划都尚未成交，也不得在同一范围并存。激活前还必须按下位支持范围证明该范围没有会混淆归属的既有持仓、外部、开放或结果未知责任。任何输入未知或归属歧义都拒绝激活；不得先启动策略后补额度。当前场所、模式和精确前置查询由 L4 固定。

活动期间检测到无法映射到本激活的订单、成交或仓位变化时，立即禁止新增风险并进入 `UNKNOWN`，保留已经存在的场所保护，且不得新建会作用于整个 instrument 的 close-position 动作；系统形成可见责任，等待用户选择退出或用户接管。该范围只有在场所持仓为零、所有订单与动作责任闭合并释放额度后才可再次激活。

## 3.2 持续判断

每个回调只读取明确截止点内的框架事件和 Halpha 激活快照。缺口、迟到修正或输入冲突不得合成事实，也不得追溯补开仓；它们形成明确不动作或 `UNKNOWN` 事件。减险、保护和用户控制可按固定失败规则继续，但不得借此增加暴露。

首次成交前，策略可在同一交易周期内按固定规则取消和替换未成交入场单。任何替换都必须经过新的 `PlanEvent → CAP → ExecutionAction`，且总目标暴露不变。首次成交后不得重置周期锁存；完全平仓后不得再次入场。

每个允许增险的有效期必须固化为 `PlanActivation` deadline。deadline 到期形成一个幂等 `PlanEvent`，立即禁止新入场，并对全部仍可能增险的开放普通或条件入场动作按原身份形成撤销/核对责任；`SUBMITTING | SUBMITTED_UNKNOWN` 只查询原身份，证明开放后才撤销。全部入场责任终态前不得关闭激活或释放额度；到期与成交竞争产生的晚到正成交只进入保护和退出/尾部清理，不恢复授权，也不形成第二入场。

## 3.3 最大损失

CAP 按本激活的已实现盈亏、未实现盈亏、资金费和手续费计算净结果；达到 `max_allowed_loss` 时原子锁存。TRADEPLAN 随即禁止新增风险并进入 `EXITING`，撤销剩余入场责任并要求退出全部本激活持仓。其他策略的盈亏不得抵扣或触发该阈值。

## 3.4 关闭

只有 EXE 已按其唯一闭合契约形成最终 `closure_digest`（包括适用的用户接管关闭摘要），且本计划不再有可形成新事件的责任时，TRADEPLAN 才能提交 `COMPLETED`、停止策略并请求 CAP 释放额度。TRADEPLAN 不复制或缩短 EXE 对持仓、普通/条件订单、ExecutionAction、成交、手续费、资金费、外部归属和 cutoff 的完整性要求。

确定失败且从未成交的首个策略激活，在 EXE closure digest 证明没有场所责任后，以 `COMPLETED` 和 `FAILED_NO_ENTRY/<reason>` 结束；进入写边界后的拒绝不自动创造第二次入场机会。存在未知结果时保持 `UNKNOWN`，等待同一身份查询、退出或用户接管。

---

# 4. 三类用户控制【TRADEPLAN-AUTO-CTL-001】

| 控制 | 事务效果 | 后续责任 |
|---|---|---|
| 停止新增风险 | CAP 在同一事务建立可由用户明确解除的 `StopStateVersion`；`PlanAllocation` 保持 `HELD`，不再形成或领取增险动作 | 对所有已知开放增险订单形成幂等撤单；`SUBMITTING/SUBMITTED_UNKNOWN` 只查询原身份，确认开放后再撤；Strategy 继续保护、减仓和平仓 |
| 退出策略 | 进入 `EXITING` 并复用停止新增风险的全部撤单责任，再形成退出全部持仓的动作 | Strategy 与 EXE 持续到事实证明平仓、兄弟订单均终态并清理 |
| 用户接管 | 先持久化 `USER_TAKEOVER`，冻结责任转移范围和切换 cutoff，再停止 Strategy | Halpha 不自动撤单、改单或平仓；继续只读核对冻结范围，用户承担场所操作；范围外新增/增险/反向活动仍为外部冲突 |

三类控制均通过稳定 `Command/Receipt` 身份处理。重复请求返回原结果；冲突请求不得覆盖较早的已生效责任变化。停止或退出的本地停增险状态一经提交立即生效，但在全部既有增险责任终态前 Receipt 只为 `PROCESSING`；无法确定时为 `UNKNOWN`，页面不得声称已停止全部入场可能。数据库或事实不可用时，不得把未持久化点击显示为已生效；用户接管和退出入口仍应可提交并明确返回 `UNKNOWN`。

“恢复新增风险”不是第四类停止控制，只以新版本解除由用户主动建立且明确可解除的 StopStateVersion；普通停止从未把 `PlanAllocation` 改为 `EXIT_ONLY`。它必须使用独立 Command，重新检查当前事实、保护、授权、额度和所有增险责任；最大损失锁存、`EXIT_ONLY`、`EXITING` 或 `USER_TAKEOVER` 不可恢复。同一激活恢复后仍遵守一次交易周期，不能重开已消费的入场机会。

并发控制按同一 PlanActivation 行锁和稳定 Command 身份串行化，优先级为 `USER_TAKEOVER > EXITING/MAX_LOSS > STOP_NEW_RISK > RESUME_NEW_RISK`。已停止新增风险仍可进入退出；任何未终结自动状态都可由用户接管；用户接管后不可恢复机器写。最大损失与用户退出复用同一撤销增险和全平责任，不能并发建立第二组退出动作；较低优先命令返回已有较高优先结果而不覆盖。

---

# 5. 条件责任与场所委托【TRADEPLAN-AUTO-CND-001】

来源条件责任只描述“谁持续监测产生该动作的源条件”：

- 本地 K 线、指标、复合价格/时间/成交量逻辑为 `HALPHA_MONITORED`；
- 场所原生条件本身被选作源条件时为 `VENUE_MONITORED`；
- 成交后安装保护、固定时间退出、用户控制、安全退出和撤单为 `NONE`。

动作可以提交市场单、限价单或场所条件单。下游订单是否由场所持续监测必须在 `ProposedAction` 的订单语义中单独表达，不能把“提交了条件单”反推成源条件由场所监测。

---

# 6. 并发、错误与公开能力【TRADEPLAN-AUTO-API-001】

公开能力最少包括：保存草稿、固定版本、激活、读取激活快照、消费策略 proposal、形成 PlanEvent/ProposedAction、提交三类控制和 `RESUME_ACTIVATION`、以 CAS 标记连续性暂停、提交关闭证据和查询时间线。所有写能力使用稳定身份、内容摘要、预期版本和数据库事务；同一激活的游标推进与计划事件写入必须原子化。任何 TRADEPLAN API 均不得写入或推进 ExecutionAction。

稳定错误类别至少包括：`PLAN_VERSION_CONFLICT`、`STRATEGY_UNAVAILABLE`、`PARAMETER_INVALID`、`FACT_UNKNOWN`、`FACT_CONFLICT`、`ATTRIBUTION_AMBIGUOUS`、`ALLOCATION_REJECTED`、`AUTHORIZATION_REJECTED`、`NEW_RISK_STOPPED`、`ACTION_PENDING_UNKNOWN`、`TAKEOVER_ACTIVE` 和 `CLOSURE_UNPROVEN`。错误必须区分确定拒绝与结果未知。

---

# 7. 最小验证契约【TRADEPLAN-AUTO-TST-001】

至少证明：

1. 同一 HalphaStrategyAdapter 与纯逻辑类可在实时 `TradingNode` 与 `BacktestEngine` 中产生相同规范化 `StrategyProposal`，并由 TRADEPLAN 映射为相同 `ProposedAction`；
2. Strategy 没有绕过 gateway 的场所写调用；
3. 同一来源身份幂等，不同输入摘要冲突且不新增风险；
4. 未成交入场单可按固定策略撤销重挂，但首次成交后完全平仓即永久结束；
5. 多激活额度互斥，其他策略盈亏不影响本激活最大损失；
6. 停止新增风险、退出和用户接管分别产生本文定义的责任效果；
7. Executor/主机/数据库写入连续性中断会在 callback、READY 领取和新场所写前把适用激活置为 `PAUSED`；App/SPA/通知单独重启不误暂停连续 Executor；只读核对可运行，`RESUME_ACTIVATION`、`EXIT_STRATEGY`、`USER_TAKEOVER` 三条恢复选择互不冒充，且不会建立新授权或额度；
8. 未知写结果不盲重放，闭合证据不足不释放额度；
9. 未接管时，场所外部动作或不可归属仓位不能被误计为本激活成果；接管后只有冻结范围内的风险减少或关闭活动可帮助证明关闭，仍不得冒充 Halpha 动作或确定损益；
10. DEMO 与 LIVE 都只由 TRADEPLAN 形成 ProposedAction，并经同一 CAP→EXE 链由 EXE 建立 ExecutionAction；TRADEPLAN 无执行动作写能力，环境身份不可修改且任何 Demo 状态不得迁移到 Live；
11. 被采用的框架语义没有 Halpha 平行实现。

---

# 8. 非目标、迁移与复杂度【TRADEPLAN-AUTO-MIG-001】

本文不建设策略 DSL、可视化流程编排、动态插件市场、通用作业平台、多次自动开仓循环或审批治理。长期可新增代码策略，但仍受同一激活、额度、事件、写边界和关闭契约约束。

本契约以四个记录族替代上一设计中的独立 `ConditionEvaluation` 及多类工作项；NautilusTrader 承担行情回调、定时器和策略实例生命周期。运行进程数不增加，不保留旧的逐动作确认或平行条件引擎。复杂度必须通过记录族、worker、定时循环和写路径数量对比证明不高于本次修订前。
