# Halpha 机器授权交易核心技术与环境等价构建边界

**文档编号：** HALPHA-ENG-002  
**版本：** v0.8.0  
**文档状态：** ACCEPTED  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** ENG  
**语言版本：** zh-CN  
**批准人：** Halpha 项目所有者  
**接受时间：** 2026-07-18T07:01:20+08:00  
**替代版本：** HALPHA-ENG-002@v0.7.0  
**上位文档或条款：** HALPHA-ARC-001 v1.9.0；HALPHA-ENG-001 v1.6.0  
**直接依赖：** 无 L3 直接依赖；本文件把上位工程约束投影为组件使用契约  
**能力消费者：** HALPHA-ALP-002 v0.5.0；HALPHA-TRADEPLAN-002 v0.10.0；HALPHA-DAT-002 v0.8.0；HALPHA-CAP-002 v1.2.0；HALPHA-EXE-002 v1.2.0；HALPHA-OUT-002 v0.8.0；HALPHA-UX-002 v0.11.0；HALPHA-SYS-002 v0.9.0（不是反向直接依赖）  
**适用纵向约束：** HALPHA-SYS-001 v1.6.0  
**本文档负责：** 长期采用的核心技术组件及使用契约；交易所模拟盘与真实资金写环境的同源构建、统一执行客户端路径、真实只读 profile 的能力裁剪、profile 允许差异和环境等价清单；量化运行、Web、数据、认证、前端、通知、Windows 宿主、备份和测试能力的第三方复用边界；Halpha 必须保留的最小产品语义与数值边界；依赖、构建、迁移、回退和组件失败结果  
**本文档不负责：** 重定义策略、计划、事实、资金、动作、复盘或交互业务语义；规定当前精确版本、制品哈希、参数、主机、凭据值、部署命令、建设顺序、资格化结论或运行可用性  

---

# 0. 技术结论【ENG-AUTO-SUM-001】

Halpha 采用一套可锁定的 Python 后端技术线、一套 React 前端技术线、一个 PostgreSQL 产品和一个 NautilusTrader 量化交易栈。DEMO 与 LIVE_WRITE 从同一源代码、锁文件和构建制品创建分离实例，使用同一 TRADEPLAN→CAP→EXE→DAT→OUT 应用路径、ExecutionAction schema/repository/state machine 和 NautilusTrader Binance execution client 类/工厂路径，差异只存在于受控 profile。LIVE_READ_ONLY 是同一构建的 Executor-only 资格化 composition，不启动 App/通知/产品数据库，且不得与写 profile 并发；它复用同一 Executor 进程、TradingNode、Binance data client、HalphaStrategyAdapter、参数、原生指标和纯逻辑，但只使用无需认证的 Binance 公开行情，composition root 不解析或注入 Binance 凭据并关闭账户佣金查询，且单调移除 execution client、产品数据库连接、HalphaCoordinator、ExecutionAction repository 与私有动作能力，只允许把不可提交 `StrategyProposal` 送入证据 sink。它不是第二策略或执行实现。成熟组件已经承担的能力不在 Halpha 内重写；可妥协的技术或策略细节按组件公开行为调整；只有计划激活、互斥额度、最大允许损失、持久动作唯一性、用户控制和事实权威等不可妥协语义保留最小自研。

NautilusTrader 是唯一的实时交易、回测、指标、订单模型和 Binance 适配量化栈。`halpha-executor` 内只有一个 `TradingNode`；`halpha-app` 不创建第二节点，也不持有 Binance 凭据。实时与回测使用同一策略类和同一动作提议边界，不保留自研行情泵、指标引擎、撮合回放、订单状态机或第二交易连接作为 fallback。

Halpha 只在额度、激活损失归属和进入稳定身份摘要的资本数值边界使用 Python `Decimal` 与 PostgreSQL `NUMERIC` 作为权威。NautilusTrader 的数值、组合、缓存和风险投影用于量化计算与执行技术输入；包括二进制浮点（f64）在内的组件投影不得替代上述精确比较或 Halpha 产品事实。

本 L3 只固定长期组件和调用边界。精确版本、锁文件摘要、许可证核对、目标 Windows 资格化、配置值、启用状态和实际证据均由 L4 记录；未取得这些记录不能推断组件当前可用。

# 1. 第三方优先决策【ENG-AUTO-DEP-001】

## 1.1 采用与保留边界【ENG-AUTO-DEP-001-REQ】

下表是本模块对上位第三方优先要求的落实，不建立另一套选型流程：

