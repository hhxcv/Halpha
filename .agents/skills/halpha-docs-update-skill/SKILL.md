---
name: halpha-docs-update-skill
description: Halpha skill for documentation creation, updates, placement, and drift checks. Use for README, docs contracts, runbooks, architecture explanations, AI-readable documentation, command documentation, docs impact checks, and current-vs-planned separation. Do not use for code implementation, PR review, PR comments, issue metadata mutation, or public GitHub writes without explicit write intent.
---

# Halpha Docs Update Skill

Telegraph style. Documentation only.

Default skill for Halpha documentation work.

## Triggers

Use when the task involves:

- creating documentation;
- updating `README.md`;
- updating `docs/` contracts or explanations;
- updating documentation-related skills;
- deciding whether a change needs docs;
- deciding where docs should live;
- checking docs against implementation;
- documenting commands, config, artifacts, schemas, contracts, runtime state, or validation;
- reducing stale, duplicated, or over-detailed documentation.

Out of scope:

- code implementation;
- PR review;
- PR comments;
- issue metadata mutation;
- roadmap writing unless explicitly requested;
- public GitHub writes unless explicitly requested.

## Hard Rules

- Follow root `AGENTS.md`.
- Do not invent commands, files, modules, APIs, config keys, schemas, artifacts, tests, or behavior.
- Do not describe planned work as implemented.
- Current behavior must be backed by code, tests, CLI behavior, generated artifacts, schemas, typed contracts, or accepted durable docs.
- Prose docs are weaker evidence than implementation.
- If prose docs conflict with implementation, fix or report the docs. Do not preserve the conflict.
- Keep documentation value higher than context cost and maintenance cost.
- Prefer updating the owning doc over creating a parallel doc.
- Prefer schema-backed or generated references over hand-written duplicated references.
- Do not duplicate full artifact catalogs, command catalogs, or schema field lists in AI-loaded docs.
- Do not expose secrets, local paths, proxy values, private config, private user state, holdings, balances, or account identifiers.
- If validation was not run, say so.

## Efficiency Gate

Before writing docs, answer:

- Who will read this: AI, human, or both?
- What decision or action will this doc improve?
- What source of truth will keep it correct?
- What future maintenance cost does it create?
- Can this be shorter, generated, linked, or omitted?

Write or update docs only when at least one is true:

- user-visible behavior changed;
- public command, config, artifact, schema, contract, or workflow changed;
- existing docs are stale or misleading;
- a durable boundary is needed to prevent AI/developer drift;
- active milestone acceptance requires docs;
- users need a run, validation, recovery, deletion, or privacy boundary;
- an artifact producer, consumer, Codex boundary, or runtime authority changed.

Do not write docs when:

- the change is internal and clear from code/tests;
- the text only restates names or directories;
- the behavior is speculative;
- the command/path/API/schema/artifact does not exist;
- the content belongs in an issue, PR body, or temporary note;
- the doc would be mostly narrative with no operational constraint.

## Audience Rule

Default for development docs: AI-readable first.

AI-readable docs should optimize for:

- source of truth;
- invariants and prohibitions;
- producer and consumer boundaries;
- artifact paths and lifecycle only when durable;
- exact commands and preconditions;
- current vs planned status;
- failure, warning, skipped, degraded, stale, and insufficient-evidence semantics;
- privacy and Codex-boundary constraints;
- concise bullets and tables over prose.

Human-readable docs should optimize for:

- onboarding;
- common user tasks;
- conceptual orientation;
- safe commands;
- limitations and non-goals.

Owners:

- `README.md`: human-first overview, install, common commands, product boundary.
- `AGENTS.md`: AI-agent root rules only.
- `.agents/skills/*/SKILL.md`: AI task workflows.
- `docs/*-contracts.md`: AI-first durable implementation contracts.
- `docs/artifact-governance.md`: artifact layers, Codex input, runtime authority, docs index.
- `MILESTONES.md`: active and completed milestones only.

If a doc is both human and AI facing, separate the human overview from AI contract details.

## Current vs Planned

Use exact status language:

- `implemented`: current behavior verified by implementation evidence.
- `contract`: durable interface or rule.
- `initial adoption`: first shipped slice of a broader contract.
- `not implemented yet`: future contract detail, not current behavior.
- `planned` or `draft`: roadmap or design content.
- `legacy`: shipped but not preferred.
- `removed`: unsupported.

Rules:

- README describes implemented user-visible behavior only.
- Contract docs may include unimplemented contract direction only when clearly marked.
- Milestone goals are not implementation evidence.
- Tests alone do not make an internal API public.

