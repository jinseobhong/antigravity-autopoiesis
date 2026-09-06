# Antigravity Lean Cortex: Physical System Blueprint (ARCHITECTURE.md)

This document establishes the definitive physical system blueprint for the Antigravity Lean Cortex platform.

---

## 1. Physical Architecture Topology

```text
+-------------------------------------------------------------------------+
|                           User / Orchestrator                           |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                  Lean Direct Execution Mode (GEMINI.md)                 |
|       - Sub-second turnaround, single-turn reasoning, zero swarm bloat   |
+-------------------------------------------------------------------------+
           |                                             |
           v                                             v
+-----------------------+                    +----------------------------+
| Physical Cortex Memory|                    |     Sandbox Confinement    |
| (core/cortex.py)      |                    |         (./sandbox/)       |
|  - SQLite DB storage  |                    +----------------------------+
|  - Ebbinghaus Decay   |                                  |
|  - Hebbian Plasticity |                                  v
|  - Sub-1ms Retrieval  |                    +----------------------------+
+-----------------------+                    |  In-Process Warm Runner    |
           |                                 |   (core/warm_runner.py)    |
           v                                 +----------------------------+
+-----------------------+                                  |
| Amnesia Immunity & JIT|                                  v
| Knowledge Persistence |                    +----------------------------+
+-----------------------+                    | 5-Tier Preflight Gatekeeper|
                                             | (scripts/preflight_check)  |
                                             |  - Flake8 == 0             |
                                             |  - AST Anti-Cheat H-CODE   |
                                             |  - 100% Companion Tests   |
                                             +----------------------------+
                                                           |
                                                           v
                                             +----------------------------+
                                             |  Sovereign User Promotion  |
                                             +----------------------------+
```

---

## 2. Core Subsystems

### 2.1 Physical Cortex Memory Engine (`core/cortex.py`)
- **Database Backend**: SQLite database file (`.agents/knowledge/cortex.db`) with WAL mode.
- **Episodic Store**: Records past defect resolutions, contexts, triggers, and directives.
- **Cognitive Decay**: Exponential Ebbinghaus retention $R(t) = S_0 \cdot \exp(-\Delta t / \tau)$.
- **Synaptic Plasticity**: Hebbian weight reinforcement $\Delta w = \eta \cdot (1 - w)$ on recall.
- **Retrieval Performance**: Lexical token matching with Jaccard normalization in < 1ms.

### 2.2 In-Process Warm Test Runner (`core/warm_runner.py`)
- Executes test suites in-process within the running Python runtime.
- Bypasses Windows `CreateProcessW` overhead, running 150+ tests in ~3 seconds.

### 2.3 Preflight Verification Gate (`scripts/preflight_check.py`)
- **Tier 1a**: Flake8 static analysis.
- **Tier 1b**: AST Anti-Cheat scanning (`H-CODE-1` through `H-CODE-12`).
- **Tier 1c**: Pure ASCII and Markdown documentation verification.
- **Tier 2**: Dynamic companion test discovery and execution.