| 所需能力 | 长期采用组件 | Halpha 使用方式与差异处理 | 决定 |
|---|---|---|---|
| 实时行情、Bar、时钟、指标、策略生命周期、工具、订单、成交、持仓技术投影、Binance 连接与核对 | NautilusTrader 的 Binance instrument provider、data/execution clients 与 TradingNode | Executor 在一个 `TradingNode` 中让 data/execution clients 绑定同一显式 instrument provider 支持集，装载 Controller 和每个激活一个 Strategy；历史预热、组合 Bar 与实时接续也只用组件公开请求、订阅和聚合器；产品记录仍由 Halpha 数据库拥有 | 采用组件；不建第二量化栈 |
| 历史回放、成交模型、费用、统计与报告 | NautilusTrader `BacktestEngine`、费用/滑点/延迟模型、`ReportProvider` 与内置 statistics | 装载与实时相同的 Strategy；Halpha 只补充一次性激活、额度、损失和证据门槛断言 | 按组件行为妥协；不自建回测引擎 |
| HTTP API、同进程有限操作页、OpenAPI 与 ASGI 运行 | FastAPI、Uvicorn、Starlette | App 暴露版本化查询与命令，并以同一进程服务端渲染 `/operations`；Starlette 承担会话 cookie、可信 Host、HTML response 和通用中间件 | 采用组件；有限操作页不引入第二前端服务或 Node/Vite 运行依赖 |
| 输入、输出与配置校验 | Pydantic、pydantic-settings | API schema 和非秘密配置使用声明式模型；秘密值不进入普通配置对象或摘要 | 采用组件 |
| 事务、迁移与 PostgreSQL 驱动 | SQLAlchemy、Alembic、psycopg、PostgreSQL | Halpha 领域事务和唯一约束保留在一个产品数据库；组件不拥有业务状态机 | 采用组件 |
| Windows 秘密存储 | keyring 的 Windows backend | 运行入口按逻辑引用取出相应秘密；数据库和文档只保存引用，不保存秘密值 | 采用组件 |
| 所有者口令、会话与 CSRF | pwdlib 的 Argon2、Starlette SessionMiddleware/TrustedHostMiddleware、asgi-csrf | pwdlib 负责口令哈希；Starlette 负责签名会话；asgi-csrf 负责签名双提交令牌；App 只补同源与业务命令边界 | 采用组件并接受签名双提交行为 |
| 非权威限频 | limits | 保护失败登录、激活/恢复增险的重复尝试和普通 Web 入口；计数器不是授权或停用事实，不能阻止第一次停止、退出或用户接管命令 | 采用组件 |
| Halpha 自有结构化日志与轮转 | structlog、标准库 rotating file handler | structlog 形成 Halpha 事件和上下文；Halpha 只补稳定理由码与秘密脱敏处理器；标准库负责本地文件轮转 | 采用组件；不建日志平台 |
| NautilusTrader 内部日志 | NautilusTrader `LoggingConfig` 与框架日志输出 | 使用框架公开配置与自身日志管线；不包装、接管或重写为 structlog 事件；L4 资格化输出、脱敏、文件和轮转行为 | 采用组件原生能力 |
| Web 工作台 | React、Material UI 与 Emotion、RJSF MUI 与 AJV8、React Router、TanStack Query、openapi-typescript、openapi-fetch | UX 定义页面和业务语义；组件承担控件、schema 表单、路由、非持久查询与生成客户端 | 采用组件；不建前端框架 |
| 邮件通知传输 | Python 标准库 `email`、`smtplib`、`ssl` | App 的 `NotificationDispatcher` 从持久 Notification 发送邮件；标准库不拥有重试或业务状态 | 采用标准库；不引入异步邮件栈 |
| App/Executor 启停与单实例 | Windows Task Scheduler、pywin32 | Task Scheduler 按 SYS 契约启动、停止和防重叠；pywin32 只提供全局命名互斥和必要系统调用 | 采用系统能力 |
| PostgreSQL 等已安装系统服务的人工启停 | Windows Service Control Manager（SCM） | 项目所有者直接使用 SCM 查询或控制既有系统服务；Halpha 不包装 SCM，也不保存平行服务状态 | 采用外部系统工具 |
| 数据库备份与还原 | PostgreSQL `pg_dump`、`pg_restore` | 形成可验证的逻辑备份与还原；不建立第二备份平台或业务快照格式 | 采用产品工具 |
| Python、前端与浏览器验证 | pytest、Hypothesis、Vitest、Playwright、axe | 分别覆盖领域契约/属性、前端逻辑、真实浏览器流程和可访问性 | 采用组件 |
| Python 依赖锁定 | pip-tools | 从显式直接依赖生成可复现锁定结果；运行时不下载或漂移依赖 | 采用组件 |

