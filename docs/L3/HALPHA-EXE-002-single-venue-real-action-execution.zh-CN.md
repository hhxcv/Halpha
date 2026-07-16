# Halpha 单场所机器授权动作、保护、核对与恢复契约

**文档编号：** HALPHA-EXE-002  
**版本：** v1.1.0  
**文档状态：** ACCEPTED  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** EXE  
**所属实现模块：** `venue_integration` 的 EXE 语义分区；与 DAT 同模块但状态所有权分离  
**语言版本：** zh-CN  
**批准人：** Halpha 项目所有者  
**接受时间：** 2026-07-16T14:07:30+08:00  
**替代版本：** HALPHA-EXE-002@v1.0.0  
**上位文档或条款：** HALPHA-EXE-001 v1.6.0  
**直接依赖：** HALPHA-ALP-002 v0.4.0、HALPHA-TRADEPLAN-002 v0.9.0、HALPHA-CAP-002 v1.1.0、HALPHA-DAT-002 v0.7.0  
**直接消费者：** HALPHA-OUT-002 v0.7.0、HALPHA-UX-002 v0.10.0  
**适用纵向约束：** HALPHA-SYS-001 v1.5.0、HALPHA-ENG-001 v1.6.0  
**本文档负责：** 一个场所内机器授权动作的持久身份、唯一写入、防重复、订单映射、条件责任、部分成交、场所保护、最大损失响应、核对、执行结果未知、闭环、恢复和用户接管  
**本文档不负责：** 形成策略信号或计划条件；授予资金权限；定义 DAT 场所事实；规定当前场所、账户、工具、订单参数、NautilusTrader 精确版本/配置、凭据、限频、超时或建设证据  

---

# 0. 设计结论【EXE-AUTO-SUM-001】

所有真实写入只允许经过以下一条链：

```text
StrategyProposal / 持久 deadline / 场所事实 / 用户 Command
→ TRADEPLAN 公开边界形成 PlanEvent + ProposedAction
→ CAP 公开边界完成资金与权限检查
→ HalphaCoordinator 在同一事务内调用各所有者公开边界
→ PostgreSQL 已提交 PlanEvent、CAP 结果与 PendingAction
→ NautilusTrader OrderFactory
→ HalphaStrategyAdapter 私有已持久动作门调用白名单 Strategy 基类写方法
→ 场所
```

EXE 只保留一个 `PendingAction` 持久记录族。客户端 UUID32、写调用证据、订单结果、执行结果未知、保护摘要和单动作闭环证据都由其版本化状态承载；不建立 `WriteControl`、`SubmissionAttempt`、`ProtectionTask` 或 `ReconciliationItem`。

NautilusTrader Binance 适配器承担订单对象、场所客户端、普通/条件订单事件、启动 reconciliation、持续持仓核对和公开单订单查询。Halpha 不复制其通用订单状态机；HalphaCoordinator 只按已持久 PendingAction 身份调用公开查询并把结果交回 EXE，不能证明时保持 UNKNOWN。但框架不能替代 CAP、动作唯一性、激活归属、Decimal 最大损失、未知或额度释放证据。

---

# 1. `PendingAction`【EXE-AUTO-ACT-001】

## 1.1 身份与内容【EXE-AUTO-ACT-001-REQ】

每个 `PendingAction` 至少包含：

| 字段 | 约束 |
|---|---|
| `pending_action_id` | Halpha 稳定动作身份 |
| `activation_id`、`plan_event_ref`、`source_identity` | 同一激活、计划事件和不可变 ProposedAction 来源 |
| `action_kind`、`action_class` | 入场、撤单、保护、止盈、减仓或平仓；以及 CAP 风险类别 |
| `action_terms`、`action_terms_digest` | 账户、工具、方向、订单类型、数量/全平语义、价格/触发、有效期、只减仓、前置动作和规范摘要 |
| `capital_decision_digest` | 建立动作时的 CAP 输入、版本与接受结果摘要 |
| `client_order_id` | 下单时为一次生成并持久化的 32 位无连字符 UUID；普通订单和条件订单分别原样映射到框架客户端订单/算法订单身份 |
| `cancel_target` | 撤单时保存原普通或条件订单的 Halpha/场所身份及其原 UUID32，不重新编码或生成目标身份 |
| `state`、`state_version`、`state_digest` | 当前状态、CAS 版本和完整内容摘要 |
| `request_digest`、`call_started_at`、`call_completed_at` | 唯一场所调用的请求与时间证据；未调用必须为空 |
| `venue_order_refs`、`venue_fact_refs` | 普通/条件订单、成交、费用和持仓 VenueFact 引用 |
| `unknown_reason`、`next_query_at` | 调用或场所结果未知及下次只读查询时间 |
| `protection_digest`、`closure_evidence_digest` | 本动作承担的保护条款及其结果、单动作责任闭合证据 |

