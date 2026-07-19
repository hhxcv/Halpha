# Halpha 要求与限制索引

**索引性质：** 非规范性导航文档  
**索引基准：** 2026-07-19
**覆盖范围：** 当前最新中文 L0–L4 文档  

本索引只收录能够直接判断符合或偏离的规范内容：必须、不得、默认要求、允许边界，以及会改变范围、责任、顺序、失败行为、记录义务或验收结果的约束。定量值、适用条件、例外和完整语义始终以所指正文为准。

最小归类单元是“文档 + 语义锚点”。混合章节中的要求使用 `-REQ` 子锚点；原章节锚点只作结构和既有引用入口。定义对象本身进入[概念定义索引](concept-definition-index.zh-CN.md)；解释问题、前提和取舍的内容进入[决策与依据索引](decision-rationale-index.zh-CN.md)。决策名称可以在要求中出现，但“为什么选择”不在本索引重复记录。

本索引直接导航当前目标路径中的要求。历史要求由 Git commit 保存，不重复记录旧版本、状态、替代关系或历史副本。L3 收录长期功能、失败、交接、组件使用和验收要求；L4 只把既有长期设计转为当前建设选择、事实和直接验收，不为没有实际消费者的流程或证据增加状态。L4 使用 YAML，不具备 Markdown 章节锚点，因此以稳定键路径作为归类单元，并链接到计划文件而不绑定易漂移的行号。

