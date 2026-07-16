# Halpha AI Work Entry Point

Applies to design, implementation, review, documentation, and validation work within the repository. This file provides only the global entry point and does not duplicate specialized methods.

## Authority and Current State

- Product and system semantics are governed by the current `ACCEPTED L0–L4`; `docs/proposals/` is used only for explicitly authorized drafting, review, or revision tasks and has no normative effect.
- Use `docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml` as the entry point for current state; if the file does not exist or lacks a record, treat the state as unknown. When working with the Chinese candidate set, read the proposal plan explicitly specified by the task and do not describe candidate content as being in effect.
- Halpha is a single-owner, self-funded, personally maintained project. Do not assume institution-grade governance, approval, high-availability, or compliance requirements, and do not describe account or capital scale decided by the owner outside the system as a Halpha capability or guarantee.

## Specialized Guidance Entry Points

- When creating, modifying, splitting, reviewing, or validating L0–L4 documents, Chinese candidates, responsibility registries, the current plan, or documentation indexes, use [`write-halpha-docs`](.agents/skills/write-halpha-docs/SKILL.md). Maintain the specific layering, terminology, content-quality, synchronization-scope, and validation requirements only in that skill.
- Register future specialized guidance in this section; do not copy complete workflows, templates, or reference material back into this file.

## Repository Work Baseline

- Before making changes, confirm task authorization and the applicable specifications; change only the files that own the target meaning and the necessary direct references.
- Preserve unrelated worktree changes; do not overwrite, revert, or incidentally clean up work in progress by the owner.
- Base conclusions on actual reads, diffs, and validation results; do not claim to have run checks that were not run.
