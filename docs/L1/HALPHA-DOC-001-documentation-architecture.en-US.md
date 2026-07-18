# Halpha Documentation Architecture

**Document ID:** HALPHA-DOC-001  
**Version:** v1.11.0  
**Document Status:** ACCEPTED  
**Level:** L1-A  
**Language Edition:** en-US  
**Joint Normative Set ID:** HALPHA-DOC-001@v1.11.0+20260718T070120+0800  
**Paired Text:** HALPHA-DOC-001-documentation-architecture.zh-CN.md  
**Joint Set Registry:** HALPHA-DOC-001-documentation-architecture.bundle.yaml  
**Effective Time:** 2026-07-18T07:01:20+08:00  
**Parent Documents:** HALPHA-CON-001 v2.11.0  
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
                   L4 Phased Delivery, Facts, and Current Records
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
| L3 | Long-term stable detailed domain design | Based on L2, defines module boundaries, interfaces, states, completion criteria, test requirements, and the specific libraries or frameworks and usage contracts selected through engineering gates and expected to be reused across stages. It MAY limit design scope but does not own construction stages, current exact versions, or enablement state. |
| L4 | Phased delivery and implementation | Within the current construction scope, narrows L0–L3 long-term designs into stage objectives, scope, sequence, dependencies, exact versions and instance choices, current configuration, qualification evidence, progress, acceptance evidence, and actual facts. |

L0–L3 form long-term reusable principles, domain content, and detailed designs. L4 selects applicable scope, combines existing designs, and makes current implementation objectives explicit; it MUST NOT add or alter stable L0–L3 rules. Stage identifiers, current scope, sequence, progress, and evidence are recorded only in L4.

## 1.3 Dependency Order of L1【DOC-L1-001】

The four L1 documents are established and maintained in this semantic-constraint order:

1. HALPHA-DOC-001-documentation-architecture establishes the document form.
2. HALPHA-VIS-001-goals-and-vision establishes long-term product objectives and direction.
3. HALPHA-FLOW-001-core-workflows-and-user-journeys selects the long-term core paths for achieving those objectives.
4. HALPHA-ARC-001-technical-requirements-and-architecture selects the long-term overall technical solution supporting those paths.

Each later document MUST conform to the earlier ones, while product, workflow, and technical meanings remain separately owned. The documents MAY be drafted in parallel, but formal effect MUST follow this order. A lower-level document MUST cite only an ACCEPTED direct parent version.

## 1.4 Use of L2–L4【DOC-L24-001】

### Definitions of L2–L4 Objects and Classifications【DOC-L24-001-DEF】

- **L2 stable-semantic responsibility map:** every stable meaning left by L1 for lower-level detail has one explicit L2 semantic owner. It describes responsibility coverage, not equal design or implementation.
- Only an L2 domain needed by a current or near-term consumer is deepened enough to constrain L3. Later responsibilities initially retain a clear boundary.

An L2 domain or an independent sub-scope uses one of three depth levels:

| Depth | Stable Meaning |
|---|---|
| L2 boundary depth | Sole responsibility, explicit exclusions, delivery or applicability boundary, and the result of absence or failure |
| L2 current-need depth | Stable objects, decisions, state boundaries, handoffs, and acceptance basis needed by current consumers |
| L2 reusable-extension depth | Reusable lifecycle, exceptions, migration, and stable common rules needed only after multiple real consumers appear |

Depth describes supported scope, generalization, and automation—not document length or process count.

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
| Phased delivery design, plan, and progress | Stage objectives, current scope, sequence, dependencies, blockers, completion state, and acceptance evidence |
| Facts, instances, and configurations | Provenance, observation or effective time, active versions, exact versions and build identifiers of third-party dependencies, deployment, current parameters, and platform-qualification evidence |
| L2 depth and support scope | Current and target depth, real consumers, reason for deepening, and explicit unsupported scope |
| ADR and current-state summary | Decision rationale or a dated derived view that does not own new product or system rules |

### Requirements for Using L2–L4【DOC-L24-001-REQ】

L2 MUST first establish domain-critical content, goals, responsibility boundaries, and stable design principles, and then add detail as construction requires. The domains registered in the responsibility map need not have equal depth. Responsibilities on an enabled path MUST be correct; undeepened capabilities MAY be manual, external, or explicitly unsupported.

