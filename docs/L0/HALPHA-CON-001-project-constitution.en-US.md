# Halpha Project Constitution: Mission, Personal Risk Control, and Development Principles

**Document ID:** HALPHA-CON-001  
**Version:** v2.11.0  
**Decision Status:** ACCEPTED  
**Level:** L0  
**Language Edition:** en-US  
**Joint Normative Set ID:** HALPHA-CON-001@v2.11.0+20260718T070120+0800  
**Paired Text:** HALPHA-CON-001-project-constitution.zh-CN.md (zh-CN)  
**Joint Set Registry:** HALPHA-CON-001-project-constitution.bundle.yaml  
**Effective Time:** 2026-07-18T07:01:20+08:00  
**Scope:** Halpha's long-term mission, role and capital sovereignty, non-breakable boundaries, highest-order trade-offs, AI and technology trust boundaries, complexity boundaries, and change conditions  
**Authority Scope:** This Constitution is the current highest normative source for every CON-* principle listed in Section 10.

---

# 0. Non-normative Summary

This section only aids reading and creates no independent norm. Each requirement is governed by the sole normative body identified by its principle ID.

- Effect, authority, and trade-offs: CON-GOV-001 through CON-GOV-006 and CON-PRI-001
- Mission, Project Owner, User, and scope: CON-MIS-001, CON-USR-001, CON-USR-002, CON-HUM-001, and CON-NGL-001
- Economic outcomes: CON-ECO-001 through CON-ECO-004
- Capital and authority: CON-CAP-001 through CON-CAP-006
- Facts, evidence, and learning: CON-TRU-001, CON-EVD-001, CON-EVD-002, CON-LRN-001, and CON-ADP-001
- AI, technology, data, cost, and security: CON-AI-001, CON-SOV-001, CON-CST-001, CON-SEC-001, and CON-SEC-002
- Operation and exit: CON-OPS-001 through CON-OPS-003 and CON-LIF-001
- Complexity and development: CON-CMP-001 through CON-CMP-004 and CON-DEV-001

---

# 1. Effect, Authority, and Highest-order Trade-offs

## 1.1 Document Purpose

This Constitution defines only the mission, role sovereignty, non-breakable boundaries, highest-order trade-offs, trust and complexity boundaries, and change conditions that MUST remain valid across product stages, implementations, and technologies. Product journeys, complete states, interfaces, fields, technical implementations, concrete configurations, test methods, operating steps, and current development status are owned by lower-level specifications or current records.

## 1.2 Document Status and Effect【CON-GOV-002】

### Normative Document Status Definition【CON-GOV-002-DEF】

This Constitution has the following statuses:

- **PROPOSED:** available for review and revision, with no normative effect;
- **ACCEPTED:** the sole current normative bilingual version package explicitly approved by the Project Owner;
- **SUPERSEDED:** replaced by a later ACCEPTED version and retained only for traceability;
- **WITHDRAWN:** withdrawn before ever taking normative effect.

### Effect Requirements【CON-GOV-002-REQ】

A version takes effect only after the Project Owner, acceptance time, both co-normative language texts, each text's content identifier, and the uniquely identifiable bilingual version package have been recorded. Unless a delayed effective time is recorded separately, the effective time equals the acceptance time. Only one current ACCEPTED bilingual version package may exist at a time.

The Constitution taking effect does not prove that an implementation conforms to its principles and does not grant any real-capital operating authority.

## 1.3 Normative Authority, Lower-level Registration, and Evidence【CON-GOV-001】

### Authority and Responsibility Definition【CON-GOV-001-DEF】

The current normative source is the body that owns a concept and determines its authoritative meaning. The co-normative language texts for the same document ID and version constitute one logical normative source, not competing sources.

| Level | Responsibility |
|---|---|
| Constitution | Mission, highest boundaries, and trade-offs |
| Lower-level specifications | Stable product, domain, technical, and operational design |
| Machine specifications | Precise fields, protocols, and constraints |
| Implementation | Execute the current specifications |
| Test, acceptance, and operating records | Provide evidence of actual behavior and conformity |

### Authority Use Requirements【CON-GOV-001-REQ】

Each concept MUST have only one current normative source. Lower-level specifications MAY only refine, instantiate, or narrow a higher-level principle; they MUST NOT redefine it, waive it, or expand its authority. Implementations, tests, operating results, and external facts MAY demonstrate conformity, expose deviation, or trigger revision, but MUST NOT rewrite a specification by themselves.

Concrete accounts, numeric values, vendors, dependencies, budgets, fields, test methods, operating steps, and current assumptions MUST be managed only when actually needed, through lower-level specifications, simple configuration, or current records. Unmaintained registries, state machines, or approval processes MUST NOT be created merely for formal completeness. When critical information is missing, stale, or conflicting, automated real actions that directly depend on that information MUST stop, while the User's ability to stop and handle the matter manually through an external path MUST remain available.

Each constitutional principle MUST have a stable ID and MUST be fully defined in only one normative body. Summaries and indexes only reference that body.

## 1.4 Normative Terms and Deviations【CON-GOV-003】

### Normative Terms Definition【CON-GOV-003-DEF】

- **MUST / MUST NOT:** mandatory requirement;
- **SHOULD / SHOULD NOT:** default requirement;
- **MAY:** permitted option.

### Deviation Handling Requirements【CON-GOV-003-REQ】