`activation_id + plan_event_ref + source_identity + action_kind` 唯一。UUID32 在建立 PendingAction 的事务前生成，并随 PendingAction 一次提交；事务失败可丢弃，事务结果未知只能按来源身份查询原 PendingAction。已提交后，重启、查询、撤单和未知恢复始终复用原值。

客户端身份只是场所关联键，不编码业务语义，也不从场所短身份反推激活。普通与条件订单端点必须都能以该 UUID32提交、查询和撤销；未资格化的端点不得进入真实写链。

## 1.2 状态【EXE-AUTO-STA-001-REQ】

`PendingAction.state` 只取：

`READY | NOT_SUBMITTED | SUBMITTING | SUBMITTED_UNKNOWN | ACKNOWLEDGED | WORKING | PARTIALLY_FILLED | FILLED | CANCELLED | REJECTED | EXPIRED | RECONCILED | HANDED_OVER`。

`READY` 尚未越过外部变化分界；`NOT_SUBMITTED` 证明没有调用；`SUBMITTING` 表示调用前状态已经提交，进程此后崩溃也必须按可能已调用处理；`SUBMITTED_UNKNOWN` 只允许查询原 UUID32；订单终态仍需订单、成交、费用、持仓和保护事实闭合后才能 `RECONCILED`。用户接管后的未调用动作进入 `HANDED_OVER`，不得再武装。

每次状态变化都保存于同一 PendingAction 的新 `state_version`，写调用证据没有独立身份、claim 或生命周期。一个 PendingAction 最多越过场所写边界一次。

---

# 2. 建立、提交与崩溃恢复【EXE-AUTO-SUB-001】

## 2.1 本地事务【EXE-AUTO-TXN-001-REQ】

HalphaCoordinator 收到待规范化来源后，以 SYS 定义的应用协调者身份开启一个 PostgreSQL 事务，并依次调用 TRADEPLAN 的来源去重与 PlanEvent/`ProposedAction` 形成边界、CAP 的纯检查边界和 EXE 的 PendingAction 建立边界。各所有者只通过自己的公开应用边界写入自己拥有的记录；EXE 不直接插入或更新 `PlanActivation`、`PlanEvent`、`PlanAllocation` 或其他模块私有表。

TRADEPLAN 先按 `source_identity` 去重并形成不可变事件内容，CAP 按同一事实截止点返回最终检查结果；CAP 接受时，EXE 以该 PlanEvent 引用和检查结果建立单向引用该事件的 PendingAction，拒绝时不建立动作。三方结果在同一事务中同时提交或同时回滚；不得先提交 PlanEvent 再回填 CAP 或动作引用。相同来源和条款返回原结果，相同来源不同摘要或条款冲突。HalphaCoordinator 只拥有调用顺序与事务汇总，不取得任一业务记录的语义或写入所有权。

事务提交前禁止调用 OrderFactory、submit、cancel 或任何场所写方法。框架 RiskEngine 可以在之后追加更保守的技术拒绝，但不能把 CAP 拒绝改为允许；其拒绝作为 PendingAction 的 `NOT_SUBMITTED` 证据保存。

## 2.2 唯一场所调用【EXE-AUTO-SUB-001-REQ】

HalphaCoordinator 处理 READY 动作时：

