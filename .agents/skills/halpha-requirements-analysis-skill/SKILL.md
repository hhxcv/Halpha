---
name: halpha-requirements-analysis-skill
description: Halpha skill for analyzing requirements before implementation. Use for requirement decomposition, milestone fit, scope boundaries, pipeline position, acceptance criteria, sequencing, and fixture or mock risk checks. Do not use for code implementation, PR writing, PR review, issue comments, or GitHub metadata mutation.
---

# Halpha Requirements Analysis Skill

Telegraph style. Requirements only.

## Triggers

Use when the task involves:

* identifying requirements;
* decomposing requirements;
* reviewing requirement changes;
* sequencing work for the active milestone;
* checking requirement scope, value, or acceptance;
* turning a product idea into implementation-ready scope;

Out of scope:

* GitHub issue metadata mutation;
* issue comments;
* PR review;
* code implementation;

## Hard Rules

* Ensure the end-to-end workflow remains complete, with clear upstream and downstream handoffs, and executable at every stage.
* Build the process skeleton before deep implementation details.
* Fit every requirement to the active milestone and current stage goal.
* Optimize for user value and deliverability, not architecture display.
* Prefer the smallest useful end-to-end slice.
* Do not create speculative frameworks, future-phase placeholders, or broad rewrites.
* Do not add heavy performance, security, reliability, or extensibility work unless current acceptance requires it.
* Do not invent commands, modules, files, APIs, sources, or behavior.
* Every requirement needs observable acceptance.
* Keep implementation scope small enough for one focused issue or PR.
* Production paths must use real data, real artifacts, and real flow.

## Fixture and Mock Rules

* Fixtures, mocks, fake data, and fake runners are allowed only in tests.
* Do not use fake data, fake flow, or temporary mocks as production behavior.
* If a temporary bridge is unavoidable, mark it explicitly and create a linked replacement requirement.
* Do not call a requirement complete while the visible product path depends on untracked fake behavior.
* Test fixtures must not hide missing production acceptance.

## Requirement Fit

A valid requirement answers:

* What user or product-use value does this create?
* Why is it needed in the active milestone?
* Where does it sit in the pipeline?
* What upstream input does it need?
* What downstream step consumes its output?
* What observable result proves completion?

Reject, split, or defer requirements that are:

* isolated implementation preferences with no flow role;
* broad architecture cleanup;
* future milestone placeholders;
* module-first work that leaves the pipeline disconnected;
* fake-data paths without a replacement requirement;
* too large for one focused issue or PR.

## Analysis Flow

1. Identify user value and active-stage fit.
2. Place the requirement in the pipeline.
3. Identify upstream input, output artifact, and downstream consumer.
4. Reduce scope to the smallest useful end-to-end slice.
5. Define out-of-scope boundaries.
6. Define observable acceptance.
7. Check fixture, mock, fake-flow, and temporary-bridge risks.
8. Return a requirement, split, defer, or rejection decision.

## Sequencing

Within a stage:

* connect the flow first;
* improve each step second;
* harden only proven weak points third.

## Requirement Output

```markdown
## Requirement

<One sentence. User or product-use value.>

## Pipeline Position

Upstream: <input or artifact>
Step: <pipeline step>
Downstream: <consumer or artifact>

## Scope

- <included work>
- <included work>

## Out of Scope

- <excluded work>
- <excluded work>

## Acceptance

- [ ] <observable result>
- [ ] <command or check>
- [ ] <artifact or user-visible behavior>

## Notes

<Only if needed. Include fixture/mock replacement requirement if relevant.>
```

Delete `Notes` when empty.
