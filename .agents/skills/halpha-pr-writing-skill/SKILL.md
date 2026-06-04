---
name: halpha-pr-writing-skill
description: Halpha skill for drafting and checking GitHub pull request titles and bodies. Use for PR title/body writing, linked issue closure text, acceptance coverage, validation summaries, risk notes, and submit-readiness checks. Do not use for PR comments, PR review, issue metadata mutation, code implementation, or direct GitHub submission without explicit write intent.
---

# Halpha PR Writing Skill

Telegraph style. PR drafting only.

Default skill for Halpha pull request title, body, and submit-readiness work.

Use for:

- drafting a PR title;
- drafting a PR body;
- enforcing the Halpha PR template;
- checking whether a PR body is ready to submit;
- mapping a PR to a linked issue and issue acceptance;
- summarizing validation evidence;
- disclosing risks, gaps, and follow-ups.

Do not use for:

- GitHub issue creation, labels, milestone changes, or state changes;
- issue comments;
- PR comments;
- PR review comments;
- code review;
- code implementation;
- merging, closing, reopening, or submitting PRs without explicit write intent.

If the user asks for PR review, PR comments, or implementation, stop and report out of scope.

## Triggers

Use when the task involves:

- writing a PR title;
- writing a PR description;
- converting a completed implementation into a PR body;
- checking PR body completeness;
- preparing a ready-to-submit PR draft;
- linking a PR to an issue;
- deciding whether `Closes #<issue-number>` is appropriate;
- summarizing changed files, behavior, validation, risks, and follow-ups for a PR.

Out of scope:

- deciding issue labels or milestone fields;
- creating or editing GitHub issues;
- reviewing code quality;
- leaving comments on a PR;
- applying code changes;
- pushing branches;
- opening a public PR unless explicit write intent is present.

## Hard Rules

- Draft only unless the user explicitly requests a public GitHub write.
- Never submit, open, edit, merge, close, or reopen a PR without explicit write intent.
- Inspect available evidence before drafting: linked issue, requirement, diff, changed files, test output, and relevant project rules.
- Do not invent issue numbers, branch names, files, modules, commands, test results, APIs, behavior, labels, reviewers, or milestones.
- Do not claim validation passed unless the command output or user-provided evidence proves it.
- If validation was not run or evidence is missing, say so plainly in the PR body.
- Keep each PR narrow enough to review as one focused change.
- Tie the PR to user or product-use value, not only implementation detail.
- Preserve Halpha's local-first, inspectable-artifact, source-aware report pipeline constraints.
- Do not introduce speculative architecture, future-phase placeholders, or broad framework work in the PR narrative.
- Production behavior must not depend on fake data, hidden mocks, or untracked temporary bridges.
- Tests, fixtures, and fake runners may be mentioned only as test behavior.
- PR body must be reviewable without forcing the reviewer to reconstruct intent from the full diff.
- Gaps, known risks, skipped checks, and follow-ups must be visible.
- Remove empty optional sections from the final PR body.

## Evidence Rules

Use the strongest available evidence in this order:

1. User-provided PR intent or issue number.
2. Linked issue title, body, and acceptance criteria.
3. Local `git status --short`, `git diff --stat`, and relevant `git diff` content when available.
4. Test or command output when available.
5. Relevant Halpha project rules, requirements, and milestone constraints.

Rules:

- If no diff was inspected, label the output as a proposed PR draft.
- If no linked issue was provided or found, use `No linked issue provided.` and add a pre-submit gap.
- If an issue is intended to be closed, use a GitHub closing keyword in the PR body.
- If the PR only relates to an issue and should not close it, use `Related to #<issue-number>` instead of `Closes #<issue-number>`.
- If acceptance criteria exist, map each relevant criterion to implementation or validation evidence.
- If evidence is partial, keep the uncertain item unchecked or mark it as a gap.

## PR Title

Format:

```text
[type] Imperative short summary
```

Allowed type prefixes:

- `[task]`
- `[bug]`
- `[docs]`
- `[chore]`

Rules:

- Use the same type vocabulary as Halpha issue metadata.
- Use an imperative verb when natural: `Add`, `Fix`, `Document`, `Preserve`, `Validate`, `Generate`.
- Name the changed artifact, command, or behavior when useful.
- Keep the title short but specific.
- Do not mention implementation mechanics unless they are the user-visible or reviewer-relevant change.
- Do not use vague titles.

Examples:

```text
[task] Add run manifest creation
[bug] Preserve source names in report context
[docs] Document local run artifacts
[chore] Add smoke test fixtures
```

Avoid:

```text
Improve pipeline
Fix stuff
Update files
Big refactor
Prepare future architecture
```

## PR Body Template

Use this exact section order for normal PRs:

```markdown
## Summary

- <Primary user or product-use result.>
- <Secondary implementation or artifact change, if needed.>

## Linked Issue

Closes #<issue-number>

## Scope

- <Included change.>
- <Included change.>

## Acceptance Coverage

- [x] <Acceptance condition> — <evidence from diff, artifact, or validation.>
- [ ] <Acceptance condition> — <remaining gap or missing evidence.>

## Validation

- [x] `<command>` — <observed result.>
- [ ] `<command>` — not run; <reason.>

## Risks / Follow-ups

- <Known risk, limitation, follow-up, or `None`.>
```

Delete any optional second bullet if empty. Do not delete required sections unless the user explicitly asks for a shorter body.

## Linked Issue Section

Preferred when the PR closes one issue:

```markdown
## Linked Issue

Closes #<issue-number>
```

Use only when the PR satisfies the issue acceptance and should close the issue.

Use this when related but not closing:

```markdown
## Linked Issue

Related to #<issue-number>
```

Use this when no issue is known:

```markdown
## Linked Issue

No linked issue provided.
```

If no issue is known, also add a pre-submit gap outside the PR body.

## Summary Section

Rules:

- 1-3 bullets.
- First bullet states product or reviewer value.
- Later bullets may mention main artifacts or behavior.
- Avoid restating every changed file.
- Avoid claiming broader completion than the diff supports.

Good:

```markdown
## Summary

- Adds the minimal CLI path needed to create a locally inspectable run manifest.
- Wires config loading into the first pipeline skeleton without introducing data-source frameworks.
```

Bad:

```markdown
## Summary

- Changed code.
- Improved architecture.
- Finished Halpha.
```

## Scope Section

Rules:

- List what is included, not every line changed.
- Keep scope aligned to one focused PR.
- Mention important files or artifacts when useful.
- Do not hide follow-up work inside broad bullets.

Example:

```markdown
## Scope

- Adds the package entry point and CLI command parsing.
- Reads `config.example.yaml` and creates `runs/<run_id>/run_manifest.json`.
- Adds a smoke test for the initial pipeline skeleton.
```

## Acceptance Coverage Section

Rules:

- Mirror linked issue acceptance when available.
- Use `[x]` only when evidence proves the item is satisfied.
- Use `[ ]` for missing, partial, or unverified evidence.
- Each item must include evidence after an em dash.
- Do not create fake acceptance criteria.

Example:

```markdown
## Acceptance Coverage

- [x] Main command exits successfully — verified by `python -m halpha run --config config.example.yaml`.
- [x] Run manifest is written — verified at `runs/<run_id>/run_manifest.json`.
- [x] Tests pass — verified by `python -m pytest`.
```

If no issue acceptance is available:

```markdown
## Acceptance Coverage

- [ ] No linked issue acceptance provided — reviewer should confirm expected completion criteria before merge.
```

## Validation Section

Rules:

- Include exact commands and observed results.
- Use `[x]` only for commands or checks that were actually run and passed.
- Use `[ ]` for commands not run, failed, or not evidenced.
- Do not summarize failed validation as success.
- If validation produced artifacts, name the artifact path.
- If validation is not applicable, state why.

Examples:

```markdown
## Validation

- [x] `python -m pytest` — passed.
- [x] `python -m halpha run --config config.example.yaml` — created `runs/<run_id>/run_manifest.json`.
```

```markdown
## Validation

- [ ] `python -m pytest` — not run; no test output was provided.
```

## Risks / Follow-ups Section

Rules:

- Use `None.` only when no meaningful risk or follow-up is known.
- Mention skipped checks, partial evidence, temporary bridges, fixture-only behavior, and reviewer decisions.
- Do not bury known gaps in positive language.
- Do not create future milestone work unless already tracked or requested.

Examples:

```markdown
## Risks / Follow-ups

- Codex CLI execution is still mocked in tests; production execution remains covered by a later tracked task.
```

```markdown
## Risks / Follow-ups

- None.
```

## Optional Sections

Add only when relevant.

### Screenshots / Artifacts

Use for UI changes, report output samples, generated files, or local artifacts that reviewers should inspect.

```markdown
## Screenshots / Artifacts

- `<path>` — <what reviewer should inspect.>
```

### Breaking Changes

Use only when behavior, commands, config, or artifact contracts change incompatibly.

```markdown
## Breaking Changes

- <Breaking change and migration note.>
```

### Security / Secrets

Use when credentials, tokens, auth files, or sensitive local paths could be involved.

```markdown
## Security / Secrets

- <Confirmation that no secrets are printed, persisted, or added to the diff.>
```

## Output Format

When drafting a PR, return:

```markdown
## PR Title

[type] Imperative short summary

## PR Body

<complete PR body>

## Pre-submit Gaps

- <Gap, missing evidence, or `None`.>
```

When checking an existing PR body, return:

```markdown
## PR Readiness

<Ready / Needs changes / Blocked>

## Findings

- <Finding and required correction.>

## Proposed PR Body

<corrected body, if useful>
```

## Drafting Flow

1. Identify whether the user wants a draft, check, or public write.
2. Confirm public write intent before any GitHub mutation.
3. Identify linked issue or state that no issue was provided.
4. Inspect available diff, files changed, tests, and issue acceptance.
5. Select the PR type prefix.
6. Draft the title.
7. Fill the PR body template in the required order.
8. Map acceptance criteria to evidence.
9. Record validation exactly as evidenced.
10. Add risks, skipped checks, and follow-ups.
11. Return pre-submit gaps separately from the PR body.

## Readiness Rules

A PR draft is `Ready` only when:

- title matches the required format;
- PR body uses the required sections in order;
- linked issue is present or the absence is explicitly accepted;
- closing keyword is correct for the intended issue relationship;
- scope is narrow and reviewable;
- summary states product or reviewer value;
- acceptance coverage maps to evidence;
- validation commands and results are accurate;
- risks, skipped checks, and follow-ups are disclosed;
- no invented files, commands, results, or behavior appear;
- no public mutation is needed or mutation intent is explicit.

Use `Needs changes` when the draft can be fixed locally.

Use `Blocked` when required evidence, permission, issue context, repository state, or owner decision is missing.

## Mutation Safety

Public PR mutations include:

- opening a PR;
- editing PR title or body;
- changing PR base or head branch;
- adding reviewers, assignees, labels, projects, or milestones;
- converting draft/ready state;
- closing, reopening, merging, or marking ready for review.

Rules:

- Drafting and readiness checks may proceed without write intent.
- Public mutations require explicit write intent.
- If write intent is unclear, provide the proposed PR title and body instead of applying it.
- User phrases such as `先写`, `draft`, `prepare`, `检查`, or `不要提交` mean no public write.
- No surprise public writes.
