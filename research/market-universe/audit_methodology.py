from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def count(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(row[field] for row in rows).items()))


def main() -> None:
    csv_path = ROOT / "universe.csv"
    summary = json.loads((ROOT / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "source_manifest.json").read_text(encoding="utf-8"))
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    active = [row for row in rows if row["currently_trading"] == "True"]

    null_profile: dict[str, dict[str, object]] = {}
    for market in sorted({row["market"] for row in active}):
        market_rows = [row for row in active if row["market"] == market]
        null_profile[market] = {
            "rows": len(market_rows),
            "missing_onboard_date": sum(not row["onboard_date_utc"] for row in market_rows),
            "missing_activity_proxy": sum(
                not row["activity_notional_24h_usd_proxy"] for row in market_rows
            ),
            "missing_top_of_book_spread": sum(
                not row["relative_spread_bps"] for row in market_rows
            ),
        }

    native_unrated = [
        row
        for row in active
        if row["economic_exposure"] == "CRYPTO_NATIVE"
        and row["activity_proxy_source"] == "UNAVAILABLE_REQUIRES_QUOTE_CONVERSION"
    ]
    tradfi_identity_required = [
        row
        for row in active
        if row["research_bucket"] == "TRADFI_EQUITY_OR_FUND_PERP"
    ]
    defaulted_exposure = [
        row
        for row in active
        if row["economic_exposure_source"]
        == "DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS"
    ]

    source_paths = {
        (source["market"], source["name"]): Path(source["cache_path"])
        for source in manifest["sources"]
    }
    coin_exchange = json.loads(
        source_paths[("BINANCE_COIN_M", "exchange_info")].read_text(encoding="utf-8")
    )
    coin_tickers = json.loads(
        source_paths[("BINANCE_COIN_M", "ticker_24h")].read_text(encoding="utf-8")
    )
    contract_sizes = {
        symbol["symbol"]: Decimal(str(symbol["contractSize"]))
        for symbol in coin_exchange["symbols"]
        if symbol.get("symbol") and symbol.get("contractSize") is not None
    }
    coin_proxy_differences: list[Decimal] = []
    for ticker in coin_tickers:
        contract_size = contract_sizes.get(ticker.get("symbol"))
        if contract_size is None:
            continue
        face_notional = Decimal(str(ticker["volume"])) * contract_size
        base_value_proxy = Decimal(str(ticker["baseVolume"])) * Decimal(
            str(ticker["weightedAvgPrice"])
        )
        if face_notional > 0 and base_value_proxy > 0:
            coin_proxy_differences.append(abs(face_notional / base_value_proxy - 1))
    coin_proxy_differences.sort()
    coin_proxy_crosscheck = {
        "matched_tickers": len(coin_proxy_differences),
        "median_relative_difference_vs_base_volume_x_weighted_average_price": float(
            coin_proxy_differences[len(coin_proxy_differences) // 2]
        ),
        "max_relative_difference_vs_base_volume_x_weighted_average_price": float(
            max(coin_proxy_differences)
        ),
    }

    invariants = {
        "current_market_symbol_key_unique": len(rows)
        == len({(row["market"], row["symbol"]) for row in rows}),
        "summary_row_count_reconciles": len(rows) == summary["all_records"],
        "summary_active_count_reconciles": len(active)
        == summary["currently_trading_records"],
        "csv_hash_reconciles": sha256(csv_path) == summary["csv"]["sha256"],
        "no_discovery_bucket_claims_liquidity_or_speculation": not any(
            "LIQUID" in row["research_bucket"]
            or "SPECULATIVE" in row["research_bucket"]
            for row in active
        ),
        "coin_m_has_comparable_usd_face_activity_proxy": all(
            row["activity_proxy_source"]
            == "COIN_M_CONTRACT_VOLUME_X_USD_FACE_CONTRACT_SIZE"
            for row in active
            if row["market"] == "BINANCE_COIN_M"
        ),
        "coin_m_face_activity_proxy_crosschecks_raw_ticker_fields": (
            coin_proxy_crosscheck["matched_tickers"]
            == sum(row["market"] == "BINANCE_COIN_M" for row in active)
            and coin_proxy_crosscheck[
                "max_relative_difference_vs_base_volume_x_weighted_average_price"
            ]
            < 0.001
        ),
        "unconverted_quote_activity_does_not_imply_thinness": all(
            row["research_bucket"] == "CRYPTO_ALT_MARKET_QUALITY_UNRATED"
            for row in native_unrated
        ),
        "tradfi_equity_fund_requires_identity_gate": all(
            row["research_eligibility"]
            == "REFERENCE_PRODUCT_IDENTITY_AND_30_90D_MARKET_QUALITY_REQUIRED_BEFORE_STRATEGY_RESEARCH"
            for row in tradfi_identity_required
        ),
    }
    assert all(invariants.values()), invariants

    result = {
        "status": "PASS_WITH_SCOPE_LIMITS",
        "conclusion": "SUPPORTS_WITHIN_SCOPE",
        "intended_use": "current-instrument discovery and research-method routing only",
        "not_supported_uses": [
            "historical point-in-time cross-sectional universe",
            "long-term liquidity or capacity conclusion",
            "manipulation finding",
            "strategy profitability or Alpha conclusion",
            "automatic product eligibility",
        ],
        "input": {
            "snapshot_id": summary["snapshot_id"],
            "csv_sha256": sha256(csv_path),
            "all_rows": len(rows),
            "currently_trading_rows": len(active),
        },
        "pre_revision_evidence": {
            "csv_sha256": "d4284afb113b8bf7f8569d3f81c20dd7e83669b1b77c5c06e9353865b647bcb3",
            "active_non_dollar_like_or_uncomparable_rows": 590,
            "rows_then_labeled_crypto_speculative_or_thin": 534,
            "coin_m_rows_missing_quote_volume": 30,
            "coin_m_non_anchor_rows_then_labeled_crypto_speculative_or_thin": 24,
            "spot_rows_missing_onboard_date": 1366,
            "spot_rows_then_labeled_crypto_liquid_alt": 304,
            "smallest_forced_percentile_group_rows": 3,
        },
        "current_profile": {
            "nulls_by_market": null_profile,
            "research_buckets": count(active, "research_bucket"),
            "activity_tiers": count(active, "activity_tier_24h"),
            "market_integrity_review": count(active, "market_integrity_review"),
            "economic_exposure_source": count(active, "economic_exposure_source"),
            "crypto_native_unrated_pending_quote_conversion": len(native_unrated),
            "tradfi_equity_or_fund_pending_reference_identity": len(
                tradfi_identity_required
            ),
            "default_crypto_native_taxonomy_rows": len(defaulted_exposure),
            "coin_m_face_activity_proxy_crosscheck": coin_proxy_crosscheck,
        },
        "invariants": invariants,
        "remaining_material_limits": [
            "The snapshot is current-state only; point-in-time membership and delisting history are absent.",
            "Activity tiers use one rolling 24-hour window and one top-of-book snapshot; each study must confirm 30-90 day persistence, costs and intended-order-size impact.",
            "Spot exchangeInfo has no onboard date and no authoritative economic taxonomy.",
            "Default CRYPTO_NATIVE exposure is an explicit exclusion-based fallback, not official asset taxonomy.",
            "TradFi equity/fund instruments remain blocked until the reference product type and corporate-action treatment are verified.",
            "Market-integrity review levels define evidence requirements and cannot establish manipulation.",
        ],
        "validation_rating": "READY_FOR_DISCOVERY_ROUTING_WITH_CAVEATS_NOT_READY_AS_A_HISTORICAL_RESEARCH_UNIVERSE",
    }
    (ROOT / "methodology_audit.json").write_bytes(
        (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
