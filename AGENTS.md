# AGENTS.md

Telegraph style. Root rules only. Read scoped `AGENTS.md` before subtree work.

Keep future edits in this style.

## Start

* Repo: `https://github.com/hhxcv/Halpha`
* Inspect the repo before changing files.
* Do not assume implementation exists.
* Do not invent commands, APIs, modules, paths, or behavior.
* Replies use repo-root paths only: `README.md`, `src/halpha/cli.py`.
* No absolute paths.
* No `~/`.
* Keep changes small.
* Touch only relevant files.
* Prefer source-backed answers.
* Never print secrets.
* Never commit secrets.
* Market output is research material, not financial advice.

## Governance

* Root rules live here.
* Scoped rules live in subtree `AGENTS.md`.
* Read scoped `AGENTS.md` before subtree work.
* Nearest scoped rule owns subtree implementation details.
* Root safety, privacy, and financial-disclaimer rules always apply.
* If rules conflict, stop and report the conflict.

## Map

Current repo may be empty or incomplete.

Expected areas, when present:

* Package code: `src/halpha/`
* Tests: `tests/`
* Docs: `README.md`, `AGENTS.md`, `docs/`
* Examples: `config.example.yaml`
* Run artifacts: `runs/`

Do not create this structure unless the task requires it.

Do not treat planned paths as existing paths.

## Direction

Halpha is an early-stage personal research project.

Target direction:

```text
market data + public information
-> online data collection
-> materials
-> structured research context
-> Codex-ready context
-> Simplified Chinese research report
-> archive
```

Current bias:

* readable artifacts
* source-aware materials
* simple pipeline
* narrow implementation steps
* no premature architecture

## Milestone Evolution

* Milestones are slices of the long-term goal, not disposable design eras.
* Current-milestone work should fit the durable product shape where practical.
* Milestone scope usually limits current content, coverage, implementation depth, and supported cases.
* Milestone scope should not make reusable artifacts milestone-local in name, title, structure, or contract identity.
* Do not mark reusable docs, protocols, contracts, schemas, modules, commands, or artifact names with current milestone labels.
* Use milestone labels only for milestone records, planning notes, issue traces, or truly local transition bridges.
* Prefer incremental evolution: add content, fill sections, deepen implementations, and stack modules on established structure.
* Avoid disposable designs that assume a later milestone will replace or rebuild the current artifact.
* If a current-milestone shortcut is unavoidable, mark it temporary, keep it narrow, and name the replacement requirement.

## Architecture

* Python-first unless requested otherwise.
* Configured collection and plain artifacts by default.
* Plain files first: Markdown, JSON, YAML, CSV, text.
* Keep raw data separate from processed material.
* Keep processed material separate from generated narrative.
* Preserve source metadata where practical.
* Codex context is an artifact, not hidden state.
* Final reports are Simplified Chinese unless requested otherwise.
* Prefer explicit names over abstractions.
* Prefer one narrow working path over a framework.
* No trading execution.
* No exchange account operations.
* No portfolio automation.
* No hosted SaaS assumptions.
* No database until plain files are insufficient.
* No background service unless requested.

## Local Privacy

* Public config files stay portable.
* Machine-local config lives in gitignored local config files.
* Keep local privacy values out of code, tests, docs, commits, PRs, issues, comments, release notes, screenshots, and logs.
* Local privacy values include proxy URLs, ports, hostnames, credentials, tokens, cookies, account IDs, machine paths, usernames, and private endpoints.
* Do not hardcode local privacy values.
* Do not print local privacy values.
* Do not summarize local privacy values in network-visible text.
* Use placeholders for examples.
* Support local variations through config fields, not hardcoded branches or environment-only behavior.
* Support both configured and omitted local values where practical.
* If `config.example.yaml` changes, sync required local config copies before local runs.
* Use local config files for local-only validation.

## Compatibility

* Compatibility is opt-in.
* No compatibility layers before shipped behavior exists.
* No aliases, shims, migrations, or fallbacks for imagined users.
* Keep old behavior only when a real public contract exists.
* If no release exists, prefer the clean current shape.
* Delete dead paths when replacing them.
* Tests alone do not make an internal API public.

## Code

* One task, one focused change.
* No unrelated rewrites.
* No broad abstractions for future guesses.
* No casual dependencies.
* No silent behavior changes.
* No dead code.
* No generated clutter.
* No hidden network calls.
* No real credentials in tests or examples.
* Use deterministic ordering when generating context files.
* Comments explain intent, not syntax.
* Error messages should be actionable.

