from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    csv_path = ROOT / "universe.csv"
    summary_path = ROOT / "summary.json"
    manifest_path = ROOT / "source_manifest.json"

    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    keys = [(row["market"], row["symbol"]) for row in rows]
    assert len(keys) == len(set(keys)), "market/symbol keys must be unique"
    assert len(rows) == summary["all_records"]
    assert sha256(csv_path) == summary["csv"]["sha256"]
    assert summary["conclusion"] == "SUPPORTS_WITHIN_SCOPE"

    active = [row for row in rows if row["currently_trading"] == "True"]
    assert len(active) == summary["currently_trading_records"]
    assert dict(sorted(Counter(row["market"] for row in active).items())) == summary[
        "counts_by_market_currently_trading"
    ]
    assert all(row["research_bucket"] and row["method_profile"] for row in rows)
    assert all(row["classification_subtype_source"] for row in rows)
    assert all(row["economic_exposure_source"] for row in rows)
    assert all(
        row["market_integrity_review"]
        in {
            "NOT_APPLICABLE_CURRENTLY",
            "STANDARD_DUE_DILIGENCE",
            "ENHANCED_DUE_DILIGENCE",
            "FORENSIC_EVIDENCE_REQUIRED_FOR_INTEGRITY_CLAIMS",
        }
        for row in rows
    )
    assert all(
        row["contract_type"] == "TRADIFI_PERPETUAL"
        for row in rows
        if row["economic_exposure"].startswith("TRADFI_DERIVATIVE_")
    )
    assert not any(row["research_bucket"] == "OTHER_OR_UNCLASSIFIED" for row in active)
    assert not any(
        "LIQUID" in row["research_bucket"] or "SPECULATIVE" in row["research_bucket"]
        for row in active
    ), "single-day discovery labels must not claim liquidity or speculation"
    assert all(
        row["activity_proxy_source"] == "COIN_M_CONTRACT_VOLUME_X_USD_FACE_CONTRACT_SIZE"
        and row["activity_notional_24h_usd_proxy"]
        for row in active
        if row["market"] == "BINANCE_COIN_M"
    )
    assert all(
        row["research_bucket"] == "CRYPTO_ALT_MARKET_QUALITY_UNRATED"
        for row in active
        if row["economic_exposure"] == "CRYPTO_NATIVE"
        and row["activity_proxy_source"] == "UNAVAILABLE_REQUIRES_QUOTE_CONVERSION"
    )
    assert all(
        "ECONOMIC_EXPOSURE_DEFAULTED_NOT_OFFICIAL_TAXONOMY"
        in row["risk_flags"].split("|")
        for row in rows
        if row["economic_exposure_source"]
        == "DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS"
    )
    assert all(
        row["market_quality_evidence"]
        == "PROVISIONAL_SINGLE_24H_ACTIVITY_AND_SINGLE_BOOK_SNAPSHOT"
        for row in active
        if row["activity_tier_24h"].startswith("A")
    )
    assert all(
        "DOLLAR_LIKE_QUOTE_PARITY_ASSUMPTION_FOR_ACTIVITY_PROXY"
        in row["risk_flags"].split("|")
        for row in active
        if row["activity_proxy_source"] == "QUOTE_VOLUME_IN_DOLLAR_LIKE_QUOTE_PROXY"
        and row["quote_asset"] != "USD"
    )
    assert all(
        row["research_eligibility"]
        == "REFERENCE_PRODUCT_IDENTITY_AND_30_90D_MARKET_QUALITY_REQUIRED_BEFORE_STRATEGY_RESEARCH"
        for row in active
        if row["research_bucket"] == "TRADFI_EQUITY_OR_FUND_PERP"
    )
    doge_spot = next(
        row for row in active if row["market"] == "BINANCE_SPOT" and row["symbol"] == "DOGEUSDT"
    )
    assert "Meme" in doge_spot["classification_subtypes"].split("|")
    assert "USDC" not in doge_spot["classification_subtypes"].split("|")
    assert doge_spot["classification_subtype_source"] == "CURRENT_USD_M_SAME_UNDERLYING_PROXY"
    assert doge_spot["research_bucket"] in {
        "CRYPTO_ALT_HIGHER_ACTIVITY_PROVISIONAL",
        "CRYPTO_ALT_MID_ACTIVITY_PROVISIONAL",
    }
    assert "OFFICIAL_MEME_SUBTYPE" in doge_spot["risk_flags"].split("|")
    for stable in ("EURI", "RLUSD", "U", "USDS"):
        assert any(row["base_asset"] == stable for row in active)
        assert all(
            row["economic_exposure"] == "STABLE_OR_FIAT_RELATIVE"
            for row in active
            if row["base_asset"] == stable
        )

    source_checks = []
    for source in manifest["sources"]:
        path = Path(source["cache_path"])
        assert path.is_file(), f"missing raw source: {path}"
        actual = sha256(path)
        assert actual == source["sha256"], f"raw source hash mismatch: {path}"
        source_checks.append({"path": str(path), "sha256": actual})

    result = {
        "status": "PASS",
        "rows": len(rows),
        "currently_trading_rows": len(active),
        "unique_market_symbol_keys": len(set(keys)),
        "csv_sha256": sha256(csv_path),
        "raw_sources_verified": len(source_checks),
        "market_integrity_review_is_due_diligence_not_a_finding": True,
        "active_other_or_unclassified": 0,
        "active_coin_m_with_comparable_usd_face_activity_proxy": sum(
            row["market"] == "BINANCE_COIN_M" for row in active
        ),
        "active_crypto_native_unrated_due_quote_conversion": sum(
            row["economic_exposure"] == "CRYPTO_NATIVE"
            and row["activity_proxy_source"] == "UNAVAILABLE_REQUIRES_QUOTE_CONVERSION"
            for row in active
        ),
    }
    (ROOT / "validation.json").write_bytes(
        (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
