# Halpha 代码定义策略与量化组件使用契约

**文档编号：** HALPHA-ALP-002  
**版本：** v0.5.0  
**文档状态：** ACCEPTED  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** ALP  
**所属实现模块：** `planning` 中的策略实现分区；不建立独立服务、进程或量化平台  
**语言版本：** zh-CN  
**批准人：** Halpha 项目所有者  
**接受时间：** 2026-07-18T07:01:20+08:00  
**替代版本：** HALPHA-ALP-002@v0.4.0  
**上位文档或条款：** HALPHA-ALP-001 v1.5.0  
**直接依赖：** HALPHA-DAT-002 v0.8.0  
**直接消费者：** HALPHA-TRADEPLAN-002 v0.10.0、HALPHA-EXE-002 v1.2.0、HALPHA-UX-002 v0.11.0  
**适用纵向约束：** HALPHA-UX-001 v1.6.0；HALPHA-SYS-001 v1.6.0；HALPHA-ENG-001 v1.6.0  
**本文档负责：** 长期采用 NautilusTrader 实现代码策略的使用契约；策略版本、参数 schema、原生指标、每激活 HalphaStrategyAdapter 生命周期、不可变 `StrategyProposal`、离线证据输入、权威边界、失败与兼容要求  
**本文档不负责：** 活跃交易计划状态与事件、机器授权、独占额度及资金检查、场所写入与核对、当前策略参数和组件精确版本；策略 DSL、动态插件、代码上传、参数优化平台、自研回放撮合或第二套量化栈  

---

# 0. 设计结论【ALP-CODE-SUM-001】

Halpha 长期使用 NautilusTrader 的 `Strategy`、`Controller`、原生指标和 `BacktestEngine` 承担通用量化运行能力，不另建策略运行框架、指标库、历史回放撮合器或绩效统计器。组件完全承担的能力，本契约只规定 Halpha 怎样使用、哪些输出可被引用以及失败时怎样停止。

每个未闭合且未进入 `USER_TAKEOVER` 的 `PlanActivation` 对应一个由 `Controller` 装载的 `HalphaStrategyAdapter(Strategy)` 实例，其框架 StrategyId 由 activation_id 稳定派生并在该激活重启后复用；具体代码策略是由该适配器组合的纯逻辑对象，不继承 NautilusTrader `Strategy`。用户接管持久化后停止并移除该实例，后续只读核对不重建适配器。适配器不注册框架外部订单技术认领；恢复已知订单只依据已持久 ExecutionAction 的 environment_id、activation_id、UUID 与条款摘要，不从 StrategyId 或框架技术身份反推产品归属。当前组件的精确配置值由 L4 固定。

同一适配器与同一纯逻辑类同时用于实时 `TradingNode` 与离线 `BacktestEngine`；差异只存在于输入来源、明确标记的历史模型代理和 `StrategyProposal` 的后续网关，不复制策略逻辑。纯逻辑只消费同一规范输入结构及其 source；历史模型代理不能伪装成实时 VenueFact，其数据与模型差异必须进入证据 manifest 和报告限制。一次激活只允许一个交易周期：已消费入场机会或激活终止后，策略不得自动重新入场。

适配器的框架 callback 不依赖返回值；它显式调用纯逻辑对象并把零个或一个不可变 `StrategyProposal` 送入 proposal sink。纯逻辑对象没有 TradingNode、Strategy、订单或场所写能力。TRADEPLAN 把可接受输出规范化为 `PlanEvent` 内的 `ProposedAction`，CAP 以同一检查实现验证环境限定授权和独占额度，EXE 才能建立 `ExecutionAction` 并通过适配器私有已持久动作门写入所属环境场所。

---

# 1. 组件采用与最小自研边界【ALP-CODE-CMP-001】

## 1.1 NautilusTrader 使用范围【ALP-CODE-CMP-001-REQ】

