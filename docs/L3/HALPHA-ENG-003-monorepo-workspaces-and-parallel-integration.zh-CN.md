# Halpha Monorepo 工作区与并行集成契约

**文档编号：** HALPHA-ENG-003  
**版本：** v0.4.0  
**文档状态：** ACCEPTED  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** ENG  
**所属实现模块：** 仓库工作区、构建输入图、验证与集成边界；不形成交易产品业务模块  
**语言版本：** zh-CN  
**批准人：** Halpha 项目所有者  
**接受时间：** 2026-07-18T23:18:42+08:00  
**替代版本：** HALPHA-ENG-003@v0.3.0  
**上位文档或条款：** HALPHA-FLOW-001 v1.9.0；HALPHA-ARC-001 v1.9.0；HALPHA-ENG-001 v1.7.0  
**直接依赖：** HALPHA-ENG-002 v0.8.0；BuildManifest 的证据摘要与 eligibility 语义受 HALPHA-ALP-002 v0.5.0 约束；HALPHA-ALP-003 v0.4.0 提供 AI 研究任务、运行请求/回执、研究运行清单与研究证据包语义；运行实体、模块、进程、配置和恢复边界服从 HALPHA-SYS-001 v1.6.0 与 HALPHA-SYS-002 v0.9.0  
**直接消费者：** HALPHA-ALP-003 v0.4.0；由 `HALPHA-PLAN-001` 授权的独立源码工作包及其集成门  
**适用纵向约束：** HALPHA-SYS-001 v1.6.0  
**本文档负责：** monorepo 内交易产品、前端、研究和按需工具的工作区边界；可信外部 AI 通过同一研究 CLI/文件协议工作的授权、路径、预算、可重演与失败清理边界；Git 原生并行与唯一集成方式；依赖定义、允许依赖方向、路径所有权、最小工作包、共享路径串行集成、选择性开发反馈和复杂度退出条件  
**本文档不负责：** 重定义研究判据或领域业务语义、模块或运行实体；规定 L4 建设授权、工作包授权、AI 客户端/模型/提示词、精确依赖版本、锁摘要、目录状态或资格证据；改变 HALPHA-ENG-002 的交易产品构建、DEMO/LIVE 等价和发布要求；新增 Halpha 自研或第三方研究 sandbox、父进程/worker 隔离协议、模型 SDK/agent framework、产品进程、数据库产品、持久工作器、真实写链、消息总线、独立产品发布组、私有包仓库或通用开发平台  

---

# 0. 设计结论【ENG-MONO-SUM-001】

Halpha 采用“宽源码边界、窄运行时边界”的 monorepo：交易产品、前端、研究和按需工程工具可以拥有不同目录、依赖环境、测试目标和构建输入图，但交易产品仍保持 HALPHA-ENG-002 与 HALPHA-SYS-002 定义的单一产品发布组、模块化单体、两种产品进程角色、一个数据库产品和每环境一条场所写链。

并行开发通过稳定语义范围、路径所有权、公开契约、工作包 DAG、选择性反馈和串行集成门取得，不把源码边界自动升级为服务、数据库、持久工作器或独立发布。开发授权、集成资格和发布资格是三个不同判断：一个工作包可以被适用 L4 授权独立开发，但在依赖、共享路径和验收未满足前不能集成；集成完成也不能替代完整产品发布门。

长期并行工具只采用 Git branch/worktree 提供独立 checkout/分支和 Git 的单一串行 merge/PR 集成；worktree 本身不强制路径所有权，路径门必须用基线与输出 commit 的差异验证。不增加 monorepo 编排器、远程构建缓存、私有包仓库或第二 CI。GitHub Actions 只能复跑仓库内同一组命令，不拥有另一套构建、资格或发布语义。工作包能否并行由 DAG 无依赖、稳定语义锚点不重叠且独占路径不重叠推导，不维护成对 `may_run_in_parallel_with` 清单。

默认只允许三种依赖定义与锁身份：交易产品 Python、研究 Python 和现有前端 Node；这不是最多三个物理环境。不同 worktree 可以从同一锁建立可删除研究 venv，但每次运行必须证明解释器、锁摘要和 `halpha_research` 源码来自当前 worktree，不共享可变 editable install。R00 只要求每个 worktree 一套研究环境，不为 AI study 另建第二物理 venv、依赖子集或运行身份。短生命周期工具复用其中适用定义或标准系统工具。新增第四种依赖定义、多个核心 Python distribution、私有包仓库、第二构建平台或独立发布流水线，必须有多个真实消费者和测得的冲突、隔离或发布问题，并证明总维护成本下降；否则不支持。

研究环境使用标准库 `venv`、一个 `pyproject.toml` 直接依赖来源和一个由 pip-tools 生成的完整 hash lock；不重复维护 runtime/dev 两套锁，也不修改产品 Python lock。研究组件身份和用途由 HALPHA-ALP-003 唯一选择；本文件只拥有独立环境、依赖声明、完整锁、安装与资格化边界。与产品重叠的组件由适用 L4 绑定到产品已资格化的同一兼容组合，研究专属组件只存在于研究环境；pytest 与 Hypothesis 承担研究契约和性质验证。精确版本、lock、workflow 和命令由适用 L4 固定。

外部 AI 仍是 CON/ENG 定义的开发者工具，不是 Halpha 运行实体。它在独立 Git worktree 内通过人也能调用的 `python -m halpha_research` 和 Pydantic JSON Schema 工作；Halpha 不反向调用模型 API，不保存供应商会话状态，也不把 AI 客户端、模型 SDK 或 agent framework 放入产品/研究锁。经项目所有者授权并在仓库规范、工作包路径、工具权限与凭据边界内工作的 AI，按可信项目开发者处理；其研究源码不因作者身份额外成为敌对输入。固定 `ResearchStrategyHarness` 可以在同一研究环境的新进程中直接装载已提交 study 并调用 NautilusTrader。R00 不建立模型外 sandbox、父进程/worker 能力分离、observation/intent、framed stdio 或专用 launcher。AI 不可用、会话丢失或供应商升级只影响创作效率，不能阻断同一固定请求由项目所有者恢复性重演，更不能影响交易产品。

“可信 AI”表示开发者所使用的 AI 不以作恶为目的，并会尽最大努力使工作正确；它不表示 AI 不会理解错误、遗漏、误用工具或产生实现缺陷。工程控制因此按场景重要程度、潜在错误成本和可恢复性选择：优先使用范围审查、输入 schema、静态检查、自动测试、独立重演、证据复核、产品内重新资格化和明确回退来发现或限制错误影响。只有新增控制降低的预期风险高于其实现、运行、升级和退出成本时才采用；不为研究代码建立成本投入明显高于风险价值的安全隔离、重复运行时或专用协议。

