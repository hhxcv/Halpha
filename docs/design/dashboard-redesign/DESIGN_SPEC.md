# Dashboard Redesign Design Specification

This document is the source of truth for implementing the redesigned Halpha
local dashboard. The PNG files in this directory are high-fidelity design
targets. Implementation must be code-native HTML, CSS, and JavaScript rendered
from local data, not embedded screenshots.

This is a user-product design specification. It is not a developer diagnostics
page, artifact inventory, or log browser.

## Reference Images

Use these images as the visual acceptance targets:

- `overview.png`: system status, report operations, monitor state, and data
  health.
- `reports.png`: all reports, Markdown reader, report actions, report metadata.
- `strategy-lab.png`: TradingView-like backtest workspace with candlesticks.
- `monitor.png`: monitor state, control, schedule, records, alerts, and jobs.
- `intelligence.png`: non-OHLCV intelligence review across data categories.
- `settings.png`: profile-based configuration editor and validation surface.

Do not recreate or reference the removed duplicate
`dashboard-redesign-overview.png`.

## Product Positioning

The dashboard is the primary user entry point for Halpha. A normal user should
be able to open the dashboard to:

- understand whether the system is healthy;
- read generated reports;
- trigger a report;
- inspect strategy backtests on a candlestick chart;
- control monitor operation;
- review collected intelligence;
- maintain configuration through safe UI controls;
- clean generated data with clear boundaries and confirmation.

The dashboard must not become:

- a raw artifact browser;
- a run-manifest dump;
- a CLI log viewer;
- a database inspection tool;
- a trading terminal;
- an exchange account tool;
- a portfolio automation system.

Market output is research material, not financial advice.

## Top-Level Navigation

Only these primary pages are allowed:

1. Overview
2. Reports
3. Strategy Lab
4. Monitor
5. Intelligence
6. Settings

`Artifacts` must not be a primary page. Artifact-level inspection may exist only
behind advanced inspect actions when a user is troubleshooting.

Old dashboard concepts map to the new product model:

| Old surface | New placement |
| --- | --- |
| Runs & reports | Reports, with run metadata only as report metadata. |
| Artifacts | Removed from navigation; advanced diagnostics only. |
| Data stores | Intelligence for review, Settings for cleanup. |
| Workbench | Overview summaries and Reports links. |
| Decision & risk | Intelligence detail or report content. |
| Event & alerts | Intelligence and Monitor. |
| Text intelligence | Intelligence Text tab. |
| Outcomes | Intelligence Outcomes tab. |
| Command center | Page-specific actions and Settings jobs, not a top-level page. |

## Global Design System

### App Shell

The shell is stable across all pages.

- Left sidebar is fixed on desktop.
- Sidebar background is dark charcoal or dark navy.
- Brand area is at the top.
- Navigation uses icon plus label.
- Active item uses a light filled row with strong contrast.
- Inactive items are subdued but readable.
- Bottom area may show local mode, health, and research-material disclaimer.
- Main canvas uses a very light neutral or white background.
- Page content is aligned to a consistent left edge.
- Desktop layout should feel like a professional productivity tool, not a
  marketing page and not a debug console.

### Top Status Area

Each page may use a compact top strip or page header controls.

Required behavior:

- show current local profile or config where relevant;
- show timezone or rendered timestamp context where relevant;
- place refresh/help/utility actions on the right;
- keep controls compact and visually quiet;
- avoid turning the top area into a command line.

### Layout Rules

- Primary task area dominates the page.
- Secondary metadata sits in compact side rails or lower panels.
- Do not use two equal columns when one side is clearly the main task.
- Do not build pages from repeated card grids unless the reference image shows
  that pattern.
- Avoid nested cards.
- Repeated comparable data uses rows, tables, tabs, or dropdowns.
- Long selectable lists use dropdowns, compact rows, search, or pagination.
- Pages should avoid whole-page horizontal scrolling.
- Desktop first viewport should show the essential workflow for that page.

### Typography

- Use a clear sans-serif system stack.
- H1 titles are compact and strong.
- Section headings are smaller than page titles.
- Body text is readable at dashboard density.
- Labels, pills, buttons, table cells, tabs, and form controls must have
  explicit font size and line height.
