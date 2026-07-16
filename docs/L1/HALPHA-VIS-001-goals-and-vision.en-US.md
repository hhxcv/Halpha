# Halpha Goals and Vision

**Document ID:** HALPHA-VIS-001  
**Version:** v1.4.0  
**Document Status:** ACCEPTED  
**Level:** L1-B  
**Language Edition:** en-US  
**Joint Normative Set ID:** HALPHA-VIS-001@v1.4.0+20260715T190414+0800  
**Paired Text:** HALPHA-VIS-001-goals-and-vision.zh-CN.md  
**Joint Set Registry:** HALPHA-VIS-001-goals-and-vision.bundle.yaml  
**Effective Time:** 2026-07-15T19:04:14+08:00  
**Parent Documents:** HALPHA-CON-001 v2.9.0; HALPHA-DOC-001 v1.9.0  
**This Document Governs:** long-term product positioning, the target user (one User), problems and value, competitive boundaries, capability scope, macro capability dependencies, non-goals, and signals of directional failure  
**This Document Does Not Govern:** redefinition of L0; specific workflows, runtime actors, interfaces, modules, states, technology, or current implementation
---

# 1. Product Identity and Long-Term Use Context【VIS-IDN-001】

## 1.1 Inherited Long-Term Product Positioning

This document does not redefine Halpha, the User, the Project Owner, or the Developer. Within the boundaries of `CON-MIS-001` and `CON-USR-001`, the long-term product positioning is:

> Halpha is a personal trading decision, execution, and learning system in which the User invests trading capital and which the User uses. It improves the User's real trading outcomes through higher-quality market judgment, strategies, plans, convenient interaction, reliable execution, and continuous learning. The Project Owner evaluates product success against commensurate development and maintenance cost.

## 1.2 Basis for the Long-Term Design【VIS-IDN-001-RAT】

The long-term product positioning is based on this use context:

- The User invests the User's own trading capital and bears the trading outcomes while using discretionary judgment, event analysis, and quantitative research.
- Trading capital, construction resources, and the long-term maintenance burden are all at an individual scale and do not presume an institutional team, infrastructure, or organizational process.
- Markets are intensely competitive and continually changing; obvious opportunities are exploited quickly, and historical effectiveness decays.
- The User has no dedicated research, execution, risk, or operations team. Available time is limited and often fragmented; the User will observe cautiously and intervene frequently early on and MAY pay less attention as the product matures.
- The User understands basic trading concepts, accepts necessary learning cost, and expects professional but not needlessly burdensome analysis, planning, and control.
- The User is willing to state economic hypotheses, principal counterevidence, invalidation conditions, risk boundaries, plan conditions, and evaluation methods in advance and will also use exchanges, professional charts, news, data, research environments, and general-purpose AI tools.

## 1.3 Product Identity Requirements【VIS-IDN-001-REQ】

The product MUST use personal use as its design baseline and MUST NOT require the User to program, maintain data pipelines, handle internal state machines, or read system logs. Complexity MUST remain within what the User and Project Owner can understand, validate, operate, take over, recover, and exit. The product always serves the trading capital invested by one User; it does not target multiple users, multiple institutions, client-fund processes, or unattended operation that replaces User judgment.

Product identity does not change with the project stage. L4 records actual markets, venues, accounts, instruments, time horizons, and the current stage. A capability adjustment that remains within the competitive boundary in section 5.3 and is not an expansion under `CON-NGL-001` does not require a change in product identity. An expansion that changes the party responsible for capital, the user model, operating model, trading time scale, commercial nature, or competitive structure MUST first be reviewed under the Constitution.

# 2. Real Problems to Solve【VIS-PRB-001】

## 2.1 Problems and Basis for Judgment【VIS-PRB-001-RAT】

### Abundant information does not directly yield a judgment about capital use or a real action

Market data, news, on-chain information, research views, and model results continue to increase. The difficulty is not acquiring more content; it is identifying which changes matter to the current account, positions, capital use, hypotheses, and candidate edges while retaining counterevidence, unknowns, and invalidation conditions.