组件若缺少一个不可妥协能力，Halpha 只允许在现有边界内增加一个窄适配。本设计允许的窄缺口仅包括：领域记录与组件事件互译、精确额度/损失比较、持久动作唯一性，以及 NautilusTrader 未公开所需账户事实时的只读查询补充。只读补充不得提交、取消或修改订单，不得复制行情订阅、账户缓存、核对循环或凭据体系；若无法资格化则该事实保持未知并阻断依赖它的动作。

## 1.2 明确不采用【ENG-AUTO-DEP-002-REQ】

Halpha 不采用第二量化框架或第二 Binance 写客户端，也不保留自研实现作自动 fallback。以下通用组件不进入运行路径：

- 通用 job、工作流、队列、retry 或 state-machine 框架；它们会与 `PlanActivation`、`PlanEvent`、本环境动作、Notification 和领域状态推进形成第二生命周期；
- Redis、消息总线、事件存储或第二产品数据库；本设计的权威记录和领取均由 PostgreSQL 承担；
- WinSW、NSSM 或把 App/Executor 再包装成 SCM 服务；直接使用 Task Scheduler 和 pywin32，SCM 只处理既有系统服务；
- 异步邮件库或邮件队列服务；单一所有者通知量由标准库与现有 dispatcher 足以承担；
- 专业图表、交易终端、高级数据表或可视化策略编辑器组件；本设计只需要服务端事实投影、普通表格、表单和时间线。

未来只有真实消费者证明上述拒绝造成无法接受的产品失败，并且替换后的总复杂度更低，才可修订本 L3。不得以“将来可能需要”预建抽象或平行路径。

# 2. NautilusTrader 使用契约【ENG-AUTO-NTL-001】

## 2.1 实时运行【ENG-AUTO-NTL-001-REQ】

SYS 声明的 Executor 创建一个 `TradingNode`，始终装载 Binance data client 与 Controller；只有 DEMO/LIVE_WRITE composition 装载 execution client 和 Halpha 协调入口。LIVE_READ_ONLY data client 只使用公开行情端点，`api_key/api_secret=None` 且 instrument provider 不查询账户佣金；配置或运行入口出现 Binance 凭据必须拒绝，而不是在已装载秘密后依靠布尔开关保持只读。Controller 按 TRADEPLAN 已持久的 `PlanActivation` 恢复、添加、停止或移除 Strategy；一个激活对应一个稳定 Strategy 身份，组件内部 Strategy 状态不是激活权威。无交易授权的前向观察可以用不可提交、非产品权威的观察身份装载同一 Strategy 适配器，但不得把该身份解释为 `PlanActivation` 或在产品数据库持久化。

`HalphaStrategyAdapter(Strategy)` 消费 NautilusTrader 提供的 Bar、timer、指标和订单事件，显式调用不继承 Strategy 的纯代码逻辑并把不可变 `StrategyProposal` 送入 Halpha sink。纯逻辑不能取得提交、修改、取消或退出订单的写 API。HalphaCoordinator 在 DEMO 与 LIVE_WRITE 都依次调用 TRADEPLAN、CAP 与 EXE 的同一公开应用边界，分别形成 `PlanEvent`/`ProposedAction`、环境限定资金与权限检查结果和 `ExecutionAction`；各所有者只写自己的记录，协调器只汇总所属环境同一事务。提交后再由 HalphaCoordinator 调用同一适配器的私有已持久动作门和 NautilusTrader OrderFactory/执行客户端工厂路径。该门只对 environment_id、profile、activation_id、UUID 与条款摘要精确匹配的 ExecutionAction 开放已资格化的单订单提交、查询与取消能力。LIVE_READ_ONLY 在 composition root 停止于不可提交 proposal sink，既不构造 HalphaCoordinator，也不解析数据库凭据或装载 execution client、ExecutionAction repository、私有动作能力及执行 reconciliation；禁止用运行时布尔开关保留这些能力后再声称只读。组件内部 RiskEngine 可作第二技术检查，不能批准 Halpha 额度或覆盖拒绝。

