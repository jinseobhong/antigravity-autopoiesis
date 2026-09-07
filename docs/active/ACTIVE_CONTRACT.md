---
id: "CONTRACT-20260907-cortex-purification-and-grounding"
title: "Cortex Knowledge Purification and Shadow Grounding Engine Contract"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
target_task_id: "TASK-033"
---

# Active Engineering Contract: Cortex Knowledge Purification and Shadow Grounding Engine (TASK-033)

> [!NOTE]
> ### Document Scope & Governance Authority
> This binding contract defines the operational invariants, database schema constraints, and role-specialized grounding schemas for TASK-033.
> - **Operational Standard**: Antigravity Engineering Constitution (`GEMINI.md` Section 3.5).
> - **Target Task ID**: `TASK-033`
> - **Validation Gate**: `python scripts/validate_active_contract.py --task TASK-033`

---

## 1. Target Scope & File Bindings
- **Production Implementation**:
  - `core/shadow_grounding.py` (New module)
  - `core/defect_diagnostics.py` (Spam filter enhancement)
- **Database & Storage**:
  - `data/cortex.db` (Purge 175 spam rows, vacuum, rebuild FTS5)
- **Companion Test Suite**:
  - `tests/test_shadow_grounding.py` (New test suite, >= 30% negative assertion ratio)
- **Verification Gates**:
  - `scripts/compliance_checker.py`
  - `scripts/validate_active_contract.py`
  - `scripts/preflight_check.py`

---

## 2. Normative System Invariants (NASA Single-Thought Standard)
- **`[INV-GRD-01]`** `core/shadow_grounding.py` SHALL define immutable value objects `ShadowGroundingDirective`, `ShadowGroundingProfile`, `ShadowGroundingResult`.
- **`[INV-GRD-02]`** `core/shadow_grounding.py` SHALL query `data/cortex.db` using SQLite FTS5.
- **`[INV-GRD-03]`** `core/shadow_grounding.py` SHALL return role-specialized grounding blocks for `contrarian`, `red_team`, `complex_ai`.
- **`[INV-GRD-04]`** In-process grounding retrieval queries in `core/shadow_grounding.py` SHALL complete execution within a 15.0 millisecond SLA.
- **`[INV-GRD-05]`** `core/defect_diagnostics.py` SHALL reject generic preflight or test clearance strings lacking substantive root causes from being persisted into `episodic_events`.
- **`[INV-GRD-06]`** The episodic database `data/cortex.db` SHALL maintain zero records containing boilerplate strings `Investigate preflight check output` or `All verification gates cleared`.
- **`[INV-GRD-07]`** CLI command `python -m core.shadow_grounding --task "<task>" [--json]` SHALL return exit code 0 on success.
- **`[INV-GRD-08]`** All functions in `core/shadow_grounding.py` SHALL maintain cyclomatic complexity <= 10.
- **`[INV-GRD-09]`** All lines in `core/shadow_grounding.py` SHALL maintain length <= 120 columns.
- **`[INV-GRD-10]`** Companion test suite `tests/test_shadow_grounding.py` SHALL maintain an adversarial negative assertion ratio of at least 30 percent.

---

## 3. Data Models & Interface Schemas

### 3.1 Value Objects (`core/shadow_grounding.py`)
```python
@dataclass(frozen=True)
class ShadowGroundingDirective:
    component: str
    outcome: str
    directive: str
    solution: Optional[str] = None
    root_cause: Optional[str] = None

@dataclass(frozen=True)
class ShadowGroundingProfile:
    role: str
    directives: Tuple[ShadowGroundingDirective, ...]
    prompt_block: str

@dataclass(frozen=True)
class ShadowGroundingResult:
    task_query: str
    elapsed_ms: float
    profiles: Dict[str, ShadowGroundingProfile]
```

### 3.2 Public Engine Functions
```python
def get_shadow_grounding(
    task_query: str,
    roles: Sequence[str] = ("contrarian", "red_team", "complex_ai"),
    limit_per_role: int = 3,
    db_path: Optional[Path] = None,
) -> ShadowGroundingResult:
    ...
```
