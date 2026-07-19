# Halpha 决策与依据索引

**索引性质：** 非规范性导航文档  
**索引基准：** 2026-07-19
**覆盖范围：** 当前最新中文 L0–L4 文档  

本索引记录“为什么这样选择”：会影响产品方向或设计取舍的真实问题、稳定前提、关键权衡、未采用方向及需要重新审视的条件。条目可以点明所解释的决策，但不在这里规定项目必须怎样行动。

本索引与要求的定位边界是：能够直接判断符合或偏离的结论属于[要求与限制索引](requirement-constraint-index.zh-CN.md)；解释该结论为何适合 Halpha 当前长期边界的内容才属于本索引。对象、角色、状态和分类的含义属于[概念定义索引](concept-definition-index.zh-CN.md)。普通说明、推理过程、例子和没有实际取舍价值的背景不收录。

L0–L3 的最小归类单元是“文档 + `-RAT` 语义锚点”，且不得与另外两份索引重叠；新 L3 没有 `-RAT` 锚点时不以普通设计章节替代。L4 只收录当前建设选择的直接依据，以 YAML 稳定键路径归类，并链接到计划文件而不绑定易漂移的行号；它不升级为稳定产品语义。条目直接导航当前目标路径，历史依据由 Git commit 保存，不重复记录旧版本、状态、替代关系或历史副本。

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
| 选择最简半自动形态：用户配置并激活有界计划后，由机器值守、触发、检查和执行；不增加逐动作授权路径 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [半自动执行形态的选择依据【VIS-OPS-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#半自动执行形态的选择依据vis-ops-001-rat) |
| 竞争取舍依据：个人项目相对机构缺少数据、接入、分工、冗余和成本优势 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [5.2 个人量化方向的选择依据【VIS-ADV-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#52-个人量化方向的选择依据vis-adv-001-rat) |
| 可能的非对称性来自只选择适合个人资金规模的机会、低协调成本、专属知识积累和较低固定成本 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [5.2 个人量化方向的选择依据【VIS-ADV-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#52-个人量化方向的选择依据vis-adv-001-rat) |
| 这些资源条件只是待检验前提，不是既有 Alpha 或收益保证 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [5.2 个人量化方向的选择依据【VIS-ADV-001-RAT】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#52-个人量化方向的选择依据vis-adv-001-rat) |

## 流程与外部工具取舍

| 决策或依据 | 文档 | 章节 |
|---|---|---|

## 领域对象取舍依据

| 决策或依据 | 文档 | 章节 |
|---|---|---|
| 来源、派生、未知与修正只是同一事实记录的属性；当前一个 `VenueFact` 记录族足以支持消费者，拆成独立对象或固定五套时间字段只会增加个人维护成本 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [唯一职责与复杂度上限【DAT-SCP-001】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#0-唯一职责与复杂度上限dat-scp-001) |
| 一次外部动作只需要一个 ExecutionAction 承担从持久化到核对闭合的责任；提交、保护和核对是其内容与行为，不值得再拆成稳定对象 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [设计结论与复杂度上限【EXE-SCP-001】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#0-设计结论与复杂度上限exe-scp-001) |
| 个人项目所有者可直接从 Review 决定后续工作；第二交接记录和生命周期不会改变决定，只增加维护成本 | [HALPHA-OUT-001](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md) | [唯一职责与复杂度上限【OUT-SCP-001】](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md#0-唯一职责与复杂度上限out-scp-001) |
| SYS 只保留业务模块、应用边界、运行实体和隔离外部写入边界四个必要概念；新增系统边界必须由当前消费者、并发、隔离或重复故障证明必要 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [建立新边界的条件【SYS-BND-001-REQ-002】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#13-建立新边界的条件sys-bnd-001-req-002) |

## 架构、运行与复杂度取舍

| 决策或依据 | 文档 | 章节 |
|---|---|---|
| 采用个人项目尺度质量优先级：单一项目所有者和有限账户不需要机构级零停机 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [1.1 个人项目尺度的取舍依据【ARC-QLT-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#11-个人项目尺度的取舍依据arc-qlt-001-rat) |
| 技术取舍同时计入理解、测试、运行、故障、迁移和退出成本 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [1.1 个人项目尺度的取舍依据【ARC-QLT-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#11-个人项目尺度的取舍依据arc-qlt-001-rat) |
| 把平台无关业务流程、对象身份和权威状态放在共同应用与领域边界中，只把形态差异留在入口适配层，避免新增入口演变为状态迁移、业务重写、分叉和误授权 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [交互入口适配的选择依据【ARC-TOP-002-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#交互入口适配的选择依据arc-top-002-rat) |
| 成熟事务、进程管理、日志与现成备份足以覆盖当前主要运行需要 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [8.1 稳定性技术选择依据【ARC-OPS-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#81-稳定性技术选择依据arc-ops-001-rat) |
| 以常用路径可用、事实新鲜、真实动作防重、核对推进以及停止与重启安全衡量稳定性 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [8.1 稳定性技术选择依据【ARC-OPS-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#81-稳定性技术选择依据arc-ops-001-rat) |
| AI 只降低编码成本，不同比例降低理解、验证、运维、恢复和责任成本 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [复杂度判断依据【CON-DEV-001-RAT】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#复杂度判断依据con-dev-001-rat) |
| 稳定性优先来自成熟技术、简单结构、SYS 与 ENG 边界和业务领域自身正确性；重复故障出现前不自建专门稳定性平台 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [8.1 稳定性技术选择依据【ARC-OPS-001-RAT】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#81-稳定性技术选择依据arc-ops-001-rat) |

## 当前建设决策依据

| 决策或依据 | 文档 | 章节 |
|---|---|---|

## 当前简化取舍

| 决策或依据 | 文档 | 章节 |
|---|---|---|
| 个人项目前期的主要交付风险是业务错误和反馈过慢；功能正确性保持严格，治理强度只随真实外部写入、不可逆影响、实际并发和重复故障增加 | [HALPHA-ENG-001](L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md) | [定位与复杂度预算【ENG-SCP-001】](L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md#0-定位与复杂度预算eng-scp-001) |
| 一次计划激活已经能表达本次机器执行范围和资金限制；账户上限、授权、额度、停止与外置 gate 等额外对象不改变当前用户决定，只增加一致性成本 | [HALPHA-CAP-002](L3/HALPHA-CAP-002-activation-capital-and-action-checks.zh-CN.md) | [设计结论【CAP-AUTO-SUM-001】](L3/HALPHA-CAP-002-activation-capital-and-action-checks.zh-CN.md#0-设计结论cap-auto-sum-001) |
| 用户停止后以新激活重新进入比恢复状态机更清楚；它保留已有风险的保护和退出，同时避免旧授权被误复活 | [HALPHA-TRADEPLAN-002](L3/HALPHA-TRADEPLAN-002-machine-authorized-one-shot-trade-plan.zh-CN.md) | [三类用户控制【TRADEPLAN-AUTO-CTL-001】](L3/HALPHA-TRADEPLAN-002-machine-authorized-one-shot-trade-plan.zh-CN.md#4-三类用户控制tradeplan-auto-ctl-001) |
| 一个产品构建标识足以追溯实际运行输入；平行构建身份和状态没有当前运行消费者 | [HALPHA-ENG-002](L3/HALPHA-ENG-002-real-trade-core-technology-stack-and-build-boundaries.zh-CN.md) | [Windows、构建、迁移与备份【ENG-AUTO-BLD-001】](L3/HALPHA-ENG-002-real-trade-core-technology-stack-and-build-boundaries.zh-CN.md#5-windows构建迁移与备份eng-auto-bld-001) |
| 策略研究只写独立工作区且不接触产品数据库、秘密或场所写，因此可以立即并行；只有所有者选中结果时才成为普通产品变更 | [HALPHA-ALP-003](L3/HALPHA-ALP-003-research-workspace-and-evidence-handoff.zh-CN.md) | [设计结论【ALP-RSCH-SUM-001】](L3/HALPHA-ALP-003-research-workspace-and-evidence-handoff.zh-CN.md#0-设计结论alp-rsch-sum-001) |
| 只有当前决定提出直接测试无法回答的问题时才增加运行观察；固定小时数和自然日门会延迟反馈，但不会自行提高未覆盖代码的正确性 | [HALPHA-PLAN-001](L4/HALPHA-PLAN-001-current-construction-plan.yaml) | [当前计划](L4/HALPHA-PLAN-001-current-construction-plan.yaml) |
| 现有 Windows 10 主机和完整产品范围保持不变；如实记录供应商支持限制并验证实际主机，比无条件迁移或缩减更符合当前资源和目标 | [HALPHA-PLAN-001](L4/HALPHA-PLAN-001-current-construction-plan.yaml) | [当前计划](L4/HALPHA-PLAN-001-current-construction-plan.yaml) |

## 维护规则

- 只有会改变方向、范围、架构或复杂度取舍的长期问题、前提与理由才进入本索引。
- 若一句话可以直接用来判定实现是否合规，应移入独立 `-REQ` 章节或 L4 要求键路径；若只回答对象是什么，应移入 `-DEF`。
- 依据失效或出现相反证据时，修订拥有该取舍的最高适当层级，并说明哪些要求需要重审。
- 章节标题、编号或锚点变化时同步修正链接；索引摘要不得自行创造新决策。