EXE `ExecutionAction` 与私有已持久动作门同时适用于 DEMO 与 LIVE_WRITE，并且只能有一个 EXE 私有可写 repository、应用服务和状态推进实现。两个写环境通过 composition root 创建分离 execution client、数据库连接和账户实例。DEMO profile 不得解析、注入或访问 LIVE 凭据引用与真实端点；LIVE_WRITE 必须额外通过真实写运行门。LIVE_READ_ONLY 不进入 EXE 动作路径，也不创建数据库实例或动作类型；其证据文件不是产品权威记录。PostgreSQL 以环境、授权效力和同环境引用约束拒绝跨环境数据，但不建立环境逻辑类型或第二领域构造器。

NautilusTrader 负责历史行情请求、实时订阅、Bar 聚合及历史—实时聚合器接续、时钟、内置指标、订单模型、Binance 协议、订单/成交事件以及其公开核对能力。Halpha 只验证策略输入的闭合、连续、重复与用途 freshness，不复制这些内部类、缓存、消息总线、连接生命周期、回填/聚合器或订单状态机。组件事件只有经过 DAT/EXE 映射并持久化后，才成为 Halpha 可引用事实或动作结果。

Binance data client 与 execution client 必须绑定同一显式 instrument provider 支持集，只加载计划和核对实际使用的工具；核对 include list 不能代替工具加载。instrument provider 提供的费率或失败回退只可用于组件技术估算，不能证明本激活实际手续费或用户账户的当前实际费率。产品确需实际费率而高层输出无法证明时，只能复用第 1.1 节同包 cached client 的窄只读查询补充；查询失败保持未知并阻止依赖该费率的增险，不引入第二 Binance client。

启动与连续核对使用 NautilusTrader 的公开能力。每个未闭合且非 `USER_TAKEOVER` 激活一个 HalphaStrategyAdapter、且不注册框架外部订单技术认领，是唯一设计拓扑；重启后即使框架把已知订单标为 EXTERNAL 技术身份，私有已持久动作门也只能按原 environment_id/activation_id/UUID 查询或取消，未知 UUID 不自动归属或撤销。精确组件配置由 L4 固定。组件合成事件、内部 portfolio 或 cache 不得自行计入激活损失、关闭责任或释放额度。组件不能证明外部结果时，EXE 保持原 `ExecutionAction` 未决并按稳定身份查询，不重发写动作。

L4 必须以关闭框架持久 cache 的黑盒重启验证证明普通与算法订单能按原 UUID 重新装入、查询、取消和核对终态，且未知 UUID 不被误撤。固定组件版本不能满足时，本契约拒绝；任何替代拓扑只能由受影响 L3/L4 目标文档形成候选版本后评审，不能成为当前自动 fallback。

## 2.2 指标与回测【ENG-AUTO-NTL-002-REQ】

策略只使用 NautilusTrader 的公开指标实现；策略数学可妥协差异按该实现调整并重新取得证据，不再维护 Halpha 平行指标公式。实时与历史回放必须装载同一 Strategy 类、参数 schema 和动作提议结构。

历史验证直接使用 `BacktestEngine`、组件费用/滑点/延迟与 bar execution 模型、`ReportProvider` 和内置 statistics。Halpha 只实现以下不可被通用回测器替代的断言：一次激活只允许一个交易闭环、每个激活的额度和最大允许损失、真实动作能力范围、证据适用范围与摘要。组件对同一 bar 内顺序或撮合的模型结果按其公开行为标识；证据不足的样本保持不确定或排除，不另建一套“更保守”撮合器。

ALP 离线证据使用 NautilusTrader 的 `BarDataWrangler`、`ParquetDataCatalog` 与已资格化 BacktestEngine：前两者承担规范 OHLCV 转换和可重建文件型 catalog，后者只承担固定版本已证明支持的历史推进、成交、费用、净值与报告能力。资金费必须先证明所选引擎会在与实时相同的策略适配路径中实际结算；若不支持，L4 必须固定 `funding_model=NOT_MODELED`，manifest/report 明示历史净值不含资金费，并在上位证据用途允许时接受该差异，不以自研结算器、第二策略 adapter 或未稳定主版本补齐。catalog、原始 bars、checksum、manifest 和报告属于可删除并重建的证据存储，不是产品数据库或事实权威；精确目录、保留、导出、重建和退出配置由 L4 固定。

## 2.3 数值与身份转换【ENG-AUTO-NTL-003-REQ】

