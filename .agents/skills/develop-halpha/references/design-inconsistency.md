# Design Inconsistency Protocol During Implementation

## Contents

- [Trigger and Containment](#trigger-and-containment)
- [Minimum Evidence](#minimum-evidence)
- [Exclude Non-Design Errors](#exclude-non-design-errors)
- [Classify and Resolve](#classify-and-resolve)
- [Close and Resume](#close-and-resume)

## Trigger and Containment

Use this protocol when a pinned component or target platform cannot express the documented requirement; interface, state, error, or timing requirements cannot all hold; an external system contradicts a design assumption; required behavior has no unique owner; current clauses require different outcomes; or implementation can continue only by inventing semantics.

Pause the affected slice and external effects, while preserving independent unaffected work. Do not bypass the discrepancy with a special branch, default value, second implementation, undocumented degradation, disabled test, or broader permission.

## Minimum Evidence

Keep only the raw material needed to reproduce the discrepancy and choose a correction:

- requested result, environment and impact;
- relevant L4 values and owning L3/L2 clauses;
- exact diff, failing test, minimal reproduction, log or external response;
- expected versus actual behavior and affected failure path;
- component version, configuration or platform fact when they may be causal;
- the smallest implementation fix, design correction, contraction or human-takeover option.

Keep the conclusion `unknown` when evidence is insufficient. Unknown is neither a component defect nor a document error.

## Exclude Non-Design Errors

Check in order:

1. Did implementation misread the semantic owner, omit a direct dependency, or use an older Git revision or process copy?
2. Is code, test expectation, fixture, migration, configuration, secret reference, environment identity, or input wrong?
3. Do component version, public API, license, platform boundary, and effective configuration match the L4 pinned choice?
4. Is the evidence only a one-off failure, unclosed result, stale fact, synthetic projection, or non-probative cache?
5. Is the discrepancy only an exact parameter, configuration, wiring or current ordering choice that L4 may own?
6. Does current design already define stop, remain-unknown, external human takeover, or explicit non-support as the valid outcome?

If implementation is wrong, fix it and validate by impact. If this is ordinary L4 adaptation, record the final value and evidence without promoting it to an L3 design defect.

## Classify and Resolve

Classify by what the correction must change, not by the file where the problem appeared:

| Layer | Meaning changed by the correction |
|---|---|
| L4 | Current objective, scope, exact version, configuration, wiring, progress, fact or validation result |
| L3 | Durable module boundary, interface, schema, state, error, idempotency, concurrency, component-use contract, authority boundary, or failure semantics |
| L2 | Unique domain responsibility, stable object or decision, business principle, handoff, support boundary, or acceptance semantics |
| L1 | Durable product direction, core user journey, architecture direction, or documentation architecture |
| L0 | Mission, highest tradeoff, role sovereignty, inviolable boundary, trust, or complexity ceiling |

Treat an L4/L3 conflict as L4 only when correcting the current record restores consistency without changing the durable contract. Otherwise classify at the highest meaning changed, then use the smallest path:

- **Implementation or configuration error:** fix it and run impact-appropriate checks.
- **L4 error:** use `write-halpha-docs` to correct the current fact when stable L0–L3 semantics remain unchanged.
- **L3 error:** update the current owning document through `write-halpha-docs`. Add one independent read-only review only when the change is core, cross-domain, repeatedly escaped earlier review or has high failure cost.
- **L2, L1 or L0 change:** give the project owner a concise decision with the conflicting clauses, observable failure, whole-design options, recommendation, migration and rollback. Do not let implementation create the new rule before that decision.

If evidence remains insufficient, keep only the affected result unknown or stopped. Independent slices that do not depend on the issue may continue.

## Close and Resume

After the required decision and document path are complete:

1. Re-read the updated current design and relevant L4 plan blocks. A separate draft or older Git revision is not implementation authority.
2. Update the implementation contract, test expectations, migration, and rollback.
3. Resume only the affected slice and revalidate direct consumers and critical counterexamples at the new highest impact level.
4. Record the issue layer, decision, document path, implementation result and remaining unknowns in the delivery.

Do not substitute "document updated" for current-state evidence or "implementation passed" for a project-owner or user decision.
