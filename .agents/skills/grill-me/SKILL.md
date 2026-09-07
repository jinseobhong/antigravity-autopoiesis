---
name: grill-me
description:
  Dispatches the Socratic Interviewer subagent (socratic-interviewer) via invoke_subagent
  to conduct an in-depth requirements interview, resolve architectural decisions, and formulate
  the binding engineering contract draft for Orchestrator ratification.
---

# Socratic Requirements Interview & Active Contract Protocol (v2.0)

A deterministic, high-rigor engineering runbook delegating Socratic requirement interrogation to the specialized `socratic-interviewer` subagent via `invoke_subagent`. Under Sovereign Authoring, the subagent conducts the interactive interview, formulates the contract in memory, and transmits the complete draft to the Primary Orchestrator via IPC for atomic writing and ratification.

---

## 1. Dedicated Socratic Interviewer Subagent Dispatch Protocol

When an interactive design interview or `/grill-me` session is requested, the primary orchestrator dispatches the `socratic-interviewer` subagent:

```json
{
  "Subagents": [
    {
      "TypeName": "socratic-interviewer",
      "Role": "Socratic Requirements Advisor",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Perform deep Socratic requirement interrogation for: <TOPIC_OR_TASK_NAME>.\n--caller-id: <CALLER_CONVERSATION_ID>\n\nExecution Bounds & Protocol:\n1. Inspect existing codebase conventions, schemas, and configurations using view_file and grep_search before asking questions.\n2. Traverse the architectural decision tree one branch at a time using ask_question.\n3. Formulate the binding contract in memory conforming to the NASA Normative Lexicon (SHALL, SHALL NOT, MUST).\n4. Do NOT call write_to_file. Transmit the complete contract draft to the caller via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message='[CONTRACT_PROPOSED] ...') before completing your turn."
    }
  ]
}
```

---

## 2. Orchestrator Sovereign Materialization Protocol

Once `socratic-interviewer` transmits the contract draft via `send_message`:
1. **Sovereign Review & Materialization**:
   The primary orchestrator reviews the draft and writes it to `docs/active/ACTIVE_CONTRACT.md`.
2. **Deterministic Preflight Gate**:
   ```bash
   python scripts/validate_doc_preapproval.py docs/active/ACTIVE_CONTRACT.md
   python scripts/compliance_checker.py docs/active/ACTIVE_CONTRACT.md
   ```
3. **Operator Ratification**:
   The orchestrator presents the executive briefing in Korean to the human operator for ratification.
4. **State Ledger Transition**:
   Upon operator approval, the orchestrator transitions `docs/active/CURRENT_STATE.md` to `IN_PROGRESS`.
