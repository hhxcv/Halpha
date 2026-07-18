# Halpha Overall Technical Requirements and Architecture

**Document ID:** HALPHA-ARC-001  
**Version:** v1.9.0  
**Document Status:** ACCEPTED  
**Level:** L1-D  
**Language Edition:** en-US  
**Joint Normative Set ID:** HALPHA-ARC-001@v1.9.0+20260718T070120+0800  
**Paired Text:** HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md  
**Joint Set Registry:** HALPHA-ARC-001-technical-requirements-and-architecture.bundle.yaml  
**Effective Time:** 2026-07-18T07:01:20+08:00  
**Parent Documents:** HALPHA-CON-001 v2.11.0; HALPHA-DOC-001 v1.11.0; HALPHA-VIS-001 v1.4.0; HALPHA-FLOW-001 v1.8.0  
**This Document Governs:** enduring technical realization of VIS and FLOW; quality tradeoffs; overall logical form; dependency direction; authoritative state; simulated and real trading-action paths; environment isolation; recovery; and architectural concerns for the eleven responsibilities  
**This Document Does Not Govern:** specific business algorithms, pages, interface fields, database structures, vendors, product and instance choices, deployment commands, numerical limits, current construction scope, or implementation state

---

# 0. Architectural Conclusions 【ARC-SUM-001】

1. Halpha uses a personally maintainable modular monolith. It does not prebuild microservices, a message bus, clusters, or institutional high availability.
2. Architectural complexity first serves trading judgment, planning, data and execution correctness, and UX. Stability comes primarily from mature technology and simple structure.
3. Each transaction-record environment uses one authoritative relational database. Simulation and real-funds environments use authoritative stores or databases that are separate from each other. L3 selects the enduring database product and usage contract; L4 records the exact version, instances, and deployment choices.
4. Exchange-simulation and real-funds actions initiated by Halpha are both owned by EXE and use the same environment-qualified ExecutionAction, state progression, CAP checks, external submission, and reconciliation chain. Real-funds actions remain additionally subject to every Halpha real-capital operating-authority boundary and real-write gate.
5. Halpha does not decide the user's total personal investment. It enforces only the configured funds-use caps and scope, applicable decision basis, pre-action checks, authorization, stopping, and recovery. It neither reserves funds for future actions nor builds two-stage funds approval or a separate production-admission product.
6. Projections and caches are rebuildable and cannot become authoritative facts. When facts are unknown or conflicting, or a result is unresolved, new real actions in the affected scope remain stopped; only a contraction action explicitly directed by the user and shown not to increase or transform risk may continue.
7. Research, AI, reporting, management, and configuration capabilities must not become required synchronous dependencies for real-action submission, stopping, reconciliation, or recovery.
8. Six horizontal business responsibilities and five vertical constraints form an eleven-responsibility map, but do not require eleven modules, eleven services, or equal implementation depth.
9. The architecture applies the three classes of control requirements in CON-CMP-003 separately. It does not copy or blur their business meaning in one generic technical-control layer.
10. General technical capabilities are evaluated against mature third-party components first. Differences that affect only replaceable technical or strategy choices are adapted to the component's actual semantics and revalidated. Halpha supplies only the smallest gap in non-negotiable product semantics, functional correctness, or security boundaries; the same capability retains no parallel implementation.

---

# 1. Engineering Goals and Tradeoffs 【ARC-QLT-001】

## 1.1 Rationale at Personal-Project Scale 【ARC-QLT-001-RAT】

The target environment is long-term maintenance for one user, a small number of accounts, a limited number of venues, and a limited number of strategies. Planned maintenance and short interruptions are acceptable; zero downtime and an institutional team are not assumptions. Every technology choice must carry development, comprehension, testing, operation, failure, upgrade, migration, and exit costs.

## 1.2 Quality Priority Requirements 【ARC-QLT-001-REQ】

The following order allocates complexity only among alternatives that all satisfy L0's non-negotiable boundaries, an applicable plan and authorization, and basic functional correctness. A necessary boundary at a lower position cannot be waived in favor of a higher-positioned objective.