## Dependencies

* Standard library first.
* Add a dependency only when it is needed now.
* Prefer small, maintained packages.
* Do not add heavy frameworks for early scaffolding.
* For dependency-backed behavior, check official docs or source.
* Do not rely on memory for external API details.
* Document new runtime dependencies when introduced.

## Data

* Treat collected data as evidence.
* Keep source names visible.
* Keep timestamps where practical.
* Keep raw inputs inspectable.
* Do not fabricate market events.
* Do not fabricate sources.
* Do not silently rewrite source material into conclusions.
* Generated analysis must distinguish facts, assumptions, and judgment.

## Artifact Expectations

* Artifact map, layer rules, and Codex input policy live in `docs/artifact-governance.md`.
* Local research data contracts live in `docs/research-data-contracts.md`.
* Outcome tracking contracts live in `docs/outcome-tracking-contracts.md`.
* On-chain and exchange-flow contracts live in `docs/onchain-flow-contracts.md`.
* User-state and personalized-risk contracts live in `docs/user-state-contracts.md`.
* Product runs preserve raw market and text artifacts.
* Shared OHLCV history lives outside per-run report directories.
* Shared OHLCV history is reusable input data, not AI context.
* `data/research/metadata/research_data_catalog.json` records implemented reusable local stores, schema refs, state refs, counts, warnings, errors, and consumers.
* `data/research/index.sqlite` records run, stage, artifact, and latest-run metadata; it stores references, not artifact contents.
* `data/research/metadata/text_event_history_state.json` records shared text-event history state, counts, duplicates, conflicts, warnings, and source refs.
* `data/research/text_events/` stores reusable text-event history; it is input data, not AI context.
* `data/research/metadata/outcome_history_state.json` records shared outcome history state, counts, duplicates, conflicts, warnings, and source refs.
* `data/research/outcomes/outcome_history.json` stores reusable outcome history; it is input data, not AI context.
* `raw/market_data_views.json` records current-run OHLCV input windows and storage refs, not full raw history.
* `raw/derivatives_market.json` records current-run public derivatives and market-structure observations, endpoint availability, warnings, and errors.
* `raw/macro_calendar.json` records current-run public macro and scheduled-event observations, endpoint availability, warnings, and errors.
* `data/macro/calendar/` stores reusable macro/calendar history; it is input data, not AI context.
* `data/macro/metadata/macro_calendar_schema.json` records reusable macro/calendar history schema and logical keys.
* `data/macro/metadata/macro_calendar_state.json` records reusable macro/calendar history state, groups, ranges, counts, duplicates, conflicts, warnings, errors, and source refs.
* `raw/macro_calendar_views.json` records current-run macro/calendar input windows, bounded records, and storage refs, not full reusable macro/calendar history.
* `analysis/macro_calendar_context.json` records deterministic macro/calendar scheduled-catalyst, recent-catalyst, no-event, stale, unavailable, partial, degraded, failed, source-availability, uncertainty, and realized-impact-not-evaluated context states, not forecasts or trading signals.
* `analysis/macro_calendar_material.md` records bounded AI-readable macro/calendar context, source availability, selected high-signal records, omission counts, and Codex/report boundaries.
* `raw/onchain_flow.json` records current-run public on-chain and exchange-flow observations, endpoint availability, warnings, and errors.
* `data/onchain/flow/` stores reusable on-chain flow history; it is input data, not AI context.
* `data/onchain/metadata/onchain_flow_schema.json` records reusable on-chain flow history schema and logical keys.
* `data/onchain/metadata/onchain_flow_state.json` records reusable on-chain flow history state, groups, ranges, counts, duplicates, conflicts, warnings, errors, and source refs.
* `raw/onchain_flow_views.json` records current-run on-chain flow input windows and storage refs, not full reusable on-chain flow history.
* `analysis/onchain_flow_context.json` records deterministic stablecoin liquidity, chain activity, network congestion, exchange-flow source-availability, stale, unavailable, partial, degraded, insufficient-data, warning, and failed context states, not forecasts or trading signals.
* `analysis/onchain_flow_material.md` records bounded AI-readable on-chain flow context, source availability, selected high-signal records, omission counts, and Codex/report boundaries.
* `data/market/derivatives/` stores reusable derivatives market history; it is input data, not AI context.
* `data/market/metadata/derivatives_market_schema.json` records reusable derivatives history schema and logical keys.
* `data/market/metadata/derivatives_market_state.json` records reusable derivatives history state, groups, ranges, counts, duplicates, conflicts, warnings, errors, and source refs.
* `raw/derivatives_market_views.json` records current-run derivatives input windows and storage refs, not full reusable derivatives history.
* `analysis/derivatives_market_context.json` records deterministic funding, open-interest, premium, basis, bounded liquidity-depth, and liquidation-availability context states, evidence, thresholds, uncertainty, warnings, and errors, not trading signals.
* `analysis/derivatives_market_material.md` records bounded AI-readable derivatives market context, source availability, data-quality limits, selected high-signal records, and omission counts for Codex/report use.
* `analysis/text_event_records.json` records normalized source-aware text event records.
* `analysis/text_entity_evidence.json` records deterministic and optional model-backed entity and asset relevance evidence.
* `analysis/text_event_classification_evidence.json` records event taxonomy candidates and financial tone evidence, not trading signals.
* `analysis/text_event_topics.json` records duplicate, same-topic, related-context, and distinct event grouping evidence.
* `analysis/text_event_signals.json` records deterministic report-facing text event signals, not trading instructions.
* `analysis/strategy_benchmark_suite.json` records fixed strategy benchmark window metadata, coverage, storage refs, warnings, errors, and source artifacts, not full raw history.
* `analysis/quant_strategy_runs.json` records configured strategy run outputs, status, params, diagnostics, evidence, uncertainty, warnings, and source artifacts.
* `analysis/strategy_evaluation_summary.json` records pipeline strategy evaluation outputs from configured strategy runs and current-run OHLCV views.
* `analysis/strategy_evaluation_material.md` records AI-readable strategy evaluation material from strategy evaluation summaries.
* `analysis/strategy_experiment.json` records current-run strategy experiment outputs for configured candidates.
* `analysis/strategy_effectiveness_gates.json` records deterministic current-run strategy gate outcomes.
* `analysis/strategy_experiment_material.md` records AI-readable strategy experiment and gate material.
* `analysis/market_strategy_signals.json` records evaluator outputs.
* `analysis/market_signals.json` records normalized report-facing market signals.
* `analysis/market_signal_material.md` is bounded AI-readable signal material.
* Feature/factor contracts live in `docs/feature-factor-contracts.md`.
* `analysis/feature_snapshots.json` records normalized source-aware feature records and source coverage from implemented current-run evidence.
* `analysis/factor_states.json` records deterministic factor states, bounded scores, directions, confidence, warnings, errors, and degraded or insufficient-evidence states from feature snapshots.
* `analysis/multi_source_signals.json` records conservative normalized research signals derived from factor states, not trading instructions.
* `analysis/intelligence_fusion.json` records deterministic cross-source confluence, conflict, risk override, event override, outcome feedback, uncertainty, and source-ref evidence, not trading instructions or Codex-generated states.
* `analysis/factor_signal_material.md` records bounded AI-readable feature, factor, and multi-source signal evidence, selected records, omission counts, and Codex/report boundaries.
* `analysis/intelligence_fusion_material.md` records bounded AI-readable fusion confluence, conflict, risk override, event override, outcome feedback, uncertainty, selected records, omission counts, and Codex/report boundaries.
* `analysis/user_state_context.json` records optional local user-state status, sanitized watchlist, disabled asset, risk, timeframe, strategy preference, exposure-summary fields, omitted-private-value counts, privacy boundaries, warnings, and errors; not account state or trading instructions.
* `analysis/market_regime_assessment.json` records deterministic market-state assessment.
* `analysis/risk_assessment.json` records deterministic risk-state assessment, including optional derivatives, macro/calendar, and on-chain flow context references.
* `analysis/decision_recommendations.json` records deterministic decision-support recommendations, risk conditions, downgrade reasons, optional derivatives, macro/calendar, on-chain flow context links, and optional fusion context, not trading instructions.
* `analysis/watch_triggers.json` records deterministic static watch triggers, including supported derivatives, macro/calendar, and on-chain flow observation, risk escalation, and risk relief conditions, not monitoring or alerts.
* `analysis/event_market_confluence.json` records deterministic event-quant and event-decision relationship records.
* `analysis/event_intelligence_assessment.json` records deterministic event relevance, severity, market response, decision-impact, optional macro/calendar proximity, and optional on-chain flow relevance assessment records.
* `analysis/alert_decisions.json` records deterministic event attention-priority decisions and optional derivatives, macro/calendar, on-chain flow relevance links, and optional fusion context, not alert delivery or trading execution.
* `analysis/alert_decision_material.md` records bounded AI-readable alert priority, downgrade, suppression, and uncertainty material.
* `analysis/event_intelligence_material.md` records bounded AI-readable event evidence, topic, signal, and confluence material.
* `analysis/decision_intelligence_delta.json` records previous-run decision-intelligence changes or `no_previous_run` status.
* `analysis/decision_intelligence_material.md` records AI-readable decision material from deterministic decision-intelligence JSON artifacts.
* `analysis/data_quality_summary.json` records current-run market, text, derivatives, macro/calendar, on-chain flow, feature/factor, intelligence-fusion, shared-store, schema, timestamp, duplicate, stale, partial-collection, and degraded quality checks.
* `analysis/data_quality_material.md` records bounded AI-readable data quality status and local store references from `analysis/data_quality_summary.json`.
* `analysis/outcome_targets.json` records deterministic source-linked outcome targets extracted from the latest previous successful run.
* `analysis/outcome_evaluations.json` records deterministic market and strategy outcome evaluations from shared OHLCV history with no-lookahead observation windows, plus event, alert, decision, and watch follow-through evaluations from later Halpha artifacts.
* `analysis/outcome_tracking_material.md` records bounded AI-readable outcome accountability material from targets, evaluations, and outcome history summaries.
* `run_manifest.json` records run lifecycle, stage status, produced artifacts, counts, warnings, errors, Codex status, and Codex input budget metadata.
* Standalone strategy backtests write `strategy_backtest.json` and `manifest.json` under a local backtest output directory.
* Standalone strategy experiments write `strategy_experiment.json`, `strategy_benchmark_suite.json`, `strategy_effectiveness_gates.json`, and `manifest.json` under a local experiment output directory.
* Codex context may include bounded signal, strategy evaluation, strategy experiment, derivatives market, macro/calendar, on-chain flow, feature/factor, intelligence fusion, decision, alert, event intelligence, data quality, and outcome tracking material, not shared OHLCV history, raw derivatives observations, raw macro/calendar observations, raw on-chain flow observations, reusable derivatives history, reusable macro/calendar history, reusable on-chain flow history, derivatives views, macro/calendar views, on-chain flow views, full macro/calendar context JSON, full derivatives context JSON, full intelligence fusion JSON, full user-state context JSON, or full on-chain flow context JSON.
* Codex context must not embed full raw streams, full raw derivatives artifacts, full raw macro/calendar artifacts, full raw on-chain flow artifacts, full local user-state files, private user notes, account identifiers, exact holdings, balances, full shared OHLCV history, full reusable derivatives history, full reusable macro/calendar history, full reusable on-chain flow history, full feature snapshots JSON, full factor states JSON, full multi-source signals JSON, full intelligence fusion JSON, full user-state context JSON, full macro/calendar context JSON, full derivatives context JSON, full on-chain flow context JSON, full reusable text-event history, full reusable outcome history, full catalog contents, SQLite contents, Parquet tables, full intermediate JSON evidence, full pairwise topic decisions, full walk-forward diagnostics, or full run manifests by default.
* Codex input should prioritize high-signal decision, risk, alert, fusion, strategy gate, derivatives, macro/calendar, on-chain flow, event, and data-quality evidence over low-priority record dumps.
* Low-confidence, unknown, duplicate, stale, no-alert, or insufficient-evidence records should be summarized or omitted from Codex input with counts or reasons when material budgets require it.
* Codex prompt may ask for decision-intelligence report sections when decision material exists.
* Codex prompt may ask for derivatives market explanation when derivatives material exists.
* Codex prompt may ask for macro/calendar scheduled-catalyst, no-event, source-availability, freshness, time-zone, and realized-impact-not-evaluated explanation when macro calendar material exists.
* Codex prompt may ask for on-chain flow explanation when on-chain flow material exists.
* Codex prompt may ask for feature, factor, and multi-source signal explanation when factor signal material exists.
* Codex prompt may ask for intelligence fusion confluence, conflict, risk override, event override, outcome feedback, and uncertainty explanation when intelligence fusion material exists.
* Codex prompt may ask for event evidence, topic grouping, and event-quant relationship explanation when event intelligence material exists.
* Codex prompt may ask for data-quality status explanation when data quality material exists.
* Codex prompt must not ask Codex to generate event categories, event impacts, event-market relationships, action levels, trading advice, or price forecasts.
* Codex prompt must not ask Codex to generate derivatives states, risk levels, signals, source availability, liquidation summaries, price forecasts, trading instructions, or position sizing.
* Codex prompt must not ask Codex to generate macro/calendar events, states, source availability, risk levels, watch triggers, alert priorities, release outcomes, policy outcomes, price forecasts, trading instructions, or position sizing.
* Codex prompt must not ask Codex to generate on-chain records, flow states, address labels, source availability, risk levels, watch triggers, alert priorities, price forecasts, trading instructions, wallet actions, or position sizing.
* Codex prompt must not ask Codex to generate feature records, factor scores, normalized signal states, action levels, price forecasts, trading instructions, or position sizing.
* Codex prompt must not ask Codex to generate fusion states, risk overrides, event overrides, alert priorities, action levels, price forecasts, trading instructions, or position sizing.
* Codex prompt must not ask Codex to generate data-quality checks, validation results, catalog contents, run-index contents, or reusable history contents.
* Final reports may include a deterministic quant strategy output table inserted from `analysis/quant_strategy_runs.json` after Codex stdout validation.
* Final reports may include a deterministic strategy effectiveness table inserted from `analysis/strategy_effectiveness_gates.json` after Codex stdout validation.
* Final reports may include a deterministic derivatives and market-structure evidence section inserted from `analysis/derivatives_market_context.json` when `analysis/derivatives_market_material.md` exists after Codex stdout validation.
* Final reports may include a deterministic macro/calendar evidence section inserted from `analysis/macro_calendar_context.json` when `analysis/macro_calendar_material.md` exists after Codex stdout validation.
* Final reports may include a deterministic on-chain flow evidence section inserted from `analysis/onchain_flow_context.json` when `analysis/onchain_flow_material.md` exists after Codex stdout validation.
* Codex prompt should not ask Codex to recreate the complete strategy run table.
* Codex prompt should not ask Codex to recreate the complete derivatives context table.
* Codex prompt should not ask Codex to recreate the complete macro/calendar context table.
* Reports come from Codex stdout, not placeholder text.
* Fake market data, fake signals, and fake Codex output stay test-only.