A MUST or MUST NOT requirement cannot be waived by an architecture decision record, revision proposal, implementation, test, or operating practice. A deviation from SHOULD or SHOULD NOT MUST state its impact scope and rationale, and the conditions for restoring, replacing, or accepting the deviation. MAY does not create a prerequisite for development, release, or opening authority.

A known violation of MUST or MUST NOT requires the affected release to be blocked. If the violation concerns real capital, or its impact cannot be shown to be isolated, increases to the funds-use caps and scope and any increase or restoration of Halpha real-capital operating authority MUST also be blocked until conformity is restored or the Constitution is formally amended.

## 1.5 Highest Conflict Order【CON-PRI-001】

All applicable mandatory requirements and non-breakable boundaries MUST be satisfied first. The priority order below applies only when choosing among eligible alternatives that all satisfy the hard boundaries; it never authorizes a higher priority to bypass, weaken, or trade away any hard boundary.

When objectives or requirements conflict, apply this order:

**The User's final control over funds-use caps and scope, Halpha real-capital operating authority, stopping, restoration, and external manual takeover → trading judgment, functional correctness, and ease of use → reliable operation achieved through mature technology and simple structure → financial-risk control and system-risk mitigation proportionate to a personal project → all other supporting governance, process, and abstraction.**

The User decides outside Halpha which accounts and how much trading capital to provide to Halpha, and limits them there. This is not a Halpha function or guarantee. Halpha only records and enforces the funds-use caps and scope configured by the User and MUST NOT increase or expand them by itself.

When facts are unknown or Halpha behaves abnormally, new real actions in the affected scope MUST stop and control MUST return to the User. Stopping, narrowing authority or scope, and external manual takeover MUST NOT depend on formal approval or a complete incident process. Reliability SHOULD be achieved first through mature technology, few dependencies, and simple structure. The complexity of supporting capabilities MUST NOT exceed their verifiable benefit to core trading and user experience.

## 1.6 Co-normative Language Texts and Language Conflicts【CON-GOV-006】

### Co-normative Language Text Definition【CON-GOV-006-DEF】

The zh-CN and en-US bodies for the same document ID and version are the co-normative language texts of one logical normative document. They have equal, direct, and independent normative effect. Neither is the original, translation, summary, interpretation, or subordinate text of the other, and neither language has priority or final interpretive authority.

### Alignment, Effect, and Conflict Handling Requirements【CON-GOV-006-REQ】

Each co-normative language text MUST be semantically complete, so that a person or AI can determine every principle, obligation, prohibition, authority, condition, and exception in that version without reading the other language text.

The two texts MUST share the document ID, version, principle IDs, section structure, decision status, effective time, and Joint Normative Set ID. They MUST express the same normative strength, scope, priority, conditions, exceptions, responsibilities, and outcomes. Each language MAY use natural phrasing; word-for-word correspondence is not required.

The Project Owner MUST approve a uniquely identifiable complete bilingual version package. Both texts MUST take effect, be revised, be superseded, or be withdrawn together. Any change affecting meaning or structure MUST update both texts and be approved as a new bilingual version package. Routine work MAY read only the working-language text; specification changes, bilingual alignment reviews, and actual language conflicts MUST examine both texts.

If the two texts have a substantive ambiguity, omission, or inconsistency, neither language takes priority; a convenient interpretation MUST NOT be selected, and a third rule MUST NOT be synthesized. Affected normative use, design approval, release, authority increase or restoration, and expansion of funds-use caps and scope MUST stop. Within an affected real-capital scope, responses MUST be limited to stopping, isolation, reconciliation, or a constraining action explicitly directed by the User that does not increase or convert risk. Principles unaffected by the conflict remain effective.

Only a new bilingual version package approved by the Project Owner MAY close a language conflict. An AI that detects or suspects a conflict MUST report the principle ID and both relevant passages and MUST NOT decide the conflict itself. Before either language text is used alone for an authority-sensitive decision, its header and Joint Set Registry MUST confirm valid identity, version, status, effective time, Joint Normative Set ID, equal bilingual authority, alignment status, and body content identifiers. If any condition is missing, the text MUST NOT be used to increase authority or expand real-capital use.

---

# 2. Project Mission, Project Owner, User, and Scope

## 2.1 Project Mission【CON-MIS-001】

### Project Identity Definition【CON-MIS-001-DEF】

Halpha is a personal trading-decision, execution, and learning system built with one Project Owner's development time and money and used with one User's own trading capital. The same human MAY serve as Project Owner, User, and Developer, but the roles' responsibilities and judgment perspectives do not merge. AI tools MAY perform development work but are not the User.

### Project Mission and Value Requirements【CON-MIS-001-REQ】

Halpha's mission is to help the User form higher-quality trading judgments and plans within the configured funds-use caps, scope, and authority, execute and manage actions reliably, conveniently, and observably, and learn continuously from results, while enabling the Project Owner to achieve attributable product success at proportionate development and maintenance cost.

Halpha does not treat the number of tools, degree of automation, technical complexity, number of governance processes, or AI autonomy as final value. Core value comes from decision quality, long-term net outcomes, execution quality, user experience, and sustainable operation.

## 2.2 Project Owner, User, and Developer Boundaries【CON-USR-001】

### Project Owner Definition【CON-USR-001-DEF】