| Priority | Objective | Typical failure |
|---:|---|---|
| 1 | Quality of trading judgment, strategy, and planning | Incorrect views, conditions, or quantities, or inability to develop a profitable edge |
| 2 | Data and execution correctness | Incorrect account state, duplicate actions, lost partial results, or distorted costs |
| 3 | Convenient UX and user control | Unclear information, slow operation, difficult stopping, easy mistakes, or inability to take over |
| 4 | Stability | Fragile components, excessive dependencies, or hard-to-understand structure make frequent capabilities unreliable |
| 5 | Mitigation of risks from the system itself | Host, dependency, network, credential, or runtime failure cannot be isolated, stopped, recovered, or taken over |
| 6 | Implementation of financial risk controls | Failure to enforce the applicable decision basis, funds-use caps and scope, Halpha real-capital operating authority, amount, or exposure checks |
| 7 | Generality, governance completeness, and future expansion | Current maintenance burden is added for hypothetical scale |

CON-CMP-003 distinguishes financial risk control, functional correctness, and mitigation of risks from the system itself. The modules that own the relevant business semantics implement basic functional correctness, which cannot be weakened because the project or capital is small. Mature choices, simple structure, isolation, and external control should limit system-failure impact. The user's total-capital decision outside Halpha is not implemented as a system workflow.

An automatic control that is missing, unverified, or untrusted must not be described as available. An affected real action must use a feasible human or official-venue path instead; when that is also unavailable, it remains stopped, waits, or ends with no trade. A supporting component with no direct consumer or observed problem retains only its boundary or is not built.

## 1.3 Overall Technical Tradeoff Favoring Mature Capabilities 【ARC-QLT-002】

For a capability that crosses domains or may become general infrastructure, architectural selection proceeds in this order: identify current consumers and non-negotiable product semantics, functional correctness, and security outcomes; evaluate mature third-party components fit for purpose; compare their actual capabilities, constraints, and full-lifecycle costs; and only then decide to adopt, adapt to component capabilities, retain a minimal supplement, or explicitly not support the capability.

If a difference between a component and an existing design affects only strategy mathematics, internal structure, technical lifecycle, naming, or another replaceable choice, detailed design must adopt the component's actual semantics and revalidate affected outcomes rather than copy an implementation to preserve an old draft. Halpha retains only minimal boundary translation or product-semantic supplementation when the component would violate non-negotiable product semantics, functional correctness, or a security boundary, or when it truly lacks the required capability.

One capability may have only one runtime implementation and one fact authority. If a component is unavailable or its evidence is insufficient, Halpha stops, waits, hands control to a human outside Halpha, or explicitly does not support the capability; it does not maintain a long-lived parallel Halpha-built substitute. Component adoption must compare removed self-built complexity with added dependency, adaptation, configuration, upgrade, recovery, and exit costs. A candidate that neither reduces net complexity nor fills a non-negotiable gap does not enter the overall design.

---

# 2. Halpha Overall Logical Form 【ARC-TOP-001】

## 2.1 Definition of the Overall Logical Form 【ARC-TOP-001-DEF】

~~~text
Interaction entry / notification
            │
            ▼
   Application commands and queries
            │
  ┌─────────┴────────────────────────────────────────────┐
  │ Research and judgment │ Plans │ Facts │ Execution actions and reconciliation │ Outcomes and interaction │
  └─────────┬────────────────────────────────────────────┘
            │
 One authoritative relational database per transaction-record environment
            │
 Simulation and real-funds environment stores remain separate
            │
   ┌────────┴────────┐
   │ Read-only external adapters │ Single isolated external-write boundary │
   └────────┬────────┘
            │
        Venues and data sources
~~~

The boxes represent logical responsibilities, not independent deployments, and do not map one-to-one to the responsibility map. The overall form consists of a modular monolith, authoritative relational databases divided by transaction-record environment, necessary external adapters, and one isolated external-write boundary per trading environment. Only the real-funds boundary may hold real write capability.

## 2.2 Constraints on the Overall Form 【ARC-TOP-001-REQ】

