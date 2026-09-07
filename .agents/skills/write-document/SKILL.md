---
name: write-document
description:
  Dispatches the Lead Technical Writing Advisor (technical-writer) via invoke_subagent
  to analyze, structure, and synthesize NASA-grade technical documentation blueprints for Orchestrator authoring.
---

# NASA-Grade Technical Documentation Protocol (v3.0)

A deterministic engineering runbook delegating documentation synthesis to the specialized `technical-writer` advisory subagent via `invoke_subagent`. Under Sovereign Authoring, the subagent analyzes technical requirements and transmits complete markdown blueprints to the Primary Orchestrator via IPC for atomic authoring, verification, and commit.

---

## 1. Technical Writing Advisor Dispatch Protocol

When technical documentation authoring is requested, the orchestrator dispatches the `technical-writer` subagent:

```json
{
  "Subagents": [
    {
      "TypeName": "technical-writer",
      "Role": "Lead Technical Writing Advisor",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Formulate NASA-grade technical documentation blueprint for: <TOPIC_OR_SPEC>.\nTarget file: <TARGET_PATH>.\n--caller-id: <CALLER_CONVERSATION_ID>\n\nExecution Bounds & Protocol:\n1. Inspect codebase conventions, models, and prior ADRs using view_file and grep_search.\n2. Formulate complete documentation draft conforming to NASA SP-2016-6105 normative keywords and double-quoted Mermaid labels.\n3. Do NOT call write_to_file. Transmit the complete specification draft to caller via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message='[TECHNICAL_SPEC_PROPOSED] ...') before completing your turn."
    }
  ]
}
```

---

## 2. Orchestrator Sovereign Materialization Protocol

Once `technical-writer` transmits the specification draft via `send_message`:
1. **Sovereign Materialization**:
   The primary orchestrator writes the draft to `<TARGET_PATH>`.
2. **Deterministic Preflight Gate**:
   ```bash
   python scripts/validate_doc_preapproval.py <TARGET_PATH>
   python scripts/compliance_checker.py <TARGET_PATH>
   ```
3. **Peer Review Dispatch (Optional)**:
   For Tier 1/2 specifications, the orchestrator invokes the `review-documentation` skill for qualitative audit.
4. **SCM Baseline Commit**:
   The orchestrator commits the verified document to the repository trunk.