不同 AI 研究角色可以通过新会话、干净 checkout、只读冻结输入和独立输出路径减少结果污染，不建设多代理运行平台，也不把这些措施表述为安全隔离。精确客户端/模型、非秘密提示协议摘要、供应商遥测/保留/训练政策、允许上传的数据类别、token/API/墙钟/计算预算及实际成本属于适用 L4 和研究证据来源记录。AI 可信不等于研究结论可信：事前政策、完整搜索、holdout 暴露、统计门、失败保留、独立重演、项目所有者最终审查和产品内重新资格化仍不可省略。

# 1. 工作区分类与仓库结构【ENG-MONO-WS-001】

## 1.1 四类工作区【ENG-MONO-WS-001-DEF】

| 工作区 | 长期责任 | 运行与发布边界 |
|---|---|---|
| 交易产品工作区 | 正式业务模块、App/Executor composition root、产品数据库、正式策略和产品测试 | 唯一后端产品 distribution；与前端组成一个产品发布组 |
| 前端工作区 | 交易工作台静态前端和生成客户端 | 独立 Node 构建单元；静态制品随产品发布组发布，不形成运行中的 Node 服务 |
| 研究工作区 | HALPHA-ALP-003 的候选研究、研究运行清单与研究证据包 | 独立 Python 依赖环境；只按需运行，不进入产品制品、进程或发布组 |
| 按需工具工作区 | 资格化、provisioning、诊断、迁移辅助和故障注入 | 短生命周期命令；不得取得持久业务责任或第二事实权威 |

工作区是源码、依赖和验证边界，不是 SYS 业务模块、运行实体或服务。一个工作区失去独立消费者、依赖差异和变化节奏后必须合并或删除，不为目录对称长期保留。

## 1.2 目标目录边界【ENG-MONO-WS-002-REQ】

长期目标结构为：

```text
src/halpha/                         # 交易产品唯一 Python distribution
  planning/
  capital/
  venue_integration/
  outcomes/
  user_workbench/
  app/                              # composition root
  executor/                         # composition root
  database/

frontend/                           # 现有前端 Node 构建单元

research/                           # 独立研究 Python 环境
  pyproject.toml
  requirements.lock                # 从 pyproject 生成的唯一完整 hash lock
  src/halpha_research/              # 只承载 ALP-003 的三项薄责任；实际文件由适用 L4 固定
  campaigns/                        # 已提交的研究政策、任务、用例/请求、角色材料与冻结选择；文件协议而非数据库
  studies/                          # 每项候选的 study 源码与固定配置
  notebooks/                        # 只提交 Jupytext .py:percent 源码
  tests/
  runs/                             # 忽略、可删除、可重建
  evidence/                         # 只保留仍被决定引用的小型冻结证据包

tools/
  qualification/
  provisioning/
  diagnostics/

tests/
  architecture/
  contracts/
  integration/
```

目录目标不授权一次性搬迁。现有文件只在真实功能修改、依赖收敛或明确重构工作包中迁移；不得为取得目录整齐而同时重写业务实现、数据库迁移和构建身份。适用 L4 必须为每次迁移声明源路径、目标路径、直接消费者、兼容验证和回退方式。

研究政策、AI 研究任务、用例、请求/回执、角色材料、运行清单、候选全量/确认性暴露索引、AI 审查视图和证据包的 Pydantic 模型及其语义由 HALPHA-ALP-003 v0.4.0 唯一拥有；本文件只要求机器 schema 从该模型生成，不同时维护手写 `schemas/`、数据类和 JSON Schema 三份定义。只有研究工作区一个实现消费者时不建立仓库级共享 contract 包；未来出现第二个真实源码消费者、双方不能由同一工作区拥有且复制漂移已经可测时，才可由相应语义所有者另行设计共享契约。研究模型不得包含正式策略规则、交易计划状态、资金或权限判断、动作写入、产品 DTO 的手工副本，也不得成为绕过拥有领域的通用 `common` 包。

`pyproject.toml` 是研究直接依赖和包元数据的唯一手写来源，`requirements.lock` 是可删除重建的生成物；不得再用 `requirements.in`、Notebook 安装单元或根产品项目文件声明同一依赖。`campaigns/` 只保存已提交、无秘密且适合 Git 的研究政策、任务、用例/请求、候选全量、确认性暴露索引的证据快照、角色材料和冻结选择；各 worktree 的 Git 快照不是确认性运行时准入权威，不保存完整聊天、模型私有状态、供应商会话或原始私有数据。`runs/` 与原始/缓存数据不进入 Git；`evidence/` 只保留仍被经济判断、晋升或反例引用且体量适合仓库的小型冻结包，大型可重建输入只保存来源和摘要。

不适合 Git 但仍被决定引用的大型证据包不得转移到 `runs/`。适用 L4 必须为它固定一个仓库外耐久文件根、稳定存储标识、相对路径、完整性摘要、保留期、备份/恢复和按来源重新取得后的复验方式；未通过这些条件时只能保持未引用材料。该文件根不是新工作区、产品存储、数据库、服务或发布组。

确认性准入另有一个单一宿主、单一文件系统、位于所有 worktree 与 `runs/` 之外的小型耐久 `confirmation_exposure_root`。它不是证据 payload 根、数据库、服务或 campaign 工作目录；只有固定研究 CLI 的确认性准入路径拥有宿主级排他锁和写权限，请求字段、单个 study 与普通工作包均不能选择、覆盖或重置它。适用 L4 必须固定稳定标识、解析路径、锁/刷新/同文件系统原子替换语义、不可变索引代与当前代摘要、备份/恢复、损坏/回滚/分叉检查和卸载后处理；根不可用或最新代不能证明时确认性能力 fail-closed。

# 2. 依赖方向与路径所有权【ENG-MONO-DEP-001】

## 2.1 允许依赖方向【ENG-MONO-DEP-001-REQ】

稳定依赖方向为：

```text
交易产品入口 → 交易产品公开应用边界 → 业务模块与端口
前端          → 唯一 OpenAPI 生成客户端 → 交易产品 API
研究工作区    → 自有 Pydantic 文件模型、固定研究 harness、带摘要数据、允许的产品纯逻辑公开接口
已提交 study  → 固定 ResearchStrategyHarness → NautilusTrader 研究运行
外部 AI       → 当前工作包允许的规范/源码/文件请求 → 同一研究 CLI 与 JSON 回执
按需工具      → 被操作能力的公开命令、配置或文件契约
```

