# Halpha Documentation Architecture

**Document ID:** HALPHA-DOC-001  
**Level:** L1-A  
**Language Edition:** en-US  
**Paired Text:** HALPHA-DOC-001-documentation-architecture.zh-CN.md  
**Parent Documents:** HALPHA-CON-001  
**This Document Governs:** document levels, responsibilities, relationships, formats, and usage rules  
**This Document Does Not Govern:** the product, workflows, technology, or current implementation

---

# 0. Overall Structure【DOC-STR-001】

## Definition of the Document-Level Structure【DOC-STR-001-DEF】

~~~text
                         L1-A Documentation Architecture
                         (documentation management only)
                                      │
L0 Constitution → L1-B Goals and Vision → L1-C Core Workflows and User Journeys
                                      ↓
                    L1-D Overall Technical Requirements and Architecture
                                      ↓
                    L2 Domain-Critical Content and Design Principles
                                      ↓
                      L3 Long-Term Stable Detailed Domain Design
                                      ↓
                      L4 Current Implementation and Facts
~~~

## Requirements for Using the Levels【DOC-STR-001-REQ】

Only three rules apply:

1. A lower level MUST conform to a higher level, and a topic MUST be defined only once at the highest level that owns it.
2. L0–L3 define what ought to be; L4 records what is currently being built and what is actually true.
3. A design change MUST first amend the document that owns the meaning, after which the affected downstream material MUST be reviewed.

---

# 1. Level Positions and Responsibilities【DOC-LVL-001】

Levels are distinguished first by the design meaning they own, not by time. “Long-term” and “current” help determine whether a design is stable or has entered delivery; they do not create a separate level responsibility.

## 1.1 Level Position, Sole Responsibility, and Delivery Distinction【DOC-OWN-001-DEF】

| Level | Core Position | Sole Responsibility |
|---|---|---|
| L0 | Project-level principles | Defines the long-term mission, highest boundaries, non-bypassable principles, and highest-order tradeoffs. |
| L1 | Overall principles | Separately defines the long-term direction, principles, and evolution conditions for documentation, product, core paths, and overall technology. |
| L2 | Domain-critical content | Defines each domain's critical problem, goals, critical capabilities, responsibility boundaries, and design principles. Horizontal core-business composition and vertical domains describe responsibility shape without changing this duty. |
| L3 | Long-term stable detailed domain design | Based on L2, defines the module boundaries, interfaces, states, failure outcomes, tests, and component-use contracts that current consumers need to reuse. It MAY limit design scope but does not own current exact versions, configuration, progress, or enablement state. |
| L4 | Current implementation and facts | Records the current objective, scope, necessary sequence and dependencies, exact versions and instance choices, configuration, progress, direct validation results, known limits, and actual facts. |

L0–L3 form long-term reusable principles, domain content, and detailed designs. L4 records current applicability, implementation objectives, and actual results; it MUST NOT add or alter stable L0–L3 rules. Current implementation identifiers, scope, sequence, progress, and validation results are recorded only in L4.

## 1.3 Dependency Order of L1【DOC-L1-001】

The four L1 documents are established and maintained in this semantic-constraint order:

1. HALPHA-DOC-001-documentation-architecture establishes the document form.
2. HALPHA-VIS-001-goals-and-vision establishes long-term product objectives and direction.
3. HALPHA-FLOW-001-core-workflows-and-user-journeys selects the long-term core paths for achieving those objectives.
4. HALPHA-ARC-001-technical-requirements-and-architecture selects the long-term overall technical solution supporting those paths.

Each later document MUST conform to the earlier ones, while product, workflow, and technical meanings remain separately owned. The documents MAY be drafted in parallel; modification and citation MUST follow this constraint order and read the direct parent.

## 1.4 Use of L2–L4【DOC-L24-001】

### Definitions of L2–L4 Objects and Classifications【DOC-L24-001-DEF】

- **L2 stable-semantic responsibility map:** every stable meaning left by L1 for lower-level detail has one explicit L2 semantic owner. It describes responsibility coverage, not equal design or implementation.
- L2 always states sole responsibility, exclusions, and failure boundaries, and adds only objects and rules that a current consumer will use. Common lifecycles or reusable rules are extracted only after multiple real consumers repeatedly need them. No extra state or upgrade workflow is created.

