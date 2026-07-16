# Halpha Core Business Workflows and User Journeys

**Document ID:** HALPHA-FLOW-001  
**Version:** v1.7.0  
**Document Status:** ACCEPTED  
**Level:** L1-C  
**Language Edition:** en-US  
**Joint Normative Set ID:** HALPHA-FLOW-001@v1.7.0+20260715T190415+0800  
**Paired Text:** HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md  
**Joint Set Registry:** HALPHA-FLOW-001-core-workflows-and-user-journeys.bundle.yaml  
**Effective Time:** 2026-07-15T19:04:15+08:00  
**Parent Documents:** HALPHA-CON-001 v2.9.0; HALPHA-DOC-001 v1.9.0; HALPHA-VIS-001 v1.4.0  
**This Document Governs:** how the user repeatedly uses Halpha for trading research, judgment, planning, real actions, inspection, intervention, recovery, and learning; the six horizontal business responsibilities and their main handoffs  
**This Document Does Not Govern:** specific pages, fields, algorithms, databases, venue protocols, numerical limits, current construction scope, implementation state, or equal deepening across the responsibility map

---

# 0. Workflow Positioning and Core Commitments 【FLOW-SUM-001】

## 0.1 Rationale for the Workflow 【FLOW-SUM-001-RAT】

Halpha's day-to-day path helps the user form judgments, compare alternatives, make plans, act correctly, understand results, and improve continuously. It does not make the user complete a separate control or governance process first.

The user may observe cautiously, intervene frequently, and stop the system at any time. Even after strong long-term operating results, the workflow must not depend on unattended operation or take away the user's ability to stop and take over externally.

## 0.2 Core Workflow Requirements 【FLOW-SUM-001-REQ】

The user decides outside Halpha which accounts and how much capital may be made available to it. FLOW governs only how the user configures and uses funds-use caps and scope, authorization, plans, stopping, and recovery inside Halpha; it does not turn the user's total-capital decision into a product workflow. Real-action paths apply the three classes of control requirements in CON-CMP-003 separately. Supporting mechanisms must not be more complex than the core trading tasks.

The workflow must ensure that:

- on entry, the user can first see what happened, whether anything is worth doing, and whether Halpha is usable;
- frequent tasks take few steps, with specialist detail available on demand;
- a real action normally originates from a fixed, enabled, complete Trading Plan; an explicit user decision, fixed in advance, to protect or reduce an existing exposure, or an explicit user instruction to cancel, protect, transfer, or reduce risk that can be shown not to increase or transform risk, may proceed without a Trading Plan, but must fix its subject, scope, and reason and enter the same funds-use caps-and-scope, Halpha real-capital operating authority, execution, and reconciliation path;
- an action that requires post-trigger human judgment proceeds only while the user is online and the complete manual-authorization path is feasible within the applicable time window; a machine-authorization path requires explicit, bounded authorization before the trigger;
- a venue or account change initiated by Halpha passes only through the single isolated external-write boundary; an action the user performs independently through an official venue interface enters as external activity;
- when facts are unknown, the path is infeasible, or permission is insufficient, the result is waiting, no trade, or stopping rather than an assumed success; only a contraction action explicitly directed by the user and shown not to increase or transform risk may continue; and
- stopping and external human takeover remain reachable.

---

# 1. Path Continuity Under Limited Attention 【FLOW-TIM-001】

FLOW defines only the product-level path: the user can quickly handle current state and time-bound decisions, and can also continue through research, planning, and review. On failure, the path first limits impact, reconciles external state, and enables human takeover. Lower-level design defines exact task ordering and interaction timing; L4 records actual performance.

When nothing is wrong, the user can enter the most valuable research, planning, or review task directly. An anomaly, a time-bound decision, or an action that may change a venue or account must be directly reachable, without turning the normal product entry into a technical status page.

## 1.1 Interruption and Recovery

