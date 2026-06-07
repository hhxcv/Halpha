from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from halpha.cli import main


def test_m0_smoke_pipeline_uses_mocks_without_product_fixtures(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    requested_urls: list[str] = []
    codex_calls: list[dict] = []

    def fake_market_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        symbol = request.full_url.rsplit("=", 1)[-1]
        return _JsonResponse(_market_payload(symbol))

    def fake_text_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _BytesResponse(_rss_payload())

    def fake_codex_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
        codex_calls.append(
            {
                "command": command,
                "input": input,
                "text": text,
                "encoding": encoding,
                "errors": errors,
                "capture_output": capture_output,
                "timeout": timeout,
                "cwd": cwd,
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout=_report_stdout(), stderr="")

    monkeypatch.setattr("halpha.collectors.market.urlopen", fake_market_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", fake_text_urlopen)
    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_codex_run)

    exit_code = main(["run", "--config", str(config_path)])

    assert exit_code == 0
    assert requested_urls == [
        "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT",
        "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=ETHUSDT",
        "https://example.com/feed.xml",
    ]

    run_dirs = sorted((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    expected_artifacts = [
        "raw/market.json",
        "raw/text_events.json",
        "analysis/market_material.md",
        "analysis/text_material.md",
        "analysis/research_context.md",
        "codex_context/context.md",
        "codex_context/prompt.md",
        "report/report.md",
        "run_manifest.json",
    ]
    for artifact in expected_artifacts:
        assert (run_dir / artifact).is_file()

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded"
    assert manifest["counts"]["market_items"] == 2
    assert manifest["counts"]["text_event_items"] == 1
    assert manifest["ohlcv_sync"]["status"] == "skipped"
    assert manifest["codex"]["status"] == "succeeded"
    assert manifest["codex"]["exit_code"] == 0
    assert manifest["artifacts"] == {
        "codex_context": "codex_context/context.md",
        "codex_prompt": "codex_context/prompt.md",
        "market_material": "analysis/market_material.md",
        "raw_market": "raw/market.json",
        "raw_text_events": "raw/text_events.json",
        "report": "report/report.md",
        "research_context": "analysis/research_context.md",
        "text_material": "analysis/text_material.md",
    }
    assert [(stage["name"], stage["status"]) for stage in manifest["stages"]] == [
        ("collect_market_data", "succeeded"),
        ("collect_text_events", "succeeded"),
        ("sync_ohlcv", "succeeded"),
        ("build_market_data_views", "succeeded"),
        ("evaluate_market_strategy_signals", "succeeded"),
        ("build_analysis_materials", "succeeded"),
        ("build_research_context", "succeeded"),
        ("build_codex_context", "succeeded"),
        ("run_codex_report", "succeeded"),
    ]
    assert manifest["stages"][-1]["artifacts"] == ["report/report.md"]

    market_raw = json.loads((run_dir / "raw/market.json").read_text(encoding="utf-8"))
    assert market_raw["source"]["name"] == "binance"
    assert [item["symbol"] for item in market_raw["items"]] == ["BTCUSDT", "ETHUSDT"]
    assert market_raw["errors"] == []

    text_raw = json.loads((run_dir / "raw/text_events.json").read_text(encoding="utf-8"))
    assert text_raw["sources"][0]["url"] == "https://example.com/feed.xml"
    assert len(text_raw["items"]) == 1
    assert text_raw["errors"] == []

    market_material = (run_dir / "analysis/market_material.md").read_text(encoding="utf-8")
    text_material = (run_dir / "analysis/text_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_market_material" in market_material
    assert "artifact_type: analysis_text_material" in text_material

    prompt = (run_dir / "codex_context/prompt.md").read_text(encoding="utf-8")
    assert "Use Chinese section headings only." in prompt
    assert "Source-provided smoke event." in prompt
    assert codex_calls[0]["input"] == prompt
    assert codex_calls[0]["encoding"] == "utf-8"
    assert codex_calls[0]["cwd"] == run_dir

    report = (run_dir / "report/report.md").read_text(encoding="utf-8")
    assert "## 风险提示" in report
    assert "binance" in report
    assert "coindesk" in report
    assert "tests/fixtures" not in config_path.read_text(encoding="utf-8")


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
    - ETHUSDT
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/feed.xml
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: true
  command: codex
  args:
    - exec
    - --sandbox
    - read-only
    - "-"
  timeout_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _market_payload(symbol: str) -> dict:
    price = "68000.00" if symbol == "BTCUSDT" else "3600.00"
    return {
        "symbol": symbol,
        "lastPrice": price,
        "priceChangePercent": "1.25",
        "volume": "123.45",
        "quoteVolume": "8394600.00",
        "closeTime": _millis(datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc)),
    }


def _rss_payload() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <item>
      <title>Smoke market event</title>
      <link>https://example.com/smoke-event</link>
      <guid>smoke-event-1</guid>
      <pubDate>Fri, 05 Jun 2026 00:30:00 GMT</pubDate>
      <description>Source-provided smoke event.</description>
    </item>
  </channel>
</rss>
"""


def _report_stdout() -> str:
    return "\n".join(
        [
            "# 每日市场情报简报",
            "",
            "## 核心摘要",
            "",
            "binance 和 coindesk 的本地上下文已用于生成报告。",
            "",
            "## 市场概览",
            "",
            "市场观察保持来源意识。",
            "",
            "## 文本事件",
            "",
            "coindesk 提供了公开文本事件。",
            "",
            "## 综合判断",
            "",
            "该判断仅基于测试上下文。",
            "",
            "## 观察要点",
            "",
            "- 继续观察公开来源。",
            "",
            "## 风险提示",
            "",
            "本内容仅供个人研究，不构成投资建议。",
            "",
        ]
    )


def _millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


class _JsonResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _BytesResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload
