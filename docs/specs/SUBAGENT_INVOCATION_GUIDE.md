---
id: "SPEC-0001"
title: "Subagent Invocation and Orchestration Guide"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
dependencies:
---

# Subagent Invocation and Orchestration Specification (v2.0)

This specification establishes the official registration directory, naming conventions, invocation mechanisms, and operational invariants for the 6 qualitative adversarial review subagents and their orchestrators in Antigravity.

---

## 1. Registered Subagent Directory

| Subagent Identifier | Target Domain | Invocation Role & Core Mandate |
| :--- | :--- | :--- |
| **`technical-reviewer-architecture`** | Code / Architecture | Audits domain abstraction honesty, value objects, ubiquitous language, and anti-speculative over-engineering (YAGNI). |
| **`technical-reviewer-resilience`** | Code / Systems | Audits concurrency races, resource disposal, unstated environmental assumptions, and error propagation voids. |
| **`technical-reviewer-ergonomics`** | Code / Readability | Audits cognitive load, narrative flow, nesting depth, mutation transparency, and 3 AM on-call comprehension. |
| **`documentation-reviewer-completeness`** | Technical Specs | Audits what is NOT written: missing failure modes, unstated assumptions, security voids, and rollback gaps. |
| **`documentation-reviewer-dialectic`** | Technical Specs | Audits logical integrity, dialectical trade-off honesty, confirmation bias, and hidden architectural costs. |
| **`documentation-reviewer-usability`** | Runbooks / Ops | Audits operational actionability, command ambiguity, mistake-proofing, and high-stress runbook safety. |

---

## 2. Invocation Mechanisms

### Method 1: Automated Parallel Dispatcher Skills (Recommended)
Rather than manually coordinating individual reviewers, operators and orchestrator agents SHOULD invoke the high-level parallel dispatcher skills:
- **`review-documentation`**: Concurrently dispatches all 3 documentation review specialists (`completeness`, `dialectic`, `usability`) via `Workspace: 'inherit'` and synthesizes an executive verdict report.
- **`review-technical`**: Concurrently dispatches all 3 technical review specialists (`domain`, `resilience`, `ergonomics`) via `Workspace: 'inherit'` and synthesizes an executive verdict report.

### Method 2: Interactive Slash Command (`/agent`)
In any active Antigravity chat session or terminal, dispatch a targeted review task directly to an individual specialist:

```text
/agent technical-reviewer-domain "Perform domain abstraction review on core/cortex.py"
/agent technical-reviewer-resilience "Audit concurrency and resource cleanup in core/worker.py"
/agent technical-reviewer-ergonomics "Audit readability and cognitive friction in core/runner.py"
/agent documentation-reviewer-completeness "Expose unwritten failure modes in docs/ARCHITECTURE.md"
/agent documentation-reviewer-dialectic "Audit trade-off honesty and logical integrity in docs/ADR-001.md"
/agent documentation-reviewer-usability "Audit operational actionability in docs/runbooks/failover.md"
```

### Method 3: Standalone CLI Session (`agy --agent`)
Launch a dedicated terminal session operating strictly under a specialist's persona:

```bash
# Launch dedicated session for technical domain review
agy --agent technical-reviewer-domain

# Launch dedicated session for specification completeness audit
agy --agent documentation-reviewer-completeness
```

### Method 4: Antigravity 2.0 GUI Dropdown & Manager
1. Type `/agents` in the chat canvas to open the interactive **Agent Manager Panel**.
2. Select the target reviewer from the custom agents list.
3. Switch active conversational context or inspect background transcript logs.

### Method 5: Programmatic Invocation via `invoke_subagent`
Supervisors and workflow runners SHALL invoke subagents using the bounded `invoke_subagent` schema:

```json
{
  "Subagents": [
    {
      "TypeName": "technical-reviewer-domain",
      "Role": "Domain Abstraction Reviewer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Perform adversarial domain abstraction review on target: <TARGET_PATH>.\n--caller-id: <CALLER_CONVERSATION_ID>\n\nProtocol:\n1. Inspect file via view_file (bounded line ranges <= 800 lines).\n2. Classify findings: [P0 Blocker | P1 Major | P2 Advisory].\n3. Cite line coordinates ([<file>:L<start>-L<end>](file:///<path>#L<start>-L<end>)) and verbatim excerpts.\n4. Provide unified diff (diff) blocks for every smell.\n5. Relay findings to caller via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message=...)."
    }
  ]
}
```

---

## 3. Operational Invariants

- **[REQ-INV-01] Tool Permission Boundary**: Qualitative review subagents **SHALL NOT** be granted write permissions (`enable_write_tools: false`). Execution is strictly read-only.
- **[REQ-INV-02] Workspace Mode Calibration**:
  - Read-only review subagents **SHALL** execute within shared workspaces (`Workspace: 'inherit'`) to eliminate git worktree cloning latency and branch garbage.
  - Isolated branch workspaces (`Workspace: 'branch'`) **SHALL NOT** be used for read-only static analysis and are reserved strictly for mutating remediation or technical subagents.
- **[REQ-INV-03] Coordinate Citation Mandate**: Review subagents **SHALL** anchor every defect finding with exact line coordinate links (`file:///<path>#L<start>-L<end>`) and verbatim code/text excerpts.
- **[REQ-INV-04] IPC Callback Relay**: Subagents dispatched programmatically **SHALL** relay their synthesized findings directly back to the caller via `send_message(Recipient='<caller_id>')` before concluding their turn.
- **DO**: Run Tier 1 quantitative compliance (`python scripts/compliance_checker.py <target>`) before invoking review subagents.
- **DON'T**: Ask qualitative review subagents to perform trivial linter, formatting, or stylistic syntax checks.