Candidates, research, and plan drafts may be saved and resumed. Resumption must highlight intervening changes, expired inputs, and decisions that must be made again. A real action that has occurred or may have occurred must never be replayed by resuming a draft; Halpha must first read and reconcile external state.

---

# 2. Recurring Usage Scenarios 【FLOW-MAP-001】

| Scenario | Main path | Permitted ending |
|---|---|---|
| Quick status check | Accounts and positions → active plans and unresolved actions → Halpha availability → high-value tasks | Exit with nothing to do, or enter one clear task |
| Candidate capture | Save source and time → add necessary context → deduplicate and screen | Wait, end, enter research, or enter planning |
| Alpha research | Hypothesis and mechanism → data and benchmark → counterevidence → conclusion and applicability | Reject, continue observing, or produce a basis for planning |
| Plan creation | Basis for judgment → entry, exit, adjustment, and protection → quantity, cost, timing, and failure handling | Keep a draft, fix and enable, or abandon |
| Manually authorized action | Current preview → current user confirmation → funds-use caps-and-scope and Halpha real-capital operating-authority check → real action → reconciliation | Wait, reject, no trade, partial or complete result, or unresolved result |
| Fixed-strategy operation | Strategy input → complete plan → condition evaluation → current facts and authorization review → action and reconciliation | Take no action, pause, narrow scope, continue, or stop |
| Protection or risk reduction | Fixed protection/risk-reduction decision or explicit user instruction → current facts → funds-use caps-and-scope and Halpha real-capital operating-authority check → action and reconciliation | Complete, reject, remain unknown, hand over externally, or remain stopped |
| Return from an external manual action | Read venue facts → mark the external source → associate with an existing plan or later decision | Facts are available to later judgments |
| Short review | Original decision → actual outcome and cost → differences in judgment, plan, data, execution, and interaction | Make no change, or create an actionable improvement |
| Failure and recovery | Stop new real actions in the affected scope → reconcile externally → repair or roll back → verify recovery conditions | Remain stopped, or have the user explicitly restore the applicable Halpha real-capital operating authority |
| Disable and exit | Stop new real actions → expose residual responsibilities → revoke write permission and credentials → export necessary material | External accounts remain independently controllable |

---

# 3. Boundary Between External Tools and Halpha 【FLOW-TOOL-001】

## 3.1 Rationale for External-Tool Responsibilities 【FLOW-TOOL-001-RAT】

Mature external tools should do what they already do well: venues provide official account operations, specialist charting tools provide deep visual analysis, news and data sources provide source material, research environments support exploration, and general-purpose AI provides only non-authoritative organization and generation.

## 3.2 Halpha-Owned Continuity and Handoff Requirements 【FLOW-TOOL-001-REQ】

Halpha must preserve research and planning context, the strategy or plan currently in use, the user's configured funds-use caps and scope and Halpha real-capital operating authority, the real actions initiated by Halpha and any unresolved responsibilities, the necessary reconciled facts, and learning derived from plans, actions, and outcomes.

Halpha does not duplicate a sufficient external capability. A handoff must let the user see the subject, time, applicable plan, action boundaries, and return path. A returned result enters reconciliation as an external fact; clicking “done” does not make it an account fact.

---

# 4. User Interaction and Control 【FLOW-UX-001】

## 4.1 Six Primary User Task Domains

### Definition of the Six User Task Domains 【FLOW-UX-001-DEF】

These are enduring task domains, not names for pages, menus, or software modules.

| User task domain | Question the user must answer | Typical tasks |
|---|---|---|
| Market observation and live intelligence | What happened in markets, events, and watched subjects | Observe prices and events, find leads, inspect plan-related signals |
| Strategy research and validation | Why might a view or strategy be valid | Form hypotheses, explore data, seek counterevidence, backtest, and compare versions |
| Trading Plans and rehearsal | If acting, how should entry, exit, protection, adjustment, and stopping work | Create, compare, preview, simulate, fix, and enable plans |
| Trade execution and position management | What action does a current plan, order, or position require | Confirm, execute, protect, adjust, cancel, exit, and handle anomalies |
| Accounts and trading records | What objectively happened, and can the facts be reconciled | Query balances, orders, fills, positions, fees, and external activity |
| Review, analysis, and learning | How good were the original judgment and plan, and what should change next | Compare plan with reality, analyze differences, and create improvements |

