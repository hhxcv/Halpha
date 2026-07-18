# Halpha 机器授权交易核心模块与环境运行实体边界

**文档编号：** HALPHA-SYS-002  
**版本：** v0.9.0  
**文档状态：** ACCEPTED  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** SYS  
**语言版本：** zh-CN  
**批准人：** Halpha 项目所有者  
**接受时间：** 2026-07-18T07:01:20+08:00  
**替代版本：** HALPHA-SYS-002@v0.8.0  
**上位文档或条款：** HALPHA-ARC-001 v1.9.0；HALPHA-SYS-001 v1.6.0  
**直接依赖：** HALPHA-ALP-002 v0.5.0、HALPHA-TRADEPLAN-002 v0.10.0、HALPHA-DAT-002 v0.8.0、HALPHA-CAP-002 v1.2.0、HALPHA-EXE-002 v1.2.0、HALPHA-OUT-002 v0.8.0、HALPHA-UX-002 v0.11.0  
**适用纵向约束：** HALPHA-ENG-001 v1.6.0  
**本文档负责：** 交易所模拟盘与真实资金写环境共用代码的机器授权交易核心模块边界、真实只读 profile 的能力裁剪、每环境两个运行实体、环境 composition root 与实例隔离、NautilusTrader 装载、每次激活一个 HalphaStrategyAdapter 的生命周期、跨模块持久交接、持久工作器、启动停止恢复、环境等价清单和运行复杂度上限  
**本文档不负责：** 定义策略、计划、事实、资金、动作、复盘或交互的业务语义；规定当前阶段、场所、账户、策略参数、NautilusTrader 精确版本或配置、主机实例、凭据、通知提供方和资格化结果  

---

# 0. 设计结论【SYS-AUTO-SUM-001】

交易核心长期保持五个业务模块、两种 Halpha 进程角色、一个 PostgreSQL 产品和每个写环境一条场所写链。DEMO 与 LIVE_WRITE 从同一构建创建分离的 `EnvironmentRuntime` 实例；每个实例固定一个 environment profile、数据库、账户、端点和凭据引用，绝不共享可变业务状态。LIVE_READ_ONLY 是资格化 composition，只实例化同一个 `halpha-executor`、TradingNode、data client、Controller、HalphaStrategyAdapter 和纯逻辑，不启动 App、NotificationDispatcher 或产品数据库；它只连接无需账户身份的场所公开行情，并固定 `authority_class=NO_TRADING_AUTHORITY`。其 composition root 不解析或注入 Binance 凭据，不查询账户佣金，也不创建数据库连接、HalphaCoordinator、ExecutionAction repository、execution client 或私有动作能力，只输出可删除的资格证据。它没有账户访问、CAP/EXE 授权、场所写链或产品权威状态。该 composition 不得与 DEMO/LIVE_WRITE 产品实例并发；精确启用的实例数由 L4 决定。NautilusTrader 是 `halpha-executor` 内的量化交易框架，不是第三进程角色、第二产品事实源或第二授权者。

```text
halpha-app
  React UI / 同进程服务端 /operations / API / PostgreSQL 应用边界 / Notification dispatcher

halpha-executor
  唯一 TradingNode
    ├─ Binance DataClient + ExecClient
    ├─ Controller
    ├─ 每个未闭合且非 USER_TAKEOVER 的 PlanActivation 一个 HalphaStrategyAdapter
    └─ 一个 HalphaCoordinator
```

生产中只有两个具有跨重启 Halpha 责任、领取或恢复语义的持久工作器：Executor 内的 `HalphaCoordinator` 和 App 内的 `NotificationDispatcher`。框架的数据订阅、K 线、计时器、指标、订单对象、事件、cache、portfolio、risk 与 reconciliation 都是进程内库能力，不另计 Halpha 工作器，也不得取得独立 Halpha checkpoint、claim、退避或产品状态。

---

# 1. 模块、进程与事实权威【SYS-AUTO-BND-001】

## 1.1 五个业务模块【SYS-AUTO-BND-001-REQ】