- Long titles must wrap cleanly.
- No one-character columns.
- No clipped button text.
- No hidden overflow for primary report or chart content.

### Color And Status

Use status color consistently:

- Teal: healthy, active, available, succeeded, positive.
- Amber: warning, partial, pending, attention needed.
- Red: failed, error, destructive action.
- Blue: link, information, secondary action.
- Gray: neutral metadata, disabled, separators.

Destructive actions must be visually separated from positive actions and require
confirmation.

### Component Standards

Selectors:

- Use dropdowns for one-of-many selection: report, run, symbol, timeframe,
  strategy, source, profile.
- Use tabs for page-internal categories.
- Use segmented controls only for small mode choices.
- Use filters above the data they affect.

Panels:

- Border and elevation are subtle.
- Radius should stay small, around 6 to 8 px.
- Panels should not be nested inside panels unless the reference image clearly
  requires it.

Tables:

- Use tables for comparable records.
- Columns should have human-readable headers.
- Values should not wrap into unreadable fragments.
- Long fields should truncate with a tooltip or open detail panel.

Charts:

- Charts must communicate the primary user question.
- Strategy Lab candlesticks are mandatory.
- Overview charts are compact trend or health summaries.
- Intelligence charts summarize coverage, severity, category, or freshness.

Markdown:

- Reports render Markdown.
- Default view must not show raw Markdown text.
- Headings, bullets, tables, blockquotes, and links must be styled for reading.
- Reader area owns the page visually on Reports.

Forms:

- Settings uses typed controls, not raw YAML editing.
- Numeric fields use numeric inputs or steppers.
- Time fields use time controls.
- Booleans use toggles or checkboxes.
- Enumerations use dropdowns or segmented controls.
- Lists use chips, multi-select, or editable rows.

Deletion and cleanup:

- Single generated report deletion requires confirmation.
- Multi-run artifact cleanup requires explicit selected-run summary.
- Shared data deletion requires stronger confirmation and clear warning that the
  data may be reused by multiple reports.
- Never make destructive actions the default or primary visual action.

### Timezone

All displayed timestamps must use configured dashboard timezone. Default display
timezone is GMT+8 / Asia/Shanghai unless configuration says otherwise.

Changing dashboard display timezone must not rewrite source artifacts or stored
UTC timestamps.

### Privacy

The dashboard is local-first and privacy-preserving.

Default views must not expose:

- secrets;
- tokens;
- cookies;
- credentials;
- private endpoints;
- account identifiers;
- raw local private paths;
- proxy values;
- raw local user-state files;
- full holdings, balances, allocations, or position sizes.

If a local-only value is necessary for operation, show a safe label or masked
value.

## Page Specifications

## Overview

Reference: `overview.png`

Purpose: answer the user's first question: "Is Halpha healthy, what has it
produced, and what needs attention?"

### Layout

Desktop layout:

- sidebar with Overview active;
- compact top status strip;
- page title `Overview`;
- main report status and operations panel near the top;
- system runtime and monitor panels below;
- data health panel across the lower main area;
- right rail with attention items and quick actions.

The page should be scannable in under one minute.

### Required Content

Reports:

- total report count;
- count by type: daily, monitor-triggered, manual;
- latest report status;
- latest report generated time;
- latest report generation duration;
- average generation duration;
- report success rate;
- small report trend or status distribution;
- actions: generate report, open latest report.

System:

- service start time;
- historical cumulative runtime if available;
- current uptime;
- local data size;
- memory usage;
- storage usage;
- dashboard refresh state.

Monitor:

- current monitor status;
- monitor start time if running;
- trigger count;
- last trigger time;
- next scheduled run if configured;
- recent alert counts;
- actions: pause, start, configure.

Data:

- data volume by class: OHLCV, text, derivatives, on-chain, macro, outcomes;
- validation pass, warning, and error counts;
- freshness status;
- duplicate or conflict summary;
- top anomalies with severity.

Attention rail:

- only actionable issues;
- show severity, short summary, and target action;
- do not show raw logs or manifest snippets.

### Interaction

