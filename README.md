# Halpha

Halpha is an early-stage personal research project focused on market intelligence and quantitative research workflows.

The project explores how market data, public information, and structured reasoning can be organized into a reusable research context for personal analysis and review.

At this stage, Halpha has an implemented M0 core report loop. No stable usage interface or release version is provided yet.

The long-term direction is to build a research assistant that helps transform market signals into clearer, reviewable research materials.

## Status

This repository is currently in the implemented M0 core report loop stage.

Implemented now:

- M0 Python package skeleton.
- `python -m halpha run --config config.example.yaml` entrypoint.
- Run directory creation.
- `run_manifest.json` lifecycle.
- Narrow public Binance market collector.
- `raw/market.json` artifact creation for collected market data or collector errors.
- Narrow public RSS text event collector.
- `raw/text_events.json` artifact creation for collected public text events or collector errors.
- AI-readable market material generation.
- `analysis/market_material.md` artifact creation from `raw/market.json`.
- AI-readable text material generation.
- `analysis/text_material.md` artifact creation from `raw/text_events.json`.
- Research context generation.
- `analysis/research_context.md` artifact creation from analysis materials.
- Codex context artifact generation.
- `codex_context/context.md` and `codex_context/prompt.md` artifact creation.
- Codex CLI report generation from persisted prompt context.
- `report/report.md` artifact creation from Codex stdout when Codex CLI succeeds.
- Codex execution status, exit code, and failure summary recording in `run_manifest.json`.

Not implemented yet:

- Report export formats other than Markdown.

The product command must not emit fake raw data, fake analysis, or a placeholder report.

## Usage

Install the package and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the M0 report loop:

```bash
python -m halpha run --config config.example.yaml
```

`config.example.yaml` uses public source configuration:

- Binance public market data for configured symbols.
- RSS feeds for configured public text sources.
- Codex CLI command and arguments for final report generation.

Required local environment:

- Public network access for configured market and RSS sources.
- A working Codex CLI on `PATH`.
- Codex CLI authentication configured outside this repository.
- Permission for Codex CLI to receive the generated local prompt through stdin.

Expected result in a properly configured online environment: writes `raw/market.json`, `raw/text_events.json`, `analysis/market_material.md`, `analysis/text_material.md`, `analysis/research_context.md`, `codex_context/context.md`, `codex_context/prompt.md`, `report/report.md`, and `run_manifest.json`. If collection or Codex execution fails, artifacts created before the failure and `run_manifest.json` record the failure without fake records or a placeholder report.

Output artifact roles:

- `raw/market.json`: inspectable market observations from configured public market sources.
- `raw/text_events.json`: inspectable public text events from configured RSS sources.
- `analysis/market_material.md`: AI-readable market material derived from raw market data.
- `analysis/text_material.md`: AI-readable text material derived from raw text events.
- `analysis/research_context.md`: structured local research context for report generation.
- `codex_context/context.md`: Codex-readable context artifact with artifact index and embedded research context.
- `codex_context/prompt.md`: prompt sent to Codex CLI through stdin.
- `report/report.md`: Simplified Chinese Markdown report generated from Codex stdout.
- `run_manifest.json`: run lifecycle, stage status, artifact paths, counts, Codex status, and errors.

Automated tests use mocks, fixtures, or fake Codex subprocesses only as test behavior. They are not product inputs and are not accepted as proof of a real-source product run.

Run tests:

```bash
python -m pytest
```

## Project Structure

Current structure:

- `AGENTS.md`: root instructions for AI agents.
- `config.example.yaml`: example M0 source-based configuration.
- `LICENSE`: project license.
- `MILESTONES.md`: active and completed milestones only.
- `pyproject.toml`: Python package metadata and test configuration.
- `README.md`: human-facing overview and structure index.
- `src/halpha/`: M0 Python package.
- `tests/`: focused tests for config, collection, materials, context, Codex runner, and the M0 smoke path.
- `runs/`: intended run artifact area; generated contents are ignored by git.

## Disclaimer

Halpha is a personal research project. It does not provide financial advice, investment recommendations, or trading signals.

