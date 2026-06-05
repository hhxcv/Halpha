from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_research_context"
RESEARCH_CONTEXT_ARTIFACT = "analysis/research_context.md"
MARKET_MATERIAL_ARTIFACT = "analysis/market_material.md"
TEXT_MATERIAL_ARTIFACT = "analysis/text_material.md"


def build_research_context(config: dict[str, Any], run: RunContext) -> list[str]:
    artifact_index = _artifact_index(run)
    market_material = _read_material(
        run.analysis_dir / "market_material.md",
        MARKET_MATERIAL_ARTIFACT,
        enabled=bool(config.get("market", {}).get("enabled")),
        producer_stage="build_analysis_materials",
    )
    text_material = _read_material(
        run.analysis_dir / "text_material.md",
        TEXT_MATERIAL_ARTIFACT,
        enabled=bool(config.get("text", {}).get("enabled")),
        producer_stage="build_analysis_materials",
    )

    output_path = run.analysis_dir / "research_context.md"
    output_path.write_text(
        render_research_context(
            config,
            run=run,
            artifact_index=artifact_index,
            market_material=market_material,
            text_material=text_material,
        ),
        encoding="utf-8",
    )
    run.manifest["artifacts"]["research_context"] = RESEARCH_CONTEXT_ARTIFACT
    return [RESEARCH_CONTEXT_ARTIFACT]


def render_research_context(
    config: dict[str, Any],
    *,
    run: RunContext,
    artifact_index: dict[str, Any],
    market_material: str | None,
    text_material: str | None,
) -> str:
    source_artifacts = [value for value in artifact_index.values() if value is not None]
    lines = [
        "---",
        "artifact_type: research_context",
        "schema_version: 1",
        "audience: codex_cli",
        "language_target: zh-CN",
        "source_artifacts:",
        *_yaml_list(source_artifacts),
        "---",
        "",
        "# research_context",
        "",
        "## run",
        "",
        "```yaml",
        _yaml_block(_run_summary(config, run)).rstrip(),
        "```",
        "",
        "## material_index",
        "",
        "```yaml",
        _yaml_block(artifact_index).rstrip(),
        "```",
        "",
        "## source_policy",
        "",
        "```yaml",
        _yaml_block(_source_policy()).rstrip(),
        "```",
        "",
        "## generation_constraints",
        "",
        "```yaml",
        _yaml_block(_generation_constraints()).rstrip(),
        "```",
        "",
        "## market_material",
        "",
    ]
    lines.extend(_embedded_material(MARKET_MATERIAL_ARTIFACT, market_material))
    lines.extend(["", "## text_material", ""])
    lines.extend(_embedded_material(TEXT_MATERIAL_ARTIFACT, text_material))
    return "\n".join(lines)


def _artifact_index(run: RunContext) -> dict[str, Any]:
    artifacts = run.manifest.get("artifacts", {})
    return {
        "raw_market": artifacts.get("raw_market"),
        "raw_text_events": artifacts.get("raw_text_events"),
        "market_material": artifacts.get("market_material"),
        "text_material": artifacts.get("text_material"),
    }


def _read_material(path: Path, artifact: str, *, enabled: bool, producer_stage: str) -> str | None:
    if not enabled:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact} was not found; {producer_stage} must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc


def _run_summary(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    report = config.get("report", {})
    return {
        "run_id": run.run_id,
        "report_title": report.get("title"),
        "report_language": report.get("language"),
    }


def _source_policy() -> dict[str, Any]:
    return {
        "allowed_sources_only": True,
        "fabricate_missing_sources": False,
        "fabricate_missing_facts": False,
        "missing_url_label": "source_url_not_provided",
        "distinguish_facts_assumptions_uncertainties_judgment": True,
        "financial_advice": False,
    }


def _generation_constraints() -> dict[str, Any]:
    return {
        "output_language": "Simplified Chinese",
        "output_format": "Markdown",
        "use_only_embedded_context": True,
        "do_not_invent_prices_events_links_sources": True,
        "include_risk_notice": True,
        "required_sections": [
            "title",
            "core_summary",
            "market_overview",
            "text_events",
            "synthesis",
            "watch_points",
            "risk_notice",
        ],
    }


def _embedded_material(artifact: str, content: str | None) -> list[str]:
    if content is None:
        return [
            "```yaml",
            _yaml_block({"artifact": artifact, "status": "not_generated"}).rstrip(),
            "```",
        ]
    return [
        f'<embed path="{artifact}">',
        content.rstrip(),
        "</embed>",
    ]


def _yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {value}" for value in values]


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML research context records.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
