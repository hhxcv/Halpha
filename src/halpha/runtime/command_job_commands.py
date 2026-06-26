from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from halpha.pipeline_stages import STAGE_ORDER
from halpha.storage import display_path, safe_local_ref as _safe_ref


CODEX_STAGE = "generate_report"


class CommandJobError(Exception):
    def __init__(self, message: str, *, status: str = "blocked") -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class CommandSpec:
    intent: str
    kind: str
    cancellable: bool
    cli_parts: tuple[str, ...]
    allow_run_dir: bool = False
    extra_cli_parts: tuple[str, ...] = ()
    stage_param: str | None = None
    codex_confirmation: str | None = None
    param_mode: str | None = None


@dataclass(frozen=True)
class CommandJobCommand:
    spec: CommandSpec
    command: list[str]
    preview: list[str]


SUPPORTED_COMMANDS = {
    "run": CommandSpec(
        intent="run",
        kind="product_run",
        cancellable=True,
        cli_parts=("run",),
        codex_confirmation="always",
    ),
    "run_no_codex": CommandSpec(
        intent="run_no_codex",
        kind="product_run",
        cancellable=True,
        cli_parts=("run",),
        extra_cli_parts=("--no-codex",),
    ),
    "run_until": CommandSpec(
        intent="run_until",
        kind="product_run",
        cancellable=True,
        cli_parts=("run",),
        stage_param="until",
        codex_confirmation="stage_reaches_codex",
    ),
    "stage_rerun": CommandSpec(
        intent="stage_rerun",
        kind="stage_rerun",
        cancellable=True,
        cli_parts=("stage",),
        allow_run_dir=True,
        stage_param="positional",
        codex_confirmation="stage_is_codex",
    ),
    "validate": CommandSpec(
        intent="validate",
        kind="product_validation",
        cancellable=True,
        cli_parts=("validate",),
        allow_run_dir=True,
    ),
    "data_inspect": CommandSpec(
        intent="data_inspect",
        kind="data_inspection",
        cancellable=True,
        cli_parts=("data", "inspect"),
        allow_run_dir=True,
    ),
    "outcomes_inspect": CommandSpec(
        intent="outcomes_inspect",
        kind="outcome_inspection",
        cancellable=True,
        cli_parts=("outcomes", "inspect"),
        allow_run_dir=True,
    ),
    "workbench_build": CommandSpec(
        intent="workbench_build",
        kind="workbench_build",
        cancellable=True,
        cli_parts=("workbench", "build"),
        allow_run_dir=True,
    ),
    "workbench_inspect": CommandSpec(
        intent="workbench_inspect",
        kind="workbench_inspection",
        cancellable=True,
        cli_parts=("workbench", "inspect"),
    ),
    "monitor_inspect": CommandSpec(
        intent="monitor_inspect",
        kind="monitor_inspection",
        cancellable=True,
        cli_parts=("monitor", "inspect"),
    ),
    "monitor_dry_run": CommandSpec(
        intent="monitor_dry_run",
        kind="monitor_dry_run",
        cancellable=True,
        cli_parts=("monitor", "run"),
        extra_cli_parts=("--dry-run",),
    ),
    "monitor_once": CommandSpec(
        intent="monitor_once",
        kind="monitor_cycle",
        cancellable=True,
        cli_parts=("monitor", "run"),
        extra_cli_parts=("--once",),
    ),
    "backtest": CommandSpec(
        intent="backtest",
        kind="strategy_backtest",
        cancellable=True,
        cli_parts=("backtest",),
        param_mode="backtest",
    ),
    "experiment": CommandSpec(
        intent="experiment",
        kind="strategy_experiment",
        cancellable=True,
        cli_parts=("experiment",),
        param_mode="experiment",
    ),
    "text_models_prepare": CommandSpec(
        intent="text_models_prepare",
        kind="text_model_preparation",
        cancellable=True,
        cli_parts=("text-models", "prepare"),
        param_mode="text_models_prepare",
    ),
    "text_intel": CommandSpec(
        intent="text_intel",
        kind="text_intelligence",
        cancellable=True,
        cli_parts=("text-intel",),
        param_mode="text_intel",
    ),
}


