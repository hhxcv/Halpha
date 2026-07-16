# Design Inconsistency Protocol During Implementation

## Contents

- [Trigger and Containment](#trigger-and-containment)
- [Evidence Bundle](#evidence-bundle)
- [Exclude Non-Design Errors](#exclude-non-design-errors)
- [Classify the Highest Affected Layer](#classify-the-highest-affected-layer)
- [L4 Handling](#l4-handling)
- [L3 Independent AI Review](#l3-independent-ai-review)
- [Human Decision for L2 and Above](#human-decision-for-l2-and-above)
- [Close and Resume](#close-and-resume)

## Trigger and Containment

Use this protocol when a pinned component or target platform cannot express the documented requirement; interface, state, error, or timing requirements cannot all hold; an external system contradicts a design assumption; required behavior has no unique owner; current ACCEPTED clauses require different outcomes; or implementation can continue only by inventing semantics.

Pause the affected slice and external effects, while preserving independent unaffected work. Do not bypass the discrepancy with a special branch, default value, second implementation, undocumented degradation, disabled test, or broader permission.

## Evidence Bundle

Create the smallest reproducible raw evidence bundle:

- task, current package, environment, and impact level;
- target L4 keys, L3/L2 clauses, and necessary higher-level clauses;
- exact code diff, tests, minimal reproduction, logs, or external response;
- component, pinned version, build identity, configuration, platform, and first-party public evidence;
- expected and actual behavior, failure scope, and normal/counterexample/duplicate/unknown/stop/recovery outcomes;
- implementation, configuration, data, freshness, permission, and environment causes already excluded;
- at least one whole correction and one contraction, stop, human-takeover, or non-support option;
- effects on a single implementation, source of truth, complexity budget, migration, and rollback.

Keep the conclusion `unknown` when evidence is insufficient. Unknown is neither a component defect nor a document error.

## Exclude Non-Design Errors

Check in order:

1. Did implementation misread the semantic owner, omit a direct dependency, or use a proposal or stale version?
2. Is code, test expectation, fixture, migration, configuration, secret reference, environment identity, or input wrong?
3. Do component version, public API, license, platform boundary, and effective configuration match the L4 pinned choice?
4. Is the evidence only a one-off failure, unclosed result, stale fact, synthetic projection, or non-probative cache?
5. Is the discrepancy an exact parameter, configuration, wiring, probe, or within-package ordering change already allowed by the L4 `implementation_adaptation_rule`?
6. Does current design already define stop, remain-unknown, external human takeover, or explicit non-support as the valid outcome?

If implementation is wrong, fix it and validate by impact. If this is ordinary L4 adaptation, record the final value and evidence without promoting it to an L3 design defect.

## Classify the Highest Affected Layer

Classify by what the correction must change, not by the file where the problem appeared:

| Layer | Meaning changed by the correction |
|---|---|
| L4 | Current stage, scope, package, exact version, configuration, wiring, qualification result, progress, fact, or evidence |
| L3 | Durable module boundary, interface, schema, state, error, idempotency, concurrency, component-use contract, authority boundary, or failure semantics |
| L2 | Unique domain responsibility, stable object or decision, business principle, handoff, support boundary, or acceptance semantics |
| L1 | Durable product direction, core user journey, architecture direction, or documentation architecture |
| L0 | Mission, highest tradeoff, role sovereignty, inviolable boundary, trust, or complexity ceiling |

Treat an L4/L3 conflict as L4 only when correcting the L4 record restores consistency without changing the L3 contract. Treat it as L3 when the contract must change, and as L2 when the L3 correction creates or changes L2 semantics. Choose the higher layer when uncertain. Follow a conflict recorded in `formalization_record` only within its exact human disposition; reclassify any extension.

## L4 Handling

Conclude that the L4 document is wrong only after all checks pass:

1. Read the complete target L4 block, primary L3, direct dependencies, and applicable L2; prove that the correction does not change stable L0-L3 semantics.
2. Check `implementation_adaptation_rule`, the current package and exit evidence, third-party-first rules, and the complexity ceiling.
3. Use first-party material for the pinned component, a target-platform reproduction, or authoritative external-system evidence to show that the L4 choice is wrong, incomplete, or infeasible.
4. Compare correcting the document, fixing implementation, narrowing support, and stopping or handing off; choose the qualified option with the lowest total complexity.
5. Confirm the change stays within user authorization, package dependencies, and real-write gates.

If the L4 document is wrong, use `write-halpha-docs` to update the unique current record and necessary direct references. Record source, time, scope, unknowns, migration, and evidence, and let semantic impact determine direct revision versus proposal. If implementation is wrong, change only implementation. If the conclusion remains uncertain, keep the slice blocked.

## L3 Independent AI Review

Treat "L3 document design error" as a conclusion gate requiring an independent AI agent. Self-review by the author or implementation agent, agreement within the same context, confidence scoring, or more tests cannot replace the independent review.

Start a fresh agent that did not participate in implementation:

- Provide the skill path, task, raw evidence bundle, current ACCEPTED target documents, and actual diff or logs.
- Do not provide the author's expected answer, suspected root cause, proposed fix, or a hint to confirm a document error.
- Require a fresh derivation from requirements, counterexamples, and failure outcomes, separately assessing implementation compliance, L3 internal consistency, and permission from higher-level design.
- Require exactly one result: `implementation error`, `L4 record error`, `L3 design error`, `L2-or-higher issue`, or `insufficient evidence`; also require exact clauses, failure impact, and the smallest correction location.
- Default to review-only so file changes do not contaminate the evidence.

Use a neutral task such as:

```text
Use $develop-halpha to independently assess the attached implementation evidence against the current Halpha design.
Re-derive the expected result from the current ACCEPTED L4 plan, target L3, its direct dependencies, and applicable L2.
Report implementation compliance, L3 internal consistency, and higher-level permission separately.
Do not assume the submitter's diagnosis is correct, and do not modify files.
```

Only after the independent agent explicitly confirms an L3 design error, and the correction does not change L2-or-higher semantics, use `write-halpha-docs` to revise L3 directly or through a proposal and revalidate direct consumers. Otherwise follow the independent classification or keep the slice blocked. If an independent agent is unavailable, report that the L3 conclusion gate cannot be completed; do not approve the revision yourself.

## Human Decision for L2 and Above

Any discrepancy whose correction changes L2, L1, or L0 requires a human decision. AI may analyze and recommend, but independent or majority AI opinion is not a decision.

Provide a concise decision brief:

- one decision question and the highest affected layer;
- conflicting clauses, raw implementation evidence, and observable failure;
- options to keep the current design, correct it as a whole, narrow/stop, or use human takeover;
- effects on product value, capital or permission, single implementation, complexity, migration, rollback, and the current package;
- recommendation, rationale, and remaining unknowns.

The project owner decides project design, construction scope, and priority. The user decides product use, accounts, capital limits and scope, real-capital permissions, recovery, or external human takeover. If one human holds both roles, state the decision capacity separately.

Before the decision, do not edit affected L2/L1/L0 specifications or let implementation establish de facto semantics. Continue only read-only diagnosis, risk reduction, and independent slices that do not depend on the decision.

## Close and Resume

After the required decision and document path are complete:

1. Re-read the updated current ACCEPTED design and relevant L4 plan blocks. A proposal is not implementation authority before acceptance.
2. Update the implementation contract, test expectations, migration, and rollback.
3. Resume only the affected slice and revalidate direct consumers and critical counterexamples at the new highest impact level.
4. Record the issue layer, decision maker or independent-review result, document path, implementation result, and remaining unknowns in the delivery.

Do not substitute "document updated" for current-state evidence or "implementation passed" for a project-owner or user decision.