L2 uses two independent responsibility dimensions:

| Shape | Governs | Does Not Govern |
|---|---|---|
| Horizontal core-business composition | A continuous business responsibility, the full lifecycle of its objects, decision authority, and adjacent handoffs; one or more modules MAY implement it | Repetition across every business area of the same data, interaction, architecture, engineering, or operational requirements |
| Vertical domain | A common constraint, quality, or technical responsibility that crosses business compositions and modules | Redefinition of horizontal business objects, business decisions, or their lifecycles |

L2 divides stable responsibility by business domain or common constraint, not by software module. Module boundaries belong to L3 under SYS constraints for system composition and runtime boundaries; L2 supplies only the stable business meaning and responsibility boundary that a module MUST implement.

L3 has two types. A `DOMAIN` L3 names one primary semantic owner and precisely implements its L2 meaning. An `ORCHESTRATION` L3 names a coordination owner and owns only necessary identity, ordering, responsibility handoffs, and completion aggregation. Specific third-party libraries or frameworks adopted for the long term belong to the corresponding module's L3 implementation solution, but a third party does not acquire ownership of Halpha product semantics, facts, or decisions.

L4 uses these record types:

| Type | Recorded Content |
|---|---|
| Current implementation | Objective, scope, necessary sequence and dependencies, blockers, progress, and direct validation results |
| Facts, instances, and configurations | Source and time, active versions, exact dependency versions and build identifiers, deployment, current parameters, and platform-validation results |
| Support decisions | Real consumers, currently supported and unsupported scope, necessary rationale, and dated current summaries |

### Requirements for Using L2–L4【DOC-L24-001-REQ】

L2 MUST first state the critical domain problem, sole responsibility, exclusions, and failure outcome, then add the objects, decisions, handoffs, and acceptance basis required by current consumers. Domains in the responsibility map need not have symmetric length, object counts, or implementation investment. An unselected capability MAY remain manual, external, or explicitly unsupported.

Before adding a rule, object, or common lifecycle, state the current consumer, the decision or failure outcome it changes, why a smaller solution is insufficient, the personal maintenance cost, and the deletion condition. Symmetry, tidy documents, and future possibility are not reasons. L4 records only current support scope, actual choices, and results.

Each stable meaning has one semantic owner. Other L2 domains MAY declare input conditions, consumption, and behavior when the input is absent, but MUST NOT duplicate the owner's rules, state system, or full workflow. A producer defines its output; a consumer defines its intake. Documents MUST NOT form an all-to-all handoff network.

A design crossing multiple L2 domains does not automatically require an orchestration L3. Use a domain L3 plus direct dependencies by default. Use `ORCHESTRATION` only for a recurring cross-domain lifecycle with a stable identity that no current domain can own.

Every L3 MUST declare its type and semantic owner, list direct dependencies and applicable vertical constraints, trace primary business meanings and cross-domain requirements, and turn existing L2 principles into stable detailed design. Actual consumers decide whether to draft or extend a design; current implementation identifiers, scope, construction order, progress, and validation results MUST NOT enter L3. If implementation needs a stable rule absent from L2, amend the owning L2 first.

After ARC and ENG capability discovery and difference classification, an L3 MAY record a specific third-party library or framework as the module's long-term implementation solution. It governs how Halpha invokes that component, its inputs and outputs, fact authority, necessary transformations, failure outcomes, compatibility boundaries, and any strictly necessary minimal supplement. Exact versions, build identities, current configuration, target-operating-system and license checks, enablement state, and actual validation results are recorded only in L4.

When a third-party library fully provides a module's internal capability, its L3 primarily states Halpha's usage, boundaries, failures, and exit path. It MUST NOT reproduce vendor-internal classes, algorithms, caches, state machines, network lifecycles, or data structures, and MUST NOT invent a Halpha internal implementation for document symmetry. An L3 MUST NOT retain third-party and self-built implementations as silent, automatic, or long-term parallel alternatives. When the component is unavailable, use stopping, external manual takeover, or explicit non-support as permitted by higher-level rules.

