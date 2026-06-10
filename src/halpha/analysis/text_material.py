from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.raw_artifacts import RawArtifactError, validate_text_events_raw_artifact


STAGE_NAME = "build_analysis_materials"
TEXT_RAW_ARTIFACT = "raw/text_events.json"
TEXT_MATERIAL_ARTIFACT = "analysis/text_material.md"


def build_text_material(config: dict[str, Any], run: RunContext) -> list[str]:
    text = config.get("text", {})
    if not text.get("enabled"):
        run.manifest["counts"]["text_material_records"] = 0
        return []

    raw_path = run.raw_dir / "text_events.json"
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{TEXT_RAW_ARTIFACT} was not found; collect_text_events must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{TEXT_RAW_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc

    try:
        validate_text_events_raw_artifact(raw, TEXT_RAW_ARTIFACT)
    except RawArtifactError as exc:
        raise PipelineError(str(exc), stage=STAGE_NAME, exit_code=3) from exc

    output_path = run.analysis_dir / "text_material.md"
    output_path.write_text(render_text_material(raw), encoding="utf-8")
    run.manifest["artifacts"]["text_material"] = TEXT_MATERIAL_ARTIFACT
    run.manifest["counts"]["text_material_records"] = len(raw["items"])
    return [TEXT_MATERIAL_ARTIFACT]


def render_text_material(raw: dict[str, Any]) -> str:
    lines = [
        "---",
        "artifact_type: analysis_text_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {TEXT_RAW_ARTIFACT}",
        "---",
        "",
        "# text_material",
        "",
    ]

    sources = raw.get("sources", [])
    for item in raw["items"]:
        lines.extend(
            [
                f"## record: {item['id']}",
                "",
                "```yaml",
                _yaml_record(_record_from_item(item, sources)).rstrip(),
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def _record_from_item(item: dict[str, Any], sources: Any) -> dict[str, Any]:
    source, source_uncertainties = _source_from_item(item, sources)
    link, link_uncertainties = _link_from_item(item)
    input_type, input_type_uncertainties = _input_type_from_item(item)
    published_at, published_at_uncertainties = _published_at_from_item(item)
    uncertainties = (
        source_uncertainties
        + link_uncertainties
        + input_type_uncertainties
        + published_at_uncertainties
    )

    return {
        "record_type": "text_event",
        "id": item["id"],
        "input_type": input_type,
        "title": item["title"],
        "published_at": published_at,
        "source": source,
        "link": link,
        "content_text": item["content_text"],
        "derived_summary": None,
        "facts": _facts_from_item(item, source, link, published_at),
        "derived_observations": [],
        "assumptions": [],
        "uncertainties": uncertainties,
    }


def _source_from_item(item: dict[str, Any], sources: Any) -> tuple[dict[str, Any], list[str]]:
    item_source = item.get("source", {})
    source_name = item_source.get("name")
    source_url = _explicit_value(item_source.get("url")) or _source_url_from_sources(
        source_name,
        sources,
    )
    source = {
        "name": source_name,
        "url": source_url,
    }
    uncertainties = []
    if source_url is None:
        uncertainties.append(f"source.url is missing from {TEXT_RAW_ARTIFACT}.")
    return source, uncertainties


def _source_url_from_sources(source_name: Any, sources: Any) -> Any:
    if not isinstance(source_name, str) or not isinstance(sources, list):
        return None
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("name") == source_name:
            return _explicit_value(source.get("url"))
    return None


def _link_from_item(item: dict[str, Any]) -> tuple[Any, list[str]]:
    link = _explicit_value(item.get("link"))
    if link is None:
        return None, [f"link is missing from {TEXT_RAW_ARTIFACT}."]
    return link, []


def _input_type_from_item(item: dict[str, Any]) -> tuple[Any, list[str]]:
    input_type = _explicit_value(item.get("type"))
    if input_type is None:
        return None, [f"type is missing from {TEXT_RAW_ARTIFACT}."]
    return input_type, []


def _published_at_from_item(item: dict[str, Any]) -> tuple[Any, list[str]]:
    published_at = _explicit_value(item.get("published_at"))
    if published_at is None:
        return None, [f"published_at is missing from {TEXT_RAW_ARTIFACT}."]
    return published_at, []


def _facts_from_item(
    item: dict[str, Any],
    source: dict[str, Any],
    link: Any,
    published_at: Any,
) -> list[str]:
    source_name = source["name"]
    if published_at is None:
        published_fact = (
            f'{source_name} published item "{item["title"]}" '
            "without a source-provided published_at timestamp."
        )
    else:
        published_fact = f'{source_name} published item "{item["title"]}" at {published_at}.'
    facts = [published_fact, f"{source_name} provided content_text for item {item['id']}."]
    if link is not None:
        facts.append(f"The item link is {link}.")
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
            "PyYAML is required to write YAML text material records.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(record, allow_unicode=True, sort_keys=False)