The overall architecture must preserve these responsibility and isolation relationships. The applicable L3 selects the enduring database product; L4 determines process count, background workers, database instances and versions, and physical deployment isolation. Simulation and real-funds external-write boundaries use the same controlled implementation path but form separate instances. Real write authority must remain singular, minimal, and isolated from simulation credentials and general application capabilities.

Module boundaries follow semantic ownership, write responsibility, failure impact, and rate of change. A service split is considered only when measured isolation, contention, deployment, or scale problems cannot be solved inside the monolith.

When a third-party component fully provides an internal module capability, Halpha design still determines the semantic owner and public boundary, but no corresponding Halpha code module, component state machine, or general wrapper layer is required. The specific component adopted for the long term and its usage contract enter the applicable L3; the exact version, current configuration, and qualification evidence enter L4.

## 2.3 Platform-Independent Flow and Interaction-Entry Adaptation 【ARC-TOP-002】

### Rationale for Interaction-Entry Adaptation 【ARC-TOP-002-RAT】

If each interaction form owns business state and flow separately, adding an entry becomes a state migration and business rewrite and creates forks, conflicts, and mistaken authorization. Halpha therefore places platform-independent business flow, object identity, and authoritative state behind common application and domain boundaries and limits form-specific differences to entry adaptation.

### Platform-Independent Flow and Entry-Adaptation Requirements 【ARC-TOP-002-REQ】

Every supported interaction form is only an entry adapter to common application commands and queries. It MUST NOT create a parallel business flow, business write chain, authorization semantics, authoritative state, or client-specific migration path. A new interaction form MUST reuse the same object identities, commands, receipts, domain handlers, and authoritative state. Entry-local state may only be a deletable, rebuildable projection or draft that does not affect business progression.

The upper-level architecture preserves only the compatibility boundary for adding an entry; it does not prebuild an authentication protocol, network exposure, notification, offline, synchronization, deployment platform, or client framework. Applicable L3 defines security and technical contracts for a form only after a concrete construction scope and real consumer exist; L4 then records current enablement and evidence.

---

# 3. Business Modules and Dependencies 【ARC-BND-001】

The six horizontal business responsibilities express continuous business semantics; the five vertical responsibilities express cross-business constraints or support boundaries. They guide module boundaries but do not prescribe one code module, process, or service per responsibility. Runtime assurance comes jointly from mature technology choices, SYS, ENG, and the relevant business owners.

Each business semantic has one L2 owner. The module implementing that semantic has sole business-write responsibility. Other modules consume results through public commands, queries, or durable handoffs and do not modify its state directly. Shared code contains only stable technical capabilities with no business-semantic ownership.

A mature third-party component may directly provide market-data, indicator, protocol, persistence, scheduling, testing, or another general technical capability. Providing the implementation does not grant it ownership of Halpha product decisions, facts, or durable business state. Halpha retains only necessary conversion and non-negotiable semantics at the public boundary; it does not prebuild a complete parallel framework for a possible future vendor change.

Dependencies follow this direction:

~~~text
Interaction entry → application use case → business logic → port
                                                       ↑
                                        external adapter implements port

Research or user judgment → Trading Plan or permitted explicit decision or instruction → action preparation
Action preparation → funds-use caps-and-scope and Halpha real-capital operating-authority check → execution → external-fact reconciliation → outcomes and interaction
~~~

Research, AI, reporting, management, and configuration functions must not become synchronous dependencies for real-action submission, stopping, reconciliation, or recovery.

---

# 4. Authoritative State and Data 【ARC-DAT-001】

## 4.1 Source, Formation, Evidentiary Weight, and Ownership Must Not Be Confused

Halpha must distinguish sourced external observations, internal business decisions and responsibilities, external-action results, reconciled citable facts, and traceable derived results. These characteristics may relate to the same business matter, but storage or display cannot convert one into another.

A derived result or cache cannot become an account fact. A correction must retain the original observation, the basis for correction, and their relationship; it must not overwrite silently. When a fact is missing, expired, conflicting, or irreconcilable, Halpha must preserve the unknown scope and its effect on action.