### A person cannot research and watch continuously

Valuable conditions may appear while the User is offline, and candidate edges need repeated updating and falsification. Requiring continuous browsing, research, and market watching converts a missing system capability into a permanent human-duty burden.

### Good judgment can be destroyed by a poor plan and poor execution

Changing a thesis at the last moment, chasing price, submitting duplicate orders, ignoring costs, failing to protect a partial fill, or failing to recheck the market and account after a trigger can consume an already limited edge.

### Real outcomes do not naturally become competitive evidence

Fills, non-triggers, expirations, rejections, manual interventions, protection, and no-trade outcomes are often scattered across tools. Without ex ante hypotheses, evaluation methods, actual costs, real-action evidence, and account reconciliation, judgment, signals, execution, Beta, leverage, luck, and Halpha's contribution cannot be distinguished.

### AI amplifies both research productivity and false edge

AI can rapidly generate explanations, strategies, and code; it can also accelerate data leakage, overfitting, selective narratives, and complexity that is difficult to validate. Multiple conclusions from AI systems sharing the same sources do not constitute independent evidence, and AI output volume is not competitiveness.

### Apparent profit is easily mistaken for Alpha

Market Beta, leverage, general risk premia, survivorship bias, ex post changes in measurement, a few extreme trades, uncounted costs, and luck can all produce attractive results.

### Edge is weak, conditional, and subject to decay

A real edge usually applies only to particular market regimes, assets, horizons, capital size, liquidity, and cost conditions. It may disappear as participants crowd in, markets adapt, data changes, or execution costs rise. Finding one strategy is not the end state; degradation and replacement are normal product problems.

### A gap exists between research and real capital

Data availability, fill assumptions, liquidity, and fees in research differ from real operation. The product MUST confront this difference and MUST NOT use simulated results as a substitute for real outcomes.

## 2.2 Product Requirements Derived from the Problems【VIS-PRB-001-REQ】

- Research, plans, User decisions, execution, and outcomes MUST remain relatable; FLOW and subordinate design define the specific linkage.
- The financial-risk controls, functional correctness, and system-risk mitigation defined by `CON-CMP-003` MUST be evaluated separately. A result in one category MUST NOT substitute for either of the other two.
- Halpha MUST identify genuine excess investment outcomes under ex ante benchmarks, costs, risks, and applicability scope.
- An edge that cannot persist with point-in-time-correct data, out-of-sample or forward conditions, and real execution constraints cannot become capital competitiveness.

# 3. Sources of Product Value【VIS-VAL-001】

## 3.1 Definition of Product-Value Categories【VIS-VAL-001-DEF】

Halpha has the following eight long-term product-value categories. They describe outcomes the product is to improve; they do not represent modules, runtime actors, or construction stages.

| Value Source | Change the Product Is to Produce |
|---|---|
| Trading and profit value | Form more competitive, falsifiable, and scoped views and strategies, improving opportunity selection, entry and exit, and capital-use outcomes |
| Judgment and planning value | Make facts, hypotheses, counterevidence, unknowns, and invalidation conditions clearer and turn judgment into an executable, adjustable plan |
| Execution value | Cause User decisions or authorized plans to be carried out uniquely and reconcilably within explicit boundaries, reducing omissions, delay, ambiguity, duplication, slippage, and unplanned intervention |
| UX value | Let the User understand state, compare options, act, stop the system, and take over manually in few steps, reducing error and wasted attention |
| Stability value | Keep core capabilities reliable under expected conditions through mature technology and a simple structure, without treating the number of platforms or infrastructure components as proof of value |
| System-risk mitigation value | Limit impact when a host, dependency, network, credential, or runtime environment fails while preserving stop, recovery, and external takeover |
| Learning value | Use real plans, costs, and outcomes to determine whether evidence still supports an edge, eliminate poor practices, and improve the next judgment |
| Financial-risk control value | Even when the system operates correctly, enforce the User-configured fund-use limit and scope and necessary pre-action checks so that Halpha does not exceed the allowed scope |