| 模块 | 语义分区 | 长期责任 |
|---|---|---|
| `planning` | ALP、TRADEPLAN | 随构建发布的代码策略依据、固定计划版本、一次激活、计划事件和 ProposedAction |
| `venue_integration` | DAT、EXE | 环境限定场所事实、ExecutionAction、每环境唯一场所写入、保护、核对、未知与闭环证据 |
| `capital` | CAP | 账户边界、机器授权、计划独占额度、动作检查和停用 |
| `outcomes` | OUT | 每次激活的复盘与改进交接 |
| `user_workbench` | UX | 用户任务、命令、回执、通知和只读投影 |

ALP 与 TRADEPLAN、DAT 与 EXE 可以共享代码模块，但不得共享可变领域对象或越权写入。SYS 与 ENG 只约束组成和工程边界，不形成第六业务模块。

业务模块的允许依赖方向与拓扑序保持无环：`DAT → ALP/TRADEPLAN/CAP/EXE`，`ALP → TRADEPLAN → CAP → EXE → OUT → UX`；这不是各文档头直接读边的穷举清单。EXE 为消费 ALP 拥有的 `HalphaStrategyAdapter` 私有已持久动作门而直接依赖 ALP，OUT/UX 还可按各自文档头只读消费前序领域投影。执行结果回到计划、用户命令进入计划以及复盘读取历史，均通过对方拥有的公开边界与稳定记录引用完成，是运行反馈而不是反向代码依赖。ENG 提供纵向组件约束，SYS 只负责组合这些模块；两者不取得业务对象写权。

## 1.2 两个运行实体【SYS-AUTO-RUN-001-REQ】

`halpha-app` 只取得 PostgreSQL、UI/API 和通知发送所需能力。它处理用户命令、查询投影、计划激活事务和通知投递；同一 FastAPI 进程还公开服务端渲染的本地主机 `/operations` 有限操作入口。该入口复用同一认证、CSRF、`Command`、`Receipt`、领域处理器与数据库，不形成第二控制面、第二认证域、第二 API、第三进程或独立业务状态；不得装载 TradingNode、场所真实写凭据、行情节点或第二套条件评价循环。

`halpha-executor` 是唯一装载 TradingNode 和场所读写凭据的进程。一个 TradingNode 同时承载数据与执行客户端；Controller 按未闭合且未进入 `USER_TAKEOVER` 的 `PlanActivation` 创建、启动、停止并移除一个对应 HalphaStrategyAdapter；`HalphaCoordinator` 负责调用各领域公开应用边界，协调持久交接、结果映射、最大损失检查、保护、闭环和恢复。协调器只拥有顺序与事务汇总；TRADEPLAN、CAP、DAT、EXE 和 UX 各自写入自己拥有的记录，协调器不得直接修改任何模块私有表。不得为每个策略创建独立 TradingNode、数据库或进程。

App 与 Executor 只通过同一环境的 PostgreSQL 已提交记录协作。唤醒可以丢失，恢复必须能从权威记录重新发现；不得用同步 RPC、进程内队列、框架 MessageBus、Redis 或外部通知承载唯一业务请求。

## 1.3 NautilusTrader 使用边界【SYS-AUTO-NT-001-REQ】

Halpha 采用 NautilusTrader 及其 Binance 适配器的公开契约承担以下通用能力：

- DataEngine 的订阅、历史读取与 K 线交付；
- Clock/Timer 的运行期定时触发；
- 已采用的公开指标，包括 ATR 与 Donchian 能力；
- OrderFactory、订单对象、Strategy 订单命令和场所订单事件；
- TradingNode、Controller、Cache、Portfolio、RiskEngine，以及启动和连续 reconciliation。

Halpha 不复制这些能力的内部类、消息、缓存、连接、重连、订单状态机或 reconciliation 算法。框架 Cache 保持进程内技术投影；框架数据库、Redis、catalog 或 event store 不作为 Halpha 恢复前置或产品权威。当前精确版本、导入路径、配置值、平台与适配器资格结果由 L4 固定。

