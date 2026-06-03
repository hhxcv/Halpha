---
name: halpha-general-issue-skill
description: Default Halpha skill for GitHub issue metadata work. Use for issue creation, drafting, triage readiness, labels, GitHub milestone assignment, state checks, and duplicate checks. Do not use for issue comments, PRs, code review, or implementation.
---

# Halpha General Issue Skill

Telegraph style. Issue metadata only.

Default skill for Halpha issue handling.

Use for issue title, body, labels, GitHub milestone, state, duplicate checks, and readiness triage.

Do not use for issue comments.
Do not use for PRs.
Do not use for code review.
Do not use for implementation.

## Triggers

Use when the task involves:

- creating an issue;
- drafting an issue;
- checking issue title or body;
- checking issue labels;
- checking issue milestone;
- checking issue open or closed state;
- triaging issue readiness;
- updating issue labels;
- assigning or correcting issue milestone;
- detecting duplicate issues.

Out of scope:

- issue comments;
- PR comments;
- PR review comments;
- PR review;
- code changes;
- future milestone planning.

If comments or PR review are required, stop and report out of scope.

## Hard Rules

- Every issue goal must serve the active milestone, focus user value, preserve product use value, and avoid goal drift.
- Issue creation must always set the active GitHub milestone.
- Do not represent milestones with labels.
- Public issue mutations require explicit write intent.
- Do not create issues for future milestones.
- Do not create speculative architecture issues.
- Do not use issue comments as triage evidence.
- Inspect existing issue metadata before updating it.
- Do not assume implementation exists.
- Do not invent commands, modules, APIs, paths, or behavior.
- Keep every issue small enough for one focused PR.

## Active Milestone

Active milestone source:

```text
MILESTONES.md
```

Before create or triage:

1. Read the active milestone source.
2. Identify the active milestone.
3. Check direct fit.
4. Resolve the matching GitHub milestone.
5. Reject, defer, or ask for owner decision if fit is unclear.

Rules:

- Use the GitHub issue `milestone` field for milestone association.
- Do not use labels for milestone association.
- Do not create placeholders for future phases.
- If the active GitHub milestone is missing, stop before creating an issue and report it.
- Do not create GitHub milestones unless requested.

## Issue Fit

A valid issue must answer:

- What user-facing or product-use value does this create?
- Why is it needed in the active milestone?
- What is the smallest useful scope?
- What observable result proves completion?

Invalid:

- broad architecture cleanup without active-milestone need;
- vague improvement request;
- future feature placeholder;
- implementation preference without product value;
- task too large for one focused PR;
- issue created only because an idea exists.

## Labels

Use one type label:

- `type:task`
- `type:bug`
- `type:docs`
- `type:chore`

Use zero or one area label:

- `area:repo`
- `area:docs`
- `area:core`
- `area:data`
- `area:report`

Use one status label:

- `status:needs-triage`
- `status:ready`
- `status:blocked`

Rules:

- `status:ready`: clear goal, clear scope, observable acceptance, clear active-milestone fit.
- `status:needs-triage`: unclear goal, unclear value, broad scope, missing acceptance, or unclear milestone fit.
- `status:blocked`: blocked by dependency, decision, credential, repo state, permission, or external condition.
- Remove stale status labels before adding a new status label.
- Do not create labels unless requested.
- Do not expand labels early.
- Do not use labels for milestones.

## GitHub Milestone

Use the active GitHub milestone.

Rules:

- New issues must set the GitHub issue `milestone` field to the active milestone.
- Existing issues must be checked against the active GitHub milestone during triage.
- If an existing issue has the wrong milestone, recommend correction.
- If no active GitHub milestone exists, do not create the issue.
- Do not create GitHub milestones unless requested.

## Issue Title

Format:

```text
[type] clear short title
```

Rules:

- Describe the matter clearly.
- Keep it as short as clarity allows.
- Name the artifact or behavior when useful.
- Avoid vague titles.

Examples:

```text
[docs] Add active milestone tracking
[task] Produce minimal report artifact
[chore] Define initial issue labels
[bug] Preserve source metadata in report context
```

Avoid:

```text
Improve project
Make Halpha better
Future architecture ideas
Add everything needed
```

## Issue Body Template

```markdown
## Goal

<One sentence. User or product-use value.>

## Context

<Why this is needed for the active milestone.>

## Scope

- <Included work>
- <Included work>

## Out of Scope

- <Excluded work>
- <Excluded work>

## Acceptance

- [ ] <Observable condition>
- [ ] <Observable condition>
- [ ] <Validation or check condition>
```

Optional:

```markdown
## Notes

<Links, constraints, or known gaps.>
```

Delete `Notes` if empty.

## Body Rules

- Goal is one sentence.
- Goal states value, not only implementation.
- Context ties to the active milestone.
- Scope is narrow.
- Out of Scope blocks drift.
- Acceptance is observable.
- Acceptance does not depend on future milestones.

## Creation Flow

1. Confirm explicit write intent.
2. Read `MILESTONES.md`.
3. Check active milestone fit.
4. Resolve the active GitHub milestone.
5. Search duplicate open issues.
6. Select type, area, and status labels.
7. Draft title and body.
8. Create issue with the GitHub milestone field set.

If duplicate exists:

- do not create a new issue;
- report the duplicate candidate;
- suggest reuse or update.

## Triage Flow

1. Read issue title and body.
2. Check labels, GitHub milestone, and state.
3. Check active milestone fit.
4. Check user or product-use value.
5. Check scope and acceptance.
6. Check duplicate risk.
7. Recommend status labels and GitHub milestone correction.
8. Update only when write intent is clear.

## Mutation Safety

Public issue mutations include:

- creating issues;
- editing issue title or body;
- adding labels;
- removing labels;
- changing GitHub milestone;
- closing issues;
- reopening issues.

Rules:

- Read-only triage may proceed when the issue task is clear.
- Suggestions may proceed without write intent.
- Public mutations require explicit write intent.
- If write intent is unclear, provide the proposed mutation instead of applying it.
- No surprise public writes.
- Do not mutate issue comments.

## PR Link

Issue should be small enough for one PR.

When a PR closes the issue, prefer GitHub closing keywords in PR body:

```text
Closes #<issue-number>
```
