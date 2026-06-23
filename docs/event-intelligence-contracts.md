# Event Intelligence Contracts

## Purpose

This document defines Halpha event-intelligence contracts.

It is a durable implementation contract, not a milestone-only plan and not an
implementation record. The contracts may evolve as shipped behavior grows, but
agents should update this document instead of creating milestone-numbered
successor contract files.

Event intelligence turns collected public text events into source-aware,
pretrained-NLP-assisted research artifacts. It does not replace raw text
collection, existing text material, quantitative evidence, strategy gates,
decision intelligence, or Codex report generation.

Target event-intelligence flow:

```text
configured public text sources or local raw text artifact
  -> raw text events
  -> normalized text event records
  -> NLP evidence generation
  -> duplicate and topic grouping
  -> accepted text event signals
  -> event-market confluence
  -> event intelligence assessment
  -> AI-readable event intelligence material
  -> research context
  -> Codex context + prompt
  -> Simplified Chinese Markdown report
```

Event-intelligence outputs are personal research material. They are not trades,
orders, account operations, position sizing, portfolio instructions, return
promises, price forecasts, or financial advice.

## Related Docs

- `docs/artifact-governance.md`: artifact map, layer rules, Codex input policy,
  and documentation index.
- `docs/quant-contracts.md`: upstream market, strategy, evaluation, signal, and
  event-quant confluence consumers.
- `docs/macro-calendar-contracts.md`: macro and scheduled-event context
  contracts for event proximity and report evidence.
- `docs/decision-intelligence-contracts.md`: downstream risk, decision, watch,
  and alert-adjacent contracts.
- `docs/outcome-tracking-contracts.md`: planned downstream target, evaluation,
  history, material, and Codex-boundary contracts.

## Contract Status

This file separates stable direction from shipped behavior.

- `contract`: expected durable interface or rule.
- `initial adoption`: first implementation slice for the active milestone.
- `not implemented yet`: allowed future contract detail that must not be
  described as shipped behavior.

README should describe only user-visible behavior that exists. This file may
define intended contracts before implementation when they are needed to guide a
focused issue.

## Scope

Define contracts for:

- Text-intelligence configuration.
- Optional pretrained NLP runtime boundaries.
- Model preparation and no-hidden-download behavior.
- Normalized text event records.
- NLP evidence records.
- Duplicate and topic grouping.
- Text event signals.
- Event-market confluence artifacts.
- Event intelligence assessment artifacts.
- AI-readable event intelligence material.
- Standalone text-intelligence manifests.
- Research context, Codex context, and report integration.
- Golden corpus and human review expectations.

## Out of Scope

- Code implementation.
- Dependency installation.
- Hosted NLP APIs or remote inference services.
- Training custom NLP, ML, or LLM models from scratch.
- Real-time event streaming.
- Scheduler, daemon, websocket, polling, or alert delivery runtime.
- Kafka, Redis, Celery, vector database, feature store, or database redesign.
- New public text source types.
- Trading execution, order placement, position sizing, or portfolio management.
- Codex-generated event classification, event impact, action levels, or price
  forecasts.

## Technology Boundaries

Event-intelligence artifacts are Halpha-owned JSON and Markdown contracts.
Pretrained NLP models may generate evidence, scores, embeddings, and candidate
labels, but deterministic Halpha gates decide what is accepted, downgraded,
skipped, degraded, or left unknown.

Selected tools are implementation aids, not product architecture boundaries.

| Area | Boundary |
| --- | --- |
| Sentence embeddings | May be used to produce similarity evidence for duplicate and topic grouping. Embedding vectors are model evidence, not stable downstream contract identity. |
| Zero-shot classification | May be used to score fixed taxonomy candidates. Halpha gates decide accepted categories and confidence. |
| Financial tone classification | May be used as bounded tone evidence. Tone is not a trading direction or price forecast. |
| Open entity extraction | May be used to extract organizations, regulators, exchanges, assets, funds, protocols, and other event actors. Halpha gates decide accepted entity and asset relevance. |
| Rules and gates | Halpha-owned deterministic logic remains the final authority for accepted event records, topics, signals, confluence, warnings, and degraded states. |
| Report interface | Halpha-owned JSON and Markdown artifacts are the stable report-loop interface. Codex explains artifacts; it must not invent structured event outputs. |