The Project Owner bears Halpha's development investment and project-governance responsibility, decides project design, development scope, sequence, and priorities, and evaluates product success and development cost. The Project Owner does not gain authority over the User's trading capital, account, or product-use decisions merely by holding that role.

### User, Developer, and Manual-path Identity Boundaries【CON-USR-002-DEF】

The User is the human product role who provides the User's own trading capital and uses Halpha, and has final authority over product-use and capital-control decisions. A Developer performs development, validation, or release work and MAY be the Project Owner or an AI tool, but does not thereby gain the User's capital decisions or control of external accounts. Manual handling and manual takeover mean that the User acts personally through Halpha or an official trading-venue entry point; they are not new operating subjects, authority modes, or approval roles.

### Human Identity Use Requirements【CON-USR-002-REQ】

The project has exactly one human Project Owner and one human User; the same human MAY hold both roles. Co-owner, administrator, approver, watchkeeper, operator, or similar identities MUST NOT be invented for interface, engineering, or operational convenience. A required non-human runtime responsibility MUST be described by its actual function and MUST NOT receive powers exclusive to the Project Owner or User.

### Project Owner Responsibility and System-boundary Requirements【CON-USR-001-REQ】

The Project Owner decides development investment and whether the project continues. The User decides the User's total personal allocation, tolerable loss, accounts, and funding arrangements outside Halpha; Halpha does not build a corresponding decision or guarantee mechanism.

Halpha MUST accept and enforce the accounts, funds-use caps and scope, real-capital operating authority, and stop, contraction, and restoration decisions explicitly configured by the User. Halpha MUST NOT increase authority or expand scope by itself. User confirmation cannot turn unknown facts into known facts and cannot remove Halpha's responsibility for functional correctness.

## 2.3 Human Decision Sovereignty and Cognitive Safety【CON-HUM-001】

Halpha MUST preserve the User's prudent, informed, and revocable decision sovereignty. It MUST NOT use urgency, gamification, hidden defaults, selective evidence, or exaggerated AI confidence to induce trading, increase funds-use caps, or expand scope.

The User MUST be able to understand Halpha's important decisions, immediately stop new real actions, lower authority, narrow the funds-use scope, and take over through an external path. Stopping and contraction take effect immediately. Restoration, increased authority, or expanded scope requires an explicit User decision and MUST NOT be triggered automatically by profit, model updates, or AI recommendations.

## 2.4 Long-term Scope and Non-goals【CON-NGL-001】

Halpha's long-term scope is a personal trading-decision, execution, observation, and learning loop maintained by one Project Owner for one User's own capital.

Unless the project's fundamental assumptions change, the following are not development goals:

- managing, holding, or trading another person's or a client's capital;
- a multi-tenant or mass-market product, or a product that stimulates trading through engagement;
- multi-person institutional approval or enterprise organizational governance;
- competition in extremely low latency or large-scale market making;
- a general-purpose AI, plugin, or quantitative-research platform;
- complex distributed infrastructure, an institutional risk engine, heavy incident management, or enterprise security and compliance governance built for hypothetical scale.

Legal, tax, account-agreement, regulatory-compliance, market-data licensing, jurisdictional, and external funding matters are handled by the User outside Halpha and are not Halpha functions or guarantees. The Constitution MUST be reviewed before changing the capital-responsibility holder, Project Owner model, single-User model, operating model, trading timescale, or commercial nature.

---

# 3. Economic Outcomes and Product Value

## 3.1 Outcome Priority【CON-ECO-001】

Returns or Halpha's internal judgment MUST NOT automatically increase funds-use caps, expand scope, or increase real-capital operating authority. Within the User's boundary, Halpha pursues the long-term net value of the real account and treats trading judgment, execution quality, and functional correctness as core product value.

Duplicate actions, incorrect states, or unreconcilable outcomes are functional defects that MUST be fixed and MUST NOT be weakened because the capital is small or the issue is classified as risk control. When evidence is insufficient, waiting, holding cash, or no trade MAY be the correct outcome, but MUST NOT become an excuse to avoid building trading capability and product value over the long term.

## 3.2 Separation of Economic Concepts【CON-ECO-002】

### Economic Outcome Concept Definitions【CON-ECO-002-DEF】

| Concept | Constitutional meaning |
|---|---|
| Account Net Outcome | The account outcome after reconciliation, exclusion of external cash flows, and inclusion of actual trading costs |
| Investment Alpha | Excess investment outcome relative to an ex ante benchmark, after costs and the agreed risk adjustment |
| Incremental Product Value | Halpha's net contribution relative to an ex ante counterfactual, after attributable incremental development, data, and operating costs |

### Separate Evaluation Requirements【CON-ECO-002-REQ】

Halpha MUST evaluate Account Net Outcome, Investment Alpha, and Incremental Product Value separately. A result MAY be quantified only when the evidence supports the strength of the conclusion; otherwise it MUST be reported as indeterminate. Unadjusted market exposure, leverage, or general risk premium MUST NOT be called Alpha, and product outcomes that cannot be monetized reliably MUST NOT be included in net product economic value.

## 3.3 Ex Ante Evaluation and Counterfactual Integrity【CON-ECO-003】

Evaluation definitions, benchmarks, costs, counterfactuals, and uncertainty MUST be set before outcomes occur. Results MUST distinguish observed facts, counterfactuals, model estimates, and inferences. Definitions MUST NOT be changed after the fact to improve a conclusion, and model estimates or inferences MUST NOT raise funds-use caps, expand scope, or increase authority by themselves.

