# Halpha 概念定义索引

**索引性质：** 非规范性导航文档  
**索引基准：** 2026-07-16  
**覆盖范围：** 当前最新中文 L0–L4 文档  
**当前来源状态：** ACCEPTED

本索引只收录正文中确有稳定特殊含义、会被反复引用的概念。每个可独立引用的对象单列一行；同一组状态值或分类值共同定义一个分类时，按一个分类概念记录。普通词语、一次性说明、纯要求、当前计划和已删除的低价值抽象不进入本索引。

每个文档编号只记录当前中文 ACCEPTED 正文；不重复记录旧版、英文、bundle 或 archive。当前九份 L3 文档均复用 L2 已定义概念，没有新增 `-DEF` 概念锚点；L4 只记录当前事实与建设计划，不定义稳定概念。成熟能力优先、按组件能力调整和最小自研属于要求与取舍，不因反复使用而另造概念；分别见[要求与限制索引](requirement-constraint-index.zh-CN.md)和[决策与依据索引](decision-rationale-index.zh-CN.md)。

当前实体与产物设计仍少；现有九份领域 L3 以字段、状态、接口和测试精确实现 L2 对象，不增加平行稳定对象，因此暂不建立第四份索引。索引中分列稳定语义不表示每项都必须成为独立物理记录族：当前 TRADEPLAN 可在启用与事件记录中表达条件责任，EXE 可在单一待执行动作记录族中保留提交、场所结果、保护和核对责任。已经稳定且需要反复引用的对象仍按概念逐行记录，具体产物待出现更多真实消费者和具体设计后再评估。

## 文档、规范与责任结构

