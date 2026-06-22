from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.data.raw_artifacts import RawArtifactError, validate_market_raw_artifact


STAGE_NAME = "build_analysis_materials"
MARKET_RAW_ARTIFACT = "raw/market.json"
MARKET_MATERIAL_ARTIFACT = "analysis/market_material.md"
EXPECTED_METRICS = (
    "price",
    "change_24h_pct",
    "volume_24h",
    "quote_volume_24h",
)


def build_market_material(config: dict[str, Any], run: RunContext) -> list[str]:
    market = config.get("market", {})
    if not market.get("enabled"):
        run.manifest["counts"]["market_material_records"] = 0
        return []

    raw_path = run.raw_dir / "market.json"
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{MARKET_RAW_ARTIFACT} was not found; collect_market_data must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{MARKET_RAW_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc

    try:
        validate_market_raw_artifact(raw, MARKET_RAW_ARTIFACT)
    except RawArtifactError as exc:
        raise PipelineError(str(exc), stage=STAGE_NAME, exit_code=3) from exc

    output_path = run.analysis_dir / "market_material.md"
    output_path.write_text(render_market_material(raw), encoding="utf-8")
    run.manifest["artifacts"]["market_material"] = MARKET_MATERIAL_ARTIFACT
    run.manifest["counts"]["market_material_records"] = len(raw["items"])
    return [MARKET_MATERIAL_ARTIFACT]


def render_market_material(raw: dict[str, Any]) -> str:
    lines = [
        "---",
        "artifact_type: analysis_market_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {MARKET_RAW_ARTIFACT}",
        "---",
        "",
        "# market_material",
        "",
    ]

    raw_source = raw.get("source", {})
    for item in raw["items"]:
        lines.extend(
            [
                f"## record: {item['id']}",
                "",
                "```yaml",
                _yaml_record(_record_from_item(item, raw_source)).rstrip(),
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def _record_from_item(item: dict[str, Any], raw_source: Any) -> dict[str, Any]:
    metrics, metric_uncertainties = _metrics_from_item(item)
    source, source_uncertainties = _source_from_item(item, raw_source)
    uncertainties = metric_uncertainties + source_uncertainties

    return {
        "record_type": "market_observation",
        "id": item["id"],
        "symbol": item["symbol"],
        "as_of": item["as_of"],
        "metrics": metrics,
        "source": source,
        "facts": _facts_from_item(item, metrics, source),
        "derived_observations": [],
        "assumptions": [],
        "uncertainties": uncertainties,
    }


def _metrics_from_item(item: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    raw_metrics = item.get("metrics")
    metrics: dict[str, Any] = {}
    uncertainties: list[str] = []

    if not isinstance(raw_metrics, dict):
        for key in EXPECTED_METRICS:
            metrics[key] = None
            uncertainties.append(f"metrics.{key} is missing from {MARKET_RAW_ARTIFACT}.")
        return metrics, uncertainties

    for key in EXPECTED_METRICS:
        metrics[key] = _explicit_value(raw_metrics.get(key))
        if metrics[key] is None:
            uncertainties.append(f"metrics.{key} is missing from {MARKET_RAW_ARTIFACT}.")

    for key in sorted(set(raw_metrics) - set(EXPECTED_METRICS)):
        metrics[key] = _explicit_value(raw_metrics.get(key))
        if metrics[key] is None:
            uncertainties.append(f"metrics.{key} is present without a usable value.")

    return metrics, uncertainties


def _source_from_item(item: dict[str, Any], raw_source: Any) -> tuple[dict[str, Any], list[str]]:
    item_source = item.get("source", {})
    raw_artifact_source = raw_source if isinstance(raw_source, dict) else {}
    source = {
        "name": item_source.get("name"),
        "url": _explicit_value(item_source.get("url"))
        or _explicit_value(raw_artifact_source.get("url")),
    }
    uncertainties = []
    if source["url"] is None:
        uncertainties.append(f"source.url is missing from {MARKET_RAW_ARTIFACT}.")
    return source, uncertainties


def _facts_from_item(item: dict[str, Any], metrics: dict[str, Any], source: dict[str, Any]) -> list[str]:
    symbol = item["symbol"]
    as_of = item["as_of"]
    source_name = source["name"]
    facts = [f"{source_name} reports a market observation for {symbol} as of {as_of}."]

    if metrics.get("price") is not None:
        facts.append(f"{source_name} reports {symbol} price as {metrics['price']} at {as_of}.")
    if metrics.get("change_24h_pct") is not None:
        facts.append(f"{source_name} reports {symbol} 24h change as {metrics['change_24h_pct']}%.")
    if metrics.get("volume_24h") is not None:
        facts.append(f"{source_name} reports {symbol} 24h volume as {metrics['volume_24h']}.")
    if metrics.get("quote_volume_24h") is not None:
        facts.append(
            f"{source_name} reports {symbol} 24h quote volume as {metrics['quote_volume_24h']}."
        )

    return facts


def _explicit_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _yaml_record(record: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML market material records.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(record, allow_unicode=True, sort_keys=False)