Do not add a dependency until the current implementation step requires it.

## Dependency Contract

NLP dependencies should be optional. The default Halpha install and non-NLP
tests must not require heavyweight NLP packages.

Initial model roles:

| Role | Candidate dependency or model | Purpose | Boundary |
| --- | --- | --- | --- |
| embedding | `sentence-transformers` with `sentence-transformers/all-MiniLM-L6-v2` | Sentence embeddings for title and content similarity. | Similarity evidence only. No vector database or hidden persistent index. |
| zero-shot classifier | `transformers` with `facebook/bart-large-mnli` | Scores fixed event taxonomy labels. | Candidate classification evidence only. Halpha gates decide final category. |
| financial tone | `transformers` with `ProsusAI/finbert` | Positive, negative, or neutral financial tone evidence. | Tone evidence only. No trading signal or return forecast. |
| entity extraction | `gliner` with `urchade/gliner_medium-v2.1` | Open entity extraction for market actors. | Entity evidence only. Halpha gates decide accepted entities and asset relevance. |

Rules:

- Optional NLP dependencies should live in a dedicated optional dependency
  group.
- Model downloads must be explicit. Normal product runs must not silently
  download model files.
- Local model cache paths are local privacy values and must not be committed or
  printed in network-visible text.
- Artifacts may record model name, provider, revision, task, threshold, and
  status, but not local cache paths.
- If a dependency, model, or model file is unavailable, write `skipped` or
  `degraded` state with warnings rather than fabricated evidence.

Initial model preparation command:

```bash
python -m halpha text-models prepare --config config.example.yaml
```

Initial adoption rules:

- `text-models prepare` is the explicit local model preparation path.
- Normal product runs must not use this command implicitly.
- With `allow_model_download: false`, the command records model metadata and
  skipped model states without downloading model files.
- With `allow_model_download: true`, the command may use `huggingface_hub` to
  download configured model snapshots into the configured local cache.
- Preparation manifests must not record local model cache paths or resolved
  download paths.

## Configuration Contract

Event intelligence extends the existing `text` config.

Contract shape:

```yaml
text:
  enabled: true
  max_items: 30
  intelligence:
    enabled: true
    model_cache_dir: data/models/text
    allow_model_download: false
    models:
      embedding:
        provider: sentence_transformers
        name: sentence-transformers/all-MiniLM-L6-v2
        revision: pinned
      classifier:
        provider: transformers_zero_shot
        name: facebook/bart-large-mnli
        revision: pinned
      sentiment:
        provider: transformers_text_classification
        name: ProsusAI/finbert
        revision: pinned
      ner:
        provider: gliner
        name: urchade/gliner_medium-v2.1
        revision: pinned
    thresholds:
      duplicate_similarity: 0.92
      same_topic_similarity: 0.82
      classifier_accept_score: 0.65
      classifier_top_margin: 0.10
      entity_accept_score: 0.50
      max_topic_window_hours: 48
```

Rules:

- `text.enabled: false` disables event intelligence.
- `text.intelligence.enabled: false` skips event-intelligence artifacts and
  records zero counts.
- Unknown config fields should fail validation once the config shape is
  implemented.
- `allow_model_download: false` is the safe default.
- Model `revision` should be pinned to a stable revision when the runtime
  implementation can resolve one.
- Thresholds must be explicit non-negative numbers where applicable.

## Model State Records

Artifacts and standalone manifests may record model states.

Model state contract:

```json
{
  "role": "classifier",
  "provider": "transformers_zero_shot",
  "name": "facebook/bart-large-mnli",
  "revision": "pinned",
  "status": "succeeded",
  "task": "event_category_zero_shot",
  "thresholds": {
    "classifier_accept_score": 0.65,
    "classifier_top_margin": 0.1
  },
  "warnings": [],
  "errors": []
}
```

