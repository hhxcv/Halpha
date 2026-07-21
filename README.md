# Halpha

Halpha 是由单一所有者维护的交易决策、执行与学习工作台。开发采用连续、可验证的小步迭代；当前焦点和环境事实记录在 `docs/L4/HALPHA-PLAN-001-current-plan.yaml`。

依赖、测试、构建和运行命令统一使用由 Python 3.13.14 创建的仓库 `.venv`。测试通过或生成产品构建不允许系统自行发起真实账户交易动作。

## 统一进程管控

`halpha-control` 是 Halpha 产品长期进程的唯一操作入口。它把 `\Halpha\App`、`\Halpha\Executor`、`\Halpha\Backup` Windows 任务，与当前仓库及所有已登记 Git 工作树中的产品进程树、TCP 监听和外部服务主动登记合并为一个视图。手工启动的 App/Executor、未知项目监听等不能归入受管任务或有效外部登记的实例会显示为 `unmanaged:<PID>`，不会被静默忽略。

从仓库根目录执行：

```powershell
# 查看 app、executor、backup、外部主动登记服务和未登记项目进程/监听
.venv\Scripts\halpha-control.exe status

# 启动产品组合；只启动 app 和 executor
.venv\Scripts\halpha-control.exe start product

# 也可按需单独启动
.venv\Scripts\halpha-control.exe start app
.venv\Scripts\halpha-control.exe start executor
.venv\Scripts\halpha-control.exe start backup

# 停止产品组合；省略服务名时同样默认为 product
.venv\Scripts\halpha-control.exe stop product
.venv\Scripts\halpha-control.exe stop

# 停止指定服务或 status 返回的未登记监听
.venv\Scripts\halpha-control.exe stop app
.venv\Scripts\halpha-control.exe stop unmanaged:12345

# 停止所有受管任务以及所有已发现的项目监听
.venv\Scripts\halpha-control.exe stop all
```

命令默认读取仓库内的 `config/halpha.toml`，日常操作不需要传配置。只有临时检查另一份配置时才追加 `--config <路径>`。CLI 主动生成的帮助、表头、状态、操作结果和错误前缀只使用 ASCII 英文，避免 Windows 终端编码问题；路径、外部错误和日志等被动内容保持来源原文。脚本需要机器读取时追加 `--json`，例如 `.venv\Scripts\halpha-control.exe status --json`。

`status` 显示 `Controlled` 时退出码为 `0`；任务缺失、状态无法确认、外部登记失效或发现未登记项目进程/监听时显示 `Attention Required` 并返回退出码 `3`。启动 App 或 Executor 前还会拒绝同类未登记实例，防止出现第二运行者。`stop app`、`stop executor` 和 `stop all` 会先禁用相应 Windows 任务，避免每分钟触发器重新拉起；再次 `start` 会重新启用任务。正常停止超时会拒绝假装成功，只有明确接受操作系统强停风险时才对任务管理的服务追加 `--force`。

研究服务保持独立，交易内核不引用研究路径、模块、虚拟环境或服务名称，也不负责研究服务的启动和停止。独立服务可向 `%LOCALAPPDATA%\Halpha\external-services` 写入通用 JSON 登记；`status` 会用登记的 PID 和 TCP 监听实况交叉核验，并显示为 `external:<service-id>`、`External Registration`。这只提供可见性，不转移启停所有权；`stop all` 和显式 `stop external:<service-id>` 都不会停止它。研究服务按各自 README 启停。禁止绕过统一入口直接长期运行产品；短时测试、构建和迁移不受此限制。

`stop all` 会同时禁用备份任务并停止所有未登记的项目监听，但跳过有效的外部主动登记服务，使用前应先查看 `status`。进程停止不等于订单、持仓、保护等业务责任已经闭合；需要恢复、退出或接管时仍须遵守正式运行契约。