## 4.2 One Authoritative Relational Database per Transaction-Record Environment

Each transaction-record environment uses one relational database for that environment's authoritative business state, unique constraints, transactions, unresolved processing responsibility, reconciliation state, and necessary history. Modules within one environment may have separate write boundaries, but do not receive separate databases by default.

Simulation and real-funds environments must use authoritative stores or databases, credential references, account identities, and write-adapter instances that are separate from each other. They share the same core business logic, ExecutionAction contract, state machine, repository interface, and adapter implementation path; they do not share account, action, authorization, or result identity. The enduring database product and usage contract enter L3; exact versions, instance count, hosts, and deployment locations are current choices owned by L4.

Task projections serve read and interaction needs; caches improve performance only. Missing projections or caches must be rebuildable and must not prevent stopping real actions, reading authoritative state, external reconciliation, or recovery.

## 4.3 Time and Numeric Values

A numeric value that can change planning, a funds-use caps-and-scope or Halpha real-capital operating-authority check, a venue action, reconciliation, or outcome interpretation must use a deterministic representation suitable for monetary and quantity precision, with units, currency, and conversion time traceable. When the distinction matters, event time, source time, receipt time, decision time, and submission time must not be conflated.

Actual correctness, freshness, and behavior during missing, incomplete, or recovering data determine whether a source is suitable for a use. Halpha does not build a common rating platform for all sources.

---

# 5. Plans, Environment-qualified Authority, and Execution Actions 【ARC-ACT-001】

## 5.1 Identifiable Decisions, Explicit Enablement, and Stopping

An enabled Trading Plan, a permitted exception decision or instruction, funds-use caps and scope, authorization, and a stopping decision must all be identifiable, with historical decisions distinguished from the currently applicable decision. A material change creates a new version or decision under the applicable semantic owner's rules; content that supported a real action must not be rewritten silently.

An interface, program, or AI must not convert Manual authorization into Machine authorization implicitly. Machine authorization must have explicit scope, duration, and failure outcome before the trigger. Stopping and narrowing scope take effect immediately. Only an explicit user operation may raise a funds-use cap, expand scope, or expand automatic-action capability.

## 5.2 Unified Execution-Action Chain

~~~text
Current branch of an enabled Trading Plan,
or a permitted explicit user decision, fixed in advance, to protect or reduce risk,
or an explicit user instruction to cancel, protect, transfer, or reduce risk that can be shown not to increase or transform risk
→ read the current environment, key facts, funds-use caps and scope, environment-qualified authority, and the stopping decision
→ confirm that the current environment's Manual- or Machine-authorization path is valid; a real-funds environment also requires applicable Halpha real-capital operating authority
→ Halpha completes environment-qualified checks of caps, scope, authority effect, and stopping under CAP rules
→ before external writing, EXE durably forms an environment-qualified ExecutionAction and establishes one processing responsibility
→ the current environment's single isolated external-write boundary refreshes key facts, repeats the CAP checks, and processes that responsibility
→ submit the venue action, query external results, and keep partial results, timeouts, and unresolved results visible
→ reconcile and update citable facts, then return the outcome to the applicable plan, protection responsibility, or learning path
~~~

Every permitted source in exchange simulation and real-funds environments MUST enter the same main chain. The chain contains no independent funds permission, reservation for future funds, or final funds approval. Manual authorization or Machine authorization chooses the action path; the CAP check determines whether the current action crosses the current environment's caps, scope, and authority effect. Neither substitutes for the other. Simulation-validation authority has no real-capital effect and cannot satisfy a real-funds check. An old manual confirmation cannot supply a missing current confirmation or Machine authorization, and a machine rule cannot replace risk judgment that the user must bear.

## 5.3 Local Transactions and Venue or Account Changes

A relational transaction makes only internal state atomic; it cannot form one transaction with an external venue or account change. Before external writing in any trading environment, Halpha MUST leave a recoverable ExecutionAction and one processing responsibility. When an external result is unclear, Halpha first queries by a stable external identity and does not resend blindly.