The sole entry point for the current implementation plan is:

~~~text
docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml
~~~

It records current scope, progress, configuration, and validation results. L4 MUST NOT alter L0–L3. Missing records mean current state is UNKNOWN.

---

# 2. Document Format and File Locations【DOC-FMT-001】

## 2.1 Naming【DOC-NAM-001】

Normative files use:

~~~text
HALPHA-<TYPE>-<NUMBER>-<ENGLISH-SHORT-TITLE>.<LANGUAGE>.md
~~~

- `HALPHA-<TYPE>-<NUMBER>` is the stable document ID and identity.
- `ENGLISH-SHORT-TITLE` uses lowercase ASCII kebab-case to aid navigation; it does not determine identity.
- All co-normative language texts use the same English short title.
- A minor title wording change does not require renaming. A material responsibility change SHOULD trigger evaluation of a new document ID.
- `LANGUAGE` uses a BCP 47 tag such as `zh-CN` or `en-US`.

### Document Type Codes

Type codes MUST use the unique spellings below. They are case-sensitive parts of document identity; an alternate abbreviation for the same English meaning MUST NOT be created or mixed across body text, anchors, registries, and filenames. `TRADEPLAN` is the compound code for trading plans; `PLAN` is reserved for the L4 current construction plan.

| Code | English Meaning | Responsibility |
|---|---|---|
| `CON` | Constitution | Project constitution |
| `DOC` | Documentation architecture | Documentation architecture |
| `VIS` | Vision | Goals and vision |
| `FLOW` | Core workflows | Core workflows and user journeys |
| `ARC` | Architecture | Overall technical requirements and architecture |
| `ALP` | Alpha research | Alpha research, economic evidence, and strategy |
| `DAT` | Data | Authoritative facts, market data, and time |
| `CAP` | Capital | Capital, risk, and authority |
| `TRADEPLAN` | Trading plan | Trading-plan and condition lifecycle |
| `EXE` | Execution | Execution, protection, reconciliation, and recovery |
| `OUT` | Outcomes | Outcomes, attribution, and learning |
| `UX` | User experience | User interaction and control surfaces |
| `SYS` | System | System composition and runtime boundaries |
| `ENG` | Engineering | Engineering quality and build boundaries |
| `PLAN` | Current construction plan | L4 current construction plan; its fixed ID is `HALPHA-PLAN-001` |

The type code is not the English short title: the short title aids reading and navigation, while the type code determines the sole owner and document identity. A new type MUST first amend this table and the responsibility registry. A code absent from this table MUST NOT be used for a normative filename or stable semantic anchor.

### Chinese Terminology

Chinese normative text SHOULD use direct, common wording that states the business meaning and SHOULD NOT invent an abstraction or metaphor when a plain expression already exists. For example, use “资金使用上限与范围” (fund-use limit and scope) instead of “资本包络” (capital envelope), “提交前再次检查资金与权限” (recheck funds and authority before submission) instead of “最终资本门” (final capital gate), and “形成并保存动作记录” (form and save an action record) instead of “动作物化” (action materialization).

English abbreviations or names are reserved for external standards, document or domain IDs, code identifiers, and technical terms that must remain consistent; their Chinese meaning MUST be given on first use. An L3 MAY retain real field or type names but MUST identify the corresponding Chinese business meaning and MUST NOT use a field name in place of a business definition. The same concept uses the same Chinese name across documents; differences in degree are stated separately rather than embedded in domain or object names.

### Distinguishing Semantic Owners from the Project Owner【DOC-SEM-001-DEF】

The Project Owner is the human responsible for project construction, design, and the construction plan. The User invests trading capital, uses the product, and makes product-use and capital-control decisions. One person MAY hold both roles, but their meanings do not merge. A Developer performs development, validation, or release work and MAY be an AI tool or the Project Owner, but is not the User. A semantic owner, primary semantic owner, or coordination owner identifies responsibility belonging to a document or L2/L3; it is not a human, account, runtime process, or authority. Ownership says who defines and maintains meaning and MUST NOT be used as an actual actor. Actual behavior MUST be attributed to the User, Project Owner, Developer, Halpha, a background task, an Executor, or a named external system. When any of these owner names appears in metadata or a table, the complete role name required by context MUST be used.

