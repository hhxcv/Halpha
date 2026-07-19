# Halpha Core Business Workflows and User Journeys

**Document ID:** HALPHA-FLOW-001  
**Level:** L1-C  
**Language Edition:** en-US  
**Paired Text:** HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md  
**Parent Documents:** HALPHA-CON-001, HALPHA-DOC-001, and HALPHA-VIS-001  
**This Document Governs:** how the user researches, forms judgments, plans, trades in simulation or with real funds, reconciles, intervenes, and reviews in Halpha, and the product-level handoffs among the core business responsibilities  
**This Document Does Not Govern:** pages, fields, internal records, technical transactions, deployment, validation orchestration, numerical limits, or current construction state

---

# 0. Workflow Positioning and Core Commitments 【FLOW-SUM-001】

## 0.1 Rationale for the Workflow 【FLOW-SUM-001-RAT】

Halpha serves a direct personal-trading path: understand the facts, form a judgment, make a plan, act correctly, reconcile the outcome, and improve. Research, controls, and engineering measures should support this path rather than become a separate governance process that the user must complete first.

The user may choose not to trade, stop Halpha, or take over through an official venue interface. Longer system operation does not change the user's final authority.

## 0.2 Core Workflow Requirements 【FLOW-SUM-001-REQ】

- On entry, the user can see accounts, positions, orders, active plans, material anomalies, and whether action is needed. With nothing to do, the user may exit or enter research, planning, or review directly.
- A real action normally comes from a fixed, complete Trading Plan. Protection, exit, or risk reduction for an existing exposure may also come from a direct User instruction with a clear subject and scope.
- One explicit plan activation may also grant a bounded machine-execution scope belonging only to that activation. The scope must fix the environment, account, plan, instrument, funds limits, term, and permitted actions. It does not change the plan or apply to later activations.
- Every external action uses current facts, passes the applicable capital and authority checks, is submitted through one execution path, and is followed by venue reconciliation. Repeated requests must not produce duplicate actions.
- When facts are unknown, authority is insufficient, or the path is infeasible, Halpha adds no new risk. Only a contraction explicitly requested by the User and shown not to increase or transform risk may continue.
- Exchange simulation and real-funds environments use the same business chain, while environment, account, authority, action, and outcome identities remain separate. Simulated decisions and results must not migrate into real-funds facts.
- Stopping, exit, and external human takeover through an official venue interface remain reachable.

---

# 1. Path Continuity Under Limited Attention 【FLOW-TIM-001】

The user should be able to enter the highest-value task from current state. Anomalies and time-bound matters take priority, but the normal entry must not become a technical status page.

Research and plan drafts may be resumed after interruption. Resumption highlights intervening changes, expired inputs, and decisions that must be made again. An external action that occurred or may have occurred must never be replayed because of resumption, restart, or a repeated click; Halpha first reconciles external facts.

---

# 2. Recurring Usage Scenarios 【FLOW-MAP-001】

| User purpose | Main path | Normal ending |
|---|---|---|
| Quick inspection | Current facts and pending work → relevant plan, order, position, or anomaly | Handle one item, or exit with nothing to do |
| Strategy research | Fix the question and boundaries → explore, falsify, and compare → human selection | Abandon, continue researching, or adopt a result |
| Plan creation | Basis → entry, exit, protection, scale, term, and failure handling → preview | Save a draft, fix the plan, or abandon it |
| Plan operation | Activate → observe conditions → check current facts and proposed action → execute and reconcile | Take no action, continue, stop new risk, exit, or hand over |
| Existing-risk handling | Current order or position → protection, risk-reduction, or exit decision → execute and reconcile | Complete, remain stopped, or hand over externally |
| Review and improvement | Original judgment and plan → actual outcome and cost → actionable differences | Make no change, or form new research, a plan, or an improvement |

These paths are not a mandatory funnel. The user may enter research, fact lookup, position handling, or review directly. With no suitable opportunity, the path ends by waiting, holding cash, or making no trade.

---

# 3. Boundary Between External Tools and Halpha 【FLOW-TOOL-001】

## 3.1 Rationale for External-Tool Responsibilities 【FLOW-TOOL-001-RAT】

Venues provide official account operations, specialist charting and research environments provide their strongest forms of analysis, and news and data sources provide source material. Halpha does not duplicate a sufficient external capability.

AI may begin exploring, implementing, running, comparing, falsifying, and organizing material from the User's research question and the currently available data and tool boundaries. Resource and stopping limits are added only when resource use or the intended claim requires them. AI does not acquire authority over facts, strategy adoption, Trading Plans, or real actions.

## 3.2 Halpha-Owned Continuity and Handoff Requirements 【FLOW-TOOL-001-REQ】

Halpha preserves research and plan context, the plan in use, User-configured capital boundaries, actions initiated by Halpha and unresolved responsibilities, and necessary reconciled facts. A cross-tool handoff identifies the subject, time, applicable plan, and return path. “Done” in an external tool cannot replace Halpha's reconciliation of account facts.

---

# 4. User Interaction and Control 【FLOW-UX-001】

## 4.1 Six User Task Domains 【FLOW-UX-001-DEF】

The enduring User tasks are market observation, strategy research, Trading Plans, trade execution and position management, accounts and trading records, and review and learning. They describe task scope, not required pages, modules, or services.

## 4.2 Requirements for Using the Task Domains 【FLOW-UX-001-REQ】

Interaction preserves task context and lets the User distinguish facts, inferences, AI suggestions, User decisions, and external outcomes. Frequent tasks take few steps; sources, history, and technical detail expand on demand.

Fixing plan content, raising capital caps or widening scope, activating a plan, stopping, exiting, and taking over are distinct User decisions. Under Section 0.2, plan activation includes the bounded machine-execution authority for that activation. One decision must not silently change another.

## 4.3 Business Flow Is Independent of Interaction Form 【FLOW-UX-002】

### Platform-Independent Business-Flow Requirements 【FLOW-UX-002-REQ】

Different interaction forms read the same authoritative state, invoke the same business commands, and return the same outcome semantics. Switching entry points must not copy, infer, or fork plans, authority, actions, or outcomes.

---

# 5. Research and Planning 【FLOW-TRADEPLAN-001】

## 5.1 AI-Led Research and Final Human Selection 【FLOW-AIR-001-REQ】

Strategy research may proceed independently. As long as it does not consume trading runtime state, account writes, or real credentials, it does not depend on the trading execution chain being available. The User need only state the question and currently available data boundary before AI begins exploring, failing, rerunning, and screening without item-by-item approval. Evaluation basis, costs, counterevidence, resources, and stopping conditions are completed only when a result is being prepared for a product or capital decision, and only to the strength of that claim. No qualified result is a normal ending.

Only the User decides whether to adopt a research result. Adoption does not automatically fix or activate a Trading Plan, change a capital boundary, or create a real action.

## 5.2 Research Entering Planning

When research supports a plan, the result states its applicable scope, main basis, counterevidence, costs, limitations, and invalidation conditions. The User may also begin planning directly from a sufficiently formed personal judgment; formal research is not mandatory for every plan.

A complete plan answers why to act, what it applies to, when to enter, when it becomes invalid, how much to take, how long it remains valid, and what happens after a trigger. Incomplete content remains a draft. A material change creates a new version; the original decision cannot be completed after an action.

---

# 6. Operation, Actions, and Reconciliation 【FLOW-RUN-001】

After activation, Halpha may observe conditions and form action intent permitted by the plan. A satisfied condition does not approve the action. Every action still reads current facts, checks capital boundaries, activation scope, and stopping state, and then proceeds through the one external-write path and reconciliation.

Plan activation is the only User authorization entry through which Halpha may create a machine action that adds risk. When a trigger requires judgment outside the plan, exceeds scope, or encounters a blocking unknown, Halpha does not request ad hoc per-action confirmation to bypass the plan; it waits, expires, makes no trade, or the User changes and reactivates the plan. Explicit protection, cancellation, reduction, and exit instructions for existing risk still enter the same check, execution, and reconciliation chain and cannot be converted into risk-adding capability.

An action performed by the User through an official venue interface is external activity. Halpha reads and reconciles the facts afterward and does not relabel that action as its own.

The User may stop Halpha from adding risk, exit a plan, or enter human takeover. Stopping does not automatically cancel orders or close positions; existing orders, positions, and protection responsibilities remain subject to reconciliation or explicit handoff.

---

# 7. Outcomes and Learning 【FLOW-LRN-001】

After a plan ends or responsibility for a material action closes, review compares the original judgment and plan with actual outcomes and cost and retains only improvements that can change a later decision. Review does not directly rewrite a strategy, plan, authority, or capital cap, and profit does not automatically widen scope.

---

# 8. Onboarding, Failure, and Exit 【FLOW-REC-001】

Onboarding first establishes read-only observation and an external takeover path through the official venue interface, then verifies planning, actions, stopping, and reconciliation. A simulation environment exercises the same business chain but cannot prove real-market performance or real-funds availability.

Failure uses a short loop: prevent affected new risk → reconcile orders, fills, and positions → repair or roll back → decide whether to continue, end, or hand over. After a system restart, the same activation may continue only when the User did not stop it, facts and original authority remain consistent, and missed actions will not be submitted.

After the User stops new risk, exits, or takes over, that activation can never resume adding risk. Existing exposure continues through its original protection or exit path. If the User wants to trade again after the old responsibilities close, a new activation is required.

If Halpha is unavailable, the User uses an official venue interface to inspect the account, revoke write capability, and manage risk. Exit stops new actions, exposes residual responsibilities, revokes credentials, and exports necessary plans and trading records.

---

# 9. Handoffs Among Core Business Responsibilities 【FLOW-HOF-001】

## 9.1 Horizontal Business Responsibilities 【FLOW-HOF-001-DEF】

| Domain | Product-level responsibility |
|---|---|
| ALP | Research strategies, evaluate economic evidence, and form adoptable results |
| TRADEPLAN | Turn a basis into a plan that can run, stop, and end |
| EXE | Preserve unique execution and reconciliation responsibility for external actions initiated by Halpha |
| OUT | Form useful review and improvement from plans and outcomes |

CAP, DAT, UX, SYS, and ENG provide capital-control, fact, interaction, runtime, and engineering constraints respectively. Responsibility names do not require same-named modules, services, or equal construction investment.

## 9.2 Requirements for Lower Levels 【FLOW-HOF-001-REQ】

Lower-level design details only the objects and failure handling needed by real consumers. It does not copy the whole workflow or build platforms for future possibilities. Current support, construction order, and evidence belong only in L4.