Within any scope where external-action identity or duplicate prevention may interact, only one external-write authority may be effective. A runtime entity that loses that authority must stop submitting. EXE and SYS define detailed claiming, idempotency, concurrency, and fencing mechanisms.

## 5.4 Isolation of Exchange Simulation, Historical Market Replay, and Real-Funds Environments

Historical research and historical market replay reuse only pure condition evaluation, plan semantics, and outcome analysis. Exchange simulation and real-funds paths MUST reuse the same TRADEPLAN→CAP→EXE→DAT→OUT application chain, ExecutionAction contract and state progression, repository interface, and venue-execution-client construction path, while environment, account, action, authorization, and result identities remain unambiguous.

- Historical market replay supports research and timing validation only and never enters the real external-write path.
- Exchange simulation uses accounts and results provided by the venue; Halpha does not build another real-time exchange with its own matching and profit-and-loss accounting. Its primary evidence objective is the system flow and mechanisms; strategy-behavior evidence is secondary.
- Simulation and real-funds environments use separate runtime instances, authoritative stores or databases, configuration profiles, endpoints, credential references, account identities, and adapter instances. Environment differences are limited to an explicit L3 allowlist and do not appear as scattered business-logic branches.
- Builds for both environments MUST produce a reviewable environment-parity manifest proving identical source digests, application services, ExecutionAction schema, repository, state machine, and venue-execution-client construction path, and listing the only permitted configuration differences. Exact digests and current validation results are recorded in L4.
- A simulation record cannot become a real-account fact. A simulation identity or credential cannot obtain real write capability, and simulation-validation authority has no real-capital effect.
- Moving from simulation to real funds requires completely new real-environment, account, action, and authorization identities and requires the user to obtain an applicable plan, funds-use caps and scope, Halpha real-capital operating authority, and any required authorization again. Simulation records MUST NOT be edited, promoted, copied, or migrated to perform that transition.
- Simulation results MUST NOT be interpreted as proving real liquidity, queue position, impact, slippage, fees, funding, latency, permissions, availability, or real Alpha performance.

If Halpha cannot prove that a simulation path cannot reach the real-write boundary, simulation must not be enabled at the same time as real credentials.

---

# 6. External Adapters and Tool Boundaries 【ARC-ADP-001】

External adapters own authentication, protocols, mapping, rate limits, error translation, external identity, and capability declaration. Core business logic does not depend on vendor SDK objects or error codes. Read and write capabilities should be separated where practical; ordinary research, AI, and interface components do not hold real trading write credentials.

An action, fact, or protection semantic unsupported by a venue or component must be rejected or explicitly degraded; a common interface must not pretend that it is supported. Halpha retains only the necessary adaptation for venues and data sources actually in use. Connection, protocol, retry, or state capabilities already supplied by a mature component must not be reimplemented in Halpha. Halpha extracts a common framework only after a second real consumer appears and shared abstraction demonstrably reduces net total complexity.

---

# 7. UX Technical Boundaries 【ARC-UX-001】

UX is a core product capability. The architecture must support FLOW's user tasks, cross-domain current state, search, and direct entry; continuous distinction between simulation and real environments; explainable current decisions, basis, unknowns, action receipts, and external results; reachable stopping and external takeover; resumption that highlights intervening changes; and read models that distinguish facts, estimates, AI suggestions, user decisions, and venue results.

Read projections may be optimized for UX, but every write command must pass through the same application boundary. An interface or notification failure must not create a hidden write path or prevent fallback stopping and external account control.

---

# 8. Stability-Oriented Technology Choices and Minimum Recovery 【ARC-OPS-001】

## 8.1 Rationale for Stability-Oriented Technology Choices 【ARC-OPS-001-RAT】

Stability is measured by core business outcomes: whether frequent paths are usable, facts are fresh, duplicate real actions are prevented, reconciliation advances, and stopping and restart are safe. It comes first from mature technology, simple structure, SYS and ENG boundaries, and correctness within each business domain—not from an independent operations platform.

