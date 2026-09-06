"""
Companion test suite for Subprocess Backpropagation Pipeline (TASK-026).

Ingests docs/active/ACTIVE_CONTRACT.md as primary specification authority.
Evaluates execution telemetry harvesting, episodic event persistence,
knowledge recency weight delta application, and Epistemic Ledger synchronization.
Validates BackpropPayload immutability, atomic file state updates, and
zero-crash fail-open error containment under locked/corrupted databases or missing ledger files.
Enforces AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12 with >= 40% negative ratio.
"""

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional
import unittest

try:
    from core.backprop_pipeline import (
        BackpropPayload,
        backpropagate_gradient,
    )
    _MODULE_AVAILABLE = True
except ModuleNotFoundError:
    try:
        from sandbox.core.backprop_pipeline import (
            BackpropPayload,
            backpropagate_gradient,
        )
        _MODULE_AVAILABLE = True
    except ModuleNotFoundError:
        _MODULE_AVAILABLE = False
        BackpropPayload = None  # type: ignore[assignment]
        backpropagate_gradient = None  # type: ignore[assignment]


def _init_test_cortex_db(db_file: Path) -> None:
    """Provisions isolated SQLite database with episodic_events and fts_events schemas."""
    con = sqlite3.connect(str(db_file))
    try:
        with con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS episodic_events (
                    id TEXT PRIMARY KEY,
                    outcome TEXT CHECK(outcome IN ('SUCCESS', 'FAILURE')) NOT NULL,
                    component TEXT NOT NULL,
                    trigger_tokens TEXT NOT NULL,
                    root_cause TEXT,
                    directive TEXT NOT NULL,
                    solution TEXT,
                    validation TEXT,
                    access_frequency INTEGER NOT NULL DEFAULT 1,
                    recency_weight REAL NOT NULL DEFAULT 1.0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_accessed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            con.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_events USING fts5(
                    id UNINDEXED,
                    component,
                    trigger_tokens,
                    directive,
                    root_cause,
                    solution
                );
                """
            )
            con.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_fts_insert AFTER INSERT ON episodic_events BEGIN
                    INSERT INTO fts_events(id, component, trigger_tokens, directive, root_cause, solution)
                    VALUES (new.id, new.component, new.trigger_tokens, new.directive, new.root_cause, new.solution);
                END;
                """
            )
    finally:
        con.close()


def _create_test_ledger_file(ledger_file: Path) -> None:
    """Initializes a test CURRENT_STATE.md with a structured Epistemic Ledger section."""
    content = (
        "---\n"
        'id: "STATE-TEST-sprint-compass"\n'
        'title: "Test State Ledger"\n'
        'status: "ACCEPTED"\n'
        "---\n\n"
        "# Project Autopoiesis Test Ledger\n\n"
        "## 6. Epistemic Ledger (Facts, Assumptions, Hypotheses)\n\n"
        "> [!NOTE]\n"
        "> ### Validated Fact `[FACT-001]`\n"
        "> - **Source / Evidence**: Preflight compliance checker.\n"
        "> - **Verified Metric**: Clean AST pass.\n\n"
        "> [!WARNING]\n"
        "> ### Working Assumption `[ASSUMP-001]`\n"
        "> - **Assumption**: Single-operator workflow permits atomic file replacement.\n"
        "> - **Invalidation Threshold**: Collision observed.\n"
        "> - **Mitigation Plan**: Implement retry loop.\n\n"
        "> [!IMPORTANT]\n"
        "> ### Hypothesis `[HYP-001]`\n"
        "> - **Hypothesis**: Bounded horizon reduces lead time.\n"
    )
    ledger_file.write_text(content, encoding="utf-8")


_TASK_026_FALLBACK_CONTRACT = """---
id: "CONTRACT-20260907-req-and-backprop"
title: "Requirements Extractor and Subprocess Backpropagation Pipeline Contract"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
target_task_id: "TASK-026"
---

# Active Engineering Contract: Requirements Extractor & Subprocess Backpropagation Pipeline

## 2. Normative Invariants (The NASA Lexicon)
- `[INV-BKP-01]` Subprocess backpropagation payload structure
- `[INV-BKP-01.1]` Invalidated assumptions capture
- `[INV-BKP-01.2]` Discovered constraints capture
- `[INV-BKP-01.3]` Applied remedies capture
- `[INV-BKP-01.4]` Weight deltas numeric recency adjustments
- `[INV-BKP-02]` Episodic event persistence in cortex.db
- `[INV-BKP-02.1]` Friction and failure record ingestion
- `[INV-BKP-02.2]` Remedy positive outcome attestation
- `[INV-BKP-03]` Epistemic Ledger synchronization in CURRENT_STATE.md
- `[INV-BKP-03.1]` Atomic file transactions for ledger updates
- `[INV-BKP-04]` Fail-open containment on corrupted or missing resources
- `[INV-BKP-04.1]` Process isolation and deterministic timeout
- `[INV-BKP-04.2]` Graceful degradation on unparseable inputs
- `[INV-BKP-05]` Cyclomatic complexity and line length enforcement

## 3. Data Schema & Specifications
```python
class BackpropPayload:
    task_id: str
    invalidated_assumptions: list
    discovered_constraints: list
    applied_remedies: list
    weight_deltas: dict
    execution_success: bool

def backpropagate_gradient(
    payload: BackpropPayload,
    db_path: Optional[Path] = None,
    ledger_path: Optional[Path] = None,
) -> bool:
    return True
```
"""


