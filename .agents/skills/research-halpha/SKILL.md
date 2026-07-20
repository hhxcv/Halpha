---
name: research-halpha
description: Select, run, and review Halpha strategy research for one valuable falsifiable question under research/**. Use when choosing a research direction from current project gaps, surveying current external research or mature methods, investigating a market mechanism, backtesting or comparing a strategy, resolving a difficult research problem, evaluating costs, robustness or economic evidence, reviewing earlier research, or preparing a selected result for product consideration. Keep research independent from product runtime and real-account trading, scale evidence to the claim, preserve failed attempts, and avoid duplicate or infrastructure-first work.
---

# Halpha Strategy Research

## Authority and Boundary

Use the current `HALPHA-ALP-001`, `HALPHA-ALP-003` and relevant L4 research facts for research semantics. Use `HALPHA-ALP-002` only when comparing research with the current code-strategy contract. Research materials own their exact question, data, code, attempts and result; they do not become product facts.

Work inside `research/**` unless the user explicitly requests a read-only review elsewhere. Do not read or persist product business data, load product secrets, change product configuration, call exchange-changing endpoints or start research with the product runtime. Public or user-provided research data remains subject to its source, license and cutoff.

Use `develop-halpha` only when a selected result is authorized to change product code or when the task also changes shared product tooling. Use `write-halpha-docs` only when stable ALP semantics or current L4 facts must change.

## Workflow

### 1. Ground the Direction and Survey Prior Art

Read the current L4 research facts, the project decision or evidence gap that motivates the work, and directly relevant Halpha design. Before new web research, scan `research/**` by mechanism, instrument or venue, question, data period and conclusion. If an earlier study answers or materially overlaps the question, reproduce, extend or reference it instead of duplicating it; do not create a global index or registry for this scan.

Do not choose a direction from general novelty, model preference or an isolated backtest idea.

Before selecting a new direction or starting an experiment for a user-defined question, search the public web for directly relevant current work and mature solutions. Prefer original papers, official venue or data-source rules and API documentation, official library documentation and source code, then credible independent replications. Use secondary summaries only to find primary material. If online access is unavailable, state that prior-art coverage is incomplete and do not present the selection as well grounded.

Record each material source, publication or access date, problem addressed, main assumptions, applicability to Halpha and the remaining gap. If existing work already answers the question or a mature tool implements the needed method, verify, reproduce, adapt or compare it instead of rebuilding it.

### 2. Select and Fix One Question

When the user has not fixed the question, form a small candidate set from current project gaps and the prior-art survey. Evaluate concrete decision or information value, the unresolved gap, a falsifier, a meaningful baseline, enough obtainable data to begin, fit with personal maintenance, any capital and validation-cycle limits explicitly supplied by the user, eventual operating complexity, and proportionate research cost. By default reject directions that require scale capital, cross-venue inventory or a long validation cycle unless they directly inform the current decision. Keep any personal capital scale the user has not supplied unknown; do not turn it into a Halpha capability or guarantee.

Select only one active question and preserve the candidates, duplication check and selection rationale in its research note.

State:

- the evaluated object or mechanism;
- the decision this result may inform;
- one falsifiable question and the result that would count against it;
- the comparison baseline;
- the intended claim strength: exploration, comparative evidence or product consideration;
- the current data boundary and known previously viewed periods.

If the user request already defines the question, do not create another approval step, but still complete the prior-art survey. If a missing choice would materially change the result, keep only that choice unresolved; do not replace it with a generic research platform.

### 3. Inspect the Actual Data

Verify the source, instrument and contract identity, timezone, interval meaning, coverage, cutoff, gaps, duplicates and revisions that matter to the question. Separate event time from acquisition time when later information or corrections could leak.

Record every interval already inspected or used for tuning. Previously viewed data can support exploration or comparison but cannot be presented later as untouched confirmation evidence.

### 4. Build the Smallest Reproducible Study

Prefer one question folder containing only what future reruns need:

```text
research/<question>/
  README.md or study.md
  study.py or notebook.ipynb
  results.json, csv or md
  attempts.md
```

Reuse mature libraries already justified by the study. Add a dependency only when the exact experiment needs it and record how to reproduce the environment. Do not create a research database, service, scheduler, generic CLI suite, persistent worker, task registry, universal schema, custom sandbox or optimization platform without a demonstrated repeated bottleneck and a current consumer.

Keep generated bulk data out of Git when appropriate, but record its source, immutable identity or retrieval rule and expected location.

Before first revealing outcomes from an interval intended as untouched evaluation, save a lightweight checkpoint in the existing study materials. Record the fixed question, search scope, development or selection gate, input identity, code or method identity, allowed fixes, and the rule for opening the interval. Use a short note, snapshot or hash as appropriate; do not require a fixed manifest, schema or new tracking system.

### 5. Run and Challenge the Study

Include only assumptions applicable to the decision, such as fees, funding, spread, slippage, latency, liquidity, capacity, position sizing and execution timing. Compare against a meaningful simple baseline and the strongest plausible alternative explanation.

Use the current product strategy as a comparison only when an exact replay or a bounded, explicitly labeled proxy is both fair and decision-relevant. Do not build a research-side second product implementation merely to force the comparison. If a comparable replay is unavailable or disproportionate, state that comparison as unknown or not run.

Preserve all material attempts, parameter searches, failures and condition changes. Never report only the best run. Mark exploratory tuning and later evaluation separately, and prevent overlap or future information from silently crossing the boundary.

If the fixed development gate fails, stop by default and preserve the untouched interval. Open it to confirm rejection only when that additional evidence has explicit decision value, and then record it as exposed. Record any outcome-revealing chart, summary or manual inspection; integrity-only access may be distinguished only when it cannot reveal performance and the reason is stated.

When a nontrivial implementation or interpretation problem could affect the study, search current original research, official documentation, source code and documented issues before inventing a workaround. Check versions, assumptions and context; record the useful lead, what was tried and why it applies or does not apply. If no reliable answer is available, preserve the unknown or weaken the claim rather than guessing past it.

Read [Research Method and Evidence](references/research-method-and-evidence.md) in full when the result may influence product strategy selection or capital use, when many candidates or parameters are searched, or when holdout, walk-forward, robustness or previously viewed data affect the claim.

### 6. Reproduce and Report Honestly

Rerun the final command from recorded inputs where proportionate. Check that reported metrics, tables and plots derive from the saved result rather than manual transcription. Verify that small inputs, commands, results and any recorded hashes remain available. For external bulk data, verify and record its source identity or retrieval rule, expected location and whether a local cache is durable or reacquirable. State unmodeled items and any environment limitation.

Conclude with exactly one bounded result:

- `SUPPORTS_WITHIN_SCOPE`
- `DOES_NOT_SUPPORT`
- `INSUFFICIENT_EVIDENCE`
- `CANNOT_DETERMINE`

Explain the scope, strongest support, strongest counterevidence, costs, sensitivity, known leakage or exposure, and what new evidence could change the conclusion. A profitable backtest, model score or single live outcome never proves future Alpha.

### 7. Hand Off Without Product Effect

Research completion does not update the product strategy, trading plan, funds, credentials, build identity or real-account trading state. Only a project-owner selection can start a product change. When selected and authorized, reimplement or review the strategy in the product path, then use `develop-halpha` for affected product tests and runtime validation; never dynamically load research code as a product fallback.

## Delivery

Report the question, data boundary, exact artifacts and command, actual attempts, conclusion, counterevidence, reproducibility result and remaining unknowns. Distinguish newly created evidence from earlier files and say what was not run. Report whether the research artifacts are Git-tracked and how external caches are retained; describe untracked artifacts only as retained in the current worktree, not as durable Git history.

Do not claim quality from experiment count, framework size or procedural formality.