- Refresh reloads all dashboard summaries.
- Generate report starts a visible job or shows a disabled state with reason.
- Open latest report navigates to Reports with that report selected.
- Attention item links navigate to the relevant page and item when available.

### Empty And Error States

- If no reports exist, show a calm empty report state and a generate action.
- If monitor has never run, show "not started" and setup action.
- If data stores are missing, show missing data category summaries, not JSON.

### Acceptance Checklist

- First viewport shows report, system, monitor, and data status.
- No raw run manifest, raw JSON, stdout, or private local path is visible.
- User can identify the next action without opening developer details.

## Reports

Reference: `reports.png`

Purpose: read and manage all reports, including scheduled reports,
monitor-triggered reports, and manual reports.

### Layout

Desktop layout:

- sidebar with Reports active;
- left report library panel;
- central Markdown reader as the dominant area;
- compact top action bar above the reader;
- right detail rail with outline, metadata, and sources.

The central reader must occupy the largest area on the page.

### Required Content

Report library:

- grouped by Daily, Monitor-triggered, Manual;
- compact rows, not large cards;
- title, type, generated time, status;
- search by title, date, or source when supported;
- selected report state.

Reader:

- rendered Markdown;
- readable headings, paragraphs, lists, tables, and links;
- no raw Markdown as default;
- vertical scrolling inside or around the reader without hiding actions.

Action bar:

- generate report;
- delete selected report;
- download;
- search within current report;
- optional report type filter.

Detail rail:

- outline with section jumps;
- report type;
- run id;
- status;
- generated time;
- duration;
- source summary;
- related data warnings.

### Interaction

- Selecting a report updates the reader and detail rail.
- Outline clicks scroll the reader to the matching section.
- Delete requires confirmation.
- Generate report starts a visible job or shows disabled reason.
- Download exports the selected report.

### Empty And Error States

- No reports: show a report empty state and generate action.
- Report missing Markdown: show unavailable reader state with run metadata.
- Broken Markdown should fail gracefully, not expose raw exceptions.

### Acceptance Checklist

- A normal user can read a report without seeing file paths or artifact names.
- Report selection uses compact rows or dropdown behavior, not a tall run dump.
- Markdown is rendered and visually comfortable.

## Strategy Lab

Reference: `strategy-lab.png`

Purpose: provide a professional backtest workspace comparable to common chart
and backtesting tools.

### Layout

Desktop layout:

- sidebar with Strategy Lab active;
- top configuration toolbar;
- metric strip below toolbar;
- candlestick chart as the dominant page element;
- right rail with parameters, recent trades, and backtest runs;
- bottom analysis tabs below the chart.

The candlestick chart must be visually dominant.

### Required Content

Toolbar:

- symbol selector;
- timeframe selector;
- strategy selector;
- date range;
- run backtest;
- download OHLCV;
- optional overflow actions.

Metrics:

- total return;
- max drawdown;
- Sharpe ratio;
- win rate;
- profit factor;
- trade count;
- average trade or exposure when available.

Chart:

- OHLCV candlesticks;
- volume bars;
- moving average or configured overlays when available;
- buy and sell markers directly on candles;
- price axis;
- time axis;
- hover or crosshair detail where practical;
- selected symbol, timeframe, and strategy visible.

Right rail:

- strategy parameters;
- recent trades;
- backtest run selector/history;
- source coverage status;
- warnings or insufficient-data state.

Bottom tabs:

- trades;
- equity curve;
- drawdown;
- performance summary;
- trade list;
- downloadable OHLCV data.

### Interaction

- Changing symbol, timeframe, or strategy updates available data and chart.
- Run backtest starts a visible job and refreshes metrics when complete.
- Buy/sell marker selection highlights related trade detail.
- Download OHLCV exports the selected data window.

### Boundaries

No trading execution controls. No order placement. No account balances. No
exchange account operations. No position sizing automation.

### Empty And Error States

- If OHLCV history is missing, show missing data state and data collection
  action.
- If strategy has insufficient data, show reason and affected metrics.
- If backtest fails, keep chart layout stable and show actionable error.

### Acceptance Checklist