| 概念 | 文档 | 章节 |
|---|---|---|
| 规范文档状态：提议、接受、被替代与撤回 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [规范文档状态定义【CON-GOV-002-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#规范文档状态定义con-gov-002-def) |
| 当前规范来源：拥有某项含义并确定其权威正文位置 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [权威与责任定义【CON-GOV-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#权威与责任定义con-gov-001-def) |
| 规范责任层次：宪法、下位规范、机器规范、实现与符合性证据 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [权威与责任定义【CON-GOV-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#权威与责任定义con-gov-001-def) |
| 规范性用语强度：“必须/不得”“应/不应”“可以” | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [规范性用语定义【CON-GOV-003-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#规范性用语定义con-gov-003-def) |
| 共同规范语言文本：同一文档编号与版本的中英文并行正文 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [共同规范语言文本定义【CON-GOV-006-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#共同规范语言文本定义con-gov-006-def) |
| Halpha 文档层级：L0 项目原则、L1 总体原则、L2 领域关键内容、L3 长期稳定详细设计、L4 分阶段落地与当前记录 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [文档层级结构定义【DOC-STR-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#文档层级结构定义doc-str-001-def) |
| 文档层级定位：项目原则、总体原则、领域关键内容、长期稳定的领域详细设计与分阶段落地 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [各层定位、唯一职责与落地区分【DOC-OWN-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#各层定位唯一职责与落地区分doc-own-001-def) |
| 文档层级职责：L0 定项目最高原则，L1 定总体原则，L2 定领域关键内容、目标与设计原则，L3 定长期稳定详细设计，L4 定阶段性实施目标并记录当前建设事实 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [各层定位、唯一职责与落地区分【DOC-OWN-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#各层定位唯一职责与落地区分doc-own-001-def) |
| L2 稳定语义责任地图：每项稳定语义都有唯一 L2 语义所有者，但不代表等量建设 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [L2–L4 对象与分类定义【DOC-L24-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#l2l4-对象与分类定义doc-l24-001-def) |
| L2 边界深度：只明确职责、不负责范围、交付边界与失败结果 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [L2–L4 对象与分类定义【DOC-L24-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#l2l4-对象与分类定义doc-l24-001-def) |
| L2 当前需求深度：定义当前消费者所需对象、决定、状态边界、交接与验收 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [L2–L4 对象与分类定义【DOC-L24-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#l2l4-对象与分类定义doc-l24-001-def) |
| L2 复用扩展深度：多个真实消费者出现后才增加复用生命周期和公共规则 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [L2–L4 对象与分类定义【DOC-L24-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#l2l4-对象与分类定义doc-l24-001-def) |
| 横向业务责任：拥有一段连续业务及其对象生命周期与决定权 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [L2–L4 对象与分类定义【DOC-L24-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#l2l4-对象与分类定义doc-l24-001-def) |
| 纵向约束责任：贯穿多个业务领域的一类共同约束、质量或技术责任 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [L2–L4 对象与分类定义【DOC-L24-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#l2l4-对象与分类定义doc-l24-001-def) |
| 领域 L3：由一个主要语义所有者精确实现其 L2 语义的设计 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [L2–L4 对象与分类定义【DOC-L24-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#l2l4-对象与分类定义doc-l24-001-def) |
| 编排 L3：只拥有必要身份、顺序、责任交接和完成汇总的跨领域设计 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [L2–L4 对象与分类定义【DOC-L24-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#l2l4-对象与分类定义doc-l24-001-def) |
| 横向业务与纵向约束两个独立责任维度 | [HALPHA-FLOW-001](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md) | [两个责任维度【FLOW-HOF-001-DEF】](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md#91-两个责任维度flow-hof-001-def) |
| 十一项责任地图：CTX、ALP、POR、TRADEPLAN、EXE、OUT 六项横向业务责任与 CAP、DAT、UX、SYS、ENG 五项纵向约束责任 | [HALPHA-FLOW-001](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md) | [两个责任维度【FLOW-HOF-001-DEF】](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md#91-两个责任维度flow-hof-001-def) |

## 产品、用户与经济结果

| 概念 | 文档 | 章节 |
|---|---|---|
| Halpha：由用户投入交易资本并使用、由项目所有者承担建设投入与产品成功责任的个人交易决策、执行与学习系统 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [项目身份定义【CON-MIS-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#项目身份定义con-mis-001-def) |
| 项目所有者：承担开发时间、金钱和维护投入，决定项目设计与当前建设计划并评价产品成功与建设成本；不因该身份取得用户的交易资本或产品使用决定权，可兼任用户和开发者 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [项目所有者定义【CON-USR-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#项目所有者定义con-usr-001-def) |
| 用户：投入本人交易资本并使用 Halpha，决定产品使用与资本控制事项并取得真实账户净结果和投资 Alpha；当前只有一位用户，可与项目所有者兼任但视角不合并 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [用户、开发者与人工路径的身份边界【CON-USR-002-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#用户开发者与人工路径的身份边界con-usr-002-def) |
| 账户净结果：剔除外部资金流并计入真实交易成本后的账户结果 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [经济结果概念定义【CON-ECO-002-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#经济结果概念定义con-eco-002-def) |
| 投资 Alpha：相对事前基准、扣除成本并按约定风险调整后的超额投资结果 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [经济结果概念定义【CON-ECO-002-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#经济结果概念定义con-eco-002-def) |
| 产品增量价值：相对事前替代方式、扣除可归属增量成本后的 Halpha 净贡献 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [经济结果概念定义【CON-ECO-002-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#经济结果概念定义con-eco-002-def) |
| 资金使用上限与范围：用户在系统外作出交易资本决定后配置给 Halpha 的执行边界 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [资金使用上限与范围定义【CON-CAP-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#资金使用上限与范围定义con-cap-001-def) |
| 真实验证（Real Validation）：表示证据来自受控真实资金环境的限定，不是独立产品路径、交易计划、权限等级、资金规模或测试方法；使用该限定的活动仍须服从明确目标、当前资金使用上限与范围、适用权限和停止边界 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [真实验证定义【CON-VAL-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#真实验证定义con-val-001-def) |
| 验证计划：组织验证目标、环境、资金范围、授权路径、停止条件和证据要求的业务计划；不替代真实动作通常所需的交易计划，也不替代例外动作所需的固定决定或指令 | [HALPHA-FLOW-001](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md) | [验证计划定义【FLOW-VAL-001-DEF】](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md#验证计划定义flow-val-001-def) |
| 金融风险控制：使用用户设定的资金使用上限与范围、固定的决定依据和动作前风险检查，约束 Halpha 正确运行时仍不适当的真实动作 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [金融风险控制的宪法级定义【CON-CAP-002-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#金融风险控制的宪法级定义con-cap-002-def) |
| 稳定运行：核心能力在预期条件下可靠可用的产品结果 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [三项责任定义【CON-OPS-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#稳定运行功能正确性与系统风险缓解的责任定义con-ops-001-def) |
| 功能正确性：相同有效事实与配置产生可解释决定，真实动作唯一、可核对，且离线回放不再次改变外部账户 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [三项责任定义【CON-OPS-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#稳定运行功能正确性与系统风险缓解的责任定义con-ops-001-def) |
| 系统自身风险缓解：限制主机、依赖、网络、凭据或运行环境故障与失控影响 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [三项责任定义【CON-OPS-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#稳定运行功能正确性与系统风险缓解的责任定义con-ops-001-def) |
| 三类控制要求：金融风险控制、功能正确性、系统自身风险缓解 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [三类控制要求定义【CON-CMP-003-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#三类控制要求定义con-cmp-003-def) |
| 产品价值类别：交易盈利、判断计划、执行、UX、稳定、系统风险缓解、学习与金融风险控制 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [产品价值类别定义【VIS-VAL-001-DEF】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#31-产品价值类别定义vis-val-001-def) |
| 候选优势：带可证伪经济机制、适用范围、成本假设和失败条件的产品级假设 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [候选优势定义【VIS-ADV-001-DEF】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#候选优势定义vis-adv-001-def) |

## 真人身份与非真人运行主体

| 概念 | 文档 | 章节 |
|---|---|---|
| 用户与项目所有者的关系：用户投入交易资本并使用产品，项目所有者投入开发成本并决定项目设计与建设计划；当前可由同一真人承担，但产品使用、资本控制和项目建设视角必须区分 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [用户、开发者与人工路径的身份边界【CON-USR-002-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#用户开发者与人工路径的身份边界con-usr-002-def) |
| 人工处理与人工接管：用户通过 Halpha 界面或交易场所官方入口亲自处理，不是新的运行主体、权限模式或审批角色 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [用户、开发者与人工路径的身份边界【CON-USR-002-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#用户开发者与人工路径的身份边界con-usr-002-def) |
| 开发者：执行开发、验证或发布工作的主体，可以是项目所有者或 AI 工具，但不因此获得用户的资金决定权或外部账户控制权 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [用户、开发者与人工路径的身份边界【CON-USR-002-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#用户开发者与人工路径的身份边界con-usr-002-def) |
| 产品参与者边界：用户作出产品使用与资本控制决定，项目所有者决定项目建设，Halpha 在已接受规则与用户决定内提供产品能力，外部系统与工具提供事实、计算、研究或场所能力；运行实体由 ARC、SYS 与下位设计拥有 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [参与者边界【VIS-OPS-001-DEF】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#参与者边界vis-ops-001-def) |
| 语义所有者、主要语义所有者与协调所有者：文档或 L2/L3 的责任归属，不是真人身份、运行主体或授权 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [语义所有者与项目所有者的区分【DOC-SEM-001-DEF】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#语义所有者与项目所有者的区分doc-sem-001-def) |

## 用户任务域、用户交互任务、研究与策略

| 概念 | 文档 | 章节 |
|---|---|---|
| 六类用户任务域：市场情报、策略研究、交易计划、交易执行、账户记录、复盘学习 | [HALPHA-FLOW-001](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md) | [六类用户任务域定义【FLOW-UX-001-DEF】](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md#六类用户任务域定义flow-ux-001-def) |
| CTX：把尚未由其他领域承担现实责任的问题、机会或风险线索识别为研究或交易计划候选，并支持用户决定其下一步去向的领域 | [HALPHA-CTX-001](L2/HALPHA-CTX-001-candidate-and-decision-context.zh-CN.md) | [0.1 CTX 责任定义【CTX-SCP-001-DEF】](L2/HALPHA-CTX-001-candidate-and-decision-context.zh-CN.md#01-ctx-责任定义ctx-scp-001-def) |
| 研究或交易计划候选：待决定是否进入正式经济研究或交易计划形成的具体问题、机会或风险线索；“候选”不表示经济价值或交易资格 | [HALPHA-CTX-001](L2/HALPHA-CTX-001-candidate-and-decision-context.zh-CN.md) | [研究或交易计划候选定义【CTX-CAN-001-DEF】](L2/HALPHA-CTX-001-candidate-and-decision-context.zh-CN.md#11-研究或交易计划候选定义ctx-can-001-def) |
| 研究或交易计划候选去向决定：用户针对一个明确候选作出的进入研究、进入计划、等待、结束或当前不形成计划的选择；规则明确且无需主观判断时可由 Halpha 形成 | [HALPHA-CTX-001](L2/HALPHA-CTX-001-candidate-and-decision-context.zh-CN.md) | [研究或交易计划候选去向决定定义【CTX-DEC-001-DEF】](L2/HALPHA-CTX-001-candidate-and-decision-context.zh-CN.md#12-研究或交易计划候选去向决定定义ctx-dec-001-def) |
| 正式经济研究：对一个经济主张或固定交易策略在明确适用范围、基准、成本、现实约束和不确定性下所得支持进行评价的研究 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [1. 进入与退出边界【ALP-OBJ-001】](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#1-进入与退出边界alp-obj-001) |
| 经济证据判断：对被评价对象在明确适用范围内形成的支持、不支持、证据不足或无法判断的结论及其主要限制 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [1.2 退出边界](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#12-退出边界) |
| 交易策略：固定输入和条件怎样形成候选计划依据的规则表达 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [3. 交易策略与计划交接【ALP-STR-001】](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#3-交易策略与计划交接alp-str-001) |
| 固定策略提供的交易计划依据：固定交易策略向 TRADEPLAN 交付的、带适用边界的计划形成输入 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [1.2 退出边界](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#12-退出边界) |

## 交易计划、资金权限与执行

| 概念 | 文档 | 章节 |
|---|---|---|
| 真实动作：Halpha 向真实交易场所或账户发起、可能造成实际变化的外部操作；不包括只读、历史研究、历史行情回放、交易所模拟盘和用户官方入口独立操作，也不等于成交结果或待执行动作记录 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [真实动作定义【CON-ACT-001-DEF】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#真实动作定义con-act-001-def) |
| 交易计划依据：由上游明确选择、带来源和用途、用于进入计划设计的输入 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [交易计划依据与责任终点定义【TRADEPLAN-SCP-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#交易计划依据与责任终点定义tradeplan-scp-001-def) |
| 交易计划责任终点：计划不再形成新事件且外部责任闭合或明确移交 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [交易计划依据与责任终点定义【TRADEPLAN-SCP-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#交易计划依据与责任终点定义tradeplan-scp-001-def) |
| 交易计划草案：允许修改、尚未具备运行效力的七类决定工作对象 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [稳定计划语义定义【TRADEPLAN-OBJ-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#稳定计划语义定义tradeplan-obj-001-def) |
| 交易计划资金需求：用户确需比较资金用途时，从交易计划依据或草案按需生成的资金规模和用途需求；不独立维护、不占用资金或授予动作权限 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [稳定计划语义定义【TRADEPLAN-OBJ-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#稳定计划语义定义tradeplan-obj-001-def) |
| 交易计划版本：固定完整计划决定及决定性引用的不可变版本 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [稳定计划语义定义【TRADEPLAN-OBJ-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#稳定计划语义定义tradeplan-obj-001-def) |
| 交易计划启用：使计划版本在明确范围和期限内承担观察、事件与交接责任的决定 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [稳定计划语义定义【TRADEPLAN-OBJ-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#稳定计划语义定义tradeplan-obj-001-def) |
| 交易计划条件判断：对计划条件在给定事实截止点作出的判定 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [稳定计划语义定义【TRADEPLAN-OBJ-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#稳定计划语义定义tradeplan-obj-001-def) |
| 交易计划事件：由条件、人工决定、外部结果或时间变化形成并固定计划版本与事实截止点的不可变计划历史记录 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [交易计划事件定义【TRADEPLAN-EVT-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#交易计划事件定义tradeplan-evt-001-def) |
| 交易计划状态轴：内容、运行、条件、交互、外部责任和结果六条独立维度 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [交易计划六条状态轴定义【TRADEPLAN-AXS-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#交易计划六条状态轴定义tradeplan-axs-001-def) |
| 拟执行动作：由适用的交易计划、保护/风险减少决定或用户明确指令形成，尚未进入执行责任的不可变拟执行内容 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [拟执行动作定义【TRADEPLAN-HOF-002-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#拟执行动作定义tradeplan-hof-002-def) |
| 完整交易计划：为什么、对象、进入、失效、数量、期限和触发处理七类决定的组合 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [交易计划七类决定定义【TRADEPLAN-DEC-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#21-交易计划七类决定定义tradeplan-dec-001-def) |
| 交易计划条件用途：进入、失效、到期、复核、退出或保护、通知 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [交易计划六类条件用途定义【TRADEPLAN-CND-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#交易计划六类条件用途定义tradeplan-cnd-001-def) |
| 交易计划条件无法判定：所需事实、时间或依赖不足以得出成立或不成立 | [HALPHA-TRADEPLAN-001](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md) | [交易计划条件无法判定定义【TRADEPLAN-EVL-001-DEF】](L2/HALPHA-TRADEPLAN-001-trade-plan-and-condition-lifecycle.zh-CN.md#交易计划条件无法判定定义tradeplan-evl-001-def) |
| CAP：负责在 Halpha 内落实资金使用上限与范围，并拥有 Halpha 真实资金操作权限、Halpha 新增真实动作停用状态和拟执行动作资金与权限检查结果语义的领域 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [CAP 定位定义【CAP-SCP-001-DEF】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#01-cap-定位定义cap-scp-001-def) |
| 资金使用上限与范围的记录与执行规则：Halpha 如何记录 CON 定义的边界、识别其适用版本并在动作检查中执行 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [CAP 负责的稳定语义定义【CAP-OBJ-001-DEF】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#11-cap-负责的稳定语义定义cap-obj-001-def) |
| 策略激活额度配额：用户为一次策略激活分配的最大保证金、最大名义仓位和最大允许损失三轴互斥额度，以及该激活结束时的释放边界 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [CAP 负责的稳定语义定义【CAP-OBJ-001-DEF】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#11-cap-负责的稳定语义定义cap-obj-001-def) |
| Halpha 全局资金上限：一个资本边界版本范围内 Halpha 已确认敞口、开放订单、未决动作保守占用和新动作后保守敞口的总边界 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [用户在 Halpha 外投入的交易资本、Halpha 全局上限与单笔上限【CAP-ENV-002】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#23-用户在-halpha-外投入的交易资本halpha-全局上限与单笔上限cap-env-002) |
| 单笔资金上限：单个不可变拟执行动作在场所量化后的名义金额上限 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [用户在 Halpha 外投入的交易资本、Halpha 全局上限与单笔上限【CAP-ENV-002】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#23-用户在-halpha-外投入的交易资本halpha-全局上限与单笔上限cap-env-002) |
| Halpha 真实资金操作权限：Halpha 禁止真实写入、经交易计划当前确认后逐次写入（人工授权）或在计划内自动写入（机器授权）的最高权限 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [Halpha 真实资金操作权限定义【CAP-MOD-001-DEF】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#31-halpha-真实资金操作权限定义cap-mod-001-def) |
| Halpha 新增真实动作停用状态：当前适用范围按新增资金动作、保护动作或全部 Halpha 动作是否禁止发起新的真实动作，以及由谁、因何停用 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [CAP 负责的稳定语义定义【CAP-OBJ-001-DEF】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#11-cap-负责的稳定语义定义cap-obj-001-def) |
| 拟执行动作资金与权限检查结果：拟执行动作是否超出资金使用上限与范围、Halpha 真实资金操作权限或 Halpha 新增真实动作停用状态的判定 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [CAP 负责的稳定语义定义【CAP-OBJ-001-DEF】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#11-cap-负责的稳定语义定义cap-obj-001-def) |
| 交易场所或账户变化：已经或可能改变交易场所订单、成交、持仓、保护或余额的实际变化 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [稳定执行语义定义【EXE-OBJ-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#交易场所或账户变化与稳定执行语义定义exe-obj-001-def) |
| 待执行动作记录：可能产生交易场所或账户变化的不可变拟执行内容及其处理范围 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [稳定执行语义定义【EXE-OBJ-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#交易场所或账户变化与稳定执行语义定义exe-obj-001-def) |
| 外部写入控制权：某写入范围内当前唯一 Halpha 执行器拥有的可验证写入控制权 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [稳定执行语义定义【EXE-OBJ-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#交易场所或账户变化与稳定执行语义定义exe-obj-001-def) |
| 交易场所提交记录：一个待执行动作记录向场所发起的一次可追溯尝试 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [稳定执行语义定义【EXE-OBJ-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#交易场所或账户变化与稳定执行语义定义exe-obj-001-def) |
| 交易场所结果引用：场所订单、成交、划转、保护或其他交易场所或账户变化的稳定身份与关联 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [稳定执行语义定义【EXE-OBJ-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#交易场所或账户变化与稳定执行语义定义exe-obj-001-def) |
| 风险敞口保护任务：持续记录风险敞口所需保护及其建立、验证、维持、替换和移交状态的工作对象 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [风险敞口保护任务定义【EXE-PRT-002-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#81-风险敞口保护任务定义exe-prt-002-def) |
| 交易执行核对事项：闭合待执行内容、场所尝试、外部身份、事实和资金责任的工作对象 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [稳定执行语义定义【EXE-OBJ-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#交易场所或账户变化与稳定执行语义定义exe-obj-001-def) |
| 交易场所或账户变化分界：Halpha 已保存待执行动作记录、但外部不可回滚变化尚未或可能已经开始的协议边界 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [交易场所或账户变化分界定义【EXE-BND-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#交易场所或账户变化分界定义exe-bnd-001-def) |
| 唯一外部写入执行器：在一个可能相互影响真实订单或防重复提交能力的写入范围内，唯一获准持有外部写入控制权并发出场所命令的 Halpha 运行实体 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [唯一外部写入执行器定义【EXE-OWN-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#41-唯一外部写入执行器定义exe-own-001-def) |
| 交易场所对象对应关系：内部待执行动作与场所客户端、订单、成交和保护对象的稳定对应关系 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [交易场所对象对应关系定义【EXE-VEN-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#51-交易场所对象对应关系定义exe-ven-001-def) |
| 执行结果未决：可能已越过交易场所或账户变化分界但无法确认实际结果的执行状态 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [执行结果未决定义【EXE-UNK-001-DEF】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#执行结果未决定义exe-unk-001-def) |

## 数据、事实与时间

| 概念 | 文档 | 章节 |
|---|---|---|
| 带来源的外部观察：可追溯来源在明确时间给出的原始内容或保留原意的规范化表达 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [带来源的外部观察定义【DAT-OBS-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#带来源的外部观察定义dat-obs-001-def) |
| 可追溯派生结果：由明确输入计算、汇总或转换得到且保留输入与方法关系的内容 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [可追溯派生结果定义【DAT-DER-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#可追溯派生结果定义dat-der-001-def) |
| DAT：拥有信息身份、来源、时间、用途质量、未知、修正和重建语义的领域 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [DAT 责任定义【DAT-SCP-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#dat-责任定义dat-scp-001-def) |
| 交易记录环境身份：区分历史研究、历史行情回放、交易所模拟盘和真实资金交易记录的稳定标识 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [交易记录环境身份定义【DAT-ENV-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#交易记录环境身份定义dat-env-001-def) |
| 账户与资金事实：对用户允许 Halpha 使用的账户与交易资本在明确事实截止点形成的当前可用结论集合 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [账户与资金事实定义【DAT-TRU-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#21-账户与资金事实定义dat-tru-001-def) |
| 信息来源适用性判断：某来源在特定用途、时效和失败边界下是否足够可靠的判断 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [信息来源适用性判断定义【DAT-SRC-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#信息来源适用性判断定义dat-src-001-def) |
| 信息处理五类时间语义：来源事件、接收、处理、领域决定和事实或投影截止点 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [信息处理五类时间语义定义【DAT-TIM-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#信息处理五类时间语义定义dat-tim-001-def) |
| 事实截止点：一次判断所依赖观察与事实不晚于哪个时点的时间边界 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [信息处理五类时间语义定义【DAT-TIM-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#信息处理五类时间语义定义dat-tim-001-def) |
| 事实未知状态：所需事实当前不足以支持业务判断的显式状态 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [事实未知状态定义【DAT-UNK-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#事实未知状态定义dat-unk-001-def) |
| 可引用事实判断：Halpha 对明确对象、用途、时间和来源形成的可引用判断 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [可引用事实判断定义【DAT-FCT-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#可引用事实判断定义dat-fct-001-def) |
| 事实判断修正：保留原结论和来源、说明变化及影响范围的新可引用事实判断 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [事实判断修正定义【DAT-COR-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#事实判断修正定义dat-cor-001-def) |
| 来源追溯关系：从来源材料和观察到可追溯派生结果、可引用事实判断及修正的可恢复关系 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [来源追溯关系定义【DAT-LIN-001-DEF】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#来源追溯关系定义dat-lin-001-def) |

## 复盘、交互与信息呈现

| 概念 | 文档 | 章节 |
|---|---|---|
| OUT：把一条交易计划启用记录及其引用的计划版本、事前决定、当时事实、用户选择、资金与权限检查、实际动作、外部结果、成本、开放责任和后续修正连接为简短复盘，并把可行动问题交给正确语义所有者重新决定的领域 | [HALPHA-OUT-001](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md) | [0.1 OUT 责任定义【OUT-SCP-001-DEF】](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md#01-out-责任定义out-scp-001-def) |
| 复盘记录：对一条交易计划启用记录及其引用的计划版本、成交、非成交、结果未决或用户接管结局所形成的评价边界、来源事实、结论和开放责任的版本化记录 | [HALPHA-OUT-001](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md) | [1.1 复盘记录定义【OUT-REV-001-DEF】](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md#11-复盘记录定义out-rev-001-def) |
| 复盘改进事项：从复盘记录中形成、带证据与适用范围并提交给一个明确语义所有者决定是否接受的可行动问题 | [HALPHA-OUT-001](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md) | [6.1 复盘改进事项定义【OUT-FBK-001-DEF】](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md#61-复盘改进事项定义out-fbk-001-def) |
| UX：拥有用户所见内容、理解顺序、命令入口、结果回执和交互任务连续性语义的领域 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [UX 责任定义【UX-SCP-001-DEF】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#ux-责任定义ux-scp-001-def) |
| 用户交互任务：需要用户理解、决定或知悉的稳定任务身份 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [四类交互对象定义【UX-OBJ-001-DEF】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#四类交互对象定义ux-obj-001-def) |
| 用户操作指令：用户对明确任务和版本提交、尚不表示处理完成的指令 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [四类交互对象定义【UX-OBJ-001-DEF】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#四类交互对象定义ux-obj-001-def) |
| 用户操作处理回执：Halpha 对用户操作指令返回的接收、拒绝、处理中、过期、转交或处理状态无法确认的可追溯说明 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [四类交互对象定义【UX-OBJ-001-DEF】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#四类交互对象定义ux-obj-001-def) |
| 用户任务通知：只指向用户交互任务、不表示任务状态、用户决定或真实动作的最小载荷 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [四类交互对象定义【UX-OBJ-001-DEF】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#四类交互对象定义ux-obj-001-def) |
| 用户操作命令闭环：从用户交互任务读取当前状态、提交指令、校验并返回结果的共同路径 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [用户操作命令闭环定义【UX-CMD-001-DEF】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#用户操作命令闭环定义ux-cmd-001-def) |
| 用户待处理事项列表：不改变来源状态和优先级的跨领域用户交互任务只读视图 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [用户待处理事项列表定义【UX-ATT-001-DEF】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#用户待处理事项列表定义ux-att-001-def) |
| 任务信息四层结构：结论、决定、依据和诊断四个渐进呈现层次 | [HALPHA-UX-001](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md) | [任务信息四层结构定义【UX-INF-001-DEF】](L2/HALPHA-UX-001-owner-interaction-and-control-surfaces.zh-CN.md#任务信息四层结构定义ux-inf-001-def) |

## 系统架构、运行与工程

| 概念 | 文档 | 章节 |
|---|---|---|
| Halpha 总体逻辑形态：模块化单体、按交易记录环境划分的权威关系型数据库、必要外部适配器和单一且隔离的真实外部写入边界；模拟与真实资金环境的权威存储彼此分离 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [Halpha 总体逻辑形态定义【ARC-TOP-001-DEF】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#21-halpha-总体逻辑形态定义arc-top-001-def) |
| Halpha 运行实体：可独立启动、停止或失去执行权，且具有明确能力、秘密、资源、依赖和故障后果的 Halpha 运行单元 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [运行实体、启动停止与恢复前置边界【SYS-RUN-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#11-运行实体启动停止与恢复前置边界sys-run-001) |
| 业务模块：承载已有明确 L2 语义所有者的内聚业务语义、状态变化和公开能力的运行时构件 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [六类运行时构件定义【SYS-BND-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#12-六类运行时构件定义sys-bnd-001-def) |
| 应用入口：把用户或 Halpha 请求编排为命令或查询的运行时构件 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [六类运行时构件定义【SYS-BND-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#12-六类运行时构件定义sys-bnd-001-def) |
| 可重建只读视图：从权威状态和已记录事实生成、删除后能够重建的面向任务视图 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [可重建只读视图定义【SYS-PRJ-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#71-可重建只读视图定义sys-prj-001-def) |
| 后台任务：没有持续用户交互会话时执行有身份、有责任工作的运行时构件 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [后台任务及其业务后果分类定义【SYS-JOB-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#61-后台任务及其业务后果分类定义sys-job-001-def) |
| 外部适配器：隔离外部协议、身份、能力、格式、错误和限频语义的构件 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [外部适配器定义【SYS-ADP-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#外部适配器定义sys-adp-001-def) |
| 隔离外部写入边界：持有最小生产写入能力并处理待执行动作记录的构件 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [六类运行时构件定义【SYS-BND-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#12-六类运行时构件定义sys-bnd-001-def) |
| 模块所有权：可变业务状态、决定和不变量到唯一负责实现模块的映射，不是真人身份，也不替代 L2 语义所有权 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [模块所有权与模块依赖方向定义【SYS-DEP-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#21-模块所有权与模块依赖方向定义sys-dep-001-def) |
| 模块依赖方向：入口经应用边界进入拥有模块、再由基础设施实现端口的单向关系 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [模块所有权与模块依赖方向定义【SYS-DEP-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#21-模块所有权与模块依赖方向定义sys-dep-001-def) |
| 应用交互类型：命令、查询、已提交事件和瞬时信号 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [四类应用交互定义【SYS-INT-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#四类应用交互定义sys-int-001-def) |
| 应用命令提交责任：一个改变状态的应用命令对应的唯一逻辑提交责任 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [应用命令提交责任与业务状态冲突处理责任定义【SYS-TXN-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#41-应用命令提交责任与业务状态冲突处理责任定义sys-txn-001-def) |
| 业务状态冲突处理责任：同一业务身份、版本或写入范围的冲突检测和唯一判定责任 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [应用命令提交责任与业务状态冲突处理责任定义【SYS-TXN-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#41-应用命令提交责任与业务状态冲突处理责任定义sys-txn-001-def) |
| 模块间交接方式：同步接口、同事务记录、持久异步、提交后事件和瞬时信号 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [五种模块间交接方式定义【SYS-HOF-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#五种模块间交接方式定义sys-hof-001-def) |
| 后台任务业务后果分类：真实动作保护与核对任务、业务连续任务和可重建任务 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [后台任务及其业务后果分类定义【SYS-JOB-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#61-后台任务及其业务后果分类定义sys-job-001-def) |
| 系统配置责任分工：业务配置由相应业务领域拥有；模块、适配、交接、运行实体、宿主、进程、资源、运行时配置与秘密注入边界由 SYS 拥有；当前工具、参数与秘密值由 L4 或外部工具记录 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [系统配置责任分工定义【SYS-CFG-001-DEF】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#系统配置责任分工定义sys-cfg-001-def) |
| 工程影响级别：核心影响、一般影响和轻量影响 | [HALPHA-ENG-001](L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md) | [工程影响级别定义【ENG-IMP-001-DEF】](L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md#21-工程影响级别定义eng-imp-001-def) |

## 维护规则

- 新概念只有在多个章节或消费者需要同一稳定特殊含义时才定义并进入本索引。
- 常见词语若没有特殊含义，直接按普通中文使用；不得通过索引把它升级为项目概念。
- 每个概念只在最高适当层级定义一次；下位文档引用、细化或规定使用要求，不重新定义。
- 新概念必须说明真实消费者；无消费者或价值不足以覆盖理解、实现与维护成本时，应删除概念并改用直接表述。
- 章节标题或锚点变化时同步修正链接；索引摘要不得创造正文没有的新含义。