### Requirements for Using the Task Domains 【FLOW-UX-001-REQ】

L3 may combine several task domains in one interface or give a frequent task its own entry, but it must preserve task-context continuity. “Accounts and trading records” provides facts; “review, analysis, and learning” provides explanations with evidence boundaries. They must not collapse into a profit-and-loss-only report.

“Trading Plans and rehearsal” turns research, a user judgment, or a position-management need into a plan that can be previewed, simulated, fixed, and enabled. “Trade execution and position management” takes over actions and responsibilities that have triggered or are underway. An order button does not replace planning.

## 4.2 Current State and Pending Work Form a Cross-Domain Entry

On entering Halpha, the user must be able to see current orders and positions, active plans, time-bound decisions, anomalies, and material changes, and then move directly to the relevant planning, execution, facts, research, or review task. L1 does not prescribe the page name or navigation form. With no pending work, the user may exit or enter any high-value task directly.

## 4.3 Real Usage Allows Direct Entry and Return Flows

A complete discovery–action–learning loop can be expressed as:

~~~text
Market observation and live intelligence
        ↓ (research when needed; a sufficiently supported user judgment may start directly)
Strategy research and validation ─────────┐
        ↓                                 │
Trading Plans and rehearsal               │
        ↓                                 │
Trade execution and position management   │
        ↓                                 │
Accounts and trading records              │
        ↓                                 │
Review, analysis, and learning ────────────┘ return to intelligence, research, or a new plan
~~~

This is not a mandatory funnel. An existing position, a protection need, or an order anomaly may enter execution and position management directly. The user may query facts directly. With no qualified opportunity, the path ends by waiting, holding cash, or making no trade. A return flow is needed only when there is an actionable issue.

## 4.4 Typical Task Paths

| User intent | Reasonable path | Normal ending |
|---|---|---|
| Check quickly whether anything needs attention | Current state and pending work → relevant plan, position, order, intelligence, or anomaly | Handle one item, or exit with nothing to do |
| Turn a view into a trade | User judgment or intelligence → optional research → plan → rehearsal or simulation → decision whether to enter a real-funds environment | No trade, keep observing, simulate, or execute for real |
| Respond to an active plan | Notification or condition trigger → current facts and plan branch → confirm, wait, reject, or act under an authorized rule | Record the decision; track and reconcile any action |
| Manage an existing order or position | Order or position → basis, current facts, and unresolved responsibilities → protect, adjust, cancel, or exit | Close the responsibility, or hand over to external manual action |
| Research and validate a strategy | Hypothesis or strategy → exploration, counterevidence, and comparison → forward observation or simulation | Reject, continue research, observe, or create a basis for planning |
| Query and review | Fact timeline → reconciliation state → comparison with the original decision | Exit, or create new research, a new plan, or an improvement |

Search, saved views, notifications, deep links, or object relationships may start these paths. L1 requires continuity and retrievable outcomes; it does not fix the number of pages.

## 4.5 Commands Must Be Unambiguous

Confirming a current proposed action, enabling or changing a plan, enabling or disabling a fixed strategy, expanding or narrowing funds-use caps and scope, stopping new real actions, entering external human takeover, and restoring applicable Halpha real-capital operating authority must remain separate commands. Narrowing funds-use scope or lowering Halpha real-capital operating authority should be fast. Raising funds-use caps, expanding scope, or increasing Halpha real-capital operating authority must show the current configuration and consequences without adding multi-level approval. A per-action confirmation must not silently change enduring funds-use caps and scope or Halpha real-capital operating authority.

## 4.6 Information Hierarchy

