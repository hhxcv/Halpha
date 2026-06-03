---
name: halpha-general-issue-skill
description: Default Halpha skill for GitHub issue work. Use for any issue-related request, including creating structured issues, reviewing issue state, triaging issue readiness, and updating labels or milestone assignment. Keep issues aligned with the active milestone and focused on user value and product use value.
---

# Halpha General Issue Skill

Telegraph style. Issue workflow only.

Default skill for Halpha issue handling.

Use this skill for any request involving GitHub issues.

## Triggers

Use this skill when the task involves:

- creating an issue;
- drafting an issue;
- reviewing an issue;
- triaging an issue;
- labeling an issue;
- updating issue labels;
- checking issue milestone fit;
- assigning or correcting issue milestone;
- detecting duplicate issues;
- preparing issue structure;
- deciding whether an issue is ready for PR work.

Do not use this skill for:

- implementing code;
- reviewing PR code;
- changing repository files;
- writing release notes;
- planning future milestones.

## Scope

- Create structured issues.
- Review existing issue state.
- Suggest issue labels.
- Update issue labels when write intent is clear.
- Assign or correct milestone when write intent is clear.
- Triage issue readiness.
- Keep issues aligned with the active milestone.
- Keep issues focused on user value and product use value.
- Do not manage PRs here.
- Do not implement code here.
- Do not create future roadmap issues.

## Hard Rules

- Every issue goal must serve the active milestone, focus user value, preserve product use value, and avoid goal drift.
- Issue creation must always use the active milestone.
- Issue creation must always apply the active milestone label when milestone labels are used.
- Public issue mutations require explicit write intent.
- Do not create issues for future milestones.
- Do not create speculative architecture issues.
- Inspect existing issue before updating it.
- Do not assume implementation exists.
- Do not invent commands, modules, APIs, paths, or behavior.
- Keep every issue small enough for one focused PR.

## Mutation Safety

Public issue mutations include:

- creating issues;
- editing issue title or body;
- adding labels;
- removing labels;
- changing milestone;
- adding comments;
- closing issues;
- reopening issues.

Rules:

- Read-only triage may proceed when the issue task is clear.
- Suggestions may proceed without write intent.
- Public mutations require explicit write intent.
- If write intent is unclear, provide the proposed mutation instead of applying it.
- No surprise public writes.

## Active Milestone Rule

The active milestone is the only valid target.

Before creating or triaging an issue:

1. Read the active milestone source.
2. Identify the active milestone.
3. Check whether the issue directly serves it.
4. Reject, defer, or ask for owner decision if fit is unclear.

Active milestone source:

```text
MILESTONES.md
```

Do not use this skill to plan future milestones.

Do not create placeholder issues for future phases.

## Issue Fit

A valid issue must answer:

- What user-facing or product-use value does this create?
- Why is it needed in the active milestone?
- What is the smallest useful scope?
- What observable result proves completion?

Invalid issue patterns:

- broad architecture cleanup without active-milestone need;
- vague improvement request;
- future feature placeholder;
- implementation preference without product value;
- task too large for one focused PR;
- issue created only because an idea exists.

## Issue Types

Use one type label.

Allowed type labels:

- `type:task`
- `type:bug`
- `type:docs`
- `type:chore`

Rules:

- `type:task`: user-visible or product-use behavior work.
- `type:bug`: existing behavior is wrong or broken.
- `type:docs`: documentation-only work.
- `type:chore`: repo maintenance with clear active-milestone value.

Do not add more type labels unless the existing set is insufficient.

## Area Labels

Use zero or one area label.

Allowed area labels:

- `area:repo`
- `area:docs`
- `area:core`
- `area:data`
- `area:report`

Rules:

- `area:repo`: repository setup, metadata, GitHub workflow.
- `area:docs`: README, AGENTS, milestone docs, public docs.
- `area:core`: core product behavior.
- `area:data`: input, loading, raw material handling.
- `area:report`: context, report material, report output.

Do not create narrow area labels early.

## Status Labels

Use one status label.

Allowed status labels:

- `status:needs-triage`
- `status:ready`
- `status:blocked`

Rules:

- `status:needs-triage`: unclear scope, missing acceptance, unclear milestone fit, or owner decision needed.
- `status:ready`: clear goal, clear scope, clear acceptance, clear active-milestone fit.
- `status:blocked`: cannot proceed until a dependency, decision, credential, repository state, or external condition is resolved.

Remove stale status labels before adding a new one.

## Milestone Labels

Use the active milestone label.

Format:

```text
milestone:<active-milestone-id>
```

Rules:

- Always use the active milestone label when creating an issue.
- Do not use future milestone labels.
- Do not keep stale milestone labels.
- Use only one milestone label.
- If the active milestone label does not exist, report it.
- Do not create labels unless requested.

## GitHub Milestone

Use the active GitHub milestone when available.

Rules:

