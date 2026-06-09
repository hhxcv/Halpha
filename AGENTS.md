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

* Product runs preserve raw market and text artifacts.
* Shared OHLCV history lives outside per-run report directories.
* Shared OHLCV history is reusable input data, not AI context.
* `raw/market_data_views.json` records current-run OHLCV input windows and storage refs, not full raw history.
* `analysis/quant_strategy_runs.json` records configured strategy run outputs, status, params, diagnostics, evidence, uncertainty, warnings, and source artifacts.
* `analysis/market_strategy_signals.json` records evaluator outputs.
* `analysis/market_signals.json` records normalized report-facing market signals.
* `analysis/market_signal_material.md` is bounded AI-readable signal material.
* `analysis/market_regime_assessment.json` records deterministic market-state assessment.
* `analysis/risk_assessment.json` records deterministic risk-state assessment.
* `analysis/decision_recommendations.json` records deterministic decision-support recommendations, not trading instructions.
* `analysis/watch_triggers.json` records deterministic static watch triggers, not monitoring or alerts.
* Codex context may include signal material, not shared OHLCV history.
* Final reports may include a deterministic quant strategy output table inserted from `analysis/quant_strategy_runs.json` after Codex stdout validation.
* Codex prompt should not ask Codex to recreate the complete strategy run table.
* Reports come from Codex stdout, not placeholder text.
* Fake market data, fake signals, and fake Codex output stay test-only.

## Docs

* Docs match current repo state.
* README is for humans.
* AGENTS.md is for AI agents.
* `docs/` is for durable project documentation and reusable implementation contracts.
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
```

The run command is the implemented product path.

The `--no-codex`, `--until`, and `stage` commands are validation helpers.

They must not fabricate skipped artifacts.

`--no-codex` requires public network access and configured public sources, but not Codex CLI execution.

`--until` runs through the named stage and records later stages as not run.

`stage` runs one named stage against an existing run directory.

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