For a personal project maintained by one owner, relational-database transactions, off-the-shelf process management, ordinary logs, and backup provided by the database or hosting environment normally cover the main needs. Halpha does not build a specialized stability platform before failures recur.

## 8.2 Stability and Recovery Requirements 【ARC-OPS-001-REQ】

The overall architecture should prefer mature components, a modular monolith, authoritative relational databases divided by transaction-record environment, few processes, and few external dependencies. It does not rebuild a sufficient off-the-shelf capability.

When a component fails, its capability is unknown, or its qualification evidence becomes invalid, the affected path stops, becomes read-only, returns control to the user, or becomes explicitly unsupported according to the business impact. It must not switch automatically to a self-built implementation that is not also the sole design and sole validation target. Before restoring or replacing the component, Halpha must reconcile external facts, compatibility boundaries, and affected evidence again.

Startup and recovery must first read authoritative state, the current stopping decision, funds-use caps and scope, and Halpha real-capital operating authority; they then connect read-only external sources, reconcile orders and positions, and handle unresolved real-action responsibilities. If a key fact, external result, or write authority is unclear, the affected scope remains stopped; only a contraction action explicitly directed by the user and shown not to increase or transform risk may continue. Restart does not replay a real action by default.

Restoring Halpha real-capital operating authority that expired, was revoked, or was contracted means only that later actions may again enter the applicable authorization path. Every action on the manual path still requires new current Manual authorization; an old confirmation cannot be reused. Still-valid Machine authorization and runtime eligibility MUST be evaluated separately. The system may continue within the original authorization scope only when accepted design for the current phase explicitly permits it and every evidence gate passes for a unique writer; authoritative-state and database continuity; unchanged build/configuration/credentials/account identity; reconciliation of external orders, fills, positions, protection, and unknowns; and no replay of missed actions. In every other phase, or when any evidence is unclear, the system MUST remain stopped for an explicit User command to resume, exit, hand over, or establish new authorization. EXE, DAT, and SYS define detailed recovery conditions and unresolved-result semantics, and current L4 MUST select and validate one phased recovery mode.

Backups preserve only authoritative state and necessary configuration that cannot be rebuilt cheaply. By default, Halpha does not build a health page, integrated monitoring, an alert center, self-healing, hot standby, multi-region deployment, automatic failover, a dedicated backup product, or an operations-incident platform. It adds only the smallest capability that reduces long-term cost after real problems recur and off-the-shelf methods prove insufficient.

---

# 9. Identity and Basic Security 【ARC-SEC-001】

Real trading credentials use the smallest practical permissions and, by default, have no withdrawal, transfer, or account-management capability. Real credentials must not enter source code, documentation, AI context, ordinary logs, or development environments. Interaction identity, runtime identity, user decisions, Machine authorization, and real trading credentials must remain separate. A program or AI cannot create authorization from its own output or mistake the existence of a session for the user's confirmation of the current action.

The user retains official account access, credential revocation, and a manual disposition path outside Halpha. If the system fails or credential leakage is suspected, Halpha first stops writes, revokes or isolates credentials, and reconciles the account.

Security investment follows actual impact. The strongest protection goes to capabilities that can submit actions, read real credentials, change funds-use caps and scope or Halpha real-capital operating authority, write account facts, or prevent stopping. The project does not build enterprise IAM, a SOC, a trusted-computing-base registry, or an institutional threat-governance platform.

---

# 10. AI Development and Technology Strategy 【ARC-TEC-001】

AI-assisted development follows ENG's impact tiers. Changes to trading judgment, planning, data, execution, frequent UX, stopping, and recovery require stronger validation; low-impact support changes use a lighter process. Halpha does not establish a common engineering-approval conclusion or production-admission committee.

Overall technology choices first directly adopt fit-for-purpose qualified mature languages, frameworks, quantitative or domain components, relational databases, official venue adapters or mature adaptation capabilities, standard logs, off-the-shelf process management and backup, and a deployment form that one person can diagnose and recover. When an off-the-shelf component differs from a replaceable technical choice, the design follows the component's actual capability and revalidates it rather than copying the old implementation detail in self-built code.

