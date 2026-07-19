# Halpha 交易核心模块与运行边界

**文档编号：** HALPHA-SYS-002  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** SYS  
**语言版本：** zh-CN  
**上位文档或条款：** HALPHA-ARC-001、HALPHA-SYS-001  
**直接依赖：** HALPHA-ALP-002、HALPHA-TRADEPLAN-002、HALPHA-DAT-002、HALPHA-CAP-002、HALPHA-EXE-002、HALPHA-OUT-002、HALPHA-UX-002  
**适用纵向约束：** HALPHA-ENG-001、HALPHA-ENG-002  
**本文档负责：** 交易核心模块、两个产品进程、一个 PostgreSQL 产品、环境隔离、唯一场所写链、持久记录与工作器上限，以及 Windows 单机的启动、停止和重启边界  
**本文档不负责：** 重定义策略、计划、事实、资金、动作、复盘或交互语义；规定当前账户、策略、组件精确版本、主机配置、建设顺序或运行结论；建设通用流程、通知、恢复或治理平台  

---

# 0. 设计结论【SYS-AUTO-SUM-001】

Halpha 保持模块化单体、两个产品进程和一个 PostgreSQL 产品：`halpha-app` 提供一个 React 工作台与 API，`halpha-executor` 运行唯一 TradingNode、唯一 HalphaCoordinator 和各激活的策略适配器。只有 Executor 可以取得场所写凭据和调用场所写接口。

Demo 与 Live 使用同一产品代码、领域记录和执行链，但环境、账户、配置、凭据、数据和进程互斥彼此隔离。只读运行从同一组合中移除产品写入、私有账户、执行客户端和秘密，不建立第二产品。

进程间只通过已提交的 PostgreSQL 记录交接。数据库提交前先建立唯一 `ExecutionAction`，提交后才允许外部写。本设计不建设消息总线、Redis、微服务、第二数据库、第二操作入口、通用请求平台或恢复状态机。

# 1. 模块与所有权【SYS-AUTO-BND-001】

## 1.1 五个业务模块【SYS-AUTO-BND-001-REQ】

| 模块 | 负责的实现边界 | 持久记录 |
|---|---|---|
| `planning` | 代码策略、固定计划、激活、计划事件与动作提议 | `TradePlanVersion`、`PlanActivation`、`PlanEvent` |
| `venue_integration` | 场所事实、唯一动作记录、提交、查询、保护与核对 | `VenueFact`、`ExecutionAction` |
| `capital` | 激活和动作的确定性资金检查 | 无自有持久业务记录 |
| `outcomes` | 激活复盘 | `Review` |
| `user_workbench` | API、页面和领域只读投影 | 无自有持久业务记录 |

每项业务状态只由表中拥有模块写入。其他模块只能调用公开领域能力或读取已提交记录，不能直接修改私有表、复制状态机或把界面、日志和框架缓存提升为业务事实。SYS 只组合这些边界，不取得业务对象写权。

## 1.2 最小依赖方向【SYS-AUTO-DEP-001-REQ】

DAT 向策略、计划、资金和执行提供场所事实；ALP 向 TRADEPLAN 提供瞬态策略提议；TRADEPLAN 形成计划事件和动作提议；CAP 返回无副作用检查结果；EXE 拥有 `ExecutionAction` 和场所写；OUT 与 UX 只读消费已提交结果。用户请求从 UX 直接进入相应拥有领域，不经过通用中间平台。

跨模块原子操作由一个应用服务协调，同一事务内每个领域仍只通过自己的写入边界修改记录。任何不能随本地事务回滚的场所动作都必须留到事务提交后执行。

# 2. 两个产品进程【SYS-AUTO-RUN-001】

## 2.1 `halpha-app`【SYS-AUTO-RUN-001-REQ】

App 承载 React 静态资源、FastAPI、认证、领域请求和查询投影。改变状态的请求携带稳定 `request_id`、目标身份、预期版本和不可变内容；拥有领域把该身份保存到现有业务记录。相同身份和内容返回原结果，相同身份但不同内容返回冲突。