## 3.4 Cash, No Trade, and Product Success【CON-ECO-004】

### Cash and No-trade Outcome Requirements

Cash and no trade MUST be included in outcome comparisons and MUST NOT be treated as failure by default, but they do not eliminate risks from existing accounts, orders, positions, or external venues.

### Product Success and Failure Requirements【CON-ECO-004-REQ】

From the User's perspective, Account Net Outcome and Investment Alpha are the primary outcomes. From the Project Owner's perspective, Incremental Product Value and sustainable product success are the primary outcomes. Code, reports, pages, transaction counts, process counts, or a single profit cannot independently prove success.

A prolonged inability to produce attributable value, or a persistent failure of trading judgment, functional correctness, user experience, reliable operation, or maintainability to meet the needs of the User and Project Owner, indicates directional failure or serious deviation.

---

# 4. User-set Funds-use Caps, Scope, and Halpha Real-capital Operating Authority

## 4.1 User-set Funds-use Caps and Scope【CON-CAP-001】

### Funds-use Caps and Scope Definition【CON-CAP-001-DEF】

Funds-use caps and scope are the accounts, maximum amounts or proportions, and applicability boundaries that the User explicitly configures within Halpha after making funding decisions outside Halpha. They are the in-system upper boundary on capital Halpha may actively use, not Halpha's decision or guarantee about the User's total personal allocation, tolerable loss, or actual maximum loss.

### Funds-use Caps and Scope Requirements【CON-CAP-001-REQ】

Every Halpha real-capital operating authority and real action MUST remain within the current funds-use caps and scope and MUST NOT increase or expand them by itself. Concrete values and configuration forms are owned by lower-level design or configuration. Account separation, retained funds, and trading-venue settings are arrangements made by the User outside Halpha.

## 4.2 Simple Action Boundary【CON-CAP-002】

### Real Action Definition【CON-ACT-001-DEF】

A real action is an external operation initiated by Halpha that may cause an actual change at a real trading venue or account. Read-only observation, historical research, simulated environments, and operations independently completed by the User through an official trading-venue entry point are not Halpha real actions. Whether an initiated operation ultimately fills does not change its nature.

### Constitutional Definition of Financial-risk Control【CON-CAP-002-DEF】

Financial-risk control constrains inappropriate real actions even when Halpha operates correctly, using the User-set funds-use caps and scope, a fixed basis for the decision, and pre-action risk checks. It is not the same as action deduplication, state correctness, or outcome reconciliation.

### Real Action Boundary Requirements【CON-CAP-002-REQ】

A real action that introduces, increases, or converts risk MAY be initiated only when a fixed basis for the decision, the current funds-use caps and scope, and valid authority all support it. An action that stops, cancels, protects, or reduces existing risk MAY be grounded in an explicit User decision, but MUST NOT be used as a route to expand risk. Lower-level specifications define concrete product paths. If conformity with the boundary cannot be determined reliably, automated action MUST stop and the decision MUST return to the User.

## 4.3 Constitutional Boundary of Halpha Real-capital Operating Authority【CON-CAP-003】

This Constitution defines only the following authorization boundaries and does not define concrete authority levels, commands, or state machines:

1. **Authorization is prior and proportionate to risk:** Before Halpha initiates a real action, it MUST have valid authorization proportionate to the risk, impact scope, reversibility, and time sensitivity. Low-intensity authorization MUST NOT substitute for the authorization required by an action that increases or converts risk.
2. **There are only two authorization paths:**
   - **Manual authorization:** The User decides on a current specific action or an explicitly controlled scope. Halpha, an interface, or AI MUST NOT fabricate authorization from a human decision that has not been made.
   - **Machine authorization:** The User grants Halpha automated action capability in advance for an explicit scope and duration. Software and AI MAY act only within that scope and MUST NOT self-authorize or expand it.
3. **The paths MUST NOT be conflated:** Manual and machine authorization identify the authorizing subject and path, not an action-risk category. Operations performed by the User outside Halpha are handled as external facts and do not become Halpha authorization.
4. **Authorization is minimally necessary and traceable:** Every authorization MUST remain within the current funds-use caps and scope, limit its applicability and duration, and leave a traceable record. Efficiency MUST NOT bypass a hard boundary, and a single highest manual threshold MUST NOT block an authorized constraining action that can be shown not to increase or convert risk.

## 4.4 Highest Boundary When Critical Facts Cannot Be Confirmed【CON-CAP-004】

Critical account, order, position, or market facts that are unknown, clearly stale, conflicting, or unreconcilable MUST NOT support automated introduction, increase, or conversion of risk. Halpha MUST stop new real actions in the affected scope, show the unknown scope to the User, and preserve external manual control. Halpha MUST NOT assume that facts are safe, continue increasing risk from stale facts, or overwrite sourced external observations with derived state.

A stop, cancellation, or constraining action explicitly initiated by the User and demonstrably not increasing or converting risk SHOULD NOT be blocked by internal process. If that cannot be demonstrated, automated action MUST still stop.

## 4.5 Changes to Halpha Real-capital Operating Authority and Funds-use Caps and Scope【CON-CAP-005】

