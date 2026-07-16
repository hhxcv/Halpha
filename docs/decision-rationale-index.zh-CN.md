# Halpha 决策与依据索引

**索引性质：** 非规范性导航文档  
**索引基准：** 2026-07-16  
**覆盖范围：** 当前最新中文 L0–L4 文档  
**当前来源状态：** ACCEPTED

本索引记录“为什么这样选择”：会影响产品方向或设计取舍的真实问题、稳定前提、关键权衡、未采用方向及需要重新审视的条件。条目可以点明所解释的决策，但不在这里规定项目必须怎样行动。

本索引与要求的定位边界是：能够直接判断符合或偏离的结论属于[要求与限制索引](requirement-constraint-index.zh-CN.md)；解释该结论为何适合 Halpha 当前长期边界的内容才属于本索引。对象、角色、状态和分类的含义属于[概念定义索引](concept-definition-index.zh-CN.md)。普通说明、推理过程、例子和没有实际取舍价值的背景不收录。

L0–L3 的最小归类单元是“文档 + `-RAT` 语义锚点”，且不得与另外两份索引重叠；新 L3 没有 `-RAT` 锚点时不以普通设计章节替代。L4 只收录当前建设选择的直接依据，以 YAML 稳定键路径归类，并用行链接跳转到当前键位置；它不升级为稳定产品语义。当前每个文档编号只记录最新中文 ACCEPTED 正文，不重复记录旧版、英文、bundle、archive 或历史参考稿。当前 ACCEPTED 集包含 ALP、TRADEPLAN、DAT、CAP、EXE、OUT、UX、SYS、ENG 九份领域 L3；当前阶段采用哪些设计及采用范围由 L4 选择。

## 产品身份、问题与价值依据