同时适用以下禁止方向：

- `src/halpha`、产品 `pyproject` 和产品运行依赖不得依赖 `research`、Notebook、研究界面或研究锁文件；
- 产品与研究代码不得调用外部 AI 模型 API、导入模型 SDK/agent framework 或依赖供应商会话；外部 AI 不得绕过研究 CLI 形成另一条运行、gate、freeze 或晋升入口；
- 研究工作区不得导入 App、Executor、数据库 ORM/repository、composition root、秘密加载器或场所写端口；
- 前端不得读取数据库、秘密或产品私有模块，不手写与 OpenAPI/领域 schema 平行的 DTO；
- fixtures、故障注入和 qualification probe 不得被产品运行代码导入；
- 工具不得通过直接表写、隐藏脚本或第二 API 绕过产品命令与迁移边界；
- 任何工作区都不得借共享工具函数取得相邻领域私有状态或业务决定权。

研究只有在策略晋升后出现真实研究消费者时，才可由研究环境消费交易产品公开、无场所副作用的纯逻辑接口；默认仍使用 HALPHA-ALP-003 的文件证据交接。交易产品不能反向从研究目录取得实现；候选研究晋升后，唯一正式源码进入交易产品工作区并按 HALPHA-ALP-002 重新资格化。

## 2.2 独占路径与共享路径【ENG-MONO-PATH-001-REQ】

每个并行工作包必须声明独占写入路径。两个同时开发的工作包不得拥有重叠路径，也不得分别修改同一稳定语义后等待合并时裁决。

以下路径或含义默认是共享串行集成点，不能由普通工作包独占：

- 仓库根 Python/Node 项目定义及产品锁文件；
- Alembic 迁移 head、迁移环境和产品 schema 所有权；
- App/Executor composition root、运行 profile 与秘密引用边界；
- 正式策略 registry、产品 OpenAPI 和由其生成的前端类型；
- BuildManifest 与产品发布摘要生成逻辑；
- 研究 policy/schema/runner/固定 harness/gate/evidence、study 入口、研究锁、confirmation exposure 索引 schema/证据快照，以及宿主级 exposure root 的唯一确认性准入写入实现；
- L3/L4 当前适用规范、当前建设计划和治理验证器。

共享串行集成点由适用 L4 为当前工作流指定唯一集成所有者。普通工作包只能提交明确输入、生成候选差异或等待集成所有者处理，不能创建平行锁文件、迁移 head、OpenAPI、正式 registry 或 BuildManifest 作为临时兼容路径。

# 3. 并行工作包与集成门【ENG-MONO-WRK-001】

## 3.1 工作包最小契约【ENG-MONO-WRK-001-REQ】

适用 L4 授权的每个并行工作包至少记录：

- `id` 与 `semantic_scopes`：稳定工作包身份，以及一个或多个 `{owner, anchor}`；`owner` 标识权威归属，`anchor` 精确到被修改的稳定语义，一个原子工作包可以涉及多个所有者；
- `base_revision`：开始开发时的干净 Git commit，并引用该 commit 所含 `HALPHA-PLAN-001` 的 `accepted_design_set` 与 `basis.accepted`；
- `owned_paths`：本工作包独占写入路径；
- `depends_on`：必须已完成的工作包或决定门；
- `contracts.inputs` 与 `contracts.outputs`：可独立构造的输入和可独立检查的交付；每项输入必须带生产者版本、commit 或内容摘要；
- `effects`：只汇总 migration、runtime、release、authority 和 credential 影响；没有影响时统一为 `NONE`；
- `integration_gate` 与 `exit_evidence`：进入唯一集成版本前的条件和实际退出证据；退出证据必须记录干净 `output_revision`。

`shared_paths`、`generated_outputs` 与 `collapse_or_delete_condition` 只在当前工作包确实涉及时记录。并行关系由 DAG 无相互依赖、`semantic_scopes` 中没有相同稳定锚点且 `owned_paths` 不重叠自动推出，不保存 `may_run_in_parallel_with`；仅 owner 相同不构成冲突，具体 anchor 重叠才构成语义冲突。依赖允许/禁止由本契约和适用拥有领域决定，不在每包复制长清单。上述字段不表示当前已授权任何工作，也不建立工作包 registry、数据库、看板或调度服务。

集成门必须在 Windows 大小写规范化并解析 symlink、junction/reparse point 后，用 `git diff --name-only base_revision...output_revision` 或等价机器检查证明已提交修改只落在 `owned_paths`，另加由唯一集成所有者拥有的已声明 `shared_paths`/`generated_outputs`；还必须拒绝允许的可删除输出根之外未跟踪、被忽略却可被运行加载或越出声明路径的材料，不能把 `git diff` 当作完整文件系统边界。`base_revision`、其中 PLAN 的 `accepted_design_set`/`basis.accepted` 或任一输入契约版本变化后，原集成资格失效；工作包必须重放差异、解决基线变化并重跑受影响生产者/消费者验证，不能只更新版本字段。

## 3.2 外部 AI 与研究 CLI 工程契约【ENG-MONO-AICLI-001-REQ】

外部 AI 的创作阶段和确定性研究运行阶段分离：

- 创作阶段只取得当前工作包需要的适用规范、CLI/schema、审查视图、study 源码路径、已有失败材料和许可允许的数据；写入限制在工作包 `owned_paths`。AI 源码完成不因文件副作用自动执行，静态导入/危险 API 检查只作为防错门；
- 确定性 `run` 在同一研究环境的新进程中直接装载已提交 study，由固定 `ResearchStrategyHarness` 装配 NautilusTrader 引擎、指标、组合/订单/成本状态、报告器和 canonical artifact writer；每次运行使用独立输出目录，完成或失败后退出；
- discovery/validation/stress/holdout 使用同一 runner、harness、锁和研究依赖。新进程、独立输出目录、schema 与预算用于可重演、资源计量和失败清理，不声称抵御恶意源码；
- holdout/复现角色使用新 worktree 或干净只读 checkout、固定 harness/study 源码/请求和单一新输出根；worktree 内索引只能预检。固定研究 CLI 必须在读取任何 holdout 数据字节前，解析政策允许的 DAT-qualified immutable `data_snapshot_ref`，核对 DAT qualification evidence、snapshot digest 与规范 UTC 半开区间；AI、study 或请求不得创建、改写或用路径、名称、digest 代替该引用，缺失、变化、修订/重导出关系不明、区间不可比较或核对不一致即拒绝。随后 CLI 才可通过单一宿主级 `confirmation_exposure_root` 的排他锁验证最新索引代、跨全部决策族查询相同引用的区间重叠/包含，并耐久原子写入不可逆 `EXPOSURE_STARTED`；锁、摘要、资格核对或写入不确定即不打开 holdout，claim 后失败或崩溃仍永久算暴露；
- 最终选择角色只读通过完整性检查的审查视图、允许的冻结源码、候选全量与确认性暴露索引，只写选择材料；它不能调用新搜索、修改硬门或进入产品共享路径。