Halpha real-capital operating authority prohibits real writes by default and is constrained by accounts and funds-use caps and scope. Increased authority, increased funds-use caps, or expanded scope MUST be completed explicitly by the User and leave a simple record. Profit, a model, a strategy, AI, or the system MUST NOT trigger such a change.

Stopping new real actions, lowering authority, lowering funds-use caps, narrowing scope, and external manual takeover MUST take effect immediately and MUST NOT depend on approval, incident closure, or a complete evidence package. When trustworthy automated controls are unavailable, only an explicit manual or external safeguard MAY be used. If that safeguard is unavailable or cannot meet the required timing, the outcome MUST be to wait, stop, or make no trade.

## 4.6 Contraction and Restoration of Halpha Real-capital Operating Authority【CON-CAP-006】

When an anomaly, unknown material fact, business error, credential risk, or reconciliation difference occurs, the funds-use caps and scope MAY be narrowed, Halpha real-capital operating authority MAY be lowered, or new real actions MAY be stopped immediately.

Restoring authority that has expired, been revoked, or been contracted, or expanding authority or scope, MUST be decided explicitly by the User and MUST occur only after the immediate issue has been handled, critical external facts have been reconciled, and the scope remains controlled. Halpha MUST support decreases as well as increases and MUST NOT automatically restore authority that has expired, been revoked, or been contracted.

When Machine authorization remains valid within its original plan, account, action, duration, and cap scope and has not been stopped, revoked, or handed over, re-establishing runtime eligibility after an interruption is not restoration of invalid authority. Continuation within the original scope is permitted only when accepted lower-level design explicitly allows automatic continuation for that phase and verifiable evidence proves a unique writer, continuity of persistent state and external facts, unchanged build/configuration/credentials/account identity, reconciliation of unknown and protection responsibilities, and no replay of missed actions. Otherwise the scope MUST remain stopped for an explicit User decision. This process MUST NOT create, expand, or extend authorization.

---

# 5. Facts, Evidence, Learning, and Adaptation

## 5.1 Fact Integrity【CON-TRU-001】

Sourced external observations, Halpha action records, reconciled facts, and research, statistics, counterfactuals, and AI-derived content MUST be distinguished from one another and identify their sources. Derived content MUST NOT become an authoritative source for account facts, User-configured funds-use caps and scope, or Halpha real-capital operating authority. Fact corrections MUST preserve the original observation and its correction relationship and MUST NOT silently overwrite it.

Unresolved conflicts in critical facts MUST remain explicit and MUST stop directly affected new real actions. Real actions, material boundary changes, and human interventions MUST leave records sufficient to reconcile intent, actual outcome, and remaining external state, but an institutional evidence or tamper-proof platform is not required.

## 5.2 Functional and Implementation Validation and Economic Evidence【CON-EVD-001】

### Boundary Between the Two Questions【CON-EVD-001-REQ】

Functional and implementation validation asks whether a specific version works correctly. Economic evidence asks whether a specific trading method merits the use of capital. The two MUST NOT substitute for each other and MUST NOT be turned into a certification system disproportionate to a personal project.

### Real Validation Definition【CON-VAL-001-DEF】

Real Validation only indicates that evidence comes from a controlled real-capital environment; it is not a separate product path, Trading Plan, authority level, capital-size level, or test method. An activity using this qualifier MUST conform to an explicit objective, current funds-use caps and scope, applicable authority, and a stop boundary. The qualifier itself does not prove safety, maximum loss, Alpha, or system maturity. Lower-level specifications own the concrete activity, evidence, and acceptance method.

### Evidence Use and Validation Strength

Validation strength MUST be proportionate to capital size, degree of automation, and failure impact. Trading judgment, facts, actions, and commonly used controls involving real capital require stronger evidence; low-impact supporting capabilities use lighter validation. A single source or single profit MUST NOT automatically increase funds-use caps, expand scope, or increase authority.

## 5.3 Evidence Applicability, Advancement, and Decay【CON-EVD-002】

Evidence MUST state the conditions under which it applies. Small samples or outcomes from different conditions MUST NOT be presented as universal conclusions. Changes in code, data, models, methods, market conditions, or trading scale that affect a conclusion, as well as duplicate actions, reconciliation differences, clear business errors, or persistent instability, MUST downgrade or invalidate the relevant evidence and stop affected new real actions or require revalidation.

Halpha MAY impose stricter temporary limits automatically but MUST NOT increase or rewrite the funds-use caps and scope configured by the User. Expansion requires an explicit User decision.

## 5.4 Ex Ante Records and Failure or Invalidation Conclusions【CON-LRN-001】

Before an outcome occurs, a major judgment affecting real trading MUST retain enough of its contemporaneous basis and the applicable funds-use caps, scope, and authority for review. Review MUST NOT selectively forget failures, no-action outcomes, adverse results, manual overrides, data problems, or execution defects.

Records MUST retain only the minimum content and duration needed by high-value consumers, MUST protect sensitive information, and MUST NOT retain credentials or unnecessary sensitive source text permanently.

## 5.5 Adaptation MUST NOT Increase Funds-use Caps or Expand Scope by Itself【CON-ADP-001】

Learning, optimization, model updates, strategy generation, parameter adjustment, and remote configuration MUST NOT increase funds-use caps, expand scope, increase Halpha real-capital operating authority, or declare themselves trusted. Their own outputs MUST NOT be the sole basis for any such expansion.