ENG establishes engineering gates for capability search, difference classification, licenses, target platforms, upgrade and exit, and net complexity change. Under DOC, L3 records the specific component adopted for the long term, Halpha's usage contract, and the minimum supplementary boundary; L4 records the exact version, build identifier, current configuration, platform-qualification evidence, and enablement state. ARC does not select a specific vendor or version.

Without an evidence-based trigger, Halpha does not introduce microservices, distributed transactions, an event-sourcing platform, a general message bus, Kubernetes, multi-region clusters, a general plugin system, multi-tenant permissions, an enterprise data lake, an integrated observability platform, or an institutional risk engine.

---

# 11. Complexity Budget and Evolution 【ARC-CMP-001】

Complexity first goes to trading judgment and planning, fact and real-action correctness, and clear controllable UX. SYS, CAP, ENG, governance, and supporting automation remain at the minimum depth needed by current real consumers. Stability alone does not justify a separate operations platform or automatic deepening of a supporting domain.

Every new platform, state machine, registry, or workflow requires a real consumer and an observed problem. A service split occurs only when measured scaling, isolation, release, contention, or security-boundary needs exceed the monolith's capacity. Before that, Halpha prefers deleting functionality, reducing synchronous dependencies, optimizing queries and tasks, isolating a few background workers, or improving adapters.

Introducing a third-party dependency must account both for the self-built code, state, tests, runtime responsibility, and maintenance surface that it removes and for the dependency, glue, configuration, license, upgrade, recovery, and exit costs that it adds. If net complexity does not decrease and no non-negotiable gap must be filled, Halpha must not introduce a new wrapper layer, parallel implementation, or platform.

---

# 12. Enduring Architectural Concerns for the Eleven Responsibilities 【ARC-L2D-001】

| Domain | Enduring architectural concern |
|---|---|
| ALP | Core judgment, economic evidence, and strategy quality; deepen only for real research consumers |
| TRADEPLAN | Complete plan semantics that can execute and end |
| EXE | Uniqueness, external results, protection, unknowns, and reconciliation for environment-qualified ExecutionAction; simulation and real-funds environments use the same execution semantics |
| DAT | Sourced facts, timeliness, correction, unknowns, and recovery |
| UX | Convenience, clarity, control, and recoverability for frequent tasks |
| SYS | Module and runtime boundaries, dependency direction, authoritative state, and simple recovery |
| CTX | Low-friction candidate capture and disposition, without a general content platform |
| OUT | Start with short reviews and actionable issues; deepen from real samples |
| POR | Implementation demand arises only when multiple real uses of funds must be compared |
| CAP | Funds-use caps and scope, authorization, action checks, stopping, and recovery boundaries |
| ENG | Impact-tiered validation, mature-capability search and minimum-self-build gates, reproducible builds, migration, rollback, and dependency maintenance |

The responsibility map describes semantic ownership, not a balanced investment plan. Every part required by an enabled core path must be correct; a part with no consumer is not built merely to complete a logical diagram. L4 records current domain depth, support scope, products, instances, and implementation tradeoffs.

---

# 13. Handoff to Lower-Level Design 【ARC-HOF-001】

HALPHA-DOC-001 governs the general responsibilities, admission rules, and current-state recording boundaries of L2, L3, and L4. ARC hands off only its overall logical form, dependency direction, mature-capability-first gate, one authoritative relational database per transaction-record environment, one isolated external-write boundary per environment, unified simulation/real-funds execution implementation with identity isolation, environment-parity proof, and recovery order to applicable lower-level design. The relevant L2/L3 specifications refine domain, module, component-usage contract, interface, data, state, error, idempotency, concurrency, fencing, and test semantics for real consumers.

Under DOC, the enduring database product and third-party component usage contracts enter the applicable L3. Exact database versions and instances, third-party component versions and build identifiers, current configuration and qualification evidence, processes and background workers, hosts and deployment locations, venues, and adapter support scope are recorded in L4. Candidate design, completed design, existing code, or one test cannot substitute for L4's current-capability and validation evidence.
