"""
Subprocess Telemetry & Gradient Backpropagation Pipeline (core.backprop_pipeline).

Harvests execution friction, runtime constraints, falsified assumptions,
and local remedies from worker subprocesses, algorithmically backpropagating
them into persistent knowledge (data/cortex.db) and the active runtime
governance ledger (docs/active/CURRENT_STATE.md).
Conforms to:
- AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12
- [INV-BKP-01] through [INV-BKP-05]
- Fail-Open Zero-Crash Policy
"""

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_CORTEX_DB = Path("data/cortex.db")
DEFAULT_LEDGER_PATH = Path("docs/active/CURRENT_STATE.md")

INSERT_EVENT_SQL = """
INSERT INTO episodic_events (
    id, outcome, component, trigger_tokens, root_cause,
    directive, solution, validation, access_frequency,
    recency_weight, created_at, last_accessed_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
"""


# ==============================================================================
# 1. Typed Value Objects & Result Envelopes
# ==============================================================================

@dataclass(frozen=True)
class BackpropPayload:
    """Immutable gradient payload carrying execution telemetry and lessons."""

    task_id: str
    component: str = "core"
    invalidated_assumptions: List[str] = field(default_factory=list)
    discovered_constraints: List[str] = field(default_factory=list)
    applied_remedies: List[str] = field(default_factory=list)
    weight_deltas: Dict[str, float] = field(default_factory=dict)
    execution_success: bool = True

    def __post_init__(self) -> None:
        """Enforces mandatory non-empty task_id invariant."""
        if not self.task_id or not self.task_id.strip():
            raise ValueError("BackpropPayload.task_id must be a non-empty string.")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes payload to standard dictionary representation."""
        return {
            "task_id": self.task_id,
            "component": self.component,
            "invalidated_assumptions": list(self.invalidated_assumptions),
            "discovered_constraints": list(self.discovered_constraints),
            "applied_remedies": list(self.applied_remedies),
            "weight_deltas": dict(self.weight_deltas),
            "execution_success": self.execution_success,
        }


# ==============================================================================
# 2. Cortex Storage Persisters (Constraints & Remedies)
# ==============================================================================

def _insert_event_to_db(
    target_db: Path,
    outcome: str,
    component: str,
    trigger_tokens: str,
    directive: str,
    details: Optional[Dict[str, Optional[str]]] = None,
) -> None:
    """Inserts a single episodic event into SQLite with bounded timeout."""
    rand_suffix = "".join(random.choices("0123456789abcdef", k=8))
    event_id = f"evt_{int(time.time())}_{rand_suffix}"
    extra = details or {}
    root_cause = extra.get("root_cause")
    solution = extra.get("solution")
    validation = extra.get("validation")

    con = sqlite3.connect(str(target_db), timeout=0.2)
    try:
        with con:
            con.execute("PRAGMA busy_timeout = 200;")
            con.execute(
                INSERT_EVENT_SQL,
                (
                    event_id,
                    outcome,
                    component,
                    trigger_tokens,
                    root_cause,
                    directive,
                    solution,
                    validation,
                    1,
                    1.0,
                ),
            )
    finally:
        con.close()


def _persist_friction_and_remedies(
    payload: BackpropPayload,
    db_path: Optional[Path],
) -> Tuple[int, List[str]]:
    """Persists discovered constraints and applied remedies to cortex.db."""
    recorded_count = 0
    errors: List[str] = []
    target_db = Path(db_path or DEFAULT_CORTEX_DB)

    for constraint in payload.discovered_constraints:
        clean_c = str(constraint).strip()
        if not clean_c:
            continue
        try:
            _insert_event_to_db(
                target_db=target_db,
                outcome="FAILURE",
                component=payload.component,
                trigger_tokens=f"{payload.component} constraint {payload.task_id}",
                directive=f"Enforce constraint: {clean_c}",
                details={"root_cause": f"Runtime friction discovered during {payload.task_id}"},
            )
            recorded_count += 1
        except Exception as err:
            errors.append(f"Constraint persist error: {err}")

    for remedy in payload.applied_remedies:
        clean_r = str(remedy).strip()
        if not clean_r:
            continue
        try:
            _insert_event_to_db(
                target_db=target_db,
                outcome="SUCCESS",
                component=payload.component,
                trigger_tokens=f"{payload.component} remedy {payload.task_id}",
                directive=f"Apply remedy: {clean_r}",
                details={
                    "solution": clean_r,
                    "validation": f"Verified during task {payload.task_id}",
                },
            )
            recorded_count += 1
        except Exception as err:
            errors.append(f"Remedy persist error: {err}")

    return recorded_count, errors


def _adjust_recency_weights(
    weight_deltas: Dict[str, float],
    db_path: Optional[Path],
) -> Tuple[int, List[str]]:
    """Adjusts recency weights in cortex.db for specified target events or components."""
    if not weight_deltas:
        return 0, []

    target_db = Path(db_path or DEFAULT_CORTEX_DB)
    if not target_db.exists():
        return 0, [f"Target database not found: {target_db}"]

    adjusted_count = 0
    errors: List[str] = []

    try:
        con = sqlite3.connect(str(target_db), timeout=0.2)
        try:
            with con:
                con.execute("PRAGMA busy_timeout = 200;")
                for target_id, delta in weight_deltas.items():
                    cur = con.execute(
                        """
                        UPDATE episodic_events
                        SET recency_weight = MAX(0.0, recency_weight + ?),
                            last_accessed_at = CURRENT_TIMESTAMP
                        WHERE id = ? OR component = ?;
                        """,
                        (float(delta), str(target_id), str(target_id)),
                    )
                    adjusted_count += cur.rowcount
        finally:
            con.close()
    except (sqlite3.Error, OSError) as err:
        errors.append(f"Weight adjustment error: {err}")

    return adjusted_count, errors


# ==============================================================================
# 3. Epistemic Ledger Synchronization (CURRENT_STATE.md)
# ==============================================================================

def _transition_assumption_block(content: str, assumption_key: str, task_id: str) -> Tuple[str, bool]:
    """Transitions a single assumption entry from [ASSUMP] to [FACT] in markdown text."""
    clean_key = assumption_key.strip()
    id_pattern = re.compile(
        rf"(>[ \t]*\[!WARNING\][ \t]*\n"
        rf"[ \t]*>?[ \t]*###[ \t]+Working Assumption[ \t]+`\[{re.escape(clean_key)}\]`[^\n]*\n)"
        rf"((?:[ \t]*>[^\n]*\n)*)",
        re.MULTILINE,
    )

    def _replace_id(match: re.Match[str]) -> str:
        body = match.group(2)
        fact_key = clean_key.replace("ASSUMP", "FACT")
        new_head = f"> [!NOTE]\n> ### Validated Fact `[{fact_key}]` (Transitioned from {clean_key})\n"
        new_body = re.sub(
            r"-[ \t]*\*\*Assumption\*\*:",
            f"- **Validated Finding (Transitioned from {clean_key})**:",
            body,
        )
        return f"{new_head}{new_body}"

    new_content, count = id_pattern.subn(_replace_id, content, count=1)
    if count > 0:
        return new_content, True

    block_pattern = re.compile(
        rf"(>[ \t]*\[!WARNING\][ \t]*\n[ \t]*>?[ \t]*###[ \t]+Working Assumption[ \t]+`\[([^\]]+)\]`[^\n]*\n"
        rf"(?:[ \t]*>[^\n]*\n)*?"
        rf"{re.escape(clean_key)}"
        rf"(?:[ \t]*>[^\n]*\n)*)",
        re.MULTILINE,
    )

    def _replace_block(match: re.Match[str]) -> str:
        block_text = match.group(1)
        orig_id = match.group(2)
        fact_id = orig_id.replace("ASSUMP", "FACT")
        converted = re.sub(r">[ \t]*\[!WARNING\]", "> [!NOTE]", block_text)
        converted = re.sub(
            rf">?[ \t]*###[ \t]+Working Assumption[ \t]+`\[{re.escape(orig_id)}\]`",
            f"> ### Validated Fact `[{fact_id}]` (Transitioned from {orig_id})",
            converted,
        )
        converted = re.sub(
            r"-[ \t]*\*\*Assumption\*\*:",
            f"- **Validated Finding (Transitioned from {orig_id})**:",
            converted,
        )
        return converted

    new_content, count = block_pattern.subn(_replace_block, content, count=1)
    if count > 0:
        return new_content, True

    ledger_section = "## 6. Epistemic Ledger (Facts, Assumptions, Hypotheses)"
    if ledger_section in content:
        safe_suffix = re.sub(r"[^\w-]", "", task_id)
        new_fact_block = (
            f"\n> [!NOTE]\n"
            f"> ### Validated Fact `[FACT-AUTO-{safe_suffix}]`\n"
            f"> - **Source / Evidence**: Falsified assumption transitioned via task {task_id}.\n"
            f"> - **Validated Finding**: {clean_key}\n"
        )
        parts = content.split(ledger_section, 1)
        return parts[0] + ledger_section + "\n" + new_fact_block + parts[1], True

    return content, False


def _atomic_write_file(target_path: Path, content: str) -> None:
    """Executes atomic file write via temporary file replacement."""
    os.makedirs(target_path.parent, exist_ok=True)
    temp_target = target_path.with_suffix(f"{target_path.suffix}.tmp_{os.getpid()}_{int(time.time()*1000)}")
    try:
        with open(temp_target, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp_target, target_path)
    finally:
        if temp_target.exists():
            temp_target.unlink(missing_ok=True)


def _update_epistemic_ledger(
    invalidated_assumptions: Sequence[str],
    task_id: str,
    ledger_path: Optional[Path],
) -> Tuple[bool, List[str]]:
    """Updates docs/active/CURRENT_STATE.md transitioning [ASSUMP] to [FACT]."""
    if not invalidated_assumptions:
        return True, []

    target = Path(ledger_path or DEFAULT_LEDGER_PATH)
    if not target.exists():
        return False, [f"Ledger file not found: {target}"]
    if target.is_dir():
        return False, [f"Ledger path is a directory: {target}"]

    errors: List[str] = []
    try:
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()

        updated_content = content
        any_transition = False
        for assump in invalidated_assumptions:
            updated_content, transitioned = _transition_assumption_block(
                updated_content, str(assump), task_id
            )
            if transitioned:
                any_transition = True

        if any_transition:
            _atomic_write_file(target, updated_content)
            return True, []

        return False, ["No matching assumptions located in ledger"]
    except (OSError, UnicodeError) as err:
        errors.append(f"Epistemic ledger update failed: {err}")
        return False, errors


# ==============================================================================
# 4. Primary Backpropagation Functional API
# ==============================================================================

def backpropagate_gradient(
    payload: Optional[BackpropPayload],
    db_path: Optional[Path] = None,
    ledger_path: Optional[Path] = None,
) -> bool:
    """
    Backpropagates runtime telemetry into cortex.db and CURRENT_STATE.md.

    Persists discovered constraints and applied remedies into cortex.db,
    adjusts recency weights, and transitions invalidated assumptions into
    validated facts in the Epistemic Ledger.
    Guarantees fail-open zero-crash behavior returning False on failures.
    """
    if payload is None:
        return False

    accumulated_errors: List[str] = []

    # 1. Ingest constraints & remedies into cortex.db
    if payload.discovered_constraints or payload.applied_remedies:
        try:
            ev_count, ev_errs = _persist_friction_and_remedies(payload, db_path)
            accumulated_errors.extend(ev_errs)
        except Exception as err:
            accumulated_errors.append(f"Friction ingestion error: {err}")

    # 2. Recency weight adjustments
    if payload.weight_deltas:
        try:
            w_count, w_errs = _adjust_recency_weights(payload.weight_deltas, db_path)
            accumulated_errors.extend(w_errs)
        except Exception as err:
            accumulated_errors.append(f"Weight adjustment error: {err}")

    # 3. Epistemic Ledger update (transition [ASSUMP] to [FACT])
    if payload.invalidated_assumptions:
        try:
            l_updated, l_errs = _update_epistemic_ledger(
                payload.invalidated_assumptions, payload.task_id, ledger_path
            )
            accumulated_errors.extend(l_errs)
        except Exception as err:
            accumulated_errors.append(f"Ledger synchronization error: {err}")

    return len(accumulated_errors) == 0


# ==============================================================================
# 5. CLI Entrypoint
# ==============================================================================

def _build_cli_parser() -> argparse.ArgumentParser:
    """Constructs command line argument parser for backpropagation execution."""
    parser = argparse.ArgumentParser(
        prog="core.backprop_pipeline",
        description="Backpropagates execution telemetry and constraints into cortex.db and CURRENT_STATE.md",
    )
    parser.add_argument("--task-id", type=str, required=True, help="Task identifier")
    parser.add_argument("--component", type=str, default="core", help="Target component identifier")
    parser.add_argument("--constraint", type=str, action="append", default=[], help="Discovered constraint")
    parser.add_argument("--remedy", type=str, action="append", default=[], help="Applied remedy")
    parser.add_argument("--invalidate-assump", type=str, action="append", default=[], help="Invalidated assumption")
    parser.add_argument("--db", type=str, default=None, help="Custom cortex.db path")
    parser.add_argument("--ledger", type=str, default=None, help="Custom CURRENT_STATE.md path")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI execution entrypoint."""
    parser = _build_cli_parser()
    parsed = parser.parse_args(argv)

    payload = BackpropPayload(
        task_id=parsed.task_id,
        component=parsed.component,
        invalidated_assumptions=parsed.invalidate_assump,
        discovered_constraints=parsed.constraint,
        applied_remedies=parsed.remedy,
        weight_deltas={},
        execution_success=True,
    )

    db_path = Path(parsed.db) if parsed.db else None
    ledger_path = Path(parsed.ledger) if parsed.ledger else None

    success = backpropagate_gradient(payload, db_path=db_path, ledger_path=ledger_path)

    if parsed.json:
        out = {"success": success, "task_id": payload.task_id}
        sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    else:
        tag = "SUCCESS" if success else "FAILED"
        sys.stdout.write(f"[{tag}] Backpropagation complete for task {payload.task_id}\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