框架 RiskEngine 只允许增加更保守的技术拒绝，例如订单速率、单笔名义值或工具限制；它不能授予 CAP 已拒绝的动作，不能替代每次激活独占额度、最大允许损失或 Decimal 归属计算。框架 Portfolio/PnL 只作技术投影和诊断，不成为 Halpha 的额度释放或闭环证据。

---

# 2. HalphaStrategyAdapter 与 HalphaCoordinator【SYS-AUTO-COORD-001】

## 2.1 HalphaStrategyAdapter 唯一提议输出【SYS-AUTO-STR-001-REQ】

每个 `HalphaStrategyAdapter(Strategy)` 固定引用一个 `PlanActivation`、纯代码策略摘要和参数摘要，其框架 StrategyId 由 `activation_id` 稳定派生并在重启后复用。适配器的框架 callback 显式调用不继承 Strategy 的纯逻辑对象，并把 ALP 定义的零个或一个瞬态 `StrategyProposal` 送入 sink；不依赖 callback 返回值。纯逻辑对象不能取得订单或场所写 API，适配器私有已持久动作门与静态测试共同证明策略逻辑无法绕过。

TRADEPLAN 把 `StrategyProposal`、持久 deadline、场所事实或用户 `Command` 规范化为同一 `PlanEvent`，并在其中嵌入 TRADEPLAN 拥有的 `ProposedAction`。稳定来源身份和输入摘要必须分开：同一来源与相同摘要重复返回原事件，同一来源出现不同摘要或条款进入冲突，不能借改变摘要形成新的动作身份。SYS 不重定义其字段或去重算法。

无动作评价只以 CAS 推进 `PlanActivation.last_bar_cursor`、计时期限或当前未知摘要；只有会改变计划或产生动作的决定才追加 `PlanEvent`。错过的增险窗口和已判未知的历史输入不得在恢复后追溯补发。

同一策略代码、参数与 `StrategyProposal` 契约必须可在 BacktestEngine 中运行。回测使用内存网关完成同样的 TRADEPLAN 规范化、PlanEvent、CAP 和动作映射；DEMO 与 LIVE_WRITE 都使用同一持久网关、应用服务和 ExecutionAction 流程，不维护第二份策略或执行实现。LIVE_READ_ONLY 复用到同一 `StrategyProposal` 边界后只进入不可提交证据 sink，不调用 TRADEPLAN/CAP/EXE 持久网关，也不建立产品动作。

DEMO 与 LIVE_WRITE 的持久动作都由 EXE 拥有的环境限定 `ExecutionAction` 表达，并使用同一 schema、私有可写 repository、应用服务、状态机和场所执行客户端构造路径。TRADEPLAN 只形成 ProposedAction。两个写环境在 composition root 形成分离实例；Demo 实例不得取得真实凭据或真实端点，Live 写实例不得消费 Demo 授权、动作或事实。LIVE_READ_ONLY 不得创建 `ExecutionAction`、PlanEvent 或其他产品记录，观察证据不转换为 Live 状态。

## 2.2 每环境唯一且跨环境等价的写链【SYS-AUTO-WRITE-001-REQ】

DEMO 与 LIVE_WRITE 唯一允许的写顺序相同：

```text
StrategyProposal / 持久 deadline / 场所事实 / 用户 Command
→ HalphaCoordinator 调用 TRADEPLAN 公开边界形成含 ProposedAction 的 PlanEvent
→ 调用 CAP 公开边界完成检查
→ 调用 EXE 公开边界建立 ExecutionAction
→ 各所有者结果在所属环境同一事务提交 PostgreSQL
→ 对应 HalphaStrategyAdapter 的私有已持久动作门使用 OrderFactory
→ 已资格化的白名单 Strategy 基类写方法
→ 场所
```

