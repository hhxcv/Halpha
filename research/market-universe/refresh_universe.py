from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


USER_AGENT = "HalphaResearchMarketUniverse/1.0"
DOLLAR_LIKE_QUOTES = {
    "BUSD",
    "DAI",
    "FDUSD",
    "RLUSD",
    "TUSD",
    "U",
    "USD",
    "USDC",
    "USDP",
    "USDS",
    "USDT",
    "USD1",
}
STABLE_OR_FIAT_ASSETS = DOLLAR_LIKE_QUOTES | {
    "AEUR",
    "BRL",
    "EURI",
    "EUR",
    "GBP",
    "JPY",
    "TRY",
}
TOKENIZED_COMMODITY_ASSETS = {"PAXG", "XAUT"}
ANCHOR_ASSETS = {"BTC", "ETH"}
NON_ECONOMIC_CLASSIFICATION_SUBTYPES = {"Cross Pair", "USDC"}
MIN_ACTIVITY_COMPARISON_GROUP = 20

SOURCES: dict[str, dict[str, str]] = {
    "BINANCE_SPOT": {
        "exchange_info": "https://api.binance.com/api/v3/exchangeInfo",
        "ticker_24h": "https://api.binance.com/api/v3/ticker/24hr",
        "book_ticker": "https://api.binance.com/api/v3/ticker/bookTicker",
    },
    "BINANCE_USD_M": {
        "exchange_info": "https://fapi.binance.com/fapi/v1/exchangeInfo",
        "ticker_24h": "https://fapi.binance.com/fapi/v1/ticker/24hr",
        "book_ticker": "https://fapi.binance.com/fapi/v1/ticker/bookTicker",
    },
    "BINANCE_COIN_M": {
        "exchange_info": "https://dapi.binance.com/dapi/v1/exchangeInfo",
        "ticker_24h": "https://dapi.binance.com/dapi/v1/ticker/24hr",
        "book_ticker": "https://dapi.binance.com/dapi/v1/ticker/bookTicker",
    },
}

