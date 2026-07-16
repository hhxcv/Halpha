# UX Review Checklist

Fail the review when a critical item is missing. Do not average safety or semantic failures into an overall visual score.

## Authority and Scope

- [ ] Every page and major surface has an accepted owner, current-phase justification, user job, and minimal carrier decision.
- [ ] Every UX rule used by the artifact maps to the current accepted UX/domain clause; the skill, benchmark, and prototype have not become parallel authorities.
- [ ] Prototype assumptions and target-state data are marked; proposals are not described as current behavior.
- [ ] P0 non-goals and complexity budget are respected.
- [ ] A necessary capability has not been inflated into marketing, onboarding, navigation, or page complexity without evidence.
- [ ] Missing or conflicting semantics are reported instead of invented.

## Professional Trading Value

- [ ] Environment, account, instrument, direction, fact cutoff, exposure, protection, open responsibility, and unknown state are visible whenever applicable.
- [ ] The primary scan path meets the accepted scenario goal without reading paragraphs; any 1-3 second target is identified as a prototype heuristic unless an accepted test owns it.
- [ ] Comparable numbers align and retain units, precision, sign, and timestamp meaning.
- [ ] Repeated expert actions are compact, predictable, and keyboard reachable.
- [ ] The workbench does not resemble a generic SaaS/OA card dashboard.

## Benchmark and Visual Direction

- [ ] A current first-party benchmark matrix exists for the specific task.
- [ ] Borrowed patterns solve documented Halpha problems and do not import out-of-scope capabilities.
- [ ] Component styling is modern, precise, restrained, and consistent across interactive states.
- [ ] Whitespace separates decisions rather than lowering information value.
- [ ] High-fidelity images were inspected at actual target resolution.

## Progressive Disclosure

- [ ] Decision-critical facts and failures remain visible without hover.
- [ ] Explanations, rationale, and deep evidence use appropriate disclosure, drawer, dialog, tab, or detail route.
- [ ] The primary surface does not contain large blocks of avoidable explanatory prose.
- [ ] Tooltips and hover content are keyboard accessible and do not carry the only copy of critical information.
- [ ] Hidden details preserve context and have obvious open, close, and focus-return behavior.

## Feedback and Async Work

- [ ] Every interaction has immediate visible response.
- [ ] Submission acknowledgement is distinct from effective business result.
- [ ] Long-running work has stable identity, current phase, truthful progress, and completion/failure feedback.
- [ ] Rejection, failure, timeout, stale, and unknown states show reason, scope, cutoff, and safe next action.
- [ ] No exception, background failure, notification failure, or external uncertainty can occur silently.
- [ ] Duplicate click, refresh, retry, navigation-away, and interruption behaviors are specified.

## Risk and Error Prevention

- [ ] Every risk-increasing, destructive, protection-reducing, authority-changing, irreversible, or system-stopping action appears in the risk inventory.
- [ ] Each in-scope risk action maps to an accepted command and effective second gate with explicit target, scope, consequence, uncertainty, and action label; unowned actions are blocked as design gaps.
- [ ] Disabled controls explain why and how the condition can change.
- [ ] Emergency stop, exit, and takeover remain reachable under accepted constraints.
- [ ] Success is not claimed before authoritative evidence; unknown is never rendered as safe or complete.

## Accessibility and Responsive Behavior

- [ ] Focus order, focus visibility, dialog trapping, focus return, keyboard operation, and accessible names are defined.
- [ ] Risk, environment, and result do not depend on color alone.
- [ ] Contrast, target size, zoom, overflow, reduced motion, and screen-reader status announcements are checked.
- [ ] Narrow-screen behavior preserves critical commands and facts without pretending to be a separate mobile trading product.

## Real-Browser Visual Debugging

- [ ] An executable prototype or product frontend was inspected through the required Playwright loop at the accepted desktop and narrow-screen viewports.
- [ ] Screenshots or snapshots were inspected before and after critical state transitions for clipping, overflow, overlap, alignment, density, focus, and state legibility.
- [ ] Primary flows exercised loading, success, rejection/failure, stale/unknown, disclosure, confirmation, duplicate prevention, refresh, and navigation behavior as applicable.
- [ ] Page errors, console errors, failed requests, and broken assets were reviewed; no layout or interaction failure was silently ignored.
- [ ] The evidence records exact routes, viewports, states, commands, screenshots/traces, findings, fixes, and unresolved limits.
- [ ] A static image-only artifact is marked `NOT_APPLICABLE_STATIC_ARTIFACT`, has full-resolution visual inspection, and is not described as interaction-validated.

## Confirmation Handoff

Ask the owner to confirm separately:

1. page and route scope;
2. professional information density and scan order;
3. visual character and component polish;
4. progressive disclosure choices;
5. action feedback and long-running status behavior;
6. risk gates and emergency-action reachability;
7. unresolved design conflicts or assumptions.
