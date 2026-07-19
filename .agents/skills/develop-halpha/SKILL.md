---
name: develop-halpha
description: Guide Halpha implementation, testing, refactoring, dependency checks, builds, runtime configuration, direct operational validation, and design-to-code traceability. Use when developing or modifying Halpha code, migrations, builds, configuration, tests, or runtime checks, or when implementation evidence exposes a suspected L0–L4 design error or conflict.
---

# Halpha Development

## Authority

Use the current files in `docs/L0`–`docs/L4` for product semantics and the current L4 plan for actual scope, component versions, configuration and results. Git commits record document history. A package name is a planning label, not task authorization or a mandatory work boundary. The user's requested outcome defines scope; real external writes, capital changes, commit, push and L4 advancement still require their own authority.

Read [Design Navigation](references/design-navigation.md) in full for every development task. If implementation evidence conflicts with design, also read [Design Inconsistency Protocol](references/design-inconsistency.md). Use `write-halpha-docs` for formal document changes.

Use the least process that preserves correctness. Early, local and reversible work defaults to ordinary Git, direct tests and a short handoff. Add process only for current irreversible effects, real external writes, meaningful concurrency, repeated failures or a decision that actually consumes extra evidence.

## Workflow

### 1. Bound the Outcome

1. Read `AGENTS.md`, inspect the worktree and preserve unrelated changes.
2. Classify the highest actual impact under `HALPHA-ENG-001#ENG-IMP-001`.
3. Read only the L4 blocks that identify the current objective, applicable environment, exact choices, constraints and known results. Read the full plan only when changing it or when the needed state cannot otherwise be found.
4. Keep work inside the user-authorized outcome. Several directly related, independently testable slices may be completed together. Split only for a new external effect, a material scope expansion, a path conflict or evidence that must arrive later.
5. Independent research may proceed in its own workspace when it does not touch product runtime, product databases, credentials or venue writes.

Missing state remains unknown. Code or passing tests never imply product availability, real-write permission or an L4 state change.

### 2. Read by Impact

| Impact | Minimum design set |
|---|---|
| Light | Target files/tests and the directly relevant L4 fact; read an owner only when behavior is encoded. |
| General | Owning L3, relevant L2 boundary, direct dependencies and consumers. |
| Core or unclear | General set plus only the L1/L0 clauses and cross-domain contracts that can change the result. |

Read target code and direct consumers before editing. Search locates owners but does not replace them. Implementation uses the current owning documents; do not substitute an older Git revision or a separate process copy.

### 3. State a Small Contract

Record the problem, expected result, excluded scope and validation. Add semantic owner, key failure behavior and rollback only when relevant. For core trading changes also cover the applicable normal path, duplicate/retry, unknown, stop, protection, takeover and restart cases.

Do not turn the contract into a new status model, approval chain or evidence object. If an unresolved choice changes behavior, report the design gap instead of inventing a default.

### 4. Reuse Before Building

Check a component only when adding, replacing or materially changing it. Verify the current pinned choice against first-party contracts and the target machine to the depth needed by the decision. Prefer direct use, then a small adapter, then the smallest Halpha supplement; explicitly leave a capability unsupported when its maintenance cost exceeds current value. Keep one implementation and one source of truth.

### 5. Implement the Authorized Result

1. Change the semantic owner's implementation and necessary direct consumers.
2. Use small reversible edits; do not require a new user round-trip for each slice already included in the requested result.
3. Add only tests, migrations, configuration and diagnostics that the changed behavior needs.
4. Keep secrets out of code, documents, ordinary logs, browsers and test artifacts. Never cause a real account or capital change without explicit authorization.
5. Do not bypass environment isolation, durable action identity, unique venue writing, fact reconciliation, protection, stop or takeover behavior.

### 6. Validate Proportionately

- **Every change:** run the smallest targeted check that directly exercises the change and likely failure.
- **Shared boundary or state change:** add relevant integration and direct-consumer checks.
- **Executable UX:** inspect the affected route, states and viewports in a real browser when visual or interaction behavior changed.
- **L4 or real-write-state change:** run the general documentation validator and the small governance validator.
- **Core trading change:** exercise normal behavior, the critical counterexample, duplicate/retry and stop or rollback in the closest authorized environment.

Use elapsed observation only when a current release, deployment or real-capital decision needs behavior that direct tests cannot establish. Waiting remains read-only and creates no permanent role or project state. When evidence arrives, verify its source, inputs, time and scope before using it.

### 7. Resolve Design Conflicts

Pause only the affected slice and preserve raw evidence. Use [Design Inconsistency Protocol](references/design-inconsistency.md) to distinguish implementation error, ordinary L4 correction and stable-design change. Independent unaffected work continues.

A project-owner decision is required when the correction changes product direction, domain responsibility, authority, capital meaning or another L2-or-higher rule. An independent second view is required only for core, cross-domain, repeated-escape or high-cost L3 changes. Use `write-halpha-docs` to update the current owning documents; never let code silently establish new semantics.

### 8. Integrate and Deliver

1. Re-read every modified file and the actual diff; remove accidental scope and unused concepts.
2. Run relevant checks and state what was and was not run.
3. Report the outcome, changed scope, design basis, validation, rollback or stop path and remaining unknowns.

Do not infer commit, push, L4 advancement, real credentials or real external writes. Do not keep a mutation-capable task open merely to wait for time or outside evidence.