App 不创建 TradingNode，不持有 Binance 写凭据，不运行策略循环，也不提供绕过领域检查的管理写入口。页面不可用时，用户仍可使用交易所官方入口接管，但该外部入口不是 Halpha 的第二控制面。

## 2.2 `halpha-executor`【SYS-AUTO-RUN-002-REQ】

Executor 只运行一个 TradingNode、一个 HalphaCoordinator，以及每个仍需机器运行的 `PlanActivation` 对应的一个 `HalphaStrategyAdapter`。Coordinator 调用各领域公开能力，负责顺序、事务汇总、动作领取、结果映射、保护、核对和重启发现；它不能直接修改领域私有表。

Executor 是唯一场所写者。只有内容、环境、账户、激活和条款与已提交 `ExecutionAction` 完全匹配的适配器私有写门可以调用 OrderFactory 和执行客户端。不得按策略、账户或激活增加 TradingNode、进程、数据库或写路径。

App 与 Executor 通过同一环境的已提交记录协作。进程内通知或唤醒只能降低延迟；丢失后必须能从数据库重新发现，不得用同步 RPC、内存队列或框架消息总线承载唯一业务请求。

# 3. 唯一写链与组件边界【SYS-AUTO-WRITE-001】

## 3.1 唯一写链【SYS-AUTO-WRITE-001-REQ】

Demo 与 Live 的写入顺序相同：

```text
策略提议 / 到期时间 / 场所事实 / 用户领域请求
→ TRADEPLAN 形成 PlanEvent 与 ProposedAction
→ CAP 检查当前激活内资金限制和场所事实
→ EXE 建立唯一 ExecutionAction
→ 所有领域写入在同一 PostgreSQL 事务提交
→ Executor 私有写门调用场所
→ DAT 保存 VenueFact，EXE 与 TRADEPLAN 经各自边界推进结果
```

同一来源重复只能返回原 `PlanEvent` 或 `ExecutionAction`。提交结果未知时只按原外部身份查询，不建立第二动作或改用第二写路径。保护、撤单、减仓和平仓也必须经过同一链，但停止新增风险不能阻断这些可证明不增险的责任。

## 3.2 NautilusTrader 使用边界【SYS-AUTO-NT-001-REQ】

NautilusTrader 承担行情订阅、时钟、指标、TradingNode、Controller、订单对象、Binance 客户端和公开核对能力。Halpha 不复制其行情泵、指标引擎、订单状态机、缓存、重连或撮合回放。

框架缓存、组合、风险和核对结果只是技术输入，不能替代 `VenueFact`、`PlanActivation` 内资金限制或 `ExecutionAction`。组件失败或公开契约不足时，受影响写入停止并显示明确错误，不自动切换到自研或第二供应商实现。

# 4. 环境隔离【SYS-AUTO-ENV-001】

Demo 与 Live 分别绑定不可变环境身份、账户、端点、凭据引用、运行配置和数据库或隔离 schema。跨环境记录引用、默认回退、凭据复用和动作领取一律拒绝。Demo 缺失或失败时不能回退到 Live；Demo 成功也不授予 Live 能力。

只读运行只连接公开行情并输出可删除结果；它不取得产品数据库写入口、私有账户、交易秘密、执行客户端或 `ExecutionAction` repository。只读结果不能转换为激活、动作或场所事实权威。

一个 PostgreSQL 产品保存业务权威；环境隔离通过独立数据库或明确隔离的 schema 实现，不增加第二数据库技术栈。浏览器缓存、日志、邮件和量化框架存储都不是权威来源。

# 5. 持久复杂度上限【SYS-AUTO-CPLX-001】

## 5.1 六个物理记录族【SYS-AUTO-SCH-001-REQ】

产品只保留第 1.1 节列出的六个物理记录族。ALP 的策略定义随产品代码发布；CAP 是无状态检查能力；UX 不拥有业务记录。条件判断、动作提议、请求身份、资金限制与检查结果、停止原因、未知范围、核对引用和复盘后续问题嵌入实际消费它们的现有记录，不拆成独立表或事件平台。

物理子表、框架存储、文件或日志不得为被删除含义重新建立独立身份、领取、重试、游标或生命周期。只有出现无法由现有记录表达且已经有当前消费者的业务责任时，才能修改拥有领域契约后增加记录族。