Every domain starts at L2 boundary depth. It moves to current-need depth only after a real current consumer appears; reusable-extension depth is never the default. Symmetry, tidy documents, or future possibility MUST NOT trigger deepening. Before deepening, state the real consumer, observed deficiency, current need, business benefit, the maintenance capacity the Project Owner can sustain, full-lifecycle cost, why a smaller solution is insufficient, and the exit path. Only L4 records current depth, target depth, support scope, and rationale.

Each stable meaning has one semantic owner. Other L2 domains MAY declare input conditions, consumption, and behavior when the input is absent, but MUST NOT duplicate the owner's rules, state system, or full workflow. A producer defines its output; a consumer defines its intake. Documents MUST NOT form an all-to-all handoff network.

A design crossing multiple L2 domains does not automatically require an orchestration L3. Use a domain L3 plus direct dependencies by default. Use `ORCHESTRATION` only for a recurring cross-domain lifecycle with a stable identity that no current domain can own.

Every L3 MUST declare its type and semantic owner, list direct dependencies and applicable vertical constraints, trace primary business meanings and cross-domain requirements, and turn existing L2 critical content, goals, and principles into stable detailed design. Current needs decide whether to draft or deepen a design; they MUST NOT appear in L3 as a P stage, current scope, construction order, progress, or evidence. If implementation needs a stable rule absent from L2, amend the owning L2 first.

After ARC and ENG capability discovery and difference classification, an L3 MAY record a specific third-party library or framework as the module's long-term implementation solution. It governs how Halpha invokes that component, its inputs and outputs, fact authority, necessary transformations, failure outcomes, version-compatibility boundaries, qualification conditions, and any strictly necessary minimal self-built supplement. Exact versions, build hashes, current configuration, target-operating-system validation, license checks, enablement state, and stage evidence are recorded only in L4.

When a third-party library fully provides a module's internal capability, its L3 primarily states Halpha's usage, boundaries, failures, and exit path. It MUST NOT reproduce vendor-internal classes, algorithms, caches, state machines, network lifecycles, or data structures, and MUST NOT invent a Halpha internal implementation for document symmetry. An L3 MUST NOT retain third-party and self-built implementations as silent, automatic, or long-term parallel alternatives. When the component is unavailable, use stopping, external manual takeover, or explicit non-support as permitted by higher-level rules.

The sole entry point for the current construction plan is:

~~~text
docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml
~~~

It records current construction scope and references needed progress, configurations, and evidence. L4 MUST NOT alter L0–L3. Missing records mean current state is UNKNOWN.

---

# 2. Document Format and File Locations【DOC-FMT-001】

## 2.1 Naming【DOC-NAM-001】

Current normative files use:

~~~text
HALPHA-<TYPE>-<NUMBER>-<ENGLISH-SHORT-TITLE>.<LANGUAGE>.md
~~~

- `HALPHA-<TYPE>-<NUMBER>` is the stable document ID and identity.
- `ENGLISH-SHORT-TITLE` uses lowercase ASCII kebab-case to aid navigation; it does not determine identity.
- All language editions use the same English short title.
- A minor title wording change does not require renaming. A material responsibility change SHOULD trigger evaluation of a new document ID.
- `LANGUAGE` uses a BCP 47 tag such as `zh-CN` or `en-US`.
- Version belongs in metadata, not the current filename. Committed historical versions are identified and restored only through Git history; they are not copied into documentation archive directories.

A language-neutral machine registry keeps the same ID and title and MAY add a purpose marker before the extension, such as `.bundle.yaml`. It MUST NOT carry natural-language normative content available in only one language.

### Current Document Type Codes

Type codes MUST use the unique spellings below. They are case-sensitive parts of document identity; an alternate abbreviation for the same English meaning MUST NOT be created or mixed across body text, anchors, registries, and filenames. `TRADEPLAN` is the compound code for trading plans; `PLAN` is reserved for the L4 current construction plan. `PLN` MUST NOT be used for a new candidate or version.

| Code | English Meaning | Responsibility |
|---|---|---|
| `CON` | Constitution | Project constitution |
| `DOC` | Documentation architecture | Documentation architecture |
| `VIS` | Vision | Goals and vision |
| `FLOW` | Core workflows | Core workflows and user journeys |
| `ARC` | Architecture | Overall technical requirements and architecture |
| `ALP` | Alpha research | Alpha research, economic evidence, and strategy |
| `CTX` | Context | Candidate and decision context |
| `DAT` | Data | Authoritative facts, market data, and time |
| `CAP` | Capital | Capital, risk, and authority |
| `TRADEPLAN` | Trading plan | Trading-plan and condition lifecycle |
| `POR` | Portfolio | Comparison of capital uses and portfolio boundary |
| `EXE` | Execution | Execution, protection, reconciliation, and recovery |
| `OUT` | Outcomes | Outcomes, attribution, and learning |
| `UX` | User experience | User interaction and control surfaces |
| `SYS` | System | System composition and runtime boundaries |
| `ENG` | Engineering | Engineering quality and build boundaries |
| `PLAN` | Current construction plan | L4 current construction plan; its fixed ID is `HALPHA-PLAN-001` |