1. 重读 PlanActivation、用户接管、StopStateVersion、PlanAllocation、前置动作和当前 VenueFact；
2. 用同一 CAP 规则执行提交前复核，并把摘要写入 PendingAction；
3. 在事务中写入请求摘要与 `SUBMITTING`，提交后才调用场所；
4. 由对应 `HalphaStrategyAdapter` 的私有已持久动作门使用 OrderFactory 创建订单，并调用已资格化的白名单 Strategy 基类写方法；门必须核验 PendingAction 的 activation_id、UUID 与条款摘要，纯代码策略和框架 callback 都不可直接访问该门；
5. 保存返回或异常，随后按原 UUID32 调用组件公开查询普通/条件订单，并继续消费场所事件、启动/持仓 reconciliation 结果；
6. 调用 DAT 公开边界把有权威来源的观察写成 VenueFact，再调用 EXE 公开边界推进同一 PendingAction。

不得使用 `market_exit` 或任何会在框架内部产生未持久子动作的便捷方法。退出与组合订单的每个可能场所变化必须先形成独立 PendingAction；无法取得独立身份和结果时不使用该能力。

框架、HTTP client 与 SDK 的自动写重试必须关闭。读取和状态查询可以有界重试，但不能更换动作、UUID32、目标订单或截止点。

## 2.3 不确定调用【EXE-AUTO-UNK-001-REQ】

| 崩溃或结果 | 唯一允许行为 |
|---|---|
| PendingAction 事务前崩溃 | 无外部效果；Strategy 可以重算同一来源身份 |
| PendingAction 已提交、尚未进入 `SUBMITTING` | 恢复原 READY 动作并重新执行提交前检查 |
| `SUBMITTING` 后崩溃、超时或断线 | 转为或保持 `SUBMITTED_UNKNOWN`，只查询原 UUID32；不得再次调用 |
| 场所证明原身份不存在且请求未进入 | 原动作进入 `NOT_SUBMITTED`，不得复活 |
| 首次入场越界后最终拒绝或无成交 | 本次一次性入场结束为未入场；不寻找第二个入场信号 |
| 风险减少责任明确未提交但责任仍存在 | TRADEPLAN 可按当前事实形成一个新的风险减少代次和新 PendingAction；原动作保持终态 |

任何 UNKNOWN 都阻止受影响范围新增风险。只有场所查询、实际事件和持久身份共同给出明确结果后才解除；超时本身不证明未发生。

---

# 3. 条件、撤单与重挂【EXE-AUTO-ORD-001】

`ProposedAction` 必须明确源条件责任为 `HALPHA_MONITORED | VENUE_MONITORED | NONE`。Halpha 条件由 `HalphaStrategyAdapter` 调用纯逻辑对象，使用框架数据、指标与 timer 判断；场所原生条件可由场所负责；固定时间、成交后保护、用户控制或安全退出使用 `NONE`。成立后可以提交 MARKET、LIMIT 或另一个经资格化的场所条件订单。场所条件只有在对应普通/算法客户端身份、条款和 WORKING 状态被确认后才算委托成功。

同一条件阶段只有一个责任方。场所条件提交或查询未知时只能查询原身份或停止，不能并行改为 Halpha 监控。写前已知场所不支持时，计划可以从一开始选择 Halpha 监控；这不是运行时 fallback。

移动挂单由纯逻辑对象经 `HalphaStrategyAdapter` 依次产生“撤销旧单”和“建立新单”两个 `StrategyProposal`，再由 TRADEPLAN 分别形成 `ProposedAction`。新单只有在旧单终态、取消与成交竞争已核对、当前持仓和剩余目标明确且重新通过 CAP 后才可提交。EXE 不自研追价、修改、拆单或路由引擎；未知旧单阻止新单。

减仓和平仓数量不得超过同 cutoff 已核对可减持仓，并使用已资格化的 `reduce_only` 或 `close_position` 语义；无法证明不会反向开仓时不提交。

---

# 4. 场所保护与风险减少【EXE-AUTO-PROT-001】

## 4.1 经资格化的场所保护【EXE-AUTO-PROT-001-REQ】

固定计划规定保护责任，TRADEPLAN 把该责任形成明确 `PlanEvent`/`ProposedAction`，CAP 检查后由 EXE 建立独立 PendingAction。首次风险敞口或新增部分成交被权威 VenueFact 确认后，HalphaCoordinator 必须通过各所有者公开边界形成与已确认敞口相称的保护责任；保护尚未由场所事实确认前，不得继续扩大该敞口。

