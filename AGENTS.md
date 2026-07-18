# Halpha AI Work Entry Point

Applies to design, implementation, review, documentation, and validation work within the repository. This file provides only the global entry point and does not duplicate specialized methods.

## Authority and Current State

- Product and system semantics are governed only by the current `ACCEPTED L0–L4`. A candidate is expressed by each affected target document in its own L0–L4 path with `PROPOSED` status; do not create a cross-layer proposal file, `docs/proposals/`, or any `archive/` directory.
- Use `docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml` as the entry point for current state; if the file does not exist or lacks a record, treat the state as unknown. A `PROPOSED` target document has no normative effect; use its declared accepted baseline or the most recent accepted Git version for normative work.
- Git records history only at actual commit cadence. Do not archive or copy uncommitted intermediate drafts or process versions; if no commit exists, no historical version needs to be retained.
- Halpha is a single-owner, self-funded, personally maintained project. Do not assume institution-grade governance, approval, high-availability, or compliance requirements, and do not describe account or capital scale decided by the owner outside the system as a Halpha capability or guarantee.

## Specialized Guidance Entry Points

- When creating, modifying, splitting, reviewing, or validating L0–L4 documents, target-document candidates, responsibility registries, the current plan, or documentation indexes, use [`write-halpha-docs`](.agents/skills/write-halpha-docs/SKILL.md). Maintain the specific layering, terminology, content-quality, synchronization-scope, and validation requirements only in that skill.
- When implementing, testing, refactoring, qualifying dependencies, changing builds or runtime configuration, or handling implementation evidence that conflicts with design, use [`develop-halpha`](.agents/skills/develop-halpha/SKILL.md). Follow its design-reading, value-tradeoff, impact-validation, and L4/L3/L2+ inconsistency decision gates.
- When designing or reviewing Halpha page scope, information architecture, wireframes, high-fidelity prototypes, interaction states, command feedback, risk confirmation, responsive behavior, accessibility, or UI acceptance evidence, use [`design-halpha-ux`](.agents/skills/design-halpha-ux/SKILL.md). Apply its professional-trader, P0-complexity, progressive-disclosure, async-feedback, and risk-control gates before implementation.
- Register future specialized guidance in this section; do not copy complete workflows, templates, or reference material back into this file.

## Repository Work Baseline

- Before making changes, confirm task authorization and the applicable specifications; change only the files that own the target meaning and the necessary direct references.
- Preserve unrelated worktree changes; do not overwrite, revert, or incidentally clean up work in progress by the owner.
- An implementation or qualification builder task may write within at most one L4 construction package. Stop at a package boundary and hand the next package off as separately scoped work. An explicitly authorized L4 design/governance coordination may update multiple package records through `write-halpha-docs`, but it must not implement or advance more than one package.
- Do not keep a mutation-capable builder active only to wait for elapsed time or external evidence. End the writable slice and hand observation off as read-only work; finalize only in a separately scoped task after the evidence is ready.
- Treat each independently testable slice as a handoff boundary: report the diff, checks, and remaining work. Continue to another slice only when the user already authorized a bounded multi-slice outcome and it remains inside the same package or explicit non-package scope. Never infer authorization to commit, push, advance L4 state, or begin the next package.
- Base conclusions on actual reads, diffs, and validation results; do not claim to have run checks that were not run.
