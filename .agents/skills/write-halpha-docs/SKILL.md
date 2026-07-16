---
name: write-halpha-docs
description: Guide the creation, modification, splitting, review, index synchronization, and validation of Halpha L0–L4 designs and their documentation. Use when working with docs/L0–L4, docs/proposals, the L2 responsibility registry, the L4 current construction plan, or concept/requirement/rationale indexes, or when deciding design tradeoffs, third-party component reuse, document layering, the unique semantic owner, direct dependencies, proposal/ACCEPTED boundaries, or bilingual bundle completeness.
---

# Halpha Design and Documentation

## Responsibilities and Rule Entry Points

This skill provides only work routing and does not infer product semantics on its own. Product and system semantics come from the Halpha specification or candidate version set applicable to the task: normative work uses only the current `ACCEPTED` L0–L4; candidate work uses the task-specified proposal, candidate baseline, and the same coordinated candidate version set, while always preserving their lack of normative effect.

When performing a task, read all three of the following rule documents in full:

1. [Design Requirements](references/design-requirements.md): Determine what to build, what to reuse, when custom implementation is allowed, and the boundaries of design completeness and complexity.
2. [Documentation Rules](references/documentation-rules.md): Determine which layer owns content, how content is related, which format to use, and how proposal/ACCEPTED status and bilingual bundles are maintained.
3. [Validation and Review Checklist](references/validation.md): Determine how to prove that semantics, scope, relationships, and mechanical results are acceptable.

Treat `HALPHA-DOC-001` as the source of documentation responsibilities, and apply the `HALPHA-ENG-001` principles of small-scoped changes, actual diffs, and graded validation to design and documentation work. When a rule conflicts with the current specification, report the conflict and do not create a parallel source of authority.

## Workflow

### 1. Determine Task Effect and Authorization

First determine whether the task concerns normative specifications, Chinese candidates, current-state records, or review, and remain consistent throughout the task:

- **Normative specifications:** Use only the current `ACCEPTED` documents as the semantic basis; do not use a proposal to fill gaps in normative semantics.
- **Chinese candidates:** Use the Chinese proposal version set specified by the task and also read its declared ACCEPTED baseline; candidates never have current normative effect.
- **Current-state records:** Start from the current `ACCEPTED` L4 plan or fact record; if a record is missing, write “unknown” rather than inferring current state from design or code.
- **Review:** Check both the text's internal consistency and whether the current normative specifications allow it, and report the two conclusions separately.

When a task authorizes only proposal work, modify only the Chinese candidates and the necessary Chinese candidate plan, responsibility registry, and navigation indexes; do not modify en-US files, bundles, normative registries, archives, or accepted normative bodies.

### 2. Establish the Minimum Complete Reading Set

Read each target file in full; do not substitute search snippets for a full reading. Then expand only one level along actual dependencies:

1. Read the relevant construction scope, phase, domain depth, and acceptance priorities in the current construction plan.
2. Read the direct parent documents or clauses declared by the target; when modifying L1 or a high-impact boundary, also read the full L0 document in the current working language.
3. For L2/L3, read the unique owner, direct horizontal dependencies, actually applicable vertical constraints, and adjacent-owner boundaries in the responsibility registry.
4. Read the concept, requirement, and rationale index entries directly referenced by the target; update an index only when the corresponding content is added, moved, or deleted.
5. When the current design proposes a custom implementation of a capability, search the official documentation, versions, licenses, and actual capabilities of mature third-party components; do not conclude from memory that no reusable capability exists.

For normative work, look first for:

- `docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml`
- `docs/L2/l2-responsibility-map.registry.yaml`
- `docs/concept-definition-index.zh-CN.md`
- `docs/requirement-constraint-index.zh-CN.md`
- `docs/decision-rationale-index.zh-CN.md`

For Chinese candidates, use the corresponding plan and responsibility registry in `docs/proposals/`. If a required path does not exist, report the gap and do not invent an authoritative source.

### 3. Complete Design Decisions Before Drafting Documentation

Follow the “component search → capability mapping → gap classification → complexity comparison → decision → validation” gate in [Design Requirements](references/design-requirements.md):

1. Adopt a mature component when it can directly meet the need; do not reimplement the capability.
2. When a gap affects only a negotiable technical or strategy choice, adjust the design to the component's actual capabilities and revalidate it.
3. Retain only the smallest Halpha custom implementation when a non-negotiable product semantic, functional-correctness requirement, or safety boundary cannot be met by the component, or when the component truly lacks the required capability.
4. Do not retain both a component implementation and a parallel custom fallback; manual takeover, an external tool, or explicitly unsupported behavior is not a parallel code implementation.

For each module, explicitly choose `adopt component`, `compromise according to component capabilities`, `minimal supplementary custom implementation`, or `unsupported`. When a component fully provides a module's capability, focus the design on how Halpha uses it, its boundaries, and failure outcomes; do not duplicate the component's internal design.

### 4. Confirm the Highest Layer and Unique Owner

Before writing, state each of the following in one sentence: the target meaning, the highest appropriate layer, the unique semantic owner, current consumers, and the decision or failure behavior being changed. If any cannot be answered, narrow the addition or stop adding it.

Locate content according to [Documentation Rules](references/documentation-rules.md). Split cross-layer content: place the highest long-term tradeoffs in L0, stage-independent overall direction in L1, stable domain principles in L2, long-term detailed module design and adopted component implementation approaches in L3, and current versions, configuration, construction state, and evidence in L4.

### 5. Draft and Synchronize the Minimum Complete Change

Lead with the conclusion, then add only the minimum content needed to make that conclusion executable, able to fail explicitly, and verifiable:

1. Modify the highest layer that owns the semantics; do not duplicate an equivalent rule downstream.
2. Give behavior a real actor, give records real consumers, and give failures explicit outcomes.
3. Delete objects with no consumers, duplicate specifications, industry templates, and platforms or governance unnecessary for a personal project.
4. Synchronize only the direct references, responsibility registries, indexes, and L4 plan entries made inaccurate by this change.
5. Do not establish normative effect information before a proposal is approved; for a normative shared specification bundle, synchronize every authorized language body, the bundle, and hashes.

Whether a normative document change must go through a proposal, what each layer may contain, and all format, relationship, version, and language rules are governed by [Documentation Rules](references/documentation-rules.md).

### 6. Validate and Deliver

Use [Validation and Review Checklist](references/validation.md) to complete semantic review, third-party capability decision review, layer and relationship review, diff inspection, and mechanical validation. At minimum, reread every modified file in full and confirm that it contains no mechanical replacement artifacts, internal contradictions, implicit parallel implementations, or unsupported claims that something is “available.”

Run from the repository root:

```powershell
python .agents/skills/write-halpha-docs/scripts/validate_halpha_docs.py <files-modified-in-this-change...>
```

For a Chinese candidate task, add `--proposal-only`; to check all currently accepted shared specification bundles, add `--accepted-integrity`. The script can detect only mechanical issues and cannot replace semantic and design review.

When `HALPHA-PLAN-001`, a construction gate, package eligibility, or real-write status changes, also run `python governance/validate_construction_plan.py`. This gate validates only machine-readable current-state consistency and does not prove that design semantics are aligned.

When delivering, report the conclusion first, then describe the actual changes, the basis for component reuse and retained custom implementation, the complexity change, validation results, and anything that remains unknown or unauthorized. Do not use document count, length, number of checks, or agreement by multiple people as a proxy for quality.
