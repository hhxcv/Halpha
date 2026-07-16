---
name: design-halpha-ux
description: Design and review Halpha professional-trading-workbench UX against the current ACCEPTED L0-L4 semantics, L4 construction state, P0 complexity limits, trader workflows, interaction safety, visual quality, and real-browser evidence. Use when defining or reviewing page inventories, information architecture, navigation, wireframes, high-fidelity prototypes, interaction states, command feedback, risk confirmations, responsive behavior, accessibility, Playwright visual debugging, or UI acceptance evidence for Halpha; also use before implementing a new or materially changed Halpha UI surface.
---

# Halpha UX Design

## Authority and Boundaries

Treat the current `ACCEPTED` L0-L4 set as the authority for product semantics and `docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml` as the authority for current phase and construction scope. A route, mockup, competitor pattern, implementation, or user-interface convention does not create product semantics by itself.

This skill is an execution method, not a parallel design authority. Keep its outputs aligned with `HALPHA-UX-001` task, command, information-layer, visual, decision, control, and quality clauses and with the applicable `HALPHA-UX-002` interaction contract. If this skill, a benchmark, or a prototype implies different product behavior, the accepted documents win; stop the affected slice and route an authorized formal design change through `write-halpha-docs`.

For every task, read [Design Evidence and P0 Scope](references/design-evidence-and-p0-scope.md) in full. Before delivery, read [UX Review Checklist](references/ux-review-checklist.md) in full.

When changing formal L0-L4 documents, proposals, the responsibility registry, the current plan, or indexes, also use `write-halpha-docs`. When implementing or changing product code, tests, builds, or runtime configuration, also use `develop-halpha`. A prototype-only request authorizes design artifacts, not product implementation.

Interpret P0 minimal complexity as the fewest justified surfaces, concepts, dependencies, and interaction paths. Do not interpret it as generic SaaS/OA styling, low information value, oversized whitespace, explanatory card grids, or removal of decision-critical trading facts. Do not treat density itself as professionalism: use compactness only when it improves accurate comparison, traceability, or task completion under the accepted scenario.

## Required Workflow

### 1. Establish Design Authority and Phase

1. Read the repository `AGENTS.md`, inspect the worktree, and preserve unrelated owner changes.
2. Read the current plan identity, accepted design set, current state, P0 Web surface, non-goals, complexity budget, applicable conflicts, and the exact construction package if implementation is in scope.
3. Read the complete owning UX L2 and L3 documents plus directly relevant domain owners. Search snippets locate evidence; they do not replace full authoritative reads.
4. Build a page-evidence matrix before naming pages. For each proposed route or surface, record the accepted owner, user job, phase necessity, entry and exit, authoritative objects, commands, critical states, and whether an existing surface or progressive disclosure can carry it.
5. Remove or challenge every surface whose distinct existence is not justified. If accepted documents require a capability but not a large dedicated experience, design the smallest adequate interaction.

Do not invent missing semantics. If the accepted set conflicts, lacks a unique owner, or cannot justify a high-impact interaction, stop the affected slice and report the design gap.

### 2. Model the Professional Trader's Job

Define the operator's scan and action loop before arranging components:

1. What can change capital, exposure, protection, or machine authority now?
2. What must remain visible without opening another layer?
3. What changed, what is still pending or unknown, and what is the fact cutoff?
4. What is the next allowed action, its consequence, and its time sensitivity?
5. What evidence or external venue handoff is needed if Halpha cannot establish the result?

Optimize for repeated expert use, fragmented attention, fast comparison, numeric accuracy, keyboard navigation, spatial memory, and unambiguous state. Do not optimize primarily for onboarding narration or marketing appearance.

### 3. Benchmark Before Visual Direction

For a new page family, redesign, or high-fidelity prototype, read [Benchmarking Professional Trading UX](references/benchmarking-professional-trading-ux.md) in full. Browse current first-party product material and capture a task-specific comparison matrix. Compare interaction patterns and information value; do not copy brand styling or import capabilities outside Halpha's accepted scope.

Use Apple HIG for component precision, feedback, progress, alerts, focus, and disclosure behavior. Use professional trading products for workspace density, scan order, linked context, order/activity status, and risk-action ergonomics. Resolve conflicts in favor of Halpha semantics and P0 scope.

### 4. Design Information Architecture and Density