Automatic adaptation MAY occur only within a limited range explicitly enabled by the User. A change beyond that range MUST remain disabled by default until the User explicitly enables it.

---

# 6. AI, Technology, Data, and Security

## 6.1 AI Trust Boundary【CON-AI-001】

Outputs from product AI and development AI are derived content that requires checking. AI MAY organize, recommend, explain, inspect, and implement, but MUST NOT be the sole source of account facts, User-configured funds-use caps and scope, increased authority, or expanded scope.

Development AI MUST NOT hold production credentials or directly change real accounts or capital. AI-generated implementations and evidence MUST be checked according to actual impact. Stopping, basic reconciliation, and external manual takeover MUST NOT depend on AI being available or correct.

## 6.2 Technology and Data Sovereignty【CON-SOV-001】

Halpha MUST retain control of, and be able to export and restore, the data and configuration necessary to preserve trading semantics, User-configured funds-use caps and scope, Halpha real-capital operating authority, critical facts, real-action state, and User control. Using mature third-party capabilities does not change this requirement or transfer the User's capital decisions.

A third party MUST NOT become a source of raised funds-use caps, expanded scope, or increased authority, a hidden dependency of stopping or external takeover, or the sole holder of necessary history. A technology boundary MUST have understandable failure impact, minimum control, data portability, and an exit path. Lower-level design determines concrete technologies and vendors.

## 6.3 Automated Non-trading Cost Boundary【CON-CST-001】

A capability that automatically incurs continuing or usage-based non-trading cost MUST remain within scope, budget, attribution, and stop boundaries approved by the Project Owner. It MUST NOT expand its budget or substitute expected returns for approval. If cost becomes unobservable or reaches a boundary, the capability MUST stop or degrade. Lower-level configuration owns the concrete values.

## 6.4 Identity, Credentials, and Least Authority【CON-SEC-001】

An external identity used for real-capital writes MUST use the least practicable authority, have limited scope, and be revocable. Trading credentials MUST NOT have withdrawal, transfer, account-administration, or self-expansion capability by default. If another high-impact capability is required, it MUST use an identity and path separate from trading writes.

Product AI, development tools, exploration environments, and ordinary development hosts MUST NOT directly hold production credentials. Credentials MUST NOT enter source code, documentation, AI context, logs, or evidence materials. Lower-level design determines concrete storage and interfaces according to actual risk.

## 6.5 Actual Impact Scope and Simple Isolation【CON-SEC-002】

Security and isolation investment MUST follow actual impact. A capability able to change a real account, User-configured funds-use caps and scope, Halpha real-capital operating authority, a critical fact, stopping ability, or external manual takeover MUST receive stronger protection and validation. A supporting capability unable to cause those effects SHOULD use lighter safeguards.

Critical single points SHOULD be kept as few as possible, and impact SHOULD be limited through least authority, simple recovery, and external manual takeover. Account and capital separation are arranged by the User outside Halpha. The project does not build institutional security governance, a trusted-computing registry, or an independent certification system.

---

# 7. Reliable Operation, Recovery, and Deactivation

## 7.1 Reliability Comes First from Simple Choices; Core Domains Ensure Action Correctness【CON-OPS-001】

### Reliable Operation, Functional Correctness, and System-risk Mitigation Responsibility Definition【CON-OPS-001-DEF】

Reliable operation is the product outcome in which core capabilities are reliably available under expected conditions. Functional correctness means that the same valid facts and configuration produce explainable decisions, and that real actions are unique, reconcilable, and do not change an external account again during offline replay. System-risk mitigation limits impact when operating conditions fail. The three MUST NOT substitute for one another.

### Reliable Operation Implementation Requirements【CON-OPS-001-REQ】

Halpha's core trading, observation, stopping, and recovery capabilities MUST operate reliably in a system maintainable by one person and SHOULD prefer mature approaches with few dependencies, clear boundaries, and easy verification. Each Halpha real action MUST have unique, recoverable processing responsibility, prevent repeated external impact, and support reconciliation with external outcomes. Lower-level design owns concrete states, retries, and technical implementation.

## 7.2 Simple Stop and Visible Degradation【CON-OPS-002】

When critical external facts, trading identity, execution, or persistence capability is unavailable or clearly unreliable, new real actions in the affected scope MUST stop, and the User MUST be shown the reason and any external state that may remain. Observation and repair capabilities that cannot change an external account MAY remain available. An alert MUST NOT replace stopping, and the project MUST NOT prebuild a complex degradation platform for low-impact failures.

## 7.3 Recovery and Independent Final Control【CON-OPS-003】

Halpha MUST NOT be the sole irreplaceable path by which the User observes accounts, revokes Halpha authority, protects capital, or regains account control. The User MUST retain final control outside Halpha's runtime, credential, and deployment failure domains.

After a restart, failure, human intervention, or identity anomaly, the affected scope MUST first remain stopped until critical external facts have been reconciled, old actions cannot repeat external effects, and runtime eligibility has been proved again. If the original Machine authorization remains valid and accepted lower-level design defines a strict evidence gate for the current phase, Halpha MAY restore runtime eligibility only within the original scope. In every other case, the User MUST explicitly restore applicable authority, continue the same task, or establish new authorization. Halpha MUST NOT continue automatically after a User stop, revocation, handover, or authorization expiry, or when the build, configuration, credentials, account identity, persistent-write continuity, or critical facts changed or cannot be proved. Credentials suspected of disclosure or loss of control MUST be revoked or invalidated. If facts or control remain unclear, the only permitted outcomes are to remain stopped or perform a constraining action demonstrably not increasing or converting risk.