“Execution,” “stability,” “system-risk mitigation,” and “financial-risk control” are distinct value categories. Unique real actions, duplicate prevention, correct state, and result reconciliation are basic functional correctness and MUST NOT be weakened because of a stage or capital size. Only L4 records the current implementation depth of each category.

## 3.2 Product-Value Requirements【VIS-VAL-001-REQ】

Halpha MUST target long-term net capital value in the real account. Where comparative material commensurate with the strength of the conclusion exists, it MUST evaluate investment Alpha and incremental product value separately; when the material is insufficient, the result remains indeterminate. Product investment order MUST conform to `CON-PRI-001` and `CON-CMP-001`; supporting control, governance, or platform construction MUST NOT crowd out trading judgment, planning, execution, UX, and reliable operation.

Market profit is not a natural consequence of putting a system online, adding AI, or executing according to a specification. Long-term profitability requires Halpha to sustain a competitive advantage over market benchmarks and available alternatives after costs and risks and to falsify, down-weight, and replace that advantage promptly as it decays.

Planning, execution, UX, and stability MAY produce incremental product value before investment Alpha has been established. If, over the long term, economic evidence remains insufficient to support an investment-Alpha conclusion for a bounded applicability scope, Halpha's core profitability claim remains unestablished. Account net outcome, investment Alpha, and incremental product value retain the meanings in `CON-ECO-002` and `CON-ECO-003`. Market appreciation, leverage, or short-term profit MUST NOT automatically be attributed to Halpha; waiting, cash, and no trade MAY still be correct capital outcomes.

# 4. Product Operating Claims【VIS-OPS-001】

## 4.1 Product-Participant Boundary

### Participant Boundary【VIS-OPS-001-DEF】

Human roles and their capital, construction, and development responsibilities are inherited entirely from `CON-USR-001` and `CON-USR-002`; VIS does not redefine them. At the product level, only these relationships are fixed: the User makes product-use and capital-control decisions; the Project Owner decides project construction and bears maintenance cost; Halpha provides continuous analysis, planning, observation, execution, and learning within accepted rules and User decisions; and external systems and tools provide facts, computation, research, or venue capabilities. ARC, SYS, and subordinate design own runtime actors, processes, and module boundaries.

### Participant Requirements【VIS-OPS-001-REQ】

Development activity and output from an external tool or AI MUST NOT be treated as a User decision, an account fact, or authority to act outside an existing boundary. Halpha MUST continually improve strategy, analysis, planning, execution, stability, and UX quality. “The User bears the trading outcome” and “the Project Owner bears construction responsibility” MUST NOT justify ignoring an obvious business error, functional defect, or poor experience.

## 4.2 Semi-Automated Execution of User Trading Plans Is a Valid Long-Term Form

### Basis for Selecting the Semi-Automated Form【VIS-OPS-001-RAT】

A User trading plan MAY originate in the User's own judgment or incorporate strategies and analysis generated or improved by Halpha. Machine watchkeeping, event triggers, and User confirmation can form a complete product. For highly uncertain or weakly evidenced opportunities, per-action human judgment MAY remain preferable to system-initiated action over the long term. FLOW, CAP, TRADEPLAN, and EXE define specific authorization paths, time limits, and action conditions.

## 4.3 Halpha Real Actions Must Conform to the User-Configured Fund-Use Limit, Scope, and Authority

Halpha MUST NOT raise the fund-use limit, expand its scope, increase real-capital operating authority, or restore a stopped capability merely because a strategy is stronger, profit is higher, operation is more automated, or a stage is more mature. Halpha does not decide the User's total investment outside the system; the fund-use limit and scope and real-capital operating authority inside the system retain their L0 and CAP meanings.

