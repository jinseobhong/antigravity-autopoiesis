---
id: "SPEC-0002"
title: "Autonomous Agent Registry and Capability Matrix Specification"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
dependencies:
  - "GEMINI.md"
  - "docs/active/ARCHITECTURE.md"
  - "docs/specs/SUBAGENT_INVOCATION_GUIDE.md"
---

# Autonomous Agent Registry and Capability Matrix Specification (v2.1)

This specification establishes the authoritative Single Source of Truth (SSOT) catalog, capability
matrix, security boundaries, and lifecycle orchestration topologies for all 10 specialized agent
personas in Project Autopoiesis.

---

## 1. Architectural Overview & Persona Taxonomy

Project Autopoiesis organizes autonomous agents into four functional tiers based on blast radius,
mutation privileges, and cognitive mandates:

```mermaid
flowchart TD
    subgraph TierP0 ["P0: Core Mutating Systems Agents (IV&V)"]
        SE["software-engineer<br>(Production Code Modules in Sandbox)"]
        QA["qa-engineer<br>(Dual Functional & Adversarial Tests)"]
        SI["socratic-interviewer<br>(Requirements & Contracts)"]
    end

    subgraph TierP1 ["P1: Qualitative Adversarial Reviewers"]
        TR["Code Review Panel (3 Specialists)<br>(Architecture, Resilience, Ergonomics)"]
        DR["Doc Review Panel (3 Specialists)<br>(Completeness, Dialectic, Usability)"]
    end

    subgraph TierP2 ["P2: Technical Documentation Architect"]
        TW["technical-writer<br>(NASA Specifications & ADRs)"]
    end

    subgraph TierP3 ["P3: Deterministic CLI Engines"]
        CC["compliance_checker<br>(AST & Code Invariants)"]
        FT["fs_topology<br>(Filesystem Principles)"]
        CD["cortex_docs<br>(Tri-Domain DB Persistence)"]
    end

    SI -->|"Active Contract"| SE
    SI -->|"Active Contract"| QA
    SE -->|"Provisional Draft"| TR
    TR -->|"Confirmed Code"| QA
    QA -->|"Verified Pass"| TW
    TW -->|"Draft Spec"| DR
```

### 1.1 Taxonomy Classification Definitions
1. **Tier P0 (Systems Builders, Elicitors & QA Verifiers)**:
   - Agents possessing scoped filesystem write privileges in `./sandbox/` or `docs/active/`.
   - Authorized for requirement elicitation (`socratic-interviewer`), production coding (`software-engineer`),
     and independent adversarial and functional test authoring (`qa-engineer`).
2. **Tier P1 (Adversarial Quality Reviewers)**:
   - Read-only agents executing qualitative code and documentation audits.
   - Enforce domain abstraction integrity, concurrency resilience, on-call ergonomics, and completeness.
3. **Tier P2 (Information Architects)**:
   - Specialized agents authoring NASA-grade technical documentation, ADRs, RFCs, and operational runbooks.
4. **Tier P3 (Deterministic CLI Utilities)**:
   - Purely deterministic, non-LLM Python CLI automation tools enforcing quantitative AST rules.

---

## 2. Complete Agent Capability & Security Matrix

The following contiguous matrix establishes the authoritative configuration, tool permissions,
watchdog timeout budgets, and dispatch skills for all 10 registered personas:

| Agent Identifier | Tier | Target Domain | Mutating Privilege | Watchdog Timeout | Declared Tool Bindings | Primary Dispatch Skill |
| :--- | :---: | :--- | :---: | :---: | :--- | :--- |
| **`Primary Orchestrator`** | P0 | All Domains | `Mutating (Sovereign)` | N/A | Full Tool Access (Sole Writer) | Direct Execution |
| **`software-engineer`** | P1 | Code / Systems Review | `Read-Only` | 300s | `view_file`, `grep_search`, `send_message` | `review-implementation` |
| **`qa-engineer`** | P1 | QA & Verification Review | `Read-Only` | 300s | `view_file`, `grep_search`, `send_message` | `review-implementation` |
| **`socratic-interviewer`** | P1 | Requirements / Contracts | `Read-Only` | 300s | `view_file`, `grep_search`, `ask_question`, `send_message` | `grill-me` |
| **`technical-writer`** | P1 | Docs / Architecture | `Read-Only` | 300s | `view_file`, `grep_search`, `send_message` | `review-documentation` |
| **`technical-reviewer-architecture`** | P1 | Code / Domain Design | `Read-Only` | 300s | `view_file`, `grep_search`, `send_message` | `review-implementation` |
| **`technical-reviewer-resilience`** | P1 | Code / Concurrency & I/O | `Read-Only` | 300s | `view_file`, `grep_search`, `send_message` | `review-implementation` |
| **`technical-reviewer-ergonomics`** | P1 | Code / Cognitive Load | `Read-Only` | 300s | `view_file`, `grep_search`, `send_message` | `review-implementation` |
| **`documentation-reviewer-completeness`** | P1 | Docs / Failure Modes | `Read-Only` | 300s | `view_file`, `grep_search`, `send_message` | `review-documentation` |
| **`documentation-reviewer-dialectic`** | P1 | Docs / Trade-off Honesty | `Read-Only` | 300s | `view_file`, `grep_search`, `send_message` | `review-documentation` |
| **`documentation-reviewer-usability`** | P1 | Docs / Operations & Ops | `Read-Only` | 300s | `view_file`, `grep_search`, `send_message` | `review-documentation` |