The type code is not the English short title: the short title aids reading and navigation, while the type code determines the sole owner and document identity. A new type MUST first amend this table and the responsibility registry. A code absent from this table MUST NOT be used for a new current normative filename or stable semantic anchor. Existing `PLN` and `OPS` identities and anchors MAY remain in Git history, but candidates and new versions MUST NOT re-establish those retired identities. Migration MUST record identity changes explicitly and MUST NOT create both old and new identities.

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

Only L0 and L1 maintain zh-CN and en-US co-normative texts and bundles. L2, L3, L4, the responsibility registry, and navigation indexes are maintained only in zh-CN and MUST NOT have en-US counterpart files. External standards, code identifiers, and necessary technical terms MAY still use English under the terminology rules.

Fixed L1 filenames are:

| Document | zh-CN | en-US |
|---|---|---|
| Documentation Architecture | `HALPHA-DOC-001-documentation-architecture.zh-CN.md` | `HALPHA-DOC-001-documentation-architecture.en-US.md` |
| Goals and Vision | `HALPHA-VIS-001-goals-and-vision.zh-CN.md` | `HALPHA-VIS-001-goals-and-vision.en-US.md` |
| Core Workflows and User Journeys | `HALPHA-FLOW-001-core-workflows-and-user-journeys.zh-CN.md` | `HALPHA-FLOW-001-core-workflows-and-user-journeys.en-US.md` |
| Overall Technical Requirements and Architecture | `HALPHA-ARC-001-technical-requirements-and-architecture.zh-CN.md` | `HALPHA-ARC-001-technical-requirements-and-architecture.en-US.md` |

## 2.2 Minimum Metadata【DOC-MET-001】

Except that L0 has no parent, every normative document MUST declare its document ID, version, status, level, language edition, parent document or provision, governed scope, and excluded scope. L0 uses scope and authority scope in place of ordinary parent, governed-scope, and excluded-scope fields. For every other document, the Markdown header owns parent, governed scope, and excluded scope; a machine registry MUST NOT duplicate them.

An L0/L1 co-normative text header MUST also declare the joint-set ID, paired text, joint-set registry, and effective time. The co-normative bundle is the sole machine registry for approval, supersession, language authority, alignment, body digests, and the joint digest. It MUST declare a schema version, document ID and version, joint-set ID, status, alignment, ordered co-normative languages and equal authority, body paths and digests, joint digest, approver, acceptance time, and superseded version. It records an effective time only for delayed effect; otherwise effective time equals acceptance time.

Document ID, version, status, language, joint-set ID, and effective time are necessary binding fields between a text header and its bundle and MUST match. A bundle MUST NOT duplicate the title, parents, per-file co-normative role, standalone-AI-use conditions, or final interpretive authority; one bundle-level field states equal authority of its co-normative languages.

Digests for a schema 3 bundle MUST be recomputed by these fixed rules:

1. Read the raw bytes of each normative text, decode them as UTF-8 with an optional UTF-8 BOM, and convert `CRLF` and lone `CR` line endings to `LF`. Perform no other whitespace folding, trimming, or Unicode normalization.
2. The normative body begins at the first line that is a level-one Markdown heading followed by whitespace and a decimal section number, with either a period or whitespace immediately after that number. It includes that heading line through end of file; the text header and earlier title are excluded. Whether the body ends with a newline is part of the digest input and MUST NOT be added or removed.
3. Encode the normative body as UTF-8 and compute SHA-256. `files.<language>.body_sha256` stores the lowercase hexadecimal digest. The language-key order of `files` MUST exactly match `normative_languages`.
4. The joint-digest input is the document ID, `LF`, version, `LF`, followed for each language in `normative_languages` order by `<language>:<body_sha256><LF>`. Compute SHA-256 over that complete UTF-8 input and store the lowercase hexadecimal digest at `joint_set.sha256`.

A schema 3 bundle MUST NOT repeat these digest rules or store the reconstructible joint-digest input. Any implementation following this section MUST be able to recompute the body and joint digests using only the normative texts, document ID, version, and normative-language order.