HalphaCoordinator 是应用协调者，不是 PlanEvent、PlanAllocation 或 ExecutionAction 的共同所有者：TRADEPLAN、CAP 与 EXE 分别通过自己的公开边界判定并写入各自记录，协调器只汇总同一环境事务的成功或回滚，任何模块都不得直接写另一模块私有表。CAP 接受或拒绝的输入摘要与结果嵌入 `PlanEvent` 或 `ExecutionAction`，不建立独立检查记录。只有已提交的 ExecutionAction 可以进入框架写接口。框架事件、Timer、reconciliation、用户命令和通知都不能跳过该链自动生成场所写入；保护、风险减少和平仓同样先形成明确 PlanEvent/ExecutionAction，禁止调用会在框架内部衍生未持久动作的 `market_exit`。

每个激活由 HalphaCoordinator 串行推进；不同账户工具可并行，但 TRADEPLAN 的活动范围唯一约束和 CAP 分配必须先阻止同一环境、账户、工具的责任混合。Controller/HalphaStrategyAdapter 生命周期不能改写计划或额度状态。

## 2.3 启动、持续运行与恢复【SYS-AUTO-REC-001-REQ】

每个 EnvironmentRuntime 的 Executor 启动后先取得该环境单实例写门，启动唯一 TradingNode 并完成框架启动 reconciliation；随后 HalphaCoordinator 从该环境 PostgreSQL 重建未结束激活和 ExecutionAction，仅为其中未进入 `USER_TAKEOVER` 的激活重建对应 HalphaStrategyAdapter，并发现 `PlanActivation=COMPLETED` 但 Review 缺失或输入摘要落后的可派生 OUT 协调责任。适配器可以先订阅数据，但在 TRADEPLAN/CAP 的恢复条件和外部责任分类完成前不得输出可提交增险动作；已接管激活继续只读核对，已完成激活的复盘补齐不创建适配器，也不能回滚交易闭合或额度释放。

本契约定义 `MANUAL_PLAN_RESUME` 的稳定运行边界，具体建设阶段是否选择该模式由 L4 记录：Executor 连续写者丢失或被替换、Windows 主机重启，或 PostgreSQL 写连续性丢失后，所有未闭合且非 `USER_TAKEOVER` 的激活必须在注册策略 callback、宣布 READY 或形成任何新 Halpha 写动作前持久为 `run_state=PAUSED`、`pause_reason=WRITER_CONTINUITY_LOST`。仅 App、浏览器、React 静态资源或 `NotificationDispatcher` 重启不暂停仍连续运行的 Executor。暂停期间允许查询、场所核对、保存迟到事实和推进既有责任，但禁止形成新的 Halpha 场所写；不得借恢复创建新授权、额度、激活、进程、工作器、数据库 epoch、fencing token 或第二写路径。

恢复暂停只能由同一 `Command`/`Receipt` 契约中的 `RESUME_ACTIVATION`、`EXIT_STRATEGY` 或 `USER_TAKEOVER` 明确推进。`RESUME_ACTIVATION` 只清除本次写者连续性暂停，不能清除用户停止、授权撤销或失效、`ALL_WRITES`、用户接管、最大损失、过期、条款变化或未知事实；`EXIT_STRATEGY` 可直接进入已允许的撤单/保护/风险减少链，不得先恢复普通策略写入。严格证据自动续行属于不同恢复模式，必须由相应目标 L3 另行定义并由 L4 明确选择，不能从本契约推导为已支持能力。

DEMO/LIVE_WRITE 运行中保留组件场所事件与持续持仓 reconciliation；启动 reconciliation 负责初始技术重建。已持久 UUID 的持续订单核对由 HalphaCoordinator 在现有 ExecutionAction/保护/闭环循环中调用组件公开单订单查询，关闭会在连续无响应后合成本地终态的组件定时器。上述能力共同构成两个写环境共用的唯一核对实现；Halpha 不另建 reconciliation 工作器、状态机、claim 或 cursor。HalphaCoordinator 只消费其结果：通过 DAT 公开边界形成 `VenueFact`，通过 EXE 公开边界推进 `ExecutionAction` 和闭环证据，通过 TRADEPLAN 公开边界保存 PlanActivation 对这些结果的引用。LIVE_READ_ONLY 不装载执行 reconciliation；它只观察数据流连续性和不可提交策略输出。

