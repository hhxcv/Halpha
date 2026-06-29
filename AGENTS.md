# AGENTS.md

Telegraph style. Root rules only. Keep this file short, factual, and stable.

## Purpose

This file defines repository-wide rules for AI coding agents and human contributors.
It should contain only high-signal project constraints that should be loaded for nearly every task.

Keep task workflows in `.agents/skills/`.
Keep durable contracts and explanations in `docs/`.
Keep current and completed milestone state in `MILESTONES.md`.
Do not use this file as a roadmap, artifact catalog, or implementation reference dump.

## Scope

These rules apply to the whole repository unless a closer `AGENTS.md` exists in a subtree.
Before working in a subtree, read the closest scoped `AGENTS.md` if present.
If root and scoped rules conflict, stop and report the conflict.

Use repo-root relative paths in reports and PR text.
Do not use absolute machine paths or `~/` paths.

## Source of Truth

Treat these as source of truth for current behavior, in this order:

1. executable code on the working branch;
2. tests and validation output;
3. schemas, typed contracts, and generated artifacts used by the implementation;
4. accepted ADRs or durable contract documents;
5. README and other prose docs.

If prose docs conflict with code, tests, schemas, or real artifacts, do not treat the prose as current behavior.
Report the mismatch or fix the docs if the task is documentation-related.

Do not invent commands, modules, APIs, files, paths, config keys, artifacts, or behavior.

## Current vs Planned

A claim is current only when it is backed by code, tests, CLI behavior, generated artifacts, schemas/contracts, or an accepted ADR.

A claim is planned, draft, or future when it exists only in roadmap notes, long-term vision docs, issue discussion, milestone text, design notes, or unmerged PRs.

Rules:

- Do not describe planned work as implemented.
- Do not convert roadmap or milestone goals into README/current-doc claims.
- Mark future-facing material with `planned`, `draft`, `intended`, or `not implemented yet`.
- If a document is a planning draft, keep it visibly non-authoritative for current behavior.

## Product Boundary

Halpha is a local-first personal market research and decision-support system.
It collects public market and event evidence, preserves inspectable artifacts, runs deterministic research and validation, prepares bounded AI-readable context, and generates Simplified Chinese research reports unless requested otherwise.

Halpha is not a trading execution system.
Do not add or imply:

- exchange, broker, wallet, or account operations;
- order placement, deposits, withdrawals, or live trading;
- portfolio automation or position sizing from real balances;
- hosted SaaS, multi-user platform, or remote-control assumptions;
- guaranteed forecasts, risk-free strategies, or unsupported market conclusions.

Market outputs must remain evidence-backed research material.
Use cautious language when evidence is incomplete, stale, conflicting, or uncertain.

## AI Boundary

AI/Codex is an explanation and report-writing layer, not the decision engine.

Deterministic code owns:

- data collection and data quality;
- feature, factor, signal, strategy, gate, lifecycle, and outcome calculations;
- regime, risk, decision, watch trigger, event intelligence, alert, and fusion states;
- validation, artifact contracts, and run manifests.

Do not ask AI/Codex to generate or decide:

- source facts, raw records, coverage state, duplicate state, or data-quality state;
- strategy signals, feature values, factor scores, optimization results, gates, lifecycle states, or fusion states;
- action levels, alert priorities, forecasts, trading instructions, or position sizing.

AI-readable context must be bounded and source-aware.
Do not embed full raw streams, full reusable histories, SQLite contents, Parquet tables, full intermediate JSON evidence, private user-state files, or local private values in Codex context by default.

## Milestone Fit

Read `MILESTONES.md` before issue, requirement, architecture, feature, or broad documentation work.

Rules:

- Serve the active milestone unless the user explicitly requests planning outside it.
- Preserve implemented product paths while extending them.
- Prefer the smallest useful end-to-end slice.
- Build process skeletons before deep implementation detail.
- Do not create speculative frameworks, future-phase placeholders, or broad rewrites.
- Do not make reusable contracts, schemas, modules, commands, or artifact names milestone-local unless they are truly transitional.
- If a temporary bridge is unavoidable, mark it explicitly and name the replacement requirement.

## Architecture Rules

- Python-first modular monolith.
- Local-first runtime, local artifacts, and local state by default.
- Halpha-owned artifacts are the stable integration boundary.
- Convert third-party objects, including vectorbt outputs, into Halpha contracts before downstream use.
- Do not persist third-party framework objects as long-term contracts.
- Reuse mature libraries for common data and quant work when needed now.
- Do not add heavy frameworks for architecture display.
- Keep raw data, normalized data, deterministic analysis, AI-readable material, reports, run manifests, shared stores, and runtime state boundaries explicit.
- Shared reusable data is not a per-run report artifact and is not AI context by default.
- Exactly three target resident Halpha process roles exist: `dashboard`, `monitor`, and `schedule`.
- Do not add a hidden supervisor, broker, worker pool, or fourth resident process.
- Do not start resident services, background loops, or destructive migrations unless explicitly requested.