适用 L4 必须固定 AI 客户端公开身份、模型标签可获得程度、非秘密协议修订、供应商遥测/保留/训练政策与允许上传的数据类别、研究 venv 的解释器、lock 身份、安装闭包、`sys.path` 与 DLL 搜索根、`ResearchStrategyHarness` 与 study 入口摘要、token/API/墙钟/CPU/内存/输入输出预算和停止结果。确认性运行还必须固定政策允许的 DAT-qualified immutable `data_snapshot_ref`、DAT qualification evidence、snapshot digest、规范 UTC 半开区间和缺失/变化/关系不明时的拒绝条件，以及单一宿主/exposure root 稳定标识与解析路径、唯一写入路径、排他锁 API、索引代 schema/摘要链、flush/fsync 等价、同文件系统原子 replace、claim/outcome 状态机、备份恢复和损坏/回滚/分叉演练。R00 明确不选择 sandbox/launcher、第二物理 venv、父进程/worker 身份、observation/intent 或专用 IPC。完整提示、聊天记忆、模型私有状态和供应商会话不作为核心重演输入；能核对的创作来源与实际成本只作为 ALP-003 定义的非权威来源材料。

CLI 只接受 ALP-003 的 Pydantic 规范 JSON 和仓库相对路径。路径经 Windows 大小写规范化并解析 symlink、junction/reparse point 后必须留在允许根；请求不得指定 shell、任意 executable/cwd/environment、URL 下载、秘密、产品命令、输出根、exposure root 或锁路径，也不得创建、改写或用路径、名称、digest 代替政策允许的 `data_snapshot_ref`。CLI 只用固定模块和参数数组启动当前研究运行，禁止 `shell=True`、`eval` 或字符串拼接执行。holdout 的普通 schema 预检和请求自报路径、名称或 digest 不能代替固定研究 CLI 对 `data_snapshot_ref`、DAT qualification evidence、snapshot digest、规范 UTC 半开区间的核对、锁内权威查询与 claim 写入；只有完成资格核对并耐久写入 claim 后才可打开数据。预算耗尽、超时或异常返回非零状态与规范回执，终止本次运行并保留已完成范围，不自动增加预算、重试、后台恢复或转用另一个运行器。

Halpha 不向模型供应商发起网络请求。外部 AI 的供应商网络只用于客户端自身创作，不能携带产品配置、秘密存储引用、数据库连接、DEMO/LIVE 凭据、产品运行日志或其他未经项目所有者和数据许可明确允许上传的材料。可信 AI 可以读取当前任务和数据许可允许的本地研究材料；是否允许供应商处理由适用 L4 和具体任务决定，不由研究目录推断。AI 不可用时项目所有者只可恢复性重演已经固定的请求，研究也可以停止或等待，交易产品不受影响。

## 3.3 DAG 与三个资格判断【ENG-MONO-WRK-002-REQ】

工作包依赖必须形成无环有向图。只有边界清楚、输入可构造、输出可独立验证、没有相互依赖且不争夺同一稳定语义锚点或路径的工作包才自动具备并行资格；其余工作保持串行。

单个研究活动的 discovery/validation、study 源码与独占证据路径可以按上述规则跨 worktree 并行；确认性 holdout 准入不能由 Git 路径不重叠推导为并行。所有 worktree 必须指向同一宿主 exposure root，并只由固定研究 CLI 的确认性准入路径在短排他锁内完成查询与不可逆 claim。不同 `data_snapshot_ref` 或互不重叠区间在 claim 耐久写入后可按资源边界并行执行；远程宿主、分叉 exposure root 或无法共享同一锁的运行不具备确认性资格。若以后需要跨宿主确认性并发，必须先重新设计一致性边界，不能在本文件下引入服务或数据库。

- **开发授权：** 允许在独占路径内根据固定输入契约实现；不表示依赖完成或输出可集成。
- **集成资格：** 依赖工作包、契约、共享路径、迁移和相关验证全部通过，且集成差异由唯一集成所有者复核。
- **发布资格：** HALPHA-ENG-002 的完整交易产品构建、迁移、BuildManifest、DEMO/LIVE 等价、回退和发布门全部通过。

开发授权不能提前形成数据库迁移、真实场所写、产品运行配置或当前支持声明。集成资格不能替代发布资格。研究工作包完成只说明研究材料可交接，不能使正式策略、产品能力或真实资金路径可用。

## 3.4 串行集成情形【ENG-MONO-WRK-003-REQ】

以下情形必须停止并行写入并进入单一集成队列：

- 两个工作包的 `semantic_scopes` 含相同稳定锚点或需要修改同一文件；
- 需要新增或排序数据库迁移；
- 共享契约发生不兼容变化；
- 正式策略 registry、OpenAPI、composition root、锁文件或 BuildManifest 发生变化；
- 选择性验证发现跨工作区影响，或无法证明影响隔离；
- 一个工作包需要修改另一个仍未集成工作包的输出。

集成失败时回到相关工作包修复或收缩范围，不在共享路径保留两套实现、兼容双写或临时 fallback。需要跨模块原子性时继续遵守 SYS 的本地事务边界，不以工作包分离引入分布式事务。

# 4. 既有构建身份与选择性验证【ENG-MONO-BLD-001】

## 4.1 产品构建身份保持不变【ENG-MONO-BLD-001-REQ】

本契约不新增产品兼容摘要、资格 bundle、第二构建身份或 BuildManifest 字段。正式产品构建继续完全服从 HALPHA-ENG-002：来自一个干净 Git commit，由现有唯一 `BuildManifest.build_digest` 绑定源修订、依赖锁、迁移头、正式策略登记、App/Executor/前端制品、非秘密配置以及既有不可分割证据摘要和 eligibility；DEMO 与 LIVE 继续使用同一产品源码、锁、迁移、正式策略和制品。

研究源码、研究依赖和研究证据包不进入产品制品，也不成为第二个可部署制品组；但它们与产品同处 monorepo，任何已提交研究变化仍会改变完整仓库修订，并按当前 BuildManifest 规则参与产品构建身份判断。本契约接受这一额外构建噪声，以保持既有构建身份语义。只有实际发布数据证明该噪声造成不可接受成本，才可以协调修订 HALPHA-ENG-002 与 BuildManifest，精确定义输入集合、迁移兼容和回退；不得由本契约提前推断研究变化与产品兼容性无关。

