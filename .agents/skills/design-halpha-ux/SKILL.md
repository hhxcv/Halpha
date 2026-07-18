---
name: design-halpha-ux
description: Design and review Halpha professional-trading-workbench UX against the current ACCEPTED L0-L4 semantics, L4 construction state, P0 complexity limits, trader workflows, interaction safety, visual quality, and impact-appropriate browser evidence. Use when defining or reviewing page inventories, information architecture, navigation, wireframes, high-fidelity prototypes, interaction states, command feedback, risk confirmations, responsive behavior, accessibility, Playwright visual debugging, or UI acceptance evidence for Halpha; also use before implementing a new or materially changed Halpha UI surface.
---

# Halpha UX Design

## Authority and Boundaries

Treat the current `ACCEPTED` L0-L4 set as the authority for product semantics and `docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml` as the authority for current phase and construction scope. A route, mockup, competitor pattern, implementation, or user-interface convention does not create product semantics by itself.

This skill is an execution method, not a parallel design authority. Keep its outputs aligned with `HALPHA-UX-001` task, command, information-layer, visual, decision, control, and quality clauses and with the applicable `HALPHA-UX-002` interaction contract. If this skill, a benchmark, or a prototype implies different product behavior, the accepted documents win; stop the affected slice and route an authorized formal design change through `write-halpha-docs`.

Load the references routed by the workflow below only when their concern is in scope. When routed to a reference, read it in full. Do not turn every localized repair into benchmarking, a full artifact set, or a Playwright campaign.

When changing formal L0-L4 target documents, the responsibility registry, the current plan, or indexes, also use `write-halpha-docs`. When implementing or changing product code, tests, builds, or runtime configuration, also use `develop-halpha`.

Interpret P0 minimal complexity as the fewest justified surfaces, concepts, dependencies, and interaction paths. Do not interpret it as generic SaaS/OA styling, low information value, oversized whitespace, explanatory card grids, or removal of decision-critical trading facts. Do not treat density itself as professionalism: use compactness only when it improves accurate comparison, traceability, or task completion under the accepted scenario.

## Required Workflow

### 1. Choose the Track and Workflow Depth

1. Read the repository `AGENTS.md`, inspect the worktree, and preserve unrelated owner changes.
2. Keep these tracks separate:
   - **Prototype-only:** Create only an isolated design artifact. Mark sample data, target-state capability, and behavioral assumptions; do not modify formal design or the product tree. Owner approval of visual direction does not authorize semantics or implementation.
   - **Formal semantics:** If the work would change a user job, owner, command, state, failure result, support boundary, authority, or risk gate, pause visual resolution and use `write-halpha-docs`. Do not implement the change until the applicable target documents are `ACCEPTED`.
   - **Implementation:** Use `develop-halpha`, the current accepted design, and one authorized construction package. Prototype confirmation does not start implementation automatically.
3. Use the lightweight workflow only for a localized repair to an existing accepted surface that adds no route, user job, authoritative object, command, async state, risk behavior, information-layer contract, or responsive contract. Typical cases are bounded copy, alignment, overflow, focus, contrast, or component-state presentation defects that do not change meaning.
4. Use the full workflow for any new surface or page family, material navigation/information-architecture/density change, high-fidelity redesign, common trading workflow change, or high-risk surface involving capital, exposure, protection, authority, authentication, stopping, takeover, recovery, stale/unknown facts, or consequential commands. When uncertain, use the full workflow.

### 2. Establish Design Authority and Phase

- **Lightweight repair:** Read the exact owning clauses and the complete target artifact or implementation. Record the defect, intended correction, completion check, affected state and viewport, and excluded scope. Load only references whose concern the repair actually changes.
- **New, material, or high-risk surface:** Read [Design Evidence and P0 Scope](references/design-evidence-and-p0-scope.md) in full; read the current plan identity, accepted design set, current state, P0 Web surface, non-goals, complexity budget, applicable conflicts, and exact package when implementation is in scope; then read the complete owning UX L2/L3 and directly relevant domain owners. Build the page-evidence matrix before naming pages.

Search snippets locate evidence; they do not replace authoritative reads. Remove or challenge every surface whose distinct existence is not justified. If accepted documents require a capability but not a dedicated experience, design the smallest adequate interaction.

Do not invent missing semantics. If the accepted set conflicts, lacks a unique owner, or cannot justify a high-impact interaction, stop the affected slice and report the design gap.

### 3. Model the Professional Trader's Job

For the full workflow, define the operator's scan and action loop before arranging components:

1. What can change capital, exposure, protection, or machine authority now?
2. What must remain visible without opening another layer?
3. What changed, what is still pending or unknown, and what is the fact cutoff?
4. What is the next allowed action, its consequence, and its time sensitivity?
5. What evidence or external venue handoff is needed if Halpha cannot establish the result?

For a lightweight repair, verify that the change does not disturb this loop. Optimize for repeated expert use, fragmented attention, fast comparison, numeric accuracy, keyboard navigation, spatial memory, and unambiguous state. Do not optimize primarily for onboarding narration or marketing appearance.

### 4. Benchmark Before Visual Direction