Halpha 从原始十进制文本解析并以 `Decimal`/`NUMERIC` 保存所有持久场所价格、触发价、数量、余额、费率、工具规则、计划配额、动作前额度消耗、激活归属的已实现与未实现盈亏、手续费、资金费及最大允许损失比较。进入动作身份或内容摘要的数值先规范化为带单位和精度的十进制字符串；摘要本身是规范化字节的哈希，不是 Decimal。禁止先转二进制浮点再形成上述权威值。

行情计算、内置指标、订单技术对象和组件 portfolio 可使用 NautilusTrader 的原生数值。它们返回的投影必须在明确来源和精度边界下转换；f64 或其他组件投影不能直接成为额度剩余量、损失触线或释放决定。EXE 在转换为场所数量与价格后重新执行拥有领域要求的边界检查；转换失败、溢出或单位冲突只产生拒绝或未知，不截断放行。

# 3. App 与数据技术契约【ENG-AUTO-APP-001】

## 3.1 API、schema 与数据库【ENG-AUTO-APP-001-REQ】

FastAPI 只公开 UX 所需版本化查询、命令和 OpenAPI schema，并在同一 `halpha-app` ASGI 进程服务端渲染 `/operations`。有限操作页直接复用相同查询服务、命令处理器、`Command`/`Receipt`、会话、CSRF、Host/Origin 与 PostgreSQL，不引入第二 API、第二认证配置、第二状态存储或另一个前端服务器；其 HTML 不依赖 React、Node、Vite 或 SPA 静态制品才能显示关键状态与提交有限操作。openapi-typescript 由同一 schema 生成浏览器类型，openapi-fetch 调用同一接口。手写 DTO 或前端枚举不能形成平行语义。HTTP 成功只表示接口结果，领域效果由 `Receipt` 和相应业务记录说明。

Pydantic 校验传输结构，pydantic-settings 读取非秘密运行配置。数据库事务、唯一约束、并发版本和持久领取使用 SQLAlchemy 与 PostgreSQL；psycopg 是唯一 PostgreSQL 驱动；Alembic 是唯一 schema 迁移机制。数据库不可用或事务结果未知时，App 与 Executor 停止形成新的外部写，不以内存队列或框架内部表继续。

领域状态只保存在拥有领域记录中。SQLAlchemy session、Nautilus cache、TanStack Query cache、日志和通知提供方均不是恢复来源。

## 3.2 Web 安全与秘密【ENG-AUTO-APP-002-REQ】

本节只定义单所有者 Web 入口的认证与请求保护契约。签名会话 cookie、CSRF、Host/Origin 和 Web 登录限频不得解释为其他客户端形态的通用认证协议；本 L3 不为未来形态预建令牌、设备、远程访问、同步或秘密存储方案。只有未来形成明确建设范围和真实消费者后，适用 L3 才能选择并资格化相应成熟组件，同时复用既有应用命令、领域处理器和权威状态。

pwdlib 的 Argon2 实现负责单所有者口令校验；Halpha 不自研口令算法。Starlette 签名会话 cookie 只表达短时 Web 会话，asgi-csrf 的签名双提交令牌保护所有不安全方法；不再自研与 session 绑定的 CSRF 令牌状态机。TrustedHostMiddleware 与一个窄同源检查拒绝不符合预期的 Host、Origin 或 Referer。精确 cookie 属性、期限、口令参数、监听范围和限频值由 L4 固定。

limits 的计数只用于登录失败、激活/恢复增险的重复尝试和普通 Web 滥用保护，不是权限、动作或停用记录。停止新增风险、退出策略和用户接管的第一次合法请求不得因普通业务限频而不可达；防重复依赖稳定 `Command` 身份，而不是限频计数。

keyring 的 Windows backend 是运行秘密唯一存储入口。App 可取得数据库、会话、口令与邮件所需秘密，但不得取得 Binance 凭据；Executor 可取得数据库和最小 Binance 凭据，但不得取得会话或邮件秘密；浏览器和构建产物不得取得任何长期秘密。秘密缺失只停止依赖该秘密的能力，并产生可见诊断；不得回退到环境默认值、文档值或第二秘密存储。

## 3.3 日志与通知【ENG-AUTO-APP-003-REQ】

Halpha 自有代码使用 structlog 输出带构建、运行实体、激活、命令、动作和理由码引用的结构化日志，标准库 rotating file handler 负责本地文件轮转。Halpha 只维护一个在序列化前运行的脱敏处理器；发现凭据形态时删除值并保留字段名和理由码。

