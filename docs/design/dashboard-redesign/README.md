# Dashboard Redesign References

This directory contains the dashboard redesign reference set.

The images are high-fidelity design references, not current implementation
screenshots. `DESIGN_SPEC.md` is the implementation and acceptance standard.

## Files

- `DESIGN_SPEC.md`: page design, component standards, interaction rules, and
  acceptance gates.
- `overview.png`: Overview page.
- `reports.png`: Reports page.
- `strategy-lab.png`: Strategy Lab page.
- `monitor.png`: Monitor page.
- `intelligence.png`: Intelligence page.
- `settings.png`: Settings page.

Do not restore the removed duplicate `dashboard-redesign-overview.png`.

## Navigation Contract

The redesigned dashboard has six primary pages:

- Overview
- Reports
- Strategy Lab
- Monitor
- Intelligence
- Settings

`Artifacts` is intentionally removed from primary navigation. Internal
artifacts, raw JSON, run manifests, logs, and file paths may appear only behind
explicit advanced diagnostics when needed.

The dashboard is the primary local user entry point for Halpha. It should help
users read reports, inspect intelligence, run backtests, control monitoring, and
manage settings through safe UI controls.

Market output is research material, not financial advice.