## Placement Rules

Choose the narrowest owner:

- user-facing install/run/validate/dashboard usage -> `README.md`;
- artifact semantics or Codex boundary -> owning `docs/*-contracts.md`;
- artifact layers, runtime authority, docs index -> `docs/artifact-governance.md`;
- storage, deletion, backup, runtime/shared/run boundary -> `docs/storage-contracts.md`;
- quant strategy, evaluation, signal, optimization, Strategy Lab -> `docs/quant-contracts.md`;
- reusable data, coverage, export, no-lookahead query -> `docs/research-data-contracts.md`;
- dashboard UI/API/job/service behavior -> `docs/dashboard-contracts.md`;
- monitor cycles and alert archive -> `docs/monitoring-contracts.md`;
- decision, risk, watch, alert contracts -> `docs/decision-intelligence-contracts.md`;
- event evidence, topics, confluence -> `docs/event-intelligence-contracts.md`;
- outcome targets/evaluations/history -> `docs/outcome-tracking-contracts.md`;
- AI workflow -> `.agents/skills/<name>/SKILL.md`;
- active or completed milestone state -> `MILESTONES.md`;
- one-off implementation explanation -> PR body or issue, not durable docs.

Create a new doc only when no existing owner can stay coherent.

## Template Rule

Templates are aids, not mandatory structure.

Use the smallest structure that preserves correctness.
Delete empty sections.
Do not force a template when a short patch is clearer.
Do not expand docs merely to satisfy a template.

Minimum contract-doc shape:

```markdown
# <Contract>

## Purpose

## Current Behavior

## Contract

## Validation
```

Add only when needed:

- Scope;
- Out of Scope;
- Produced Artifacts;
- Codex Boundary;
- Runtime State;
- Privacy;
- Failure / Recovery;
- Migration / Legacy.

Minimum how-to shape:

```markdown
# <Task>

## Command

## Expected Output

## Boundaries
```

## Command Rules

Before documenting a command:

1. Confirm it exists in code, README, CLI help, tests, or validated output.
2. State preconditions: network, Codex CLI, local config, shared history, runtime service, destructive apply.
3. Prefer common commands in `README.md`.
4. Prefer detailed behavior in the owning contract doc.
5. Prefer `python -m halpha <command> --help` for full CLI surface.
6. Do not maintain full command catalogs in AI-loaded docs.
7. Do not document destructive commands without dry-run or explicit confirmation boundaries.
8. Do not claim a command passed unless evidence proves it.

## Artifact Rules

When documenting an artifact, include only durable facts:

- path;
- producer;
- consumer;
- layer: raw, shared data, intermediate evidence, material, context, prompt, report, workbench, runtime state, manifest;
- Codex status: embedded, summarized, path-only, or excluded;
- run-local vs shared vs derived vs mutable state;
- warnings, errors, skipped, degraded, stale, insufficient-evidence, no-lookahead, or as-of semantics when relevant;
- deletion or backup boundary when relevant.

Do not include full examples unless short, sanitized, stable, and necessary.

## Update Flow

1. Identify the documentation impact.
2. Classify audience: AI, human, or both.
3. Classify doc type and owner.
4. Read the owning doc and nearby related docs.
5. Inspect implementation evidence.
6. Decide: update, create, delete, reject, or defer.
7. Make the smallest useful change.
8. Update durable cross-links only when needed.
9. Run the narrowest relevant check.
10. Report changed files, validation, and gaps.

Reject or defer when evidence is insufficient.

## Review Checklist

- Is this useful enough to justify context and maintenance cost?
- Is the intended reader clear?
- Is development documentation AI-readable by default?
- Is README kept human-first?
- Is current behavior backed by implementation evidence?
- Is planned work clearly marked?
- Is the owning doc correct?
- Did this avoid duplicate command, artifact, or schema catalogs?
- Did this avoid private local values?
- Did this preserve Halpha boundaries: local-first, artifact-backed, deterministic decisions, AI explanation layer, no trading execution?
- Did validation run, or is the gap stated?

## Output

For analysis-only work:

```markdown
## Documentation Decision

<update | create | delete | reject | defer>

## Target

- `<path>`: <reason>

## Evidence

- <code/test/schema/artifact/command/doc evidence>

## Scope

- <included>

## Out of Scope

- <excluded>

## Validation

- `<command>` or `not run: <reason>`
```

For completed docs work:

```markdown
## Changed Files

- `<path>`

## Summary

- <what changed>

## Validation

- `<command>` or `not run: <reason>`

## Gaps

- <known gap or `None`>
```