保护优先使用 NautilusTrader 与场所共同公开且已经资格化的原生条件订单能力。每种受支持保护都必须验证触发来源、订单身份、查询与撤销、部分执行、有效期、只减仓或全平含义，以及 Halpha 离线后的持续行为。具体订单类型、触发类型、保护数量、止盈层数、固定或移动公式和场所参数属于 L4 当前选择，本 L3 不把其中一种映射固定为长期唯一方案。若经资格化的场所全平条件单能在仓位变化后沿用同一稳定身份并可在重启后查询、取消和核对，则后来增量敞口可以由该既有保护继续覆盖而无需新场所写；任一恢复能力不能证明时，L4 必须采用可恢复的显式数量方案或拒绝支持，不能增加平行写路径。

同一保护阶段只有一个监控责任方。场所保护提交或查询未知时，保护责任保持 UNKNOWN，停止新增风险并只查询原稳定身份；不得并行切换为 Halpha 监控或提交内容等价的第二保护。明确不存在、被拒绝、失效或与当前敞口不一致时形成保护缺口；计划规定的持久期限到达后，TRADEPLAN 决定退出或用户接管，EXE 只执行由该决定形成并重新通过 CAP 的风险减少动作。

替换保护时，原保护必须保持有效，直到新保护已由场所确认并经事实核对。若新旧保护并存可能造成反向开仓、过度减仓或其他更大风险，只能采用经过资格化的有界替换协议；否则明确不支持替换。组合订单或便捷方法只有在每个可能产生场所变化的子动作都先具有独立 PendingAction、稳定外部身份和可核对结果时才可使用；会在框架内部生成未持久子动作的能力不得进入写链。

## 4.2 部分成交、晚到成交与相关订单清理【EXE-AUTO-TP-001-REQ】

部分成交、取消与成交竞争以及晚到成交始终按原 PendingAction 和稳定外部身份核对，不能依据单一订单状态推定剩余敞口、另一订单或保护已经结束。任何减仓动作的固定数量不得超过同一事实截止点已核对的可减持仓；数量未知或可能反向开仓时不提交。

入场责任尚未终结时，授权 deadline 到期、退出或保护触发都必须先按原身份取消仍开放的普通/条件增险订单并查询其最终结果；`SUBMITTING | SUBMITTED_UNKNOWN` 只查询原身份，证明开放后才撤销。取消后出现的晚到成交形成新的已确认敞口；TRADEPLAN 必须据此形成新的风险减少责任，不能修改、复活或重复提交已经越过场所写边界的动作。新敞口在责任闭合前持续阻止新增风险。

任何会让场所按整个 instrument 解析平仓数量的动作，只有在 TRADEPLAN 能证明对应 `(environment, account, instrument)` 处于独占活动范围，且最新 VenueFact 不存在未归属外部活动、未知订单或身份冲突时才可提交。前提不成立时不得使用 instrument-wide 动作；已存在的场所保护保持原状并进入可见未知或用户接管责任。

任一风险减少动作使已核对持仓为零后，HalphaCoordinator 必须通过 EXE 公开边界按原稳定身份处理仍开放的入场、保护、止盈或其他相关订单，并通过 DAT/TRADEPLAN 公开边界保存事实与计划引用。取消或查询未知时只查询原身份；全部相关订单终态、晚到成交已处理且第 6.2 节闭环条件成立前，不得关闭激活或释放额度。

---

# 5. 最大允许损失【EXE-AUTO-LOSS-001-REQ】

HalphaCoordinator 在同一事实 cutoff 下，把本激活可归属的已实现盈亏、未实现盈亏、实际手续费和实际资金费以 Decimal 交给 CAP。框架 Portfolio/PnL、预测费率、其他激活和外部活动不得计入。

```text
activation_net_pnl = realized_pnl + unrealized_pnl + funding_income - commission
activation_loss = max(0, -activation_net_pnl)
```