For a new page family, redesign, or high-fidelity prototype, read [Benchmarking Professional Trading UX](references/benchmarking-professional-trading-ux.md) in full. Browse current first-party product material and capture a task-specific comparison matrix. Compare interaction patterns and information value; do not copy brand styling or import capabilities outside Halpha's accepted scope.

Use Apple HIG for component precision, feedback, progress, alerts, focus, and disclosure behavior. Use professional trading products for workspace density, scan order, linked context, order/activity status, and risk-action ergonomics. Resolve conflicts in favor of Halpha semantics and P0 scope.

### 5. Design Information Architecture and Density

Read [Visual Density and Progressive Disclosure](references/visual-density-and-progressive-disclosure.md) in full before creating or materially changing information architecture, wireframes, high-fidelity layout, density, or disclosure. A localized repair that leaves these concerns unchanged may skip it.

1. Specify the always-visible trading context and decision-critical fields.
2. Map content to the accepted conclusion, decision, evidence, and diagnosis layers; then choose inline secondary detail, disclosure/popover, drawer/dialog, or dedicated evidence route as its visual carrier.
3. Prefer stable workbench regions, compact rows, aligned numeric columns, linked selection, and persistent context over large cards and prose.
4. Define normal, selected, hover, focus, disabled, stale, empty, loading, processing, success, rejected, failed, and unknown appearances that actually apply.
5. Use whitespace to separate decisions, not to reduce information value. Measure useful facts and actions per viewport and the interactions required for critical facts.

### 6. Specify Feedback, Async Work, and Risk Controls

Read [Feedback, Async State, and Risk Controls](references/feedback-async-and-risk-controls.md) in full whenever a surface contains commands, background work, external facts, configuration, deletion, protection, stopping, takeover, or other consequential actions.

For every action, specify immediate local response; accepted or submitted acknowledgement and stable identity; processing or waiting state; authoritative effective result; rejected, failed, timed-out, stale, and unknown outcomes; recovery; and duplicate-click, refresh, navigation-away, retry, and interruption behavior.

Never use a toast, spinner, HTTP success, or `PROCESSING` label to imply business effect. Never allow an exception or failed background task to disappear silently. Use only states and command identities supported by the accepted owners.

For every proposed risk-increasing, irreversible, protection-reducing, authority-changing, destructive, or system-stopping action, map the action and its second gate to the accepted owner and command contract. Present the accepted current preview plus explicit command, normally in a confirmation dialog; use an equivalent guard only when it demonstrably prevents accidental activation while presenting target, scope, consequence, current facts, uncertainty, reversibility, and the exact action label. If the action or guard is not owned by accepted design, block the slice and report a design gap. Preserve the accepted reachability of emergency stop, exit, and takeover commands.

### 7. Produce Proportionate Artifacts, Not Accidental Implementation

- For a lightweight repair, produce only the concise repair contract and before/after evidence needed to review the affected states and viewports.
- For the full workflow, produce the applicable page-evidence matrix, critical-field visibility map, interaction/async-state table, risk-action inventory, and page/state inventory. Add a benchmark matrix only when Step 4 applies.

Create low-fidelity structure before high-fidelity styling. For exact Chinese copy, component states, and dense tables, prefer a deterministic design canvas or isolated prototype outside product source. Use generated imagery for mood or visual exploration, not as authoritative interaction specification.

Prototype critical flows in normal, in-progress, rejected/failed, unknown/stale, risk-confirmation, receipt/acknowledgement, and final reconciled states when applicable. A single happy-path screenshot is not sufficient evidence for an operational trading surface.

### 8. Validate and Hand Off

- **Lightweight repair:** Perform an author review and the smallest relevant mechanical or visual check. When an executable visual or interaction behavior changed, inspect the affected route, state, and viewport in a real browser; use Playwright when browser automation is the useful verification method.
- **New, material, or high-risk surface:** Render the accepted desktop and narrow-screen viewports, inspect every screen at full resolution, walk the primary trader task, trace every field and action to accepted semantics, and read [UX Review Checklist](references/ux-review-checklist.md) in full before delivery.
- **Full real-browser gate:** For an executable new/material surface, or any executable surface affecting consequential commands, capital, exposure, protection, authority, authentication, stop, takeover, recovery, stale/unknown facts, or common trading flow, read [Playwright Visual Validation](references/playwright-visual-validation.md) in full and use the `playwright` skill to exercise the applicable interaction states. Unit tests and static screenshots do not satisfy this gate.

For a static image-only prototype with no DOM or executable interaction surface, record Playwright as `NOT_APPLICABLE_STATIC_ARTIFACT` and perform full-resolution visual inspection. Do not describe it as interaction-validated. If a required executable browser gate cannot run because current construction state lacks the runtime, route, or evidence, report `BLOCKED` with the exact missing condition.

Do not ask the owner to reconfirm decisions already fixed by accepted design, L4 scope, or explicit task authorization. Make and justify bounded visual and interaction choices within that authority; when a remaining choice would expand scope, change product/risk semantics, or select among materially different long-lived directions with no evidence-backed default, batch the genuine decision items into one owner handoff using the checklist. Handoff must distinguish accepted requirement, design decision, prototype assumption, unresolved conflict, and implementation status. Do not claim that a polished prototype is implemented, qualified, or eligible for real write.