当产品 BuildManifest 或资格基线已经冻结且绑定完整仓库 commit 时，研究可继续在独立 branch/worktree 开发和运行，但研究提交不得合入该产品集成分支而使冻结基线漂移；只有冻结窗口结束，或产品集成所有者显式更新基线并重新执行适用资格门后才可合入。研究进程读取独立 checkout 不改变已冻结产品身份。

研究工作区可以在自己的运行清单和证据包内记录研究源码与包摘要；这些摘要只服务研究重演和交接，不进入产品 BuildManifest，也不表示产品构建或交易资格。

## 4.2 选择性开发反馈【ENG-MONO-BLD-002-REQ】

开发反馈可以按变更路径、依赖图和生成输出运行最小充分检查：

- 单一工作区内部变化运行本工作区测试、格式和依赖边界检查；
- 公开契约变化运行全部直接生产者与消费者的契约测试；
- 共享路径、迁移、正式策略、composition root、产品锁或 BuildManifest 变化运行完整相关产品检查；
- 无法可靠分类的变化按更高影响执行，不以路径名称推断隔离成功。

选择性验证只缩短开发反馈，不缩短产品集成和发布门。准备产品发布时仍执行 HALPHA-ENG-002 规定的完整产品构建、迁移、架构、集成、浏览器、恢复、DEMO/LIVE 等价和适用外部资格验证。某次选择性检查遗漏跨工作区影响时，开发者必须补充依赖图或契约检查；不得把偶然成功写成永久跳过规则。

## 4.3 生成物与单一来源【ENG-MONO-BLD-003-REQ】

OpenAPI、前端类型、从 Pydantic 模型生成的研究 schema、依赖锁、许可证清单、迁移 head 和构建摘要都必须有唯一生成来源。生成物只能由拥有输入的工作包或集成所有者更新；消费者不得手工修补生成结果形成平行语义。

生成工具不可用或输出漂移时，受影响工作包不能集成。允许保留上一已验证发布用于回退，但不能同时把旧生成物和新手工补丁作为当前双实现。

## 4.4 轻量工程工具选择【ENG-MONO-TOOL-001-REQ】

工作区长期只使用以下既有或标准工具：

- Git branch 与 worktree 为每个获授权工作包提供独立 checkout；每包绑定干净 `base_revision`，由 base-to-output 差异门强制路径范围，Git merge/PR 是进入唯一集成版本的路径；
- Python 标准库 `venv` 分别建立产品和研究环境，pip-tools 从各自唯一输入生成各自 hash lock；
- Python 标准库 `argparse`、`pathlib`、`subprocess`、`json` 与 `hashlib` 承担研究 CLI、路径收敛、新进程运行、规范 JSON 与摘要；Pydantic 生成同一文件协议 schema；
- pytest、Hypothesis、现有文档校验器和架构/契约测试提供本地反馈；
- 现有 GitHub Actions 只在干净 checkout 复跑同一锁安装与命令，不能维护另一套成功标准。

以上 Python 工具承担防错、可重演和失败清理，不被描述为恶意源码安全隔离。AI 作为可信开发者仍可能犯错，因此按影响和错误成本使用范围审查、schema、静态检查、测试、重演、证据复核与产品内重新资格化。R00 不选择 OS sandbox/container、父进程/worker、第二研究 venv 或专用 IPC；只有实际风险与失败证据证明某项新增控制的净价值高于其安装、运行、升级和退出成本时，才先修订本 L3 再评价。出现第四种身份、持久守护或远程服务时必须同时按第 9.1 节复核，改变产品拓扑时复核 ARC。

Nx、Turborepo、Bazel、Pants、uv/Poetry workspace 编排、私有 Python 包仓库、远程构建 cache、模型供应商 SDK、PydanticAI、LangChain/LangGraph、AutoGen、CrewAI、Semantic Kernel、MCP SDK/server、向量库/RAG、MLflow、DVC、Airflow、Prefect、第二 CI/构建平台和通用 monorepo graph 服务均不进入默认基线。单一项目所有者、按需外部 AI、JSON/CLI 文件交接和受限并发不足以抵消这些平台的供应商 API、工具循环、状态、重试、追踪、配置、升级、诊断和退出成本，也不能提高研究证据权威。

只有至少两个真实 AI 客户端长期因 CLI/schema 使用产生可测重复适配或错误，才比较由同一 Pydantic 模型生成、只走 stdio、无状态且不增加业务命令的薄 MCP adapter，仍不先建 HTTP 服务。只有真实出现跨会话持久编排、无人值守多步恢复或多个独立 agent 共享状态，且其收益超过新状态与运维成本，才重新评价 agent framework；形成受支持产品入口、常驻或远程服务时先按第 9.1 节复核 FLOW/VIS/ARC/SYS/UX。

# 5. 迁移、运行时与凭据隔离【ENG-MONO-ISO-001】

## 5.1 单一迁移线【ENG-MONO-ISO-001-REQ】

产品数据库只有一个 Alembic head 和一条按序集成的迁移线。工作包可以在独占测试 fixture 中表达所需 schema 候选，但只有集成所有者可以创建、排序和合并正式迁移。迁移不得引用研究包、Notebook 或研究依赖，也不得用平行表、双写或兼容 reader 掩盖未完成语义裁决。

两个工作包都需要 schema 变化时按依赖和具体 schema 语义锚点的所有者确定顺序；无法证明旧数据、开放责任和回退可解释时阻断集成。迁移失败继续遵守 HALPHA-ENG-002 的备份、恢复或前向修复边界。

## 5.2 研究和工具隔离【ENG-MONO-ISO-002-REQ】

研究、外部 AI 与普通工具默认只有无交易写能力的本地身份。它们不得取得 LIVE/DEMO 场所写凭据、产品数据库写角色、App/Executor 长期秘密或可调用场所写端口的配置。需要产品材料时使用带来源和摘要的只读导出；可信外部 AI 可以读取当前任务、数据许可和供应商处理政策明确允许的研究材料，默认审查入口仍是 `ai_review_view.json` 与无秘密机器回执。完整数据、holdout 和本地完整证据 payload 是否可由 AI 读取，按材料敏感性、许可与审查需要由适用 L4 或具体任务明确，不以作者身份或目录自动推断。需要对真实外部系统资格化的工具必须由适用 L4 明确限定凭据类别、动作范围、退出证据和与产品运行的时间隔离。