NautilusTrader 内部日志只使用其公开 `LoggingConfig` 和框架自身输出机制。Halpha 不把框架 logger 包装进 structlog、不拦截框架内部事件重造日志，也不让 Halpha 脱敏处理器假装覆盖框架日志；L4 必须分别资格化框架日志的格式、级别、秘密暴露、文件与轮转行为。两条日志流都只服务普通诊断，不建立日志采集平台或产品事实。

App 的 `NotificationDispatcher` 使用标准库 `email`、`smtplib` 和 `ssl` 发送 UX 已持久的 Notification。SMTP 响应映射为成功、可重试失败、最终失败或结果未知；重试身份、次数和结束由 Notification 拥有，标准库调用不得建立内部队列或自动无限重试。发送失败不改变交易、授权、保护或用户控制结果。

# 4. 前端技术契约【ENG-AUTO-WEB-001】

React 只组织 UX 页面和局部呈现状态；Material UI 与 Emotion 提供布局、普通表格、表单控件、反馈和主题。RJSF MUI 根据 ALP 提供的 JSON Schema 生成参数表单，AJV8 只提供即时客户端校验；服务器 Pydantic 与拥有领域校验是接受或拒绝的唯一权威。

React Router 维护稳定路由和中断返回位置。TanStack Query 只管理内存中的查询、轮询、失效和加载/错误状态，不持久化缓存、不离线提交命令、不作乐观业务状态更新，也不成为事实权威。资本相关命令由 openapi-fetch 提交稳定 `Command`，随后重新查询 `Receipt` 与业务对象。

服务端 `/operations` 仅用 FastAPI/Starlette 的 HTML 响应或当前后端模板能力生成最小表单和状态页；不为它新增 SPA bundle、客户端状态管理、第二 API client 或第三运行实体。它只公开 UX 列明的恢复激活、退出策略、用户接管与回执查询，并与 React 入口共享幂等键、预期版本和领域拒绝。

前端不自行实现 schema 表单引擎、API 类型生成、请求缓存、路由或可访问性扫描；也不引入专业图表、高级表格或交易终端组件。需要的价格、订单和事件关系使用服务端投影的普通表格与时间线表达。

# 5. Windows 运行、备份与构建【ENG-AUTO-BLD-001】

## 5.1 宿主与后台工作【ENG-AUTO-BLD-001-REQ】

App 与 Executor 由 Windows Task Scheduler 启动、停止和重启，并配置为拒绝同一运行实体的重叠启动；Executor 还通过 pywin32 取得操作系统全局作用域的命名互斥。同一实体的第二实例因互斥失败直接退出，不用数据库记录模拟进程锁；精确调度属性和互斥名称由 L4 固定。SCM 只作为 PostgreSQL 等已安装系统服务的人工启停入口，不承载 App/Executor，也不产生 Halpha 服务状态。

持久后台责任由 SYS 声明的 `NotificationDispatcher` 和 `HalphaCoordinator` 消费领域记录；不引入通用 job、retry、workflow 或 state-machine 框架。进程崩溃后从 PostgreSQL 权威记录和场所核对恢复，不从内存任务或组件 cache 恢复。

采用 `MANUAL_PLAN_RESUME` 的构建必须遵守以下恢复策略：Executor 连续写者丢失/替换、Windows 主机重启或 PostgreSQL 写连续性丢失后，启动代码必须在注册 callback、宣布 READY 或新写前把未闭合且非接管激活持久为 `PAUSED/WRITER_CONTINUITY_LOST`；App、SPA 静态资源、浏览器或通知 dispatcher 单独重启不得误暂停连续 Executor。暂停期只运行查询、核对与迟到事实保存；恢复激活、退出策略或用户接管均走同一 `Command`/`Receipt` 和领域边界。不得以新进程、epoch、租约、fencing token、后台恢复 worker 或自动 fallback 实现该模式。

`pg_dump` 与 `pg_restore` 是数据库备份和还原工具。备份不能证明可恢复；只有在隔离目标上还原、校验迁移头和关键身份后才可作为回退输入。当前计划、路径、保留期和最近证据属于 L4。

## 5.2 构建、迁移与回退【ENG-AUTO-BLD-002-REQ】

Python 直接依赖通过 pip-tools 产生锁定结果，前端使用其包管理器锁文件；生产运行不使用浮动版本、启动时下载或动态插件。可部署发布组至少能识别源修订、依赖锁摘要、迁移头、策略登记摘要、App/Executor/前端产物摘要和非秘密配置摘要；`/operations` 必须随同一个 App 后端产物发布，不能依赖另一个发布或 SPA 静态制品。构建身份不表示获准交易。