---

## 3. End-to-End Decoupled IV&V Orchestration Topology

Project Autopoiesis enforces an Independent Verification and Validation (IV&V) closed-loop lifecycle,
supporting both single-pair execution and Interface-Locked Modular Parallelism:

```mermaid
sequenceDiagram
    autonumber
    actor Operator as "Human Operator"
    participant Orch as "Primary Orchestrator"
    participant SI as "socratic-interviewer"
    participant Proto as "Interface Lockdown"
    participant QA as "qa-engineer (Dual Cluster)"
    participant SE as "software-engineer (Worker Cluster)"
    participant TR as "technical-reviewer Panel"
    participant TW as "technical-writer"
    participant DR as "documentation-reviewer Panel"
    participant Prod as "Trunk Production Root"

    Operator->>Orch: "Initiate Feature Request (/grill-me)"
    Orch->>SI: "Dispatch Requirement Elicitation"
    SI->>Operator: "Socratic Dialog & Design Decisions"
    SI->>Orch: "Active Contract Staged (ACTIVE_CONTRACT.md)"
    Operator->>Orch: "Contract Ratified (ACCEPTED)"

    Note over Orch, Proto: "Phase 1: Interface Lockdown"
    Orch->>Proto: "Stage Protocols & Value Objects (sandbox/core/types.py)"

    par ["Phase 2: Modular Fan-Out Dispatch"]
        Orch->>QA: "Synthesize Functional & Adversarial Test Suites"
        QA-->>Orch: "Dual Test Suites Staged (tests/)"
        Orch->>SE: "Author Decoupled Implementation Modules"
        SE-->>Orch: "Candidate Modules Staged in sandbox/core/"
    end

    Note over Orch, TR: "Phase 3: Provisional Multi-Module Review"
    Orch->>TR: "Dispatch 3-Reviewer Panel (review-implementation)"
    TR-->>Orch: "Provisional Critique & Diff Blocks"
    Orch->>SE: "Apply Refinements -> Code Confirmed"

    Note over Orch, Prod: "Phase 4: Deterministic Hard Gate"
    Orch->>Orch: "Run Confirmed Modules vs Dual Test Suites"
    Orch->>Prod: "Apply Unified Patch (git apply)"

    Note over Orch, DR: "Documentation Lifecycle"
    Orch->>TW: "Dispatch Documentation (write-document)"
    TW->>Orch: "Specs Staged in sandbox/docs/"
    Orch->>DR: "Dispatch 3-Reviewer Panel (review-documentation)"
    DR-->>Orch: "Consolidated Verdict: APPROVED"
    Orch->>Prod: "Apply Documentation Patch"
    Orch->>Operator: "Sprint Milestone Verified & Promoted"
```

---

## 4. Deep-Dive Persona Profiles

### 4.1 `software-engineer` (Systems Implementation Advisor & Code Strategist)
- **Primary Mandate**: Formulates deep domain algorithm blueprints and AST-compliant code implementations for the Primary Orchestrator.
- **Pure Advisory Invariant**: Emits structured code blueprints via `send_message` with zero direct file mutations.
- **Quality Mandate**: Enforces CC $\le 10$, nesting depth $\le 3$, and strict KISS/YAGNI principles.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for implementation advice.

### 4.2 `qa-engineer` (Systems QA Advisor & Adversarial Test Strategist)
- **Primary Mandate**: Formulates exhaustive test matrices, fault domain mappings, and companion test suite blueprints.
- **Negative Ratio Mandate**: Maintains $\ge 40\%$ negative assertions evaluating edge cases and exceptions (`H-CODE-3`).
- **Pure Advisory Invariant**: Emits companion test code via `send_message` for the Orchestrator to author and execute.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for test strategy.

### 4.3 `socratic-interviewer` (Socratic Requirements Advisor & Contract Elicitor)
- **Primary Mandate**: Conducts interactive Socratic interviews via `ask_question`, resolving requirements and formulating contract drafts.
- **Fail-Closed Invariant**: Enforces `[INV-GRILL-07]` (Silence Is Not Consent); missing responses quarantine to `ON_HOLD`.
- **Pure Advisory Invariant**: Transmits contract drafts via `send_message` to Orchestrator without direct filesystem writes.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for requirement elicitation.