| 所需能力 | 采用组件能力 | Halpha 使用边界 |
|---|---|---|
| 策略回调与生命周期 | `Strategy` 与 `Controller` | 每个未闭合且非 `USER_TAKEOVER` 激活创建一个 `HalphaStrategyAdapter`；具体代码策略作为纯逻辑对象组合而非继承 Strategy；装载、停止和移除受 `PlanActivation` 生命周期约束；组件状态只是可重建技术投影 |
| 行情事件和定时输入 | `TradingNode` 的数据事件与时钟 | 策略只消费满足 DAT 用途要求且带稳定来源身份的输入；组件缓存不是 Halpha 事实权威 |
| 历史预热与实时接续 | `request_aggregated_bars`、`subscribe_bars` 与 DataEngine 原生聚合器 | 先注册 handler/指标，由公开历史请求建立并预热同一聚合器，再在完成回调中转入实时订阅；Halpha 只校验闭合、连续、重复和历史—实时边界，不自研回填器、聚合器或第二行情源 |
| 通道与波动指标 | 原生 `DonchianChannel` 与 `AverageTrueRange` | 内置一次性突破策略固定窗口、输入顺序和触发语义；不复制公式，不保留自研计算 fallback |
| 历史数据规范化与重复读取 | `BarDataWrangler` 与 `ParquetDataCatalog` | Wrangler 只把已校验规范 OHLCV 转为公开 `Bar`；Catalog 只保存可从带摘要原始输入重建的离线 instrument 与 bar，不是产品数据库、事实权威或自研 replay loop |
| 历史资金费处理 | 所选 BacktestEngine 已资格化的原生能力；不支持时显式 `NOT_MODELED` | 先验证所选框架版本是否会在同一策略路径中实际结算资金费；支持才复用并固定来源与边界，不支持则由 L4/manifest/report 显著披露历史净值不含资金费并接受证据局限。除非上位产品要求明确判定该差异不可妥协，否则不自研资金费结算、不引入第二策略适配层或未稳定主版本 |
| 历史运行与成交模拟 | `BacktestEngine` 及其费用、滑点、延迟和成交模型 | 只用于离线证据；当前模型与配置由 L4 固定并资格化 |
| 报告与绩效统计 | `ReportProvider` 和内置 statistics | 输出是 ALP 经济证据判断的材料，不直接形成真实启用资格或线上事实 |

组件内部 `Cache`、`Portfolio`、`RiskEngine`、订单状态和绩效结果不得自动成为 Halpha 的计划、额度、权限、事实或执行权威。Halpha 只从经资格化的公开输出生成必要引用；无法映射时保持未知或阻止新风险，不解析组件内部状态建立平行权威。

## 1.2 保留的最小 Halpha 能力【ALP-CODE-CMP-002-REQ】

Halpha 只保留组件不拥有的产品语义：

- 随受控构建发布的代码策略清单、不可变策略身份和实现摘要；
- 用户参数的 JSON Schema、规范化及领域交叉约束；
- 一个 `HalphaStrategyAdapter`，把框架 callback 显式转换为纯逻辑输入和 `StrategyProposal` sink，并提供私有已持久动作门；
- 经济证据适用范围与真实启用资格门；
- 一次激活一次交易周期、独占额度和最大允许损失等产品断言。

这些能力不形成动态 registry 服务、独立数据库记录族、后台 worker 或通用量化抽象层。若后续组件公开能力能够承担其中的技术部分，删除对应 Halpha 实现；不得同时保留组件实现和自研实现作为自动 fallback。

---

# 2. 策略定义、参数与输出【ALP-CODE-OBJ-001】

## 2.1 代码策略定义【ALP-CODE-OBJ-001-REQ】

每个随构建发布的代码策略定义至少固定：

- `strategy_id + strategy_version` 与实现摘要；
- 实际纯逻辑类、`HalphaStrategyAdapter` 兼容版本和直接量化组件依赖；
- 用户可配置参数的 JSON Schema、单位、默认值、范围和交叉约束；
- 所需 bar/定时事件、闭合与连续性要求、最大允许过期和未知结果；
- 使用的原生指标、动作种类、经济适用范围和明确失效条件；
- 可引用的经济证据判断及其适用范围。

策略逻辑、参数含义、输入语义、指标映射或动作语义发生实质变化时必须形成新策略版本和实现摘要。参数值由不可变交易计划版本绑定；运行中修改参数必须形成新计划版本，不热更新正在运行的实例。