FIELDNAMES = [
    "snapshot_time_utc",
    "market",
    "symbol",
    "status",
    "currently_trading",
    "base_asset",
    "quote_asset",
    "margin_asset",
    "contract_type",
    "contract_size",
    "underlying_type",
    "underlying_subtypes",
    "classification_subtypes",
    "classification_subtype_source",
    "onboard_date_utc",
    "age_days",
    "delivery_date_utc",
    "tick_size",
    "step_size",
    "min_qty",
    "min_notional",
    "ticker_volume_24h_raw",
    "quote_volume_24h",
    "activity_notional_24h_usd_proxy",
    "activity_proxy_source",
    "trade_count_24h",
    "bid_price",
    "ask_price",
    "relative_spread_bps",
    "activity_tier_24h",
    "market_quality_evidence",
    "economic_exposure",
    "economic_exposure_source",
    "research_bucket",
    "research_eligibility",
    "market_integrity_review",
    "risk_flags",
    "method_profile",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh the point-in-time Binance research instrument universe."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--cache-root",
        type=Path,
        help="Git-external directory for immutable raw public endpoint responses.",
    )
    source_group.add_argument(
        "--raw-cache-dir",
        type=Path,
        help="Replay one previously saved raw response snapshot without network access.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory for the normalized CSV, summary and source manifest.",
    )
    return parser.parse_args()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_json(url: str) -> tuple[Any, bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        headers = {
            "date": response.headers.get("Date", ""),
            "etag": response.headers.get("ETag", ""),
            "last_modified": response.headers.get("Last-Modified", ""),
        }
    return json.loads(raw), raw, headers


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def decimal_text(value: Any) -> str:
    parsed = decimal_or_none(value)
    return "" if parsed is None else format(parsed, "f")


def timestamp_text(value: Any) -> str:
    parsed = decimal_or_none(value)
    if parsed is None or parsed <= 0:
        return ""
    return datetime.fromtimestamp(float(parsed) / 1000.0, tz=UTC).isoformat().replace(
        "+00:00", "Z"
    )


def filter_value(symbol: dict[str, Any], filter_type: str, *keys: str) -> str:
    for item in symbol.get("filters", []):
        if item.get("filterType") == filter_type:
            for key in keys:
                if key in item:
                    return decimal_text(item[key])
    return ""


def current_status(market: str, symbol: dict[str, Any]) -> tuple[str, bool]:
    status = (
        symbol.get("contractStatus", "")
        if market == "BINANCE_COIN_M"
        else symbol.get("status", "")
    )
    return str(status), status == "TRADING"


def ticker_maps(payload: Any) -> dict[str, dict[str, Any]]:
    rows = payload if isinstance(payload, list) else [payload]
    return {str(row["symbol"]): row for row in rows if isinstance(row, dict) and row.get("symbol")}


def spread_bps(book: dict[str, Any]) -> str:
    bid = decimal_or_none(book.get("bidPrice"))
    ask = decimal_or_none(book.get("askPrice"))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return ""
    mid = (bid + ask) / 2
    return format(((ask - bid) / mid) * Decimal(10_000), ".8f")


def base_exposure(row: dict[str, Any]) -> str:
    base = row["base_asset"]
    underlying_type = row["underlying_type"]
    contract_type = row["contract_type"]

    if contract_type == "TRADIFI_PERPETUAL":
        if underlying_type == "COMMODITY":
            return "TRADFI_DERIVATIVE_COMMODITY"
        if underlying_type in {"EQUITY", "KR_EQUITY", "HK_EQUITY"}:
            return "TRADFI_DERIVATIVE_EQUITY_OR_FUND"
        if underlying_type == "INDEX":
            return "TRADFI_DERIVATIVE_INDEX"
        if underlying_type == "PREMARKET":
            return "TRADFI_DERIVATIVE_PREMARKET"
        return "TRADFI_DERIVATIVE_OTHER"
    if base in TOKENIZED_COMMODITY_ASSETS:
        return "TOKENIZED_COMMODITY"
    if base in ANCHOR_ASSETS:
        return "CRYPTO_ANCHOR"
    if base in STABLE_OR_FIAT_ASSETS:
        return "STABLE_OR_FIAT_RELATIVE"
    return "CRYPTO_NATIVE"


def economic_exposure_source(row: dict[str, Any], exposure: str) -> str:
    if exposure.startswith("TRADFI_DERIVATIVE_"):
        return "CURRENT_INSTRUMENT_OFFICIAL_METADATA"
    if exposure == "CRYPTO_ANCHOR":
        return "EXPLICIT_BTC_ETH_MODELING_ROLE"
    if exposure == "TOKENIZED_COMMODITY":
        return "EXPLICIT_ISSUER_AND_REFERENCE_MAPPING"
    if exposure == "STABLE_OR_FIAT_RELATIVE":
        return "EXPLICIT_STABLE_OR_FIAT_MAPPING"
    return "DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS"


def assign_activity_tiers(rows: list[dict[str, Any]]) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row["currently_trading"]:
            continue
        value = decimal_or_none(row["activity_notional_24h_usd_proxy"])
        if value is not None and value > 0:
            groups[row["market"]].append(row)

    for group in groups.values():
        if len(group) < MIN_ACTIVITY_COMPARISON_GROUP:
            for row in group:
                row["activity_tier_24h"] = "UNRATED_SMALL_COMPARISON_GROUP"
            continue
        group.sort(
            key=lambda row: (
                -(decimal_or_none(row["activity_notional_24h_usd_proxy"]) or Decimal(0)),
                row["symbol"],
            )
        )
        count = len(group)
        for index, row in enumerate(group):
            percentile = (index + 1) / count
            if percentile <= 0.10:
                row["activity_tier_24h"] = "A1_TOP_10PCT_PROVISIONAL_24H"
            elif percentile <= 0.40:
                row["activity_tier_24h"] = "A2_10_TO_40PCT_PROVISIONAL_24H"
            elif percentile <= 0.80:
                row["activity_tier_24h"] = "A3_40_TO_80PCT_PROVISIONAL_24H"
            else:
                row["activity_tier_24h"] = "A4_BOTTOM_20PCT_PROVISIONAL_24H"


def enrich_classification_subtypes(rows: list[dict[str, Any]]) -> None:
    known_bases = {row["base_asset"] for row in rows}
    usd_m_subtypes: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["market"] != "BINANCE_USD_M" or not row["currently_trading"]:
            continue
        subtypes = set(filter(None, row["underlying_subtypes"].split("|"))) - NON_ECONOMIC_CLASSIFICATION_SUBTYPES
        if not subtypes:
            continue
        base = row["base_asset"]
        usd_m_subtypes[base].update(subtypes)
        for prefix in ("1000000", "1000", "1M"):
            if base.startswith(prefix) and base[len(prefix) :] in known_bases:
                usd_m_subtypes[base[len(prefix) :]].update(subtypes)

    for row in rows:
        own = set(filter(None, row["underlying_subtypes"].split("|"))) - NON_ECONOMIC_CLASSIFICATION_SUBTYPES
        if own:
            row["classification_subtypes"] = "|".join(sorted(own))
            row["classification_subtype_source"] = "CURRENT_INSTRUMENT_OFFICIAL_METADATA"
        elif usd_m_subtypes.get(row["base_asset"]):
            row["classification_subtypes"] = "|".join(
                sorted(usd_m_subtypes[row["base_asset"]])
            )
            row["classification_subtype_source"] = "CURRENT_USD_M_SAME_UNDERLYING_PROXY"
        else:
            row["classification_subtypes"] = ""
            row["classification_subtype_source"] = "UNKNOWN"


def method_classification(row: dict[str, Any]) -> None:
    exposure = row["economic_exposure"]
    tier = row["activity_tier_24h"]
    subtypes = set(filter(None, row["classification_subtypes"].split("|")))
    age_days = int(row["age_days"]) if row["age_days"] else None
    spread = decimal_or_none(row["relative_spread_bps"])
    flags: list[str] = []

    if not row["currently_trading"]:
        flags.append("NOT_CURRENTLY_TRADING")
    if row["activity_proxy_source"] == "UNAVAILABLE_REQUIRES_QUOTE_CONVERSION":
        flags.append("ACTIVITY_PROXY_UNAVAILABLE_REQUIRES_QUOTE_CONVERSION")
    if (
        row["activity_proxy_source"] == "QUOTE_VOLUME_IN_DOLLAR_LIKE_QUOTE_PROXY"
        and row["quote_asset"] != "USD"
    ):
        flags.append("DOLLAR_LIKE_QUOTE_PARITY_ASSUMPTION_FOR_ACTIVITY_PROXY")
    if tier == "A4_BOTTOM_20PCT_PROVISIONAL_24H":
        flags.append("LOWER_RELATIVE_24H_ACTIVITY_NOT_LONG_TERM_LIQUIDITY")
    if tier.startswith("A"):
        flags.extend(["SINGLE_24H_ACTIVITY_ONLY", "SINGLE_TOP_OF_BOOK_SNAPSHOT_ONLY"])
    if row["market"] == "BINANCE_SPOT" and not row["onboard_date_utc"]:
        flags.append("ONBOARD_DATE_UNAVAILABLE_FROM_SPOT_EXCHANGE_INFO")
    if row["economic_exposure_source"] == "DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS":
        flags.append("ECONOMIC_EXPOSURE_DEFAULTED_NOT_OFFICIAL_TAXONOMY")
    if spread is None:
        flags.append("TOP_OF_BOOK_SPREAD_UNAVAILABLE")
    if spread is not None and spread > Decimal(20):
        flags.append("WIDE_TOP_OF_BOOK_GT_20BPS")
    if age_days is not None and age_days < 180:
        flags.append("NEW_LT_180D")
    elif age_days is not None and age_days < 365:
        flags.append("SHORT_HISTORY_LT_365D")
    if "Meme" in subtypes:
        flags.append("OFFICIAL_MEME_SUBTYPE")
    if "Alpha" in subtypes:
        flags.append("OFFICIAL_BINANCE_ALPHA_SUBTYPE")
    if row["classification_subtype_source"] == "CURRENT_USD_M_SAME_UNDERLYING_PROXY":
        flags.append("CROSS_MARKET_SUBTYPE_FROM_CURRENT_USD_M")
    if exposure.startswith("TRADFI_DERIVATIVE_"):
        flags.extend(["TRADFI_REFERENCE_DERIVATIVE", "REFERENCE_PRODUCT_DETAIL_REVIEW_REQUIRED"])
    if exposure in {"TRADFI_DERIVATIVE_EQUITY_OR_FUND", "TRADFI_DERIVATIVE_COMMODITY"}:
        flags.append("UNDERLYING_CLOSED_SESSION_GAP_AND_BASIS_RISK")
    if exposure == "TRADFI_DERIVATIVE_PREMARKET":
        flags.append("PREMARKET_REFERENCE_AND_PRICE_DISCOVERY_RISK")
    if exposure == "TOKENIZED_COMMODITY":
        flags.append("TOKEN_ISSUER_RESERVE_REDEMPTION_AND_TRACKING_RISK")

    if not row["currently_trading"]:
        bucket = "INACTIVE_OR_DELISTED_RECORD"
        eligibility = "NOT_CURRENT"
        method = "retain for survivorship-bias context; do not enter the current tradable screen"
    elif exposure == "CRYPTO_ANCHOR":
        bucket = "CRYPTO_ANCHOR_REFERENCE"
        eligibility = "REFERENCE_ALLOWED_STRATEGY_REQUIRES_30_90D_MARKET_QUALITY_AND_COST_GATE"
        method = "time-series and cross-market reference; multi-regime costs, funding and beta controls; anchor is a modeling role, not a safety claim"
    elif exposure == "CRYPTO_NATIVE" and age_days is not None and age_days < 180:
        bucket = "CRYPTO_ALT_NEW_OR_EVENT_DRIVEN"
        eligibility = "EVENT_OR_LISTING_EXPLORATION_ONLY"
        method = "listing/event study with point-in-time availability, extreme costs and single-event concentration checks"
    elif exposure == "CRYPTO_NATIVE" and tier in {
        "A1_TOP_10PCT_PROVISIONAL_24H",
        "A2_10_TO_40PCT_PROVISIONAL_24H",
    }:
        bucket = "CRYPTO_ALT_HIGHER_ACTIVITY_PROVISIONAL"
        eligibility = "CANDIDATE_AFTER_30_90D_MARKET_QUALITY_GATE"
        method = "cross-sectional and time-series tests after history gate; control market beta, size, momentum, liquidity and single-asset concentration"
    elif exposure == "CRYPTO_NATIVE" and tier == "A3_40_TO_80PCT_PROVISIONAL_24H":
        bucket = "CRYPTO_ALT_MID_ACTIVITY_PROVISIONAL"
        eligibility = "SELECTIVE_AFTER_30_90D_MARKET_QUALITY_GATE"
        method = "selective trend, carry or event tests after history gate; stronger cost, concentration, delisting and regime checks"
    elif exposure == "CRYPTO_NATIVE" and tier == "A4_BOTTOM_20PCT_PROVISIONAL_24H":
        bucket = "CRYPTO_ALT_LOWER_ACTIVITY_PROVISIONAL"
        eligibility = "EXPLORATION_ONLY_UNTIL_30_90D_MARKET_QUALITY_EVIDENCE"
        method = "market-quality or event exploration; trade/book evidence and extreme cost stress before executable claims"
    elif exposure == "CRYPTO_NATIVE":
        bucket = "CRYPTO_ALT_MARKET_QUALITY_UNRATED"
        eligibility = "QUOTE_CONVERSION_AND_30_90D_MARKET_QUALITY_REQUIRED"
        method = "resolve quote conversion and comparable activity units before choosing a strategy method; do not infer thinness or speculation"
    elif exposure == "TOKENIZED_COMMODITY":
        bucket = "TOKENIZED_COMMODITY"
        eligibility = "TOKEN_REFERENCE_AND_30_90D_MARKET_QUALITY_REQUIRED"
        method = "underlying benchmark plus token tracking, issuer, reserve, redemption, venue and quote-risk tests"
    elif exposure == "STABLE_OR_FIAT_RELATIVE":
        bucket = "STABLE_OR_FIAT_RELATIVE"
        eligibility = "PEG_REFERENCE_AND_30_90D_MARKET_QUALITY_REQUIRED"
        method = "peg, reserve or FX-reference research with quote conversion, depeg tails and venue-fragmentation tests"
    elif exposure == "TRADFI_DERIVATIVE_COMMODITY":
        bucket = "TRADFI_COMMODITY_PERP"
        eligibility = "REFERENCE_CONTRACT_AND_30_90D_MARKET_QUALITY_REQUIRED"
        method = "primary benchmark/calendar plus Binance basis, funding, EWMA/index and closed-session gap tests"
    elif exposure == "TRADFI_DERIVATIVE_EQUITY_OR_FUND":
        bucket = "TRADFI_EQUITY_OR_FUND_PERP"
        eligibility = "REFERENCE_PRODUCT_IDENTITY_AND_30_90D_MARKET_QUALITY_REQUIRED_BEFORE_STRATEGY_RESEARCH"
        method = "first identify single stock, ordinary fund, leveraged/inverse fund or other reference; then use primary security/calendar/corporate-actions data plus Binance basis, funding and overnight-gap tests"
    elif exposure == "TRADFI_DERIVATIVE_INDEX":
        bucket = "TRADFI_INDEX_PERP"
        eligibility = "INDEX_METHODOLOGY_AND_30_90D_MARKET_QUALITY_REQUIRED"
        method = "official index methodology and session data plus Binance basis, funding and replication tests"
    elif exposure == "TRADFI_DERIVATIVE_PREMARKET":
        bucket = "TRADFI_PREMARKET_PERP"
        eligibility = "EXPLORATION_ONLY"
        method = "event and price-discovery research only; no primary-history or fair-value equivalence assumption"
    else:
        bucket = "OTHER_OR_UNCLASSIFIED"
        eligibility = "REQUIRES_MANUAL_SCOPE"
        method = "define economic exposure and reference source before strategy research"

    if "Meme" in subtypes and bucket in {
        "CRYPTO_ALT_HIGHER_ACTIVITY_PROVISIONAL",
        "CRYPTO_ALT_MID_ACTIVITY_PROVISIONAL",
    }:
        eligibility += "_WITH_THEME_AND_MARKET_QUALITY_GUARD"
        method += "; add meme/event concentration, crowding and market-integrity counterevidence"

    elevated = {
        "LOWER_RELATIVE_24H_ACTIVITY_NOT_LONG_TERM_LIQUIDITY",
        "WIDE_TOP_OF_BOOK_GT_20BPS",
        "NEW_LT_180D",
        "OFFICIAL_MEME_SUBTYPE",
        "PREMARKET_REFERENCE_AND_PRICE_DISCOVERY_RISK",
    }.intersection(flags)
    if "NOT_CURRENTLY_TRADING" in flags:
        market_integrity_review = "NOT_APPLICABLE_CURRENTLY"
    elif len(elevated) >= 2 or "PREMARKET_REFERENCE_AND_PRICE_DISCOVERY_RISK" in elevated:
        market_integrity_review = "FORENSIC_EVIDENCE_REQUIRED_FOR_INTEGRITY_CLAIMS"
    elif elevated:
        market_integrity_review = "ENHANCED_DUE_DILIGENCE"
    else:
        market_integrity_review = "STANDARD_DUE_DILIGENCE"

    row["research_bucket"] = bucket
    row["research_eligibility"] = eligibility
    row["market_integrity_review"] = market_integrity_review
    row["risk_flags"] = "|".join(sorted(set(flags)))
    row["method_profile"] = method


def normalize_symbol(
    market: str,
    symbol: dict[str, Any],
    ticker: dict[str, Any],
    book: dict[str, Any],
    snapshot_time: datetime,
) -> dict[str, Any]:
    status, trading = current_status(market, symbol)
    onboard_date = timestamp_text(symbol.get("onboardDate"))
    age_days = ""
    if onboard_date:
        onboard = datetime.fromisoformat(onboard_date.replace("Z", "+00:00"))
        age_days = str(max(0, (snapshot_time - onboard).days))

    row: dict[str, Any] = {
        "snapshot_time_utc": snapshot_time.isoformat().replace("+00:00", "Z"),
        "market": market,
        "symbol": str(symbol.get("symbol", "")),
        "status": status,
        "currently_trading": trading,
        "base_asset": str(symbol.get("baseAsset", "")),
        "quote_asset": str(symbol.get("quoteAsset", "")),
        "margin_asset": str(symbol.get("marginAsset", "")),
        "contract_type": "SPOT" if market == "BINANCE_SPOT" else str(symbol.get("contractType", "")),
        "contract_size": decimal_text(symbol.get("contractSize")),
        "underlying_type": "" if market == "BINANCE_SPOT" else str(symbol.get("underlyingType", "")),
        "underlying_subtypes": "|".join(sorted(map(str, symbol.get("underlyingSubType", [])))),
        "classification_subtypes": "",
        "classification_subtype_source": "UNKNOWN",
        "onboard_date_utc": onboard_date,
        "age_days": age_days,
        "delivery_date_utc": "" if market == "BINANCE_SPOT" else timestamp_text(symbol.get("deliveryDate")),
        "tick_size": filter_value(symbol, "PRICE_FILTER", "tickSize"),
        "step_size": filter_value(symbol, "LOT_SIZE", "stepSize"),
        "min_qty": filter_value(symbol, "LOT_SIZE", "minQty"),
        "min_notional": filter_value(symbol, "MIN_NOTIONAL", "notional", "minNotional")
        or filter_value(symbol, "NOTIONAL", "notional", "minNotional"),
        "ticker_volume_24h_raw": decimal_text(ticker.get("volume")),
        "quote_volume_24h": decimal_text(ticker.get("quoteVolume")),
        "trade_count_24h": str(ticker.get("count", "")),
        "bid_price": decimal_text(book.get("bidPrice")),
        "ask_price": decimal_text(book.get("askPrice")),
        "relative_spread_bps": spread_bps(book),
        "activity_tier_24h": "UNRATED_REQUIRES_QUOTE_CONVERSION_OR_ACTIVITY_PROXY",
        "market_quality_evidence": "UNRATED_REQUIRES_HISTORY",
    }
    if not trading:
        row["activity_notional_24h_usd_proxy"] = ""
        row["activity_proxy_source"] = "NOT_CURRENT"
        row["activity_tier_24h"] = "NOT_CURRENT"
        row["market_quality_evidence"] = "NOT_CURRENT"
    elif market == "BINANCE_COIN_M":
        contract_volume = decimal_or_none(ticker.get("volume"))
        contract_size = decimal_or_none(symbol.get("contractSize"))
        if contract_volume is not None and contract_size is not None and contract_size > 0:
            row["activity_notional_24h_usd_proxy"] = format(contract_volume * contract_size, "f")
            row["activity_proxy_source"] = "COIN_M_CONTRACT_VOLUME_X_USD_FACE_CONTRACT_SIZE"
        else:
            row["activity_notional_24h_usd_proxy"] = ""
            row["activity_proxy_source"] = "UNAVAILABLE_REQUIRES_QUOTE_CONVERSION"
    elif row["quote_asset"] in DOLLAR_LIKE_QUOTES:
        row["activity_notional_24h_usd_proxy"] = row["quote_volume_24h"]
        row["activity_proxy_source"] = "QUOTE_VOLUME_IN_DOLLAR_LIKE_QUOTE_PROXY"
    else:
        row["activity_notional_24h_usd_proxy"] = ""
        row["activity_proxy_source"] = "UNAVAILABLE_REQUIRES_QUOTE_CONVERSION"
    row["economic_exposure"] = base_exposure(row)
    row["economic_exposure_source"] = economic_exposure_source(
        row, row["economic_exposure"]
    )
    return row


def counter(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    values = Counter(str(row[field]) for row in rows)
    return dict(sorted(values.items()))


def write_json(path: Path, payload: Any) -> bytes:
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    replay = args.raw_cache_dir is not None
    prior_sources: dict[str, dict[str, Any]] = {}
    if replay:
        cache_dir = args.raw_cache_dir.resolve()
        if not cache_dir.is_dir():
            raise FileNotFoundError(cache_dir)
        snapshot_id = cache_dir.name
        snapshot_time = datetime.strptime(snapshot_id, "%Y-%m-%dT%H%M%SZ").replace(tzinfo=UTC)
        existing_manifest = output_dir / "source_manifest.json"
        if existing_manifest.is_file():
            prior = json.loads(existing_manifest.read_text(encoding="utf-8"))
            if Path(prior.get("raw_cache_root", "")).resolve() == cache_dir:
                prior_sources = {
                    str(Path(item["cache_path"]).resolve()): item for item in prior.get("sources", [])
                }
    else:
        snapshot_time = datetime.now(tz=UTC).replace(microsecond=0)
        snapshot_id = snapshot_time.strftime("%Y-%m-%dT%H%M%SZ")
        cache_dir = args.cache_root.resolve() / snapshot_id
        cache_dir.mkdir(parents=True, exist_ok=False)

    payloads: dict[str, dict[str, Any]] = defaultdict(dict)
    source_manifest: dict[str, Any] = {
        "generation_mode": "RAW_CACHE_REPLAY" if replay else "LIVE_PUBLIC_ENDPOINTS",
        "snapshot_id": snapshot_id,
        "snapshot_time_utc": snapshot_time.isoformat().replace("+00:00", "Z"),
        "raw_cache_root": str(cache_dir),
        "sources": [],
    }

    for market, endpoints in SOURCES.items():
        for name, url in endpoints.items():
            cache_path = cache_dir / f"{market.lower()}-{name}.json"
            if replay:
                raw = cache_path.read_bytes()
                payload = json.loads(raw)
                headers = prior_sources.get(str(cache_path.resolve()), {}).get(
                    "response_headers", {}
                )
            else:
                payload, raw, headers = fetch_json(url)
                cache_path.write_bytes(raw)
            payloads[market][name] = payload
            source_manifest["sources"].append(
                {
                    "market": market,
                    "name": name,
                    "url": url,
                    "bytes": len(raw),
                    "sha256": sha256(raw),
                    "cache_path": str(cache_path),
                    "response_headers": headers,
                }
            )

    rows: list[dict[str, Any]] = []
    for market in SOURCES:
        exchange_info = payloads[market]["exchange_info"]
        tickers = ticker_maps(payloads[market]["ticker_24h"])
        books = ticker_maps(payloads[market]["book_ticker"])
        for symbol in exchange_info.get("symbols", []):
            name = str(symbol.get("symbol", ""))
            rows.append(
                normalize_symbol(
                    market,
                    symbol,
                    tickers.get(name, {}),
                    books.get(name, {}),
                    snapshot_time,
                )
            )

    enrich_classification_subtypes(rows)
    assign_activity_tiers(rows)
    for row in rows:
        if row["activity_tier_24h"].startswith("A"):
            row["market_quality_evidence"] = "PROVISIONAL_SINGLE_24H_ACTIVITY_AND_SINGLE_BOOK_SNAPSHOT"
        method_classification(row)
    rows.sort(key=lambda row: (row["market"], row["symbol"]))

    csv_path = output_dir / "universe.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=FIELDNAMES,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    csv_raw = csv_path.read_bytes()

    active_rows = [row for row in rows if row["currently_trading"]]
    summary = {
        "conclusion": "SUPPORTS_WITHIN_SCOPE",
        "scope": "Binance Spot, USD-M and COIN-M instruments returned by official public exchangeInfo endpoints",
        "snapshot_id": snapshot_id,
        "snapshot_time_utc": snapshot_time.isoformat().replace("+00:00", "Z"),
        "all_records": len(rows),
        "currently_trading_records": len(active_rows),
        "counts_by_market_all": counter(rows, "market"),
        "counts_by_market_currently_trading": counter(active_rows, "market"),
        "counts_by_research_bucket_currently_trading": counter(active_rows, "research_bucket"),
        "counts_by_activity_tier_currently_trading": counter(
            active_rows, "activity_tier_24h"
        ),
        "counts_by_economic_exposure_currently_trading": counter(active_rows, "economic_exposure"),
        "counts_by_economic_exposure_source_currently_trading": counter(
            active_rows, "economic_exposure_source"
        ),
        "counts_by_market_integrity_review_currently_trading": counter(
            active_rows, "market_integrity_review"
        ),
        "csv": {
            "path": str(csv_path),
            "bytes": len(csv_raw),
            "rows_excluding_header": len(rows),
            "sha256": sha256(csv_raw),
        },
        "important_limitations": [
            "The 24-hour activity tier is a provisional discovery tag, not a liquidity or market-quality conclusion.",
            "Market-integrity review levels are due-diligence requirements and never findings of manipulation.",
            "Spot exchangeInfo has no authoritative asset taxonomy or onboard date.",
            "Current exchangeInfo is not a historical point-in-time universe and cannot by itself remove survivorship bias.",
            "TradFi exchangeInfo does not reliably distinguish a single stock from an ETF or leveraged reference product; each study must verify the official reference contract.",
            "Stable/fiat asset membership is a small explicit research mapping and must be reviewed when Binance adds a new quote or reference asset.",
            "Binance underlyingSubType mixes asset themes with contract markers; classification removes known non-economic markers but preserves the official raw field and its source.",
            "Non-dollar-like quote instruments remain market-quality-unrated until quote conversion and 30-90 day evidence are supplied; they are not inferred to be thin or speculative.",
            "Dollar-like quote volume is only an approximate USD activity proxy and each study must stress quote-asset parity and depeg periods.",
        ],
    }
    summary_raw = write_json(output_dir / "summary.json", summary)
    source_manifest["normalized_outputs"] = [
        {
            "path": str(csv_path),
            "bytes": len(csv_raw),
            "sha256": sha256(csv_raw),
        },
        {
            "path": str(output_dir / "summary.json"),
            "bytes": len(summary_raw),
            "sha256": sha256(summary_raw),
        },
    ]
    write_json(output_dir / "source_manifest.json", source_manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