| 决策或依据 | 文档 | 章节 |
|---|---|---|
| 工具前提：用户继续使用交易所、图表、新闻、数据与通用 AI | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [1.2 长期设计依据【VIS-IDN-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#12-长期设计依据vis-idn-001-rat) |
| 目标用户前提：用户理解基础交易概念，接受必要学习但拒绝无效繁琐 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [1.2 长期设计依据【VIS-IDN-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#12-长期设计依据vis-idn-001-rat) |
| 使用前提：用户愿意事前表达假设、反证、边界、条件和权限 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [1.2 长期设计依据【VIS-IDN-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#12-长期设计依据vis-idn-001-rat) |
| 维护前提：项目由项目所有者长期独立维护 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [1.2 长期设计依据【VIS-IDN-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#12-长期设计依据vis-idn-001-rat) |
| 长期设计前提：用户投入自有交易资本并承担交易结果，项目所有者投入开发成本，产品由单一用户使用 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [1.2 长期设计依据【VIS-IDN-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#12-长期设计依据vis-idn-001-rat) |
| 长期设计前提：市场竞争和优势衰减要求持续证伪与替换 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [1.2 长期设计依据【VIS-IDN-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#12-长期设计依据vis-idn-001-rat) |
| 长期设计前提：用户时间有限且碎片化，没有专职团队 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [1.2 长期设计依据【VIS-IDN-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#12-长期设计依据vis-idn-001-rat) |
| 长期设计前提：资本、维护资源和可承担负担均为个人尺度 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [1.2 长期设计依据【VIS-IDN-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#12-长期设计依据vis-idn-001-rat) |
| 产品问题依据：大量信息不能自然形成与当前账户、持仓和资金使用相关的判断 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [2.1 问题与判断依据【VIS-PRB-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#21-问题与判断依据vis-prb-001-rat) |
| 产品问题依据：分散的真实结果不会自然成为可归因的竞争证据 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [2.1 问题与判断依据【VIS-PRB-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#21-问题与判断依据vis-prb-001-rat) |
| 产品问题依据：用户无法持续研究和全天值守 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [2.1 问题与判断依据【VIS-PRB-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#21-问题与判断依据vis-prb-001-rat) |
| 产品问题依据：研究环境与真实数据、成本、流动性和执行存在断层 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [2.1 问题与判断依据【VIS-PRB-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#21-问题与判断依据vis-prb-001-rat) |
| 产品问题依据：真实优势范围有限、会衰减且需要持续替换 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [2.1 问题与判断依据【VIS-PRB-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#21-问题与判断依据vis-prb-001-rat) |
| 产品问题依据：正确判断会被临时改计划、重复动作和执行遗漏破坏 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [2.1 问题与判断依据【VIS-PRB-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#21-问题与判断依据vis-prb-001-rat) |
| 产品问题依据：AI 同时放大研究效率、伪优势和不可验证复杂度 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [2.1 问题与判断依据【VIS-PRB-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#21-问题与判断依据vis-prb-001-rat) |
| 产品问题依据：Beta、杠杆、偏差、成本遗漏和运气会制造表面盈利 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [2.1 问题与判断依据【VIS-PRB-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#21-问题与判断依据vis-prb-001-rat) |
| 选择半自动形态：机器值守、事件触发与用户确认已能构成完整产品 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [半自动执行形态的选择依据【VIS-OPS-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#半自动执行形态的选择依据vis-ops-001-rat) |
| 竞争取舍依据：个人项目相对机构缺少数据、接入、分工、冗余和成本优势 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [5.2 个人量化方向的选择依据【VIS-ADV-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#52-个人量化方向的选择依据vis-adv-001-rat) |
| 可能的非对称性来自只选择适合个人资金规模的机会、低协调成本、专属知识积累和较低固定成本 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [5.2 个人量化方向的选择依据【VIS-ADV-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#52-个人量化方向的选择依据vis-adv-001-rat) |
| 这些资源条件只是待检验前提，不是既有 Alpha 或收益保证 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [5.2 个人量化方向的选择依据【VIS-ADV-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#52-个人量化方向的选择依据vis-adv-001-rat) |

## 流程与外部工具取舍

| 决策或依据 | 文档 | 章节 |
|---|---|---|
| 核心流程取自形成判断、制定计划、正确行动和复盘学习的真实交易主线 | [HALPHA-FLOW-001](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md) | [0.1 流程选择依据【FLOW-SUM-001-RAT】](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md#01-流程选择依据flow-sum-001-rat) |
| 早期以用户频繁观察和随时停用为前提，成熟后再降低关注强度 | [HALPHA-FLOW-001](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md) | [0.1 流程选择依据【FLOW-SUM-001-RAT】](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md#01-流程选择依据flow-sum-001-rat) |
| 成熟外部工具优先承担其擅长的任务：交易场所负责官方账户操作，专业图表负责深度视觉分析，新闻和数据源提供原始材料，研究环境支持探索，通用 AI 只做非权威整理和生成 | [HALPHA-FLOW-001](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md) | [3.1 外部工具分工依据【FLOW-TOOL-001-RAT】](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md#31-外部工具分工依据flow-tool-001-rat) |

## 领域对象取舍依据

| 决策或依据 | 文档 | 章节 |
|---|---|---|
| 不建立互斥的信息对象类型：来源、推导方式、核对状态和所有权是可同时成立的记录关系 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [不建立互斥信息对象类型的依据【DAT-ROL-001-RAT】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#不建立互斥信息对象类型的依据dat-rol-001-rat) |
| 分开五类时间语义：它们分别支持事件解释、延迟判断、处理追踪、决定时点和事实截止点；无消费者时不增加时间字段 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [五类时间语义的选择依据【DAT-TIM-001-RAT】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#五类时间语义的选择依据dat-tim-001-rat) |
| POR 未满足深化条件时只保留进入条件和人工交接：少量资金用途可由用户直接比较，长期保存比较内容和复核过程没有重复消费者 | [HALPHA-POR-001](L2/HALPHA-POR-001-portfolio-and-capital-allocation.zh-CN.md) | [0.1 未满足深化条件时只保留边界的依据【POR-SCP-001-RAT】](L2/HALPHA-POR-001-portfolio-and-capital-allocation.zh-CN.md#01-未满足深化条件时只保留边界的依据por-scp-001-rat) |
| TRADEPLAN 保留六项可独立判断的稳定计划语义，但不要求六个物理记录族；启用记录可以表达当前判断投影，事件可以携带判断输入与历史，前提是身份、截止点、拒绝、恢复和结束结果仍可验证 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [六项稳定计划语义的选择依据【TRADEPLAN-OBJ-001-RAT】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#六项稳定计划语义的选择依据tradeplan-obj-001-rat) |
| 交易计划状态分为内容、运行、条件、交互、外部责任和结果六轴，避免暂停、版本有效和外部责任被一个总状态混淆 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [六条状态轴的选择依据【TRADEPLAN-AXS-001-RAT】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#六条状态轴的选择依据tradeplan-axs-001-rat) |
| 七类计划决定只作为完整性检查维度，分别回答理由、对象、进入、失效、规模、期限和触发后处理，不建立七个对象 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [七类决定的选择依据【TRADEPLAN-DEC-001-RAT】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#七类决定的选择依据tradeplan-dec-001-rat) |
| 六类条件用途用于区分同一观察的不同资金使用、真实动作和失败处理后果，不建立六套条件对象 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [六类条件用途的选择依据【TRADEPLAN-CND-001-RAT】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#六类条件用途的选择依据tradeplan-cnd-001-rat) |
| CAP 分开资金边界落实、策略激活额度配额、真实资金操作权限、停用状态和动作检查结果，因为五者分别改变额度隔离、写入权限、停用或执行责任；配额之外的预留、风险总分和独立许可没有独立高价值消费者 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [1.3 五项稳定语义的选择依据【CAP-OBJ-001-RAT】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#13-五项稳定语义的选择依据cap-obj-001-rat) |
| CAP 分开外部实际余额、Halpha 全局资金上限和单笔资金上限，并让风险减少/保护动作不占用新增资金额度，是为了避免把用户入金误当成授权、漏算并发占用或阻塞退出路径，同时不引入资金预留和复杂风险模型 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [三种额度分离依据【CAP-ENV-002-RAT】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#三种额度分离依据cap-env-002-rat) |
| EXE 的六项稳定执行语义是防重复和恢复责任所需的最小可验证分离，不要求六个物理记录族；提交、场所结果、保护和核对证据可以嵌入单一待执行动作记录族，但不能覆盖历史或混淆未知与责任 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [稳定执行语义的选择依据【EXE-OBJ-001-RAT】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#稳定执行语义的选择依据exe-obj-001-rat) |
| UX 只保留用户交互任务、用户操作指令、用户操作处理回执和用户任务通知；任务信息与决定预览可从拥有领域重建 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [四类交互对象的选择依据【UX-OBJ-001-RAT】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#四类交互对象的选择依据ux-obj-001-rat) |
| UX 的使用场景只决定注意力与恢复强度，四层信息只决定展示深度；二者不形成会话实体、页面类型或业务状态 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [使用场景与四层信息的选择依据【UX-SEM-001-RAT】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#使用场景与四层信息的选择依据ux-sem-001-rat) |
| SYS 只定义六类有独立语义或故障边界的运行时构件；进程、主机和部署单元不作为业务构件概念 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [1.3 六类运行时构件的选择依据【SYS-BND-001-RAT】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#13-六类运行时构件的选择依据sys-bnd-001-rat) |
| SYS 其余分类只在改变调用、持久化、恢复或所有权行为时保留；框架和中间件变化不产生新分类 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [其余系统分类的保留依据【SYS-SEM-001-RAT】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#14-其余系统分类的保留依据sys-sem-001-rat) |

## 架构、运行与复杂度取舍

| 决策或依据 | 文档 | 章节 |
|---|---|---|
| 采用个人项目尺度质量优先级：单一项目所有者和有限账户不需要机构级零停机 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [1.1 个人项目尺度的取舍依据【ARC-QLT-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#11-个人项目尺度的取舍依据arc-qlt-001-rat) |
| 技术取舍同时计入理解、测试、运行、故障、迁移和退出成本 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [1.1 个人项目尺度的取舍依据【ARC-QLT-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#11-个人项目尺度的取舍依据arc-qlt-001-rat) |
| 成熟事务、进程管理、日志与现成备份足以覆盖当前主要运行需要 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [8.1 稳定性技术选择依据【ARC-OPS-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#81-稳定性技术选择依据arc-ops-001-rat) |
| 以常用路径可用、事实新鲜、真实动作防重、核对推进以及停止与重启安全衡量稳定性 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [8.1 稳定性技术选择依据【ARC-OPS-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#81-稳定性技术选择依据arc-ops-001-rat) |
| AI 只降低编码成本，不同比例降低理解、验证、运维、恢复和责任成本 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [复杂度判断依据【CON-DEV-001-RAT】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#复杂度判断依据con-dev-001-rat) |
| 稳定性优先来自成熟技术、简单结构、SYS 与 ENG 边界和业务领域自身正确性；重复故障出现前不自建专门稳定性平台 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [8.1 稳定性技术选择依据【ARC-OPS-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#81-稳定性技术选择依据arc-ops-001-rat) |
| ENG 使用三档影响级别选择相称验证；分类不形成工程认可或准入对象，相邻级别长期采用相同验证时独立分级失去价值 | [HALPHA-ENG-001](L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md) | [2.3 三档影响级别的选择依据【ENG-IMP-001-RAT】](L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md#23-三档影响级别的选择依据eng-imp-001-rat) |

## 当前建设决策依据

| 决策或依据 | 文档 | 章节 |
|---|---|---|
| 已知 L0–L2 冲突不伪装为闭合，也不得由 L4 豁免；四项冲突关闭前 D00 与 B01–B05 保持阻断，只允许无产品语义、无真实写能力的隔离 B00 资格化 | [HALPHA-PLAN-001](L4/HALPHA-PLAN-001-current-construction-plan.yaml) | [formalization_record](L4/HALPHA-PLAN-001-current-construction-plan.yaml#L107) |
| 当前组件能力取舍：订单保护以显式数量 `reduce_only` 代替 `close_position`；历史回测使用 reference-price/fee 代理并将资金费标为 `NOT_MODELED`，不自研结算器、不切换 2.0 RC、也不设自动盈利硬门；恢复只采用 `external_order_claims=None` 单一路径，任一资格化失败即阻断，不预建第二恢复拓扑 | [HALPHA-PLAN-001](L4/HALPHA-PLAN-001-current-construction-plan.yaml) | [owner_decisions_accepted](L4/HALPHA-PLAN-001-current-construction-plan.yaml#L90) |
| 以正式化前设计为比较基线，删除重复自研后，权威持久记录族由 26 降至不超过 16、持久工作器类别由 5 降至不超过 2，其他结构计数不增加 | [HALPHA-PLAN-001](L4/HALPHA-PLAN-001-current-construction-plan.yaml) | [complexity_budget.comparison_baseline / complexity_budget.before](L4/HALPHA-PLAN-001-current-construction-plan.yaml#L151) |

## 维护规则

- 只有会改变方向、范围、架构或复杂度取舍的长期问题、前提与理由才进入本索引。
- 若一句话可以直接用来判定实现是否合规，应移入独立 `-REQ` 章节或 L4 要求键路径；若只回答对象是什么，应移入 `-DEF`。
- 依据失效或出现相反证据时，修订拥有该取舍的最高适当层级，并说明哪些要求需要重审。
- 章节标题、编号或锚点变化时同步修正链接；索引摘要不得自行创造新决策。