每个未闭合且非 `USER_TAKEOVER` 激活一个 HalphaStrategyAdapter、且不注册框架外部订单技术认领，是本契约唯一拓扑；精确组件配置由 L4 固定。HalphaCoordinator 通过适配器私有已持久动作门，只对 environment_id、activation_id、UUID32 与不可变条款摘要精确匹配既有 ExecutionAction 的普通或算法订单执行已资格化的查询和取消；框架把重启对象标为 EXTERNAL 技术身份不改变该规则，也不构成产品认领。

人工/外部订单、未知 UUID、摘要冲突或框架合成事件不得证明本激活成交、盈亏或闭环，也不得被 Halpha 自动撤销；它们可以证明账户存在外部活动、必须停止增险并要求用户接管。当前 L4 选择若不能在无持久 cache 重启后重新装入、查询、取消并核对已知 UUID 的普通/算法订单，同时隔离未知 UUID，则当前实现方案拒绝；任何替代拓扑只能由受影响 L3/L4 目标文档形成候选版本后评审，不作为当前运行 fallback。

---

# 3. 持久记录与工作器上限【SYS-AUTO-CPLX-001】

## 3.1 十六个物理记录族【SYS-AUTO-SCH-001-REQ】

权威 PostgreSQL 只保留以下 16 个跨重启产品物理记录族：

| 所有者 | 记录族 |
|---|---|
| TRADEPLAN（4） | `TradePlanDraft`、`TradePlanVersion`、`PlanActivation`、`PlanEvent` |
| DAT（1） | `VenueFact` |
| CAP（4） | `AccountCapitalLimitVersion`、`MachineAuthorizationVersion`、`PlanAllocation`、`StopStateVersion` |
| EXE（1） | 环境限定 `ExecutionAction`：DEMO/LIVE_WRITE 使用同一 schema 与语义，EXE 是唯一写入所有者；LIVE_READ_ONLY 不建立该记录 |
| OUT（2） | `Review`、`ImprovementHandoff` |
| UX（4） | `Task`、`Command`、`Receipt`、`Notification` |

`PlanActivation` 吸收每条规则的最近 K 线游标、持久 deadline、当前 `ConditionJudgement`、`protection_state=NONE | WORKING | UNKNOWN | GAP | CLOSED`、CAP 权威引用和动作 `closure_digest` 引用；不另存最大损失锁存或停增险权威。`PlanEvent` 吸收 `ProposedAction`、来源身份、输入与 CAP 结果摘要。`PlanAllocation` 吸收损失事实 cutoff 与最近资金费查询 cutoff。`ExecutionAction` 物理族用数据库约束固定 `environment_id`、`authority_class`、profile、账户和归属，只由 EXE 的一个私有可写 repository、应用服务和状态推进函数写入；它吸收两个写环境适用的客户端 UUID32、提交证据、结果未知、保护与单动作闭合证据。TRADEPLAN 没有 ExecutionAction 写入口。DAT 定义的完整 `FactUnknownValue` 只嵌入实际承受限制的上述宿主，不形成独立记录。LIVE_READ_ONLY 的追加式观察文件是资格制品，不属于上述 16 个产品记录族，也不能被任何模块作为权威输入读取。

因此不建立 `ConditionEvaluation`、`Observation`、`FactWindow`、`FactUnknown`、`FactCorrection`、`IngestionCheckpoint`、`CapitalAuthorizationCheck`、`WriteControl`、`SubmissionAttempt`、`ProtectionTask` 或 `ReconciliationItem`。这些含义分别由上述宿主记录的版本化字段承担；不得在物理子表、事件表或框架存储中恢复独立 identity、claim、cursor 或生命周期。

ALP 的代码策略定义和证据随唯一构建发布，不复制为运行时记录族。Notification 自身承担 outbox；不建立第二通知记录。

## 3.2 两个持久工作器【SYS-AUTO-WORK-001-REQ】