策略只随构建静态登记。运行时不得扫描目录、下载代码、执行用户表达式或加载数据库指定的任意模块。

`FixedStrategyPlanBasis` 是内嵌在 `TradePlanVersion` 中的不可变值，只包含策略身份与版本、实现摘要、规范化参数及摘要、事实输入合同、允许动作 profile、经济适用边界，以及当前 `BuildManifest` 的 build_digest、证据摘要与适用范围。它不是独立记录族、信号、授权或动作；证据或参数变化只能形成新 BuildManifest 或新交易计划版本，不能改写旧值。

## 2.2 不可变 `StrategyProposal`【ALP-CODE-ACT-001-REQ】

`StrategyProposal` 是策略处理一次稳定输入后返回的瞬态值，不是持久记录、领域动作或场所命令。它至少携带策略与激活身份、规则身份、稳定触发身份、输入摘要、拟议动作种类与参数、风险增加/减少方向、原因和有效期限。TRADEPLAN 是把它以及非策略来源规范化为 `ProposedAction` 的唯一语义所有者。

`HalphaStrategyAdapter` 拥有 final-style 的框架 callbacks：callback 调纯逻辑对象的确定性评价方法，再显式把零个或一个 `StrategyProposal` 交给 sink；框架忽略 callback 返回值不影响交接。需要撤旧再建新的逻辑必须使用两个有序来源事件，不引入批动作返回。适配器内由 HalphaCoordinator 调用的私有已持久动作门只白名单开放已资格化的单订单提交、已知订单查询与取消能力，且调用前必须核验已提交 `ExecutionAction` 的 environment_id、activation_id、UUID 与条款摘要。框架把重启订单标为 EXTERNAL 技术身份时，该门也只能处理 UUID 精确匹配同环境既有 ExecutionAction 的对象，不能认领或处理未知 UUID。Backtest、DEMO、LIVE_READ_ONLY 与 LIVE_WRITE 使用同一适配器类和纯逻辑；只有会建立 `ExecutionAction` 的 DEMO/LIVE_WRITE composition 才能注入同一个私有动作能力。LIVE_READ_ONLY 只把不可提交的 `StrategyProposal` 交给证据 sink，不得注入私有动作能力、执行事件 sink 或任何等价写端口。新增任何框架写方法或把只读 profile 接入动作门都需要修订契约和重新资格化。

纯逻辑模块不得导入 Strategy、TradingNode、OrderFactory、ExecutionClient，静态检查还禁止 `submit_order_list`、`cancel_orders`、`cancel_all_orders`、`close_position`、`close_all_positions`、`market_exit` 及任何等价写入口。该适配器不复制组件事件循环、指标、订单或恢复生命周期，也不注册框架外部订单技术认领；当前组件对替代配置的限制和证据由 L4 资格化，不作运行时 fallback。

相同策略版本、规范化参数、激活前态和稳定输入必须产生相同输出摘要。相同触发身份出现不同输入摘要时返回冲突；输入缺失、过期、不连续、组件异常或数值无效时不得产生风险增加输出。TRADEPLAN 决定是否把该值转成 `PlanEvent`，因而策略不能把自身输出解释为已授权动作。

适配器只在 `PlanActivation` 仍允许相应分支时把纯逻辑输出送入 sink。入场机会被消费后，纯逻辑只能提出该周期所需的减仓、平仓或退出建议。停止新增风险屏蔽风险增加输出；进入退出处理后适配器仍可交接必要的减仓或平仓建议，直到退出责任闭合。激活已确认平仓终结、退出责任已闭合或用户接管后不再产生任何新动作；用户接管由系统停止并移除适配器，停止本身不撤单也不平仓。

## 2.3 事实与恢复边界【ALP-CODE-DAT-001-REQ】

实时实例使用 NautilusTrader 投递的 bar、定时器和执行回调，但稳定触发身份、输入摘要及被采纳的决定由 `PlanEvent` 保存，外部结果由 `VenueFact` 保存。组件进程内缓存、指标增量状态和时钟只用于计算，重启后必须从 `PlanActivation`、已保存的 `PlanEvent` 与满足用途要求的 `VenueFact` 重建。