研究、外部 AI 和普通工具只能按需启动。唯一允许跨进程终止保留的研究运行状态，是 HALPHA-ALP-003 要求写入 `confirmation_exposure_root` 的不可逆确认性暴露 claim 与索引代；它们是小型研究资格证据，不是产品业务状态、持久任务 cursor/due/退避或自动恢复责任。除此之外，终止后不得留下其他持久 claim、cursor、due、退避、自动恢复责任或产品业务状态。它们不得成为 App、Executor、保护、核对、停止、恢复或发布的同步依赖。研究消耗资源或供应商成本时，交易产品和项目所有者预算优先；达到预算或影响产品开放责任时停止研究任务。

本地 Notebook、CLI 或临时研究服务器只是开发工具。若未来需要受支持的独立研究应用、长期常驻服务、产品认证、远程入口、持久状态或自动启动，必须按第 9.1 节对应行复核或修改适用上位，再修订并接受相应 SYS、UX、ENG 与适用 L4 设计；本契约不授权该演进。

# 6. 集成交接与失败结果【ENG-MONO-INT-001】

## 6.1 研究到产品的交接【ENG-MONO-INT-001-REQ】

研究交接、正式策略晋升和 active studies 中可运行等价原型的移除完全由 HALPHA-ALP-003 唯一拥有。本文件只保证产品运行时不反向依赖研究工作区，并禁止为交接建立第三个共享 distribution、自动代码转译器或研究—产品同步器；产品正式策略 registry、产品锁和资格验证仍由既有产品契约唯一拥有。

研究证据包摘要可以被正式策略来源追溯或资格记录引用，但不为此新增 BuildManifest 研究字段。BuildManifest 仍通过完整仓库 commit 间接绑定该修订中全部已提交研究内容；它不绑定未提交运行或仓库外大型历史包，也不把这些材料变成产品资格输入。冻结证据引用的源码 commit 必须从受保留 Git ref/正式历史可达，或证据包包含规范源码快照和摘要；删除 worktree/分支、squash 或 Git 垃圾回收前必须验证这一条件，正向、负向与零候选结果相同。研究工作区被删除、重建或依赖升级不能静默改变已经发布的正式策略源码。

## 6.2 失败与阻断【ENG-MONO-INT-002-REQ】

| 情形 | 必须结果 |
|---|---|
| 工作包稳定语义锚点或独占路径重叠 | 不并行；收缩或交由一个集成工作包 |
| 基线、输入契约或实际差异不能证明 | 集成资格失效；固定新基线、重放差异并重验，不手改版本字段 |
| DAG 出现循环或依赖版本未知 | 阻断开发授权或集成，不猜测顺序 |
| 出现多个迁移 head、正式 registry、OpenAPI 或锁文件 | 阻断集成，回到唯一生成来源 |
| 产品源码反向依赖研究工作区 | 架构检查失败；删除依赖或显式完成正式晋升 |
| 研究或工具取得产品写角色、交易写凭据或持久责任 | 停止相关入口；重新设计，不以配置说明接受 |
| 外部 AI 越过角色 read/write roots、提前读取 holdout、本地完整 payload、秘密/原始数据或修改共享协议 | 停止相关 AI 入口并使受影响研究资格失效；记录暴露范围，不用新会话伪装未暴露 |
| 研究请求包含大小写/路径逃逸、symlink/junction/reparse point 逃逸、shell/命令注入、动态 import、网络下载或任意环境 | 校验拒绝且不启动进程；保留无秘密 violation 回执 |
| AI 或其他开发者越过任务授权、工作包路径、数据许可、供应商处理政策、秘密或凭据边界 | 停止相关入口，记录暴露范围并使受影响研究资格失效；可信不构成扩大权限的依据 |
| study 自报或篡改 `PASS`、p 值、绩效、候选计数、canonical report，删除失败或只保留胜者 | `gate` 从规范输入、原始引擎产物和完整索引重算；来源或摘要不匹配使运行失效，不能冻结证据包 |
| holdout 准入无法取得单一 exposure root 的锁，最新索引代/摘要不明，原子写入/刷新不确定，或根丢失、回滚、分叉、损坏 | 固定研究 CLI 不得打开 holdout；确认性能力禁用，不能改用 worktree Git 副本、另一根或人工口头记录 |
| 请求、AI 或 study 创建/改写 `data_snapshot_ref`，以路径、名称或 digest 代替政策允许引用，资格材料缺失或变化，修订/重导出关系不明，规范 UTC 半开区间不可比较，或请求与 DAT qualification evidence 不一致 | 固定研究 CLI 在打开 holdout 前拒绝；新的或变化引用只有先取得 DAT 资格材料并由适用 L4 与研究政策显式选择后才能准入，关系不明时确认性能力 fail-closed |
| 运行在不可逆 claim 后失败、被 kill 或宿主崩溃，或 outcome 更新失败 | 原 claim 永久按暴露保留；恢复后只可写引用原 claim 的失败/outcome 新索引代，不得删除、重试为新确认或回滚当前代 |
| token/API/墙钟/计算/体量预算耗尽 | 当前请求明确停止、终止适用进程树并保留部分结果；不自动扩额、后台重试或切换供应商 |
| AI 客户端、模型或供应商会话不可用 | 研究创作等待或停止；项目所有者只可恢复性重演已经固定的请求，不承担常规中间研究；产品与既有证据不受影响 |
| 选择性验证漏掉共享契约影响 | 补跑完整相关检查，修正依赖图；当前结果不可集成 |
| 研究工作区失败或不可安装 | 只阻断研究工作；不得阻断既有产品发布与运行 |
| 删除 worktree/分支或 squash 后证据源码 commit 不再从耐久 ref 可达且包内无规范源码快照 | 阻断删除或使该证据不可引用；不得只保留不可达 commit ID |
| 工作区长期只有转发、重复模型或共享路径争用抵消收益 | 合并回拥有工作区并删除边界 |
| 需要新增产品进程、数据库、消息总线或独立发布组 | 本契约阻断；先修订并接受相应 ARC/SYS 设计 |

# 7. 最小验收契约【ENG-MONO-TST-001】

适用 L4 启用相应能力前，至少证明：