Halpha's long-term product form permits the User to confirm a current action and also to enable explicit and bounded in-plan action in advance. Contraction actions such as protection, cancellation, and risk reduction MUST NOT be broadened into a capability to add risk. Only FLOW and the applicable L2/L3 own action eligibility, authorization, states, checks, and reconciliation; VIS does not restate them.

## 4.4 Product Boundary in a Multi-Tool Environment

Exchanges, professional charts, news, data, research environments, and general-purpose AI MAY provide mature observation, computation, venue operation, research, and explanation. Halpha's product responsibility is to preserve continuity among judgment, plans, account meaning, action provenance, outcomes, and evidence across those tools and to let the User understand, query, stop, and take over. Aggregated display does not transfer User decision authority, the authority of external account facts, or the semantic ownership of subordinate domains.

Mature external tools are preferred when they can perform a task independently without breaking high-value context. Halpha adds only the necessary capability when external tools force the User to reconstruct repeatedly the context needed for a trading decision or cannot close the continuity among plan, action, reconciliation, and learning. FLOW defines specific tool handoffs; ARC and subordinate design define technical choices.

## 4.5 Professional Depth Does Not Mean Daily Complexity

Halpha maintains one set of trading and capital semantics across every interaction mode and retains advanced analysis and bounded customization appropriate to the User's use context. Professional quality comes from accurate expression of facts, evidence, risks, authority, unknowns, and outcomes—not from information density, configuration count, technical terminology, or continuous demand on attention.

Halpha SHOULD absorb internal complexity through inherited context, reasonable defaults, templates, and automation; normal use SHOULD NOT require the User to operate internal mechanisms. Simplification MUST NOT hide material risk, counterevidence, unknowns, the fund-use limit and scope, real-capital operating authority, system capability scope, or real outcomes, and MUST NOT make the User's final trading judgment or decide personal fund arrangements outside the system. FLOW and subordinate design determine information hierarchy and interaction form.

# 5. Product Differentiation, Competitiveness, and Building Alpha【VIS-ADV-001】

## 5.1 Product-Level Derived Terminology and Use

### Candidate-Edge Definition【VIS-ADV-001-DEF】

Account net outcome, investment Alpha, and incremental product value use exactly the meanings in `CON-ECO-002` and `CON-ECO-003`; VIS does not redefine them.

A **candidate edge** is a product-level hypothesis with a falsifiable economic mechanism, applicability scope, cost assumptions, and invalidation conditions. It is not investment Alpha. Economic evidence supporting an investment-Alpha conclusion continues to be judged under the benchmark, cost, risk adjustment, evaluation method, conclusion strength, applicability scope, and validity status defined by L0 and ALP. No separate product-level evidence name is introduced.

### Requirements for Using Derived Terminology【VIS-ADV-001-REQ】

A candidate edge is not a permanent property or return guarantee. A backtest, one profitable outcome, or a product narrative cannot by itself strengthen an economic-evidence conclusion.

## 5.2 Basis for Choosing a Personal Quantitative Direction【VIS-ADV-001-RAT】

Small capital, one User, and AI do not constitute a general advantage. Compared with professional institutions, Halpha ordinarily lacks comparable data and access, infrastructure, specialization, operational redundancy, capital, and trading-cost advantages. General-purpose AI is also available to other participants and is not itself a moat.

Possible sources of asymmetry are that personal capital need not accommodate institutional scale and MAY select only a few opportunities while holding cash for long periods; one User has lower coordination cost; User-specific knowledge, judgment, and real outcomes can accumulate over time; AI can reduce the fixed cost of research, development, comparison, and falsification; and the system can observe continuously and execute repetitive work so that limited and fragmented human attention is concentrated on critical judgment.

These are conditions worth testing, not existing Alpha. AI can amplify research and operating capability but cannot remove constraints in information, capital, infrastructure, and real execution. A more rigorous product process does not automatically prove investment Alpha.

## 5.3 Competitive-Scope Requirements【VIS-ADV-001-REQ-002】

### Competitive Structures with a Realistic Opportunity

Halpha gives priority to investigating opportunities with these structures:

