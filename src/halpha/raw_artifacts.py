from __future__ import annotations

from typing import Any


class RawArtifactError(Exception):
    pass


def validate_market_raw_artifact(raw: Any, artifact: str) -> None:
    items = _items(raw, artifact)
    for index, item in enumerate(items):
        path = f"items[{index}]"
        _required_string(item, "id", artifact, path)
        _required_string(item, "symbol", artifact, path)
        _required_string(item, "as_of", artifact, path)
        _required_source_name(item, artifact, path)


def validate_text_events_raw_artifact(raw: Any, artifact: str) -> None:
    items = _items(raw, artifact)
    for index, item in enumerate(items):
        path = f"items[{index}]"
        _required_string(item, "id", artifact, path)
        _required_string(item, "title", artifact, path)
        _optional_string(item, "published_at", artifact, path)
        _required_source_name(item, artifact, path)
        _required_string(item, "content_text", artifact, path)


def validate_derivatives_market_raw_artifact(raw: Any, artifact: str) -> None:
    items = _items(raw, artifact)
    for index, item in enumerate(items):
        path = f"items[{index}]"
        _required_string(item, "item_id", artifact, path)
        _required_string(item, "data_class", artifact, path)
        _required_string(item, "source", artifact, path)
        _required_string(item, "market_type", artifact, path)
        _required_string(item, "symbol", artifact, path)
        _required_string(item, "period", artifact, path)
        _required_string(item, "as_of", artifact, path)
        _required_string(item, "endpoint", artifact, path)
        _required_mapping(item, "metrics", artifact, path)
        _required_mapping(item, "units", artifact, path)
        _required_mapping(item, "raw_fields", artifact, path)
        _required_list(item, "warnings", artifact, path)
        _required_list(item, "errors", artifact, path)
    _required_list(raw, "availability", artifact, "artifact")
    _required_list(raw, "errors", artifact, "artifact")


def _items(raw: Any, artifact: str) -> list[Any]:
    if not isinstance(raw, dict):
        raise RawArtifactError(f"{artifact} is invalid: artifact must be a JSON object.")
    items = raw.get("items")
    if not isinstance(items, list):
        raise RawArtifactError(f"{artifact} is invalid: items must be a list.")
    return items


def _required_string(item: Any, key: str, artifact: str, path: str) -> str:
    if not isinstance(item, dict):
        raise RawArtifactError(f"{artifact} is invalid: {path} must be a JSON object.")
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RawArtifactError(f"{artifact} is invalid: {path}.{key} is required.")
    return value


def _optional_string(item: Any, key: str, artifact: str, path: str) -> str | None:
    if not isinstance(item, dict):
        raise RawArtifactError(f"{artifact} is invalid: {path} must be a JSON object.")
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RawArtifactError(f"{artifact} is invalid: {path}.{key} must be a string or null.")
    return value


def _required_source_name(item: dict[str, Any], artifact: str, path: str) -> None:
    source = item.get("source")
    if not isinstance(source, dict):
        raise RawArtifactError(f"{artifact} is invalid: {path}.source must be a JSON object.")
    value = source.get("name")
    if not isinstance(value, str) or not value.strip():
        raise RawArtifactError(f"{artifact} is invalid: {path}.source.name is required.")


def _required_mapping(item: dict[str, Any], key: str, artifact: str, path: str) -> dict[str, Any]:
    value = item.get(key)
    if not isinstance(value, dict):
        raise RawArtifactError(f"{artifact} is invalid: {path}.{key} must be a JSON object.")
    return value


def _required_list(item: dict[str, Any], key: str, artifact: str, path: str) -> list[Any]:
    value = item.get(key)
    if not isinstance(value, list):
        raise RawArtifactError(f"{artifact} is invalid: {path}.{key} must be a list.")
    return value
