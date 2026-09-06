---
name: "documentation_tone"
description: "Enforces NASA-grade normative lexicon (SHALL, SHALL NOT, MUST, DO, DON'T), epistemic honesty, and anti-handwaving tone standards for all technical writing."
globs:
  - "docs/**/*.md"
  - ".agents/rules/*.md"
  - ".agents/agents/*.md"
  - ".agents/skills/**/*.md"
---

# Enterprise Technical Documentation Tone & Manner (NASA Normative Standard)

This specification establishes mandatory linguistic, epistemic, and rhetorical standards for all technical documentation, architecture blueprints, decision records, and operational guides.

---

## 1. The 5 Normative Directives (The NASA Lexicon)

All technical requirements, operational commands, and engineering constraints MUST use one of the five canonical normative keywords. No other ambiguous modals (e.g., "should probably", "is recommended to", "might") are permitted for binding specifications.

| Keyword | Target Domain | Binding Level | Definition & Operational Impact |
| :--- | :---: | :---: | :--- |
| **`SHALL`** | **System / Software** | **Mandatory** | Absolute behavioral requirement of the system. Failure to satisfy blocks deployment and release. |
| **`SHALL NOT`** | **System / Software** | **Prohibitive** | Critical negative constraint. Defines system behaviors that must never occur under any circumstance. |
| **`MUST`** | **Data / Protocol** | **Absolute Invariant** | Non-negotiable physical, mathematical, cryptographic, or wire-protocol invariants. |
| **`DO`** | **Human / Agent** | **Action Directive** | Mandatory execution instruction for engineers, operators, and runbook executors. |
| **`DON'T`** | **Human / Agent** | **Strict Prohibition** | Explicit engineering anti-pattern, dangerous operational shortcut, or prohibited practice. |

### Syntactic Examples
- `[REQ-001]` The Gateway **SHALL** terminate TLS 1.3 connections within 10 milliseconds of handshake initiation.
- `[REQ-002]` The Identity Service **SHALL NOT** persist plaintext credentials or unmasked tokens in any persistent store or log sink.
- `[INV-001]` All intra-cluster payload envelopes **MUST** conform to Protobuf v3 schema definitions.
- **DO**: Validate array bounds and null pointer guards prior to memory dereference.
- **DON'T**: Catch generic exceptions (`catch (Exception e)`) without rethrowing or logging structured contextual telemetry.

---

## 2. The Atomicity Rule (Single-Thought Mandate)

Compound requirements joined by coordinating conjunctions (`and`, `or`, `as well as`, `along with`) are **STRICTLY PROHIBITED** within a single normative statement.

- **Non-Compliant (Compound)**:
  > The StorageEngine SHALL compress blocks with ZSTD and stream them to S3 within 2 seconds.
- **Compliant (Atomic)**:
  > - `[REQ-STOR-01]` The StorageEngine **SHALL** compress all blocks exceeding 64KB using ZSTD level 3.
  > - `[REQ-STOR-02]` The StorageEngine **SHALL** upload compressed blocks to the object store within 2,000 milliseconds of compaction completion.

---

## 3. Epistemic Calibration & Anti-Handwaving

Technical writing MUST exhibit total scientific integrity. Vague adjectives and subjective assertions degrade system safety.

### Prohibited Lexicon (Banned Handwaving)
The following terms are **FORBIDDEN** unless accompanied by quantified empirical bounds:
- `seamless`, `effortless`, `blazing-fast`, `lightning-fast`, `infinitely scalable`, `robust`, `ultra-low latency`, `easy to use`.

### Empirical Boundary Invariant
Every performance or capability claim MUST specify exact operational boundaries:
- **Forbidden**: "The cache provides ultra-low latency reads."
- **Mandatory**: "The cache **SHALL** serve 99.9% of read requests in $< 2\text{ms}$ up to 50,000 QPS with a memory footprint $\le 8\text{GB}$."

### Epistemic Classification
Every major architectural statement MUST be explicitly categorized:
1. **Validated Fact**: Confirmed via benchmark, production telemetry, or mathematical proof (MUST cite source).
2. **Working Assumption**: Unverified baseline dependency (MUST identify downstream risk and validation plan).
3. **Hypothesis**: Proposed approach pending experimentation (MUST state measurable falsification criteria).

---

## 4. Multi-Tier Audience Partitioning

Documents MUST support dual reading velocities to serve both executive decision-makers and on-call engineers:

1. **Executive Fast-Path (< 60 Seconds)**:
   - Placed immediately after document metadata.
   - Summarizes: The core problem, the chosen architectural posture, irreversible financial/operational trade-offs, and residual risks.
2. **Engineering Deep-Path (Full Technical Depth)**:
   - Uncompromising technical rigor: wire protocols, failure blast radiuses, race conditions, and deterministic rollback mechanics.

---

## 5. Defensive Trade-Off Rhetoric

No architecture is universally superior. Every document proposing a design MUST document:
- **Operational Tax**: Added operational overhead (e.g., cluster maintenance, observability cost).
- **Failure Blast Radius**: Worst-case cascading failure modes when downstream dependencies fail or partition.
- **Degradation Mechanics**: How the system intentionally degrades under overload (shedding load, dropping to read-only mode).
