---
name: review-implementation
description:
  Dispatches the 3 specialized implementation review subagents in parallel via invoke_subagent for qualitative audit.
  Use this skill whenever the user asks to review code, run a code review, or perform an adversarial implementation audit.
---

# Automated Implementation Review Dispatcher (v2.0)

A production-hardened orchestration runbook that dispatches the 3 qualitative implementation reviewer subagents concurrently in a single `invoke_subagent` tool call within shared read-only workspaces (`Workspace: 'inherit'`).

---

## 1. Targeted Implementation Review Subagents (The Code Panel)

This dispatcher exclusively orchestrates the 3 implementation review specialists defined in `.agents/agents/`:
1. **`implementation-reviewer-domain`**: Audits domain abstraction honesty, value objects, ubiquitous language, and anti-speculative over-engineering (YAGNI).
2. **`implementation-reviewer-resilience`**: Audits concurrency races, resource leaks, unstated environmental assumptions, and error propagation voids.
3. **`implementation-reviewer-ergonomics`**: Audits narrative flow, cognitive friction, nesting depth, mutation transparency, and 3 AM on-call comprehension.

> [!IMPORTANT]
> **Registry Alignment Invariant**: The `TypeName` in `invoke_subagent` MUST strictly match the agent manifest filename registered in `.agents/agents/` (`implementation-reviewer-domain.md` $\rightarrow$ `TypeName: "implementation-reviewer-domain"`).

---

## 2. Pre-Flight Target Validation Protocol

Before dispatching subagents, the parent orchestrator MUST validate the target implementation to prevent resource waste and runtime crashes:

1. **Existence & Readability**: Verify that `<TARGET_PATH>` exists and is readable on the local filesystem.
2. **Source Code Check**: The target document MUST be a recognized source code file (`.py`, `.ts`, `.js`, `.go`, `.java`, `.cpp`, `.cs`, `.rs`, `.rb`, `.php`, etc.). Prohibit binaries, compiled archives, minified bundles, or non-text assets.
3. **File Size Boundaries**: File size MUST be within $10\text{ bytes} \le \text{size} \le 500\text{ KB}$ ($\le 1,000$ LOC target). Reject oversized dumps immediately with `E_INVALID_TARGET_CODE`.

---

## 3. Parallel Invocation Protocol (`invoke_subagent`)

### 3.1 Workspace Mode: `inherit`
Code review is strictly a read-only static analysis activity.
- **DO NOT USE** `Workspace: 'branch'`: Cloning git branches/worktrees introduces severe disk I/O, clone latency, and branch garbage for zero mutation isolation benefit.
- **ALWAYS USE** `Workspace: 'inherit'` to inspect source code in the shared workspace cleanly and efficiently.

### 3.2 Dispatch Payload Template

When implementation review is triggered, execute a single `invoke_subagent` call dispatching all 3 reviewers simultaneously:

```json
{
  "Subagents": [
    {
      "TypeName": "implementation-reviewer-domain",
      "Role": "Domain Abstraction Reviewer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Perform adversarial domain abstraction review on target code: <TARGET_PATH>.\n--caller-id: <CALLER_CONVERSATION_ID>\n\nExecution Bounds & Protocol:\n1. Inspect code strictly via view_file (bounded line ranges <= 800 lines). Do NOT invoke list_dir on parent directories.\n2. Classify all findings into: [P0 Blocker | P1 Major | P2 Advisory].\n3. Cite exact line coordinates ([<file>:L<start>-L<end>](file:///<path>#L<start>-L<end>)) and verbatim excerpts.\n4. Provide concrete, copy-pasteable unified diff (diff) blocks for every reported smell.\n5. If 100% compliant, output your formal Architecture Certification: PASSED.\n6. Relay findings directly to caller via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message='...') before finishing."
    },
    {
      "TypeName": "implementation-reviewer-resilience",
      "Role": "Evolutionary Resilience Reviewer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Perform adversarial resilience review on target code: <TARGET_PATH>.\n--caller-id: <CALLER_CONVERSATION_ID>\n\nExecution Bounds & Protocol:\n1. Inspect code strictly via view_file (bounded line ranges <= 800 lines). Do NOT invoke list_dir on parent directories.\n2. Classify all findings into: [P0 Blocker | P1 Major | P2 Advisory].\n3. Cite exact line coordinates ([<file>:L<start>-L<end>](file:///<path>#L<start>-L<end>)) and verbatim excerpts.\n4. Provide concrete, copy-pasteable unified diff (diff) blocks for every reported resilience defect.\n5. If 100% compliant, output your formal Resilience Certification: PASSED.\n6. Relay findings directly to caller via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message='...') before finishing."
    },
    {
      "TypeName": "implementation-reviewer-ergonomics",
      "Role": "Cognitive Ergonomics Reviewer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Perform adversarial ergonomics review on target code: <TARGET_PATH>.\n--caller-id: <CALLER_CONVERSATION_ID>\n\nExecution Bounds & Protocol:\n1. Inspect code strictly via view_file (bounded line ranges <= 800 lines). Do NOT invoke list_dir on parent directories.\n2. Classify all findings into: [P0 Blocker | P1 Major | P2 Advisory].\n3. Cite exact line coordinates ([<file>:L<start>-L<end>](file:///<path>#L<start>-L<end>)) and verbatim excerpts.\n4. Provide concrete, copy-pasteable unified diff (diff) blocks for every reported cognitive hazard.\n5. If 100% compliant, output your formal Ergonomics Certification: PASSED.\n6. Relay findings directly to caller via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message='...') before finishing."
    }
  ]
}
```