### Requirements for Concepts, Actors, and Records【DOC-SEM-001-REQ】

1. A concept with stable special meaning MUST first be defined at the highest appropriate level by one semantic owner. Undefined special concepts MUST NOT be used as requirements, states, objects, or rationale.
2. Common words retain their normal meaning. Use direct qualified names for needed distinctions; do not create a concept for one-off content without an independent consumer.
3. A concept name MUST remain clear outside its source document, section title, and domain ID. Generic words such as “candidate,” “decision,” “state,” “record,” “result,” “mode,” and “notification” require a necessary object or purpose qualifier. Cross-document references MUST use the same complete name and MUST NOT depend on restatement or temporary renaming at the point of reference.
4. Domain IDs identify who owns, defines, or governs a meaning; they are not actors. Formation, reading, submission, stopping, reconciliation, and notification MUST be attributed to the User, Project Owner, Developer, Halpha, a background task, an Executor, or a named external system.
5. A new concept, object, recorded behavior, or dataset MUST identify its real consumer, the decision or failure behavior it changes, and its deletion condition. Do not create it when consumption value does not cover understanding, implementation, operating, and maintenance cost.
6. L2 governs record meaning that changes decisions, responsibility, or failure handling. Fields, storage, and transport belong in L3; current sources, configuration, limits, and exceptions belong in L4.

Only L0 and L1 maintain zh-CN and en-US co-normative texts. The two texts have equal authority, are independently complete, and have no priority language. L2, L3, L4, the responsibility registry, and navigation indexes are maintained only in zh-CN and MUST NOT have en-US counterpart files. External standards, code identifiers, and necessary technical terms MAY still use English under the terminology rules.

Fixed L1 filenames are:

| Document | zh-CN | en-US |
|---|---|---|
| Documentation Architecture | `HALPHA-DOC-001-documentation-architecture.zh-CN.md` | `HALPHA-DOC-001-documentation-architecture.en-US.md` |
| Goals and Vision | `HALPHA-VIS-001-goals-and-vision.zh-CN.md` | `HALPHA-VIS-001-goals-and-vision.en-US.md` |
| Core Workflows and User Journeys | `HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md` | `HALPHA-FLOW-001-core-workflows-and-user-journeys.en-US.md` |
| Overall Technical Requirements and Architecture | `HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md` | `HALPHA-ARC-001-technical-requirements-and-architecture.en-US.md` |

## 2.2 Minimum Metadata【DOC-MET-001】

Except that L0 has no parent, every normative document MUST declare its document ID, level, language edition, parent document or provision, governed scope, and excluded scope. L0 uses scope and authority scope in place of ordinary parent, governed-scope, and excluded-scope fields. An L0/L1 co-normative text header MUST also declare its paired text; the two texts share a stable document ID, section structure, and semantic anchors. For every other document, the Markdown header owns parent, governed scope, and excluded scope; a machine registry MUST NOT duplicate them.

A document header follows the structure declared in this section. L1–L3 metadata MUST NOT contain a current implementation identifier, choice, progress, or validation result. Implementation state is read only from L4.

An L4 time record MUST use a time meaning appropriate to its content: observation time for a fact, cutoff or decision time for a plan or summary, and applicability start for an instance or configuration. Add expiry or review time only when a real temporal boundary exists. A machine registry or current plan MUST NOT store a self-referential path field. The applicable machine specification defines concrete field names and types.

## 2.3 File Locations【DOC-LOC-001】

~~~text
docs/
  L0/
  L1/
  L2/
  L3/
  L4/
~~~

Each stable document ID maintains its body at the target path for its level. That body expresses the document's design, while actual Git commits support historical traceability, comparison, and recovery. A machine-readable companion is maintained only when a real product or current-fact consumer needs it.

---

# 3. Minimum Reading Rules for AI【DOC-AIR-001】