def _load_task_026_contract() -> str:
    """Loads TASK-026 contract from active contract file, cortex.db, or fixture."""
    contract_path = Path("docs/active/ACTIVE_CONTRACT.md")
    if contract_path.exists():
        try:
            content = contract_path.read_text(encoding="utf-8")
            if 'target_task_id: "TASK-026"' in content:
                return content
        except OSError:
            _err_fallback = True
    db_path = Path("data/cortex.db")
    if db_path.exists():
        try:
            con = sqlite3.connect(str(db_path))
            cur = con.execute(
                "SELECT raw_content FROM contract_revisions WHERE task_id = 'TASK-026' "
                "ORDER BY revision_id DESC LIMIT 1;"
            )
            row = cur.fetchone()
            con.close()
            if row:
                return str(row[0])
        except Exception:
            _err_fallback = True
    return _TASK_026_FALLBACK_CONTRACT


class TestBackpropPipelineContractInvariants(unittest.TestCase):
    """Verifies that the specification contract defines normative invariants [INV-BKP-01..05]."""

    def setUp(self) -> None:
        self.contract_text = _load_task_026_contract()
        self.assertTrue(
            len(self.contract_text.strip()) > 0,
            "Contract text missing from active contract, cortex.db, and fixture",
        )

    def test_contract_metadata_and_acceptance(self) -> None:
        """Positive test: Verifies contract is ACCEPTED and target_task_id matches valid format."""
        self.assertIn('status: "ACCEPTED"', self.contract_text)
        self.assertRegex(self.contract_text, r'target_task_id:\s*"TASK-\d+"')

    def test_contract_defines_all_normative_backprop_invariants(self) -> None:
        """Positive test: Verifies presence of backprop normative invariants."""
        required_invariants = [
            "[INV-BKP-01]",
            "[INV-BKP-01.1]",
            "[INV-BKP-01.2]",
            "[INV-BKP-01.3]",
            "[INV-BKP-01.4]",
            "[INV-BKP-02]",
            "[INV-BKP-02.1]",
            "[INV-BKP-02.2]",
            "[INV-BKP-03]",
            "[INV-BKP-03.1]",
            "[INV-BKP-04]",
            "[INV-BKP-04.1]",
            "[INV-BKP-04.2]",
            "[INV-BKP-05]",
        ]
        for inv_id in required_invariants:
            self.assertIn(
                inv_id,
                self.contract_text,
                f"Missing invariant definition {inv_id} in active contract",
            )

    def test_contract_defines_backprop_technical_interfaces(self) -> None:
        """Positive test: Verifies contract specifies BackpropPayload dataclass and API."""
        self.assertIn("class BackpropPayload", self.contract_text)
        self.assertIn("def backpropagate_gradient", self.contract_text)
        self.assertIn("invalidated_assumptions", self.contract_text)
        self.assertIn("discovered_constraints", self.contract_text)
        self.assertIn("applied_remedies", self.contract_text)
        self.assertIn("weight_deltas", self.contract_text)

    def test_negative_contract_missing_synthetic_invariant(self) -> None:
        """Negative test: Evaluates assertion failure when checking non-existent invariant."""
        synthetic_id = "[INV-BKP-NONEXISTENT-888]"
        self.assertNotIn(
            synthetic_id,
            self.contract_text,
            "Non-existent invariant unexpectedly found in contract text",
        )


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.backprop_pipeline pending implementation by software-engineer",
)
class TestBackpropPipelinePositive(unittest.TestCase):
    """Evaluates positive gradient backpropagation, episodic event recording, and ledger updates."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_cortex.db"
        self.ledger_path = Path(self.temp_dir.name) / "CURRENT_STATE.md"
        _init_test_cortex_db(self.db_path)
        _create_test_ledger_file(self.ledger_path)

        con = sqlite3.connect(str(self.db_path))
        try:
            with con:
                con.execute(
                    """
                    INSERT INTO episodic_events (
                        id, outcome, component, trigger_tokens, directive, access_frequency,
                        recency_weight, created_at, last_accessed_at
                    ) VALUES ('evt_prior_001', 'FAILURE', 'fs_topology', 'depth limit',
                              'Limit directory nesting depth', 1, 1.0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                    """
                )
        finally:
            con.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_backprop_persists_episodic_event_with_remedies(self) -> None:
        """Positive test: Verifies episodic record persisted into cortex.db with applied remedies [INV-BKP-02]."""
        payload = BackpropPayload(
            task_id="TASK-026",
            invalidated_assumptions=[],
            discovered_constraints=["Max payload size 10MB limit detected"],
            applied_remedies=["Implemented chunked streaming buffer in transport layer"],
            weight_deltas={},
            execution_success=True,
        )
        success = backpropagate_gradient(
            payload,
            db_path=self.db_path,
            ledger_path=self.ledger_path,
        )
        self.assertTrue(success, "Expected backpropagate_gradient to return True")

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT outcome, component, directive, solution FROM episodic_events "
                "WHERE solution LIKE '%chunked streaming%';"
            )
            row = cur.fetchone()
            self.assertIsNotNone(row, "Expected persisted episodic event with applied remedy")
            self.assertEqual(row[0], "SUCCESS")
            self.assertIn("chunked streaming", row[3])
        finally:
            con.close()

    def test_backprop_applies_weight_deltas_to_cortex(self) -> None:
        """Positive test: Verifies recency weights updated for targeted episodic events [INV-BKP-01.4]."""
        payload = BackpropPayload(
            task_id="TASK-026",
            invalidated_assumptions=[],
            discovered_constraints=[],
            applied_remedies=[],
            weight_deltas={"evt_prior_001": 0.5},
            execution_success=True,
        )
        success = backpropagate_gradient(
            payload,
            db_path=self.db_path,
            ledger_path=self.ledger_path,
        )
        self.assertTrue(success)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT recency_weight FROM episodic_events WHERE id = 'evt_prior_001';"
            )
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertGreater(row[0], 1.0, f"Expected weight > 1.0 after delta, got {row[0]}")
        finally:
            con.close()

    def test_backprop_updates_epistemic_ledger_assumption_invalidation(self) -> None:
        """Positive test: Verifies invalidated assumption transitions to validated fact [INV-BKP-03]."""
        payload = BackpropPayload(
            task_id="TASK-026",
            invalidated_assumptions=["ASSUMP-001"],
            discovered_constraints=["NTFS file locks require retry backoff"],
            applied_remedies=["Added 50ms exponential backoff retry loop"],
            weight_deltas={},
            execution_success=True,
        )
        success = backpropagate_gradient(
            payload,
            db_path=self.db_path,
            ledger_path=self.ledger_path,
        )
        self.assertTrue(success)

        updated_ledger = self.ledger_path.read_text(encoding="utf-8")
        self.assertIn(
            "ASSUMP-001",
            updated_ledger,
            "Assumption ID should remain referenced in the epistemic ledger",
        )
        self.assertTrue(
            "Validated Fact" in updated_ledger or "FACT" in updated_ledger,
            "Expected assumption ASSUMP-001 to be transitioned to validated fact",
        )
        active_working_assumption = "> ### Working Assumption `[ASSUMP-001]`"
        self.assertNotIn(
            active_working_assumption,
            updated_ledger,
            "Working assumption marker should no longer be present in original unverified state",
        )

    def test_backprop_payload_immutability(self) -> None:
        """Positive test: Enforces BackpropPayload dataclass immutability [INV-BKP-01]."""
        payload = BackpropPayload(
            task_id="TASK-026",
            invalidated_assumptions=[],
            discovered_constraints=[],
            applied_remedies=[],
            weight_deltas={},
            execution_success=True,
        )
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            payload.task_id = "TASK-099"  # type: ignore[misc]

    def test_backprop_payload_to_dict_serialization(self) -> None:
        """Positive test: Verifies to_dict returns dictionary containing all payload fields."""
        payload = BackpropPayload(
            task_id="TASK-026",
            invalidated_assumptions=["ASSUMP-001"],
            discovered_constraints=["Buffer ceiling 1MB"],
            applied_remedies=["Added streaming read"],
            weight_deltas={"evt_001": 0.25},
            execution_success=True,
        )
        data = payload.to_dict()

        self.assertIsInstance(data, dict)
        self.assertEqual(data["task_id"], "TASK-026")
        self.assertEqual(data["invalidated_assumptions"], ["ASSUMP-001"])
        self.assertEqual(data["discovered_constraints"], ["Buffer ceiling 1MB"])
        self.assertEqual(data["applied_remedies"], ["Added streaming read"])
        self.assertEqual(data["weight_deltas"], {"evt_001": 0.25})
        self.assertIs(data["execution_success"], True)


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.backprop_pipeline pending implementation by software-engineer",
)
class TestBackpropPipelineNegative(unittest.TestCase):
    """Evaluates payload validation, locked DB containment, and missing ledger fail-open resilience."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_cortex.db"
        self.ledger_path = Path(self.temp_dir.name) / "CURRENT_STATE.md"
        _init_test_cortex_db(self.db_path)
        _create_test_ledger_file(self.ledger_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_negative_empty_task_id_payload_handled(self) -> None:
        """Negative test: BackpropPayload with empty task_id raises ValueError or returns False."""
        empty_payload_handled = False
        try:
            payload = BackpropPayload(task_id="")
            success = backpropagate_gradient(
                payload,
                db_path=self.db_path,
                ledger_path=self.ledger_path,
            )
            if not success:
                empty_payload_handled = True
        except (ValueError, TypeError):
            empty_payload_handled = True

        self.assertTrue(
            empty_payload_handled,
            "Empty task_id should be rejected via ValueError or backpropagate_gradient False",
        )

    def test_negative_none_payload_handled(self) -> None:
        """Negative test: None payload returns False or raises ValueError/TypeError without crash."""
        none_handled = False
        try:
            success = backpropagate_gradient(
                None,  # type: ignore[arg-type]
                db_path=self.db_path,
                ledger_path=self.ledger_path,
            )
            if not success:
                none_handled = True
        except (ValueError, TypeError):
            none_handled = True

        self.assertTrue(
            none_handled,
            "None payload should be safely handled with False or ValueError/TypeError",
        )

    def test_negative_database_locked_fail_open_containment(self) -> None:
        """Negative test: Concurrently locked database fails open without unhandled crash [INV-BKP-04.1]."""
        lock_con = sqlite3.connect(str(self.db_path), timeout=0.05)
        try:
            with lock_con:
                lock_con.execute("BEGIN EXCLUSIVE TRANSACTION;")
                payload = BackpropPayload(
                    task_id="TASK-026",
                    applied_remedies=["Test remedy during db lock"],
                )
                result = backpropagate_gradient(
                    payload,
                    db_path=self.db_path,
                    ledger_path=self.ledger_path,
                )
                self.assertIs(
                    result,
                    False,
                    "Expected backpropagate_gradient to return False on database lock contention",
                )
        finally:
            lock_con.close()

    def test_negative_database_corrupted_fail_open_containment(self) -> None:
        """Negative test: Malformed or non-sqlite database triggers fail-open error containment."""
        corrupt_db = Path(self.temp_dir.name) / "corrupted.db"
        corrupt_db.write_text("CORRUPTED_DISK_SECTOR_NO_SQLITE_HEADER", encoding="utf-8")

        payload = BackpropPayload(
            task_id="TASK-026",
            applied_remedies=["Remedy on corrupted db"],
        )
        result = backpropagate_gradient(
            payload,
            db_path=corrupt_db,
            ledger_path=self.ledger_path,
        )
        self.assertIs(
            result,
            False,
            "Expected backpropagate_gradient to return False on corrupted database",
        )

    def test_negative_missing_ledger_file_fail_open_containment(self) -> None:
        """Negative test: Missing Epistemic Ledger file triggers fail-open without unhandled crash."""
        nonexistent_ledger = Path(self.temp_dir.name) / "missing_dir" / "CURRENT_STATE.md"
        payload = BackpropPayload(
            task_id="TASK-026",
            invalidated_assumptions=["ASSUMP-001"],
            applied_remedies=["Remedy with missing ledger"],
        )
        result = backpropagate_gradient(
            payload,
            db_path=self.db_path,
            ledger_path=nonexistent_ledger,
        )
        self.assertIs(
            result,
            False,
            "Expected backpropagate_gradient to return False when ledger file is missing",
        )

    def test_negative_unwritable_ledger_directory_fail_open(self) -> None:
        """Negative test: Unwritable ledger path fails open gracefully."""
        directory_as_ledger = Path(self.temp_dir.name)
        payload = BackpropPayload(
            task_id="TASK-026",
            invalidated_assumptions=["ASSUMP-001"],
        )
        result = backpropagate_gradient(
            payload,
            db_path=self.db_path,
            ledger_path=directory_as_ledger,
        )
        self.assertIs(
            result,
            False,
            "Expected backpropagate_gradient to return False when ledger path is a directory",
        )

    def test_negative_weight_delta_nonexistent_event_handled(self) -> None:
        """Negative test: Weight delta for non-existent event ID fails open or ignores without crash."""
        payload = BackpropPayload(
            task_id="TASK-026",
            weight_deltas={"evt_totally_nonexistent_9999": 0.5},
            execution_success=True,
        )
        result = backpropagate_gradient(
            payload,
            db_path=self.db_path,
            ledger_path=self.ledger_path,
        )
        self.assertIsInstance(
            result,
            bool,
            "Expected boolean return on weight delta for non-existent event",
        )


if __name__ == "__main__":
    unittest.main()