A current single-language L2/L3 ACCEPTED document header additionally declares approver, acceptance time, and superseded version. Add an effective time only for delayed effect. L1–L3 metadata MUST NOT contain a generic date, a “current effect” derivable from status and level, a duplicate design-acceptance statement, or a P stage, current construction selection, progress, or evidence. Implementation state is read only from L4.

States are `PROPOSED`, `ACCEPTED`, `SUPERSEDED`, and `WITHDRAWN`. The lifecycle applies to L0–L3 normative documents and L4 conventions or ADRs that require approval.

An L4 time record MUST use a time meaning appropriate to its content: observation time for a fact, cutoff or decision time for a plan or summary, and effective time for an instance or configuration. Add expiry or review time only when a real temporal boundary exists. The current plan uses `as_of`, approver, and acceptance time; it MUST NOT repeat effective time when acceptance has immediate effect. A machine registry or current plan MUST NOT store a self-referential path field. The applicable machine specification defines concrete field names and types.

## 2.3 File Locations【DOC-LOC-001】

~~~text
docs/
  L0/
  L1/
  L2/
  L3/
  L4/
~~~

- `L0`–`L4` store the current documents and their machine companions. A candidate version directly edits its target-level document; a separate cross-level proposal file is not created.
- The documentation tree MUST NOT create `proposals/` or an `archive/` directory at any level. Candidates, history, and process versions MUST NOT be carried by such directories or duplicate copies.
- Only an actual Git commit forms a historical version node that must remain recoverable. Uncommitted intermediate drafts, process versions, and candidates overwritten by later edits are not archived or copied elsewhere.
- Whether a candidate state is retained in a commit follows the actual review and commit cadence. Committed `PROPOSED`, `ACCEPTED`, `SUPERSEDED`, or `WITHDRAWN` states remain in Git history; the current file expresses only the state in the current worktree or commit.

---

# 3. Minimum Reading Rules for AI【DOC-AIR-001】

1. A current-state task MUST start from the L4 current construction plan. Missing records mean UNKNOWN; code or long-term design MUST NOT be used to infer state.
2. An implementation task starts from current scope, then reads the domain L3 corresponding to the primary semantic owner, including its long-term third-party capabilities and usage boundaries. It then reads that L3's direct dependencies, applicable vertical L2s, necessary L1s, and the exact versions, current configuration, and qualification evidence in L4. It reads documents corresponding to the coordination owner and participants only when a real orchestration L3 exists. Unused documents are not read.
3. A formal task uses only current `ACCEPTED` documents. When a target-level document is marked `PROPOSED`, its candidate content has no normative effect; formal work uses that document's most recent accepted Git version or an explicitly named accepted baseline. An uncommitted intermediate draft is not a version that must be read or retained.
4. L1–L3 MUST NOT claim current state, and L4 MUST NOT invent product or system rules. Missing semantics or conflict between current finalized documents stops implementation and MUST be reported.
5. An ordinary task reads directly cited L0 provisions. Normative approval, an overall complexity-direction change, or a change in real-capital limit or scope requires the full L0 in the working language.

---

# 4. Entering Implementation【DOC-IMP-001】

Before formal implementation or persistent integration:

- all four L1 documents have current ACCEPTED versions;
- current scope is registered in L4 with applicable designs, dependencies, and blockers;
- the complete L2 responsibility map exists at `docs/L2/l2-responsibility-map.registry.yaml`; it records the current responsibility identities, shapes, normative documents, and limited stable semantics without copying normative text, building a complex cross-domain graph, or recording current depth;
- the primary L2s, direct dependencies, applicable vertical L2s, and L3s needed by current scope are current ACCEPTED versions at the depth declared by L4; when scope needs an orchestration L3, its coordinator and participating domains meet the same requirement;
- L3 introduces no stable rules absent from L2; stable acceptance semantics are explicit in L2/L3, and current facts, configuration, supported scope, and unsupported scope are recorded in L4.
- every capability proposed for self-building has undergone ENG-governed discovery of mature third-party capabilities, difference classification, and complexity comparison; L3 has removed internally duplicated design that can be directly reused and has bounded the minimal supplement, while L4 records the current exact dependencies and qualification evidence required to enter implementation. Insufficient evidence remains a blocker or explicit non-support and MUST NOT be replaced by a parallel self-built implementation.