Allowed model states:

```text
succeeded
skipped
degraded
failed
unavailable
```

Rules:

- `succeeded`: model evidence was generated.
- `skipped`: model role was disabled or not required.
- `degraded`: fallback behavior ran without the configured model.
- `failed`: a model role attempted to run and failed.
- `unavailable`: dependency or model files were missing.
- State records must not include local cache paths, tokens, credentials, or
  machine-specific hostnames.

## Common JSON Artifact Rules

Each event-intelligence JSON artifact should use:

```json
{
  "schema_version": 1,
  "artifact_type": "artifact_name",
  "run_id": "20260606T000000Z",
  "created_at": "2026-06-06T00:00:00Z",
  "source_artifacts": [],
  "model_states": [],
  "coverage": {},
  "records": [],
  "warnings": [],
  "errors": []
}
```

Rules:

- `schema_version` starts at `1`.
- `artifact_type` must match the artifact contract name.
- `run_id` must identify the current run when used in the product pipeline.
- `created_at` must be ISO 8601 UTC.
- `source_artifacts` must use repo artifact paths.
- `model_states` must record model role status when model-backed evidence is
  involved.
- `records` may be empty only when status, coverage, warnings, or model states
  explain why.
- `warnings` record degraded, low-confidence, ambiguous, or incomplete evidence.
- `errors` record artifact-specific failures that did not prevent writing a
  partial artifact.
- Do not fabricate conclusions to avoid empty or unknown output.
- Use deterministic ordering for records and source references.

## Text Event Records

Artifact:

```text
analysis/text_event_records.json
```

Purpose:

- Normalize raw text items into stable event records before NLP evidence is
  generated.

Artifact type:

```text
text_event_records
```

Source artifacts:

```text
raw/text_events.json
```

Record contract:

```json
{
  "event_id": "text_event:coindesk:abcdef123456",
  "raw_item_id": "text:coindesk:abcdef1234567890",
  "input_type": "rss_item",
  "source": {
    "name": "coindesk",
    "url": "https://example.invalid/rss"
  },
  "title": "Example title",
  "content_text": "Example content.",
  "link": "https://example.invalid/article",
  "canonical_url": "https://example.invalid/article",
  "published_at": "2026-06-06T00:00:00Z",
  "collected_at": "2026-06-06T00:00:10Z",
  "language": "en",
  "normalized_title": "example title",
  "normalized_text": "example title example content",
  "warnings": [],
  "source_artifacts": [
    "raw/text_events.json"
  ]
}
```

Rules:

- Preserve source-provided facts.
- Canonical URL handling may remove tracking parameters and normalize stable URL
  components, but must not invent a URL.
- Missing optional fields should become explicit warnings.
- Normalization supports downstream processing only; it must not rewrite source
  text into conclusions.

## NLP Evidence Records

NLP evidence may be embedded in later artifacts or stored as intermediate
records when implementation requires it.

Evidence record families:

```text
entity_evidence
asset_relevance_evidence
category_candidate_evidence
financial_tone_evidence
similarity_evidence
```

Initial entity and asset relevance artifact:

```text
analysis/text_entity_evidence.json
```

Artifact type:

```text
text_entity_evidence
```

Source artifacts:

```text
analysis/text_event_records.json
```

Entity evidence contract:

```json
{
  "event_id": "text_event:coindesk:abcdef123456",
  "text": "BlackRock",
  "label": "company",
  "score": 0.87,
  "accepted": true,
  "method": "pretrained_entity_model",
  "model": {
    "provider": "gliner",
    "name": "urchade/gliner_medium-v2.1",
    "revision": "pinned"
  },
  "warnings": []
}
```

Category candidate evidence contract:

```json
{
  "event_id": "text_event:coindesk:abcdef123456",
  "category": "etf_flows",
  "model_score": 0.81,
  "rank": 1,
  "top_margin": 0.14,
  "rule_evidence": [
    "matched term: bitcoin etf"
  ],
  "accepted_by_gate": true,
  "confidence": "medium",
  "warnings": []
}
```

Category and tone evidence artifact:

```text
analysis/text_event_classification_evidence.json
```

Artifact type:

```text
text_event_classification_evidence
```

Source artifacts:

```text
analysis/text_event_records.json
analysis/text_entity_evidence.json
```

Record contract:

```json
{
  "event_id": "text_event:coindesk:abcdef123456",
  "raw_item_id": "text:coindesk:abcdef1234567890",
  "accepted_symbols": [
    "BTCUSDT"
  ],
  "category_evidence": {
    "state": "accepted",
    "primary_category": "etf_flows",
    "confidence": "medium",
    "threshold_checks": {
      "classifier_accept_score_met": true,
      "classifier_top_margin_met": true,
      "rule_or_entity_evidence_met": true
    },
    "candidates": [],
    "rule_evidence": {},
    "warnings": []
  },
  "financial_tone_evidence": {
    "state": "accepted",
    "tone": "positive",
    "model_score": 0.87,
    "scope": "event_text_tone_only",
    "not_trading_signal": true,
    "warnings": []
  },
  "warnings": [],
  "source_artifacts": [
    "analysis/text_event_records.json",
    "analysis/text_entity_evidence.json"
  ]
}
```

Rules:

- Model evidence is not final classification.
- Every accepted evidence item should include model or rule traceability.
- Weak or conflicting evidence should be marked `low_confidence`, `unknown`,
  `skipped`, or `degraded` instead of forced into a category.
- Financial tone is bounded event-text evidence only, not a trading signal,
  action level, or forecast.

## Event Taxonomy

Initial event taxonomy:

```text
etf_flows
regulation_compliance
macro_policy
monetary_policy
stablecoin_liquidity
exchange_market_structure
security_exploit
institutional_adoption
derivatives_leverage
onchain_network
legal_enforcement
other
unknown
```

Rules:

- `unknown` is valid and preferable to unsupported certainty.
- `other` is for source-relevant events that are outside the fixed taxonomy.
- Taxonomy labels are research categories, not action levels.
- Codex must not create new taxonomy labels.

## Topic Grouping

Artifact:

```text
analysis/text_event_topics.json
```

Purpose:

- Group duplicates, same-topic events, and related context while preserving
  source event traceability.

Artifact type:

```text
text_event_topics
```

Source artifacts:

```text
analysis/text_event_records.json
analysis/text_entity_evidence.json
```

Topic record contract:

```json
{
  "topic_id": "text_event_topic:btc:etf_flows:abcdef123456",
  "status": "succeeded",
  "topic_label": "BTC ETF flow concentration",
  "primary_category": "etf_flows",
  "symbols": [
    "BTCUSDT"
  ],
  "event_ids": [],
  "source_count": 2,
  "event_count": 3,
  "first_seen_at": "2026-06-06T00:00:00Z",
  "latest_seen_at": "2026-06-06T03:00:00Z",
  "merge_decisions": [
    {
      "left_event_id": "text_event:source:a",
      "right_event_id": "text_event:source:b",
      "relationship": "same_topic",
      "similarity": 0.86,
      "reasons": [
        "embedding_same_topic_similarity_met",
        "asset_overlap_met",
        "time_window_met"
      ]
    }
  ],
  "warnings": [],
  "source_artifacts": [
    "analysis/text_event_records.json",
    "analysis/text_entity_evidence.json"
  ]
}
```

Relationship taxonomy:

```text
duplicate
same_topic
related_context
distinct
```

Rules:

- `duplicate` should require exact or high-confidence evidence.
- `same_topic` should group related coverage without deleting source events.
- Embedding similarity alone must not force a merge.
- Topic grouping must preserve source events and merge reasons.

## Text Event Signals

Artifact:

```text
analysis/text_event_signals.json
```

Purpose:

- Convert accepted event evidence into bounded report-facing event signals.