class CommandJobBuilder:
    def __init__(self, config: dict[str, Any], *, config_path: Path, base: Path) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.resolved_config_path = self.config_path.resolve()
        self.base = base

    def build(self, intent: str, params: dict[str, Any]) -> CommandJobCommand:
        spec = SUPPORTED_COMMANDS.get(intent)
        if spec is None:
            raise CommandJobError(f"unsupported command job intent: {intent or 'missing'}", status="unsupported")
        command, preview = self._command_for_spec(spec, params)
        return CommandJobCommand(spec=spec, command=command, preview=preview)

    def _command_for_spec(self, spec: CommandSpec, params: dict[str, Any]) -> tuple[list[str], list[str]]:
        supported_params = {"run_dir"} if spec.allow_run_dir else set()
        if spec.stage_param:
            supported_params.add("stage_name")
        if spec.codex_confirmation:
            supported_params.add("confirm_codex")
        supported_params.update(self._param_mode_supported_params(spec.param_mode))
        extra = sorted(set(params) - supported_params)
        if extra:
            raise CommandJobError(f"unsupported {spec.intent} job parameter(s): {', '.join(extra)}")
        stage_name = self._validated_stage_name(params.get("stage_name")) if spec.stage_param else None
        if self._requires_codex_confirmation(spec, stage_name) and params.get("confirm_codex") is not True:
            raise CommandJobError("confirm_codex must be true for command jobs that may invoke Codex.")
        cli_parts = list(spec.cli_parts)
        if spec.stage_param == "positional" and stage_name:
            cli_parts.append(stage_name)
        command = [sys.executable, "-m", "halpha", *cli_parts, "--config", str(self.resolved_config_path)]
        preview = ["python", "-m", "halpha", *cli_parts, "--config", command_config_ref(self.config_path)]
        if spec.stage_param == "until" and stage_name:
            command.extend(["--until", stage_name])
            preview.extend(["--until", stage_name])
        if spec.extra_cli_parts:
            command.extend(spec.extra_cli_parts)
            preview.extend(spec.extra_cli_parts)
        self._extend_param_mode_args(spec.param_mode, params, command, preview)
        run_dir = params.get("run_dir")
        if run_dir is not None:
            run_dir_path = self._validated_run_dir(str(run_dir))
            command.extend(["--run-dir", str(run_dir_path)])
            preview.extend(["--run-dir", _safe_ref(run_dir_path, base=self.base)])
        return command, preview

    def _param_mode_supported_params(self, param_mode: str | None) -> set[str]:
        if param_mode == "backtest":
            return {"strategy_name", "symbol", "timeframe", "output_dir"}
        if param_mode == "experiment":
            return {"strategy_names", "output_dir"}
        if param_mode == "text_models_prepare":
            return {"output_dir"}
        if param_mode == "text_intel":
            return {"input_path", "output_dir"}
        return set()

    def _extend_param_mode_args(
        self,
        param_mode: str | None,
        params: dict[str, Any],
        command: list[str],
        preview: list[str],
    ) -> None:
        if param_mode == "backtest":
            strategy_name = self._validated_strategy_name(params.get("strategy_name"), param_name="strategy_name")
            symbol = self._validated_symbol(params.get("symbol"))
            timeframe = self._validated_timeframe(params.get("timeframe"))
            command.extend(["--strategy", strategy_name, "--symbol", symbol, "--timeframe", timeframe])
            preview.extend(["--strategy", strategy_name, "--symbol", symbol, "--timeframe", timeframe])
            self._extend_optional_output_dir(params, command, preview)
        elif param_mode == "experiment":
            strategy_names = self._validated_strategy_names(params.get("strategy_names"))
            for strategy_name in strategy_names:
                command.extend(["--strategy", strategy_name])
                preview.extend(["--strategy", strategy_name])
            self._extend_optional_output_dir(params, command, preview)
        elif param_mode == "text_models_prepare":
            self._extend_optional_output_dir(params, command, preview)
        elif param_mode == "text_intel":
            input_path = params.get("input_path")
            if input_path is not None:
                if not isinstance(input_path, str):
                    raise CommandJobError("input_path must be a string.")
                path = self._validated_input_path(str(input_path))
                command.extend(["--input", str(path)])
                preview.extend(["--input", _safe_ref(path, base=self.base)])
            self._extend_optional_output_dir(params, command, preview)

    def _extend_optional_output_dir(
        self,
        params: dict[str, Any],
        command: list[str],
        preview: list[str],
    ) -> None:
        output_dir = params.get("output_dir")
        if output_dir is None:
            return
        if not isinstance(output_dir, str):
            raise CommandJobError("output_dir must be a string.")
        path = self._validated_local_path(str(output_dir), param_name="output_dir")
        command.extend(["--output-dir", str(path)])
        preview.extend(["--output-dir", _safe_ref(path, base=self.base)])

    def _validated_strategy_name(self, value: Any, *, param_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CommandJobError(f"{param_name} must not be empty.")
        strategy_name = value.strip()
        if strategy_name not in self._configured_strategy_names():
            raise CommandJobError(f"{param_name} is not configured or enabled: {strategy_name}.")
        return strategy_name

    def _validated_strategy_names(self, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or not value:
            raise CommandJobError("strategy_names must be a non-empty list when provided.")
        return [self._validated_strategy_name(item, param_name="strategy_names") for item in value]

    def _validated_symbol(self, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CommandJobError("symbol must not be empty.")
        symbol = value.strip()
        if symbol not in self._configured_symbols():
            raise CommandJobError(f"symbol is not configured: {symbol}.")
        return symbol

    def _validated_timeframe(self, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CommandJobError("timeframe must not be empty.")
        timeframe = value.strip()
        if timeframe not in self._configured_timeframes():
            raise CommandJobError(f"timeframe is not configured: {timeframe}.")
        return timeframe

    def _validated_positive_int(self, value: Any, *, param_name: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise CommandJobError(f"{param_name} must be a positive integer.")
        return value

    def _configured_strategy_names(self) -> set[str]:
        quant = self.config.get("quant") if isinstance(self.config.get("quant"), dict) else {}
        strategies = quant.get("strategies") if isinstance(quant.get("strategies"), list) else []
        return {
            str(strategy.get("name"))
            for strategy in strategies
            if isinstance(strategy, dict) and strategy.get("name") and strategy.get("enabled", True) is not False
        }

    def _configured_symbols(self) -> set[str]:
        market = self.config.get("market") if isinstance(self.config.get("market"), dict) else {}
        values = market.get("symbols") if isinstance(market.get("symbols"), list) else []
        return {str(value) for value in values}

    def _configured_timeframes(self) -> set[str]:
        market = self.config.get("market") if isinstance(self.config.get("market"), dict) else {}
        ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
        values = ohlcv.get("timeframes") if isinstance(ohlcv.get("timeframes"), list) else []
        return {str(value) for value in values}

    def _validated_stage_name(self, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CommandJobError("stage_name must not be empty.")
        stage_name = value.strip()
        if stage_name not in STAGE_ORDER:
            supported = ", ".join(STAGE_ORDER)
            raise CommandJobError(f"stage_name must be one of: {supported}.")
        return stage_name

    def _requires_codex_confirmation(self, spec: CommandSpec, stage_name: str | None) -> bool:
        if spec.codex_confirmation == "always":
            return True
        if spec.codex_confirmation == "stage_is_codex":
            return stage_name == CODEX_STAGE
        if spec.codex_confirmation == "stage_reaches_codex" and stage_name:
            return STAGE_ORDER.index(stage_name) >= STAGE_ORDER.index(CODEX_STAGE)
        return False

    def _validated_run_dir(self, value: str) -> Path:
        if not value or not value.strip():
            raise CommandJobError("run_dir must not be empty.")
        path = Path(value)
        resolved = path if path.is_absolute() else self.base / path
        runs_root = self._run_output_root().resolve()
        try:
            resolved.resolve().relative_to(runs_root)
        except ValueError as exc:
            raise CommandJobError("run_dir must stay within the configured run output directory.") from exc
        return resolved

    def _validated_input_path(self, value: str) -> Path:
        path = self._validated_local_path(value, param_name="input_path")
        if not path.is_file():
            raise CommandJobError("input_path must reference an existing file.")
        return path

    def _validated_local_path(self, value: str, *, param_name: str) -> Path:
        if not value or not value.strip():
            raise CommandJobError(f"{param_name} must not be empty.")
        path = Path(value)
        resolved = path if path.is_absolute() else self.base / path
        try:
            resolved.resolve().relative_to(self.base.resolve())
        except ValueError as exc:
            raise CommandJobError(f"{param_name} must stay within the config directory.") from exc
        return resolved

    def _run_output_root(self) -> Path:
        run_config = self.config.get("run") if isinstance(self.config.get("run"), dict) else {}
        output_dir = Path(str(run_config.get("output_dir") or "runs"))
        return output_dir if output_dir.is_absolute() else self.base / output_dir


def command_config_ref(config_path: Path) -> str:
    path = Path(config_path)
    if not path.is_absolute():
        return display_path(path, external_ref="<external-config>")
    return "<external-config>"