The default view shows the current conclusion, key basis, major unknowns, next action, and whether Halpha is usable. Sources, history, models, execution attempts, and technical information expand on demand. Facts, estimates, AI suggestions, user decisions, and venue results must remain distinguishable.

---

# 5. Research or Trading Plan Candidates, Research, and Planning 【FLOW-TRADEPLAN-001】

## 5.1 Destinations for Research or Trading Plan Candidates

A candidate preserves enough context to understand its source, time, subject, initial judgment, and current relevance. Under CTX rules, the user or Halpha decides to end it, wait, enter economic research, or form a Trading Plan directly when the basis is sufficient. Not every candidate requires formal research.

## 5.2 Research Entering Planning

When Halpha forms a strategy or research conclusion under ALP rules, it must express the mechanism, applicable scope, counterevidence, costs, liquidity boundaries, evidence limitations, and invalidation conditions. Research may improve judgment or provide a Trading Plan basis, but it cannot directly create an order.

## 5.3 Decisions Required Before a Real Action

A real action normally must reference a complete Trading Plan; TRADEPLAN owns plan completeness and version boundaries. Exceptions are limited to an explicit user decision, fixed in advance, to protect or reduce an existing exposure and an explicit user instruction to cancel, protect, transfer, or reduce risk that can be shown not to increase or transform risk. Before action, an exception must fix its subject, scope, reason, and permitted outcome, and must pass through the same funds-use caps-and-scope, Halpha real-capital operating authority, execution, and reconciliation path as a plan-based action.

A plan may consume a user decision, a research basis, or a necessary comparison among uses of funds. Before enablement, it must support preview, rehearsal, fixing, or an end without action. Incomplete content remains a draft. A material change creates a new version; the original decision cannot be filled in after a real action.

## 5.4 Compare Multiple Uses of Funds Only When Necessary

An ordinary single-purpose plan or a validation with one objective does not require comparison among multiple uses of funds. The POR boundary is entered only when multiple real uses compete for the same funds, or an existing position and a proposed action require comparison of shared exposure or rebalancing. After the user chooses, TRADEPLAN still forms the applicable plan.

---

# 6. Operating Modes, Trading Plan Enablement, Events, and Real Actions 【FLOW-RUN-001】

## 6.1 Trading-Record Environments and Halpha Real-Capital Operating Authority

Historical research and historical market replay support research and validation; an exchange simulator and a real-funds environment support trading paths. Accounts, actions, and results from different environments must remain distinguishable. Moving from simulation to real funds requires the user to select the real environment, applicable plan, funds-use caps and scope, and Halpha real-capital operating authority again. A simulated decision, authorization, or action identity must not migrate into a real decision, authorization, or fact. ARC and lower-level design define storage and adapter isolation.

## 6.2 Trading Plan Enablement and Observation

After a plan is enabled, Halpha may evaluate conditions, the completeness and timeliness of necessary facts, and external events. A satisfied condition creates only a current plan branch; it does not prove that a trade should occur. An action still depends on current facts and an applicable authorization path.

## 6.3 Two Authorization Paths and Their Business Uses

A real action has only two authorization paths: Manual authorization and Machine authorization. Real Validation, protection, and risk reduction are purposes or risk situations, not a third authorization path.

### Manual-Authorization Path

Manual authorization is a user decision about the current specific action or an explicitly controlled scope. When post-trigger human judgment is required, the action may continue only while the user is online, can understand and respond, and the complete path from notification through submission is feasible within the applicable time window. Otherwise the outcome is waiting, expiry, blocking, or no trade; it must not be converted automatically into Machine authorization.

### Machine-Authorization Path

The user must grant Machine authorization before the trigger and define its scope, duration, action range, and failure outcome. Halpha may act only within the authorization intersection under deterministic rules. If a key fact is unknown, timing is infeasible, a judgment must be borne by a person, or the authorization boundary is unclear, Halpha must stop the action and enter reconciliation, human takeover, or no trade.

