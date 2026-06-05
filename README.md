# Halpha

Halpha is an early-stage personal research project focused on market intelligence and quantitative research workflows.

The project explores how market data, public information, and structured reasoning can be organized into a reusable research context for personal analysis and review.

At this stage, Halpha is a public project space for recording ideas, planning directions, future experiments, and the initial M0 scaffold. No stable usage interface or release version is provided yet.

The long-term direction is to build a research assistant that helps transform market signals into clearer, reviewable research materials.

## Status

This repository is currently in the initial scaffold stage.

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

The scaffold must not emit fake raw data, fake analysis, or a placeholder report.

## Usage

Install the package and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the current scaffold:

```bash
python -m halpha run --config config.example.yaml
```

Expected current result in an online environment with a configured Codex CLI: writes `raw/market.json`, `raw/text_events.json`, `analysis/market_material.md`, `analysis/text_material.md`, `analysis/research_context.md`, `codex_context/context.md`, `codex_context/prompt.md`, and `report/report.md`. If collection or Codex execution fails, artifacts created before the failure and `run_manifest.json` record the failure without fake records or a placeholder report.

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
- `src/halpha/`: M0 Python package scaffold.
- `tests/`: focused scaffold and config tests.
- `runs/`: intended run artifact area; generated contents are ignored by git.

## Disclaimer

Halpha is a personal research project. It does not provide financial advice, investment recommendations, or trading signals.

