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
* Nearest scoped rule owns local implementation details.
* Root safety, privacy, and financial-disclaimer rules always apply.
* If rules conflict, stop and report the conflict.

## Map

Current repo may be empty or incomplete.

Expected areas, when present:

* Package code: `src/halpha/`
* Tests: `tests/`
* Docs: `README.md`, `AGENTS.md`
* Examples: `config.example.yaml`
* Local run artifacts: `runs/`

Do not create this structure unless the task requires it.

Do not treat planned paths as existing paths.

## Direction

Halpha is an early-stage personal research project.

Target direction:

```text
market data + public information
-> local collection
-> local materials
-> structured research context
-> Codex-ready context
-> Simplified Chinese research report
-> local archive
```

Current bias:

* local-first
* readable artifacts
* source-aware materials
* simple pipeline
* narrow implementation steps
* no premature architecture

## Architecture

* Python-first unless requested otherwise.
* Local-first by default.
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

## Docs

* Docs match current repo state.
* README is for humans.
* AGENTS.md is for AI agents.
* Do not describe planned work as implemented.
* Use `planned`, `intended`, or `not implemented yet` for future work.
* Keep public docs concise.
* Do not add large roadmaps unless requested.
* Do not document commands that do not exist.
* Update docs when user-visible behavior changes.

## Commands

Use existing repo commands only.

If no command exists, say so.

When commands are introduced, document the smallest useful set here.

Expected future commands may include:

```bash
python -m pytest
python -m halpha run --config config.example.yaml
```

Do not claim these commands work until implemented and verified.

## Validation

* Run the narrowest relevant check.
* Prefer tests for changed behavior.
* Use smoke checks for early scaffolding.
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
* Do not send local research material to remote services unless requested.

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
