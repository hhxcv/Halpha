from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MONITOR_ENABLED = False
DEFAULT_MONITOR_INTERVAL_SECONDS = 300
DEFAULT_MONITOR_MAX_CYCLES = 1
DEFAULT_MONITOR_COOLDOWN_SECONDS = 3600
DEFAULT_MONITOR_OUTPUT_DIR = "runs/monitor"
DEFAULT_MONITOR_TARGET_STAGE = "build_personalized_risk_material"
DEFAULT_MONITOR_NO_CODEX = True
SUPPORTED_MONITOR_FIELDS = {
    "cooldown_seconds",
    "enabled",
    "interval_seconds",
    "max_cycles",
    "no_codex",
    "output_dir",
    "target_stage",
}


@dataclass(frozen=True)
class MonitorConfig:
    enabled: bool
    interval_seconds: int
    max_cycles: int
    cooldown_seconds: int
    output_dir: Path
    target_stage: str
    no_codex: bool


def load_monitor_config(config: dict[str, Any]) -> MonitorConfig:
    section = config.get("monitor", {})
    if not isinstance(section, dict):
        raise ValueError("monitor config must be a mapping.")

    return MonitorConfig(
        enabled=section.get("enabled", DEFAULT_MONITOR_ENABLED),
        interval_seconds=section.get("interval_seconds", DEFAULT_MONITOR_INTERVAL_SECONDS),
        max_cycles=section.get("max_cycles", DEFAULT_MONITOR_MAX_CYCLES),
        cooldown_seconds=section.get("cooldown_seconds", DEFAULT_MONITOR_COOLDOWN_SECONDS),
        output_dir=Path(str(section.get("output_dir", DEFAULT_MONITOR_OUTPUT_DIR))),
        target_stage=section.get("target_stage", DEFAULT_MONITOR_TARGET_STAGE),
        no_codex=section.get("no_codex", DEFAULT_MONITOR_NO_CODEX),
    )


def monitor_config_lines(settings: MonitorConfig) -> list[str]:
    return [
        f"enabled: {str(settings.enabled).lower()}",
        f"interval_seconds: {settings.interval_seconds}",
        f"max_cycles: {settings.max_cycles}",
        f"cooldown_seconds: {settings.cooldown_seconds}",
        f"output_dir: {settings.output_dir.as_posix()}",
        f"target_stage: {settings.target_stage}",
        f"no_codex: {str(settings.no_codex).lower()}",
    ]
