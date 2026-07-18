# Halpha Monorepo 工作区与并行集成契约

**文档编号：** HALPHA-ENG-003  
**版本：** v0.3.0  
**文档状态：** ACCEPTED  
**层级：** L3  
**L3 类型：** DOMAIN  
**主要语义所有者：** ENG  
**所属实现模块：** 仓库工作区、构建输入图、验证与集成边界；不形成交易产品业务模块  
**语言版本：** zh-CN  
**批准人：** Halpha 项目所有者  
**接受时间：** 2026-07-18T09:59:00+08:00  
**替代版本：** 无（首次接受）  
**上位文档或条款：** HALPHA-FLOW-001 v1.9.0；HALPHA-ARC-001 v1.9.0；HALPHA-ENG-001 v1.6.0  
**直接依赖：** HALPHA-ENG-002 v0.8.0；BuildManifest 的证据摘要与 eligibility 语义受 HALPHA-ALP-002 v0.5.0 约束；HALPHA-ALP-003 v0.3.0 提供 AI 研究任务、运行请求/回执、研究运行清单与研究证据包语义；运行实体、模块、进程、配置和恢复边界服从 HALPHA-SYS-001 v1.6.0 与 HALPHA-SYS-002 v0.9.0  
**直接消费者：** HALPHA-ALP-003 v0.3.0；由 `HALPHA-PLAN-001` 授权的独立源码工作包及其集成门  
**适用纵向约束：** HALPHA-SYS-001 v1.6.0  
**本文档负责：** monorepo 内交易产品、前端、研究和按需工具的工作区边界；外部 AI 通过同一研究 CLI/文件协议工作的模型外沙箱、可见性、路径、预算与失败隔离；Git 原生并行与唯一集成方式；依赖定义、允许依赖方向、路径所有权、最小工作包、共享路径串行集成、选择性开发反馈和复杂度退出条件  
**本文档不负责：** 重定义研究判据或领域业务语义、模块或运行实体；规定 L4 建设授权、工作包授权、AI 客户端/模型/提示词、沙箱提供者/配置、精确依赖版本、锁摘要、目录状态或资格证据；改变 HALPHA-ENG-002 的交易产品构建、DEMO/LIVE 等价和发布要求；新增 Halpha 自研 sandbox、模型 SDK/agent framework、产品进程、数据库产品、持久工作器、真实写链、消息总线、独立产品发布组、私有包仓库或通用开发平台  

---

# 0. 设计结论【ENG-MONO-SUM-001】

Halpha 采用“宽源码边界、窄运行时边界”的 monorepo：交易产品、前端、研究和按需工程工具可以拥有不同目录、依赖环境、测试目标和构建输入图，但交易产品仍保持 HALPHA-ENG-002 与 HALPHA-SYS-002 定义的单一产品发布组、模块化单体、两种产品进程角色、一个数据库产品和每环境一条场所写链。

并行开发通过稳定语义范围、路径所有权、公开契约、工作包 DAG、选择性反馈和串行集成门取得，不把源码边界自动升级为服务、数据库、持久工作器或独立发布。开发授权、集成资格和发布资格是三个不同判断：一个工作包可以被适用 L4 授权独立开发，但在依赖、共享路径和验收未满足前不能集成；集成完成也不能替代完整产品发布门。

长期并行工具只采用 Git branch/worktree 提供独立 checkout/分支和 Git 的单一串行 merge/PR 集成；worktree 本身不强制路径所有权，路径门必须用基线与输出 commit 的差异验证。不增加 monorepo 编排器、远程构建缓存、私有包仓库或第二 CI。GitHub Actions 只能复跑仓库内同一组命令，不拥有另一套构建、资格或发布语义。工作包能否并行由 DAG 无依赖、稳定语义锚点不重叠且独占路径不重叠推导，不维护成对 `may_run_in_parallel_with` 清单。

默认只允许三种依赖定义与锁身份：交易产品 Python、研究 Python 和现有前端 Node；这不是最多三个物理环境。不同 worktree 可以从同一锁建立可删除实例，但每次运行必须证明解释器、锁摘要和 `halpha_research` 源码来自当前 worktree，不共享可变 editable install。完整数据/holdout 研究还必须从同一研究锁建立父进程与 worker 两个可删除物理 venv：父进程实例安装 `halpha_research` 与完整研究闭包；worker 实例只安装锁内声明的第三方子集和冻结 worker 源码，不安装、挂载或加入 `sys.path` 的 runner/harness/evidence 源码。两个实例不形成新锁身份，但各自解释器、安装闭包、`sys.path`、DLL 搜索根和摘要必须可验证。短生命周期工具复用其中适用定义或标准系统工具。新增第四种依赖定义、多个核心 Python distribution、私有包仓库、第二构建平台或独立发布流水线，必须有多个真实消费者和测得的冲突、隔离或发布问题，并证明总维护成本下降；否则不支持。

研究环境使用标准库 `venv`、一个 `pyproject.toml` 直接依赖来源和一个由 pip-tools 生成的完整 hash lock；不重复维护 runtime/dev 两套锁，也不修改产品 Python lock。研究组件身份和用途由 HALPHA-ALP-003 唯一选择；本文件只拥有独立环境、依赖声明、完整锁、安装与资格化边界。与产品重叠的组件由适用 L4 绑定到产品已资格化的同一兼容组合，研究专属组件只存在于研究环境；pytest 与 Hypothesis 承担研究契约和性质验证。精确版本、lock、workflow 和命令由适用 L4 固定。