### 4.4 `technical-writer` (Lead Technical Writing Advisor & Systems Information Architect)
- **Primary Mandate**: Analyzes architectural state and synthesizes NASA-grade technical specifications, ADRs, and runbook blueprints.
- **Normative Invariant**: Uses strict normative keywords (`SHALL`, `SHALL NOT`, `MUST`, `DO`, `DON'T`).
- **Pure Advisory Invariant**: Emits documentation blueprints via `send_message` for the Orchestrator to author.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for documentation synthesis.

### 4.5 `technical-reviewer-architecture` (Domain Abstraction Reviewer)
- **Primary Mandate**: Audits domain abstraction honesty, value objects, ubiquitous language, and speculative over-engineering.
- **Panel Participation**: Member of `--type code` review panel.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for read-only qualitative review.

### 4.6 `technical-reviewer-resilience` (Evolutionary Resilience Reviewer)
- **Primary Mandate**: Audits concurrency hazards, resource leaks, error containment, and unstated environmental assumptions.
- **Panel Participation**: Member of `--type code` review panel.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for read-only qualitative review.

### 4.7 `technical-reviewer-ergonomics` (Cognitive Ergonomics Reviewer)
- **Primary Mandate**: Audits cognitive load, on-call comprehension, SLAP conformance, and nesting depth $\le 3$.
- **Panel Participation**: Member of `--type code` review panel.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for read-only qualitative review.

### 4.8 `documentation-reviewer-completeness` (Specification Completeness Reviewer)
- **Primary Mandate**: Exposes unstated assumptions, missing failure states, rollback gaps, and security voids.
- **Panel Participation**: Member of `--type doc` review panel.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for read-only qualitative review.

### 4.9 `documentation-reviewer-dialectic` (Dialectical Logic Reviewer)
- **Primary Mandate**: Audits logical integrity, self-rationalization, trade-off honesty, and causal validity.
- **Panel Participation**: Member of `--type doc` review panel.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for read-only qualitative review.

### 4.10 `documentation-reviewer-usability` (Operational Usability Reviewer)
- **Primary Mandate**: Audits operational actionability, command ambiguity, mistake-proofing, and high-stress runbook safety.
- **Panel Participation**: Member of `--type doc` review panel.
- **Invocation Mechanism**: Dispatched via Antigravity `invoke_subagent` for read-only qualitative review.

---

## 5. Operational Invariants & Governance Directives

Technical directives and system invariants are defined below conforming to NASA SP-2016-6105 Rev 2.

### 5.1 Registration & Parity Directives
- **`[REQ-REG-01]` Zero-Drift Invariant**: Every markdown persona located in `.agents/agents/*.md`
  **SHALL** maintain a corresponding registered record in Section 2 of this specification.
- **`[REQ-REG-02]` Tool Privilege Ceiling**: Qualitative review personas **SHALL NOT** declare
  mutating filesystem tools (`write_to_file`, `replace_file_content`).
- **`[REQ-REG-03]` Fail-Closed Timeout Enforcement**: Out-of-process executions exceeding their
  declared timeout budget **SHALL** transition to `ON_HOLD` with exit code `2` per `[INV-GRILL-07]`.
- **`[REQ-REG-04]` Programmatic IPC Attestation**: Subagents dispatched via `invoke_subagent`
  **SHALL** transmit structured completion metrics to caller via `send_message` before concluding.
- **`[REQ-REG-05]` Production Confinement Mandate**: Autonomous mutating agents **SHALL NOT** apply
  modifications directly to the production root trunk (`.`) during active authoring.
- **`[REQ-REG-06]` IV&V Separation Mandate**: Test suites authored by `qa-engineer` **SHALL** be
  evaluated independently from implementations authored by `software-engineer`.
- **`[REQ-REG-07]` Interface-First Parallelism Mandate**: Modular multi-agent execution **SHALL** establish
  frozen type protocols in `types.py` or `protocols.py` prior to dispatching concurrent implementation workers.

### 5.2 Mandatory Engineering Actions
- **`DO`**: Verify all agent persona manifests using `python scripts/compliance_checker.py .agents/agents/*.md`.
- **`DO`**: Freeze `protocols.py` before fan-out worker dispatch on Tier 3 modular tasks.
- **`DO`**: Execute `python scripts/compliance_checker.py docs/specs/AGENT_REGISTRY.md` upon any registry modification.
- **`DON'T`**: Merge candidate code to production without passing the independent QA test harness.
- **`DON'T`**: Allow implementation agents to author their own final acceptance test suites.
