---
name: code-review
description: >-
  Dispatches the 3 specialized code review subagents in parallel via invoke_subagent for qualitative review.
  Use this skill whenever the user asks to review code, run a code review, or perform an adversarial code audit.
---

# Automated Code Review Dispatcher (invoke_subagent)

A specialized orchestration runbook that dispatches the 3 qualitative code reviewer subagents concurrently in a single `invoke_subagent` tool call within clean isolated branches (`Workspace: 'branch'`).

---

## 1. Targeted Code Review Subagents (The Code Panel)

This dispatcher exclusively orchestrates the 3 code review specialists defined in `.agents/agents/`:
1. **`code-reviewer-design`**: Audits domain modeling honesty, single responsibility, and anti-overengineering.
2. **`code-reviewer-ergonomics`**: Audits narrative flow, cognitive friction, and 3 AM on-call comprehension.
3. **`code-reviewer-resilience`**: Audits unstated environmental assumptions, failure blast radiuses, and coupling.

---

## 2. Parallel Invocation Protocol

When code review is requested, the agent SHALL execute a single `invoke_subagent` tool call dispatching all 3 code reviewers simultaneously:

```json
{
  "Subagents": [
    {
      "TypeName": "code-reviewer-design",
      "Role": "Domain Abstraction Reviewer",
      "Model": "inherit",
      "Workspace": "branch",
      "Prompt": "Perform adversarial domain review on target code: <TARGET_PATH>. Focus on domain modeling and over-engineering."
    },
    {
      "TypeName": "code-reviewer-ergonomics",
      "Role": "Cognitive Ergonomics Reviewer",
      "Model": "inherit",
      "Workspace": "branch",
      "Prompt": "Perform adversarial readability review on target code: <TARGET_PATH>. Focus on 3 AM on-call comprehension."
    },
    {
      "TypeName": "code-reviewer-resilience",
      "Role": "Evolutionary Resilience Reviewer",
      "Model": "inherit",
      "Workspace": "branch",
      "Prompt": "Perform adversarial resilience review on target code: <TARGET_PATH>. Focus on unstated assumptions and coupling."
    }
  ]
}
```

---

## 3. Code Review Report Synthesis

After all 3 subagents report back from the background, aggregate their qualitative critiques into a unified report:

```markdown
# Consolidated Code Qualitative Review Report

## 1. Executive Verdict
- **Status**: [APPROVED | CONDITIONAL_PASS | REJECTED]
- **Risk Profile**: [LOW | MEDIUM | CRITICAL]
- **Synthesis**: Brief 2-3 sentence overview of code health.

## 2. Reviewer Findings
### A. Domain Modeling & Abstraction (`code-reviewer-design`)
- [Design Smell & Refactoring Direction]

### B. Cognitive Ergonomics & Readability (`code-reviewer-ergonomics`)
- [Cognitive Friction Point & Readable Alternative]

### C. Evolutionary Resilience & Coupling (`code-reviewer-resilience`)
- [Implicit Assumption & Hardening Direction]

## 3. Recommended Code Refactoring Checklist
- [ ] Refactoring item 1 (P0 Blocker)
- [ ] Refactoring item 2 (P1 Refinement)
```