外部 AI 仍是 CON/ENG 定义的开发者工具，不是 Halpha 运行实体。它在独立 Git worktree 内通过人也能调用的 `python -m halpha_research` 和 Pydantic JSON Schema 工作；Halpha 不反向调用模型 API，不保存供应商会话状态，也不把 AI 客户端、模型 SDK 或 agent framework 放入产品/研究锁。AI 编写的研究源码是未受信输入，只有模型之外、由外部 AI 客户端或宿主提供并通过适用 L4 恶意 fixture 资格门 的成熟沙箱/OS 边界才可执行完整数据或 holdout 运行；schema、venv、worktree、静态扫描与普通 `subprocess` 都不构成该安全边界。即使存在 OS 沙箱，未受信 study 也不得与可信 runner/NautilusTrader 处于同一解释器或能力域：可信父进程从不 import worker，独占数据、时钟、固定 harness、引擎、报告和证据写入；沙箱 worker 只通过有界 framed stdio 接收 point-in-time observation 并返回 research intent。AI 不可用、会话丢失或供应商升级只影响创作效率，不能阻断同一固定请求由项目所有者恢复性重演，更不能影响交易产品。

不同 AI 研究角色通过新会话、新进程、只读输入、独占输出路径和模型外强制边界取得程序性隔离，不建设多代理运行平台。逐事件 observation/intent transcript 只留在模型不可读的本地完整 payload；外部模型只取得安全聚合视图和规范回执。精确客户端/模型、非秘密提示协议摘要、供应商遥测/保留/训练政策、沙箱提供者与配置摘要、父进程/worker 运行身份、ACL/挂载、IPC framing/schema/超时、网络、允许命令、进程树与资源边界、完整数据是否可见、token/API/墙钟/计算预算及实际成本属于适用 L4 和研究证据来源记录。

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
  studies/                          # 每项候选的未受信短生命周期 worker 源码与固定配置
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

研究政策、AI 研究任务、用例、请求/回执、`PointInTimeObservation`、`ResearchIntent`、角色材料、运行清单、候选全量/确认性暴露索引、AI 审查视图和证据包的 Pydantic 模型及其语义由 HALPHA-ALP-003 唯一拥有；本文件只要求机器 schema 从该模型生成，不同时维护手写 `schemas/`、数据类和 JSON Schema 三份定义。只有研究工作区一个实现消费者时不建立仓库级共享 contract 包；未来出现第二个真实源码消费者、双方不能由同一工作区拥有且复制漂移已经可测时，才可由相应语义所有者另行设计共享契约。研究模型不得包含正式策略规则、交易计划状态、资金或权限判断、动作写入、产品 DTO 的手工副本，也不得成为绕过拥有领域的通用 `common` 包；`ResearchIntent` 只供固定研究 harness 映射仿真订单，不是 `ExecutionAction` 或产品命令。

`pyproject.toml` 是研究直接依赖和包元数据的唯一手写来源，`requirements.lock` 是可删除重建的生成物；不得再用 `requirements.in`、Notebook 安装单元或根产品项目文件声明同一依赖。`campaigns/` 只保存已提交、无秘密且适合 Git 的研究政策、任务、用例/请求、候选全量、确认性暴露索引的证据快照、角色材料和冻结选择；各 worktree 的 Git 快照不是确认性运行时准入权威，不保存完整聊天、模型私有状态、供应商会话或原始私有数据。`runs/` 与原始/缓存数据不进入 Git；`evidence/` 只保留仍被经济判断、晋升或反例引用且体量适合仓库的小型冻结包，大型可重建输入只保存来源和摘要。

不适合 Git 但仍被决定引用的大型证据包不得转移到 `runs/`。适用 L4 必须为它固定一个仓库外耐久文件根、稳定存储标识、相对路径、完整性摘要、保留期、备份/恢复和按来源重新取得后的复验方式；未通过这些条件时只能保持未引用材料。该文件根不是新工作区、产品存储、数据库、服务或发布组。

确认性准入另有一个单一宿主、单一文件系统、位于所有 worktree 与 `runs/` 之外的小型耐久 `confirmation_exposure_root`。它不是证据 payload 根、数据库、服务或 campaign 工作目录；只有可信父进程拥有宿主级排他锁和写权限，worker、模型与普通工作包均无访问权。适用 L4 必须固定稳定标识、解析路径、SID/ACL、锁/刷新/同文件系统原子替换语义、不可变索引代与当前代摘要、备份/恢复、损坏/回滚/分叉检查和卸载后处理；根不可用或最新代不能证明时确认性能力 fail-closed。

# 2. 依赖方向与路径所有权【ENG-MONO-DEP-001】

## 2.1 允许依赖方向【ENG-MONO-DEP-001-REQ】

稳定依赖方向为：