Alembic 迁移声明兼容构建、失败停止点和回退或前向修复路径。迁移只改变 schema 和明确数据转换，不执行领域命令或场所动作。无法证明旧构建可解释新记录时，回退保持停止；先还原兼容 schema/构建并核对开放责任，再由用户显式恢复增险。

组件升级必须重新检查公开能力、许可证、目标平台、数值、默认自动行为和退出边界；按影响重跑相应契约、真实外部和重启验证。升级失败时保留旧锁定发布或停止受影响能力，不临时启用第二组件。

## 5.3 环境 profile 与等价清单【ENG-AUTO-BLD-003-REQ】

DEMO 与 LIVE_WRITE 必须从同一源修订、依赖锁、迁移头、策略登记、App/Executor/前端制品和数据库 schema 生成。每个可部署发布组必须生成机器可校验的写环境等价清单，至少记录：源代码与锁文件摘要、TRADEPLAN/CAP/EXE 应用服务摘要、ExecutionAction schema/ORM、EXE 私有 repository、状态推进函数、HalphaStrategyAdapter、NautilusTrader Binance execution client 类与工厂路径、迁移头，以及 profile 允许差异集合。LIVE_READ_ONLY 另以能力裁剪清单证明同一源修订、锁、Executor、TradingNode、data client、适配器、参数、指标和纯逻辑成立，同时 execution client、数据库连接、HalphaCoordinator、动作 repository、私有动作能力和全部 venue write 均不存在；该清单不能替代写环境等价清单。

DEMO/LIVE_WRITE 写环境允许差异只包括：`environment_id`、`authority_class`、环境 profile 身份、模拟/真实端点、凭据引用、数据库连接引用、账户身份，以及场所适配器公开契约确需的环境配置。策略代码、计划语义、CAP Decimal 计算与检查、ExecutionAction 类型与状态、repository、应用服务、防重复、保护、核对、恢复和 OUT 评价入口不得列为允许差异。清单出现未列差异、摘要缺失或 Demo profile 可解析 LIVE 凭据/端点时，两个写环境等价资格均失败；不得以人工声称或单次成功替代。LIVE_READ_ONLY 的差异只能是上述明确能力裁剪、`NO_TRADING_AUTHORITY`、无凭据公开行情端点和资格证据配置，不能产生替代 adapter、策略逻辑、执行对象或持久状态。

等价清单证明代码和机制同源，不证明真实市场行为。DEMO 证据的首要用途是系统机制验证，策略行为验证次之；LIVE 的流动性、排队、冲击、滑点、费用、资金费率、延迟、权限、可用性和真实 Alpha 仍需独立证据。

# 6. 失败与停止【ENG-AUTO-ERR-001】

| 失败 | 必须结果 |
|---|---|
| NautilusTrader 启动、连接或核对失败 | Executor 停止新增风险；保留原动作身份并查询；不能证明结果时保持未决，用户可在 Binance 官方入口接管 |
| Strategy 试图绕过私有已持久动作门直接写订单 | 构建或运行契约拒绝该策略；受影响激活不再新增风险 |
| 所需账户事实不由量化组件公开且窄只读补充未资格化 | DAT 保持事实未知；依赖该事实的动作被阻断，不改用第二交易栈 |
| Decimal 解析、单位、范围或转换失败 | 拒绝输入或保持未知；不以组件浮点投影放行额度或损失决定 |
| 数据库提交结果未知 | 停止新的外部写，按稳定业务身份读取；不从内存重放 |
| 会话、CSRF、口令或秘密组件失败 | 拒绝受影响 Web 或外部能力；不扩大权限；三类控制保留官方交易所人工路径 |
| Executor/主机/PostgreSQL 写连续性丢失 | `MANUAL_PLAN_RESUME` 在 callback、READY 和新写前持久暂停开放激活；只读核对，等待同一命令边界中的恢复激活、退出策略或用户接管 |
| React/SPA 静态制品不可用 | 同进程 `/operations` 继续提供经过相同认证与 CSRF 的关键状态和有限控制；不启用无认证或第二控制面 |
| 邮件发送失败或未知 | 保持同一 Notification 继续有界处理或显式放弃；交易与控制结果不变 |
| 组件版本、锁或迁移不兼容 | 停止受影响入口，回到已验证发布或人工计划；不启用平行 fallback |

# 7. 验收契约【ENG-AUTO-TST-001】