## Docs

* Docs match current repo state.
* README is for humans.
* AGENTS.md is for AI agents.
* `docs/` is for durable project documentation and reusable implementation contracts.
* Documentation index:
* `docs/artifact-governance.md`: artifact map, artifact layer rules, Codex input policy, and doc index.
* `docs/quant-contracts.md`: quantitative data, strategy, evaluation, signal, and strategy material contracts.
* `docs/macro-calendar-contracts.md`: macro and scheduled-event data, context, material, and Codex-boundary contracts.
* `docs/onchain-flow-contracts.md`: on-chain and exchange-flow data, context, material, and Codex-boundary contracts.
* `docs/feature-factor-contracts.md`: feature, factor, multi-source signal, material, and Codex-boundary contracts.
* `docs/intelligence-fusion-contracts.md`: fusion artifact, planned material, integration, and Codex-boundary contracts.
* `docs/user-state-contracts.md`: optional local user-state, personalized-risk, privacy, material, and Codex-boundary contracts.
* `docs/event-intelligence-contracts.md`: text event, NLP evidence, topic, event signal, confluence, and event material contracts.
* `docs/decision-intelligence-contracts.md`: regime, risk, recommendation, watch trigger, delta, and decision material contracts.
* `docs/outcome-tracking-contracts.md`: planned outcome target, evaluation, history, material, and Codex-boundary contracts.
* `runs/README.md`: run artifact directory purpose.
* Directory descriptions state long-term purpose, not just current file inventory.
* Prefer stable contract files.
* Update existing contract files as behavior evolves.
* Do not title or name reusable docs and contracts with current milestone labels.
* Do not create milestone-numbered successor contract files unless the contract is truly milestone-local.
* Do not describe planned work as implemented.
* Use `planned`, `intended`, or `not implemented yet` for future work.
* Keep public docs concise.
* Do not add large roadmaps unless requested.
* Do not document commands that do not exist.
* Update docs when user-visible behavior changes.

