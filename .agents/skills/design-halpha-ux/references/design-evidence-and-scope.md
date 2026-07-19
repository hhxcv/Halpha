# Design Evidence and Scope

## Normative Alignment

This skill refines how to design and review Halpha UX; it does not own Halpha behavior. Keep every artifact traceable to the current owners:

| Skill concern | Normative anchor |
|---|---|
| Page and task scope | `HALPHA-UX-001#UX-SCP-001`, `#UX-WRK-001`, and the current L4 construction plan |
| Commands, acknowledgement, and result | `HALPHA-UX-001#UX-CMD-001` and `#UX-CTL-001` |
| Progressive disclosure | `HALPHA-UX-001#UX-INF-001` conclusion, decision, evidence, and diagnosis layers |
| Visual value and density | `HALPHA-UX-001#UX-VIS-001` and the applicable `HALPHA-UX-002` visual contract |
| Consequence preview and risk controls | `HALPHA-UX-001#UX-COG-001`, `#UX-CTL-001`, and the applicable domain/L3 command contract |
| Real rendering and interaction validation | `HALPHA-UX-001#UX-QLT-001`, `#UX-L3-001`, and `HALPHA-UX-002#UX-AUTO-TST-001` |

Use the current documents and plan; do not hard-code an older Git revision from this skill. When an instruction here appears broader than current semantics, narrow it to the current scope or report a formal design gap. Benchmark evidence, design taste, and Playwright findings may reveal a gap, but none can resolve it by themselves.

## Page Need Check

Create a page or major surface only when these short answers justify it:

| Field | Required evidence |
|---|---|
| Proposed route or surface | Stable name; route only if navigation or deep-link identity is needed |
| Current semantic owner | Exact L2/L3 owner and relevant clause |
| Current use | L4 objective and implementation status that actually consume it |
| Professional user job | Time-sensitive decision or repeated expert task it enables |
| Authoritative information | Facts, plan, action or domain result shown |
| Entry and exit | How the owner reaches, resumes, completes, or abandons it |
| Critical states | Normal, pending, failed, rejected, stale, unknown, takeover, or terminal states that apply |
| Actions | Exact documented actions; distinguish request from effective result |
| Minimal carrier | Dedicated route, existing page region, drawer, dialog, popover, disclosure, or no UI |
| Minimality | Why an existing surface or smaller carrier cannot meet the job |

Fail the gate when the surface is justified only by convention, a framework route, competitor imitation, visual balance, or implementation convenience.

## Capability Does Not Imply Visual Expansion

A documented capability may require only a small interaction. Do not promote it into a branded page, dashboard, wizard or navigation area without a current user job.

For example, a required login justifies the smallest clear owner-password interaction and applicable error feedback. It does not by itself justify a marketing panel, brand story, onboarding flow or elaborate second column.

Apply the same reasoning to settings, notifications, evidence views, and maintenance tools. A necessary backend capability does not automatically deserve a first-level product page.

## Personal-Maintenance Complexity Test

For each proposed element, ask:

1. Does it expose a current fact, decision, action, or required recovery path?
2. Will an expert owner use it repeatedly or under time pressure?
3. Can an existing workbench surface carry it without hiding critical meaning?
4. Does it introduce another state, component family, dependency, route, or concept to maintain?
5. Is its lifecycle cost offset by decision value or risk reduction?

Remove elements that fail questions 1 and 2. Prefer merging or disclosure when question 3 is yes. Challenge additions with high costs under questions 4 and 5.

Minimalism means:

- fewer unique page types and workflows;
- one clear source of truth per state;
- one consistent command feedback model;
- mature component reuse;
- no duplicated explanatory or navigation structures;
- no second trading terminal, charting suite, notification center, or strategy editor unless current design changes.

It does not mean:

- low-density screens with little decision value;
- generic admin dashboards or card grids;
- large areas of prose on the primary work surface;
- removing facts professional users need to compare;
- hiding risk, pending, stale, failure, or unknown state.

## Design Gap Rule

If page inclusion, risk behavior, state ownership, or limited-operation access cannot be derived from current documents, do not settle it through visual design. Isolate the affected slice, describe the missing decision, and route formal changes through `write-halpha-docs` when authorized.
