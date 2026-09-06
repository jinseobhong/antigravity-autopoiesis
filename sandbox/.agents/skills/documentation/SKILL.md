---
name: documentation
description: >-
  Dispatches the Lead Technical Writer subagent (technical-writer) via invoke_subagent
  to author, structure, and refactor NASA-grade technical documentation, ADRs, RFCs, and runbooks.
  Use this skill whenever the user asks to write documentation, create architecture guides, 
  design specs, ADRs, RFCs, or runbooks.
---

# NASA-Grade Technical Documentation Protocol (Author Dispatcher)

A deterministic, high-rigor engineering runbook that delegates documentation authoring to the specialized `technical-writer` subagent via `invoke_subagent`.

---

## 1. Dedicated Technical Writer Subagent Dispatch Protocol

When technical documentation authoring is requested, the orchestrator SHALL dispatch the `technical-writer` subagent in an isolated workspace:

```json
{
  "Subagents": [
    {
      "TypeName": "technical-writer",
      "Role": "Lead Technical Writer",
      "Model": "inherit",
      "Workspace": "branch",
      "Prompt": "Author NASA-grade technical documentation for: <TOPIC_OR_SPEC>. Target file: sandbox/docs/<PATH>.md. Strictly enforce @.agents/rules/DOCUMENTATION_TONE.md and @.agents/rules/DOCUMENTATION_STANDARD.md."
    }
  ]
}
```

---

## 2. 4-Stage High-Rigor Documentation Pipeline

### Stage 1: Archetype Framing & Provenance Binding
1. **Identify Archetype**: Determine if the requested artifact is an `ADR`, `RFC / Blueprint`, `Runbook`, or `Postmortem`.
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

## 3. Handoff to Adversarial Peer Review (`doc-review`)

Once the `technical-writer` finishes authoring the draft:
1. The draft artifact is persisted to `sandbox/docs/`.
2. The orchestrator SHALL offer or automatically invoke the `doc-review` skill to trigger the 3 concurrent reviewer subagents (`completeness`, `dialectic`, `usability`) for peer review before final promotion.