## Commands

Use existing repo commands only.

If no command exists, say so.

Implemented setup command:

```bash
python -m pip install -e ".[dev]"
```

Implemented commands:

```bash
python -m pytest
python -m halpha run --config config.example.yaml
python -m halpha run --config config.example.yaml --no-codex
python -m halpha run --config config.example.yaml --until <stage_name>
python -m halpha stage <stage_name> --config config.example.yaml --run-dir runs/<run_id>
python -m halpha backtest --config config.example.yaml --strategy <strategy_name> --symbol <symbol> --timeframe <timeframe>
python -m halpha experiment --config config.example.yaml
python -m halpha text-models prepare --config config.example.yaml
python -m halpha text-intel --config config.example.yaml
python -m halpha text-intel --config config.example.yaml --input runs/<run_id>/raw/text_events.json
python -m halpha data inspect --config config.example.yaml
python -m halpha data inspect --config config.example.yaml --run-dir runs/<run_id>
python -m halpha outcomes inspect --config config.example.yaml
python -m halpha outcomes inspect --config config.example.yaml --run-dir runs/<run_id>
```

The run command is the implemented product path.

The `--no-codex`, `--until`, and `stage` commands are validation helpers.

They must not fabricate skipped artifacts.

`--no-codex` requires public network access and configured public sources, but not Codex CLI execution.

