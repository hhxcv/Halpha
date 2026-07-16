# Feedback, Async State, and Risk Controls

## Every Action Has a Visible Lifecycle

Specify feedback at four distinct layers:

1. **Local response:** within perceptual immediacy, show pressed state, focus, field validation, or button-local activity and prevent accidental duplicate submission.
2. **Submission acknowledgement:** show that the message, event, command, or task reached the responsible boundary; include stable identity and submission time when available.
3. **Ongoing work:** show queued, processing, waiting for an external system, retrying, reconciling, or blocked state using only terms supported by the authoritative model. Display determinate progress when truthful; otherwise show active indeterminate progress plus the current phase.
4. **Authoritative result:** show effective, rejected, failed, cancelled, abandoned, timed out, stale, or unknown as supported by accepted semantics, with evidence cutoff and next action.

Submission acknowledgement is not business effect. `PROCESSING`, a spinner, an HTTP response, or a toast must never masquerade as order placement, cancellation, exit, protection, or capital release.

## Feedback Placement

Use the least intrusive surface that preserves the consequence:

- button-local feedback for immediate submission;
- inline field messages for validation;
- a nonblocking toast or status message for transient acknowledgement;
- persistent row state, activity item, banner, or Task for ongoing work, failure, unknown, or required follow-up;
- a dialog only when the user must decide before proceeding;
- a detail drawer or route for evidence and diagnosis.

Success messages may disappear after the durable state is visible. Failure, rejection, unknown, and required follow-up must persist until resolved, superseded, or explicitly acknowledged according to accepted semantics.

## No Silent Failure

For every failed or abnormal path, display:

- what failed in user language;
- the affected object, scope, and environment;
- whether the requested effect occurred, did not occur, or is unknown;
- a stable reason or correlation identity when available;
- fact cutoff and last confirmed state;
- safe retry conditions, alternative action, or external venue handoff;
- whether the system will continue retrying or has stopped.

Do not expose secrets, raw stack traces, or provider errors as the primary message. Preserve technical detail in a protected diagnostic layer.

## Long-Running Work

For work that may outlive the current view:

- give it a stable visible identity;
- keep status available after navigation or refresh;
- show current phase and latest meaningful change;
- show determinate progress only when backed by real units;
- allow cancellation only when semantically safe;
- explain consequences before cancelling work that has partial effects;
- notify completion or failure in context and through the accepted Task/notification path when required.

Avoid indefinite unlabeled spinners. If progress stalls, transition to a visible waiting, delayed, failed, or unknown state rather than silently continuing animation.

## Risk-Action Inventory

Inventory proposed or existing actions by consequence, not by button color. Treat the following as review triggers, not as proof that Halpha owns or exposes the action:

- deletion or irreversible evidence loss;
- configuration changes that affect runtime, data, permissions, notifications, or recovery;
- increasing capital, notional, loss, or machine authority;
- activating or resuming risk;
- modifying or removing protection;
- manual trade behavior with material exposure consequence;
- stopping a strategy, executor, application, or protective process;
- exiting, taking over, releasing capital, or changing recovery authority.

Add any action with comparable irreversibility, uncertainty, privilege, exposure, or blast radius even when it is not listed above. For every item, record the accepted semantic owner, command, preview, current phase, and permitted carrier. If any of those are missing, mark the affected interaction `DESIGN_GAP`; do not create a generic settings, deletion, system-control, or trading command from this list.

## Effective Second Gate

Every in-scope risk action must either map to the effective second gate required by accepted design or remain blocked as a design gap. A current consequence preview followed by an explicit command in a confirmation dialog is the default presentation. An equivalent guard may be used only when the accepted contract permits it and it is at least as resistant to accidental activation, such as a typed confirmation phrase, press-and-hold, reauthentication, or a separate preview-and-commit step.

The gate must show:

- exact action name, never generic “确定” as the primary label;
- target object, environment, account, instrument, and scope;
- current facts and cutoff;
- immediate and downstream consequences;
- what the action does not do;
- uncertainty, partial-effect, and external-system behavior;
- reversibility and recovery path;
- preview identity, digest, expected version, and expiry when required by accepted design;
- a safe cancel path and keyboard focus behavior.

Use stronger friction for rare, irreversible, protection-reducing, or broad-scope actions. Do not repeat the same warning so often that the owner learns to dismiss it automatically.

Emergency stop, exit, and takeover are high consequence but time sensitive. Apply the accepted current preview and explicit command while keeping the first legitimate request reachable. Do not add arbitrary approvals, long wizards, generic rate limits, or dependencies on an unavailable full interface. A visual warning does not authorize a command that accepted design has not defined.

## Control-State Requirements

For every consequential control, define:

- enabled conditions;
- disabled reason shown adjacent or on focus/hover;
- in-flight duplicate prevention;
- stale-preview invalidation;
- version-conflict behavior;
- navigation-away behavior;
- retry idempotency;
- result reconciliation;
- accessibility name and focus return after dialog close.

Color must never be the only risk or result channel. Pair color with text, icon, position, and state language.