1. monorepo 依赖图无环，交易产品、前端、研究、外部 AI 和工具的允许及禁止依赖可由自动架构检查验证；产品/研究代码不调用模型 API 或导入模型 SDK/agent framework；
2. 至少两个获并行资格的工作包绑定干净 `base_revision`、带版本/摘要的输入和干净 `output_revision`；独立 worktree 提供 checkout 隔离，路径经大小写规范化和 symlink/junction/reparse point 解析后，base-to-output 差异门与未跟踪/忽略材料检查共同证明修改只落在各自 `owned_paths`，共享/生成路径只由唯一集成所有者修改，Git 串行 merge/PR 后没有平行实现残留；
3. `src/halpha` 不依赖 `research`，研究不能导入产品 repository、composition root、秘密加载器或场所写端口；外部 AI 只能写当前工作包 `owned_paths`；
4. 研究 `pyproject.toml` 能生成唯一完整 hash lock，干净 `venv` 安装、`pip check`、许可证闭包和删除后重建通过，且不改变产品 lock；不同 worktree 的可删除 venv 都验证解释器、锁摘要和实际加载源码来自本 worktree，不共享可变 editable install；每个 worktree 只需一套研究环境，不建立父进程/worker 双 venv；
5. HALPHA-ALP-003 选择的研究组件在固定锁下完成公开导入与 CLI 路径验证；pytest/Hypothesis 覆盖研究政策子集、数据、摘要、路径逃逸、extra fields、命令注入、预算和重复运行反例；统计 gate 还以已知 null/正/负样例证明 `confirmation_claim_type` 生效：BH/BY set-FDR 只能冻结完整集合级材料，事后抽取的集合成员不能成为个体最终候选，预选单假设全局 α 或预声明有限族 Bonferroni strong-FWER 才能形成个体确认资格；
6. 人与 AI 用同一请求和 CLI 得到相同请求摘要与核心结果；外部 AI 不能产生另一条运行/gate/freeze/晋升入口，AI 不可用或会话丢失时项目所有者只作固定请求的恢复性重演；
7. 固定 `ResearchStrategyHarness` 在同一研究环境的新进程中直接装载已提交 study；runner 绑定数据/holdout、时钟、引擎、指标、组合/订单/成本状态、确认性计数、报告器和 canonical writer；study 自报或篡改 `PASS`、p 值、绩效、报告、候选计数、失败记录或胜者集合不能通过来源、摘要和 gate 重算；
8. L4 明确记录 R00 不采用 sandbox/launcher、第二物理 venv、父进程/worker、observation/intent、专用 IPC、driver/service/VM/image/distro；普通新进程和独立输出目录只用于可重演、预算停止与失败清理；
9. 提案、证伪、holdout/复现与最终选择角色按研究污染风险使用新会话、干净 checkout、冻结输入和独立输出；AI 可读取任务与数据许可允许的材料，供应商遥测、保留/训练政策和允许上传数据类别有实证记录，秘密与交易写凭据始终不进入研究环境；
10. token/API/墙钟/CPU/内存与输入输出预算达到时请求停止并留下规范回执，不自动扩额、后台重试、切换供应商或创建持久责任；
11. 每个并行工作包只有最小必填字段、一个或多个 `{owner, anchor}` 稳定语义范围和互不重叠的独占路径；同 owner 不同 anchor 可以并行，同 anchor 必须串行，并行关系不依赖人工成对清单；discovery/validation 可跨 worktree 并行，但 confirmation admission 必须经单一宿主 exposure root 的短排他锁；
12. 共享路径只有一个集成所有者，正式迁移只有一个 Alembic head，生成输出只有一个来源；runner/harness/gate、Pydantic schema、study 入口、exposure-index 协议、研究锁与 evidence 由共享集成所有者串行修改，不由各 AI 研究用例复制或重置；运行时 exposure root 只有固定研究 CLI 的确认性准入路径可写，worktree Git 快照和普通请求无写权；CLI 只解析政策允许的 DAT-qualified immutable `data_snapshot_ref` 并核对 DAT qualification evidence、snapshot digest 与规范 UTC 半开区间，请求不得创建或改写引用；缺失、变化、修订/重导出关系不明、区间不可比较或请求不一致均在打开 holdout 前失败；并发双任务、旧 worktree、锁竞争、partial write、kill-before-result、进程/宿主崩溃和恢复反例证明最多一个先行 claim、数据只在 claim 后打开、失败 claim 永久保留且索引代不回滚/分叉；
13. 选择性验证覆盖直接生产者和消费者，完整产品发布仍执行 HALPHA-ENG-002 的全部发布门；
14. 没有 Nx/Turborepo/Bazel、workspace 编排平台、私有包仓库、模型 SDK/agent framework/MCP 服务、向量库、实验数据库、调度器、产品兼容摘要、资格 bundle、第二构建身份或研究安全沙箱；研究变化仍按现有 BuildManifest 规则进入完整仓库来源判断；
15. 正式发布仍来自干净 commit，由唯一 `BuildManifest.build_digest` 绑定 HALPHA-ENG-002 要求的输入，完整仓库来源可追溯，DEMO/LIVE 使用同一产品制品和允许差异；
16. 研究、外部 AI 和按需工具没有交易写凭据、产品数据库写入、持久工作器、自动启动或产品同步依赖；研究 Python 是第三且最后一种依赖定义/锁身份，不限制从同一锁重建可删除实例；
17. 正向、负向和零候选证据引用的源码从耐久 Git ref 可达或包内含规范源码快照与摘要；删除 worktree/分支、squash 和垃圾回收后仍可重演；
18. 研究、AI 客户端或依赖损坏不会阻断既有产品构建、发布、启动、保护、核对或恢复；删除任一无消费者工作区、AI 客户端、venv、runs、可重建生成物或选择性验证规则不会丢失产品业务状态或形成第二事实权威。

# 8. Git 原生工作区与串行集成的选择依据【ENG-MONO-CMP-001-RAT】

在本契约边界内，Halpha 只有一个项目所有者、一个仓库、一个产品发布组和少量可独立工作包。Git branch/worktree 提供独立 checkout、完整历史、差异审查和失败丢弃，base-to-output 差异门提供路径约束，Git merge/PR 提供串行集成；DAG、稳定语义锚点与路径集合足以判断能否并行。增加 monorepo 编排平台不会减少产品运行复杂度，反而增加配置语言、缓存正确性、升级和诊断责任。

独立研究环境解决真实的科学依赖、Notebook 和产品运行依赖冲突，同时仍以文件证据交接并复用产品正式量化栈。外部 AI 通过同一 CLI/JSON 契约提高创作、筛选和复核吞吐，不需要 Halpha 集成模型运行时。Halpha 把项目开发者使用的 AI 视为不会作恶并会尽最大努力的可信开发者，同时承认它会理解错误、遗漏或产生缺陷；因此控制目标是以与错误成本相称的审查、schema、测试、重演、holdout、证据复核和产品内资格化减少错误影响，而不是为 `research` 单独构造敌对代码模型。