`--until` runs through the named stage and records later stages as not run.

`stage` runs one named stage against an existing run directory.

`backtest` runs one configured strategy against shared local OHLCV history.

`backtest` does not run the full report pipeline or Codex CLI.

`experiment` runs configured strategy candidates against fixed benchmark suite windows from shared local OHLCV history.

`experiment` does not run the full report pipeline or Codex CLI.

`text-models prepare` explicitly prepares configured local text-intelligence models or records skipped/unavailable model states.

`text-models prepare` must not be treated as permission for hidden model downloads during normal product runs.

`text-intel` runs standalone text intelligence processing from configured text sources or an existing raw text artifact.

`text-intel` does not run the full report pipeline or Codex CLI.

`data inspect` summarizes local store metadata, run index state, text-event history state, OHLCV metadata, derivatives metadata, macro/calendar metadata, on-chain flow metadata, feature/factor artifact status, intelligence-fusion status, Codex input budget state, and data-quality summaries.

`data inspect` is read-only. It does not collect network data, run processors, run strategy evaluation, run Codex CLI, repair stores, or export raw records.

`outcomes inspect` summarizes outcome targets, outcome evaluations, outcome material, and shared outcome history state.

`outcomes inspect` is read-only. It does not collect network data, run processors, run strategy evaluation, run Codex CLI, repair stores, or export raw records.

