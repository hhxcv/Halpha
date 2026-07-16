# Halpha 机器授权与策略独占额度控制契约

**文档编号：** HALPHA-CAP-002  
**版本：** v1.1.0  
**文档状态：** ACCEPTED  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** CAP  
**所属实现模块：** `capital`  
**语言版本：** zh-CN  
**批准人：** Halpha 项目所有者  
**接受时间：** 2026-07-16T14:07:30+08:00  
**替代版本：** HALPHA-CAP-002@v1.0.0  
**上位文档或条款：** HALPHA-CAP-001 v2.9.0；HALPHA-CON-001 v2.10.0、HALPHA-ARC-001 v1.8.0、HALPHA-DOC-001 v1.10.0、HALPHA-ENG-001 v1.6.0  
**直接依赖：** HALPHA-TRADEPLAN-002 v0.9.0、HALPHA-DAT-002 v0.7.0  
**直接消费者：** HALPHA-EXE-002 v1.1.0、HALPHA-OUT-002 v0.7.0、HALPHA-UX-002 v0.10.0  
**适用纵向约束：** HALPHA-UX-001 v1.5.0；HALPHA-SYS-001 v1.5.0；HALPHA-ENG-001 v1.6.0  
**本文档负责：** Halpha 账户级资本边界、每激活互斥额度、机器授权、动作风险分类、两阶段检查、最大损失锁存、停止状态和额度释放  
**本文档不负责：** 决定用户投入规模；在 Binance 冻结或隔离资金；保证实际损失上限；定义策略条件、场所事实、订单生命周期或页面；选择当前账户、金额、杠杆或阈值  

---

# 0. 设计结论【CAP-AUTO-SUM-001】

用户激活策略时，为该激活独占分配 `max_margin`、`max_notional` 和 `max_allowed_loss`。多个策略可以同时激活，但同一额度不能被重复分配；资金始终留在 Binance 账户中，所谓“独占”是 Halpha 内部承诺，不是场所冻结、子账户隔离或损失保证。

`max_margin` 和 `max_notional` 只限制 Halpha 主动增加风险的动作。行情、费用、资金费或场所规则导致已有持仓自然越界时，CAP 阻止后续增险，但不要求因此自动减仓或平仓；如何减仓和平仓仍由策略、最大损失退出或用户指令决定。

`max_allowed_loss` 只计算本激活行为及其持仓的净结果：

```text
activation_net = realized_pnl + unrealized_pnl + funding - commission
activation_loss = max(-activation_net, 0)
```

达到阈值后不可逆地停止本激活新增风险，并要求退出本激活全部持仓。其他激活的盈利、亏损、费用或资金费既不触发也不抵扣该阈值。

CAP 只新增四个持久记录族：`AccountCapitalLimitVersion`、`MachineAuthorizationVersion`、`PlanAllocation` 和 `StopStateVersion`。每次检查结果嵌入 `PlanEvent` 或 `PendingAction`，不另建授权检查、风险决定或额度预留记录族。NautilusTrader `RiskEngine` 和 `Portfolio` 可作为技术防错与交叉校验，但不是激活额度、损失归属或授权权威。

---

# 1. 持久对象【CAP-AUTO-OBJ-001】

## 1.1 `AccountCapitalLimitVersion`

账户边界版本至少包含稳定身份、不可变版本、环境、账户、计价资产、允许 instrument 范围、Halpha 可分配的三个总额度、单位与换算约定、生效时间、用户指令和内容摘要。相同身份版本内容不同必须冲突。

账户边界是用户给 Halpha 的上限，不等于场所可用余额。收缩边界立即阻止新的分配和增险；它不撤销已有保护，也不因自然越界强制平仓。

## 1.2 `MachineAuthorizationVersion`

每次激活引用一个不可变机器授权版本，至少固定：

- 激活、计划、环境、账户、instrument、方向和持仓模式范围；
- 允许的动作种类及订单语义，例如入场、撤单、保护、止盈、减仓和平仓；
- 允许的订单类型、触发价类型、有效期、reduce-only/close-position 约束；
- 授权开始、截止时间、最大损失后的允许动作和未知结果处理；
- 用户控制、策略版本、参数摘要、额度条款摘要和内容摘要。

授权只允许固定集合内的动作，不产生动作义务。策略提议、CAP 批准和 EXE 执行必须引用同一授权版本；过期或内容冲突时禁止新增风险，保护和退出只按授权中明确保留的动作继续。

## 1.3 `PlanAllocation`

`PlanAllocation` 与一个 `activation_id` 一一对应，至少保存三个独占额度、计价资产、状态版本、当前已知持仓与开放增险责任摘要、预留摘要、损失事实 cutoff、最近资金费查询 cutoff、唯一的最大损失锁存、关闭证据引用和释放状态。两个 cutoff 只是本记录内的嵌入值，没有独立 identity、claim 或 worker；重启按它们和已去重 VenueFact 继续。最大损失是否已触线只以该记录为权威；TRADEPLAN、EXE、SYS 和 UX 只保存引用或派生显示。