- The opportunity applies only at smaller capital scale or matters to personal capital but cannot readily accommodate institutional capital or cover institutional fixed cost.
- Selectivity itself has value: the User MAY focus narrowly, wait, or not trade instead of deploying trading capital continuously.
- A candidate edge MAY arise from User-specific context, cross-source synthesis, rapid falsification, and accumulated real outcomes rather than a single public signal that can be copied cheaply.
- AI can reduce an individual's fixed research and development cost and preserve output in a proprietary context and evidence loop.
- The candidate edge MAY remain viable after realistic information availability, decision and execution constraints, cost, liquidity, and risk.
- Research, operation, maintenance, takeover, and exit can be sustained by one User and the Project Owner.

Within these conditions, Halpha SHOULD expand its verifiable capability scope and MUST NOT permanently exclude a holding horizon, trading frequency, or strategy family merely because early project capability is limited. Each specific opportunity still MUST be falsified and evaluated under ex ante definitions; it cannot be inferred directly from the project's personal nature or assumptions about institutional behavior.

### Structurally Disadvantaged Competitive Directions

The following structures offer Halpha almost no realistic opportunity and are not product-capability directions:

- Outcomes are determined mainly by faster response, better priority, greater capital, or lower funding or trading cost.
- The opportunity depends on proprietary data, access, infrastructure, continuous operation, runtime redundancy, or synchronized coordination that a personal project cannot reasonably obtain or sustain.
- Public information and general-purpose AI make the opportunity cheap to copy, and Halpha has no additional User-specific context, evidence accumulation, or feedback advantage.
- The opportunity appears viable only when real cost, liquidity, execution uncertainty, temporary exposure, or the configured fund-use limit and scope are ignored.
- Producing sufficient economic value would require institution-scale coverage, action burden, or maintenance complexity.

Holding period, trade count, and strategy label are not independent criteria. No opportunity MAY be pursued by automatically raising the fund-use limit, expanding its scope, weakening reconcilability, or surrendering the User's final control. L1 sets only the stable competitive boundary and neither approves nor permanently excludes a specific strategy. Applicable L2, L3, and L4 respectively own strategy principles, detailed contracts, and current support scope.

# 6. Long-Term Product Capability Scope【VIS-CAP-001】

## 6.1 Capability Scope

The following are long-term capabilities the product MUST be able to combine incrementally according to actual value. They do not represent software modules, runtime actors, or equal construction investment.

1. **Market observation and real-time intelligence:** Identify market changes, opportunities, and risks relevant to the User's current attention and capital use without turning an information stream into pressure to trade.
2. **Strategy research and validation:** Organize hypotheses, mechanisms, alternative explanations, counterevidence, and real constraints, producing falsifiable strategies and eliminating invalid hypotheses.
3. **Trading plans and rehearsal:** Turn judgment into a complete plan that can be adjusted, stopped, and checked before action.
4. **Trade execution and position management:** Reliably handle in-plan actions, protection, adjustment, exit, and exceptional responsibility while keeping outcomes reconcilable.
5. **Account and trading facts:** Let the User understand current and historical account outcomes, external activity, unknown facts, and outstanding responsibility while keeping simulated and real environments distinguishable.
6. **Review, analysis, and learning:** Connect hypotheses, plans, actions, costs, and outcomes and distinguish the contributions of strategy, planning, execution, interaction, and external factors.
7. **User UX and pending matters:** Provide clear entry points for viewing, comparison, decisions, stopping, takeover, and deep work under different time conditions.
8. **Financial-risk control and real-capital operating authority:** Enforce the User-configured fund-use limit and scope, real-capital operating authority, and proportionate pre-action checks without deciding the User's total investment outside the system.
9. **System-risk mitigation:** Limit the impact of system failure or loss of control through simple isolation, stopping, recovery, and external takeover.

## 6.2 Capability-Implementation Requirements【VIS-CAP-001-REQ】

