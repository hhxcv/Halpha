---
name: write-halpha-docs
description: Guide the creation, modification, splitting, review, index synchronization, and validation of Halpha L0–L4 designs and their documentation. Use when working with docs/L0–L4, the L2 responsibility registry, the L4 current construction plan, or concept/requirement/rationale indexes, or when deciding design tradeoffs, third-party component reuse, document layering, the unique semantic owner, direct dependencies, document authority, or bilingual document completeness.
---

# Halpha Design and Documentation

## Responsibilities and Rule Entry Points

This skill provides only work routing and does not infer product semantics on its own. Use the authority and history model defined by `HALPHA-DOC-001`.

Route the task before loading references. Read each selected reference in full, but do not load a reference merely because the skill triggered:

| Reference | Read when |
|---|---|
| [Documentation Rules](references/documentation-rules.md) | Creating, changing, splitting, moving, or synchronizing L0–L4 content or supporting records, and reviewing layer, ownership, language, registry, index, history, or current-state placement. |
| [Design Requirements](references/design-requirements.md) | Adding or changing product/system behavior, stable concepts, records, workflows, design tradeoffs, component reuse, custom implementation, support boundaries, or complexity; also for a substantive design review. |
| [Validation and Review Checklist](references/validation.md) | Performing a review, or finalizing any task that changed documents, registries, indexes, or plans. Load it after the design is frozen if the task is authoring only. |

If scope expands, pause and read the newly applicable reference before acting. A wording, link, metadata, or mechanical synchronization task does not by itself require component research or the design reference.

Treat `HALPHA-DOC-001`, especially `DOC-AIR-001`, as the source of documentation responsibilities and minimum reading direction. Apply the `HALPHA-ENG-001` impact and review rules, small-scoped changes, actual diffs, and graded validation. When a rule conflicts with the current specification, report the conflict and do not create a parallel source of authority.

## Workflow

### 1. Run a Short Preflight

Before research or edits, state one compact preflight:

- **Task mode and authorization:** current-document maintenance, L4 current-state record, or review-only; name the authorized targets and exclusions.
- **Impact:** core, general, or lightweight according to semantic consequence; when uncertain, start one level higher and downgrade only after proving isolation.
- **Layer and owner:** the meaning being changed, its highest appropriate layer, unique semantic owner, and directly affected consumers. For a semantic-free change, state that these remain unchanged.

Remain consistent with the chosen mode:

- **Specifications:** Follow the authority model in `HALPHA-DOC-001` and report any required source that is missing.
- **Current-state records:** Start from the current L4 plan or fact record; if a record is missing, write “unknown” rather than inferring current state from design or code.
- **Review:** Check both the text's internal consistency and whether the current normative specifications allow it, and report the two conclusions separately.

Modify only the affected target documents and necessary direct responsibility-registry, current-plan, and navigation references. L0/L1 keep their paired languages synchronized; L2–L4 remain zh-CN only.

Do not bypass the manual semantic gate for L0–L2 meaning, layer, or ownership changes. Mechanical checks and independent AI review do not replace the project owner's decision on those meanings.

### 2. Establish the Minimum Complete Reading Set

Read each target file in full; do not substitute search snippets for a full reading. Expand only along actual dependencies:

1. For current-state work, enter through `docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml` or the applicable current fact record. For other work, read the relevant L4 scope only when construction scope, current support, sequence, or component evidence affects the task.
2. Read the target's declared parent documents or clauses. Read the full L0 in the current working language only for an L1 or core-impact boundary, overall complexity direction, real-capital scope, or project applicability changes; otherwise read the directly cited L0 clauses.
3. For L2/L3, use `docs/L2/l2-responsibility-map.registry.yaml` to identify the unique owner, direct horizontal dependencies, applicable vertical constraints, and adjacent-owner boundaries; read only those actually involved.
4. Read direct consumers only when the owned meaning may change them. Read concept, requirement, and rationale index entries only when the corresponding owned content is added, moved, renamed, or deleted.
5. When the design route applies and a capability is proposed for custom implementation or component choice, search fixed-version official documentation, licenses, maintenance, platform support, and actual public capabilities. Do not perform this research for unrelated editorial, status, or validation-only tasks.

Read and edit the affected target documents. Read the responsibility registry or L4 plan only when ownership, dependencies, construction scope, support, or synchronization makes it relevant. Report any necessary source that is missing.

### 3. Complete Routed Design Decisions Before Drafting

When the design route applies, follow [Design Requirements](references/design-requirements.md) before drafting. Component research is required only for a custom capability or component choice in scope. Record the actual consumer and result, first-party evidence, gap type, total complexity, and one decision: `adopt component`, `compromise according to component capabilities`, `minimal supplementary custom implementation`, or `unsupported`. Keep insufficient evidence unknown or blocked, one runtime implementation and fact authority, and only Halpha's use contract when a component supplies the capability; do not restate component internals.

### 4. Confirm the Layer, Owner, and L3 Boundary

Before writing, state each of the following in one sentence: the target meaning, the highest appropriate layer, the unique semantic owner, current consumers, and the decision or failure behavior being changed. If any cannot be answered, narrow the addition or stop adding it.

