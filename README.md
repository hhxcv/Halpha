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
- Explicit failure for unimplemented product stages.

Not implemented yet:

- market data collection;
- public text event collection;
- analysis material generation;
- Codex report generation.

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

Expected current result: non-zero exit, with a manifest under `runs/<run_id>/run_manifest.json` recording the first unimplemented stage.

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