Full report runs require public network access, configured public sources, and a working Codex CLI.

Do not claim success without running the relevant command.

## Validation

* Run the narrowest relevant check.
* Prefer tests for changed behavior.
* Use smoke checks for early scaffolding.
* Use `python -m pytest` for automated validation.
* Use `python -m halpha run --config config.example.yaml --no-codex` for real-source product acceptance when Codex CLI use is not needed.
* Use `python -m halpha run --config config.example.yaml --until <stage_name>` for bounded stage-through acceptance.
* Use `python -m halpha stage <stage_name> --config config.example.yaml --run-dir runs/<run_id>` to rerun one stage against existing artifacts.
* Use `python -m halpha backtest --config config.example.yaml --strategy <strategy_name> --symbol <symbol> --timeframe <timeframe>` to validate one standalone strategy backtest when shared OHLCV history exists.
* Use `python -m halpha experiment --config config.example.yaml` to validate standalone strategy experiment and gate artifacts when shared OHLCV history exists.
* Use `python -m halpha text-models prepare --config config.example.yaml` to validate configured text model metadata without downloads when `allow_model_download` is false.
* Use `python -m halpha text-intel --config config.example.yaml` to validate standalone text intelligence collection and implemented processors.
* Use `python -m halpha text-intel --config config.example.yaml --input runs/<run_id>/raw/text_events.json` to validate standalone text intelligence from existing raw text artifacts.
* Use `python -m halpha data inspect --config config.example.yaml` to validate local research data catalog, run index, text-event history, OHLCV metadata, derivatives metadata, macro/calendar metadata, on-chain flow metadata, feature/factor artifact status, intelligence-fusion status, Codex input budget state, and latest data-quality state without Codex CLI.
* Use `python -m halpha data inspect --config config.example.yaml --run-dir runs/<run_id>` to inspect data-quality state for a specific run.
* Use `python -m halpha outcomes inspect --config config.example.yaml` to validate latest outcome target, evaluation, material, and history state without Codex CLI.
* Use `python -m halpha outcomes inspect --config config.example.yaml --run-dir runs/<run_id>` to inspect outcome state for a specific run.
* For event-intelligence acceptance, inspect recent text event records, entity evidence, classification evidence, topic grouping, event signals, event-market confluence, and event intelligence material.
* For alert-decision acceptance, use `python -m halpha run --config config.example.yaml --until build_alert_decision_material` when final Codex output is not needed.
* For alert-decision acceptance, inspect `analysis/event_intelligence_assessment.json`, `analysis/alert_decisions.json`, `analysis/alert_decision_material.md`, and `run_manifest.json`.
* Alert priority, event severity, decision impact, downgrade reasons, and no-alert states must come from generated artifacts, not Codex wording.
* Use `python -m halpha stage build_alert_decision_material --config config.example.yaml --run-dir runs/<run_id>` to rerun only report-facing alert material against existing upstream artifacts.
* For Codex input acceptance, inspect `run_manifest.json` `codex_input`, `analysis/research_context.md`, `codex_context/context.md`, and `codex_context/prompt.md`.
* For Codex input acceptance, verify full intermediate JSON, raw streams, shared OHLCV history, and full run manifests are referenced by path, not embedded wholesale.
* For on-chain flow acceptance, inspect `raw/onchain_flow.json`, `data/onchain/metadata/onchain_flow_state.json`, `raw/onchain_flow_views.json`, `analysis/onchain_flow_context.json`, `analysis/onchain_flow_material.md`, `analysis/data_quality_summary.json`, and `python -m halpha data inspect --config config.example.yaml`.
* For intelligence-fusion acceptance, inspect `analysis/intelligence_fusion.json`, `analysis/intelligence_fusion_material.md`, decision and alert fusion fields, `analysis/data_quality_summary.json`, `python -m halpha data inspect --config config.example.yaml --run-dir runs/<run_id>`, Codex context boundaries, and the final report when Codex CLI validation is allowed.
* Treat critical asset-mapping errors, false duplicate merges, missing traceability, or unsafe event upgrades as regression-fixture candidates.
* Treat unsafe alert escalation, missing no-alert suppression, or Codex-boundary leakage as regression-fixture candidates.
* For strategy experiment acceptance, inspect `runs/strategy_experiments/<id>/manifest.json` and `strategy_effectiveness_gates.json` for benchmark, experiment, and gate counts.
* For current default strategy acceptance, expect at least three `effective` research candidates under deterministic gates.
* Use `python -m halpha run --config config.example.yaml` for real-source product acceptance when the user permits Codex CLI use.
* State before a real Codex CLI run that generated local research context will be sent to Codex CLI.
* Do not treat fixtures, mocked HTTP responses, or fake Codex subprocesses as product acceptance.
* For docs-only changes, use `git diff --check` when available.
* Do not claim success without proof.
* If validation is blocked, state what was not run and why.
* If a failure is unrelated, say why it is unrelated.