Artifact type:

```text
text_event_signals
```

Source artifacts:

```text
analysis/text_event_records.json
analysis/text_event_topics.json
analysis/text_event_classification_evidence.json
```

Signal record contract:

```json
{
  "event_signal_id": "text_event_signal:BTCUSDT:etf_flows:abcdef123456",
  "status": "accepted",
  "symbol": "BTCUSDT",
  "relevance_scope": "symbol",
  "topic_id": "text_event_topic:btc:etf_flows:abcdef123456",
  "primary_category": "etf_flows",
  "event_bias": "supportive",
  "risk_impact": "neutral",
  "opportunity_impact": "opportunity_up",
  "strength": "medium",
  "confidence": "medium",
  "recency": "fresh",
  "evidence": [],
  "uncertainty": [],
  "warnings": [],
  "source_event_ids": [],
  "source_artifacts": []
}
```

Allowed signal states:

```text
accepted
low_confidence
unknown
skipped
degraded
rejected
failed
```

Signal taxonomies:

```text
event_bias: supportive | adverse | mixed | neutral | unknown
risk_impact: risk_up | risk_down | neutral | mixed | unknown
opportunity_impact: opportunity_up | opportunity_down | neutral | mixed | unknown
strength: low | medium | high | unknown
confidence: low | medium | high | unknown
recency: fresh | recent | stale | unknown
```

Rules:

- Event signals are research context, not trading signals.
- Accepted signals require source evidence and model or rule traceability.
- Sentiment alone must not determine event bias.
- Low-confidence evidence must stay low-confidence or unknown.
- Do not infer price direction or return magnitude.

## Event-Market Confluence

Artifact:

```text
analysis/event_market_confluence.json
```

Purpose:

- Explain whether structured event evidence supports, conflicts with, or is
  independent from current quant, strategy gate, risk, and decision evidence.

Artifact type:

```text
event_market_confluence
```

Source artifacts may include:

```text
analysis/text_event_signals.json
analysis/market_signals.json
analysis/strategy_effectiveness_gates.json
analysis/risk_assessment.json
analysis/decision_recommendations.json
```

Record contract:

```json
{
  "confluence_id": "event_market_confluence:BTCUSDT:1d",
  "status": "succeeded",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "relationship": "conflict",
  "event_bias_summary": "supportive",
  "quant_direction_summary": "bearish",
  "decision_action_level": "WATCH",
  "risk_effect": "do_not_upgrade",
  "interpretation": "Event support exists but quant and risk evidence remain conservative.",
  "watch_implications": [],
  "evidence": [],
  "uncertainty": [],
  "linked_event_signal_ids": [],
  "linked_decision_record_ids": [],
  "warnings": [],
  "source_artifacts": []
}
```

Relationship taxonomy:

```text
confluence
conflict
independent
insufficient_event_evidence
unknown
```

Rules:

- Event confluence is explanatory. It must not upgrade action levels by itself.
- Conflict and confluence records should cite both event and quant or decision
  evidence when available.
- Missing event evidence should produce `insufficient_event_evidence` or
  `unknown`, not fabricated event support.

## Event Intelligence Assessment

Status: implemented.

Artifact:

```text
analysis/event_intelligence_assessment.json
```

Purpose:

- Turn event signals and event-market confluence into deterministic event
  assessment records that explain event relevance, severity, source reliability,
  market response, and decision impact before alert priority is assigned.

Artifact type:

```text
event_intelligence_assessment
```

Source artifacts may include:

```text
analysis/text_event_records.json
analysis/text_entity_evidence.json
analysis/text_event_classification_evidence.json
analysis/text_event_topics.json
analysis/text_event_signals.json
analysis/event_market_confluence.json
analysis/market_signals.json
analysis/strategy_effectiveness_gates.json
analysis/market_regime_assessment.json
analysis/risk_assessment.json
analysis/decision_recommendations.json
analysis/watch_triggers.json
analysis/macro_calendar_context.json
analysis/onchain_flow_context.json
```