### External Manual Actions and Engineering Validation

An action the user performs through an official venue interface is external activity. Halpha supplies the necessary handoff context, then reads and reconciles venue facts on return; it cannot relabel the external action as a Halpha action. Engineering or Real Validation may use either authorization path, but the validation purpose cannot raise ordinary funds-use caps, expand scope, or increase Halpha real-capital operating authority.

## 6.4 Unified Real-Action Chain

~~~text
Current branch of an enabled Trading Plan,
or a permitted explicit user decision, fixed in advance, to protect or reduce risk,
or an explicit user instruction to cancel, protect, transfer, or reduce risk that can be shown not to increase or transform risk
→ read current key facts and confirm that the Manual- or Machine-authorization path is usable
→ Halpha applies CAP rules to check funds-use caps and scope, Halpha real-capital operating authority, stop state, and applicable limits
→ before external writing, Halpha applies EXE rules to record the proposed action and establish one processing responsibility
→ the single isolated external-write boundary refreshes key facts, repeats the funds-use caps-and-scope and Halpha real-capital operating-authority check, and submits the venue action
→ partial results, timeouts, and unresolved results remain visible and are advanced under EXE rules
→ Halpha reconciles external facts under DAT rules and returns the outcome to the applicable plan, protection responsibility, or outcome-learning path
~~~

Every permitted source enters the same path for funds-use caps and scope, Halpha real-capital operating authority, execution, reconciliation, and stopping. The chain neither reserves funds for future actions nor creates an independent or final funds approval. A Manual-authorization path must confirm that the current action is supported by the user's current decision or by a still-valid decision for an explicitly controlled scope; a Machine-authorization path requires prior authorization that remains valid through submission. EXE owns detailed action identity, failure, and retry semantics.

## 6.5 Stopping and Human Intervention

The user can immediately stop new Halpha real actions globally or within an account or strategy scope. Stopping does not itself cancel an order, transfer funds, or close a position. A required real disposition must originate from a new permitted action source or be performed by the user through an official venue interface.

After human intervention, Halpha first reads external orders and positions, then identifies the applicable plan or protection responsibility; any decision for a later action still requires the normal decision and authorization path. Restart or recovery must not let an old proposed action, confirmation, or processing record produce another external action. If external facts remain unclear, the affected scope remains stopped.

---

# 7. Outcomes, Learning, and Changes to Funds-use Caps and Scope 【FLOW-LRN-001】

After a plan ends or responsibility for an important real action closes, a short review answers what was originally judged, what actually happened, what it cost, and which actionable differences arose from judgment, planning, data, execution, UX, or stability. OUT owns review and cross-record attribution semantics. A review conclusion cannot directly rewrite a strategy, plan, authorization, or funds-use caps and scope.

When the user asks to raise a funds-use cap or expand scope, Halpha should summarize the relevant quality of judgment, plan expression, fact reliability, execution correctness, UX control, and recovery behavior. Halpha must not expand scope automatically because of profits, workflow completion, or a model conclusion, and it does not decide how much total capital the user should add.

---

# 8. Onboarding, Real Validation, Failure, and Exit 【FLOW-REC-001】

## 8.1 Minimum Onboarding

Minimum onboarding first establishes read-only connectivity and the external account-control path. It lets the user see account facts, configure funds-use caps and scope and Halpha real-capital operating authority, verify credential revocation and human takeover, and then exercise the plan and action path in an isolated environment. Real Validation begins only after the user explicitly selects the real environment, validation objective, and funds-use caps and scope. Onboarding does not wait for every domain to be deepened and does not create a common production-admission package.

## 8.2 Real Validation Path

Each Real Validation must have an explicit objective, real environment, authorization path, funds-use caps and scope, expected action, stopping conditions, and evidence requirements. Stopping and external takeover remain available. A result may support or refute the objective, remain indeterminate, expose a business or technical problem, remain unresolved or unknown, or end by an active stop. One success or profit does not prove maturity.