## 7.4 Deactivation, Exit, and Record Retention【CON-LIF-001】

The User MUST be able to stop Halpha new real actions, revoke Halpha authority and credentials, and manage remaining accounts, orders, and positions through an external path. Exit MUST NOT depend on a complex process. Necessary configuration and records MUST be exportable, and external accounts MUST remain independently controllable.

Reuse MUST begin from a closed and controlled scope, reconcile external facts first, and then require explicit restoration by the User. The project does not require a successor identity, an institutional exit archive, or a dedicated exit platform.

---

# 8. Complexity, Technology Choices, and Development Trade-offs

## 8.1 Complexity Verifiable by the Project Owner【CON-CMP-001】

Halpha's complexity and development speed MUST NOT exceed the Project Owner's ability to understand, validate, operate, stop, take over, and recover the system. AI's ability to generate more code does not change this limit.

Design MUST account for full-lifecycle cost. Complexity MUST be invested first in trading judgment, planning, fact correctness, execution, and user experience. The complexity of supporting governance, documentation, security, and operations MUST NOT exceed their verifiable benefit to core value and hard boundaries and MUST NOT produce a system thicker than the core trading capability.

## 8.2 Real Consumers and an End-to-end Loop【CON-CMP-002】

Before expanding scope or building abstractions, the project MUST close and validate an end-to-end capability that provides actual User value in the smallest applicable scope. A shared abstraction, service, or platform SHOULD be created only after real duplication exists, semantics are stable, extraction produces a net reduction in complexity, and the boundary is verifiable.

Development trade-offs MUST prioritize core trading capability and user experience and achieve reliable operation through mature technology, simple structure, and functional correctness. Other supporting capabilities deepen only after actual bottlenecks appear. Concrete development sequence and current scope do not belong in the Constitution.

## 8.3 Minimum Correctness and Control Requirements for Real Actions【CON-CMP-003】

### Three Control Categories Definition【CON-CMP-003-DEF】

| Category | Constitutional meaning |
|---|---|
| Financial-risk control | Constrain inappropriate real actions using the User-set funds-use caps and scope, a fixed basis for the decision, and pre-action risk checks |
| Functional correctness | Ensure that User boundaries and authority are enforced correctly and that critical facts and real actions remain unique, reconcilable, and unable to produce duplicate external effects |
| System-risk mitigation | Limit the impact of system failure through least authority, simple stopping and recovery, and external manual takeover |

### Minimum Real Action Requirements【CON-CMP-003-REQ】

All three categories MUST be effective and MUST NOT substitute for one another. Implementation depth MAY be proportionate to the actual impact of a personal project. A real-action path MUST have few dependencies, explicit boundaries, reconciliation, stopping, recovery, and external manual takeover.

By default, the project MUST NOT build multi-level capital approval, a production-admission committee, an institutional risk or security platform, a formal incident process for every failure, or one state machine covering every risk category. Functional correctness MUST NOT become optional because the project or capital size is small.

## 8.4 Mature-capability Priority and Technology Introduction Threshold【CON-CMP-004】

Among qualified solutions that satisfy confirmed product semantics, functional correctness, safety boundaries, User control, and necessary data portability, Halpha MUST first evaluate and preferentially reuse existing capabilities that are mature, understandable, verifiable, and exitable. Halpha MUST NOT duplicate those capabilities merely because an existing draft, internal structure, or algorithmic detail differs from them.

If differences between an existing mature capability and the existing design affect only replaceable technical or strategy choices, lower-level design MUST contract or adjust the solution to the capability's actual semantics and revalidate the affected outcomes. The minimum self-built implementation that fills the gap MAY be retained only when existing capabilities cannot satisfy non-negotiable product semantics, functional correctness, or safety boundaries, or when no mature capability suited to the purpose exists. The same capability MUST NOT retain both third-party and self-built implementations as silent, automatic, or long-term parallel alternatives. Stopping, external manual takeover, or explicit non-support MAY be a failure outcome, but MUST NOT masquerade as a second Halpha implementation.

Technology and abstraction MAY be introduced only when they solve an observed problem, reduce full-lifecycle complexity on net relative to reuse or non-construction alternatives, the Project Owner can understand and recover them, and an exit path exists. Lower-level design and current records determine concrete capability searches, difference evidence, languages, frameworks, databases, services, vendors, and versions; they MUST NOT be specified in the Constitution.

## 8.5 AI-driven Development Boundary【CON-DEV-001】

### Basis for Complexity Judgment【CON-DEV-001-RAT】

AI lowers coding cost; it does not necessarily lower the cost of understanding, validation, integration, operation, recovery, or responsibility.

### AI-driven Development Requirements【CON-DEV-001-REQ】

Development concurrency and feature count MUST remain within the Project Owner's review capacity, system verifiability, and long-term maintenance attention. Validation strength MUST follow actual impact: core trading and User control receive stronger validation, while low-impact supporting changes use lightweight checks. The project does not require an independent certification body, formal evidence package, or heavy release approval by default.

---

# 9. Review, Revision, and Actual Use