- Candlestick chart is visible without scrolling on desktop.
- Buy and sell markers are drawn on the chart when trades exist.
- Backtest metrics are visible near the chart.
- Run history is compact and does not become a large card list.

## Monitor

Reference: `monitor.png`

Purpose: control and inspect local monitor operation without exposing low-level
job internals by default.

### Layout

Desktop layout:

- sidebar with Monitor active;
- top monitor summary strip;
- monitor timeline as the main area;
- controls and configuration on the right;
- recent alerts and jobs below.

### Required Content

Summary strip:

- current state;
- last cycle status;
- next report or next scheduled check;
- alerts today;
- warnings and errors.

Timeline:

- cycle started;
- cycle completed;
- warning;
- failure;
- running state;
- time;
- duration;
- result summary;
- key counts;
- detail link when relevant.

Controls:

- start monitor;
- stop monitor;
- run one cycle;
- dry run;
- enable or disable daily report;
- schedule configuration.

Configuration:

- interval;
- max cycles before restart;
- cooldown;
- daily report time;
- watched assets;
- notification channels or local delivery state.

Tables:

- recent alerts with time, severity, summary, status;
- recent jobs with time, job, status, duration.

### Interaction

- Start and stop actions must create explicit visible local job state.
- Dry run validates without collecting or running hidden work.
- Schedule changes must show validation state.
- Timeline filters can narrow status without hiding errors by default.

### Empty And Error States

- No monitor history: show setup and dry-run actions.
- Monitor disabled: show disabled state and enable action.
- Failed cycle: show summary and path to detail without dumping manifest JSON.

### Acceptance Checklist

- User can see whether monitor is running.
- User can safely start, stop, and run one cycle.
- Warnings and errors are actionable.
- Developer diagnostics are not the default surface.

## Intelligence

Reference: `intelligence.png`

Purpose: review collected non-OHLCV intelligence and understand evidence,
coverage, severity, related assets, sources, and linked reports.

### Layout

Desktop layout:

- sidebar with Intelligence active;
- top filters;
- category tabs;
- KPI strip;
- compact intelligence list;
- center charts and evidence summaries;
- right detail panel.

### Required Categories

Tabs:

- Text;
- Derivatives;
- On-chain;
- Macro;
- Outcomes;
- Data quality.

Text:

- news and text events;
- event classification;
- topic grouping;
- related assets;
- source coverage.

Derivatives:

- funding;
- open interest;
- basis;
- premium;
- liquidity depth;
- liquidation availability where implemented.

On-chain:

- flows;
- chain activity;
- liquidity state;
- congestion;
- source availability.

Macro:

- scheduled events;
- freshness;
- source availability;
- realized impact not evaluated state where relevant.

Outcomes:

- outcome targets;
- follow-through;
- evaluation status;
- strategy or report linkage.

Data quality:

- coverage;
- freshness;
- duplicates;
- stale records;
- schema warnings;
- validation errors.

### Required Detail Panel

Selecting an intelligence item updates:

- title;
- category tags;
- severity;
- confidence;
- summary;
- first seen;
- last updated;
- source count;
- related assets;
- related reports;
- concise evidence;
- readable source references.

### Interaction

- Filters affect current tab.
- Reset clears filters.
- Selecting a row updates charts and detail where appropriate.
- Related report opens Reports with the report selected when available.

### Empty And Error States

- If a category has no data, show missing category state and likely source.
- If only partial data exists, show partial coverage and affected sources.
- Do not display raw source payloads by default.

### Acceptance Checklist

- Page feels like an intelligence review desk, not a data dump.
- Tabs organize data classes.
- Full raw JSON is hidden unless advanced diagnostics are explicitly opened.

## Settings

Reference: `settings.png`

Purpose: select and edit configuration profiles through safe UI controls
instead of raw configuration text.

### Layout

Desktop layout:

- sidebar with Settings active;
- top profile selector and validation state;
- left settings section list;
- main parameter editor;
- right rail with pending changes and validation results;
- storage maintenance area near the bottom.

### Required Sections

- General
- Market data
- Strategy
- Reports
- Monitor
- Intelligence sources
- Storage
- Dashboard

### Required Behavior

Profile:

- select active config profile;
- show validation state;
- save changes;
- validate;
- create backup.

