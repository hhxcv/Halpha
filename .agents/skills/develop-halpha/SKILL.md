---
name: develop-halpha
description: Guide Halpha implementation, testing, refactoring, dependency qualification, build work, and design-to-code traceability. Use when developing or modifying Halpha code, migrations, builds, runtime configuration, qualification probes, or implementation tests, or when implementation evidence exposes a suspected L4, L3, L2, L1, or L0 design omission, error, or conflict.
---

# Halpha Development

## Authority

Treat the current `ACCEPTED` L0-L4 set as the authority for product and system semantics. Treat `docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml` as the authority for current state and construction scope. Translate design into implementation; do not invent product semantics, expand construction scope, change account or capital decisions, or elevate code, tests, or third-party behavior into specifications.

Read [Design Navigation](references/design-navigation.md) in full for every development task. When implementation evidence conflicts with design, also read [Design Inconsistency Protocol](references/design-inconsistency.md) in full. When creating, changing, or validating L0-L4 documents, the responsibility registry, current plan, or indexes, also use `write-halpha-docs` for document ownership, proposal/ACCEPTED boundaries, synchronization, and validation.

Use the least process that satisfies the current impact level. Escalate reading, review, and validation only when the task or observed evidence requires it. Do not weaken the design inconsistency decision gates.

## Workflow

### 1. Confirm Scope, State, and Impact

1. Read the repository `AGENTS.md`, inspect the actual worktree, and preserve unrelated owner changes.
2. Provisionally classify the highest impact under `HALPHA-ENG-001#ENG-IMP-001` before expanding design reads. Use the higher level when uncertain, then confirm the classification after loading the applicable clauses.
3. Read the complete relevant YAML blocks from the current L4 plan: document identity and `accepted_design_set`, `current_state`, `implementation_adaptation_rule`, the target construction package, and every L4 key that package directly references for versions, configuration, gates, or evidence.
4. Read `p0_non_goals`, `complexity_budget`, or `formalization_record` when the task can affect scope, complexity, or a recorded conflict. Read the entire L4 plan only when changing the plan, crossing packages or domains, failing to identify the target package, or affecting build order, real-write gates, or a recorded upstream conflict.
5. Perform only work authorized by the user and allowed by package dependencies. Keep qualification probes, product implementation, DEMO writes, and LIVE writes separated by the L4 environment and gates. Missing state remains unknown; never infer it from code, design completion, or passing tests.

A recorded upstream conflict is resolved only within the exact `formalization_record.conflicts[*].p0_disposition` scope. It is not a general L4 exemption from higher-level design.

### 2. Build an Impact-Scoped Design Set

Use [Design Navigation](references/design-navigation.md) to locate the semantic owner and value rationale, then apply this reading depth:

| Impact | Required design set |
|---|---|
| Light | Read the targeted L4 context and complete target files/tests. For a proven non-semantic auxiliary change, stop there. Read the owning L3/L2 whenever code, configuration, fixtures, or assertions encode behavior. |
| General | Also read the primary owning L3 in full, its direct dependencies, the primary owner L2, applicable vertical L2 constraints, and the responsibility-registry entry. |
| Core or unclear | Use the General set plus the necessary L1/L0 clauses and every direct consumer or cross-domain contract that can change the outcome. |

Always read target code, tests, migrations, configuration, or probes in full before editing, and inspect their direct consumers and existing boundaries. Search locates owners; search snippets do not replace authoritative files.

Use only current `ACCEPTED` documents for formal implementation. Use `docs/proposals/` only for explicitly authorized proposal work, candidate review, or isolated prototypes; never describe candidate content as current design.

If stable rules are absent from L2/L3, accepted clauses directly conflict, or no unique semantic owner can be found, do not invent a code rule. Continue at Step 7.

### 3. State the Implementation Contract

Match the contract to impact:

- **Light:** Record the intent, completion check, and excluded scope in one concise note.
- **General:** Also record the current package, semantic owner, applicable clauses, affected consumers, key failure behavior, validation, and rollback boundary.
- **Core or unclear:** Also cover normal and critical counterexamples; duplicate/retry, unknown, stop, takeover, recovery, and terminal behavior; component reuse; migration; exit evidence; and net lifecycle complexity.

If any unresolved item would change behavior, narrow the slice or report the design gap. Do not choose a default for implementation convenience.

### 4. Qualify Components Only When Relevant

Run this step when adding or replacing a capability or dependency, changing a pinned version/platform, or implementing a generic capability that may already exist. Otherwise retain the accepted component choice and skip new qualification work.