Read [Visual Density and Progressive Disclosure](references/visual-density-and-progressive-disclosure.md) in full before wireframes or high-fidelity work.

1. Specify the always-visible trading context and decision-critical fields.
2. Map content to the accepted conclusion, decision, evidence, and diagnosis layers; then choose inline secondary detail, disclosure/popover, drawer/dialog, or dedicated evidence route as its visual carrier.
3. Prefer stable workbench regions, compact rows, aligned numeric columns, linked selection, and persistent context over large cards and prose.
4. Define normal, selected, hover, focus, disabled, stale, empty, loading, processing, success, rejected, failed, and unknown appearances.
5. Use whitespace to separate decisions, not to reduce information value. Measure useful facts and actions per viewport and the number of interactions required for critical facts.

### 5. Specify Feedback, Async Work, and Risk Controls

Read [Feedback, Async State, and Risk Controls](references/feedback-async-and-risk-controls.md) in full whenever a surface contains commands, background work, external facts, configuration, deletion, protection, stopping, takeover, or other consequential actions.

For every action, specify:

- immediate local response;
- accepted/submitted acknowledgement and stable identity;
- processing or waiting state and, when knowable, progress;
- effective result based on authoritative evidence;
- rejection, failure, timeout, stale, and unknown outcomes with reason and recovery;
- duplicate-click, refresh, navigation-away, retry, and interruption behavior.

Never use a toast, spinner, HTTP success, or `PROCESSING` label to imply business effect. Never allow an exception or failed background task to disappear silently. Use only states and command identities supported by the accepted owners.

For every proposed risk-increasing, irreversible, protection-reducing, authority-changing, destructive, or system-stopping action, map the action and its second gate to the accepted owner and command contract. Use the accepted current preview plus explicit command, normally presented as a confirmation dialog; use an equivalent guard only when it demonstrably prevents accidental activation and still presents target, scope, consequence, current facts, uncertainty, reversibility, and the exact action label. If the action or guard is not owned by accepted design, do not invent it in the prototype: block that slice and report a design gap. Preserve the accepted reachability of emergency stop, exit, and takeover commands; safety confirmation must not become an arbitrary blocking workflow.

### 6. Produce Design Artifacts, Not Accidental Implementation

Before images, produce:

1. page-evidence matrix;
2. benchmark matrix;
3. critical-field visibility map;
4. interaction and async-state table;
5. risk-action inventory;
6. page/state inventory.

Then create low-fidelity structure before high-fidelity styling. For exact Chinese copy, component states, and dense tables, prefer a deterministic design canvas or isolated prototype outside product source. Use generated imagery for mood or visual exploration, not as authoritative interaction specification. Do not modify the product tree when the user requested confirmation before implementation.

Prototype critical flows in at least these states when applicable: normal, in progress, rejected/failed, unknown/stale, risk confirmation, receipt/acknowledgement, and final reconciled result. A single happy-path screenshot is not sufficient evidence for an operational trading surface.

### 7. Validate and Hand Off

1. Render at the accepted target viewport and at the narrow-screen breakpoint.
2. Inspect every screen visually; verify compactness, hierarchy, alignment, overflow, focus, and state legibility.
3. When an executable prototype or product frontend exists, read [Playwright Visual Validation](references/playwright-visual-validation.md) in full and use the `playwright` skill with a real browser to inspect layout and exercise interaction states. Running unit tests or looking only at static screenshots is not sufficient.
4. Walk the primary trader task without explanations from the designer. If critical meaning depends on a paragraph, redesign the hierarchy or disclosure.
5. Trace each field and action back to accepted semantics. Mark prototype data and target-state capability explicitly.
6. Apply [UX Review Checklist](references/ux-review-checklist.md), report failures instead of averaging them away, and revise before requesting confirmation.
7. Ask the owner to confirm page scope, information density, visual direction, disclosure behavior, command feedback, and risk gates separately.

For a static image-only prototype with no DOM or executable interaction surface, record Playwright as `NOT_APPLICABLE_STATIC_ARTIFACT` and perform full-resolution visual inspection. Do not describe a static image as interaction-validated. Any frontend implementation or executable prototype must complete the Playwright loop before handoff unless the current accepted construction state prevents it; in that case report `BLOCKED` with the exact missing runtime or route evidence.

Handoff must distinguish accepted requirement, design decision, prototype assumption, unresolved conflict, and implementation status. Do not claim that a polished prototype is implemented, qualified, or eligible for real write.