### Definition of a Validation Plan 【FLOW-VAL-001-DEF】

A Validation Plan organizes the validation objective, environment, funds-use caps and scope, authorization path, stopping conditions, and evidence requirements. It does not replace the Trading Plan normally required for a real action, nor the fixed decision or instruction required for an exception. Lower-level design and L4 decide, from real consumers, whether an independent Validation Plan object or automated orchestration is needed.

## 8.3 Failure and Recovery

Failure uses a short loop: stop new real actions in the affected scope → reconcile external orders and positions → preserve necessary material → repair or roll back → reconcile unresolved responsibility and the authorization path → have the user decide whether to restore applicable Halpha real-capital operating authority. While an unknown or unresolved result remains, the scope stays stopped; only a contraction action explicitly directed by the user and shown not to increase or transform risk may continue.

## 8.4 Halpha Is Inaccessible

The user uses an official venue interface to inspect the account, revoke Halpha's write capability, and cancel, protect, or dispose of positions when necessary. After recovery, Halpha produces no new real action by default; it first reads external facts and avoids replaying old records. After applicable Halpha real-capital operating authority is restored, every action on the manual path still requires new current Manual authorization; an old confirmation cannot be reused. Unattended operation requires Machine authorization to be established again.

## 8.5 Disable and Exit

Exit stops new real actions, exposes residual orders and positions, revokes credentials, exports necessary plans and trading records, and confirms that the account remains independently controllable outside Halpha. Complex offboarding, successor identities, and institutional archiving are not requirements for this personal project.

---

# 9. Handoffs Between Horizontal Business Responsibilities and Vertical Constraints 【FLOW-HOF-001】

## 9.1 Two Responsibility Dimensions 【FLOW-HOF-001-DEF】

### Six Horizontal Business Responsibilities

| Domain | Sole primary responsibility | Enduring entry condition or product effect |
|---|---|---|
| CTX | Research or Trading Plan candidates and their disposition | Capture, screen, and decide whether to enter research, planning, waiting, or ending |
| ALP | Alpha research, economic evidence, and strategy | Improve judgment and profitability |
| POR | Comparison among multiple uses of funds | Enter only when multiple real uses must be compared |
| TRADEPLAN | Trading Plan and condition lifecycle | Turn a basis into a complete plan that can run and end |
| EXE | Actions, venue results, protection, and reconciliation progress | Preserve sole responsibility and basic correctness for venue or account changes initiated by Halpha |
| OUT | Integrated outcomes, attribution, and improvement handoff | Create a review or issue only when the outcome can change a later decision |

### Five Vertical Constraints

ARC defines the five vertical constraints, whose stable semantics are owned by CAP, DAT, UX, SYS, and ENG respectively. FLOW only confirms that horizontal paths are subject to the applicable constraints; it does not copy vertical-domain rules.

## 9.2 Use of the Responsibility Map and Requirements for Lower Levels 【FLOW-HOF-001-REQ】

The six horizontal business responsibilities and five vertical constraints form an eleven-responsibility map, but they do not require eleven modules, eleven services, or equal implementation depth. Real consumers, business value, and maintenance cost determine whether to deepen a domain; L4 records current choices and investment.

### Handoff to Lower Levels

HALPHA-DOC-001 governs the general responsibilities, admission rules, and current-state recording boundaries of L2, L3, and L4. FLOW hands off only the six horizontal business responsibilities, main handoffs, task-context continuity, and product-level outcomes for action, no action or waiting, unknown facts, stopping, external human takeover, recovery, and ending that this document defines. Lower-level document creation, deepening, and current records follow DOC.

FLOW's direct handoff also requires every lower-level path to preserve the three classes of control requirements in CON-CMP-003 and their responsibility boundaries. A path must not reintroduce funds reservation for future actions or two-stage funds and real-action approval. Other level and governance constraints are referenced directly from CON and DOC rather than rewritten in FLOW.
