# runs

Local run artifact area.

Generated run contents are local and ignored by git.

Intended per-run layout:

- `raw/`: collected source data.
- `analysis/`: deterministic AI-readable materials.
- `codex_context/`: Codex prompt and context artifacts.
- `report/`: Simplified Chinese Markdown report.
- `run_manifest.json`: run status, stages, sources, artifacts, counts, and errors.

The product run command writes per-run raw inputs, deterministic analysis material,
Codex context, report output, and `run_manifest.json` here.