Record contract:

```json
{
  "assessment_id": "event_intelligence_assessment:BTCUSDT:1d:text_event_topic:abc123",
  "status": "succeeded",
  "scope": {
    "symbol": "BTCUSDT",
    "timeframe": "1d",
    "topic_id": "text_event_topic:BTCUSDT:abc123"
  },
  "event_summary": "A bounded source-aware summary derived from structured event artifacts.",
  "affected_assets": ["BTCUSDT"],
  "relevant_timeframes": ["1d"],
  "source_reliability": "medium",
  "event_severity": "medium",
  "market_response_relationship": "independent",
  "decision_impact": "no_change",
  "risk_effect": "neutral",
  "watch_relevance": "none",
  "confidence": "low",
  "evidence": [],
  "downgrade_reasons": [],
  "uncertainty": [],
  "warnings": [],
  "linked_macro_calendar_context_ids": [],
  "macro_calendar_relevance": [],
  "linked_onchain_flow_context_ids": [],
  "onchain_flow_relevance": [],
  "source_artifacts": []
}
```

Source reliability taxonomy:

```text
high
medium
low
unknown
```

Event severity taxonomy:

```text
critical
high
medium
low
noise
unknown
```

Market response relationship taxonomy:

```text
confirmed
conflicting
independent
insufficient_market_evidence
unknown
```

Decision impact taxonomy:

```text
could_invalidate
could_downgrade
could_upgrade_attention
supports_existing_view
no_change
insufficient_evidence
unknown
```

Risk effect taxonomy:

```text
risk_up
risk_down
neutral
mixed
unknown
```

Watch relevance taxonomy:

```text
confirmation
invalidation
risk_escalation
risk_relief
wait_condition
none
unknown
```

Rules:

- Event assessment is a deterministic Halpha artifact, not a Codex-generated
  interpretation.
- Assessment records may be topic-scoped, event-scoped, or asset/timeframe
  scoped, but each record must expose its scope explicitly.
- Accepted high-severity or critical assessment requires source artifacts,
  event evidence, and either market, risk, decision, or watch-trigger relevance.
- Low-confidence, unrelated, stale, duplicate, or insufficient-evidence events
  should remain visible through downgrade reasons or low-severity records.
- Scheduled or recent macro/calendar context may appear as proximity evidence
  only when event source timestamps overlap the catalyst window.
- Stale, unavailable, degraded, or partial macro/calendar source states may add
  source uncertainty or downgrade reasons.
- No-event macro/calendar windows must not be treated as low-risk evidence and
  must not create event relevance by themselves.
- On-chain flow context may appear as liquidity, network-activity, congestion,
  or source-availability relevance only when accepted event evidence is linked
  to the same asset scope.
- Stale, unavailable, degraded, or partial on-chain flow source states may add
  source uncertainty or downgrade reasons.
- Normal or unrelated on-chain flow context must not create event relevance by
  itself.
- Event assessment must not assign alert priority, action level, trading advice,
  position sizing, price targets, or return forecasts.
- Alert priority is assigned by `analysis/alert_decisions.json`, not by this
  artifact.

## Event Intelligence Material

Artifact:

```text
analysis/event_intelligence_material.md
```

Purpose:

- Provide bounded AI-readable event intelligence for Codex report generation.

YAML front matter:

```yaml
artifact_type: analysis_event_intelligence_material
schema_version: 1
audience: ai
source_artifacts:
  - analysis/text_event_records.json
  - analysis/text_event_classification_evidence.json
  - analysis/text_event_topics.json
  - analysis/text_event_signals.json
  - analysis/event_market_confluence.json
  - analysis/event_intelligence_assessment.json
```

Expected sections:

```text
event_source_policy
event_model_policy
event_overview
topic_summary
event_signal_summary
event_market_confluence
event_intelligence_assessment
risk_and_uncertainty
report_usage_rules
records
```

Rules:

- Keep material bounded.
- Do not embed full raw feeds or long article bodies.
- Include source names, links where available, timestamps, event categories,
  topic grouping, event signals, confluence or conflict, uncertainty, warnings,
  and model-state caveats.
- State that NLP model outputs are evidence, not final trading or decision
  authority.
- Do not ask Codex to generate event categories, event impacts, action levels,
  price forecasts, or trading recommendations.
- When event assessment artifacts exist, material should explain assessment
  results compactly and should not embed full intermediate JSON records.

## Standalone Text Intelligence

Standalone text intelligence is a validation and review path.

Expected commands:

```bash
python -m halpha text-models prepare --config config.example.yaml
python -m halpha text-intel --config config.example.yaml
python -m halpha text-intel --config config.example.yaml --input runs/<run_id>/raw/text_events.json
python -m halpha text-intel --config config.example.yaml --output-dir runs/text_intelligence
```

Rules:

- The command may collect configured public text sources when `--input` is not
  provided.
- The command must not run the full report pipeline or Codex CLI.
- The command must not write fake downstream artifacts for unimplemented
  processors.
- Planned capabilities that are not available in the standalone command should
  be recorded as omitted capabilities, not as executed processors.
- Standalone artifacts should live under a local text-intelligence output
  directory.

Standalone manifest:

```text
runs/text_intelligence/<id>/manifest.json
```

Implemented standalone outputs also include:

```text
runs/text_intelligence/<id>/analysis/event_intelligence_material.md
```

Manifest rules:

- Record command inputs, source artifact paths, produced artifact paths, model
  states, thresholds, counts, warnings, errors, omitted capabilities, skipped
  executed processors, and degraded processors.
- The `processors` list records processors that actually ran or were attempted
  by the standalone command.
- The `omitted_capabilities` list records supported product-pipeline
  capabilities that are intentionally unavailable in standalone mode.
- Do not record local model cache paths or local privacy values.

## Pipeline Integration

Target product pipeline order:

```text
collect_text_events
build_text_event_records
build_text_entity_evidence
build_text_event_classification_evidence
build_text_event_topics
build_text_event_signals
build_event_market_confluence
build_event_intelligence_assessment
build_event_intelligence_material
build_analysis_materials
build_research_context
build_codex_context
run_codex_report
```

Rules:

- Existing raw text collection remains the upstream source.
- Existing `analysis/text_material.md` remains source-aware text material.
- Event intelligence is additive.
- `build_event_market_confluence` runs after market, risk, decision, and
  watch-trigger artifacts exist in the full product pipeline.
- `build_event_intelligence_assessment` runs after event-market confluence and
  current decision-intelligence artifacts exist.
- Event intelligence may be skipped when text or text intelligence is disabled.
- Skipped stages must not fabricate unknown artifacts.
- Manifest counts should record records, topics, event signals, accepted signals,
  low-confidence signals, confluence records, assessment records, assessment
  severity coverage, assessment downgrade coverage, model-state counts,
  warnings, and errors when those artifacts are implemented.

## Research Context and Codex Context Integration

Event intelligence may be added to the existing report context when generated.

`analysis/research_context.md` contract additions:

```yaml
text_event_records: analysis/text_event_records.json
text_entity_evidence: analysis/text_entity_evidence.json
text_event_classification_evidence: analysis/text_event_classification_evidence.json
text_event_topics: analysis/text_event_topics.json
text_event_signals: analysis/text_event_signals.json
event_market_confluence: analysis/event_market_confluence.json
event_intelligence_assessment: analysis/event_intelligence_assessment.json
event_intelligence_material: analysis/event_intelligence_material.md
```

`codex_context/context.md` contract additions:

```yaml
text_event_records: analysis/text_event_records.json
text_entity_evidence: analysis/text_entity_evidence.json
text_event_classification_evidence: analysis/text_event_classification_evidence.json
text_event_topics: analysis/text_event_topics.json
text_event_signals: analysis/text_event_signals.json
event_market_confluence: analysis/event_market_confluence.json
event_intelligence_assessment: analysis/event_intelligence_assessment.json
event_intelligence_material: analysis/event_intelligence_material.md
```

