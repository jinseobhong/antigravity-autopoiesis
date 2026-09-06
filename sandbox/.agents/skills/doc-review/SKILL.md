---
name: doc-review
description: >-
  Dispatches the 3 specialized technical writer subagents in parallel via invoke_subagent for qualitative review.
  Use this skill whenever the user asks to review technical documentation, audit specifications, or critique design docs.
---

# Automated Technical Documentation Review Dispatcher (invoke_subagent)

A specialized orchestration runbook that dispatches the 3 qualitative technical document reviewer subagents concurrently in a single `invoke_subagent` tool call within clean isolated branches (`Workspace: 'branch'`).

---

## 1. Targeted Technical Writer Subagents (The Doc Panel)

This dispatcher exclusively orchestrates the 3 documentation review specialists defined in `.agents/agents/`:
1. **`doc-reviewer-completeness`**: Audits what is NOT written: missing failure states, rollback voids, and blind spots.
2. **`doc-reviewer-dialectic`**: Audits logical consistency, challenges confirmation bias, and exposes hidden trade-off costs.
3. **`doc-reviewer-usability`**: Audits operational actionability, mistake-proofing, and high-stress runbook safety.

---

## 2. Parallel Invocation Protocol

When documentation review is requested, the agent SHALL execute a single `invoke_subagent` tool call dispatching all 3 document reviewers simultaneously:

```json
{
  "Subagents": [
    {
      "TypeName": "doc-reviewer-completeness",
      "Role": "Specification Completeness Reviewer",
      "Model": "inherit",
      "Workspace": "branch",
      "Prompt": "Perform adversarial completeness audit on target document: <TARGET_PATH>. Expose missing failure states and rollback voids."
    },
    {
      "TypeName": "doc-reviewer-dialectic",
      "Role": "Dialectical Logic Reviewer",
      "Model": "inherit",
      "Workspace": "branch",
      "Prompt": "Perform adversarial dialectic audit on target document: <TARGET_PATH>. Expose self-rationalization and trade-off gaps."
    },
    {
      "TypeName": "doc-reviewer-usability",
      "Role": "Operational Usability Reviewer",
      "Model": "inherit",
      "Workspace": "branch",
      "Prompt": "Perform adversarial usability audit on target document: <TARGET_PATH>. Expose ambiguous instructions and operational traps."
    }
  ]
}
```

---

## 3. Documentation Review Report Synthesis

After all 3 subagents report back from the background, aggregate their qualitative critiques into a unified report:

```markdown
# Consolidated Technical Documentation Review Report

## 1. Executive Verdict
- **Status**: [APPROVED | CONDITIONAL_PASS | REJECTED]
- **Specification Quality**: [LOW | MEDIUM | HIGH]
- **Synthesis**: Brief 2-3 sentence overview of document integrity.

## 2. Reviewer Findings
### A. Specification Completeness & Omissions (`doc-reviewer-completeness`)
- [Unwritten Failure State / Omitted Rollback]

### B. Dialectic Rigor & Trade-off Honesty (`doc-reviewer-dialectic`)
- [Logical Fallacy / Unexamined Trade-off]

### C. Operational Usability & Actionability (`doc-reviewer-usability`)
- [Operational Trap / Ambiguity Correction]

## 3. Required Document Revisions Checklist
- [ ] Revision item 1 (P0 Blocker)
- [ ] Revision item 2 (P1 Refinement)
```
