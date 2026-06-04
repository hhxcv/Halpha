# runs

Local run artifact area.

Generated run contents are local and ignored by git.

Intended per-run layout:

- `raw/`: collected source data.
- `analysis/`: deterministic AI-readable materials.
- `codex_context/`: Codex prompt and context artifacts.
- `report/`: Simplified Chinese Markdown report.
- `run_manifest.json`: run status, stages, sources, artifacts, counts, and errors.

Current scaffold creates the directories and manifest.

Collection, analysis, and report artifacts are not implemented yet.