CAP 是最大允许损失判断与锁存的唯一所有者；达到上限时，只在对应 `PlanAllocation` 锁存结果，且不得被后来盈利解除。HalphaCoordinator 消费该 CAP 结果，通过 TRADEPLAN 公开边界形成停止新增风险和退出事件，再通过 EXE 公开边界建立相应风险减少 PendingAction。EXE 不在 `PlanActivation`、PendingAction 或组件投影中建立第二损失锁存。手续费、资金费、持仓归属或 mark price 未知时，CAP 结果保持 UNKNOWN，相关范围停止新增风险并继续查询；超过计划 deadline 仍不能解析时由 TRADEPLAN 决定退出或要求用户接管，不能以框架估值补齐。

最大保证金和最大名义仓位只在 Halpha 主动增加风险前检查；行情变化造成既有持仓自然越界不在本模块自动减仓或平仓。策略本身的止损、退出和最大允许损失仍照常执行。

---

# 6. Reconciliation 与闭环【EXE-AUTO-REC-001】

## 6.1 框架 reconciliation【EXE-AUTO-REC-001-REQ】

NautilusTrader 启动 reconciliation、场所普通/条件订单事件和持续持仓 reconciliation 必须保持开启。HalphaCoordinator 对已持久 UUID 的持续订单核对只调用组件公开单订单查询，不运行组件会在连续无响应后合成本地终态的定时器，也不建立第二订单状态机。每个未闭合且非 `USER_TAKEOVER` 激活只使用一个由 activation_id 稳定派生 StrategyId 的 `HalphaStrategyAdapter`，且不注册框架外部订单技术认领；已接管激活只读核对，不重建适配器。当前组件精确配置及其不支持的替代配置由 L4 固定和资格化，不作运行时 fallback。

恢复时，HalphaCoordinator 可以通过适配器私有已持久动作门，对框架 cache 中呈 EXTERNAL 技术身份但 activation_id、UUID32 与不可变条款摘要精确匹配既有 PendingAction 的普通或算法订单执行已资格化的查询与取消；这不把框架对象认领为 Strategy 所有。Halpha 动作归属始终只由 PendingAction 的 activation_id、UUID32 与条款摘要共同证明；用户接管活动只能按 TRADEPLAN 冻结范围和 DAT `handover_command_ref` 分类，不能成为 PendingAction。UUID 未知、摘要不符或无法唯一匹配的人工/其他程序对象必须标为未归属外部活动，停止新增风险并形成用户责任；Halpha 不自动撤销、不计入本激活损益、不用于闭环。框架 EXTERNAL/VENUE/RECONCILIATION 标签或合成事件本身都不改变产品归属。

L4 必须以黑盒重启验证证明：关闭框架持久 cache 时，已持久 UUID32 的普通和算法订单能够重新进入 cache、按原身份查询和取消并核对到终态，未知 UUID 不被误撤，Strategy 停止/移除不会产生新调用。任一行为未通过，则本契约真实写入资格失败；任何替代拓扑只能另起 L3/L4 提案重新评审，不在当前设计中并存第二拓扑、自研 reconciliation 或第二场所客户端。

这是唯一技术 reconciliation 实现。HalphaCoordinator 不建立 ReconciliationItem 或独立核对 worker；它调用 DAT 公开边界把有权威来源的观察规范化为 VenueFact，调用 EXE 公开边界更新 PendingAction，并调用 TRADEPLAN 公开边界保存 PlanActivation 的 EXE 结果引用。各所有者只写自己的记录；框架合成订单/成交事件或未绑定到已持久 UUID32 的对象不能证明本激活成交、盈亏或闭环。

## 6.2 动作与激活闭环【EXE-AUTO-CLOSE-001-REQ】

PendingAction 只有在其普通/条件订单终态、成交与费用完整、对持仓和保护的影响明确且无 `SUBMITTING | SUBMITTED_UNKNOWN` 后，才进入 `RECONCILED` 并保存 `closure_evidence_digest`。

EXE 只有在同一权威 cutoff 同时证明以下共同条件时，才形成最终 `closure_digest`；HalphaCoordinator 随后通过 TRADEPLAN 公开边界把该摘要引用到 PlanActivation，并通过 CAP 公开边界请求释放额度：

