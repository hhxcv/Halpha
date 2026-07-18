# Halpha Design Navigation for Development

## Contents

- [Authority and Entry Points](#authority-and-entry-points)
- [L4 Reading Scope](#l4-reading-scope)
- [Task-Based Design Routing](#task-based-design-routing)
- [Value and Tradeoff Sources](#value-and-tradeoff-sources)
- [Index Boundaries](#index-boundaries)
- [Readiness Check](#readiness-check)

## Authority and Entry Points

Follow this direction of authority. Never promote a lower layer, implementation, or index above its owner:

```text
L0 hard boundaries and highest tradeoffs
-> L1 documentation, product, workflow, and architecture direction
-> L2 unique domain ownership and stable semantics
-> L3 durable module contracts, interfaces, states, and component-use contracts
-> L4 current stage, scope, exact versions, configuration, qualification, progress, and evidence
-> implementation and tests
```

Treat only the current `ACCEPTED` L0-L4 set as formal design. A candidate may exist only as a `PROPOSED` version in its affected target L0-L4 path; do not use `docs/proposals/`, an `archive/` directory, or an uncommitted process copy as a design source. Git records history only when an actual commit exists.

## L4 Reading Scope

Start at `docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml`, but load only the complete semantic blocks needed for the task:

1. Always read document identity and `accepted_design_set`, `current_state`, `stable_contract_references`, the target construction package, and the L4 keys it directly references.
2. Read `p0_non_goals`, `complexity_budget`, and `formalization_record` when scope, lifecycle complexity, or a recorded conflict may be affected.
3. Read the full plan only when modifying it, crossing packages or domains, failing to identify the target package, or affecting build order, real-write gates, or recorded upstream conflicts.

L4 selects current depth and exact choices; it cannot create missing stable L0-L3 rules.

## Task-Based Design Routing

| Question | Primary entry | Continue with |
|---|---|---|
| Current state, target package, blockers, versions, configuration, or qualification evidence | Current L4 plan | Target package references and actual evidence |
| Unique owner of stable semantics | `docs/L2/l2-responsibility-map.registry.yaml` | Owning L2 and its scope anchors |
| Module, API, schema, state, error, idempotency, or component-use contract | Owning L3 | Direct L3 dependencies, primary and vertical L2, necessary L1/L0 |
| AI development, impact, tests, release, rollback, or dependency selection | `docs/L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md` | `docs/L3/HALPHA-ENG-002-real-trade-core-technology-stack-and-build-boundaries.zh-CN.md` and L4 |
| Whether product value justifies work | L0 and L1-VIS | L1-FLOW, L1-ARC, rationale index, and current L4 non-goals |
| User journey, stop, takeover, recovery, or external-tool handoff | `docs/L1/HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md` | Relevant horizontal L2/L3, CAP/DAT/UX/EXE constraints, and L4 |
| Topology, authority state, dependency direction, or environment isolation | `docs/L1/HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md` | SYS/ENG and business-owner L2/L3, then L4 |
| Where a document change belongs | `docs/L1/HALPHA-DOC-001-documentation-architecture.zh-CN.md` | `write-halpha-docs` |

Expand only along actual dependencies: read each target owner in full, its direct parent and applicable constraints, direct horizontal dependencies, and actual consumers. Do not load unrelated domains for completeness.

## Value and Tradeoff Sources

Evaluate value in this order; never infer project value from an implementation preference:

1. **Hard boundaries:** Read `HALPHA-CON-001#CON-GOV-003`, `#CON-PRI-001`, and any directly affected L0 clauses. Cost, schedule, or L4 convenience cannot trade away mandatory constraints.
2. **Product value:** Read `HALPHA-CON-001#CON-MIS-001`, `#CON-ECO-001`, `#CON-CMP-001`, plus `HALPHA-VIS-001#VIS-VAL-001`, `#VIS-LOOP-001`, `#VIS-NGL-001`, and `#VIS-FAL-001`. Favor decision, planning, execution, UX, reliable operation, and sustainable maintenance value rather than feature count.
3. **Technical priority:** Read `HALPHA-ARC-001#ARC-QLT-001`, `#ARC-QLT-002`, `#ARC-TEC-001`, and `#ARC-CMP-001`. Among qualified choices, favor mature components, simple topology, few dependencies, one source of truth, and one runtime implementation.
4. **Current value:** Read the relevant L4 `planning_horizon`, target `construction_packages` entry, `p0_non_goals`, `complexity_budget`, `exit_evidence`, and `formalization_record`. Value outside the current package does not expand current authorization.
5. **Why a decision exists:** Use `docs/decision-rationale-index.zh-CN.md` to find the owning `-RAT` clause or L4 key, then read the authoritative text. An index summary does not create a decision.

When goals conflict, reject choices that violate hard boundaries, then use `CON-PRI-001` and `ARC-QLT-001` among qualified options. Count understanding, tests, dependencies, configuration, migration, operations, observability, upgrades, rollback, and personal maintenance—not only lines of code.

## Index Boundaries

- Use `docs/requirement-constraint-index.zh-CN.md` to locate compliance requirements; read the linked `-REQ` owner.
- Use `docs/decision-rationale-index.zh-CN.md` to locate alternatives and rationale; read the linked `-RAT` owner or L4 key.
- Use `docs/concept-definition-index.zh-CN.md` to locate the unique `-DEF` owner for stable objects, roles, states, or classifications.
- Use `docs/L2/l2-responsibility-map.registry.yaml` to locate unique L2 semantic ownership. L4 still controls current construction depth.

Indexes navigate; they are not duplicate specifications. If an index conflicts with its current ACCEPTED owner, follow the owner and handle the index defect through the design inconsistency protocol.

## Readiness Check

Before editing, answer only the questions that can change this task's implementation:

- What package, gate, and exit evidence authorize the slice?
- Who owns the affected semantics, and which direct contracts apply?
- What must succeed, reject, remain unknown, stop, recover, or hand off?
- Which accepted component supplies generic behavior, if component work is in scope?
- Which L4 keys own exact versions, configuration, and qualification state?
- What value is added, what complexity is removed, and what lifecycle cost is introduced?

If an applicable answer is missing, read the owner or report the gap. Do not invent it.
