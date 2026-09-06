---
name: write-document
description:
  Dispatches the Lead Technical Writer subagent (technical-writer) via invoke_subagent
  to author, structure, and refactor NASA-grade technical documentation, ADRs, RFCs, and runbooks.
  Use this skill whenever the user asks to write documentation, create architecture guides, 
  design specs, ADRs, RFCs, or runbooks.
---

# NASA-Grade Technical Documentation Protocol (v2.0)

A deterministic, high-rigor engineering runbook that delegates documentation authoring to the specialized `technical-writer` subagent via `invoke_subagent`, featuring automated peer-review handoff.

---

## 1. Dedicated Technical Writer Subagent Dispatch Protocol

When technical documentation authoring is requested, the orchestrator SHALL dispatch the `technical-writer` subagent within the shared workspace (`Workspace: 'inherit'`):

> [!IMPORTANT]
> **Workspace Mode Invariant**: Authorship MUST use `Workspace: 'inherit'`. Using `Workspace: 'branch'` isolates files in an ephemeral git clone that is deleted upon subagent completion, causing silent data loss of the authored documentation.

### Dispatch Payload Template

```json
{
  "Subagents": [
    {
      "TypeName": "technical-writer",
      "Role": "Lead Technical Writer",
      "Model": "inherit",
      "Workspace": "inherit",
      "Prompt": "Author NASA-grade technical documentation for: <TOPIC_OR_SPEC>.\nTarget file: <TARGET_PATH> (default: docs/<PATH>.md).\n--caller-id: <CALLER_CONVERSATION_ID>\n\nGovernance & Rules:\n- Strictly enforce @.agents/rules/DOCUMENTATION_TONE.md (Fallback: repository tone in GEMINI.md)\n- Strictly enforce @.agents/rules/DOCUMENTATION_STANDARD.md (Fallback: repository standards in GEMINI.md)\n\nExecution Bounds & Protocol:\n1. Execute 5-Stage High-Rigor Pipeline: Discovery -> Framing -> Normative Synthesis -> Quantitative Modeling -> Quality Gate.\n2. Create necessary parent directories and write the draft to <TARGET_PATH>.\n3. Upon completion, notify the orchestrator via send_message(Recipient='<CALLER_CONVERSATION_ID>', Message='Document authored successfully at <TARGET_PATH>. Summary: <SUMMARY>') before completing your turn."
    }
  ]
}
```

---

## 2. 5-Stage High-Rigor Documentation Pipeline

### Stage 0: Discovery & Architecture Ingestion (Pre-Authoring)
1. **Codebase Inspection**: Inspect relevant source files, API routes, data models, and configurations before drafting.
2. **Contract Extraction**: Extract wire formats, parameter constraints, and error codes directly from existing implementation code.
3. **Prior Art & ADR Cross-Reference**: Inspect existing documentation in `docs/` or `.agents/` to ensure continuity and avoid contradicting existing ADRs.

### Stage 1: Archetype Framing & Provenance Binding
1. **Identify Archetype**: Determine if the requested artifact is an `ADR`, `RFC / Architecture Blueprint`, `Operational Runbook`, or `Incident Postmortem`.
2. **Bind Frontmatter**: Construct the mandatory YAML header (`id`, `title`, `status`, `owner`, `last_reviewed`, `supersedes`).
3. **Establish Boundary**: Define explicit "Goals" and "Non-Goals" to prevent scope creep.

### Stage 2: Normative Requirements Synthesis (The NASA Lexicon)
1. Formulate all functional constraints using the strict 5 normative keywords:
   - **`SHALL`**: Mandatory system behavioral requirement.
   - **`SHALL NOT`**: Critical negative constraint / forbidden failure mode.
   - **`MUST`**: Absolute data/protocol/wire invariant.
   - **`DO`**: Mandatory execution instruction for engineers.
   - **`DON'T`**: Explicit anti-pattern or prohibited practice.
2. Enforce the **Single-Thought Mandate**: Split any compound statements containing `and/or` into distinct atomic numbered requirements (`[REQ-xxx]`, `[CONSTR-xxx]`).

### Stage 3: Quantitative Modeling & C4 Diagramming
1. **C4 Architecture Diagrams**: Model system boundaries using Mermaid (Level 1 System Context and Level 2 Container topology). Sequence diagrams for asynchronous or distributed workflows.
2. **NFR Matrix**: Specify quantitative bounds for Throughput, P99 Latency, Availability, RTO/RPO, and graceful degradation paths.
3. **NASA V-Matrix**: Map each `SHALL` and `SHALL NOT` to a concrete verification method (`Test`, `Analysis`, `Inspection`, `Demonstration`).

### Stage 4: Deterministic Quality Gate Audit
Before presenting the completed document, execute the pre-publication audit checklist:
- [ ] **Frontmatter Validated**: `id`, `status` (`DRAFT`, `PROPOSED`, `ACCEPTED`), and `owner` present.
- [ ] **Anti-Handwaving Cleared**: Zero unquantified adjectives (`seamless`, `lightning-fast`, `infinitely scalable`).
- [ ] **NASA Syntax Conformance**: All binding requirements use `SHALL`, `SHALL NOT`, `MUST`, `DO`, `DON'T`.
- [ ] **Mermaid Syntax Valid**: Fenced with `mermaid`, all node labels with special characters enclosed in double quotes.
- [ ] **Link Integrity**: Single H1 header, clean section nesting, and all code references use valid `file:///` or relative links.
- [ ] **Trade-Offs Explicit**: Operational overhead, failure blast radius, and negative consequences documented.

---

## 3. Automated Handoff to Adversarial Peer Review (`review-documentation`)

Once the `technical-writer` finishes authoring the draft:
1. The draft artifact is persisted to `<TARGET_PATH>` in the shared repository.
2. The orchestrator SHALL automatically invoke the **`review-documentation`** skill to dispatch the 3 concurrent qualitative reviewers:
   - **`documentation-reviewer-completeness`**: Audits missing failure modes and unstated assumptions.
   - **`documentation-reviewer-dialectic`**: Audits logical consistency and trade-off honesty.
   - **`documentation-reviewer-usability`**: Audits operational ergonomics and step verification.
3. If peer review issues a `REJECTED` or `CONDITIONAL_PASS` verdict, the orchestrator enters an automated revision loop, feeding the remediation checklist back to `technical-writer` until `APPROVED`.