Parameter editor:

- booleans use toggles or checkboxes;
- enums use dropdowns;
- numbers use numeric controls;
- times use time controls;
- lists use chips, multi-select, or editable rows;
- local-private values are masked or labeled safely.

Change summary:

- pending changes before save;
- changed section;
- old value label when safe;
- new value label when safe;
- validation warnings and errors.

Storage maintenance:

- separate generated run artifacts from shared reusable data;
- support multi-run generated artifact cleanup;
- warn before shared data deletion;
- show what will be deleted and what will remain;
- require stronger confirmation for shared data.

### Interaction

- Save is disabled when there are no changes or validation blocks saving.
- Validate runs without hidden network collection unless explicitly stated.
- Backup creates a visible local backup action state.
- Cleanup actions require confirmation.

### Empty And Error States

- No profiles: show profile setup state.
- Invalid config: show field-level errors where possible.
- Unsupported parameter: show read-only advanced row, not raw YAML dump.

### Acceptance Checklist

- User edits configuration through controls, not raw YAML.
- Private or local-only values are not exposed.
- Destructive storage cleanup is separated, confirmed, and clear.

## Removed Or Hidden Surfaces

These must not reappear as primary pages:

- Artifacts
- Data stores
- Workbench
- Decision & risk
- Event & alerts
- Text intelligence
- Outcomes
- Command center

Their capabilities must be folded into the six product pages:

- report artifacts become report metadata or advanced report diagnostics;
- data stores become Intelligence summaries and Settings cleanup;
- workbench summaries become Overview and Reports signals;
- command actions become page-local actions;
- event, outcome, and text intelligence become Intelligence tabs;
- monitor command control becomes Monitor.

## Implementation Standards

### Data Shaping

Dashboard APIs should transform artifact data into user-facing view models.
Default UI components should not parse arbitrary raw artifacts in the browser.

Required view-model qualities:

- stable field names;
- status normalized to healthy, warning, failed, partial, missing, skipped;
- timestamps already safe for configured display timezone;
- source refs redacted or converted to safe labels;
- counts and summaries prepared before detail rows.

### Loading

Loading state must preserve the final layout skeleton. It must not collapse to a
single tiny card or leave the page blank.

### Empty States

Empty states must answer:

- what is missing;
- why it may be missing;
- what the user can do next.

Empty states must not blame implementation internals.

### Errors

Errors must be actionable:

- short summary;
- affected area;
- retry or inspect action where safe;
- no stack trace by default.

### Accessibility

- Keyboard focus is visible.
- Buttons have clear labels.
- Icon-only actions have accessible names.
- Contrast is sufficient for status text.
- Destructive actions are distinguishable by more than color where practical.

### Responsive Behavior

Desktop is the primary target. On smaller widths:

- sidebar may collapse;
- right rails move below the main area or become drawers;
- primary task remains first;
- chart and report reader remain usable;
- tables avoid forcing whole-page horizontal scroll.

### Browser Verification

Each page implementation must be validated in a real browser:

- load page by hash or route;
- capture screenshot at a desktop viewport close to the reference;
- compare with matching PNG;
- click primary controls;
- verify loading, empty, warning, and error states;
- verify no console error during normal load.

### Visual Fidelity Gate

A page is not accepted if any of these are visible:

- clipped primary content;
- one-character wrapping;
- raw JSON in default view;
- raw Markdown in Reports reader;
- inert primary controls with no disabled reason;
- repeated diagnostic card lists where a compact selector is expected;
- missing candlestick chart in Strategy Lab;
- missing buy or sell markers when trade data exists;
- private paths, credentials, tokens, or account identifiers;
- page layout materially different from the reference image;
- Artifacts restored as a top-level page.

## PR Acceptance Standard

Every dashboard UI PR must include:

- page or component scope;
- reference image used;
- screenshots or Playwright evidence for affected pages;
- tests or smoke checks for changed behavior;
- statement of any intentional visual deviation;
- privacy boundary confirmation;
- research-material, no-trading boundary confirmation when relevant.

Dashboard changes that alter visible behavior should update this file or
`docs/dashboard-contracts.md` when the product contract changes.
