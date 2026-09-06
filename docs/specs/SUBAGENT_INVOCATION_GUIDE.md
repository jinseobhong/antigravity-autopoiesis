---
id: "SPEC-0001"
title: "Subagent Invocation and Orchestration Guide"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
dependencies:
---

# Subagent Invocation and Orchestration Specification (v2.2)

This specification establishes the official registration directory, naming conventions, invocation
mechanisms, and operational invariants for all 10 specialized agent personas and their orchestrators in
Antigravity.

---

## 1. Registered Subagent Directory

| Subagent Identifier | Target Domain | Invocation Role & Core Mandate |
| :--- | :--- | :--- |
| **`software-engineer`** | Code / Systems | Authors minimal production-grade code satisfying contracts under IV&V. |
| **`qa-engineer`** | Code / QA & IV&V | Authors independent adversarial test suites, boundary tests, and defect hunting. |
| **`socratic-interviewer`** | Requirements / Architecture | Conducts Socratic requirement elicitation interviews and authors binding active contracts. |
| **`technical-writer`** | Docs / Architecture | Authors NASA-grade technical specifications, ADRs, RFCs, and operational runbooks. |
| **`technical-reviewer-architecture`** | Code / Architecture | Audits domain abstraction honesty, value objects, ubiquitous language, and anti-speculative YAGNI. |
| **`technical-reviewer-resilience`** | Code / Systems | Audits concurrency races, resource disposal, unstated environmental assumptions, and error voids. |
| **`technical-reviewer-ergonomics`** | Code / Readability | Audits cognitive load, narrative flow, nesting depth, mutation transparency, and on-call ergonomics. |
| **`documentation-reviewer-completeness`** | Technical Specs | Audits what is NOT written: missing failure modes, unstated assumptions, security and rollback gaps. |
| **`documentation-reviewer-dialectic`** | Technical Specs | Audits logical integrity, dialectical trade-off honesty, confirmation bias, and hidden costs. |
| **`documentation-reviewer-usability`** | Runbooks / Ops | Audits operational actionability, command ambiguity, mistake-proofing, and runbook safety. |

---

## 2. Invocation Mechanisms

### Method 1: Automated Parallel Dispatcher Skills (Recommended)
Rather than manually coordinating individual reviewers, operators and orchestrator agents SHOULD invoke
the high-level dispatcher skills:
- **`implement`**: Dispatches modular `software-engineer` workers and dual `qa-engineer` verifiers in `sandbox/`.
- **`review-implementation`**: Concurrently dispatches all 3 technical reviewers (`architecture`, `resilience`, `ergonomics`) via `Workspace: 'inherit'`.
- **`write-document`**: Dispatches `technical-writer` with pre-approval lint gating.
- **`review-documentation`**: Concurrently dispatches all 3 doc reviewers (`completeness`, `dialectic`, `usability`) via `Workspace: 'inherit'`.
- **`grill-me`**: Dispatches `socratic-interviewer` for requirements elicitation.

### Method 2: Standalone Subprocess Runner (`core.agent_runner`)
Run any agent out-of-process in an isolated worker process with watchdog timeout enforcement:
```bash
# Run software engineer standalone
python -m core.agent_runner run --agent software-engineer

# Run QA engineer standalone
python -m core.agent_runner run --agent qa-engineer

# Run 3-reviewer parallel panel
python -m core.agent_runner panel --type code --target core/fs_topology.py
```

### Method 3: Programmatic Invocation via `invoke_subagent`
Supervisors and workflow runners SHALL invoke subagents using the bounded `invoke_subagent` schema.
For modular parallel execution, multiple workers are dispatched simultaneously:

```json
{
  "Subagents": [
    {
      "TypeName": "software-engineer",
      "Role": "Lead Systems Software Engineer (Storage)",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Implement Storage module in sandbox/core/storage.py --caller-id: <CALLER_ID>"
    },
    {
      "TypeName": "software-engineer",
      "Role": "Lead Systems Software Engineer (Engine)",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Implement Engine module in sandbox/core/engine.py --caller-id: <CALLER_ID>"
    },
    {
      "TypeName": "qa-engineer",
      "Role": "Lead Systems QA Engineer (Functional)",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Synthesize functional tests in sandbox/tests/test_functional.py --caller-id: <CALLER_ID>"
    },
    {
      "TypeName": "qa-engineer",
      "Role": "Lead Systems QA Engineer (Adversarial)",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Synthesize adversarial tests in sandbox/tests/test_adversarial.py --caller-id: <CALLER_ID>"
    }
  ]
}
```

---

## 3. Operational Invariants

- **[REQ-INV-01] Tool Permission Boundary**: Qualitative review subagents **SHALL NOT** be granted write
  permissions (`enable_write_tools: false`). Mutating agents (`software-engineer`, `qa-engineer`,
  `technical-writer`, `socratic-interviewer`) have targeted write permissions restricted to their domains.
- **[REQ-INV-02] Workspace Mode Calibration**:
  - Subagents **SHALL** execute within shared workspaces (`Workspace: 'inherit'`) to guarantee that
    authored artifacts in `./sandbox/` persist across conversational turns.
  - Ephemeral branch workspaces (`Workspace: 'branch'`) **SHALL NOT** be used for persistent code or docs.
- **[REQ-INV-03] Coordinate Citation Mandate**: Review subagents **SHALL** anchor every defect finding with
  exact line coordinate links (`file:///<path>#L<start>-L<end>`) and verbatim code/text excerpts.
- **[REQ-INV-04] IPC Callback Relay**: Subagents dispatched programmatically **SHALL** relay their
  synthesized findings directly back to the caller via `send_message(Recipient='<caller_id>')` before
  concluding their turn.
- **[REQ-INV-05] Sandbox Confinement**: Implementation subagents **SHALL** write new/candidate files
  strictly within `./sandbox/`. Direct root mutations are strictly forbidden.
- **DO**: Run Tier 1 quantitative compliance (`python scripts/compliance_checker.py <target>`) before
  invoking review subagents.
- **DON'T**: Perform large implementations directly in the primary orchestrator context.
