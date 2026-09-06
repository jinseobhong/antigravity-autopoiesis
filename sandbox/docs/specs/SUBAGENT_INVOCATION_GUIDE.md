---
id: "SPEC-0002"
title: "Subagent Invocation and Orchestration Guide"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-06"
dependencies: ["SPEC-0001"]
---

# Subagent Invocation and Orchestration Specification

This specification establishes the official invocation mechanisms for the 6 qualitative adversarial review subagents in Antigravity.

---

## 1. Registered Subagent Directory

| Subagent Identifier | Target Domain | Invocation Role & Focus |
| :--- | :--- | :--- |
| **`code-reviewer-design`** | Code / Architecture | Audits domain modeling honesty, SRP, and anti-overengineering. |
| **`code-reviewer-ergonomics`** | Code / Readability | Audits cognitive load, narrative flow, and 3 AM on-call comprehension. |
| **`code-reviewer-resilience`** | Code / Systems | Audits unstated assumptions, failure blast radiuses, and coupling. |
| **`doc-reviewer-completeness`** | Technical Specs | Audits what is NOT written: missing failure modes and rollback voids. |
| **`doc-reviewer-dialectic`** | Technical Specs | Audits logical consistency, trade-off honesty, and confirmation bias. |
| **`doc-reviewer-usability`** | Runbooks / Ops | Audits operational clarity, unambiguous commands, and crisis safety. |

---

## 2. Invocation Methods

### Method 1: Interactive Slash Command (`/agent`)
In any active Antigravity chat session or terminal, dispatch a targeted review task directly:

```text
/agent code-reviewer-design "Perform qualitative review on core/cortex.py focusing on domain modeling"
/agent code-reviewer-ergonomics "Audit readability and cognitive friction in core/warm_runner.py"
/agent doc-reviewer-completeness "Expose unwritten failure modes in docs/active/ARCHITECTURE.md"
```

### Method 2: Standalone CLI Session (`agy --agent`)
Launch a dedicated, isolated terminal session operating strictly under that reviewer's persona:

```bash
# Launch a dedicated session for domain abstraction review
agy --agent code-reviewer-design

# Launch a dedicated session for specification completeness audit
agy --agent doc-reviewer-completeness
```

### Method 3: Antigravity 2.0 GUI Dropdown & Manager
1. Type `/agents` in the chat canvas to open the interactive **Agent Manager Panel**.
2. Select the target reviewer from the custom agents list.
3. Switch active conversational context or monitor background execution.

### Method 4: Programmatic Invocation via `invoke_subagent`
Supervisor agents and orchestration workflows SHALL invoke subagents using the `invoke_subagent` tool schema:

```json
{
  "Subagents": [
    {
      "TypeName": "code-reviewer-design",
      "Role": "Domain Abstraction Reviewer",
      "Model": "inherit",
      "Workspace": "branch",
      "Prompt": "Perform adversarial domain review on target: <TARGET_PATH>."
    }
  ]
}
```

---

## 3. Operational Invariants
- **[REQ-INV-01]** Review subagents **SHALL NOT** be granted write permissions (`enable_write_tools: false`).
- **[REQ-INV-02]** Subagents invoked programmatically **SHALL** execute within isolated branches (`Workspace: 'branch'`).
- **DO**: Run Tier 1 quantitative compliance (`python scripts/compliance_checker.py <target>`) before invoking review subagents.
- **DON'T**: Ask review subagents to perform trivial linter or style checks.