长期组件边界至少由以下验证覆盖：

1. 同一 HalphaStrategyAdapter 与纯逻辑类在实时节点与 `BacktestEngine` 产生同结构 `StrategyProposal`，且静态与运行检查证明纯逻辑无法取得任何订单写 API；
2. NautilusTrader 的行情、指标、订单、成交、条件单、取消、部分成交、启动 reconciliation、场所事件、持续持仓核对及公开单订单查询按公开契约映射；关闭会因连续无响应合成本地终态的定时器，不注册框架外部订单技术认领，无持久 cache 重启后已知普通/算法订单可按原 activation_id/UUID 查询、取消和核对终态，未知 UUID 不被误撤，超时和未知不会产生第二写入；
3. 每个资本权威值经过 Decimal 解析、持久化、比较、摘要和组件转换往返，NautilusTrader 投影不能改变额度或最大损失结论；
4. FastAPI/OpenAPI 生成的前端类型、Pydantic 校验和领域拒绝一致；DEMO/LIVE_WRITE 共用同一 `ExecutionAction` schema、EXE 私有 repository、应用服务与状态推进，数据库以环境和授权效力约束隔离实例；数据库事务、唯一约束、并发版本和 Alembic 失败恢复可重复；LIVE_READ_ONLY 的能力裁剪清单和运行测试证明没有 execution client、数据库连接、HalphaCoordinator、ExecutionAction repository、私有动作能力或场所写入；
5. 口令、会话、签名双提交 CSRF、Host/Origin、秘密隔离和日志脱敏在真实浏览器与真实进程边界验证；Halpha structlog 与 NautilusTrader LoggingConfig 两条日志流分别验证脱敏、输出和轮转，且没有包装或接管；
6. Notification 重复、SMTP 超时、可重试、最终失败和未知保持同一身份，不改变业务结果；
7. App、Executor、数据库连接和量化节点分别终止并恢复时，只从权威记录与核对恢复，不重复动作；Executor/主机/数据库写连续性丢失后先暂停开放激活，App/SPA/通知单独重启不误暂停，三个显式恢复选择及不可清除的安全停止可验证；Windows 单实例与启停行为可验证；
8. 锁定构建可重建，`pg_dump` 产物能在隔离目标以 `pg_restore` 恢复，迁移和回退保持历史身份可读；
9. React 页面、RJSF 表单、TanStack Query 过期处理、命令回流、Playwright 关键路径和 axe 可访问性检查符合 UX 契约；删除或破坏 SPA 静态制品后，同一 App `/operations` 仍能以相同认证、CSRF、Command/Receipt 和领域处理器显示关键状态、提交有限操作和查询原回执，且并发提交保持相同幂等结果。

模拟、录制响应和组件测试可覆盖故障，但不能替代需要由 L4 记录的 Binance、Windows、SMTP 和恢复资格化。任何未完成项保持未知或禁用相应能力。

# 8. 迁移、复杂度与 L4 边界【ENG-AUTO-MIG-001】

迁移到本设计时删除 App 内第二量化节点、自研行情/Bar/指标/回测/撮合/订单状态机、第二 Binance 写客户端、通用任务/重试/状态机候选、异步邮件候选、服务包装器、专业图表和高级表格候选。保留自研仅限产品记录、领域纯规则、持久动作门、精确额度/损失、组件边界翻译、同源检查和秘密脱敏。

本方案不增加进程角色、数据库产品、每写环境路径、每环境物理权威记录族或执行实现；DEMO/LIVE_WRITE 分离的是 EnvironmentRuntime 实例、profile、端点、凭据引用、数据库和账户，不是业务代码、ExecutionAction 所有权或状态机。LIVE_READ_ONLY 只是同一 Executor composition 的能力单调裁剪，其追加式资格日志可删除重建且不成为数据库、记录族、worker 或执行实现。同进程 `/operations` 不构成第二 Web 应用。新增组件分别替代既有自研计划，且每项只有一个消费者边界。组件不能资格化时优先缩小支持范围、停止或由用户在官方工具接管，不建设第二实现。

L4 记录精确组件版本与制品摘要、许可证、目标 Windows 与 Python/Node 资格化、组件配置、锁文件、PostgreSQL 精确版本/实例/连接与迁移头、Task Scheduler/SCM 实例配置、SMTP/密钥引用、备份计划、建设状态、阻断、测试和真实外部证据。本 L3 不声明任何这些选择已经安装、通过或可用于真实资金。