| 工作器 | 进程 | 唯一持久责任 |
|---|---|---|
| `HalphaCoordinator` | Executor | 重建 HalphaStrategyAdapter、消费 proposal/框架事件、经各所有者公开边界协调 PlanEvent→CAP→ExecutionAction、提交、事实映射、保护、最大损失、闭环、恢复与只读核对 |
| `NotificationDispatcher` | App | 领取已有 Notification、发送并保存投递结果 |

数据订阅、K 线生成、Timer、指标、框架事件处理、启动/持续 reconciliation 和 Controller 生命周期没有独立 Halpha checkpoint 或退避，不计持久工作器。OUT 归集、Task/Notification 形成和额度释放由原业务事务或 HalphaCoordinator 的闭环分支调用；`PlanActivation=COMPLETED` 且 Review 缺失或输入摘要落后就是现有协调器可重复发现的责任，不另存 claim/cursor，也不形成新扫描器。

相对于本契约重写前的 26 个记录族和最多 5 个持久工作器，本设计收缩为每个写环境 16 个物理记录族和 2 个持久工作器；业务模块仍为 5、进程角色仍为 2、权威数据库产品仍为 1、每写环境写链仍为 1，不以新增平台或第二实现换取环境隔离。Demo/LIVE_WRITE 使用同一 ExecutionAction 所有权和实现，分离的是 EnvironmentRuntime 实例、profile、端点、凭据引用、数据库与账户。LIVE_READ_ONLY 不增加记录族、持久工作器、进程、数据库或写链。

---

# 4. 激活、停止、退出与用户接管【SYS-AUTO-CTL-001】

计划激活仍由 App 在一个 PostgreSQL 事务中调用 TRADEPLAN 与 CAP 公开边界，固定计划版本、机器授权、互斥 PlanAllocation 和 PlanActivation；任一失败全部回滚，各模块只写自己的记录。事务提交后才允许 HalphaCoordinator 创建并启动 HalphaStrategyAdapter。重复激活命令按原命令身份返回原结果，不创建第二激活。

“停止新增风险”只使 HalphaStrategyAdapter 的增险 proposal 不可提交；既有查询、保护、撤单和风险减少责任继续。“退出策略”由代码策略或用户命令形成显式 PlanEvent 和本环境的 `ExecutionAction`，不调用框架 `market_exit`。

用户接管必须先持久化。HalphaCoordinator 观察到接管后，以不管理场所订单的行为停止并移除对应 HalphaStrategyAdapter；停止时不得自动撤单、补保护或平仓。TradingNode 和 HalphaCoordinator 继续只读查询与 reconciliation，只有 EXE 的最终 `closure_digest` 成立才允许通过 CAP 公开边界释放额度。同一激活不得恢复自动写入；再次自动交易必须新激活。实现该行为的精确组件配置属于 L4。

---

# 5. Windows 单机生命周期【SYS-AUTO-WIN-001-REQ】

Windows 单机使用 Task Scheduler 管理 App 与 Executor，并配置为拒绝同一运行实体的重叠启动。Executor 在加载真实写凭据和启动 TradingNode 前还必须通过 pywin32 取得一个操作系统全局作用域的命名互斥体；不能取得时只退出或只读诊断，不启动第二写者。精确调度属性和互斥名称由 L4 固定。操作系统在进程结束时释放互斥体，因此不建立数据库 `WriteControl`、租约、fencing token 或心跳生命周期。

正常停止必须由进程显式停止 HalphaStrategyAdapter、HalphaCoordinator 和 TradingNode，并按已资格化的组件公开生命周期顺序等待资源释放；不得依赖 Unix 信号处理。非计划退出由 Task Scheduler 重启，但采用 `MANUAL_PLAN_RESUME` 的新进程仍须先取得互斥体、完成启动 reconciliation，并按该模式的规则持久暂停开放激活，等待用户显式选择恢复激活、退出策略或用户接管。

所属环境数据库不可用时不得以内存继续形成 PlanEvent、ExecutionAction 或场所写入。通知失败不回滚交易状态，也不成为授权或恢复依据。

---

# 6. 验证契约【SYS-AUTO-TST-001-REQ】