## Git

* Check worktree state before editing.
* Do not overwrite user changes.
* Do not reformat unrelated files.
* Do not rename files casually.
* Do not change license text casually.
* Do not create branches, commits, tags, or releases unless requested.

## GitHub / PRs

* No surprise public writes.
* Do not open issues unless requested.
* Do not open PRs unless requested.
* Do not comment on issues or PRs unless requested.
* If reviewing a PR, inspect the relevant code, tests, and docs before verdict.
* Diff-only review is insufficient for behavior claims.
* Findings need evidence.
* If unsure, state the gap instead of guessing.

## Security

* Never commit secrets, API keys, tokens, cookies, or credentials.
* Use placeholders in examples.
* Prefer `.env.example` over real `.env`.
* Do not log secrets.
* Do not print secrets.
* Do not add telemetry unless requested.
* Do not send research material to remote services unless requested.

## Financial Boundary

Halpha is a personal research project.

Do not present generated content as:

* conclusions without sufficient investigation
* claims not backed by available evidence
* speculative assertions presented as facts
* analysis based on unreliable or unverified online information
* guaranteed forecast
* risk-free strategy

Use cautious language for uncertain market conclusions.

## Reporting

Final task reports should include:

* files changed
* change summary
* validation run
* known gaps

Keep reports brief.

No long narratives.