1. A current-state task MUST start from the L4 current construction plan. Missing records mean UNKNOWN; code or long-term design MUST NOT be used to infer state.
2. An implementation task starts from the current objective and scope, then reads the domain L3 corresponding to the primary semantic owner. It then reads that L3's direct dependencies, applicable vertical L2s, necessary L1s, and the exact versions, current configuration, and validation results in L4. It reads documents corresponding to the coordination owner and participants only when a real orchestration L3 exists. Unused documents are not read.
3. Design and implementation tasks read the applicable target documents. A required missing document MUST be reported rather than filled by inference.
4. L1–L3 MUST NOT claim current state, and L4 MUST NOT invent product or system rules. Missing semantics or conflict between current finalized documents stops implementation and MUST be reported.
5. An ordinary task reads directly cited L0 provisions. A change to documentation governance, overall complexity direction, or real-capital limit or scope requires the full L0 in the working language.

---

# 4. Entering Implementation【DOC-IMP-001】

Implementation needs only the conditions directly relevant to its result:

- current design identifies the product result and sole semantic owner;
- L4 records the current objective, scope, exact choices, and known blockers;
- the L2/L3 rules needed by current consumers can determine normal and failure outcomes, and L3 creates no stable meaning absent from L2; and
- when a generic capability is added or replaced, ENG has compared mature capabilities and selected the smallest maintainable option.

The project need not design capabilities without current consumers or complete project-wide documentation, engineering approval, or admission machinery before one result can be implemented. A design gap blocks only behavior that depends on it; work with independent paths, databases, credentials, and external-write effects MAY continue. Starting implementation, completing tests, and the User increasing Halpha real-capital operating authority remain separate facts.

---

# 5. Update Location【DOC-UPD-001】

Amend the highest level that owns the meaning: L0 for mission and highest boundaries; L1-A for documentation rules; L1-B for product direction; L1-C for business paths; L1-D for overall technology; L2 for domain principles; L3 for detailed-design rules and long-term component-use contracts; and L4 for exact versions, current configuration, platform and license validation results, current plans, and facts. Review only affected downstream material.

---

# 6. Creating, Splitting, and Reviewing【DOC-SPL-001】

An L2 document owns one independently named horizontal core-business composition or vertical domain. An L3 owns one explicit implementation scope and declares a primary semantic owner or coordination owner. Actual consumers decide whether to draft or extend L2/L3 and its design scope; they do not require symmetric document size, object counts, or implementation investment across the responsibility map. L4 owns current scope, sequence, and progress.

Do not create a long-lived document for every task, ordinary class, third-party-library internal object, or content expressible by public contracts, data structures, types, and tests. Merge or assign one semantic owner when multiple documents own the same stable meaning; split a document that owns independently evolving responsibilities; merge or delete a document that loses independent responsibility; and reduce content to the smallest useful scope when maintenance cost persistently exceeds real consumption value. When a document loses independent responsibility, modify the affected target documents in the same working change and migrate every direct consumer. After a boundary or scope change, review the semantic owner, direct horizontal dependencies, and vertical constraints of every affected L3.

## 6.1 Direct Changes and Impact Validation【DOC-CHG-001】

A document change directly edits the target file for its stable document ID. Validation strength follows semantic impact rather than changed-line count:

- A change that preserves identity, level, ownership, responsibility, normative strength, behavior, failure handling, acceptance, external effects, stable concepts, dependencies, support scope, and migration uses lightweight checks.
- A change to any of those meanings MUST read direct parents, adjacent owners, and direct consumers; cover critical normal and counterexample paths; and receive independent review proportionate to actual impact.
- Creating, splitting, merging, renaming, or deleting a document MUST prove independent responsibility, migrate direct consumers, and delete stale references.

Direct does not mean silent. Affected direct downstream material, responsibility registries, and indexes MUST be synchronized, and applicable validation MUST pass. Any L0/L1 meaning or structure change MUST update both language bodies in the same working change.

## 6.2 Cross-Document Synchronization【DOC-CHG-002】

A cross-level or cross-document change first edits the highest document that owns the meaning and, after the meaning is stable, synchronizes necessary direct consumers, responsibility registries, indexes, and the L4 current plan. If necessary synchronization cannot be completed within the authorized scope, stop and report the gap.