## 5.2 一个持久工作器【SYS-AUTO-WORK-001-REQ】

唯一 Halpha 持久工作器是 Executor 内的 `HalphaCoordinator`。它从已有记录发现未结束激活、未决动作、保护、核对和复盘交接，不为每种责任建立扫描器。

TradingNode 的数据订阅、计时器、指标、事件、缓存和核对循环属于采用组件的进程内能力；Controller 与策略适配器属于激活内运行对象。它们都不取得独立 Halpha 任务身份、领取权或持久检查点。

# 6. Windows 单机生命周期【SYS-AUTO-WIN-001】

Windows 使用 Task Scheduler 启动 App 和 Executor，并拒绝同一角色重叠运行。Executor 在读取写凭据或创建执行客户端前必须取得操作系统全局命名互斥体；失败时退出写运行。精确任务参数、互斥名称和凭据位置由 L4 记录。

Executor 启动或非计划重启时按以下顺序处理：取得互斥体；验证环境、数据库、迁移和非秘密配置；启动 TradingNode 并读取场所当前事实；把每个未结束激活、未决 `ExecutionAction` 与场所订单和持仓核对。只有身份、条款、事实和开放责任一致时，才重建适配器并继续原激活。

无法一致核对时，通过拥有领域把具体结果记为 `UNKNOWN` 并不可逆停止该激活新增风险；随后只允许查询、保护、撤单、减仓、退出或用户接管。这里不增加恢复状态、恢复命令、运行世代、租约或第二写门。

正常停止先阻止形成新的增险动作，保留并记录在途责任，再按组件公开生命周期依次停止策略适配器、Coordinator 和 TradingNode。数据库不可用时不得以内存继续形成业务记录或场所写；进程恢复不能复活过期、已停止或已接管的激活。

# 7. 用户控制与结束【SYS-AUTO-CTL-001】

停止新增风险、退出策略和用户接管直接调用 TRADEPLAN 拥有的领域请求。请求结果由 `PlanActivation` 和 `PlanEvent` 表达，不建立通用控制记录或第二流程。

用户接管必须先持久化，随后停止并移除对应策略适配器，且不自动撤单或平仓。Coordinator 继续只读核对迟到结果；只有 DAT 与 EXE 按同一事实截止点证明持仓、订单和动作责任全部确定结束，TRADEPLAN 才能结束激活并允许同一真实账户建立新激活。用户接管本身不等于结束，也不能恢复该激活的机器写入。

# 8. 最小验证契约【SYS-AUTO-TST-001】

实现至少证明：

1. 产品只有 App、Executor、一个 TradingNode、一个 Coordinator、一个 PostgreSQL 技术栈和一条场所写链；
2. App 无场所写凭据或交易节点，策略逻辑无法绕过已持久动作门；
3. Demo 与 Live 共用领域代码和动作链，但环境、账户、数据、凭据和动作不能互相引用；
4. 重复请求、重复回调和重启不会产生第二激活、第二 `ExecutionAction` 或第二次场所提交；
5. 数据库事务失败时没有场所写，场所结果未知时只查询原身份；
6. 重启先核对，一致时继续，不一致时停止新增风险且不出现恢复状态机；
7. 停止新增风险不阻断保护和退出，用户接管不自动撤单或平仓；
8. PostgreSQL 中只有六个产品记录族，Halpha 只有一个持久工作器，被删除的平台概念没有换名复活；
9. Task Scheduler 与全局互斥体共同阻止双 Executor 写入，正常停止和数据库故障均保持可识别结果。

# 9. 明确不建设与 L4 边界【SYS-AUTO-NON-001】

不建设第二 TradingNode、自研行情或订单引擎、策略插件平台、消息总线、Redis、微服务、独立行情/保护/核对服务、第二产品数据库技术栈、平行场所写适配器、通用工作流、恢复状态机或第二操作入口。

L4 只记录当前精确组件版本、环境与账户、数据库/schema 绑定、Windows 主机和 Task Scheduler 配置、秘密注入、当前运行实例、检查结果和已知限制。本 L3 不声明这些当前已经部署或可用。
