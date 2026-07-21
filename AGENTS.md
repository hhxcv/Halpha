# Halpha AI Work Entry Point

Applies to design, implementation, review, documentation, and validation work within the repository. This file provides only the global entry point and does not duplicate specialized methods.

## Authority and Current State

- Product and system semantics come from the Chinese files currently present in `docs/L0`–`docs/L4`; each document exists in one current copy and Git commits record its history.
- Use `docs/L4/HALPHA-PLAN-001-current-plan.yaml` as the entry point for current state; if the file does not exist or lacks a record, treat the state as unknown. Do not use an older Git revision to fill a gap in the current files.
- Halpha is a single-owner, self-funded, personally maintained project. Do not assume institution-grade governance, approval, high-availability, or compliance requirements, and do not describe account or capital scale decided by the owner outside the system as a Halpha capability or guarantee.

## Specialized Guidance Entry Points

- When creating, modifying, splitting, reviewing, or validating L0–L4 documents or the current plan, use [`write-halpha-docs`](.agents/skills/write-halpha-docs/SKILL.md). Maintain the specific layering, ownership, complexity, and validation guidance only in that skill; do not create translations, proposal/accept copies, bundles, responsibility registries, or navigation indexes.
- When implementing, testing, refactoring, qualifying dependencies, changing builds or runtime configuration, or handling implementation evidence that conflicts with design, use [`develop-halpha`](.agents/skills/develop-halpha/SKILL.md). Follow its design-reading, value-tradeoff, impact-validation, and L4/L3/L2+ inconsistency decision gates.
- When designing or reviewing Halpha page scope, information architecture, wireframes, high-fidelity prototypes, interaction states, command feedback, risk confirmation, responsive behavior, accessibility, or UI acceptance evidence, use [`design-halpha-ux`](.agents/skills/design-halpha-ux/SKILL.md). Apply its professional-trader, personal-maintenance complexity, progressive-disclosure, feedback, and risk-control guidance before implementation.
- When investigating a concrete market or strategy question, running or reviewing backtests, evaluating costs, robustness or economic evidence, or working inside `research/**`, use [`research-halpha`](.agents/skills/research-halpha/SKILL.md). Start research directions from current project gaps and a proportionate survey of current external work. Research stays question-first and independent from product runtime; a result does not authorize a product strategy change, capital use or real-account trading action.
- Register future specialized guidance in this section; do not copy complete workflows, templates, or reference material back into this file.

## AI Delegation and Parallel Worktrees

- Within one user-authorized task and its current worktree, Codex may decide whether, when, and how many subagents to use. Do not require fixed counts, mandatory delegation, or user confirmation merely to delegate an in-scope subtask.
- Subagents inherit the parent task's authorization, semantic and path boundaries, effects, and exclusions. They do not authorize a new top-level outcome, worktree, commit, push, real-account trading action, or L4 fact change; the parent task remains the sole integrator and reviews the consolidated diff and validation. Concurrent changes are allowed only when semantic and file scopes do not overlap.
- Separately writable top-level tasks may run concurrently when their paths, product effects, credentials, databases, and exchange-changing effects are independent; writable tasks use separate branches/worktrees and integrate serially. Research that changes only its own workspace and has no product-runtime, database, credential, or exchange-changing effect may start immediately.

## Repository Work Baseline

- Before making changes, confirm task authorization and the applicable specifications; change only the files that own the target meaning and the necessary direct references.
- Preserve unrelated worktree changes; do not overwrite, revert, or incidentally clean up work in progress by the owner.
- Stay within the user-authorized outcome and use continuous small iterations: design only what the next verifiable result needs, implement it, validate it, fix it, and integrate it before selecting the next result. Split the work only when it introduces a real-account trading action, must wait for external evidence, creates a path conflict, or materially expands the authorized result. Never infer a current L4 fact change from code changes.
- Do not keep a mutation-capable task active only to wait for elapsed time or external evidence. Finish mutations before any necessary read-only observation, then use the result only for the decision that requested it; this does not create permanent builder, observer, or finalizer roles and does not require a new top-level task when it remains inside the authorized outcome.
- Use independently testable slices internally, but do not force a new task or user round-trip for every slice inside one already authorized bounded result. Report the consolidated diff, checks, and remaining work at the natural outcome boundary. Never infer authorization to commit, push, change current L4 facts, or perform a real-account trading action.
- Base conclusions on actual reads, diffs, and validation results; do not claim to have run checks that were not run.
- When Codex creates a Halpha strategy plan through the product UI or API within explicit user authorization, it must actively select `AI 创建` in the UI or submit `creator_kind: AI` through the API; it must not leave the human-creation default selected. The origin marker does not authorize fixing, activating, funding, or trading the plan.