## Data and Artifact Rules

- Production paths use real data, real artifacts, and real flow.
- Fixtures, mocked HTTP responses, fake market data, fake signals, and fake Codex subprocesses are test-only.
- Preserve source names, timestamps, source refs, warning states, error states, and no-lookahead or as-of boundaries where applicable.
- Missing, stale, partial, skipped, degraded, unavailable, failed, and insufficient-evidence states are valid outputs.
- Do not hide failed collection, empty intervals, source disagreement, or weak evidence behind optimistic summaries.
- Keep source material inspectable when practical.
- Do not silently rewrite evidence into conclusions.
- Update durable contract docs only when implemented artifact semantics change.
- Do not duplicate the full artifact catalog in this file.

## Documentation Rules

- Docs must match current repository state.
- README is for human project orientation.
- `AGENTS.md` is for repository-wide AI rules.
- `.agents/skills/` is for task-specific AI workflows.
- `docs/` is for durable project documentation and implementation contracts.
- `MILESTONES.md` records the active and completed milestones only; it is not a roadmap.
- Do not document commands, config keys, files, artifacts, modules, or APIs that do not exist.
- Prefer generated or schema-backed reference docs over hand-written duplicated reference material.
- Keep public docs concise.
- Do not add large roadmaps unless requested.
- Update docs when user-visible behavior, interfaces, commands, or artifact semantics change.
- If behavior changes and docs are intentionally not updated, state why in the PR.

## Privacy and Security

Never commit, print, summarize, or expose:

- secrets, API keys, tokens, cookies, credentials, or account identifiers;
- real local proxy URLs, hostnames, ports, usernames, private endpoints, or machine paths;
- private user-state files, private policy files, private notes, holdings, balances, or exact position data.

Use placeholders in examples.
Prefer gitignored local config files for machine-local settings.
Public config files must remain portable.
Do not add telemetry or send research material to remote services unless explicitly requested.

## Commands

Use existing repository commands only.
If a command does not exist or cannot be run in the current environment, say so.
Do not invent replacements.

Setup:

```bash
python -m pip install -e ".[dev]"
```

General validation:

```bash
python -m pytest
python -m ruff check .
```

Product validation and smoke paths:

```bash
python -m halpha validate --config config.example.yaml
python -m halpha run --config config.example.yaml --no-codex
python -m halpha run --config config.example.yaml --until <stage_name>
python -m halpha stage <stage_name> --config config.example.yaml --run-dir runs/<run_id>
```

CLI entry points documented by README include:

```bash
python -m halpha run --config config.example.yaml
python -m halpha validate --config config.example.yaml
python -m halpha dashboard
python -m halpha schedule --config config.example.yaml
python -m halpha monitor --help
python -m halpha data inspect --config config.example.yaml
python -m halpha backtest --config config.example.yaml --strategy <strategy_name> --symbol <symbol> --timeframe <timeframe>
python -m halpha experiment --config config.example.yaml
python -m halpha text-intel --config config.example.yaml
python -m halpha outcomes inspect --config config.example.yaml
python -m halpha workbench build --config config.example.yaml
```

Full report runs require public network access, configured public sources, a working Codex CLI, and Codex CLI authentication outside this repository.
`--no-codex`, `--until`, `stage`, `validate`, `data inspect`, `outcomes inspect`, and `workbench inspect/build` are useful bounded validation paths.

For docs-only changes, run the narrowest available check.
When a local checkout is available, use:

```bash
git diff --check
```

Do not claim success without command output or other concrete evidence.
If validation is blocked, state what was not run and why.

## Git and PR Rules

- Check worktree state before editing when using a local checkout.
- Do not overwrite user changes.
- Do not reformat unrelated files.
- Do not rename files casually.
- Do not change license text casually.
- Create branches, commits, PRs, issue mutations, or public comments only when explicitly requested.
- Keep one focused change per PR.
- Do not mix unrelated refactors with documentation changes.
- Do not add dependencies without current need and explicit PR justification.

PR descriptions must state:

- what changed;
- why it changed;
- validation run or not run;
- documentation impact;
- known gaps or follow-ups.

Use the Halpha PR-writing skill when drafting PR title or body content.

## Task Skills

Use task-specific skills when they exist.
Do not copy their workflows into this root file.

Known repository skills include:

- issue metadata work: `.agents/skills/halpha-general-issue-skill/SKILL.md`;
- requirement analysis: `.agents/skills/halpha-requirements-analysis-skill/SKILL.md`;
- PR title/body writing: `.agents/skills/halpha-pr-writing-skill/SKILL.md`.

If a requested workflow has no skill yet, keep the implementation narrow and source-backed.

## Reporting

Final task reports should include:

- files changed;
- change summary;
- validation run;
- known gaps.

Keep reports brief. No long narratives.