接受前至少证明：

1. 生产拓扑只有 App、Executor、一个 TradingNode、一个 HalphaCoordinator 和每个未闭合且非 `USER_TAKEOVER` 激活一个 HalphaStrategyAdapter；没有 App TradingNode、第三进程、Redis、消息总线、框架持久 cache 或 event store；
2. 纯逻辑评价每次只能产生零个或一个 `StrategyProposal`，框架 callback 显式送入 sink；静态与运行测试证明纯逻辑无法取得任何订单写 API；
3. 同一 HalphaStrategyAdapter、纯逻辑源码、参数和 `StrategyProposal` 在 BacktestEngine、Demo、LIVE_READ_ONLY 与 LIVE_WRITE 节点中一致；Demo/LIVE_WRITE 都经同一 TRADEPLAN→CAP→EXE 链由 EXE 建立同一 `ExecutionAction`，环境等价清单证明源代码摘要、应用服务、schema、repository、状态机和执行客户端类/工厂路径一致；LIVE_READ_ONLY 能力裁剪清单与运行测试证明只到不可提交 proposal sink，且 Binance 凭据、账户佣金查询、execution client、数据库连接、HalphaCoordinator、动作 repository、私有动作能力和场所写入均不存在；
4. PlanEvent、CAP 结果与 ExecutionAction 在所属环境同一事务成功或失败，提交前不存在任何场所写；
5. Controller 可创建、启动、停止、移除 HalphaStrategyAdapter，重启后按开放 PlanActivation 重建且不补发错过的增险窗口；
6. 启动 reconciliation、场所事件、持续持仓核对及按已持久 UUID32 的公开单订单查询覆盖普通订单、条件订单、成交、部分成交和持仓；组件不得因查询无响应生成会阻断后来正向事实或取消的不可逆技术终态；不注册框架外部订单技术认领，无持久 cache 重启后仍可按 activation_id/UUID32 恢复、查询和取消呈 EXTERNAL 技术身份的已知普通/算法订单并核对终态，未知 UUID 不被误撤，失败即拒绝本契约而非切换第二拓扑；
7. 用户接管先持久化再以不管理场所订单的行为停止 HalphaStrategyAdapter，不自动撤单或平仓，节点继续只读核对；
8. Task Scheduler 的重叠启动拒绝行为与操作系统全局作用域命名互斥体共同阻止双 Executor 写入；Executor/主机/PostgreSQL 写连续性丢失后开放激活在 callback、READY 和新写前进入 `PAUSED`，App/浏览器/静态资源/通知进程单独重启不误暂停连续 Executor；三个显式恢复选择及不可清除的安全停止可验证；
9. PostgreSQL 中只有 16 个物理产品记录族，生产只有 2 个 Halpha 持久工作器；被删除对象没有以子表、框架存储、隐藏 cursor 或后台循环复活；
10. `/operations` 与 React 工作台同属 `halpha-app`，复用同一认证、CSRF、Command/Receipt、领域处理器与数据库；SPA 静态资源不可用时仍可查看关键恢复状态并提交允许的有限操作，且没有第二控制面；
11. 环境 profile 允许差异仅限端点、凭据引用、数据库、账户、环境/授权效力和经 L3 明列的场所配置；环境身份不可修改，Demo 凭据/状态不能触达或迁移到 Live。当前精确 NautilusTrader、场所适配器与 Windows 平台未通过 L4 资格化时，系统拒绝对应环境写入而不启用自研平行实现。

---

# 7. 明确不建设与 L4 边界【SYS-AUTO-NON-001-REQ】

不建设第二 TradingNode、自研行情/订单/reconciliation 引擎、策略 DSL、插件平台、消息总线、Redis、微服务、独立行情/保护/核对服务、框架 event store、第二产品数据库或平行场所写适配器。

L4 只选择精确依赖版本与构建摘要、场所和账户、框架配置、Windows 主机与 Task Scheduler 实例、凭据、通知提供方、阈值、建设顺序、限制和资格化证据；本 L3 不声称这些当前已经可用。