The project need not deepen every L2 equally or complete all L3 in advance. Complete responsibility coverage does not mean complete future detail. Domains without a current consumer MAY remain at boundary depth or never become separate runtime modules. An isolated prototype MAY use specified proposed versions, but current dependencies MUST be finalized before persistent integration. Starting implementation, completing tests, and the User increasing Halpha real-capital operating authority are separate facts; no unified engineering-approval or admission system is created.

---

# 5. Update Location【DOC-UPD-001】

Amend the highest level that owns the meaning: L0 for mission and highest boundaries; L1-A for documentation rules; L1-B for product direction; L1-C for business paths; L1-D for overall technology; L2 for domain principles; L3 for detailed-design rules and the specific libraries or frameworks adopted for the long term with their usage contracts; and L4 for exact versions, current configuration, platform and license qualification evidence, current plans, and facts. Review only affected downstream material.

---

# 6. Creating, Splitting, and Reviewing【DOC-SPL-001】

An L2 document owns one independently named horizontal core-business composition or vertical domain. An L3 owns one explicit implementation scope and declares a primary semantic owner or coordination owner. A current or near-term need only decides whether to draft or deepen L2/L3 and its design scope; it is not an L3 stage plan and does not require symmetric document size, object counts, or implementation investment across the responsibility map. L4 owns P stages, current scope, and sequence.

Do not create a long-lived document for every task, ordinary class, third-party-library internal object, or content expressible by public contracts, data structures, types, and tests. Merge or assign one semantic owner when multiple documents own the same stable meaning; split a document that owns independently evolving responsibilities; merge or delete a document that loses independent responsibility; and reduce a domain to a shallower depth when deepening cost persistently exceeds real consumption value. When an accepted document loses independent responsibility, the affected target documents MUST themselves form new versions in one coordinated change, record supersession, and migrate every direct consumer. A version that once had effect remains only in Git history and MUST NOT be erased through `WITHDRAWN`. After a boundary or depth change, review the semantic owner, direct horizontal dependencies, and vertical constraints of every affected L3.

## 6.1 Minor Changes to Accepted Documents【DOC-CHG-001】

A minor change to an accepted document MAY directly create a new `ACCEPTED` version without retaining an intermediate `PROPOSED` version. Classification depends on semantic impact, not changed-line count. A minor change MUST:

- preserve document identity, level, sole semantic owner, governed scope, and excluded scope;
- preserve normative strength, authorization, allowed and prohibited actions, normal/failure/unknown/stop/recovery/end behavior, acceptance criteria, and external effects;
- add, replace, or remove no stable concept, object, state, workflow, role, authority, support scope, dependency direction, or migration requirement; and
- be limited to spelling, formatting, navigation, metadata, or link correction, minor title wording, or clarification that changes no decision or failure handling.

Direct does not mean silent. The new version MUST record its version and supersession, receive Project Owner approval, synchronize affected downstream references and indexes, and pass applicable validation. A co-normative document MUST update every language body, bundle, and digest as one effective package.

## 6.2 Changes That Require Candidate Versions in the Target Documents【DOC-CHG-002】

A major change or new scenario MUST first be expressed by each affected L0–L4 target document as its own `PROPOSED` candidate version and becomes `ACCEPTED` only after review and Project Owner approval. A cross-level proposal document MUST NOT substitute for candidate text in each semantic owner. This includes any change that:

- changes document identity, level, sole semantic owner, responsibility boundary, dependency direction, or normative strength;
- changes authorization, allowed or prohibited actions, normal/failure/unknown/stop/recovery/end behavior, acceptance criteria, external effects, or migration requirements;
- adds, replaces, or removes a stable concept, object, state, workflow, role, authority, support scope, or normative scenario; or
- creates, splits, merges, renames, or withdraws a normative document, or establishes a new L3 scope, L4 phased scenario, or ADR decision scenario.

Each candidate document MUST identify its own target level, candidate baseline or superseded version, `PROPOSED` status, and direct dependencies. A cross-level change MUST use a joint normative set ID, coordinated change ID, or explicit cross-references to identify one candidate set, and synchronize the responsibility registry, indexes, and affected downstream material. A candidate has no normative effect until accepted.

When the Project Owner explicitly accepts content that has already completed review, the coordinated working change MAY directly produce the final `ACCEPTED` versions of all target documents; it need not create, commit, or retain an intermediate `PROPOSED` version merely for form. A separate candidate commit exists only when the actual Git commit cadence creates one; an uncommitted process version requires no archive. When classification as minor or major is uncertain, treat the change as major and mark the target documents `PROPOSED`.