Codex prompt rules:

- Require Simplified Chinese Markdown report output.
- Use event intelligence material as Halpha-generated event evidence.
- Explain event topic grouping, event signals, source coverage, recency, and
  event-quant confluence or conflict when artifacts exist.
- Explain event assessment severity, source reliability, decision impact,
  downgrade reasons, and uncertainty only from Halpha-generated assessment
  material when present.
- Keep event uncertainty near event conclusions.
- Do not ask Codex to generate or revise event taxonomy labels, event impacts,
  event-market relationships, action levels, strategy gates, or price forecasts.
- Do not turn event signals into trading instructions, position sizing, account
  actions, investment recommendations, return promises, or deterministic market
  claims.
- If event intelligence is absent or degraded, do not ask Codex to recreate it
  from raw text.

## Golden Corpus and Human Review

Golden fixtures should cover:

- Asset relevance.
- Event taxonomy classification.
- Entity extraction acceptance.
- Duplicate safety.
- Same-topic grouping.
- Unknown fallback behavior.
- Model-unavailable degraded behavior.
- Evidence traceability.

Validation rules:

- High-confidence asset relevance should require source evidence and model or
  rule traceability.
- High-confidence category classification should require model score, threshold
  decision, and rule or entity evidence.
- Duplicate false merges should be treated as critical regressions.
- Ambiguous cases may be `unknown` or `low_confidence`.
- Human review of real-source runs should sample recent topics, accepted event
  signals, and confluence records.
- Representative misclassifications should become regression fixtures when they
  are within the implemented scope.

### Manual Review Checklist

For real-source event-intelligence acceptance, review the newest standalone
text-intelligence output or product run artifacts without exposing local config
values.

Recommended inputs:

```bash
python -m halpha text-intel --config <local config>
python -m halpha run --config <local config> --no-codex
```

Checklist:

- Inspect `analysis/text_event_records.json` for source names, canonical URLs,
  timestamps, warnings, and absence of fabricated source fields.
- Inspect `analysis/text_entity_evidence.json` for accepted asset relevance.
  High-confidence asset relevance should cite deterministic alias rules or
  model evidence and configured symbols.
- Inspect `analysis/text_event_classification_evidence.json` for accepted event
  categories. Accepted categories should have model scores, threshold checks,
  rule evidence or accepted symbols, model metadata, and warnings when evidence
  is weak.
- Inspect `analysis/text_event_topics.json` for duplicate and same-topic
  decisions. False duplicate merges are critical and should become regression
  fixtures.
- Inspect `analysis/text_event_signals.json` for accepted, low-confidence, and
  unknown signal states. Ambiguous events should remain unknown or
  low-confidence rather than being forced.
- Inspect `analysis/event_market_confluence.json` when present for confluence,
  conflict, independent, or insufficient-event-evidence relationships and for
  decision links.
- Inspect `analysis/event_intelligence_assessment.json` when present for
  severity, source reliability, market response relationship, decision impact,
  downgrade reasons, uncertainty, warnings, and source artifacts.
- Inspect `analysis/event_intelligence_material.md` for bounded source-aware
  report material and explicit Codex usage boundaries.
- If a representative misclassification, false merge, missing traceability, or
  unsafe upgrade is found, add or update a golden fixture and expected output
  before changing gates.

## Contract Summary

- Event intelligence is additive to existing text, quant, strategy, decision,
  and report artifacts.
- Pretrained NLP models generate evidence; Halpha gates decide accepted
  artifacts.
- Artifacts must expose source references, model metadata, thresholds, scores,
  acceptance reasons, warnings, and degraded states.
- Event assessment artifacts, when implemented, must explain event severity,
  source reliability, decision impact, downgrade reasons, uncertainty, and
  source artifacts before alert priority is assigned.
- Standalone text-intelligence validation is required for fast local review.
- Codex may explain event intelligence; it must not invent structured event
  intelligence outputs.
