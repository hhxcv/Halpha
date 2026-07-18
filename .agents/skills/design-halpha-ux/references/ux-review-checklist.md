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

- [ ] When visual-direction benchmarking is in scope, a current first-party benchmark matrix exists for the specific task; otherwise the review records why it is not applicable.
- [ ] Borrowed patterns solve documented Halpha problems and do not import out-of-scope capabilities.
- [ ] Component styling is modern, precise, restrained, and consistent across interactive states.
- [ ] Whitespace separates decisions rather than lowering information value.
- [ ] High-fidelity images, when produced, were inspected at actual target resolution.

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

- [ ] An executable prototype or product frontend, when the full real-browser gate applies, was inspected through the required Playwright loop at the accepted desktop and narrow-screen viewports.
- [ ] Screenshots or snapshots were inspected before and after critical state transitions for clipping, overflow, overlap, alignment, density, focus, and state legibility.
- [ ] Primary flows exercised loading, success, rejection/failure, stale/unknown, disclosure, confirmation, duplicate prevention, refresh, and navigation behavior as applicable.
- [ ] Page errors, console errors, failed requests, and broken assets were reviewed; no layout or interaction failure was silently ignored.
- [ ] The evidence records exact routes, viewports, states, commands, screenshots/traces, findings, fixes, and unresolved limits.
- [ ] A static image-only artifact is marked `NOT_APPLICABLE_STATIC_ARTIFACT`, has full-resolution visual inspection, and is not described as interaction-validated.

## Owner Decision Handoff

Do not ask the owner to reconfirm decisions already fixed by the accepted design, current L4 scope, or explicit task authorization. Within those boundaries, the designer may choose and justify information density, scan order, visual character, component polish, progressive disclosure, and feedback presentation, then expose the choices in the handoff for review.

Request one grouped owner decision only when at least one unresolved choice:

1. adds or removes a page, route, user job, command, authoritative object, or support boundary not derivable from the accepted set;
2. changes a risk gate, emergency-action reachability, authority, failure/unknown behavior, or other product semantics;
3. is a materially different long-lived visual direction with no evidence-backed default and would substantially change the delivered result; or
4. depends on a design conflict, scope expansion, or assumption that requires owner authority.

The handoff still records page scope, density and scan order, visual direction, disclosure, async feedback, risk controls, evidence, and unresolved limits. Batch genuine decision items once; do not turn this inventory into seven mandatory approval exchanges.
