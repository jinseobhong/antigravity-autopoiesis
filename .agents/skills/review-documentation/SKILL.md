---
name: review-documentation
description: 
  Dispatches the 3 specialized technical documentation review subagents in parallel via invoke_subagent for qualitative audit.
  Use this skill whenever the user asks to review technical documentation, audit specifications, or critique design docs.
---

# Automated Technical Documentation Review Dispatcher (v2.0)

A production-hardened orchestration runbook that dispatches the 3 qualitative documentation reviewer subagents concurrently in a single `invoke_subagent` tool call within shared read-only workspaces (`Workspace: 'inherit'`).

---

## 1. Targeted Documentation Review Subagents (The Doc Panel)

This dispatcher exclusively orchestrates the 3 documentation review specialists defined in `.agents/agents/`:
1. **`documentation-reviewer-completeness`**: Audits what is NOT written: missing failure states, unstated assumptions, security voids, and rollback gaps.
2. **`documentation-reviewer-dialectic`**: Audits logical integrity, challenges confirmation bias, self-rationalization, and exposes hidden architectural costs.
3. **`documentation-reviewer-usability`**: Audits operational actionability, command ambiguity, mistake-proofing, and high-stress runbook safety.

> [!IMPORTANT]
> **Registry Alignment Invariant**: The `TypeName` in `invoke_subagent` MUST strictly match the agent manifest filename registered in `.agents/agents/` (`documentation-reviewer-completeness.md` $\rightarrow$ `TypeName: "documentation-reviewer-completeness"`).

---

## 2. Pre-Flight Target Validation Protocol

Before dispatching subagents, the parent orchestrator MUST validate the target document to prevent resource waste and runtime crashes:

1. **Existence & Readability**: Verify that `<TARGET_PATH>` exists and is readable on the local filesystem.
2. **Content-Type Check**: The target document MUST be a UTF-8 encoded text or markdown file (`.md`, `.markdown`, `.txt`, `.adoc`, `.rst`). Prohibit binary, archive, compiled, or media files.
3. **File Size Boundaries**: File size MUST be within $10\text{ bytes} \le \text{size} \le 500\text{ KB}$. Empty files or massive non-specification dumps MUST be rejected immediately with `E_INVALID_TARGET_DOCUMENT`.

---

## 3. Parallel Invocation Protocol (`invoke_subagent`)

### 3.1 Workspace Mode: `inherit`
Documentation review is strictly a read-only static text analysis activity. 
- **DO NOT USE** `Workspace: 'branch'`: Cloning git branches/worktrees introduces severe disk I/O, clone latency, and branch garbage for zero mutation isolation benefit.
- **ALWAYS USE** `Workspace: 'inherit'` to inspect documents in the shared workspace cleanly and efficiently.

### 3.2 Dispatch Payload Template

When documentation review is triggered, execute a single `invoke_subagent` call dispatching all 3 reviewers simultaneously:

```json
{
  "Subagents": [
    {
      "TypeName": "documentation-reviewer-completeness",
      "Role": "Specification Completeness Reviewer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Perform adversarial completeness audit on target document: <TARGET_PATH>.\n--caller-id: <CALLER_CONVERSATION_ID>\n\nExecution Bounds & Protocol:\n1. Inspect document strictly via view_file (bounded line ranges <= 800 lines). Do NOT invoke list_dir on parent directories.\n2. Classify all findings into: [P0 Blocker | P1 Major | P2 Advisory].\n3. Cite exact line coordinates ([<file>:L<start>-L<end>](file:///<path>#L<start>-L<end>)) and verbatim excerpts.\n4. If 100% compliant, output your formal Clean-Pass Certification.\n5. Relay findings directly to caller via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message='...') before finishing."
    },
    {
      "TypeName": "documentation-reviewer-dialectic",
      "Role": "Dialectical Logic Reviewer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Perform adversarial dialectic audit on target document: <TARGET_PATH>.\n--caller-id: <CALLER_CONVERSATION_ID>\n\nExecution Bounds & Protocol:\n1. Inspect document strictly via view_file (bounded line ranges <= 800 lines). Do NOT invoke list_dir on parent directories.\n2. Classify all findings into: [P0 Blocker | P1 Major | P2 Advisory].\n3. Cite exact line coordinates ([<file>:L<start>-L<end>](file:///<path>#L<start>-L<end>)) and verbatim excerpts.\n4. If 100% compliant, output your formal Clean-Pass Certification.\n5. Relay findings directly to caller via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message='...') before finishing."
    },
    {
      "TypeName": "documentation-reviewer-usability",
      "Role": "Operational Usability Reviewer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Perform adversarial usability audit on target document: <TARGET_PATH>.\n--caller-id: <CALLER_CONVERSATION_ID>\n\nExecution Bounds & Protocol:\n1. Inspect document strictly via view_file (bounded line ranges <= 800 lines). Do NOT invoke list_dir on parent directories.\n2. Classify all findings into: [P0 Blocker | P1 Major | P2 Advisory].\n3. Cite exact line coordinates ([<file>:L<start>-L<end>](file:///<path>#L<start>-L<end>)) and verbatim excerpts.\n4. If 100% compliant, output your formal Clean-Pass Certification.\n5. Relay findings directly to caller via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message='...') before finishing."
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

| Defect Profile | Executive Verdict | Specification Quality | CI/CD Merge Policy |
| :--- | :--- | :--- | :--- |
| $\ge 1$ `P0 Blocker` OR $\ge 3$ `P1 Major` | **`REJECTED`** | **`LOW`** | Block merge / block deployment immediately. |
| 0 `P0 Blocker` AND $1 - 2$ `P1 Major` | **`CONDITIONAL_PASS`** | **`MEDIUM`** | Merge blocked until Required Revision checklist items are completed. |
| 0 `P0 Blocker` AND 0 `P1 Major` (Advisories only) | **`APPROVED`** | **`HIGH`** | Immediate merge permitted; P2 Advisories are optional polish. |

---

## 6. Report Persistence & Synthesis Template

Save the synthesized audit report artifact to:  
`<appDataDir>/brain/<conversation-id>/consolidated_doc_review_report.md`

```markdown
# Consolidated Technical Documentation Review Report

- **Target Document**: [`<filename>`](file:///<absolute_path>)
- **Timestamp**: YYYY-MM-DDTHH:MM:SSZ
- **Reviewers**: `documentation-reviewer-completeness`, `documentation-reviewer-dialectic`, `documentation-reviewer-usability`

---

## 1. Executive Verdict
- **Status**: [APPROVED | CONDITIONAL_PASS | REJECTED]
- **Specification Quality**: [HIGH | MEDIUM | LOW]
- **Summary**: Concise 2-3 sentence synthesis of structural integrity, failure boundaries, and dialectical rigor.

---

## 2. Reviewer Findings

### A. Specification Completeness & Blind Spots (`documentation-reviewer-completeness`)
- 🚨 **Severity**: [P0 Blocker | P1 Major | P2 Advisory]
- 📍 **Location**: [`<filename>:L<start>-L<end>`](file:///<path>#L<start>-L<end>)
- 🔍 **Omitted Failure Mode / Void**: ...
- 💥 **Production Risk**: ...
- 💡 **Required Addition**: ...

### B. Dialectic Rigor & Trade-off Honesty (`documentation-reviewer-dialectic`)
- 🚨 **Severity**: [P0 Blocker | P1 Major | P2 Advisory]
- 📍 **Location**: [`<filename>:L<start>-L<end>`](file:///<path>#L<start>-L<end>)
- 🔍 **Logical Fallacy / Bias**: ...
- 💥 **Hidden Architectural Cost**: ...
- 💡 **Required Dialectical Defense**: ...

### C. Operational Usability & Actionability (`documentation-reviewer-usability`)
- 🚨 **Severity**: [P0 Blocker | P1 Major | P2 Advisory]
- 📍 **Location**: [`<filename>:L<start>-L<end>`](file:///<path>#L<start>-L<end>)
- 🔍 **Operational Ambiguity / Trap**: ...
- 💥 **Execution Risk**: ...
- 💡 **Concrete Actionable Correction**: ...

---

## 3. Required Document Revisions Checklist
- [ ] [P0 Blocker] Description of critical blocker requiring immediate remediation
- [ ] [P1 Major] Description of required architectural or operational addition
- [ ] [P2 Advisory] Optional clarity or stylistic refinement
```
