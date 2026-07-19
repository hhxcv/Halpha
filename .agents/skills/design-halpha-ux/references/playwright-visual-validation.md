# Playwright Visual Validation

## Scope and Authority

Use this workflow for every executable Halpha prototype, implemented frontend change, or rendered-UI review. It operationalizes the real-rendering and browser-acceptance requirements in `HALPHA-UX-001#UX-QLT-001`, `#UX-L3-001`, `HALPHA-UX-002#UX-AUTO-TST-001`, and the current L4 plan. It does not create routes, states, commands, breakpoints, or acceptance semantics.

Use the `playwright` skill and a real browser. An available interactive browser debugger may supplement diagnosis, but preserve reproducible Playwright evidence. Vitest, component tests, DOM inspection, axe, and static screenshots are complementary; none replaces this visual interaction loop.

## Mandatory Debug Loop

1. **Establish the target.** Read the current L4 route, viewport, browser, fixture, construction eligibility, and build state. Use an authorized deterministic profile; never create real writes merely to obtain UI evidence.
2. **Start the actual surface.** Serve the exact build or executable prototype under review. Record the startup command, URL, build identity, data profile, and known unavailable dependencies. If the surface cannot run, report `BLOCKED` instead of substituting a mock screenshot.
3. **Open specified viewports.** Inspect the target desktop viewport and the current narrow-screen breakpoint. Add an intermediate width when layout behavior changes between them.
4. **Capture the baseline.** Navigate to each in-scope route with Playwright, wait for stable rendering, and capture a full-page or region screenshot. Inspect the image at native size before interacting.
5. **Exercise behavior.** Use accessible roles, labels, and keyboard input to walk the primary task. Capture the screen after disclosure, selection, validation, submission acknowledgement, processing, final result, rejection/failure, stale/unknown, risk confirmation, refresh, and navigation transitions as applicable.
6. **Inspect layout.** Check clipping, overlap, unintended scroll, sticky-region collisions, drawer/dialog bounds, text truncation, numeric alignment, target size, density, breakpoint reflow, and whether critical state disappears below or behind another layer.
7. **Inspect interaction logic.** Check focus order and return, dialog trapping, keyboard reachability, disabled reasons, duplicate-click prevention, loading and interruption, stale-preview invalidation, refresh/resume, drawer close behavior, error persistence, and distinction between acknowledgement and authoritative result.
8. **Inspect runtime signals.** Review page errors, console warnings/errors, failed requests, redirect loops, missing assets, and unhandled promises for each flow. Keep secret-bearing payloads out of captured evidence.
9. **Iterate and rerun.** Fix each in-scope critical issue, repeat the affected flow, and capture the corrected state. Do not declare completion from a single happy-path screenshot or from tests that were not visually inspected.

## Required Evidence

Record:

- exact command, URL, build/profile, browser, route, and viewport;
- states and interaction steps exercised;
- screenshots, snapshots, or traces before and after critical transitions;
- console, page-error, request-failure, and axe results where applicable;
- each layout or logic finding, its severity, disposition, and rerun result;
- unresolved limitations and whether they are implementation defects, unavailable runtime evidence, or formal design gaps.

Keep static image review separate. When no executable DOM exists, use `NOT_APPLICABLE_STATIC_ARTIFACT`, inspect the artifact at native resolution, and do not claim keyboard, focus, responsive, async, or interaction validation.