1. 对应环境、账户和 instrument 的场所净持仓为零；
2. 本激活已知普通和条件订单均终态，且同范围场所查询不存在开放普通/算法订单；
3. 全部 Halpha PendingAction 已 `RECONCILED | NOT_SUBMITTED | HANDED_OVER`，无 `SUBMITTING | SUBMITTED_UNKNOWN` 或其他在途/未知调用；
4. 不存在新增、增险、反向、超出冻结范围或会改变归属的外部活动与身份冲突。

未进入用户接管时，Halpha 可归属成交、实际手续费和资金费还必须覆盖完整，才能形成正常关闭摘要。进入用户接管时，命令冻结的责任范围和 `handover_command_ref` 是额外输入；匹配范围且只减少/关闭风险的官方入口活动可以消除持仓和订单责任，但不得被 Halpha 认领、撤销、改写为 PendingAction 或计入确定的策略执行结果。用户活动使精确损益不可归属时，激活账户结果保持 `UNKNOWN`，不单独阻止满足上述接管关闭条件后的额度释放。

范围外或方向不明的外部活动会阻止释放。无法闭环时保持 UNKNOWN、创建用户任务并继续只读核对或进入用户接管；不得以框架 cache 清空、订单列表暂时为空或超时替代证据。

---

# 7. 启动恢复与用户接管【EXE-AUTO-HO-001】

Executor 依赖 SYS 规定的 Windows 重叠启动拒绝和操作系统级命名互斥行为保证单写进程，不建立数据库 WriteControl；精确宿主属性和互斥名称属于 L4。启动唯一 TradingNode 并完成框架启动 reconciliation 后，HalphaCoordinator 再按未闭合且非 `USER_TAKEOVER` 的 PlanActivation 恢复对应 HalphaStrategyAdapter 与稳定 per-activation StrategyId，在不注册框架外部订单技术认领的行为下按第 6.1 节查询和核对呈 EXTERNAL 技术身份的已知订单，并恢复 `READY | SUBMITTED_UNKNOWN` 等未闭合 PendingAction；已接管激活不重建适配器，只继续只读核对。恢复期间不提交新增风险。该生命周期顺序必须由 L4 的黑盒重启验证证明，不能证明时本契约拒绝。

用户接管命令必须先持久化，并在既有 `Command/Receipt`、`PlanEvent` 与 `PlanActivation` 中冻结 command ref、切换 cutoff、环境/账户/instrument、当时已知持仓方向与数量、已知开放普通/算法订单身份和责任摘要；不新增接管记录族。HalphaCoordinator 随后调用 ALP/SYS 公开生命周期边界，以“不由框架管理场所订单”的行为停止并移除对应 HalphaStrategyAdapter，并通过 EXE 公开边界阻止其 READY 动作继续提交；停止本身不得自动撤单、补保护或平仓。已经 `SUBMITTING | SUBMITTED_UNKNOWN` 的动作只查询原身份。TradingNode 继续运行，HalphaCoordinator 通过各所有者公开边界记录迟到 ACK、成交、费用、持仓和用户接管/外部活动，不直接写入相邻模块私有状态。

接管后用户通过场所官方入口处理。Halpha 只读核对冻结范围；风险减少/关闭活动经 DAT 标为 `USER_TAKEOVER` 后可用于第 6.2 节接管关闭，新增、增险、反向、范围外或冲突活动仍阻止关闭。闭环事实成立后接管责任可以关闭并释放额度，同一激活永不恢复自动写入；精确收益无法归属时结果保持 UNKNOWN。Executor 不可达或接管结果未知时，App 只能提示用户立即检查官方入口，不能宣称写入已经停止。

---

# 8. 公开能力与错误【EXE-AUTO-API-001】

```text
create_pending_action(plan_event_ref, proposed_action, capital_decision)
process_pending_action(pending_action_id)
apply_venue_fact(pending_action_id?, venue_fact_ref)
collect_activation_pnl_inputs(activation_id, cutoff)
evaluate_activation_closure(activation_id, cutoff)
apply_user_takeover(activation_id, command_ref)
```

