---
id: "CONTRACT-20260907-advisory-agents-rebuild"
title: "Rebuild Core 4 Agents as Sovereign Advisory Consultants Contract"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
target_task_id: "TASK-032"
---

# Active Engineering Contract: Rebuild Core 4 Agents as Sovereign Advisory Consultants (TASK-032)

> [!NOTE]
> ### Document Scope & Governance Authority
> This binding contract defines the operational invariants, role specifications, tool constraints, and IPC schemas for TASK-032: Rebuild Core 4 Agents as Sovereign Advisory Consultants.
> - **Operational Standard**: Antigravity Engineering Constitution (`GEMINI.md` Section 3.5).
> - **Target Task ID**: `TASK-032`
> - **Validation Gate**: `python scripts/validate_active_contract.py --task TASK-032`

---

## 1. Executive Summary & Problem Formulation

Under the ratified **Sovereign Authoring Posture (GEMINI.md v9.0)**, the Primary Orchestrator is the sole author and executor in the repository. Subagents are strictly barred from mutating files or executing commands (enforced mechanically via `scripts/guard_ivv_pipeline.py`).

Legacy agent manifests for the core 4 personas (`software-engineer`, `qa-engineer`, `socratic-interviewer`, `technical-writer`) still contain obsolete instructions claiming direct file authoring, sandbox staging, and self-promotion.

To eliminate this friction and align agents with physical reality, TASK-032 transforms these 4 personas into **Specialized Advisory Consultants**:
1. **`software-engineer`**: Systems Implementation Advisor & Code Strategist. Analyzes domain architectures, evaluates trade-offs, and formulates drop-in Python code blueprints conforming to AST Anti-Cheat (`H-CODE-1..12`) for the Orchestrator to author.
2. **`qa-engineer`**: Systems QA Advisor & Adversarial Test Strategist. Formulates boundary matrices, identifies fault domains, calculates negative test ratios, and synthesizes complete companion test suites for the Orchestrator to author.
3. **`socratic-interviewer`**: Socratic Requirements Advisor & Contract Elicitor. Conducts Socratic elicitation interviews via `ask_question`, aligns NFRs and state models with the operator, and relays complete contract drafts via `send_message` to the Orchestrator for materialization.
4. **`technical-writer`**: Lead Technical Writing Advisor & Systems Information Architect. Analyzes architectural state, crafts NASA-grade documentation/ADR/RFC blueprints, and relays complete markdown specifications via `send_message` to the Orchestrator for materialization.

Additionally, companion dispatcher skills (`.agents/skills/grill-me/SKILL.md` and `.agents/skills/write-document/SKILL.md`) are updated to reflect the Sovereign IPC handoff.

---

## 2. Normative System Invariants (NASA Single-Thought Standard)

- **`[INV-ADV-01]`** All 4 agent manifests SHALL declare `role: subagent`.
- **`[INV-ADV-02]`** All 4 agent manifests SHALL declare read-only tools exclusively.
- **`[INV-ADV-03]`** `software-engineer.md` SHALL define an advisory mandate emitting code blueprints via `send_message`.
- **`[INV-ADV-04]`** `qa-engineer.md` SHALL define a test strategy mandate requiring >= 40% negative assertion ratio.
- **`[INV-ADV-05]`** `socratic-interviewer.md` SHALL transmit contract draft payloads via `send_message`.
- **`[INV-ADV-06]`** `technical-writer.md` SHALL define a documentation blueprint mandate emitting drafts via `send_message`.
- **`[INV-ADV-07]`** Skill `grill-me` SHALL specify Orchestrator file materialization.
- **`[INV-ADV-08]`** Skill `write-document` SHALL specify Orchestrator file materialization.
- **`[INV-ADV-09]`** All modified manifests SHALL clear `scripts/compliance_checker.py`.
- **`[INV-ADV-10]`** All modified manifests SHALL clear `scripts/validate_doc_preapproval.py`.

---

## 3. Structured IPC Schemas

### 3.1 Software Engineer Advisory Schema
```markdown
### [SYSTEMS IMPLEMENTATION ADVISORY & CODE BLUEPRINT]
- Target Component: <Domain Name / Target Path>
- Architectural Trade-Offs: <Trade-off analysis>
- Target Invariant Conformance: <H-CODE-1..12 and contract invariant mappings>
- Drop-in Implementation Blueprint:
  // Complete, production-grade drop-in code for the Orchestrator to write
```

### 3.2 QA Engineer Test Strategy Schema
```markdown
### [QA TEST STRATEGY & COMPANION TEST BLUEPRINT]
- Target Component: <Component Name / Target Path>
- Equivalence & Boundary Matrix: <Positive, Negative, Boundary, Concurrency Matrix>
- Negative Assertion Ratio: <Calculated Ratio >= 40%>
- Drop-in Companion Test Suite:
  // Complete unittest test suite for the Orchestrator to write
```

### 3.3 Socratic Interviewer Contract Schema
```markdown
### [SOCRATIC CONTRACT PROPOSAL & ELICITATION REPORT]
- Target Task: <TASK_ID: Title>
- Elicited Technical Decisions: <Key decisions and trade-offs resolved>
- Complete Normative Contract Payload:
  // Full markdown draft of ACTIVE_CONTRACT.md
```

### 3.4 Technical Writer Specification Schema
```markdown
### [TECHNICAL SPECIFICATION BLUEPRINT & ARCHITECTURAL DRAFT]
- Document Title & Archetype: <Title & Archetype (ADR/RFC/Spec/Runbook)>
- Normative Directives Matrix: <SHALL / SHALL NOT requirements>
- Complete Markdown Specification:
  // Full markdown draft of target document
```

---

## 4. Verification and Acceptance Matrix (V-Matrix)

| Requirement | Verification Method | Target Criteria |
| :--- | :---: | :--- |
| `[INV-ADV-01]` | Automated AST Inspection | 0 mutating tools in frontmatter across all 4 manifests |
| `[INV-ADV-02]` | Static Compliance | Read-only tool bindings enforced in frontmatter |
| `[INV-ADV-03]` | Text & Schema Audit | `software-engineer.md` defines advisory mandate and IPC schema |
| `[INV-ADV-04]` | Text & Schema Audit | `qa-engineer.md` defines test strategy mandate and >= 40% negative ratio |
| `[INV-ADV-05]` | Text & Schema Audit | `socratic-interviewer.md` defines IPC contract proposal without file staging |
| `[INV-ADV-06]` | Text & Schema Audit | `technical-writer.md` defines advisory blueprint mandate |
| `[INV-ADV-07]` | Skill Workflow Audit | `grill-me` skill specifies Orchestrator authoring |
| `[INV-ADV-08]` | Skill Workflow Audit | `write-document` skill specifies Orchestrator authoring |
| `[INV-ADV-09]` | Preflight Checker | 100% compliance pass on `compliance_checker.py` |
| `[INV-ADV-10]` | Preflight Checker | 100% pre-approval pass on `validate_doc_preapproval.py` |
