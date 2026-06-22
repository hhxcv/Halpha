from __future__ import annotations

from typing import Any

from halpha.decision.decision_intelligence import (
    build_decision_intelligence_material as _build_decision_intelligence_material,
)
from halpha.runtime.pipeline_contracts import RunContext


def build_decision_intelligence_material(config: dict[str, Any], run: RunContext) -> list[str]:
    return _build_decision_intelligence_material(config, run)
