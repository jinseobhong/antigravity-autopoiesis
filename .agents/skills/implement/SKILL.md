---
name: implement
description:
  Executes implementation directly under Sovereign Authoring Posture: coordinates interface lockdown,
  primary direct authoring, companion test synthesis, optional read-only review panels, and preflight verification gates.
---

# Sovereign Engineering Implementation Pipeline Protocol (v5.0)

A deterministic, high-velocity engineering runbook enforcing the Sovereign Authoring Posture. The Primary Orchestrator directly authors production-grade code and companion test suites, maintaining zero-drift alignment with active contracts, while subagents serve exclusively as read-only qualitative reviewers.

---

## 1. Execution Routing Decision Matrix

Before proceeding, the primary orchestrator evaluates task complexity:

| Task Complexity Tier | Scope Criteria | Authoring Model | Quality Assurance Gate |
| :--- | :--- | :--- | :--- |
| **Tier 1: Atomic Edit** | Single-file tweak, < 100 lines | Direct Primary Execution | Automated lint & preflight check |
| **Tier 2: Feature Module** | Single module + tests, 100-300 lines | Direct Primary Authoring | 100% companion test pass + AST compliance |
| **Tier 3: Complex Subsystem** | Multi-file system, > 300 lines | Direct Authoring + Read-Only Review Panel | Multi-perspective read-only review + Full preflight |

---

## 2. Implementation & Verification Workflow

```mermaid
sequenceDiagram
    autonumber
    actor Operator as "Human Operator"
    participant Orch as "Primary Orchestrator (Sole Writer)"
    participant Rev as "review-implementation Panel (Read-Only)"
    participant Gate as "Preflight Gatekeeper (scripts/preflight_check.py)"
    participant Repo as "Repository Trunk"

    Note over Orch: "Phase 1: Interface Lockdown"
    Orch->>Orch: "Define Frozen Data Models & Protocols"

    Note over Orch: "Phase 2: Direct Implementation & Test Synthesis"
    Orch->>Orch: "Author Production Logic (H-CODE-1..12 Conformance)"
    Orch->>Orch: "Author Companion Test Suite (>= 30% Negative Assertions)"

    opt "Phase 3: Optional Qualitative Review (Tier 3 Only)"
        Orch->>Rev: "Dispatch Read-Only Reviewers (Architecture, Resilience, Ergonomics)"
        Rev-->>Orch: "Advisory Findings & Recommendations"
        Orch->>Orch: "Refactor Code to Address Valid Feedback"
    end

    Note over Orch, Gate: "Phase 4: Deterministic Hard Gate Verification"
    Orch->>Gate: "Run Preflight Check (Compliance, Topology, Regressions)"
    Gate-->>Orch: "PREFLIGHT PASS (Exit code 0)"

    Note over Orch, Repo: "Phase 5: Baseline Configuration Commit"
    Orch->>Repo: "git add <files> && git commit -m '...'"
    Orch->>Operator: "Milestone Verified & Committed"
```

---

## 3. Core Verification Commands

```bash
# 1. Run Companion Test Suite
python -m unittest discover tests/

# 2. Run AST Compliance Gate
python scripts/compliance_checker.py <target_files...>

# 3. Run Full Preflight Verification
python scripts/preflight_check.py --quick
```