删除模型外 sandbox、父进程/worker、observation/intent、专用 IPC 和第二研究 venv，直接减少了平台资格、协议翻译、性能门、运行身份和长期串行维护面。固定 `ResearchStrategyHarness` 在同一研究环境中直接装载 study，仍由 NautilusTrader 统一数据推进、指标、撮合、成本、PnL 和报告。确认性暴露由单宿主小型文件根和短排他锁防止并发/崩溃重用，不增加服务、队列、数据库或持久 worker，且只串行准入，不阻断 discovery/validation 并行。只有实际失败和风险估算证明更强控制的预期收益高于其安装、运行、升级和退出成本时，才修订本 L3 重新评价；不采用成本投入明显高于风险价值的隔离。若实际数据证明选择性检查不可靠、集成排队长期成为主要瓶颈、两个以上 AI 客户端反复适配同一 CLI，或两个以上工作区重复维护同一能力，再比较更强工具；在此之前简单 Git、单一研究 venv、无状态 CLI、直接 harness、宿主文件锁与既有测试链的净复杂度最低。

# 9. 复杂度、退出与适用 L4 选择边界【ENG-MONO-CPLX-001】

本契约增加一种研究 Python 依赖定义/锁身份、每个 worktree 一套可删除研究 venv、工作区依赖图、路径所有权、外部 AI 的角色/预算边界、一个固定 harness、每次运行一个短生命周期进程、一个单宿主小型耐久 exposure root 和选择性验证规则；不增加 Halpha 自研或第三方研究 sandbox、父进程/worker、observation/intent、专用 IPC、第二研究 venv、模型 SDK、agent 服务、产品进程、数据库、持久工作器、授权路径、真实写链、产品发布组和通用平台。交易产品核心继续是一个 Python distribution；前端继续是一个同发布组构建单元；研究工作区和外部 AI 都不发布为 Halpha 产品。

适用 L4 应选择实际启用的最少工作区、AI 角色和工作包，并记录集成所有者、精确锁、AI 客户端/模型公开身份、非秘密协议修订、供应商遥测/保留/训练政策、允许上传的数据类别、研究 venv/sys.path/DLL 根、固定 harness 与 study 入口、单宿主 exposure root 的稳定路径/写入路径/锁/索引代/原子性/备份恢复、token/API/CPU/内存/墙钟/输入输出预算、组件、路径、DAG、选择性检查和重演证据。研究工作只可在不影响交易产品资源与开放责任时运行；资源竞争时停止或降低研究并发，不为此建设资源调度平台。L4 明确记录不采用 sandbox/launcher/IPC、driver/service/VM/image/distro、父进程/worker 或第二研究 venv。没有真实消费者的目录、角色或 exposure root 不创建；不能证明并行等待时间减少、故障/依赖分离增加或维护成本下降的边界应合并。

当工作区或 AI 集成需要独立版本承诺、Halpha 模型调用、跨会话持久编排、长期运行、独立数据库、产品认证、远程入口、单独发布或跨边界同步业务调用时，本契约的成本比较失效。开发者必须停止扩展，先比较删除、收缩、文件交接或按需外部工具是否足够；只有相应 FLOW/VIS/ARC 的重新触发条件成立后才可以建立新的 SYS/UX/ENG 候选。

## 9.1 上位设计重新触发条件【ENG-MONO-UP-001】

以下变化超出本契约边界，必须先修订并接受对应上位设计，不能由 L3/L4 局部放宽：

| 未来变化 | 必须先复核或修改 | 处理边界 |
|---|---|---|
| 受支持的产品研究应用、自动研究到计划交接或用户代码执行入口 | HALPHA-FLOW-001；若改变产品角色、长期要求用户编程或形成独立研究产品线，同时复核 HALPHA-VIS-001 | 未修订并接受上述设计前仍只允许本地按需工具，以及项目所有者最终选择后的文件证据交接 |
| Halpha 调用模型 API、保存供应商会话、跨会话持久 agent 编排或让产品运行同步依赖 AI | HALPHA-ARC-001 与 HALPHA-FLOW-001；若改变产品角色或形成通用 AI 能力，同时复核 HALPHA-VIS-001，并由 SYS/ENG/UX 承接 | 未完成上位设计前只允许外部 AI 按需调用无状态本地 CLI，Halpha 不持有 provider key |
| 新增产品持久进程、服务、数据库、发布组、远程认证入口、持久状态或同步业务调用 | HALPHA-ARC-001，并由相应 SYS/UX/ENG 承接 | 未满足 ARC 实证拆分条件时优先删除、收缩或保持文件交接 |
| 拟为研究新增安全 sandbox、独立镜像、第四种依赖/构建身份、持久守护或远程执行平台 | HALPHA-ENG-003；形成产品进程、服务、远程入口或同步依赖时同时复核 HALPHA-ARC-001 | 必须先用实际错误场景、错误成本和控制全生命周期成本证明净价值，并形成新的 L3 候选；当前不因 AI 作者身份限制完整数据或确认性研究 |
| 与 NautilusTrader 并行、同权或 fallback 的第二正式量化栈 | `CON-CMP-004` 与 `ARC-QLT-002` 已禁止以平行实现换取兼容 | 不得由本契约授权；整体替换单一正式栈时重新进行 L3/L4 组件资格化 |
| 自动判定多个数据源、修订、重导出或切片之间的等价关系 | HALPHA-DAT-001，并由 DAT 形成新的或修订既有 L3 | 当前只消费 DAT-qualified immutable `data_snapshot_ref` 与资格材料；ALP/ENG/L4 不定义 lineage 算法，关系不明时确认性能力 fail-closed |
| 研究 API、agent framework、MCP/远程工具服务、向量库、实验数据库、调度器、统一策略接口等组合成通用 AI/量化研究平台 | `CON-NGL-001`，并通常同时复核 HALPHA-VIS-001、HALPHA-FLOW-001 与 HALPHA-ARC-001 | 在上位范围被明确修改前属于非目标 |
| 研究或工具取得产品数据库写角色、LIVE 写凭据或真实动作能力，或研究输出自动修改正式策略、交易计划、资金范围或权限 | `CON-SEC-001`、适用 `CON-CAP-001` 至 `CON-CAP-006`、`CON-ADP-001`、HALPHA-FLOW-001 与 HALPHA-ARC-001，并由 ALP/TRADEPLAN/CAP/EXE/DAT/SYS/ENG 承接；正式策略变更回到 ALP-002/ALP-003，交易计划变更回到 TRADEPLAN 所有者 | 继续保持研究无写能力、人工选择、产品内重验和用户显式授权；不得自动晋升、自授权或把研究派生内容提升为事实 |