稳定错误至少包括：`CAP_REJECTED`、`DUPLICATE_IDENTITY_CONFLICT`、`PREDECESSOR_OPEN`、`NOT_SUBMITTED`、`SUBMISSION_RESULT_UNKNOWN`、`VENUE_REJECTED`、`POSITION_UNKNOWN`、`PROTECTION_UNKNOWN`、`PROTECTION_GAP`、`EXTERNAL_ACTIVITY_DETECTED`、`LOSS_UNKNOWN` 和 `USER_TAKEOVER_ACTIVE`。

---

# 9. 验证契约【EXE-AUTO-TST-001-REQ】

接受前至少证明：

1. 纯策略逻辑和框架 callback 无法直接取得场所写能力，所有真实写入都经过 `HalphaStrategyAdapter` 私有已持久动作门并核验 activation_id、UUID 与条款摘要，且之前已有同事务提交的 PlanEvent、CAP 结果和 PendingAction；
2. 32 位无连字符 UUID 在普通与条件订单的提交、查询、取消和重启恢复中原样往返；相同来源不同条款冲突；
3. 写调用自动重试关闭；崩溃前、PendingAction 提交后、`SUBMITTING` 后和响应保存前各窗口都只恢复原身份，UNKNOWN 不产生第二调用；
4. 授权 deadline 到期会幂等撤销/核对全部开放普通或条件增险订单；取消与成交竞争、部分成交和取消后重挂不超过剩余目标，未知旧单阻止新单；
5. 首次风险敞口和后来增量部分成交都被经资格化的场所保护覆盖；同一场所全平保护只有在仓位变化后仍自动覆盖且重启可恢复时才复用原身份，否则形成新的显式保护责任；UNKNOWN 不提交内容等价的第二保护，保护缺口按计划形成退出或接管；
6. 部分成交、取消竞争和晚到成交不超过已核对可减持仓；instrument-wide 平仓只有独占活动范围且无外部未知时可提交，归零后全部相关入场、保护和风险减少订单均按原身份清理并核对；
7. 启动 reconciliation、场所事件、持续持仓核对及按已持久 UUID 的公开单订单查询共同覆盖普通/条件订单、部分成交和持仓；关闭会因连续无响应而合成本地终态的组件定时器，不注册框架外部订单技术认领，关闭持久 cache 的重启后仍能按原 activation_id/UUID 恢复、查询和取消呈 EXTERNAL 技术身份的已知普通/算法订单并核对终态，未知 UUID 不被误撤或归属；
8. 最大允许损失只使用本激活 Decimal 实际盈亏、手续费与资金费；触线只在 PlanAllocation 锁存并触发退出，其他激活不影响，保证金/名义自然越界不触发硬平仓；
9. closure digest 只有在场所净持仓零、范围内无开放普通/算法订单、所有 Halpha PendingAction 已闭合且无在途/未知、无新增/增险/反向外部冲突时成立；正常关闭还要求费用完整，接管关闭允许精确损益保持 UNKNOWN；
10. 用户接管先冻结责任范围并持久化，再以不管理场所订单的行为停止并移除 HalphaStrategyAdapter，无自动撤单/平仓；匹配冻结范围的官方风险减少/关闭活动可帮助形成接管关闭，但不冒充 Halpha 动作，且同一激活不恢复写入；
11. 数据库只有 PendingAction 一个 EXE 记录族，不存在 WriteControl、SubmissionAttempt、ProtectionTask、ReconciliationItem 或隐藏核对工作器；
12. 当前适配器任一必需订单、身份、费用、资金费或 reconciliation 契约未通过 L4 资格化时，真实写入被拒绝且没有自研平行写路径。

---

# 10. 明确不建设与 L4 边界【EXE-AUTO-NON-001-REQ】

不建设第二场所写管线、自研交易所协议栈、自研订单状态机、自研 reconciliation、算法路由、通用保护策略平台、会在框架内部产生未持久子动作的便捷写路径、数据库写控制生命周期或独立保护/核对服务。

L4 只固定当前 NautilusTrader 与场所适配器版本、公开订单参数映射、普通/条件端点、配置、限频、超时、Windows 运行实例、账户模式和资格化证据；本 L3 不声称这些当前已经可用。