```text
交易产品入口 → 交易产品公开应用边界 → 业务模块与端口
前端          → 唯一 OpenAPI 生成客户端 → 交易产品 API
研究工作区    → 自有 Pydantic 文件模型、可信父进程/固定研究 harness、带摘要数据、允许的产品纯逻辑公开接口
未受信 worker  → point-in-time observation → bounded research intent → 可信父进程
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
- 研究 policy/schema/runner/固定 harness/gate/evidence、observation/intent 协议、研究锁、confirmation exposure 索引 schema/证据快照，以及宿主级 exposure root 的唯一父进程写入实现；
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

- 创作阶段只取得当前工作包需要的适用规范、CLI/schema、AI 可见审查视图、候选独占 worker 源码路径、已有失败材料和合成/脱敏 fixture；写入限制在工作包 `owned_paths`。AI 源码完成不因文件副作用自动执行，静态导入/危险 API 检查只作为防错门；
- 确定性 `run` 由模型上下文之外的可信父进程拥有。父进程从不 import、`exec` 或在同一解释器调用 worker，独占解析数据根/holdout、时钟、NautilusTrader 引擎、固定 `ResearchStrategyHarness`、指标与组合/订单/成本状态、确认性计数、报告器和 canonical artifact writer；父进程自身不位于未受信 worker 的能力域；
- 每次运行只启动一个新的模型外沙箱 worker。worker 可见根只包含冻结 worker 源码、同一研究锁所需的只读运行时和新临时根，不挂载 runner/harness/evidence 源码、数据/holdout 文件、产品配置或输出根；可信父进程按事件发送 schema 校验的 `PointInTimeObservation`，worker 只返回同 sequence 的有界 `ResearchIntent`。worker stdout 只允许 framed 协议，stderr、非协议 stdout 和完整 transcript 由可信 launcher 捕获到模型不可读的本地完整 payload，不流式转发；
- discovery/validation/stress/holdout 均使用同一父进程—worker 能力边界。沙箱拒绝供应商网络、环境秘密、未授权文件/目录、输出外写与子进程，并在消息或资源预算达到时终止 worker 及适用进程树；外部 AI 只取得父进程生成的无原始数据与秘密规范回执和 `ai_review_view.json`，不取得逐事件 observation/intent；
- holdout/复现角色使用新 worktree 或只读 checkout、新 worker 沙箱进程、固定父进程/harness/worker 源码/请求和单一新输出根；但 worktree 内索引只能预检。可信父进程必须在读取任何 holdout 数据字节前，解析政策允许的 DAT-qualified immutable `data_snapshot_ref`，核对 DAT qualification evidence、snapshot digest 与规范 UTC 半开区间；AI、worker 或请求不得创建、改写或用路径、名称、digest 代替该引用，缺失、变化、修订/重导出关系不明、区间不可比较或核对不一致即拒绝。随后父进程才可通过单一宿主级 `confirmation_exposure_root` 的排他锁验证最新索引代、跨全部决策族查询相同引用的区间重叠/包含，并耐久原子写入包含 `confirmation_exposure_key`、`data_snapshot_ref`、资格证据引用、snapshot digest 与规范 UTC 半开区间的不可逆 `EXPOSURE_STARTED`；锁、摘要、资格核对或写入不确定即不打开 holdout，claim 后失败或崩溃仍永久算暴露。模型上下文不取得行级 holdout、原始日志、transcript、完整 payload 或 exposure root，也不能修改研究用例、任务清单、runner/harness/gate/schema、确认性暴露证据快照或共享锁；
- 最终选择角色只读通过完整性检查的 `ai_review_view.json`、允许的冻结 worker 源码、候选全量与确认性暴露索引，只写选择材料；它不能读取本地行级 Parquet/HTML/日志/transcript、调用新搜索、修改硬门或进入产品共享路径。

适用 L4 必须为每个启用角色固定 AI 客户端公开身份、模型标签可获得程度、非秘密协议修订、供应商遥测/保留/训练政策与允许上传的数据类别、目标 Windows edition/SKU/build 与虚拟化前提、具体 sandbox/launcher 名称、公开 launch API/CLI 和双向 IPC transport、提供者/版本/hash/来源/许可证/补丁与 EOL/卸载责任，以及是否安装 driver、service、VM、image 或 distro；任一新增身份必须先按第 9.1 节分类，不能把它称为已有宿主能力。还必须固定 worktree、模型/可信父进程/worker 各自解析后的 read/write roots，父/worker 物理 venv 的解释器、同一 lock 身份、安装闭包、`sys.path` 与 DLL 搜索根，沙箱配置摘要、父进程与 worker 的 SID/用户、ACL/挂载、网络策略、允许命令、进程树终止、`ResearchStrategyHarness` 与 observation/intent schema 摘要，以及 IPC 长度头格式、先验长度上限、sequence、partial frame/EOF/BrokenPipe、并发有界 stderr 排空、超限前内存分配、超时和 Windows Job Object 嵌套/kill-tree/零残留语义。确认性运行还必须固定政策允许的 DAT-qualified immutable `data_snapshot_ref`、DAT qualification evidence、snapshot digest、规范 UTC 半开区间和缺失/变化/关系不明时的拒绝条件，以及单一宿主/exposure root 稳定标识与解析路径、唯一 writer SID、排他锁 API、索引代 schema/摘要链、flush/fsync 等价、同文件系统原子 replace、claim/outcome 状态机、备份恢复和损坏/回滚/分叉演练。允许字段/profile、数据与 transcript 可见范围、token/API/墙钟/CPU/内存/逐消息与总输入输出预算和停止结果也必须固定。AI 客户端与沙箱工具不进入研究 lock，完整提示、聊天记忆、模型私有状态和供应商会话不作为核心重演输入；能核对的创作来源与实际成本只作为 ALP-003 定义的非权威来源材料。

CLI 只接受 ALP-003 的 Pydantic 规范 JSON 和仓库相对路径。路径经 Windows 大小写规范化并解析 symlink、junction/reparse point 后必须留在允许根；请求不得指定 shell、任意 executable/cwd/environment、动态 import、URL 下载、秘密、自由文本 intent、产品命令、输出根、exposure root 或锁路径，也不得创建、改写或用路径、名称、digest 代替政策允许的 `data_snapshot_ref`。可信父进程只用固定模块和参数数组要求资格化沙箱启动固定 worker 入口，禁止 `shell=True`、`eval`、字符串拼接执行或把 worker 导入父进程。父进程必须拒绝额外/未分帧/重复/乱序/超大/超时、非有限数值、未知字段/profile 和越界 intent；worker 不得取得原始数据路径、未来事件、引擎对象、确认性计数、exposure root 或 artifact writer。请求校验不约束 AI 源码内部行为；适用 L4 资格门必须用实际沙箱与恶意 worker fixture 证明 import/monkeypatch 父进程、越权文件/目录、秘密、网络、shell/子进程、输出外写、原始数据回显、未来访问、协议注入和资源越界被模型之外真实阻断或由父进程 fail-closed。holdout 的普通 schema 预检和请求自报路径、名称或 digest 不能代替可信父进程对 `data_snapshot_ref`、DAT qualification evidence、snapshot digest、规范 UTC 半开区间的核对、锁内权威查询与 claim 写入；只有父进程完成资格核对并耐久写入 claim 后才可打开数据。预算耗尽、协议冲突或任何越权返回非零状态与规范回执，终止 worker 及适用进程树并保留已完成范围，不自动增加预算、重试、后台恢复或转用另一个 AI/运行器。

Halpha 不向模型供应商发起网络请求。外部 AI 的供应商网络只用于客户端自身创作，不能携带原始私有数据、本地完整证据 payload、产品配置、秘密存储引用、数据库连接、DEMO/LIVE 凭据或产品运行日志；无法证明不上传时只允许公开且许可允许模型处理、合成或脱敏材料。最低复杂度优先复用外部 AI 客户端或宿主已有且资格通过的成熟沙箱，Halpha 不自研 Python sandbox。没有合格能力时只允许上述安全材料做 discovery，确认性 holdout、完整数据角色和最终候选资格保持未启用，也不退化为逐次人工代跑；只有真实消费者证明必要时，适用 L4 才比较按需 OS sandbox/container 与继续停用的全生命周期成本，不建立常驻平台。AI 不可用时项目所有者只可恢复性重演已经固定的请求，研究也可以停止或等待，交易产品不受影响。

## 3.3 DAG 与三个资格判断【ENG-MONO-WRK-002-REQ】

工作包依赖必须形成无环有向图。只有边界清楚、输入可构造、输出可独立验证、没有相互依赖且不争夺同一稳定语义锚点或路径的工作包才自动具备并行资格；其余工作保持串行。

单个研究活动的 discovery/validation、worker 源码与独占证据路径可以按上述规则跨 worktree 并行；确认性 holdout 准入不能由 Git 路径不重叠推导为并行。所有 worktree 必须指向同一宿主 exposure root，并只由可信父进程在短排他锁内完成查询与不可逆 claim。不同 `data_snapshot_ref` 或互不重叠区间在 claim 耐久写入后可按资源边界并行执行；远程宿主、分叉 exposure root 或无法共享同一锁的运行不具备确认性资格。若以后需要跨宿主确认性并发，必须先重新设计一致性边界，不能在本文件下引入服务或数据库。

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
- Python 标准库 `argparse`、`pathlib`、`subprocess`、`json` 与 `hashlib` 承担研究 CLI、路径收敛、可信父进程要求沙箱启动固定 worker、framed stdio、规范 JSON 与摘要；Pydantic 生成同一文件及 observation/intent 协议 schema；
- pytest、Hypothesis、现有文档校验器和架构/契约测试提供本地反馈；
- 现有 GitHub Actions 只在干净 checkout 复跑同一锁安装与命令，不能维护另一套成功标准。

以上 Python 工具都不承担未受信源码安全隔离，普通新进程也不能阻止同一能力域的污染。模型外沙箱优先复用外部 AI 客户端或宿主已经提供的成熟强制能力，并由适用 L4 绑定其身份与配置；可信父进程—未受信 worker 的 stdio 协议进一步隔离引擎与 canonical writer。二者都是按需研究执行前提，不是第四种 Python 依赖定义、产品进程、服务或 Halpha 自研 sandbox。现有能力未通过适用 L4 资格门时保持完整数据与确认性研究禁用。若以后必须新增 OS sandbox/container，先比较安装、启动、镜像/补丁、资源、退出和平台差异成本；只有不增加独立镜像/依赖/构建身份时才可在本契约下由 L4 选择，出现第四种身份、持久守护或远程服务时必须先修订本 L3，并在改变产品拓扑时复核 ARC。

Nx、Turborepo、Bazel、Pants、uv/Poetry workspace 编排、私有 Python 包仓库、远程构建 cache、模型供应商 SDK、PydanticAI、LangChain/LangGraph、AutoGen、CrewAI、Semantic Kernel、MCP SDK/server、向量库/RAG、MLflow、DVC、Airflow、Prefect、第二 CI/构建平台和通用 monorepo graph 服务均不进入默认基线。单一项目所有者、按需外部 AI、JSON/CLI 文件交接和受限并发不足以抵消这些平台的供应商 API、工具循环、状态、重试、追踪、配置、升级、诊断和退出成本，也不能提高研究证据权威。

只有至少两个真实 AI 客户端长期因 CLI/schema 使用产生可测重复适配或错误，才比较由同一 Pydantic 模型生成、只走 stdio、无状态且不增加业务命令的薄 MCP adapter，仍不先建 HTTP 服务。只有真实出现跨会话持久编排、无人值守多步恢复或多个独立 agent 共享状态，且其收益超过新状态与运维成本，才重新评价 agent framework；形成受支持产品入口、常驻或远程服务时先按第 9.1 节复核 FLOW/VIS/ARC/SYS/UX。

# 5. 迁移、运行时与凭据隔离【ENG-MONO-ISO-001】

## 5.1 单一迁移线【ENG-MONO-ISO-001-REQ】

产品数据库只有一个 Alembic head 和一条按序集成的迁移线。工作包可以在独占测试 fixture 中表达所需 schema 候选，但只有集成所有者可以创建、排序和合并正式迁移。迁移不得引用研究包、Notebook 或研究依赖，也不得用平行表、双写或兼容 reader 掩盖未完成语义裁决。

两个工作包都需要 schema 变化时按依赖和具体 schema 语义锚点的所有者确定顺序；无法证明旧数据、开放责任和回退可解释时阻断集成。迁移失败继续遵守 HALPHA-ENG-002 的备份、恢复或前向修复边界。

## 5.2 研究和工具隔离【ENG-MONO-ISO-002-REQ】

研究、外部 AI 与普通工具默认只有无交易写能力的本地身份。它们不得取得 LIVE/DEMO 场所写凭据、产品数据库写角色、App/Executor 长期秘密或可调用场所写端口的配置。需要产品材料时使用带来源和摘要的只读导出；外部 AI 默认只看公开且允许模型处理、合成/脱敏 fixture、`ai_review_view.json` 与无秘密机器回执。完整数据、holdout 和本地完整证据 payload 只由第 3.2 节资格通过的可信父进程读取；沙箱 worker 只取得 point-in-time observation，模型上下文只取得聚合视图，二者都不取得数据文件路径或完整 payload。需要对真实外部系统资格化的工具必须由适用 L4 明确限定凭据类别、动作范围、退出证据和与产品运行的时间隔离。

研究、外部 AI 和普通工具只能按需启动。唯一允许跨进程终止保留的研究运行状态，是 HALPHA-ALP-003 要求写入 `confirmation_exposure_root` 的不可逆确认性暴露 claim 与索引代；它们是小型研究资格证据，不是产品业务状态、持久 worker cursor/due/退避或自动恢复责任。除此之外，终止后不得留下其他持久 claim、cursor、due、退避、自动恢复责任或产品业务状态。它们不得成为 App、Executor、保护、核对、停止、恢复或发布的同步依赖。研究消耗资源或供应商成本时，交易产品和项目所有者预算优先；达到预算或不能证明资源隔离时停止研究任务。

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
| 模型外沙箱或其 SID/ACL/挂载/网络/进程树/资源边界不能实际证明 | 只允许公开且许可允许模型处理、合成/脱敏材料做 discovery；完整数据、确认性 holdout 与最终候选资格保持禁用，不逐次人工代跑 |
| AI/worker 源码尝试越权文件/目录、runner/harness/数据/holdout 路径、环境秘密、网络、子进程、输出外写、原始数据回显或共享材料改写 | 沙箱真实阻断、终止 worker 与适用进程树并留下无秘密 violation；静态扫描或提示承诺不能放行 |
| 可信父进程 import/同解释器执行 worker，或 worker 尝试 monkeypatch/import 父进程/NautilusTrader、读取未来事件/确认性计数 | 运行资格失败并保持完整数据/确认性能力禁用；必须恢复父进程—worker 能力边界后重新资格化 |
| worker 返回额外/未分帧/重复/乱序/超大/超时、未知字段/profile、非有限数值或越界 intent | 父进程 fail-closed、终止 worker、保留规范 violation；不得把部分或修补后的输出写成 canonical 成功结果 |
| holdout 准入无法取得单一 exposure root 的锁，最新索引代/摘要不明，原子写入/刷新不确定，或根丢失、回滚、分叉、损坏 | 父进程不得打开 holdout；确认性能力禁用，不能改用 worktree Git 副本、另一根或人工口头记录 |
| 请求、AI 或 worker 创建/改写 `data_snapshot_ref`，以路径、名称或 digest 代替政策允许引用，资格材料缺失或变化，修订/重导出关系不明，规范 UTC 半开区间不可比较，或请求与 DAT qualification evidence 不一致 | 父进程在打开 holdout 前拒绝；新的或变化引用只有先取得 DAT 资格材料并由适用 L4 与研究政策显式选择后才能准入，关系不明时确认性能力 fail-closed |
| 父进程在不可逆 claim 后失败、被 kill 或宿主崩溃，或 outcome 更新失败 | 原 claim 永久按暴露保留；恢复后只可写引用原 claim 的失败/outcome 新索引代，不得删除、重试为新确认或回滚当前代 |
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
4. 研究 `pyproject.toml` 能生成唯一完整 hash lock，干净 `venv` 安装、`pip check`、许可证闭包和删除后重建通过，且不改变产品 lock；不同 worktree 的可删除 venv 都验证解释器、锁摘要和实际加载源码来自本 worktree，不共享可变 editable install；完整数据角色的父进程/worker 两个物理 venv 来自同一锁，分别证明安装闭包、`sys.path`、DLL 搜索根和摘要，worker 环境不安装/挂载 runner、harness 或 evidence 源码；
5. HALPHA-ALP-003 选择的研究组件在固定锁下完成公开导入与 CLI 路径验证；pytest/Hypothesis 覆盖研究政策子集、数据、摘要、路径逃逸、extra fields、命令注入、动态 import、预算和重复运行反例；统计 gate 还以已知 null/正/负样例证明 `confirmation_claim_type` 生效：BH/BY set-FDR 只能冻结完整集合级材料，事后抽取的集合成员不能成为个体最终候选，预选单假设全局 α 或预声明有限族 Bonferroni strong-FWER 才能形成个体确认资格；这些应用级检查不替代执行沙箱；
6. 人与 AI 用同一请求和 CLI 得到相同请求摘要与核心结果；外部 AI 不能产生另一条运行/gate/freeze/晋升入口，AI 不可用或会话丢失时项目所有者只作固定请求的恢复性重演；
7. 可信父进程从不 import/同解释器执行 worker，独占数据/holdout、时钟、固定 harness、NautilusTrader 引擎、指标与组合/订单/成本状态、确认性计数、报告器和 canonical writer；worker mount 不含这些源码或数据根，只能逐事件接收 point-in-time observation 并返回有界 intent；
8. 适用 L4 的沙箱资格门在固定 Windows edition/SKU/build 与虚拟化前提上，以所选 sandbox/launcher 的公开 launch API/CLI 和真实双向 IPC transport 完成重复启动、管道往返、partial frame/EOF/BrokenPipe、有界 stderr 排空、Job Object 嵌套/kill-tree、预算终止和零残留 smoke；提供者版本/hash/来源/许可证/补丁/EOL/卸载责任及 driver/service/VM/image/distro 增量均有证据，新增第四身份时先触发第 9.1 节而非继续资格化。实际沙箱对未授权文件读取/目录枚举、父进程/runner/harness/数据/holdout/exposure 路径、秘密/环境、网络、shell/子进程、junction/symlink、输出外写、原始数据回显、共享材料改写和 CPU/内存/墙钟越界恶意 fixture 均真实阻断并终止 worker 与适用进程树；monkeypatch/import、未来访问、额外/未分帧/乱序/超大/超时/未知 intent fixture 由能力边界或父进程 fail-closed；静态扫描、venv、新进程和请求 schema 不被当作该证据；
9. 提案、证伪、holdout/复现与最终选择角色在新会话/进程和强制 read/write roots 中运行；模型只读 `ai_review_view.json`、允许源码与索引，本地行级 Parquet/HTML/日志/transcript/完整 payload、holdout 和秘密越权被阻断并使受影响研究失去资格；供应商遥测、保留/训练政策和允许上传数据类别有实证记录；
10. token/API/墙钟/CPU/内存/逐消息与总输入输出预算达到时请求停止、worker 与整个适用进程树终止并留下规范回执，不自动扩额、后台重试、切换供应商或创建持久责任；
11. 每个并行工作包只有最小必填字段、一个或多个 `{owner, anchor}` 稳定语义范围和互不重叠的独占路径；同 owner 不同 anchor 可以并行，同 anchor 必须串行，并行关系不依赖人工成对清单；discovery/validation 可跨 worktree 并行，但 confirmation admission 必须经单一宿主 exposure root 的短排他锁；
12. 共享路径只有一个集成所有者，正式迁移只有一个 Alembic head，生成输出只有一个来源；runner/harness/gate、Pydantic schema、observation/intent/exposure-index 协议、研究锁与 evidence 由共享集成所有者串行修改，不由各 AI 研究用例复制或重置；运行时 exposure root 只有可信父进程 writer，worktree Git 快照、worker 和 AI 无写权；可信父进程只解析政策允许的 DAT-qualified immutable `data_snapshot_ref` 并核对 DAT qualification evidence、snapshot digest 与规范 UTC 半开区间，请求不得创建或改写引用；缺失、变化、修订/重导出关系不明、区间不可比较或请求不一致均在打开 holdout 前失败；并发双任务、旧 worktree、锁竞争、partial write、kill-before-result、进程/宿主崩溃和恢复反例证明最多一个先行 claim、数据只在 claim 后打开、失败 claim 永久保留且索引代不回滚/分叉；
13. 选择性验证覆盖直接生产者和消费者，完整产品发布仍执行 HALPHA-ENG-002 的全部发布门；
14. 没有 Nx/Turborepo/Bazel、workspace 编排平台、私有包仓库、模型 SDK/agent framework/MCP 服务、向量库、实验数据库、调度器、产品兼容摘要、资格 bundle 或第二构建身份；研究变化仍按现有 BuildManifest 规则进入完整仓库来源判断；模型外沙箱与短生命周期 worker 仅作为按需外部执行前提，不形成产品进程或 Halpha 平台；
15. 正式发布仍来自干净 commit，由唯一 `BuildManifest.build_digest` 绑定 HALPHA-ENG-002 要求的输入，完整仓库来源可追溯，DEMO/LIVE 使用同一产品制品和允许差异；
16. 研究、外部 AI 和按需工具没有交易写凭据、产品数据库写入、持久工作器、自动启动或产品同步依赖；研究 Python 是第三且最后一种依赖定义/锁身份，不限制从同一锁重建可删除实例；
17. 正向、负向和零候选证据引用的源码从耐久 Git ref 可达或包内含规范源码快照与摘要；删除 worktree/分支、squash 和垃圾回收后仍可重演；
18. 研究、AI 客户端、沙箱或依赖损坏不会阻断既有产品构建、发布、启动、保护、核对或恢复；删除任一无消费者工作区、AI 客户端、沙箱配置、venv、runs、可重建生成物或选择性验证规则不会丢失产品业务状态或形成第二事实权威。

# 8. Git 原生工作区与串行集成的选择依据【ENG-MONO-CMP-001-RAT】

在本契约边界内，Halpha 只有一个项目所有者、一个仓库、一个产品发布组和少量可独立工作包。Git branch/worktree 提供独立 checkout、完整历史、差异审查和失败丢弃，base-to-output 差异门提供路径约束，Git merge/PR 提供串行集成；DAG、稳定语义锚点与路径集合足以判断能否并行。增加 monorepo 编排平台不会减少产品运行复杂度，反而增加配置语言、缓存正确性、升级和诊断责任。

独立研究环境解决真实的科学依赖、Notebook 和产品运行依赖冲突，同时仍以文件证据交接并复用产品正式量化栈。外部 AI 通过同一 CLI/JSON 契约提高创作、筛选和复核吞吐，不需要 Halpha 集成模型运行时；但 AI 源码只有在模型外沙箱实证通过、且与可信父进程/引擎形成能力边界时才可自主处理完整数据和 holdout。最低复杂度先复用客户端/宿主既有成熟强制边界；Windows 上是否存在同时满足隔离、双向 IPC、同一锁身份和零新增服务/镜像的成熟组合必须由适用 L4 资格证据实证，不能由文档假定；资格失败就停止确认性能力，不以 Halpha 自研 sandbox、逐次人工代跑或虚假隔离换取进度。observation/intent 是需要维护字段、profile、订单映射、性能预算与等价性黄金测试的窄研究策略协议，不只是两个 Pydantic 消息；因此初始只资格化一个中低频方向族和最少 profile，字段/intent 类型持续扩张、IPC 增量超限或与直接 NautilusTrader harness 不等价时收缩或重审 L3。确认性暴露由单宿主小型文件根和短排他锁防止并发/崩溃重用，不增加服务、队列、数据库或持久 worker，且只串行准入，不阻断 discovery/validation 并行。研究仍只带来同一研究 lock 的可删除父/worker venv、按需沙箱配置和小型 exposure root，不增加产品进程、数据库、迁移、凭据、模型 SDK 或发布。若实际数据证明选择性检查不可靠、集成排队长期成为主要瓶颈、两个以上 AI 客户端反复适配同一 CLI，或两个以上工作区重复维护同一能力，再比较更强工具；在此之前简单 Git、无状态 CLI、资格化外部沙箱、受限 stdio、宿主文件锁与既有测试链的净复杂度最低。

# 9. 复杂度、退出与适用 L4 选择边界【ENG-MONO-CPLX-001】

本契约增加一种研究 Python 依赖定义/锁身份、从同一锁建立的两个可删除物理 venv、工作区依赖图、路径所有权、外部 AI 的角色可见性/预算边界、一个按需模型外沙箱资格前提、一个固定可信 harness、一个受上限约束的窄 observation/intent 协议、每次运行一个短生命周期 worker、一个单宿主小型耐久 exposure root 和选择性验证规则；它通过只资格化单一初始方向、优先复用既有成熟沙箱且资格失败即停用，不增加 Halpha 自研 sandbox、模型 SDK、agent 服务、产品进程、数据库、持久工作器、授权路径、真实写链、产品发布组和通用平台来限制复杂度。交易产品核心继续是一个 Python distribution；前端继续是一个同发布组构建单元；研究工作区、外部 AI、可信父进程与 worker 沙箱都不发布为 Halpha 产品。

适用 L4 应选择实际启用的最少工作区、AI 角色和工作包，按机器与资源隔离证据设置低并发上限，并记录集成所有者、精确锁、AI 客户端/模型公开身份、非秘密协议修订、供应商遥测/保留/训练政策、目标 Windows SKU/build/虚拟化前提、sandbox/launcher/IPC transport 的来源/版本/hash/许可证/补丁/EOL/卸载与 driver/service/VM/image/distro 影响、可信父进程与 worker 的 SID/用户、ACL/挂载、网络、允许命令、进程树终止、模型/父进程/worker 各自 read/write roots 和物理 venv/sys.path/DLL 根、固定 harness 与 observation/intent schema/摘要/framing/sequence/大小/超时/字段和类型上限/性能与等价性门、单宿主 exposure root 的稳定路径/writer/锁/索引代/原子性/备份恢复、数据/transcript/完整 payload 可见性、token/API/CPU/内存/墙钟/输入输出预算、组件、路径、DAG、选择性检查和恶意 fixture 证据。研究工作只可在不影响交易产品资源与开放责任时运行；同一宿主不能证明资源隔离时，LIVE_WRITE 期间停止研究，不为此建设资源调度平台。没有真实消费者的目录、角色、sandbox 配置或 exposure root 不创建；不能证明并行等待时间减少、故障/依赖隔离增加或维护成本下降的边界应合并。

当工作区或 AI 集成需要独立版本承诺、Halpha 模型调用、跨会话持久编排、长期运行、独立数据库、产品认证、远程入口、单独发布或跨边界同步业务调用时，本契约的成本比较失效。开发者必须停止扩展，先比较删除、收缩、文件交接或按需外部工具是否足够；只有相应 FLOW/VIS/ARC 的重新触发条件成立后才可以建立新的 SYS/UX/ENG 候选。

## 9.1 上位设计重新触发条件【ENG-MONO-UP-001】

以下变化超出本契约边界，必须先修订并接受对应上位设计，不能由 L3/L4 局部放宽：

| 未来变化 | 必须先复核或修改 | 处理边界 |
|---|---|---|
| 受支持的产品研究应用、自动研究到计划交接或用户代码执行入口 | HALPHA-FLOW-001；若改变产品角色、长期要求用户编程或形成独立研究产品线，同时复核 HALPHA-VIS-001 | 未修订并接受上述设计前仍只允许本地按需工具，以及项目所有者最终选择后的文件证据交接 |
| Halpha 调用模型 API、保存供应商会话、跨会话持久 agent 编排或让产品运行同步依赖 AI | HALPHA-ARC-001 与 HALPHA-FLOW-001；若改变产品角色或形成通用 AI 能力，同时复核 HALPHA-VIS-001，并由 SYS/ENG/UX 承接 | 未完成上位设计前只允许外部 AI 按需调用无状态本地 CLI，Halpha 不持有 provider key |
| 新增产品持久进程、服务、数据库、发布组、远程认证入口、持久状态或同步业务调用 | HALPHA-ARC-001，并由相应 SYS/UX/ENG 承接 | 未满足 ARC 实证拆分条件时优先删除、收缩或保持文件交接 |
| 为研究沙箱新增独立镜像、第四种依赖/构建身份、持久守护或远程执行平台 | HALPHA-ENG-003；形成产品进程、服务、远程入口或同步依赖时同时复核 HALPHA-ARC-001 | 当前只允许复用已存在且通过资格的按需模型外边界；未完成新候选前保持完整数据与确认性研究禁用 |
| 与 NautilusTrader 并行、同权或 fallback 的第二正式量化栈 | `CON-CMP-004` 与 `ARC-QLT-002` 已禁止以平行实现换取兼容 | 不得由本契约授权；整体替换单一正式栈时重新进行 L3/L4 组件资格化 |
| 自动判定多个数据源、修订、重导出或切片之间的等价关系 | HALPHA-DAT-001，并由 DAT 形成新的或修订既有 L3 | 当前只消费 DAT-qualified immutable `data_snapshot_ref` 与资格材料；ALP/ENG/L4 不定义 lineage 算法，关系不明时确认性能力 fail-closed |
| 研究 API、agent framework、MCP/远程工具服务、向量库、实验数据库、调度器、统一策略接口等组合成通用 AI/量化研究平台 | `CON-NGL-001`，并通常同时复核 HALPHA-VIS-001、HALPHA-FLOW-001 与 HALPHA-ARC-001 | 在上位范围被明确修改前属于非目标 |
| 研究或工具取得产品数据库写角色、LIVE 写凭据或真实动作能力，或研究输出自动修改正式策略、交易计划、资金范围或权限 | `CON-SEC-001`、适用 `CON-CAP-001` 至 `CON-CAP-006`、`CON-ADP-001`、HALPHA-FLOW-001 与 HALPHA-ARC-001，并由 ALP/TRADEPLAN/CAP/EXE/DAT/SYS/ENG 承接；正式策略变更回到 ALP-002/ALP-003，交易计划变更回到 TRADEPLAN 所有者 | 继续保持研究无写能力、人工选择、产品内重验和用户显式授权；不得自动晋升、自授权或把研究派生内容提升为事实 |