状态只需 `HELD | EXIT_ONLY | TAKEOVER_HELD | RELEASED`：

- `HELD` 允许授权范围内增险；
- `EXIT_ONLY` 禁止增险，仍允许保护、撤单、减仓和平仓；
- `TAKEOVER_HELD` 表示 Halpha 已停止自动写入但仍保留额度，避免其他策略使用尚未证明释放的责任；
- `RELEASED` 只在关闭证据成立后进入，且不可重开。

额度不是数据库外的内存计数。分配、预留变化、最大损失锁存和释放均以预期版本、稳定锁顺序和本地事务提交。

## 1.4 `StopStateVersion`

`StopStateVersion` 是账户或激活范围内“是否停止新增风险”的唯一权威，保存原因、用户或系统来源、开始时间、适用授权版本、可选 `PlanAllocation.loss_latch` 引用和解除规则；它不复制最大损失布尔值。是否允许新增风险由当前 StopStateVersion、PlanAllocation 状态、授权和计划生命周期共同派生，不在 PlanActivation 另存开关。系统最大损失锁存不能被普通恢复命令解除；用户停止可由新的明确用户命令改变。停止状态不表示已撤单、已平仓或已接管。

---

# 2. 分配与互斥【CAP-AUTO-ALLOC-001】

创建分配时，在同一环境、账户和计价资产下锁定账户边界及所有未释放分配，并同时证明：

```text
sum(held.max_margin) + requested.max_margin <= account.max_margin
sum(held.max_notional) + requested.max_notional <= account.max_notional
sum(held.max_allowed_loss) + requested.max_allowed_loss <= account.max_allowed_loss
```

三个轴独立检查，任一失败即整体拒绝。`TAKEOVER_HELD` 仍计入求和。实际场所余额、保证金模式、杠杆和 instrument 规则还必须足够；但这些动态事实不能扩大用户给 Halpha 的静态边界。

不同激活不得借用闲置额度、用盈利抵消另一激活损失，或在场所总余额仍足够时跳过内部互斥。用户若要调整额度，必须形成新的计划/授权决定；运行中只允许收缩为不再增险的效果，不就地扩大已授权风险。

释放只接受 EXE 按其唯一完整闭合契约形成、并由 TRADEPLAN 完成状态引用的最终 `closure_digest`。CAP 不复制或缩短该证据清单；进程退出、策略实例停止、订单提交失败、用户接管、本地投影为零或不完整摘要都不能单独释放额度。

---

# 3. 动作分类【CAP-AUTO-CLS-001】

CAP 先按动作对最坏暴露的影响分类，再应用额度：

| 类别 | 典型动作 | 额度效果 |
|---|---|---|
| `RISK_INCREASING` | 新入场、增加数量、使未成交入场单更可能扩大承诺的替换 | 必须同时通过授权、停止状态、margin、notional 和 loss 检查 |
| `RISK_NEUTRAL` | 不扩大最坏暴露的撤单、查询和同身份核对 | 不消费新额度，但不得绕过授权和接管状态 |
| `RISK_REDUCING` | reduce-only/close-position 保护、止盈、减仓和平仓 | 即使 margin/notional 已自然越界仍可继续；不得反向开仓 |
| `AMBIGUOUS` | 缺价格、数量、持仓模式或场所映射，无法证明最坏暴露 | 拒绝并进入明确未知责任，不按乐观估算放行 |

订单名称不决定分类。例如限价单可以增险，条件单也可以是 close-position 减险。分类使用规范化订单语义、当前场所事实和最坏可执行数量；未知不能按零处理。

用户接管后所有 Halpha 场所写动作均不再授权，包括原本减险的自动动作；只读核对和用户在场所的直接操作不受 CAP 机器授权控制。

---

# 4. 两阶段检查【CAP-AUTO-CHK-001】

同一个纯检查契约在两个边界调用：

1. TRADEPLAN 提交 `ProposedAction` 时，在事务中检查并把决定、输入摘要和理由写入 `PlanEvent`；通过后由 EXE 在同一受控写路径建立 `PendingAction`。
2. EXE 即将越过真实写边界前，使用同一授权、分配和动作身份重新检查最新停止状态、授权有效期、场所事实截止点及预留；结果嵌入 `PendingAction` 状态推进。

两次检查不创建独立记录族。第二次失败只使原 `PendingAction` 确定拒绝或等待核对，不得新建动作、自动换订单类型或使用框架内部重试绕过决定。

增险动作至少按以下顺序证明：