重建输入不足、组件状态无法证明等价或事件顺序冲突时，策略停止增加风险并把结果交给 TRADEPLAN 记录为未知；不得以最近值、零值、自研指标或第二策略运行器继续。

## 2.4 本地接口【ALP-CODE-API-001-REQ】

ALP 只暴露 `describe_strategy`、`validate_parameters`、`build_fixed_plan_basis` 和由 `Controller` 调用的适配器工厂。前三者是确定、无场所副作用的本地能力；工厂只接受已固定依据和消费方提供的激活上下文，返回组合了相应纯逻辑对象的 `HalphaStrategyAdapter`。离线与实时 proposal sink 实现相同 `StrategyProposal` 接收契约，只有后续持久化或回测执行方式不同。

---

# 3. 离线证据使用契约【ALP-CODE-EVD-001】

## 3.1 同一策略类【ALP-CODE-EVD-001-REQ】

历史证据必须由 `BacktestEngine` 装载与实时运行相同的 `HalphaStrategyAdapter`、纯逻辑类、参数规范化、原生指标映射和 `StrategyProposal` 映射。历史输入没有实时环境所需的同类 mark、quote 或其他事实时，L4 可以选择组件模型已经支持的数据作为带 source 的显式代理，交给同一纯逻辑输入边界；代理、保守缓冲、适用范围和局限必须进入 manifest，不得虚构实时 VenueFact，也不得为此增加第二行情源或平行策略逻辑。规范 OHLCV 只经 `BarDataWrangler` 进入 `ParquetDataCatalog`。资金费只有在所选框架版本、公开类型与同一策略适配路径被资格化为确实结算时才进入历史净值；否则必须以 `NOT_MODELED` 进入 manifest 和报告，明确历史净值与实时完整损失口径不可等同。该差异可由上位证据用途接受时，优先接受组件能力边界，不增加 Rust/第二 adapter、自研 replay、funding 或 PnL 实现。`BacktestEngine` 负责其已支持的事件时钟、历史推进、订单模拟、费用、滑点、延迟、成交、组合技术投影和报告；Halpha 不复制这些能力，也不以自研结果为并行判断。

`ReportProvider` 与内置 statistics 的输出只作为证据材料。ALP 仍负责记录被评价策略、数据与事实截止点、成本和成交假设、样本内外边界、适用场所与规模、主要缺口及支持强度。报告成功、单次模拟盈利或单次真实盈利都不能自行提高启用资格、额度或权限。

## 3.2 Halpha 证据门与断言【ALP-CODE-EVD-002-REQ】

只有 BuildManifest 内不可分割的证据摘要与 eligibility 字段明确允许且完整覆盖拟用策略版本、参数范围、方向、事实来源、动作 profile、场所、成本和规模时，才能形成可真实启用的固定策略依据；任一范围缺失、冲突、过期或被否定时拒绝新引用。证据变化形成新的 BuildManifest/build_digest，不建立 `StrategyEvidenceAssessment` 身份或版本，也不改写旧计划依据或开放交易责任。

离线证据运行除经济结果外，必须验证以下 Halpha 产品断言：

1. 每个激活最多消费一次风险增加入场机会，平仓后不自动重新入场；
2. 每个 `StrategyProposal` 必须经过与实时相同的 TRADEPLAN 转换和 CAP 纯检查，不能绕过独占额度；
3. 本激活最大允许损失触线后不再增加风险，并产生退出路径；
4. 策略代码无法取得场所写端口，实时与离线对同一规范输入产生相同 `StrategyProposal`。

这些断言不替代 `BacktestEngine` 的模拟能力，也不把组件的浮点技术投影写成 Halpha 资金或盈亏权威。

---

# 4. 失败、兼容与停止【ALP-CODE-OPS-001】

