"""Probe credential-free Binance Futures public REST connectivity."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence
from urllib.request import ProxyHandler, Request, build_opener

import keyring


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from halpha.configuration import executor_settings, load_settings, settings_digest
from halpha.domain_values import content_digest
from halpha.winvault import executor_secret_resolver


DEFAULT_CONFIG = ROOT / "config/halpha.live-read-only.toml"
DEFAULT_OUTPUT = ROOT / "build/qualification/live-read-only-public-connectivity.json"
TIME_URL = "https://fapi.binance.com/fapi/v1/time"
EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo?symbol=BTCUSDT"


class PublicConnectivityProbeError(RuntimeError):
    """A sanitized public-connectivity probe failure."""


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _get_json(opener: Any, url: str) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        headers={"User-Agent": "Halpha-Public-ReadOnly-Check/1"},
        method="GET",
    )
    with opener.open(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise PublicConnectivityProbeError("PUBLIC_RESPONSE_ROOT_INVALID")
        return int(response.status), payload


def probe_public_endpoints(
    *,
    proxy_url: str | None,
    opener_builder: Callable[..., Any] = build_opener,
) -> dict[str, Any]:
    """Return sanitized observations; never return the proxy or response bodies."""

    handler = ProxyHandler(
        {"http": proxy_url, "https": proxy_url} if proxy_url is not None else {}
    )
    opener = opener_builder(handler)
    time_status, time_payload = _get_json(opener, TIME_URL)
    exchange_status, exchange_payload = _get_json(opener, EXCHANGE_INFO_URL)
    symbols = exchange_payload.get("symbols")
    btcusdt = (
        next(
            (
                item
                for item in symbols
                if isinstance(item, dict) and item.get("symbol") == "BTCUSDT"
            ),
            None,
        )
        if isinstance(symbols, list)
        else None
    )
    return {
        "time_http_status": time_status,
        "exchange_info_http_status": exchange_status,
        "server_time_integer": isinstance(time_payload.get("serverTime"), int),
        "btcusdt_symbol_present": btcusdt is not None,
        "btcusdt_contract_type": (
            str(btcusdt.get("contractType")) if btcusdt is not None else None
        ),
        "btcusdt_status": str(btcusdt.get("status")) if btcusdt is not None else None,
    }


def probe(config_path: Path) -> dict[str, Any]:
    settings = load_settings(config_path)
    role_settings = executor_settings(settings)
    checks = {
        "live_read_only_profile_selected": (
            settings.release.profile == "BINANCE_LIVE_READ_ONLY"
        ),
        "no_trading_authority_selected": (
            settings.release.authority_class == "NO_TRADING_AUTHORITY"
        ),
        "binance_credentials_structurally_absent": (
            settings.executor.binance_api_key_reference is None
            and settings.executor.binance_api_secret_reference is None
        ),
        "time_endpoint_http_200": False,
        "exchange_info_endpoint_http_200": False,
        "server_time_shape_valid": False,
        "btcusdt_perpetual_trading_contract_observed": False,
        "no_venue_write_performed": False,
        "no_secret_value_persisted": False,
    }
    if not (
        checks["live_read_only_profile_selected"]
        and checks["no_trading_authority_selected"]
        and checks["binance_credentials_structurally_absent"]
    ):
        raise PublicConnectivityProbeError("READ_ONLY_CONFIGURATION_REQUIRED")
    resolver = executor_secret_resolver(keyring.get_keyring(), role_settings)
    proxy_reference = role_settings.executor.runtime_proxy_reference
    proxy_secret = (
        resolver.resolve(proxy_reference) if proxy_reference is not None else None
    )
    proxy_url = proxy_secret.get_secret_value() if proxy_secret is not None else None
    try:
        observations = probe_public_endpoints(proxy_url=proxy_url)
    finally:
        proxy_url = None
        proxy_secret = None
    checks.update(
        {
            "time_endpoint_http_200": observations["time_http_status"] == 200,
            "exchange_info_endpoint_http_200": (
                observations["exchange_info_http_status"] == 200
            ),
            "server_time_shape_valid": observations["server_time_integer"] is True,
            "btcusdt_perpetual_trading_contract_observed": (
                observations["btcusdt_symbol_present"] is True
                and observations["btcusdt_contract_type"] == "PERPETUAL"
                and observations["btcusdt_status"] == "TRADING"
            ),
            "no_venue_write_performed": True,
            "no_secret_value_persisted": True,
        }
    )
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "operation": "BINANCE_PUBLIC_READ_ONLY_CONNECTIVITY",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "QUALIFIED" if all(checks.values()) else "REJECTED",
        "checks": checks,
        "observations": {
            **observations,
            "configuration_digest": settings_digest(settings),
            "proxy_reference_present": proxy_reference is not None,
        },
        "network_scope": "TWO_PUBLIC_GET_REQUESTS_NO_AUTHENTICATION_NO_VENUE_WRITE",
        "runtime_real_write_gate": "CLOSED",
        "contains_secret": False,
        "source_sha256": {
            "tools/qualification/probe_live_read_only_public_connectivity.py": (
                _sha256_file(Path(__file__))
            ),
            "src/halpha/winvault.py": _sha256_file(ROOT / "src/halpha/winvault.py"),
        },
        "superseded_by": None,
    }
    evidence["evidence_digest"] = content_digest(evidence)
    return evidence


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise PublicConnectivityProbeError("OUTPUT_OUTSIDE_REPOSITORY")
    try:
        evidence = probe(args.config.resolve())
    except Exception as exc:
        reason = (
            str(exc)
            if isinstance(exc, PublicConnectivityProbeError)
            else f"PUBLIC_CONNECTIVITY_FAILED type={type(exc).__name__}"
        )
        evidence = {
            "schema_version": 1,
            "operation": "BINANCE_PUBLIC_READ_ONLY_CONNECTIVITY",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": "REJECTED",
            "reason": reason,
            "runtime_real_write_gate": "CLOSED",
            "contains_secret": False,
        }
        evidence["evidence_digest"] = content_digest(evidence)
    _write_json(output, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