1. 身份、内容摘要、环境和 instrument 一致；
2. 激活仍可新增风险，未接管、未过期、未锁存最大损失；
3. 动作类别和订单语义在机器授权内；
4. 来源事实足够新且归属无歧义；
5. 计入现有持仓、开放订单、在途动作和本动作最坏增量后，`max_notional` 不越界；
6. 按场所 instrument 与保证金模式计算的最坏新增保证金使 `max_margin` 不越界；
7. 本激活 `activation_loss < max_allowed_loss`；
8. 账户边界和场所动态可用性仍足够。

所有金额、数量和阈值比较由 Halpha `Decimal` 权威计算。适配库的二进制浮点 Portfolio/RiskEngine 可拒绝动作或报警，但不能扩大 CAP 已批准范围，也不能作为损失归属的唯一证据。

---

# 5. 损失归属与锁存【CAP-AUTO-LOSS-001】

损失输入只接受 DAT/EXE 可追溯到本激活的成交、持仓、手续费和资金费事实。场所账户汇总值、其他策略事件、外部手工订单或无法归属的修正不得分摊进本激活；归属未知时停止新增风险并核对。

计算使用同一计价资产、明确汇率截止点和 `Decimal`。手续费作为正成本从净结果扣除；资金费保留场所符号。达到或超过阈值的第一次事务提交同时：

- 锁存 `max_loss_reached=true` 及输入摘要；
- 将分配推进为 `EXIT_ONLY`；
- 建立引用该损失锁存的 StopStateVersion；
- 通知 TRADEPLAN 进入 `EXITING` 并产生退出全部本激活持仓的责任。

重复输入幂等；迟到费用可使最终损失进一步增加但不能解除锁存。阈值不是止损成交价，也不能保证滑点、跳空、强平或故障后的最终损失不超过额度。

---

# 6. 框架边界与故障恢复【CAP-AUTO-CMP-001】

NautilusTrader `RiskEngine`、`Portfolio`、instrument 精度和保证金信息优先复用，用于订单格式、防止明显无效动作和运行交叉校验。以下语义不可委托给框架：每激活互斥额度、Halpha 主动增险定义、最大损失口径、跨重启锁存、用户接管和释放证明。

数据库不可用时不以内存额度继续写入。重启时从四类记录和场所事实恢复，重新计算每个未释放激活的持仓、开放责任、损失和停止状态；与已持久摘要不一致时禁止新增风险并进入核对，而不是覆盖旧事实。

场所或框架对自然越界报警不自动生成强平动作。只有固定策略、最大损失规则或用户退出命令可以要求减仓/平仓。

---

# 7. 公开能力、错误与验证【CAP-AUTO-API-001】

公开能力最少包括：固定账户边界、创建机器授权、原子分配额度、分类并检查 proposal、提交前复核、更新本激活损失、停止/恢复新增风险、进入接管保留和按关闭证据释放。调用均携带稳定身份、内容摘要、预期版本和事实截止点。

稳定错误至少包括：`ACCOUNT_LIMIT_EXCEEDED`、`ALLOCATION_CONFLICT`、`AUTHORIZATION_MISMATCH`、`AUTHORIZATION_EXPIRED`、`NEW_RISK_STOPPED`、`MARGIN_LIMIT_EXCEEDED`、`NOTIONAL_LIMIT_EXCEEDED`、`MAX_LOSS_REACHED`、`ATTRIBUTION_UNKNOWN`、`VALUATION_UNKNOWN`、`TAKEOVER_ACTIVE`、`RELEASE_UNPROVEN` 和 `VERSION_CONFLICT`。

至少验证：

1. 并发激活不能重复分配三个额度轴；
2. 资金仍在 Binance 时，其他策略仍不能使用已分配份额；
3. margin/notional 自然越界只阻止增险，不强制退出；
4. 本激活净损失口径准确，其他激活不影响阈值；
5. 阈值触发原子停止新增风险并要求全退出，重启后仍锁存；
6. reduce-only/close-position 在自然越界时仍可通过，且不能反向开仓；
7. proposal 与提交前复核使用同一纯检查语义；
8. 用户接管停止所有自动写且额度保持到闭合证明；
9. 未知归属、价格、费用或写结果不按零处理；
10. Framework RiskEngine 不能扩大 Halpha CAP 决定。

---

# 8. 非目标、迁移与复杂度【CAP-AUTO-MIG-001】

本文不建设交易所资金隔离、资金调拨、自动组合优化、跨账户净额、借用额度、机构审批、多币种风险平台或收益/损失保证。

本契约将授权检查结果和预留变化吸收到现有 `PlanEvent`、`PendingAction` 与 `PlanAllocation`，删除独立 `CapitalAuthorizationCheck` 记录族；只保留四个 CAP 记录族。外部框架仅作技术防线，不复制产品额度状态。进程、worker、数据库和真实写路径数量均不增加，复杂度必须不高于本次修订前。