## 9.1 Review, Revision, and Issue Handling【CON-GOV-004】

This Constitution MUST be reviewed at least every 12 months from its effective time or the last formal review. It MUST be reviewed earlier when the capital-responsibility holder, Project Owner model, single-User model, capital scale and risk, trading timescale, automation autonomy, commercial nature, Project Owner control capacity, or a major failure changes materially.

A revision MUST identify the affected principles, triggering facts, lower-level impact, migration, and authority-reduction arrangements, and the Project Owner MUST approve a uniquely identifiable complete bilingual version package. The two co-normative texts MUST be accepted, superseded, or withdrawn together. A single-language change, lower-level design, implementation, test, or operating practice MUST NOT amend the Constitution silently.

An operating problem MUST NOT be interpreted as a temporary waiver of a hard boundary. The affected capability MUST first stop, contract, or return to the User under this Constitution before the project decides that it remains valid, begins a revision, or suspends it.

## 9.2 Constitutional Effect and Real-capital Use【CON-GOV-005】

For a PROPOSED version to become ACCEPTED, the Project Owner MUST confirm that the two co-normative bodies have no known material contradiction, that principle IDs and normative bodies are unique, that normative strength and meaning are aligned, and that authority boundaries are clear, and MUST approve a uniquely identifiable complete bilingual version package.

Incomplete lower-level specifications do not prevent this Constitution from taking effect, but ACCEPTED does not prove implementation correctness and does not authorize real-capital use. A real-capital capability MAY be used only after the User-configured funds-use caps and scope, Halpha real-capital operating authority, critical facts, functional correctness, stopping, and external-takeover constraints on which that capability actually depends have been implemented and validated.

The User decides outside Halpha whether to provide trading capital, how much to provide, and when to use it. Halpha accepts only an explicit User decision to increase funds-use caps, expand scope, or increase authority and does not establish a personal-allocation approval process or uniform institutional production admission.

---

# 10. Principle Index (Non-normative)

This index only locates each principle's sole normative body and does not redefine it.

| Principle ID | Sole Body | Short Title |
|---|---|---|
| CON-GOV-001 | 1.3 | Normative authority and lower-level registration |
| CON-GOV-002 | 1.2 | Document status and effect |
| CON-GOV-003 | 1.4 | Normative terms |
| CON-GOV-004 | 9.1 | Review, revision, and issue handling |
| CON-GOV-005 | 9.2 | Constitutional effect and real-capital use |
| CON-GOV-006 | 1.6 | Co-normative language texts and language conflicts |
| CON-PRI-001 | 1.5 | Highest conflict order |
| CON-MIS-001 | 2.1 | Project mission |
| CON-USR-001 | 2.2 | Project Owner, User, and Developer boundaries |
| CON-USR-002 | 2.2 | Human identity and manual-path boundaries |
| CON-HUM-001 | 2.3 | Decision sovereignty and cognitive safety |
| CON-NGL-001 | 2.4 | Long-term scope and non-goals |
| CON-ECO-001 | 3.1 | Outcome priority |
| CON-ECO-002 | 3.2 | Separation of economic concepts |
| CON-ECO-003 | 3.3 | Ex ante evaluation |
| CON-ECO-004 | 3.4 | Cash, no trade, and success |
| CON-CAP-001 | 4.1 | User-set funds-use caps and scope |
| CON-CAP-002 | 4.2 | Simple action boundary |
| CON-CAP-003 | 4.3 | Constitutional boundary of Halpha real-capital operating authority |
| CON-CAP-004 | 4.4 | Highest boundary when critical facts cannot be confirmed |
| CON-CAP-005 | 4.5 | Changes to Halpha real-capital operating authority and funds-use caps and scope |
| CON-CAP-006 | 4.6 | Contraction and restoration of Halpha real-capital operating authority |
| CON-TRU-001 | 5.1 | Fact integrity |
| CON-EVD-001 | 5.2 | Functional and implementation validation and economic evidence |
| CON-EVD-002 | 5.3 | Evidence applicability and decay |
| CON-LRN-001 | 5.4 | Ex ante records and failure or invalidation conclusions |
| CON-ADP-001 | 5.5 | Adaptation MUST NOT increase funds-use caps or expand scope by itself |
| CON-AI-001 | 6.1 | AI trust boundary |
| CON-SOV-001 | 6.2 | Technology and data sovereignty |
| CON-CST-001 | 6.3 | Automated non-trading cost boundary |
| CON-SEC-001 | 6.4 | Identity, credentials, and least authority |
| CON-SEC-002 | 6.5 | Actual impact scope and simple isolation |
| CON-OPS-001 | 7.1 | Reliability comes first from simple choices; core domains ensure action correctness |
| CON-OPS-002 | 7.2 | Simple stop and visible degradation |
| CON-OPS-003 | 7.3 | Recovery and independent final control |
| CON-LIF-001 | 7.4 | Deactivation, exit, and record retention |
| CON-CMP-001 | 8.1 | Complexity verifiable by the Project Owner |
| CON-CMP-002 | 8.2 | Real consumers and an end-to-end loop |
| CON-CMP-003 | 8.3 | Minimum correctness and control requirements for real actions |
| CON-CMP-004 | 8.4 | Mature-capability priority and technology introduction threshold |
| CON-DEV-001 | 8.5 | AI-driven development boundary |