---

## 4. Asynchronous Barrier & Graceful Degradation Protocol

To prevent orchestrator deadlocks while waiting for background subagents:

1. **Timeout Ceiling**: The rendezvous timeout for all 3 subagents is **300 seconds**.
2. **Quorum Rules**:
   - **Full Quorum (3/3 Completed)**: Proceed directly to Full Report Synthesis.
   - **Degraded Quorum (2/3 Completed before timeout)**: Proceed to Degraded Report Synthesis. Explicitly annotate the missing reviewer section with `⚠️ [AGENT_TIMEOUT | AGENT_FAILED]` and set Executive Verdict to `CONDITIONAL_PASS` or `REJECTED`.
   - **Quorum Failure (< 2/3 Completed)**: Terminate workflow with `E_ORCHESTRATION_QUORUM_FAILED`. Do not issue an Executive Verdict.
3. **Deduplication**: If multiple reviewers flag the identical line coordinate with the same underlying defect, merge them into a single entry retaining the highest severity rating.

---

## 5. Deterministic Verdict Calculus

The Executive Verdict MUST NOT be subjectively assigned. Enforce this strict decision calculus:

| Defect Profile | Executive Verdict | Risk Profile | CI/CD Merge Policy |
| :--- | :--- | :--- | :--- |
| $\ge 1$ `P0 Blocker` OR $\ge 3$ `P1 Major` | **`REJECTED`** | **`CRITICAL`** | Block PR merge / block deployment immediately. |
| 0 `P0 Blocker` AND $1 - 2$ `P1 Major` | **`CONDITIONAL_PASS`** | **`MEDIUM`** | Merge blocked until Required Refactoring checklist items are completed. |
| 0 `P0 Blocker` AND 0 `P1 Major` (Advisories only) | **`APPROVED`** | **`LOW`** | Immediate merge permitted; P2 Advisories are optional polish. |

---

## 6. Report Persistence & Synthesis Template

Save the synthesized audit report artifact to:  
`<appDataDir>/brain/<conversation-id>/consolidated_implementation_review_report.md`

```markdown
# Consolidated Implementation Review Report

- **Target Code**: [`<filename>`](file:///<absolute_path>)
- **Timestamp**: YYYY-MM-DDTHH:MM:SSZ
- **Reviewers**: `implementation-reviewer-domain`, `implementation-reviewer-resilience`, `implementation-reviewer-ergonomics`

---

## 1. Executive Verdict
- **Status**: [APPROVED | CONDITIONAL_PASS | REJECTED]
- **Risk Profile**: [LOW | MEDIUM | CRITICAL]
- **Summary**: Concise 2-3 sentence synthesis of domain encapsulation, fault tolerance, and cognitive clarity.

---

## 2. Reviewer Findings

### A. Domain Modeling & Abstraction (`implementation-reviewer-domain`)
- 🚨 **Severity**: [P0 Blocker | P1 Major | P2 Advisory]
- 📍 **Location**: [`<filename>:L<start>-L<end>`](file:///<path>#L<start>-L<end>)
- 🔍 **Domain Modeling Defect**: ...
- 🧩 **Offending Code**:
  ```<lang>
  // Verbatim code extract
  ```
- 💥 **Architectural Risk**: ...
- 💡 **Domain Refactoring Proposal**:
  ```diff
  - // Offending code
  + // Clean domain replacement
  ```

### B. Evolutionary Resilience & Coupling (`implementation-reviewer-resilience`)
- 🚨 **Severity**: [P0 Blocker | P1 Major | P2 Advisory]
- 📍 **Location**: [`<filename>:L<start>-L<end>`](file:///<path>#L<start>-L<end>)
- 🔍 **Resilience Fault Line**: ...
- 🧩 **Offending Code**:
  ```<lang>
  // Verbatim code extract
  ```
- 💥 **Failure Blast Radius**: ...
- 💡 **Hardening Refactoring Proposal**:
  ```diff
  - // Brittle / leaky code
  + // Resilient replacement
  ```

### C. Cognitive Ergonomics & Readability (`implementation-reviewer-ergonomics`)
- 🚨 **Severity**: [P0 Blocker | P1 Major | P2 Advisory]
- 📍 **Location**: [`<filename>:L<start>-L<end>`](file:///<path>#L<start>-L<end>)
- 🔍 **Cognitive Friction Point**: ...
- 🧩 **Offending Code**:
  ```<lang>
  // Verbatim code extract
  ```
- 💥 **Mental Model Hazard**: ...
- 💡 **Readable Alternative**:
  ```diff
  - // Convoluted code
  + // Linear readable code
  ```

---

## 3. Recommended Code Refactoring Checklist
- [ ] [P0 Blocker] Description of critical blocker requiring immediate remediation
- [ ] [P1 Major] Description of required architectural or resilience fix
- [ ] [P2 Advisory] Optional readability or naming refinement
```