1. Check the owning L3 component contract and the L4 pinned candidate, artifact, platform, and qualification gate. Do not silently upgrade, substitute, or change topology.
2. Verify the pinned version against first-party documentation, public APIs or source, license, target platform, and an actual probe when required. Recheck time-sensitive facts.
3. Separate non-negotiable product semantics, correctness, and safety from negotiable technical or policy choices.
4. Prefer, in order: direct adoption, adaptation to the component, the smallest necessary Halpha supplement, or explicit non-support.
5. Keep one runtime implementation and one source of truth per capability. On qualification failure, stop and return to design; do not add silent, automatic, or permanent parallel fallbacks.

### 5. Implement a Small Slice

1. Implement the smallest independently testable vertical slice that can be rolled back and does not cross package dependencies.
2. Change the semantic owner's implementation and only necessary direct consumers. Shared code must not acquire business-semantic ownership.
3. Add impact-proportionate tests, migrations, configuration identity, stop behavior, and diagnostic evidence with the slice.
4. Keep real secrets out of development tools, AI, browsers, ordinary logs, documents, and test artifacts. Do not cause real account or capital changes without explicit user authorization.
5. Never bypass the single write path, environment isolation, durable action identity, permissions, stop, reconciliation, recovery, or complexity limits for debugging.

### 6. Validate by Impact

- **Core:** Validate the normal path, critical counterexamples, duplicate/retry, and stop/rollback behavior; run relevant automated tests; independently re-derive from requirements or failure scenarios; exercise the critical chain in the closest authorized environment; preserve an executable rollback.
- **General:** Run relevant tests and an actual runtime or rendering check; verify failure behavior and preserve the necessary rollback.
- **Light:** Perform an author review and the smallest relevant mechanical check.

Also verify that authoritative clauses are implemented, third-party behavior matches evidence, unknown database or external outcomes fail closed, required package `exit_evidence` exists, and the complexity budget and single implementation remain intact. Passing tests never advances L4 state, enables real writes, or raises capital scope by itself.

If the task changes `HALPHA-PLAN-001`, a construction gate, package eligibility, or real-write status, run `python governance/validate_construction_plan.py` in addition to the impact-appropriate implementation tests. A passing governance check proves only internal state consistency; it never proves that an upstream semantic conflict is closed.

### 7. Handle Design Inconsistencies

When real code, a pinned component, the target platform, an external system, or test evidence conflicts with design:

1. Pause the affected slice, preserve raw evidence, and read [Design Inconsistency Protocol](references/design-inconsistency.md).
2. Exclude implementation/configuration/environment errors, insufficient evidence, and ordinary L4 adaptation.
3. Classify by the highest stable meaning the fix would change. Use the higher layer and stricter gate when uncertain.
4. Apply the decision gate exactly:

| Highest affected layer | Decision gate |
|---|---|
| L4 | Carefully evaluate higher-level design, implementation evidence, current package, and complexity. If the L4 document is wrong and the correction does not change stable L0-L3 semantics, use `write-halpha-docs` to correct it. Reclassify immediately if stable semantics would change. |
| L3 | Require an independent AI agent to re-derive from raw materials and explicitly confirm an L3 document design error. Only then use `write-halpha-docs` for direct revision or a proposal. If independent review is unavailable or inconclusive, do not decide or edit the L3 design. |
| L2, L1, or L0 | Require a human decision. AI may prepare evidence, impact, options, and a recommendation, but must not edit the affected specification or bypass it in code before the decision. The project owner decides project design and construction scope; the user decides capital, accounts, permission increases, or scope expansion. |

Do not repeat a human decision already accepted and recorded in the current design unless new evidence exceeds its exact scope.

### 8. Re-read, Integrate, and Deliver

1. Re-read every modified file and the actual diff. Remove task-external changes, mechanical replacement residue, hidden second implementations, and undesigned semantics.
2. Run the relevant checks and report exact commands and results. State which relevant checks were not run.
3. Integrate only when evidence meets the slice completion criteria. Use `write-halpha-docs` when the current plan, configuration facts, or qualification evidence must change; a delivery note cannot replace the L4 record.
4. Lead delivery with the outcome, then report implementation scope, direct design basis, component reuse versus retained custom code, validation, rollback/stop path, inconsistency resolution, and remaining unknowns or human decisions.

Never describe code completion, passing tests, accepted documents, component installation, or one external success as "currently available" or "real writes enabled." Current capability claims must come from L4 evidence with source, time, and scope.