- New issues must target the active GitHub milestone.
- Existing issues must be checked against the active GitHub milestone during triage.
- If an issue targets a stale milestone, recommend correction.
- If no GitHub milestone exists yet, use the active milestone label and report the missing GitHub milestone.
- Do not create GitHub milestones unless requested.

## Issue Title

Format:

```text
[type] concise action
```

Examples:

```text
[docs] Add active milestone document
[task] Add minimal report output artifact
[chore] Add repository issue labels
[bug] Fix missing source metadata in report context
```

Rules:

- Use imperative wording.
- Keep title under 80 characters.
- Name the artifact or behavior.
- Avoid vague titles.

Avoid:

```text
Improve project
Make Halpha better
Future architecture ideas
Add everything needed
```

## Issue Body Template

Use this structure.

```markdown
## Goal

<One sentence. What user or product-use value this issue creates.>

## Context

<Why this is needed for the active milestone. Keep it factual.>

## Scope

- <Included work>
- <Included work>

## Out of Scope

- <Excluded work>
- <Excluded work>

## Acceptance

- [ ] <Observable condition>
- [ ] <Observable condition>
- [ ] <Validation or review condition>
```

Optional section:

```markdown
## Notes

<Links, constraints, or known gaps.>
```

Delete `Notes` if empty.

## Issue Body Rules

- Goal must be one sentence.
- Goal must state value, not only implementation.
- Context must tie to the active milestone.
- Context must not become a roadmap.
- Scope must be narrow.
- Out of Scope must block drift.
- Acceptance must be observable.
- Acceptance must not depend on future milestones.
- Notes are optional.

## Creation Flow

Before creating an issue:

1. Confirm explicit write intent.
2. Read the active milestone source.
3. Check active milestone fit.
4. Search for duplicate open issues.
5. Select one type label.
6. Select one area label if useful.
7. Select one status label.
8. Select the active milestone label.
9. Select the active GitHub milestone when available.
10. Draft title.
11. Draft body.
12. Create the issue.

If duplicate exists:

- Do not create a new issue.
- Report the duplicate candidate.
- Suggest updating the existing issue.

## Triage Flow

For an existing issue:

1. Read issue title and body.
2. Read comments if needed.
3. Check active milestone fit.
4. Check user value.
5. Check product-use value.
6. Check whether goal is clear.
7. Check whether scope is bounded.
8. Check whether acceptance is observable.
9. Check duplicate risk.
10. Recommend labels.
11. Recommend milestone correction if needed.
12. Update only when write intent is clear.

## Triage Outcomes

Use one outcome.

### Ready

Use when:

- Goal is clear.
- Value is clear.
- Scope is narrow.
- Acceptance is observable.
- Active milestone fit is clear.
- No blocking decision remains.

Apply:

- `status:ready`

### Needs triage

Use when:

- Goal is unclear.
- Value is unclear.
- Scope is too broad.
- Acceptance is missing.
- Active milestone fit is unclear.
- Duplicate risk needs review.

Apply:

- `status:needs-triage`

### Blocked

Use when:

- Required decision is missing.
- Required dependency is unavailable.
- Required repo structure does not exist yet.
- Required external account, token, service, or permission is unavailable.

Apply:

- `status:blocked`

## Label Update Rules

- Remove stale status label before adding a new status label.
- Keep at most one type label.
- Keep at most one status label.
- Keep at most one area label unless the issue truly crosses areas.
- Keep exactly one active milestone label when milestone labels are used.
- Remove stale milestone labels.
- Do not add labels outside the allowed set unless requested.
- If a needed label does not exist, report it.
- Do not create labels unless requested.

## Comment Rules

Use comments only when write intent is clear.

Triage comment format:

```markdown
Triage result: <ready | needs-triage | blocked>

Reason:
- <short reason>
- <short reason>

Suggested labels:
- `<label>`
- `<label>`

Milestone:
- `<active milestone>`

Next action:
- <one concrete action>
```

Keep comments short.

No long narratives.

## Duplicate Rules

Duplicate check is required before creating new issues.

Search by:

- title keywords;
- target artifact;
- target behavior;
- related area label;
- active milestone.

If likely duplicate:

- do not create a new issue;
- report the matching issue;
- suggest reuse or update.

## PR Link Rule

Issue should be small enough for one PR.

Do not require PR branch names.

Do not require PR templates yet.

When a PR closes the issue, prefer GitHub closing keywords in PR body:

```text
Closes #<issue-number>
```

## Review Rule

When reviewing an issue, answer:

- Does it serve the active milestone?
- Does it create user or product-use value?
- Is it actionable?
- Is it small enough?
- Are labels correct?
- Is milestone assignment correct?
- Is acceptance clear?
- Is anything blocked?

If unsure, state the gap.

Do not guess.

## Minimal Label Set

Initial labels:

```text
type:task
type:bug
type:docs
type:chore

area:repo
area:docs
area:core
area:data
area:report

status:needs-triage
status:ready
status:blocked

milestone:<active-milestone-id>
```

Do not expand this set early.