## 规范、责任与文档治理

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 规范权威、下位登记与证据（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [权威使用要求【CON-GOV-001-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#权威使用要求con-gov-001-req) |
| 规范性用语及偏离必须按统一规则处理 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [偏离处理要求【CON-GOV-003-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#偏离处理要求con-gov-003-req) |
| 最高冲突顺序（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [1.5【CON-PRI-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#15-最高冲突顺序con-pri-001) |
| 共同规范语言文本与语言冲突（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [对齐与冲突处理要求【CON-GOV-006-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#对齐与冲突处理要求con-gov-006-req) |
| 复核、修订与问题处理（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [9.1【CON-GOV-004】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#91-复核修订与问题处理con-gov-004) |
| 当前宪法与真实资金使用（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [9.2【CON-GOV-005】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#92-当前宪法与真实资金使用con-gov-005) |
| L0–L4 设计文档总体结构 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [层级使用要求【DOC-STR-001-REQ】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#层级使用要求doc-str-001-req) |
| 四篇 L1 文档的依赖顺序 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [1.3【DOC-L1-001】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#13-l1-的依赖顺序doc-l1-001) |
| L2–L4 只写真实消费者需要的内容，并按责任与当前支持范围控制复杂度 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [L2–L4 使用要求【DOC-L24-001-REQ】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#l2l4-使用要求doc-l24-001-req) |
| 文档文件命名与中文术语规则 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [2.1【DOC-NAM-001】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#21-命名doc-nam-001) |
| 具有特殊含义的概念须先在最高适当层级定义，再供其他章节引用 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [概念、行为主体与记录要求【DOC-SEM-001-REQ】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#概念行为主体与记录要求doc-sem-001-req) |
| 常见词语不得被赋予隐藏的项目含义；一次性说明不得升级为概念 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [概念、行为主体与记录要求【DOC-SEM-001-REQ】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#概念行为主体与记录要求doc-sem-001-req) |
| 概念名脱离原章节后仍须明确业务对象和作用，跨文档使用同一完整名称 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [概念、行为主体与记录要求【DOC-SEM-001-REQ】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#概念行为主体与记录要求doc-sem-001-req) |
| 领域编号只表示语义责任，运行行为须由具体主体承担 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [概念、行为主体与记录要求【DOC-SEM-001-REQ】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#概念行为主体与记录要求doc-sem-001-req) |
| 新概念、对象、记录行为及其数据须有真实消费者，价值须覆盖完整成本 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [概念、行为主体与记录要求【DOC-SEM-001-REQ】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#概念行为主体与记录要求doc-sem-001-req) |
| L2 只固定会改变决定、责任或失败处理的记录语义，具体字段进入 L3，当前事实进入 L4 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [概念、行为主体与记录要求【DOC-SEM-001-REQ】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#概念行为主体与记录要求doc-sem-001-req) |
| 规范文档须声明最小元数据、语言对应和适用时间字段 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [2.2【DOC-MET-001】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#22-最小元数据doc-met-001) |
| 设计文档目录与存放位置 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [2.3【DOC-LOC-001】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#23-文件位置doc-loc-001) |
| AI 的设计文档最小读取规则 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [3【DOC-AIR-001】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#3-ai-最小读取规则doc-air-001) |
| 设计文档创建、拆分与复核条件 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [6【DOC-SPL-001】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#6-创建拆分与复核doc-spl-001) |
| 设计语义变更的分层更新位置 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [5【DOC-UPD-001】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#5-更新位置doc-upd-001) |
| 正式实现的文档前置条件 | [HALPHA-DOC-001](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md) | [4【DOC-IMP-001】](L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md#4-进入实现doc-imp-001) |

## 产品定位、价值与演进

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 项目使命（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [项目使命与价值要求【CON-MIS-001-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#项目使命与价值要求con-mis-001-req) |
| 人的决策主权与认知安全（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [2.3【CON-HUM-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#23-人的决策主权与认知安全con-hum-001) |
| 长期范围与非目标（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [2.4【CON-NGL-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#24-长期范围与非目标con-ngl-001) |
| 结果优先级（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [3.1【CON-ECO-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#31-结果优先级con-eco-001) |
| 账户净结果、投资 Alpha 与产品增量价值须分别评价；优势的发现、证伪、淘汰和替换按产品能力评价 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [分离评价要求【CON-ECO-002-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#分离评价要求con-eco-002-req) |
| 事前评价与反事实完整性（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [3.3【CON-ECO-003】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#33-事前评价与反事实完整性con-eco-003) |
| 现金与不交易不得视为产品失败，产品成功须按增量价值判定 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [产品成功与失败判定要求【CON-ECO-004-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#产品成功与失败判定要求con-eco-004-req) |
| 产品设计须服务单一用户投入的交易资本，并受项目所有者可承担的建设与维护成本约束 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [1.3 产品身份保持要求【VIS-IDN-001-REQ】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#13-产品身份保持要求vis-idn-001-req) |
| 要解决的真实问题（产品目标与愿景） | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [2.2 由问题产生的产品要求【VIS-PRB-001-REQ】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#22-由问题产生的产品要求vis-prb-001-req) |
| 八类产品价值须分别形成并以长期净资本价值为最终目标 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [3.2 产品价值要求【VIS-VAL-001-REQ】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#32-产品价值要求vis-val-001-req) |
| 用户、项目所有者、Halpha 与外部系统或工具须保持产品责任边界；运行实体、进程和模块边界由 ARC、SYS 与下位设计拥有 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [参与者要求【VIS-OPS-001-REQ】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#参与者要求vis-ops-001-req) |
| 候选优势不得被当作永久属性；回测、单次盈利或叙事不得自行提高经济证据结论 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [派生术语使用要求【VIS-ADV-001-REQ】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#派生术语使用要求vis-adv-001-req) |
| 竞争方向须服从个人资本、数据、接入、维护和证据边界 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [5.3 竞争范围要求【VIS-ADV-001-REQ-002】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#53-竞争范围要求vis-adv-001-req-002) |
| 产品能力只按当前消费者扩展，并共同遵守简单、可验证的稳定性约束 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [6.2 能力实现要求【VIS-CAP-001-REQ】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#62-能力实现要求vis-cap-001-req) |
| 核心交易与 UX 闭环可同 Alpha 研究并行，但都须服从价值依赖和真实场景验证 | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [9.1 能力协同要求【VIS-DEP-001-REQ】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#91-能力协同要求vis-dep-001-req) |
| 必须连接的产品价值依赖（产品目标与愿景） | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [7【VIS-LOOP-001】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#7-必须连接的产品价值依赖vis-loop-001) |
| 方向失败信号（产品目标与愿景） | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [11【VIS-FAL-001】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#11-方向失败信号vis-fal-001) |
| 用户应获得的结果（产品目标与愿景） | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [8【VIS-OUT-001】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#8-用户应获得的结果vis-out-001) |
| 下位设计交接（产品目标与愿景） | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [12【VIS-HOF-001】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#12-下位设计交接vis-hof-001) |
| 长期非目标与复杂度约束（产品目标与愿景） | [HALPHA-VIS-001](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md) | [10【VIS-NGL-001】](L1/HALPHA-VIS-001-goals-and-vision.zh-CN.md#10-长期非目标与复杂度约束vis-ngl-001) |

## 用户、资金使用限制与风险控制

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 用户拥有产品使用与资本控制的最终决定权；Halpha 必须接受并执行用户明确配置的账户、资金使用上限与范围、真实资金操作权限以及停止、缩小和恢复决定，不得自行扩权或扩大范围 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [项目所有者责任与系统边界要求【CON-USR-001-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#项目所有者责任与系统边界要求con-usr-001-req) |
| 当前项目只有一位真人用户；项目所有者可以兼任用户和开发者，AI 工具也可以作为开发者，但开发者不属于用户角色，不新增管理员、审批人和值守人身份 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [真人身份使用要求【CON-USR-002-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#真人身份使用要求con-usr-002-req) |
| Halpha 只能记录并执行用户已配置的资金使用上限与范围 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [资金使用上限与范围要求【CON-CAP-001-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#资金使用上限与范围要求con-cap-001-req) |
| 新增真实风险只经用户明确激活的完整计划；针对已有责任的停止、撤单、保护、减仓或退出只有在可证明不增险时执行，且不能恢复旧激活或扩大范围 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [4.3【CON-CAP-003】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#43-halpha-真实资金操作权限的宪法边界con-cap-003) |
| 关键事实不能确认时必须明确保留“事实未知”，不得用推断、旧值、默认值或用户确认伪造确定性 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [4.4【CON-CAP-004】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#44-关键事实无法确认时的上位边界con-cap-004) |
| Halpha 真实资金操作权限与资金使用上限、范围变更 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [4.5【CON-CAP-005】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#45-halpha-真实资金操作权限与资金使用上限范围变更con-cap-005) |
| 收缩与重启连续性 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [4.6【CON-CAP-006】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#46-收缩与重启连续性con-cap-006) |

## 研究或交易计划候选、研究、证据与策略

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 正式经济研究入口必须明确经济机制、被评价对象、决策用途与可证伪问题 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [1.1 进入要求【ALP-OBJ-001-REQ】](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#11-进入要求alp-obj-001-req) |
| 候选优势进入正式研究前须具备经济机制、适用边界、成本假设与证伪条件 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [2.1 候选优势进入研究要求【ALP-ADV-001-REQ】](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#21-候选优势进入研究要求alp-adv-001-req) |
| 研究材料不得直接充当经济证据判断，关键主张须独立确认 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [2.2 研究材料与经济证据判断分离【ALP-EVD-001-REQ】](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#22-研究材料与经济证据判断分离alp-evd-001-req) |
| 正式策略须绑定固定定义、经济证据判断和适用范围，并说明如何形成计划输入 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [3.1 正式策略边界【ALP-STR-001-REQ】](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#31-正式策略边界alp-str-001-req) |
| 失败与失效结论须保留适用边界，并在无新增信息时阻止重复研究 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [4.1 保留和复用要求【ALP-NEG-001-REQ】](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#41-保留和复用要求alp-neg-001-req) |
| 功能与实现验证和经济证据须回答不同问题，并按后果提高验证强度 | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [两类问题的边界【CON-EVD-001-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#两类问题的边界con-evd-001-req) |
| 证据适用范围、晋级与衰减（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [5.3【CON-EVD-002】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#53-证据适用范围晋级与衰减con-evd-002) |
| 事前记录与失败、失效结论（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [5.4【CON-LRN-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#54-事前记录与失败失效结论con-lrn-001) |
| 自适应不得自行提高资金使用上限或扩大范围（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [5.5【CON-ADP-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#55-自适应不得自行提高资金使用上限或扩大范围con-adp-001) |
| Alpha 研究与策略必须明确输入与输出，不得形成交易计划、资金决定或真实动作 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [5. 明确输入与输出【ALP-IO-001】](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#5-明确输入与输出alp-io-001) |
| Alpha 研究与策略的唯一职责 | [HALPHA-ALP-001](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md) | [0【ALP-SCP-001】](L2/HALPHA-ALP-001-alpha-research-evidence-and-strategy.zh-CN.md#0-唯一职责alp-scp-001) |

## 交易计划与运行条件

| 要求或限制 | 文档 | 章节 |
|---|---|---|

## 执行、外部动作、保护与核对

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 一个 ProposedAction 最多建立一个有效 ExecutionAction，且只有 EXE 可以推进它 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [`ExecutionAction`【EXE-ACT-001】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#1-executionactionexe-act-001) |
| 场所写入前必须持久化唯一 ExecutionAction，并在提交前重读事实和复核同一 CAP 规则 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [建立与提交【EXE-INT-001】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#2-建立与提交exe-int-001) |
| 同一实际写入传播范围只能有一个 Halpha 写者，且只有它可以取得真实写凭据 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [单一写者与场所身份【EXE-WRT-001】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#3-单一写者与场所身份exe-wrt-001) |
| 可能已经提交但结果未知时，必须按原身份先查询和核对，不盲重试、不创建第二动作 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [结果、重复与未知【EXE-OUT-001】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#4-结果重复与未知exe-out-001) |
| 风险出现后必须持续核对保护；保护缺失、冲突或未知时停止新增风险并保留退出和接管 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [保护、核对与用户接管【EXE-PRT-001】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#5-保护核对与用户接管exe-prt-001) |
| 重启恢复动作责任而不重放命令；连续性无法完整证明时旧激活永久停止新增风险 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [重启与责任闭合【EXE-RCV-001】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#6-重启与责任闭合exe-rcv-001) |
| Demo 与 Live 复用执行实现但隔离环境、账户、凭据、存储、激活、动作和端点 | [HALPHA-EXE-001](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md) | [环境隔离与下位边界【EXE-ENV-001】](L2/HALPHA-EXE-001-execution-protection-reconciliation-and-recovery.zh-CN.md#7-环境隔离与下位边界exe-env-001) |
| 计划激活与执行动作（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [5【ARC-ACT-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#5-计划激活与执行动作arc-act-001) |

## 事实、数据、时间与状态

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 事实完整性（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [5.1【CON-TRU-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#51-事实完整性con-tru-001) |
| DAT 只拥有事实及其可用性，不得重写领域决定，也不得为来源、质量、追溯或修正再建立第二套事实系统 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [唯一职责与复杂度上限【DAT-SCP-001】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#0-唯一职责与复杂度上限dat-scp-001) |
| 产品事实须按当前用途携带必要的环境、对象、来源、身份、值、单位、时间、截止点及派生输入和方法 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [带来源事实【DAT-FCT-001】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#1-带来源事实dat-fct-001) |
| 历史研究、历史回放、Demo 与 Live 必须隔离，模拟事实不得复制、改名或提升为真实事实 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [环境与身份隔离【DAT-ENV-001】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#2-环境与身份隔离dat-env-001) |
| 来源与时间能否使用由当前消费者决定；只保存当前用途需要的时间，来源切换不得未经等价验证而静默发生 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [来源、时间与当前可用性【DAT-SRC-001】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#3-来源时间与当前可用性dat-src-001) |
| 未知不得解释为零、否或安全；依赖未知事实的新增风险动作停止，只读核对、既有保护、退出和用户接管保持可用 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [未知与消费者行为【DAT-UNK-001】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#4-未知与消费者行为dat-unk-001) |
| 事实修正必须追加而非覆盖，并保留到依赖它的交易责任闭合；不可重建且仍承担责任的事实须可导出 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [修正、保留与重建【DAT-COR-001】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#5-修正保留与重建dat-cor-001) |
| L3 只定义当前消费者所需的事实契约，L4 只记录当前来源、阈值、版本与直接验证结果 | [HALPHA-DAT-001](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md) | [下位设计与当前记录【DAT-L3-001】](L2/HALPHA-DAT-001-authoritative-facts-market-data-and-time.zh-CN.md#6-下位设计与当前记录dat-l3-001) |
| 权威状态必须落入关系型数据库，并保留来源、形成方式、证明力与所有权差异 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [4【ARC-DAT-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#4-权威状态与数据arc-dat-001) |

## 结果、归因、反馈与学习

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| OUT 只拥有一条 Review 版本链；后续问题只是 Review 内普通文本，不建立任务或改进交接对象 | [HALPHA-OUT-001](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md) | [唯一职责与复杂度上限【OUT-SCP-001】](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md#0-唯一职责与复杂度上限out-scp-001) |
| 成交、非成交、未知和用户接管都可复盘；未知不得填零或补造成交、费用与盈亏 | [HALPHA-OUT-001](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md) | [哪些结果可以复盘【OUT-CAS-001】](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md#2-哪些结果可以复盘out-cas-001) |
| 复盘引用来源并受事实截止点限制；后来修正改变评价时追加 Review 版本，不改写源事实 | [HALPHA-OUT-001](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md) | [来源、时间与修正【OUT-EVD-001】](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md#3-来源时间与修正out-evd-001) |
| 盈利不能掩盖动作、保护、核对或用户控制失败；归因只写证据支持的主要贡献，不估算伪精确比例 | [HALPHA-OUT-001](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md) | [简短评价与归因【OUT-EVL-001】](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md#4-简短评价与归因out-evl-001) |
| 复盘中的后续问题不自动创建任务、修改其他领域或扩大资金与机器执行范围 | [HALPHA-OUT-001](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md) | [后续问题【OUT-FBK-001】](L2/HALPHA-OUT-001-outcomes-attribution-and-learning.zh-CN.md#5-后续问题out-fbk-001) |
| 每个 PlanActivation 只有一个稳定 Review 身份；重复写入幂等，修正形成不可变新版本 | [HALPHA-OUT-002](L3/HALPHA-OUT-002-one-shot-activation-review.zh-CN.md) | [身份与版本【OUT-RT-SCP-001】](L3/HALPHA-OUT-002-one-shot-activation-review.zh-CN.md#1-身份与版本out-rt-scp-001) |
| Review 写入失败不改变交易责任；OUT 只保留一个记录族且不建立 worker、队列、游标或分析存储 | [HALPHA-OUT-002](L3/HALPHA-OUT-002-one-shot-activation-review.zh-CN.md) | [验证与复杂度【OUT-RT-CHK-001】](L3/HALPHA-OUT-002-one-shot-activation-review.zh-CN.md#5-验证与复杂度out-rt-chk-001) |

## 用户交互任务、交互与操作控制

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| UX 技术边界（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [7【ARC-UX-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#7-ux-技术边界arc-ux-001) |
| 任何受支持交互形态只作为共同应用命令与查询的入口适配器，不得建立平行业务流、写链、授权或权威状态；没有明确建设范围和真实消费者时不得预建认证、网络、通知、离线、同步、部署平台或客户端框架 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [平台无关流程与入口适配要求【ARC-TOP-002-REQ】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#平台无关流程与入口适配要求arc-top-002-req) |

## 系统架构、集成与技术边界

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 工程目标与取舍（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [1.2 质量优先级要求【ARC-QLT-001-REQ】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#12-质量优先级要求arc-qlt-001-req) |
| 总体架构须保持模块化单体、关系型权威状态与隔离的外部适配 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [2.2 总体形态约束【ARC-TOP-001-REQ】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#22-总体形态约束arc-top-001-req) |
| 稳定性技术选择与最小恢复（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [8.2 稳定性与恢复要求【ARC-OPS-001-REQ】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#82-稳定性与恢复要求arc-ops-001-req) |
| AI 信任边界（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [6.1【CON-AI-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#61-ai-信任边界con-ai-001) |
| 技术与数据主权（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [6.2【CON-SOV-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#62-技术与数据主权con-sov-001) |
| 自动化非交易成本边界（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [6.3【CON-CST-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#63-自动化非交易成本边界con-cst-001) |
| 身份、凭据与最小权限（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [6.4【CON-SEC-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#64-身份凭据与最小权限con-sec-001) |
| 实际影响范围与简单隔离（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [6.5【CON-SEC-002】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#65-实际影响范围与简单隔离con-sec-002) |
| SYS 只拥有系统组成与集成，不得重写业务领域含义 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [SYS 责任【SYS-BND-001-REQ】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#11-sys-责任sys-bnd-001-req) |
| 新模块、进程、存储或持久工作只在现有边界已经影响当前消费者时建立 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [建立新边界的条件【SYS-BND-001-REQ-002】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#13-建立新边界的条件sys-bnd-001-req-002) |
| 每项可变业务状态、决定和不变量只有一个拥有模块，依赖保持单向 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [单一所有权【SYS-DEP-001-REQ】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#21-单一所有权sys-dep-001-req) |
| 同进程直接调用优先；本地状态全部提交或全部不成立，外部动作先持久再由唯一写者处理 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [本地事务【SYS-TXN-001-REQ】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#32-本地事务sys-txn-001-req) |
| 后台工作只在责任必须离开当前请求继续时存在；只读视图和适配器不得取得业务决定或写入权 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [后台工作、只读视图与外部适配【SYS-JOB-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#4-后台工作只读视图与外部适配sys-job-001) |
| 配置不能创造业务权限、恢复被停止的激活、跳过检查或提供危险默认值 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [配置与运行【SYS-CFG-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#5-配置与运行sys-cfg-001) |
| AI 开发与技术策略（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [10【ARC-TEC-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#10-ai-开发与技术策略arc-tec-001) |
| SYS 六项最小不变量（系统组成与集成） | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [SYS 不变量【SYS-INV-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#8-sys-不变量sys-inv-001) |
| 只有实际规模、故障隔离、并发或独立启停需要证明收益大于个人维护成本时才拆分基础设施 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [演进与验证【SYS-CHK-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#6-演进与验证sys-chk-001) |
| 复杂度预算与演进（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [11【ARC-CMP-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#11-复杂度预算与演进arc-cmp-001) |
| SYS 只提供直接架构不变量，验证和发布方法由 ENG 负责 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [演进与验证【SYS-CHK-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#6-演进与验证sys-chk-001) |
| 架构结论（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [0【ARC-SUM-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#0-架构结论arc-sum-001) |
| 身份与基本安全（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [9【ARC-SEC-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#9-身份与基本安全arc-sec-001) |
| 外部适配与工具边界（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [6【ARC-ADP-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#6-外部适配与工具边界arc-adp-001) |
| 系统组成结论（系统组成与集成） | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [0【SYS-SUM-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#0-系统组成结论sys-sum-001) |
| 系统组成与集成的当前事实 L4 记录范围 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [L4 当前事实【SYS-L4-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#9-l4-当前事实sys-l4-001) |
| 业务模块与依赖（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [3【ARC-BND-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#3-业务模块与依赖arc-bnd-001) |
| 与相邻领域的固定边界（系统组成与集成） | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [相邻领域边界【SYS-HND-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#7-相邻领域边界sys-hnd-001) |

## 工程开发、稳定运行与恢复

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 稳定性优先来自简单选择，动作正确性由核心领域保证（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [稳定运行的实现要求【CON-OPS-001-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#稳定运行的实现要求con-ops-001-req) |
| 简单停止与可见降级（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [7.2【CON-OPS-002】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#72-简单停止与可见降级con-ops-002) |
| 恢复与独立最终控制（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [7.3【CON-OPS-003】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#73-恢复与独立最终控制con-ops-003) |
| 停用、退出与资料保留（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [7.4【CON-LIF-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#74-停用退出与资料保留con-lif-001) |
| 项目所有者可验证复杂度（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [8.1【CON-CMP-001】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#81-项目所有者可验证复杂度con-cmp-001) |
| 真实消费者与纵向闭环（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [8.2【CON-CMP-002】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#82-真实消费者与纵向闭环con-cmp-002) |
| 真实动作的最低正确性与控制要求（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [真实动作最低要求【CON-CMP-003-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#真实动作最低要求con-cmp-003-req) |
| 技术引入门槛（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [8.4【CON-CMP-004】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#84-成熟能力优先与技术引入门槛con-cmp-004) |
| AI 驱动开发边界（项目宪法） | [HALPHA-CON-001](L0/HALPHA-CON-001-project-constitution.zh-CN.md) | [AI 驱动开发要求【CON-DEV-001-REQ】](L0/HALPHA-CON-001-project-constitution.zh-CN.md#ai-驱动开发要求con-dev-001-req) |
| 运行实体、资源、运行时配置、秘密注入、启动停止、备份范围和恢复前置边界由 SYS 统一规定 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [启动、停止与重启【SYS-RUN-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#51-启动停止与重启sys-run-001) |
| 启停、重启和还原不得扩大权限或复活被停止的激活；原激活只有在范围、事实、唯一写者、连续性、身份和未决责任均重新核对且不补发动作时才可继续 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [启动、停止与重启【SYS-RUN-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#51-启动停止与重启sys-run-001) |
| 稳定性优先来自成熟技术、简单结构和业务正确性，不默认建设专门稳定性平台 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [8.2 稳定性与恢复要求【ARC-OPS-001-REQ】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#82-稳定性与恢复要求arc-ops-001-req) |
| 只有重复实际故障且简化结构、更换组件、修正配置和现成工具都不足时，才增加具有当前消费者的最小运行能力切片 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [8.2 稳定性与恢复要求【ARC-OPS-001-REQ】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#82-稳定性与恢复要求arc-ops-001-req) |

## 当前建设计划与下位交接

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 责任地图只保留长期架构关注点，当前支持范围和实际投入只由 L4 记录 | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [12【ARC-L2D-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#12-责任的长期架构关注点arc-l2d-001) |
| 下位设计清单（总体技术架构） | [HALPHA-ARC-001](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md) | [13【ARC-HOF-001】](L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md#13-下位设计清单arc-hof-001) |

## 当前产品最小闭环要求

| 要求或限制 | 文档 | 章节 |
|---|---|---|
| 策略研究可在独立工作区直接开始；不因产品建设、模拟运行或长期观察而等待，也不得接触产品数据库、秘密和场所写 | [HALPHA-FLOW-001](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md) | [AI 主导研究与最终人工选择【FLOW-AIR-001-REQ】](L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md#51-ai-主导研究与最终人工选择flow-air-001-req) |
| 用户一次明确激活完整计划即可授予只属于该激活的有界机器执行范围；不得再要求第二资金授权、外置 gate 或逐动作确认 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [权限进入与转换要求【CAP-MOD-001-REQ】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#22-权限进入与转换要求cap-mod-001-req) |
| PlanActivation 直接固定计划、环境、账户、工具、资金限制、动作范围和期限；范围变化或用户停止后要继续交易必须新建激活 | [HALPHA-TRADEPLAN-002](L3/HALPHA-TRADEPLAN-002-machine-authorized-one-shot-trade-plan.zh-CN.md) | [`PlanActivation`](L3/HALPHA-TRADEPLAN-002-machine-authorized-one-shot-trade-plan.zh-CN.md#12-planactivation) |
| 同一真实账户一次只允许一个未闭合激活；并发资金比较只有在真实竞争反复发生且人工计划成为瓶颈后才另行设计 | [HALPHA-CAP-001](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md) | [激活资金边界【CAP-ENV-001】](L2/HALPHA-CAP-001-capital-risk-and-authority.zh-CN.md#1-激活资金边界cap-env-001) |
| 每个增险动作在提议时和场所调用前使用同一 CAP 检查；输入缺失、冲突或过期时拒绝新增风险，保护、撤单、减仓和退出不得被误阻 | [HALPHA-CAP-002](L3/HALPHA-CAP-002-activation-capital-and-action-checks.zh-CN.md) | [同一轻量检查【CAP-AUTO-CHK-001】](L3/HALPHA-CAP-002-activation-capital-and-action-checks.zh-CN.md#4-同一轻量检查cap-auto-chk-001) |
| 所有场所写必须先持久化唯一 ExecutionAction；提交结果未知时查询原身份，不能盲重试、改换订单或建立第二动作 | [HALPHA-EXE-002](L3/HALPHA-EXE-002-single-venue-real-action-execution.zh-CN.md) | [建立与提交【EXE-AUTO-SUB-001】](L3/HALPHA-EXE-002-single-venue-real-action-execution.zh-CN.md#2-建立与提交exe-auto-sub-001) |
| Demo 与 Live 共用产品代码但隔离环境、账户、凭据、激活、动作和事实；真实秘密只在构建、数据库、唯一写者、激活和当前事实检查完成后读取 | [HALPHA-ENG-002](L3/HALPHA-ENG-002-real-trade-core-technology-stack-and-build-boundaries.zh-CN.md) | [秘密与真实写前置检查【ENG-AUTO-SEC-001】](L3/HALPHA-ENG-002-real-trade-core-technology-stack-and-build-boundaries.zh-CN.md#6-秘密与真实写前置检查eng-auto-sec-001) |
| 工作台只保留计划、激活运行和账户设置三个主要入口；清楚呈现环境、过期、未知、动作、场所事实和责任闭合，不建立通用任务、回执、通知或恢复平台 | [HALPHA-UX-002](L3/HALPHA-UX-002-owner-trading-workbench-interaction-and-visual-standard.zh-CN.md) | [三个主要入口【UX-AUTO-IA-001】](L3/HALPHA-UX-002-owner-trading-workbench-interaction-and-visual-standard.zh-CN.md#3-三个主要入口ux-auto-ia-001) |
| 用户必须能停止新增风险、退出策略和通过官方场所接管；用户停止或接管后的旧激活永不恢复机器新增风险 | [HALPHA-TRADEPLAN-002](L3/HALPHA-TRADEPLAN-002-machine-authorized-one-shot-trade-plan.zh-CN.md) | [三类用户控制【TRADEPLAN-AUTO-CTL-001】](L3/HALPHA-TRADEPLAN-002-machine-authorized-one-shot-trade-plan.zh-CN.md#4-三类用户控制tradeplan-auto-ctl-001) |
| 纯系统重启只有在用户未停止、原激活有效、唯一写者和持久连续性成立、身份未变、外部事实已核对且不会补发动作时才可继续；否则停止新增风险 | [HALPHA-SYS-001](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md) | [启动、停止与重启【SYS-RUN-001】](L2/HALPHA-SYS-001-system-composition-and-integration.zh-CN.md#51-启动停止与重启sys-run-001) |
| 早期个人项目默认使用直接测试、普通 Git、短说明和人工决定；功能正确性不降低，流程和治理只随真实影响、实际并发和重复故障增强 | [HALPHA-ENG-001](L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md) | [最小开发闭环【ENG-LCY-001】](L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md#3-最小开发闭环eng-lcy-001) |
| 一个 product_build_id 识别实际产品输入；独立研究和普通文档不改变它，不建立第二摘要或资格身份 | [HALPHA-ENG-002](L3/HALPHA-ENG-002-real-trade-core-technology-stack-and-build-boundaries.zh-CN.md) | [Windows、构建、迁移与备份【ENG-AUTO-BLD-001】](L3/HALPHA-ENG-002-real-trade-core-technology-stack-and-build-boundaries.zh-CN.md#5-windows构建迁移与备份eng-auto-bld-001) |
| 研究最小记录只需问题、来源与 cutoff、代码或命令、假设、结果、失败和限制；只有所有者选中结果后才按普通产品变更进入正式策略 | [HALPHA-ALP-003](L3/HALPHA-ALP-003-research-workspace-and-evidence-handoff.zh-CN.md) | [进入产品【ALP-RSCH-INT-001】](L3/HALPHA-ALP-003-research-workspace-and-evidence-handoff.zh-CN.md#5-进入产品alp-rsch-int-001) |
| 当前完整产品范围和 Windows 10 主机保持不变；一个已授权产品结果内按直接依赖连续实现，不设置按小时建设许可或强制自然日观察 | [HALPHA-PLAN-001](L4/HALPHA-PLAN-001-current-construction-plan.yaml) | [当前计划](L4/HALPHA-PLAN-001-current-construction-plan.yaml) |
| required 浏览器测试不得以 skip 冒充通过；变更只重跑实际受影响检查，观察只有当前决定提出直接问题时才增加 | [HALPHA-PLAN-001](L4/HALPHA-PLAN-001-current-construction-plan.yaml) | [当前计划](L4/HALPHA-PLAN-001-current-construction-plan.yaml) |

## 维护规则

- 新增或修改会改变项目行为、责任、边界、失败处理或验收的规范时，更新正文与本索引。
- 要求段只写规范结论及其适用条件；稳定对象含义移入 `-DEF`，问题背景和取舍理由移入 `-RAT`。
- 新增记录或生成数据的要求必须指出实际消费者以及它会改变的决定、责任或失败处理；没有消费者的字段和记录行为从 L2 删除。
- 同一语义锚点或 L4 键路径不得同时出现在概念、要求、决策与依据索引；直接引用同一上位要求不新增重复条目。
- 章节标题、编号或锚点变化时同步修正链接；索引摘要不缩小、扩大或替代正文要求。