Locate content according to [Documentation Rules](references/documentation-rules.md). Split cross-layer content: place the highest long-term tradeoffs in L0, long-term overall direction in L1, stable domain principles in L2, long-term detailed module design and adopted component implementation approaches in L3, and current scope, versions, configuration, progress, and direct results in L4.

For every authored, modified, or reviewed L0–L3 document, explicitly check the full document for phase narratives, current scope or order, progress or evidence, current deployment or configuration, precise current versions or enablement, and other current-state claims. Move task-owned occurrences to L4; report pre-existing out-of-scope occurrences rather than treating them as stable authority. L3 may retain the long-term component choice and Halpha use contract, but L4 owns current values and direct results.

Treat any phase narrative or construction identifier such as `P0`, `B04`, or `R00` in L0–L3 as a hard layer failure. Move the current meaning to L4 before synchronization or review; do not merely remove the identifier while leaving progress, order, milestone, or current-scope content behind. L0–L2 also must not own precise build-artifact names or fields when ordinary language such as “可重复构建” and “相称验证” is sufficient.

### 5. Draft, Freeze, Then Synchronize

Lead with the conclusion, then add only the minimum content needed to make that conclusion executable, able to fail explicitly, and verifiable:

1. Draft only the semantic owner documents first. Give behavior a real actor, records real consumers, failures explicit outcomes, and delete duplicate or unconsumed complexity.
2. Freeze the design only when meaning and scope, highest layer and owner, behavior/failure/unknown paths, compatibility or migration, and any component/custom boundary are stable, with no known upstream conflict requiring another design decision.
3. After freeze, synchronize only direct references, responsibility-registry entries, indexes, L4 plan entries, and languages made inaccurate by the frozen delta. Do not edit downstream copies while the owned decision is still moving.
4. For L0/L1, update both language bodies in the same change and verify their semantic alignment directly.

Before adding a named concept, persistent record, state family, command, process, database, write path, or governance check, compare it with deletion, ordinary language, direct tests, and a manual step. Keep the new item only when a current consumer changes behavior without it. This comparison is working reasoning, not a new required artifact.

Do not add change-specific governance validators while semantics are still moving. Mechanical validation may enforce stable repository-wide format or layer rules; it must not hard-code one change's parameters, package states, or workflow as a second specification.

If synchronization or review reveals a design change, unfreeze, update the semantic owner first, reassess impact and routed references, then repeat only the invalidated review and synchronization work.

What each layer may contain, and all format, relationship, language, and history rules are governed by [Documentation Rules](references/documentation-rules.md).

### 6. Apply Bounded Independent Review

Independent review derives expectations and counterexamples from the applicable specifications rather than replaying the drafting steps. Bound it by impact:

| Impact | Independent review requirement and cap |
|---|---|
| Core | Require one full independent post-freeze review. Use at most one independent reviewer and let that reviewer perform at most one later targeted delta re-review: two passes total. Do not declare the change acceptable without the full pass. |
| General | Use author review by default. When `HALPHA-ENG-001` triggers a second perspective because of ambiguity, cross-domain change, severe failure, or a repeated escape, use at most one independent reviewer with one full and, if required, one targeted delta pass. Reclassify to core if findings expose core impact. |
| Lightweight | Use author review only; no independent pass unless the change is reclassified. |

The cap limits duplicate reviewer passes, not the L0–L2 manual gate, project-owner decision, or final validation. After review, inspect the actual delta. Require the single targeted delta re-review only when a post-review change alters the impact, highest layer or owner, authority or scope, a core expectation or counterexample, failure/stop/recovery behavior, unique implementation or write authority, complexity ceiling, or the basis of the prior review. Otherwise author-review the delta and invalidated direct references and rerun the applicable mechanical checks.

Stop review when blocking findings are closed, required manual and independent gates are satisfied, final validation passes, and remaining details do not change the core value loop, safety/recovery boundary, unique implementation or write path, or complexity ceiling. If a normative conflict or owner decision remains unresolved after the allowed targeted pass, stop editing and report it; do not add reviewers to manufacture agreement.

### 7. Validate and Deliver

Read [Validation and Review Checklist](references/validation.md) in full. Complete the applicable semantic, component-decision, layer/relationship, actual-diff, and mechanical checks. Reread every modified file in full and confirm that it contains no mechanical replacement artifacts, contradictions, implicit parallel implementations, or unsupported claims that something is “available.” This final gate is required even when earlier review found no issues.

Run from the repository root:

```powershell
python .agents/skills/write-halpha-docs/scripts/validate_halpha_docs.py <files-modified-in-this-change...>
```

The validator checks mechanical structure; it cannot replace semantic and design review.

When `HALPHA-PLAN-001` or real-write status changes, also run `python governance/validate_construction_plan.py`. This check validates only a few machine-readable current-state invariants and does not prove that design semantics are aligned.

When delivering, report the conclusion first, then describe the actual changes, validation results, anything that remains unknown or unauthorized, and, when applicable, the component/custom decision and complexity change. Do not use document count, length, number of checks, or agreement by multiple people as a proxy for quality.
