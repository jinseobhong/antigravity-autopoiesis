---
id: "SPEC-0001"
title: "Subagent Invocation and Orchestration Guide"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
dependencies:
  - "GEMINI.md"
  - "docs/specs/AGENT_REGISTRY.md"
---

# Subagent Invocation and Orchestration Specification (v3.0)

This specification establishes the official registration directory, naming conventions, invocation
mechanisms, and operational invariants for all specialized agent personas and reviewer panels in
Antigravity.

---

## 1. Registered Subagent Directory

| Subagent Identifier | Target Domain | Invocation Role & Core Mandate |
| :--- | :--- | :--- |
| **`software-engineer`** | Code / Architecture | Qualitative code implementation review and structural audit. |
| **`qa-engineer`** | QA / Verification | Qualitative test strategy review and test matrix gap analysis. |
| **`socratic-interviewer`** | Requirements / Architecture | Conducts Socratic requirement elicitation interviews to resolve ambiguity. |
| **`technical-writer`** | Docs / Specifications | Qualitative documentation review, NASA tone conformance, and structural auditing. |
| **`technical-reviewer-architecture`** | Code / Architecture | Audits domain abstraction honesty, value objects, and anti-speculative YAGNI. |
| **`technical-reviewer-resilience`** | Code / Systems | Audits concurrency races, resource disposal, and failure containment. |
| **`technical-reviewer-ergonomics`** | Code / Readability | Audits cognitive load, narrative flow, nesting depth, and on-call ergonomics. |
| **`documentation-reviewer-completeness`** | Technical Specs | Audits missing failure modes, unstated assumptions, and rollback gaps. |
| **`documentation-reviewer-dialectic`** | Technical Specs | Audits logical integrity, dialectical trade-off honesty, and hidden costs. |
| **`documentation-reviewer-usability`** | Runbooks / Ops | Audits operational actionability, command ambiguity, and runbook safety. |

---

## 2. Invocation Mechanisms

### Method 1: Sovereign Direct Execution (Primary Orchestrator)
The Primary Orchestrator is the sole author and executor in the repository. Production source code,
test suites, and documentation modifications are authored directly in-process by the primary agent
to eliminate multi-agent coordination latency and token inflation.

### Method 2: High-Level Reviewer Dispatcher Skills (Recommended)
For qualitative multi-perspective reviews, the primary orchestrator invokes high-level dispatcher skills:
- **`review-implementation`**: Concurrently dispatches all 3 technical reviewers (`architecture`, `resilience`, `ergonomics`) via `Workspace: 'inherit'`.
- **`review-documentation`**: Concurrently dispatches all 3 doc reviewers (`completeness`, `dialectic`, `usability`) via `Workspace: 'inherit'`.
- **`autopoiesists`**: Concurrently dispatches the 9 specialized Autopoiesist perspectives.
- **`grill-me`**: Dispatches `socratic-interviewer` for requirements elicitation.

### Method 3: Programmatic Invocation via `invoke_subagent` (Read-Only Review Panels)
Supervisors and workflow runners SHALL invoke subagents using the bounded `invoke_subagent` schema
strictly for read-only analysis:

```json
{
  "Subagents": [
    {
      "TypeName": "technical-reviewer-architecture",
      "Role": "Domain Abstraction Reviewer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Audit domain abstraction honesty in core/evolutionary_engine.py --caller-id: <CALLER_ID>"
    },
    {
      "TypeName": "technical-reviewer-resilience",
      "Role": "Evolutionary Resilience Reviewer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Audit concurrency safety and resource cleanup in core/evolutionary_engine.py --caller-id: <CALLER_ID>"
    }
  ]
}
```

---

## 3. Operational Invariants

- **[REQ-INV-01] Read-Only Subagent Boundary**: Subagents **SHALL NOT** possess filesystem mutation
  privileges. All file write and command execution attempts by subagents are intercepted and blocked
  by `scripts/guard_ivv_pipeline.py`.
- **[REQ-INV-02] Shared Workspace Calibration**: Subagents **SHALL** execute within shared workspaces
  (`Workspace: 'inherit'`) to read workspace files without duplicating disk storage.
- **[REQ-INV-03] Coordinate Citation Mandate**: Review subagents **SHALL** anchor every defect finding with
  exact line coordinate links (`file:///<path>#L<start>-L<end>`) and verbatim code/text excerpts.
- **[REQ-INV-04] IPC Callback Relay**: Subagents dispatched programmatically **SHALL** relay their
  synthesized findings directly back to the caller via `send_message(Recipient='<caller_id>')` before
  concluding their turn.
- **DO**: Run quantitative compliance (`python scripts/compliance_checker.py <target>`) before
  invoking review subagents.
- **DON'T**: Grant mutating file write permissions to subagents.