| 情形 | 必须结果 |
|---|---|
| 策略摘要、参数 schema 或组件公开契约不匹配 | 相关策略版本不可启动，不退回相近版本 |
| 原生指标不可用或输出不满足资格化契约 | 阻止该策略版本；不启用自研指标 fallback |
| 数据缺失、过期、时钟冲突或数值异常 | 不产生风险增加输出，保留未知原因 |
| `Strategy` 处理器异常 | 停止该实例的新风险输出；已有持仓仍由计划退出、用户接管或执行核对路径处理 |
| 策略尝试直接写场所 | 立即拒绝调用、停止实例并记录系统问题；不把调用改送第二写路径 |
| 重复或乱序回调 | 由稳定触发身份幂等处理；冲突保持未知，不重复产生动作 |
| 用户接管 | `Controller` 停止并移除实例；Halpha 不自动撤单、平仓或恢复该激活 |
| 离线引擎或报告失败 | 证据保持不足或无法判断，不影响既有开放交易责任 |

NautilusTrader 的精确版本、构建哈希、许可证、目标平台、指标构造参数、回测模型和运行配置由 L4 资格化。组件版本或配置变化若可能改变事件顺序、指标、成交模拟或 `StrategyProposal`，必须更新实现摘要并重验受影响证据。升级只替换单一组件实现，不保留旧版或第二量化栈作为运行时自动 fallback。

---

# 5. 最小验收契约【ALP-CODE-TST-001】

实现至少验证：

1. `Controller` 为每个未闭合且非 `USER_TAKEOVER` 激活装载一个 `HalphaStrategyAdapter`，其 StrategyId 由 activation_id 稳定派生；正常终结、退出责任闭合和用户接管时停止并移除，停止新增风险与退出处理中仍保留必要的减仓或平仓输出，同一激活不得自动重新入场；
2. 实时 `TradingNode` 与 `BacktestEngine` 装载同一适配器与纯逻辑类，对同一规范输入产生相同 `StrategyProposal` 身份、摘要和动作含义；
3. 静态依赖检查与运行时保护同时证明策略代码不能调用提交、撤单、修改或市价退出等写能力；
4. 参数边界、单位、未知字段、非有限数值和交叉约束被确定接受或拒绝，运行中参数不能热更新；
5. 原生 `DonchianChannel` 与 `AverageTrueRange` 通过固定黄金向量、重启重建和边界输入验证，代码中不存在同能力自研公式或自动 fallback；
6. 数据缺口、过期、重复、乱序、摘要冲突和组件异常都不产生重复或风险增加动作；
7. `BacktestEngine`、`ReportProvider` 与内置 statistics 承担回放、撮合和绩效输出，Halpha 只执行证据范围门和一次性、额度、损失及写边界断言；
8. 在不注册框架外部订单技术认领且不使用框架持久 cache 时，重启后能从 Halpha 权威记录按原 activation_id 与 UUID 重建；已知普通/算法订单即使呈 EXTERNAL 技术身份仍可查询、取消并核对终态，未知 UUID 不被误撤；无法等价重建时停止新风险并保持未知；
9. 组件升级改变公开行为时实现摘要与证据必须更新，且不存在并行量化实现；
10. 没有 DSL、动态插件、用户代码、批量优化、通用研究平台或第二量化栈入口。
11. LIVE_READ_ONLY 与写 profile 装载同一适配器、参数、原生指标和纯逻辑，但适配器的私有动作能力与执行事件 sink 均为空；其 `StrategyProposal` 只能进入不可提交证据 sink，运行测试证明无法建立或提交 `ExecutionAction`。

---

# 6. 复杂度与删除边界【ALP-CODE-MIG-001】

本契约不新增进程、数据库、持久记录族、场所写路径或运行模式。每激活适配器且不注册框架外部订单技术认领是本契约唯一运行拓扑；若 L4 固定的组件版本无法在无持久 cache 的重启后按原 UUID 查询、取消和核对已知普通/算法订单，则该选择拒绝，任何替代拓扑都必须直接修订其语义所有者 L3 和相应 L4 选择并重新评审接受。NautilusTrader 的单一策略运行与回测栈替代自研指标、回放、撮合、绩效和策略生命周期设计；Halpha 只保留不可妥协的产品边界和薄转换。若不再有代码策略消费者，可在所有开放激活责任闭合后删除策略清单与转换，不影响 TRADEPLAN、CAP、EXE 的独立权威。
