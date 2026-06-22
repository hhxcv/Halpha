from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen
from xml.etree import ElementTree

from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.runtime.public_http import market_proxy_url_from_config, urlopen_from_public_proxy
from halpha.data.raw_artifacts import RawArtifactError, validate_text_events_raw_artifact
from halpha.storage import write_json


STAGE_NAME = "collect_text_events"
TEXT_ARTIFACT = "raw/text_events.json"
RSS_SOURCE_TYPE = "rss"
REQUEST_TIMEOUT_SECONDS = 20


def collect_text_events(config: dict[str, Any], run: RunContext) -> list[str]:
    text = config.get("text", {})
    if not text.get("enabled"):
        run.manifest["counts"]["text_event_items"] = 0
        return []

    raw = collect_text_events_raw(text, proxy_url=_proxy_url_from_config(config))
    artifact_path = run.raw_dir / "text_events.json"
    write_json(artifact_path, raw)
    run.manifest["artifacts"]["raw_text_events"] = TEXT_ARTIFACT
    run.manifest["counts"]["text_event_items"] = len(raw["items"])

    if not raw["items"] and raw["errors"]:
        raise PipelineError(
            _collector_failure_message(raw["errors"]),
            stage=STAGE_NAME,
            exit_code=3,
            artifacts=[TEXT_ARTIFACT],
        )

    return [TEXT_ARTIFACT]


def collect_text_events_raw(text: dict[str, Any], *, proxy_url: str | None = None) -> dict[str, Any]:
    raw = _collect_raw_text_events(text, proxy_url=proxy_url)
    try:
        validate_text_events_raw_artifact(raw, TEXT_ARTIFACT)
    except RawArtifactError as exc:
        raise PipelineError(str(exc), stage=STAGE_NAME, exit_code=3) from exc
    return raw


def _collect_raw_text_events(text: dict[str, Any], *, proxy_url: str | None) -> dict[str, Any]:
    collected_at = _utc_timestamp()
    max_items = text.get("max_items")
    if not isinstance(max_items, int) or isinstance(max_items, bool):
        max_items = None

    sources = list(text.get("sources", []))
    raw = {
        "schema_version": 1,
        "artifact_type": "text_events_raw",
        "collector": "text",
        "collection_method": "rss",
        "collected_at": collected_at,
        "sources": [_source_summary(source) for source in sources],
        "items": [],
        "errors": [],
    }
    urlopen_func = _urlopen_from_proxy(proxy_url)

    for source in sources:
        if max_items is not None and len(raw["items"]) >= max_items:
            break

        try:
            items = _collect_rss_source(source, collected_at, urlopen_func=urlopen_func)
        except TextCollectionError as exc:
            raw["errors"].append(
                {
                    "source": source.get("name"),
                    "url": source.get("url"),
                    "message": str(exc),
                }
            )
            continue

        remaining = None if max_items is None else max_items - len(raw["items"])
        raw["items"].extend(items if remaining is None else items[:remaining])

    return raw


def _collect_rss_source(source: dict[str, Any], collected_at: str, *, urlopen_func) -> list[dict[str, Any]]:
    source_type = source.get("type")
    if source_type != RSS_SOURCE_TYPE:
        raise TextCollectionError(f"unsupported text source type: {source_type}")

    body = _request_feed(source, urlopen_func=urlopen_func)
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise TextCollectionError(f"RSS feed is not valid XML: {exc}") from exc

    rss_items = _rss_items(root)
    if not rss_items:
        raise TextCollectionError("RSS feed contains no items")

    return [_text_item(source, item, collected_at) for item in rss_items]


def _request_feed(source: dict[str, Any], *, urlopen_func) -> str:
    url = source.get("url")
    request = Request(str(url), headers={"User-Agent": "Halpha/0.0.0"})
    try:
        with urlopen_func(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
    except HTTPError as exc:
        detail = _read_error_detail(exc)
        raise TextCollectionError(f"RSS request failed: HTTP {exc.code}{detail}") from exc
    except URLError as exc:
        raise TextCollectionError(f"RSS request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise TextCollectionError("RSS request timed out") from exc

    return body.decode("utf-8", errors="replace")


def _proxy_url_from_config(config: dict[str, Any]) -> str | None:
    return market_proxy_url_from_config(config, error_factory=TextCollectionError)


def _urlopen_from_proxy(proxy_url: str | None):
    return urlopen_from_public_proxy(
        proxy_url,
        error_factory=TextCollectionError,
        default_urlopen=urlopen,
        proxy_handler_factory=ProxyHandler,
        opener_factory=build_opener,
    )


def _rss_items(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [
        element
        for element in root.iter()
        if _local_name(element.tag) == "item"
    ]


def _text_item(source: dict[str, Any], item: ElementTree.Element, collected_at: str) -> dict[str, Any]:
    title = _required_item_text(item, "title")
    link = _first_child_text(item, {"link"})
    published_at = _published_at(item)
    content_text = _content_text(item) or title
    source_name = _required_source_text(source, "name")
    source_url = source.get("url") if source.get("url") else None

    return {
        "id": _item_id(source_name, item, title, published_at, collected_at),
        "type": "rss_item",
        "title": title,
        "published_at": published_at,
        "source": {
            "name": source_name,
            "url": source_url,
        },
        "link": link,
        "content_text": content_text,
        "language": None,
    }


def _required_source_text(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TextCollectionError(f"text source missing {key}")
    return value.strip()


def _required_item_text(item: ElementTree.Element, name: str) -> str:
    value = _first_child_text(item, {name})
    if not value:
        raise TextCollectionError(f"RSS item missing {name}")
    return value


def _first_child_text(item: ElementTree.Element, names: set[str]) -> str | None:
    for child in list(item):
        if _local_name(child.tag) in names:
            text = " ".join(child.itertext()).strip()
            if text:
                return unescape(text)
    return None


def _content_text(item: ElementTree.Element) -> str | None:
    value = _first_child_text(item, {"encoded", "description", "summary"})
    if not value:
        return None
    return _strip_html(value)


def _published_at(item: ElementTree.Element) -> str | None:
    value = _first_child_text(item, {"pubDate", "published", "updated"})
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _utc_timestamp(parsed)


def _item_id(
    source_name: str,
    item: ElementTree.Element,
    title: str,
    published_at: str | None,
    collected_at: str,
) -> str:
    seed = _first_child_text(item, {"guid", "id"}) or _first_child_text(item, {"link"})
    seed = seed or f"{title}:{published_at or collected_at}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"text:{source_name}:{digest}"


def _source_summary(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": source.get("name"),
        "type": source.get("type"),
        "url": source.get("url") if source.get("url") else None,
    }


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _strip_html(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    text = " ".join(" ".join(parser.parts).split())
    return unescape(text)


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")


def _collector_failure_message(errors: list[dict[str, Any]]) -> str:
    summaries = [
        f"{error.get('source')}: {error.get('message')}"
        for error in errors
    ]
    return f"text collection failed for {len(errors)} source(s): {'; '.join(summaries)}"


def _read_error_detail(error: HTTPError) -> str:
    try:
        body = error.read().decode("utf-8").strip()
    except Exception:
        body = ""
    if not body:
        return ""
    excerpt = body[:200].replace("\n", " ")
    return f": {excerpt}"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


class TextCollectionError(Exception):
    pass