These capabilities need not all exist in the same stage and need not be built as separate modules. Capabilities required by a current consumer MUST form a usable loop; remaining capabilities MAY retain only a boundary, use an external tool, be handled manually, or be explicitly unsupported.

Proportionate stability is a common quality constraint, not a separate User work domain or high-investment product line. Mature components, few dependencies, and simple deployment are preferred; core data and execution semantics MUST ensure correct real actions. AI MAY generate hypotheses, research implementations, and counterevidence, but it cannot be economic evidence, change an evaluation definition, delete failures, or strengthen its own conclusion on the basis of its own output.

# 7. Product-Value Dependencies That Must Be Connected【VIS-LOOP-001】

Halpha's product value depends on these relationships holding together:

~~~text
Trustworthy facts and falsifiable judgment
↔ Executable plans and clear human choice
↔ Bounded, reliable, stoppable action or no action
↔ Reconcilable outcomes and real costs
↔ Attribution, learning, elimination, and replacement
~~~

These relationships express only mutual value dependencies. They do not prescribe processing order, participant handoffs, authorization paths, object states, tools, or pages. FLOW owns actual paths, and the applicable L2/L3 own detailed semantics. Every actual path MUST allow waiting, rejection, cash, no trade, stopping, or manual takeover to be a valid outcome and MUST NOT force action merely to close a diagram.

# 8. Outcomes the User Should Obtain【VIS-OUT-001】

Halpha SHOULD enable the User to:

- Understand the accounts, funds, orders, positions, protection, differences, and unknowns relevant to a trading decision.
- Act through a plan containing a thesis, counterevidence, invalidation conditions, risk, and the fund-use limit and scope.
- Complete frequent analysis, decisions, review, stopping, and manual takeover in few steps.
- Receive prioritized reminders and clear state both while observing cautiously early on and while paying less attention as the product matures.
- Experience reliable core operation, understandable recovery after failure, and no duplicated real action.
- Explain real costs, outcomes, and product contribution and honestly eliminate invalid candidate edges and strategies.
- Form Alpha for a bounded applicability scope when evidence supports it and down-weight, pause, and replace a decaying edge.

The first six outcomes MAY create incremental product value before investment Alpha exists. No outcome automatically raises the fund-use limit, expands its scope, or increases Halpha real-capital operating authority.

# 9. Long-Term Capability Dependencies【VIS-PHS-001】

## 9.1 Capability-Coordination Requirements【VIS-PHS-001-REQ】

The core trading and UX loop MAY be built in parallel with Alpha research and forward evidence; the two kinds of real use MAY expose problems in each other. Research MUST NOT treat complex infrastructure as a prerequisite. Execution and UX MUST be validated by real business scenarios. Halpha MUST NOT automatically initiate a profit-seeking real action that introduces, increases, or transforms risk before a complete plan, functional correctness, User capital control, and economic evidence proportionate to that action exist. Contraction actions that protect, cancel, or reduce existing risk remain governed by the permitted sources and unified action chain in FLOW; this requirement MUST NOT reinterpret them as risk-increasing actions. Proportionate stability is obtained with the core chain rather than through a parallel stability product line.

# 10. Ownership of the Current Construction Order【VIS-EVO-001】

## 10.1 Construction-Order Requirements【VIS-EVO-001-REQ】

Only the current L4 plan records the current stage, stage identifier, milestone content, completion state, and next step. In that plan, the Project Owner orders work by trading value, UX, actual failures, cost, dependencies, and maintenance capacity. Feature count MUST NOT represent progress, and a stage status MUST NOT raise the fund-use limit, expand its scope, or increase real-capital operating authority.

# 11. Long-Term Non-Goals and Constraints Shared by All Stages【VIS-NGL-001】

## 11.1 Long-Term Non-Goals

This document inherits all project-level non-goals in `CON-NGL-001` and does not redefine them. In addition, these product forms are not long-term Halpha objectives:

- Beginner trading education, trade calls, guaranteed returns, social copy trading, or replacing the User's final responsibility for accounts, positions, and capital use.
- A full-time trading workstation that requires continuous all-day operation across multiple screens.
- A comprehensive news aggregator, general-purpose replacement for professional charting, or content-consumption information terminal.
- A general-purpose multi-venue trading terminal, bot, or strategy marketplace that replaces real trading venues.
- An automation platform that lets arbitrary scripts, temporary models, external alerts, or AI output connect directly to real capital.
- An institutional risk engine, multi-level production admission, heavyweight incident process, enterprise security platform, or governance system requiring a dedicated team.
- Proving success by trade count, strategy count, backtest count, alert count, code volume, or feature count.

## 11.2 Constraints Shared by All Stages

- Each stage closes real value only within bounded markets, accounts, strategies, and data. Halpha does not decide the User's total investment outside the system.
- Mature tools are preferred for horizontal professional capabilities. Halpha adds only product capabilities needed to preserve continuity among judgment, plans, actions, reconciliation, and evidence.
- Account facts, actual costs, and reconciliation MUST NOT be deferred. A candidate edge MUST allow falsification, down-weighting, and exit.
- L1 breadth describes the long-term value loop and prevents responsibility omissions; it does not promise equal deepening, automation, or investment across domains. L4 records current depth and support scope. Horizontal business responsibilities and vertical constraints need not become separate modules.
- Complexity and maintenance attention go first to ALP, TRADEPLAN, DAT, EXE, and UX. The individual and combined burden of CAP, SYS, ENG, security, governance, documentation, and other supporting capabilities MUST NOT exceed their actual benefit to the core business or create a system thicker than the core trading chain.
- A domain MAY control complexity by narrowing support scope, reducing variants and generalization, or using manual or external implementation. Functional correctness, stopping, reconciliation, and the User's final control on a supported path MUST NOT be weakened as a result.
- An idealized loop MUST NOT justify prebuilding institutional processes, platforms, or infrastructure. A security claim that persistently crowds out trading capability, UX, and reliable operation is itself a directional failure.

# 12. Signals of Directional Failure【VIS-FAL-001】

The direction or its claims SHOULD be reviewed or narrowed when any of these conditions persists:

- Outcomes are explained mainly by Beta, leverage, incidental trades, or uncounted costs, while forward evidence continually disappears.
- Failures, search scope, adverse outcomes, and real execution differences are not retained and explained.
- A candidate edge lacks a mechanism, applicability status, capital-size and liquidity boundary, cost, or invalidation condition.
- Trading judgment, plans, or strategies remain frequently wrong over the long term and produce no profitability-based competitiveness.
- Core execution, data, UX, or stability problems continually cause wrong actions, missed opportunities, or a high manual burden.
- Halpha repeatedly rebuilds mature horizontal tools without creating continuity among plans, actions, reconciliation, and evidence.
- CAP, ENG, security, governance, or incident processes become more complex than the core business and continually slow value delivery.
- Routine maintenance and attention cost remain higher than judgment, execution, UX, stability, and learning value over the long term.
- Over the long term, the product can prove only recordkeeping and discipline value and cannot form Alpha evidence for any bounded applicability scope.

The last condition means that the Alpha claim remains unestablished; it does not negate other product value already created.

# 13. Handoff to Subordinate Design【VIS-HOF-001】

HALPHA-FLOW-001 MUST turn this document's value dependencies into repeatable product-level paths covering action, no action or waiting, unknown facts, failure, stopping, manual takeover, recovery, and end, and MUST make handoffs among Halpha, the User, and external tools explicit. FLOW MUST NOT treat section 7 as fixed steps or an object state machine.

HALPHA-ARC-001 MUST prioritize support for replaceable Alpha and competitiveness capabilities, smooth UX, reliable data and execution, and personally maintainable stable operation obtained through mature components, a simple topology, and few dependencies. The real-action path MUST implement financial-risk control, functional correctness, and system-risk mitigation separately. Evidence from the complete chain MUST demonstrate actual support scope; strategy name, holding period, document completion, or stage name MUST NOT be used to infer it.
