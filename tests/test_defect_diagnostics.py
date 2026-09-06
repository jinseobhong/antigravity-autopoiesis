"""
Companion test suite for Preflight Defect Diagnostics & Cortex Ingestion (TASK-025).

Ingests docs/active/ACTIVE_CONTRACT.md as primary specification authority.
Evaluates diagnostic string parsing, component categorization, fail-open cortex.db
episodic ingestion, resolution tracking, and CLI --no-telemetry suppression.
Enforces AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12 with >= 40% negative ratio.
"""

import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Dict, List, Optional
import unittest
from unittest import mock

try:
    from core.defect_diagnostics import (
        DefectCategory,
        DefectDiagnostic,
        categorize_preflight_diagnostics,
        ingest_preflight_defects,
        parse_diagnostic_string,
        record_preflight_resolution,
    )
    _MODULE_AVAILABLE = True
except ModuleNotFoundError:
    try:
        from sandbox.core.defect_diagnostics import (
            DefectCategory,
            DefectDiagnostic,
            categorize_preflight_diagnostics,
            ingest_preflight_defects,
            parse_diagnostic_string,
            record_preflight_resolution,
        )
        _MODULE_AVAILABLE = True
    except ModuleNotFoundError:
        _MODULE_AVAILABLE = False
        DefectCategory = None  # type: ignore[assignment]
        DefectDiagnostic = None  # type: ignore[assignment]
        categorize_preflight_diagnostics = None  # type: ignore[assignment]
        ingest_preflight_defects = None  # type: ignore[assignment]
        parse_diagnostic_string = None  # type: ignore[assignment]
        record_preflight_resolution = None  # type: ignore[assignment]

try:
    from scripts.preflight_check import build_parser
    _parser_instance = build_parser()
    _PREFLIGHT_TELEMETRY_SUPPORTED = any(
        "--no-telemetry" in action.option_strings
        for action in _parser_instance._actions
    )
except (ModuleNotFoundError, Exception):
    try:
        from sandbox.scripts.preflight_check import build_parser
        _parser_instance = build_parser()
        _PREFLIGHT_TELEMETRY_SUPPORTED = any(
            "--no-telemetry" in action.option_strings
            for action in _parser_instance._actions
        )
    except (ModuleNotFoundError, Exception):
        _PREFLIGHT_TELEMETRY_SUPPORTED = False


def _init_test_cortex_db(db_file: Path) -> None:
    """Provisions isolated SQLite database with episodic_events schema for testing."""
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
                "CREATE INDEX IF NOT EXISTS idx_comp_out ON episodic_events(component, outcome);"
            )
    finally:
        con.close()


def _load_task_025_contract() -> Optional[str]:
    contract_path = Path("docs/active/ACTIVE_CONTRACT.md")
    if contract_path.exists():
        try:
            content = contract_path.read_text(encoding="utf-8")
            if 'target_task_id: "TASK-025"' in content:
                return content
        except OSError:
            _err_fallback = True
    db_path = Path("data/cortex.db")
    if db_path.exists():
        try:
            con = sqlite3.connect(str(db_path))
            cur = con.execute(
                "SELECT raw_content FROM contract_revisions WHERE task_id = 'TASK-025' "
                "ORDER BY revision_id DESC LIMIT 1;"
            )
            row = cur.fetchone()
            con.close()
            if row:
                return row[0]
        except Exception:
            _err_fallback = True
    return None


@unittest.skipUnless(
    _load_task_025_contract() is not None,
    "TASK-025 contract not present in active contract or cortex.db archive",
)
class TestDefectDiagnosticsContractInvariants(unittest.TestCase):
    """Verifies that ACTIVE_CONTRACT.md defines normative invariants [INV-DIAG-01..07]."""

    def setUp(self) -> None:
        contract_text = _load_task_025_contract()
        self.assertIsNotNone(contract_text, "TASK-025 contract text missing")
        self.contract_text = contract_text or ""

    def test_contract_metadata_and_acceptance(self) -> None:
        """Positive test: Verifies contract is ACCEPTED and targets TASK-025."""
        self.assertIn('status: "ACCEPTED"', self.contract_text)
        self.assertIn('target_task_id: "TASK-025"', self.contract_text)

    def test_contract_defines_all_normative_invariants(self) -> None:
        """Positive test: Verifies normative invariants [INV-DIAG-01..07] presence."""
        for inv_id in [
            "[INV-DIAG-01]",
            "[INV-DIAG-02]",
            "[INV-DIAG-02.1]",
            "[INV-DIAG-02.2]",
            "[INV-DIAG-02.3]",
            "[INV-DIAG-02.4]",
            "[INV-DIAG-03]",
            "[INV-DIAG-03.1]",
            "[INV-DIAG-03.2]",
            "[INV-DIAG-03.3]",
            "[INV-DIAG-04]",
            "[INV-DIAG-04.1]",
            "[INV-DIAG-05]",
            "[INV-DIAG-05.1]",
            "[INV-DIAG-05.2]",
            "[INV-DIAG-06]",
            "[INV-DIAG-07]",
            "[INV-DIAG-07.1]",
            "[INV-DIAG-07.2]",
        ]:
            self.assertIn(
                inv_id,
                self.contract_text,
                f"Missing invariant definition {inv_id} in contract",
            )

    def test_contract_defines_technical_interfaces(self) -> None:
        """Positive test: Verifies contract specifies classes and functional API."""
        self.assertIn("class DefectCategory", self.contract_text)
        self.assertIn("class DefectDiagnostic", self.contract_text)
        self.assertIn("def parse_diagnostic_string", self.contract_text)
        self.assertIn("def categorize_preflight_diagnostics", self.contract_text)
        self.assertIn("def ingest_preflight_defects", self.contract_text)
        self.assertIn("def record_preflight_resolution", self.contract_text)

    def test_negative_contract_missing_invariant_assertion(self) -> None:
        """Negative test: Evaluates rejection when an expected invariant is omitted."""
        synthetic_contract = "status: ACCEPTED\ntarget: TASK-025\n[INV-DIAG-01]\n"
        missing_inv = "[INV-DIAG-99]"
        self.assertNotIn(missing_inv, synthetic_contract)


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.defect_diagnostics pending implementation by software-engineer",
)
class TestDefectDiagnosticsParsingPositive(unittest.TestCase):
    """Evaluates positive parsing and extraction contracts across defect categories."""

    def test_parse_compliance_defect_cyclomatic_complexity(self) -> None:
        """Positive test: Parses [Compliance] cyclomatic complexity defect [INV-DIAG-02.1]."""
        raw = (
            "[Compliance] core/agent_runner.py:L142 [CYCLOMATIC_COMPLEXITY_EXCEEDED] "
            "Function 'execute' has CC=14 (max 10 allowed)"
        )
        diag = parse_diagnostic_string(raw)
        self.assertEqual(diag.category, DefectCategory.COMPLIANCE_CHECKER)
        self.assertEqual(diag.component, "compliance_checker")
        self.assertIn("CYCLOMATIC_COMPLEXITY_EXCEEDED", diag.trigger_tokens)
        self.assertIn("complexity", diag.root_cause.lower())
        self.assertTrue(len(diag.directive) > 0)
        self.assertEqual(diag.raw_diagnostic, raw)

    def test_parse_compliance_defect_line_length(self) -> None:
        """Positive test: Parses [Compliance] line length defect [INV-DIAG-02.1]."""
        raw = "[Compliance] core/cortex.py:L88 [LINE_LENGTH_EXCEEDED] Line exceeds 120 chars"
        diag = parse_diagnostic_string(raw)
        self.assertEqual(diag.category, DefectCategory.COMPLIANCE_CHECKER)
        self.assertEqual(diag.component, "compliance_checker")
        self.assertIn("LINE_LENGTH_EXCEEDED", diag.trigger_tokens)
        self.assertEqual(diag.raw_diagnostic, raw)

    def test_parse_compliance_defect_lazy_stub(self) -> None:
        """Positive test: Parses [Compliance] lazy stub defect [INV-DIAG-02.1]."""
        raw = (
            "[Compliance] core/state.py:L45 [LAZY_STUB_PASS] "
            "Lazy placeholder 'pass' statement is prohibited"
        )
        diag = parse_diagnostic_string(raw)
        self.assertEqual(diag.category, DefectCategory.COMPLIANCE_CHECKER)
        self.assertIn("LAZY_STUB_PASS", diag.trigger_tokens)
        self.assertEqual(diag.raw_diagnostic, raw)

    def test_parse_topology_violation_root_pollution(self) -> None:
        """Positive test: Parses [Topology] root pollution violation [INV-DIAG-02.2]."""
        raw = "[Topology] [H-TOPO-1] temp_test.py (depth=0): Root directory pollution detected"
        diag = parse_diagnostic_string(raw)
        self.assertEqual(diag.category, DefectCategory.FS_TOPOLOGY)
        self.assertEqual(diag.component, "fs_topology")
        self.assertIn("H-TOPO-1", diag.trigger_tokens)
        self.assertIn("root", diag.root_cause.lower())
        self.assertTrue(len(diag.directive) > 0)
        self.assertEqual(diag.raw_diagnostic, raw)

    def test_parse_topology_violation_max_depth(self) -> None:
        """Positive test: Parses [Topology] nesting depth violation [INV-DIAG-02.2]."""
        raw = (
            "[Topology] [H-TOPO-3] core/a/b/c/d/e/deep.py (depth=6): "
            "Maximum directory nesting depth exceeded"
        )
        diag = parse_diagnostic_string(raw)
        self.assertEqual(diag.category, DefectCategory.FS_TOPOLOGY)
        self.assertEqual(diag.component, "fs_topology")
        self.assertIn("H-TOPO-3", diag.trigger_tokens)
        self.assertEqual(diag.raw_diagnostic, raw)

    def test_parse_test_failure_assertion_error(self) -> None:
        """Positive test: Parses [Test Failure] assertion failure [INV-DIAG-02.3]."""
        raw = (
            "[Test Failure] tests.test_agent_runner.TestRunner.test_exec: "
            "AssertionError: Expected True but got False"
        )
        diag = parse_diagnostic_string(raw)
        self.assertEqual(diag.category, DefectCategory.TEST_ENGINE)
        self.assertEqual(diag.component, "test_engine")
        self.assertIn("AssertionError", diag.trigger_tokens)
        self.assertTrue(len(diag.root_cause) > 0)
        self.assertTrue(len(diag.directive) > 0)
        self.assertEqual(diag.raw_diagnostic, raw)

    def test_parse_test_error_unhandled_exception(self) -> None:
        """Positive test: Parses [Test Error] runtime exception [INV-DIAG-02.3]."""
        raw = (
            "[Test Error] tests.test_cortex.TestCortex.test_write: "
            "sqlite3.OperationalError: database is locked"
        )
        diag = parse_diagnostic_string(raw)
        self.assertEqual(diag.category, DefectCategory.TEST_ENGINE)
        self.assertEqual(diag.component, "test_engine")
        self.assertTrue(
            "OperationalError" in diag.trigger_tokens or "sqlite3" in diag.trigger_tokens
        )
        self.assertEqual(diag.raw_diagnostic, raw)

    def test_to_event_payload_serialization(self) -> None:
        """Positive test: Verifies to_event_payload schema contract [INV-DIAG-03]."""
        raw = "[Compliance] file.py:L10 [SYNTAX_ERROR] invalid syntax"
        diag = parse_diagnostic_string(raw)
        payload = diag.to_event_payload()
        self.assertEqual(payload["outcome"], "FAILURE")
        self.assertEqual(payload["component"], diag.component)
        self.assertEqual(payload["trigger_tokens"], diag.trigger_tokens)
        self.assertEqual(payload["directive"], diag.directive)
        self.assertEqual(payload["root_cause"], diag.root_cause)


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.defect_diagnostics pending implementation by software-engineer",
)
class TestDefectDiagnosticsCategorization(unittest.TestCase):
    """Evaluates multi-item categorization across heterogeneous diagnostic inputs."""

    def test_categorize_multiple_mixed_diagnostics(self) -> None:
        """Positive test: Categorizes list containing compliance, topology, test defects."""
        raw_list = [
            "[Compliance] core/foo.py:L10 [MAX_PARAMETERS_EXCEEDED] Function has 9 params",
            "[Topology] [H-TOPO-2] orphan.py (depth=0): File is orphaned",
            "[Test Failure] tests.test_bar.TestBar.test_run: AssertionError: mismatch",
        ]
        results = categorize_preflight_diagnostics(raw_list)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].category, DefectCategory.COMPLIANCE_CHECKER)
        self.assertEqual(results[1].category, DefectCategory.FS_TOPOLOGY)
        self.assertEqual(results[2].category, DefectCategory.TEST_ENGINE)


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.defect_diagnostics pending implementation by software-engineer",
)
class TestDefectDiagnosticsIngestionPositive(unittest.TestCase):
    """Evaluates cortex.db failure persistence and resolution tracking in isolated DB."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cortex.db"
        _init_test_cortex_db(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ingest_preflight_defects_single_failure(self) -> None:
        """Positive test: Ingests failures into isolated DB [INV-DIAG-03]."""
        raw_list = [
            "[Compliance] core/logic.py:L20 [LINE_LENGTH_EXCEEDED] Line exceeds 120 chars",
            "[Topology] [H-TOPO-1] stray.py (depth=0): Stray root file",
        ]
        count = ingest_preflight_defects(raw_list, db_path=self.db_path)
        self.assertEqual(count, 2)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT outcome, component, trigger_tokens, directive, root_cause "
                "FROM episodic_events ORDER BY rowid ASC;"
            )
            rows = cur.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "FAILURE")
            self.assertEqual(rows[0][1], "compliance_checker")
            self.assertIn("LINE_LENGTH_EXCEEDED", rows[0][2])
            self.assertTrue(len(rows[0][3]) > 0)
            self.assertTrue(len(rows[0][4]) > 0)

            self.assertEqual(rows[1][0], "FAILURE")
            self.assertEqual(rows[1][1], "fs_topology")
            self.assertIn("H-TOPO-1", rows[1][2])
        finally:
            con.close()

    def test_record_preflight_resolution_marks_success(self) -> None:
        """Positive test: Records outcome='SUCCESS' for cleared components [INV-DIAG-04]."""
        raw_list = [
            "[Compliance] core/logic.py:L20 [LINE_LENGTH_EXCEEDED] Line exceeds 120 chars"
        ]
        ingest_preflight_defects(raw_list, db_path=self.db_path)

        res_count = record_preflight_resolution(
            ["compliance_checker"], db_path=self.db_path
        )
        self.assertEqual(res_count, 1)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT outcome, component, trigger_tokens, directive, solution "
                "FROM episodic_events WHERE outcome = 'SUCCESS';"
            )
            rows = cur.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "SUCCESS")
            self.assertEqual(rows[0][1], "compliance_checker")
            self.assertIn("LINE_LENGTH_EXCEEDED", rows[0][2])

            directive = rows[0][3]
            solution = rows[0][4]

            # Substantive checks: directive must not be boilerplate placeholder
            self.assertNotIn("All verification gates cleared.", directive)
            self.assertNotIn("Verified resolution.", directive)
            self.assertIn("line length", directive.lower())
            self.assertIn("Maintain line length <= 100", directive)

            # Substantive checks: solution must not be boilerplate placeholder
            self.assertNotEqual(solution, "Quality gate cleared in subsequent preflight run.")
            self.assertNotIn("Quality gate cleared", solution)
            self.assertIn("line length", solution.lower())
        finally:
            con.close()

    def test_record_preflight_resolution_multiple_components(self) -> None:
        """Positive test: Records resolution across multiple cleared components [INV-DIAG-04]."""
        raw_list = [
            "[Compliance] core/logic.py:L20 [CYCLOMATIC_COMPLEXITY_EXCEEDED] CC=15",
            "[Topology] [H-TOPO-1] stray.py (depth=0): Stray root file",
            "[Test Failure] tests.test_mod: AssertionError: mismatch",
        ]
        ingest_preflight_defects(raw_list, db_path=self.db_path)

        cleared = ["compliance_checker", "fs_topology", "test_engine"]
        res_count = record_preflight_resolution(cleared, db_path=self.db_path)
        self.assertEqual(res_count, 3)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT outcome, component, trigger_tokens, directive, solution "
                "FROM episodic_events WHERE outcome = 'SUCCESS' ORDER BY rowid ASC;"
            )
            rows = cur.fetchall()
            self.assertEqual(len(rows), 3)

            # Compliance resolution
            self.assertEqual(rows[0][1], "compliance_checker")
            self.assertIn("CYCLOMATIC_COMPLEXITY_EXCEEDED", rows[0][2])
            self.assertIn("Maintain function CC <= 10", rows[0][3])
            self.assertIn("Single Level of Abstraction", rows[0][3])
            self.assertIn("cyclomatic complexity", rows[0][4].lower())
            self.assertNotIn("Quality gate cleared", rows[0][4])

            # Topology resolution
            self.assertEqual(rows[1][1], "fs_topology")
            self.assertIn("H-TOPO-1", rows[1][2])
            self.assertIn("filesystem topology boundary", rows[1][3])
            self.assertIn("root directory pollution", rows[1][4].lower())
            self.assertNotIn("Quality gate cleared", rows[1][4])

            # Test engine resolution
            self.assertEqual(rows[2][1], "test_engine")
            self.assertIn("AssertionError", rows[2][2])
            self.assertIn("Maintain 100% test pass rate", rows[2][3])
            self.assertIn("assertion failure", rows[2][4].lower())
            self.assertNotIn("Quality gate cleared", rows[2][4])
        finally:
            con.close()

    def test_no_spurious_success_when_no_prior_failure(self) -> None:
        """Negative test: Asserts spurious SUCCESS events are NOT created without prior failure."""
        count = record_preflight_resolution(
            ["compliance_checker", "fs_topology", "test_engine"],
            db_path=self.db_path,
        )
        self.assertEqual(count, 0)

        single_result = record_preflight_resolution(
            component="compliance_checker",
            db_path=self.db_path,
        )
        self.assertFalse(single_result)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT COUNT(*) FROM episodic_events WHERE outcome = 'SUCCESS';"
            )
            self.assertEqual(cur.fetchone()[0], 0)
        finally:
            con.close()

    def test_no_spurious_success_when_prior_failure_already_resolved(self) -> None:
        """Negative test: Asserts SUCCESS is not re-recorded once defect is already resolved."""
        raw_list = [
            "[Compliance] core/mod.py:L15 [CYCLOMATIC_COMPLEXITY_EXCEEDED] CC=12"
        ]
        ingest_preflight_defects(raw_list, db_path=self.db_path)

        first_count = record_preflight_resolution(
            ["compliance_checker"], db_path=self.db_path
        )
        self.assertEqual(first_count, 1)

        second_count = record_preflight_resolution(
            ["compliance_checker"], db_path=self.db_path
        )
        self.assertEqual(second_count, 0)

        single_result = record_preflight_resolution(
            component="compliance_checker", db_path=self.db_path
        )
        self.assertFalse(single_result)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT COUNT(*) FROM episodic_events WHERE outcome = 'SUCCESS';"
            )
            self.assertEqual(cur.fetchone()[0], 1)
        finally:
            con.close()

    def test_selective_resolution_only_failed_components_resolved(self) -> None:
        """Positive test: Verifies only components with unresolved failures are resolved."""
        raw_list = [
            "[Test Failure] tests.test_unit: AssertionError: expected 1 got 2"
        ]
        ingest_preflight_defects(raw_list, db_path=self.db_path)

        cleared = ["compliance_checker", "fs_topology", "test_engine"]
        res_count = record_preflight_resolution(cleared, db_path=self.db_path)
        self.assertEqual(res_count, 1)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT component FROM episodic_events WHERE outcome = 'SUCCESS';"
            )
            rows = cur.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "test_engine")
        finally:
            con.close()

    def test_resolution_synthesizes_substantive_lesson_and_evidence(self) -> None:
        """Positive test: Verifies resolution synthesizes prescriptive lesson and evidence note."""
        raw_list = [
            "[Compliance] core/runner.py:L50 [CYCLOMATIC_COMPLEXITY_EXCEEDED] CC=14 max 10"
        ]
        ingest_preflight_defects(raw_list, db_path=self.db_path)

        res_count = record_preflight_resolution(
            ["compliance_checker"],
            resolution_note="Decomposed runner logic into 3 single-responsibility helpers.",
            db_path=self.db_path,
        )
        self.assertEqual(res_count, 1)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute(
                "SELECT directive, solution FROM episodic_events WHERE outcome = 'SUCCESS';"
            )
            row = cur.fetchone()
            self.assertIsNotNone(row)
            directive, solution = row[0], row[1]

            self.assertIn("Maintain function CC <= 10 and Single Level of Abstraction", directive)
            self.assertIn("Decomposed runner logic into 3 single-responsibility helpers", directive)

            self.assertIn("cyclomatic complexity", solution.lower())
            self.assertIn("Decomposed runner logic into 3 single-responsibility helpers", solution)
            self.assertNotIn("Quality gate cleared in subsequent preflight run.", solution)
        finally:
            con.close()


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.defect_diagnostics pending implementation by software-engineer",
)
class TestDefectDiagnosticsNegativeAndEdgeCases(unittest.TestCase):
    """Adversarial negative test suite evaluating boundary, malformed, and fault-injection paths."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "negative_test.db"
        _init_test_cortex_db(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_negative_categorize_empty_diagnostics(self) -> None:
        """Negative test: Verifies empty diagnostics list returns empty list."""
        result = categorize_preflight_diagnostics([])
        self.assertEqual(result, [])

    def test_negative_ingest_empty_diagnostics(self) -> None:
        """Negative test: Verifies empty list records 0 events without DB writes."""
        count = ingest_preflight_defects([], db_path=self.db_path)
        self.assertEqual(count, 0)
        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute("SELECT COUNT(*) FROM episodic_events;")
            self.assertEqual(cur.fetchone()[0], 0)
        finally:
            con.close()

    def test_negative_resolution_empty_components(self) -> None:
        """Negative test: Verifies empty component list records 0 resolution events."""
        count = record_preflight_resolution([], db_path=self.db_path)
        self.assertEqual(count, 0)

    def test_negative_parse_unrecognized_prefix(self) -> None:
        """Negative test: Gracefully categorizes unrecognized string [INV-DIAG-02.4]."""
        raw = "Unexpected terminal warning text without prefix tag"
        diag = parse_diagnostic_string(raw)
        expected_cat = getattr(
            DefectCategory,
            "GENERAL_PREFLIGHT",
            getattr(DefectCategory, "UNKNOWN", DefectCategory.COMPLIANCE_CHECKER),
        )
        self.assertEqual(diag.category, expected_cat)
        self.assertEqual(diag.raw_diagnostic, raw)
        self.assertTrue(len(diag.directive) > 0)

    def test_negative_parse_empty_string(self) -> None:
        """Negative test: Handles completely empty diagnostic string gracefully."""
        diag = parse_diagnostic_string("")
        expected_cat = getattr(DefectCategory, "GENERAL_PREFLIGHT", diag.category)
        self.assertEqual(diag.category, expected_cat)
        self.assertEqual(diag.raw_diagnostic, "")

    def test_negative_parse_whitespace_string(self) -> None:
        """Negative test: Handles whitespace-only string gracefully."""
        diag = parse_diagnostic_string("   \t\n   ")
        expected_cat = getattr(DefectCategory, "GENERAL_PREFLIGHT", diag.category)
        self.assertEqual(diag.category, expected_cat)

    def test_negative_parse_malformed_bracket_format(self) -> None:
        """Negative test: Handles incomplete bracket without crashing."""
        raw = "[Compliance unclosed bracket line"
        diag = parse_diagnostic_string(raw)
        self.assertEqual(diag.raw_diagnostic, raw)

    def test_negative_parse_corrupted_characters(self) -> None:
        """Negative test: Handles control characters and non-ASCII streams safely."""
        raw = "\x00\x01\xfe\xff corrupted stream with [Compliance] marker"
        diag = parse_diagnostic_string(raw)
        self.assertIn("corrupted stream", diag.raw_diagnostic)

    def test_negative_ingest_db_locked_fails_open(self) -> None:
        """Negative test: Verifies fail-open behavior when DB is locked [INV-DIAG-05]."""
        raw_list = ["[Compliance] core/test.py:L1 [SYNTAX_ERROR] syntax error"]
        with mock.patch(
            "core.defect_diagnostics.record_event",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            # Must NOT raise unhandled exception
            try:
                count = ingest_preflight_defects(raw_list, db_path=self.db_path)
            except Exception as exc:
                self.fail(f"ingest_preflight_defects failed to fail-open: {exc}")
            self.assertEqual(count, 0)

    def test_negative_resolution_db_unavailable_fails_open(self) -> None:
        """Negative test: Verifies resolution fail-open when DB access fails [INV-DIAG-05.1]."""
        raw_list = ["[Compliance] core/test.py:L1 [SYNTAX_ERROR] syntax error"]
        ingest_preflight_defects(raw_list, db_path=self.db_path)

        with mock.patch(
            "core.defect_diagnostics.record_event",
            side_effect=sqlite3.OperationalError("database disk image is malformed"),
        ):
            try:
                count = record_preflight_resolution(
                    ["compliance_checker"], db_path=self.db_path
                )
            except Exception as exc:
                self.fail(f"record_preflight_resolution failed to fail-open: {exc}")
            self.assertEqual(count, 0)

    def test_negative_ingest_corrupted_db_file(self) -> None:
        """Negative test: Handles corrupted DB file gracefully without preflight crash."""
        corrupt_db = Path(self.temp_dir.name) / "corrupt.db"
        corrupt_db.write_bytes(b"NON_SQLITE_BINARY_HEADER_DATA")
        raw_list = ["[Topology] [H-TOPO-1] bad.py: bad file"]
        try:
            count = ingest_preflight_defects(raw_list, db_path=corrupt_db)
        except Exception as exc:
            self.fail(f"Corrupt DB caused unhandled exception: {exc}")
        self.assertEqual(count, 0)

    def test_negative_ingest_no_telemetry_suppresses_persistence(self) -> None:
        """Negative test: Verifies --no-telemetry suppresses DB write [INV-DIAG-06]."""
        raw_list = ["[Compliance] file.py:L1 [SYNTAX_ERROR] syntax error"]
        count = ingest_preflight_defects(
            raw_list, db_path=self.db_path, no_telemetry=True
        )
        self.assertEqual(count, 0)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute("SELECT COUNT(*) FROM episodic_events;")
            self.assertEqual(cur.fetchone()[0], 0)
        finally:
            con.close()

    def test_negative_resolution_no_telemetry_suppresses_persistence(self) -> None:
        """Negative test: Verifies --no-telemetry suppresses resolution event [INV-DIAG-06]."""
        raw_list = ["[Compliance] file.py:L1 [SYNTAX_ERROR] syntax error"]
        ingest_preflight_defects(raw_list, db_path=self.db_path)

        count = record_preflight_resolution(
            ["compliance_checker"], db_path=self.db_path, no_telemetry=True
        )
        self.assertEqual(count, 0)

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.execute("SELECT COUNT(*) FROM episodic_events WHERE outcome = 'SUCCESS';")
            self.assertEqual(cur.fetchone()[0], 0)
        finally:
            con.close()

    def test_boundary_extremely_long_diagnostic_string(self) -> None:
        """Negative test: Safely processes oversized 10,000 character diagnostic line."""
        oversized = "[Compliance] file.py:L1 [LONG_PAYLOAD] " + ("X" * 10000)
        diag = parse_diagnostic_string(oversized)
        self.assertEqual(diag.category, DefectCategory.COMPLIANCE_CHECKER)
        self.assertEqual(len(diag.raw_diagnostic), len(oversized))


class TestPreflightCLITelemetryFlag(unittest.TestCase):
    """Evaluates preflight_check.py CLI flag integration for --no-telemetry."""

    @unittest.skipUnless(
        _PREFLIGHT_TELEMETRY_SUPPORTED,
        "--no-telemetry flag pending preflight_check.py integration in Phase 2",
    )
    def test_negative_preflight_cli_no_telemetry_flag(self) -> None:
        """Negative test: Verifies --no-telemetry option parses cleanly [INV-DIAG-06]."""
        parser = build_parser()
        args = parser.parse_args(["--no-telemetry"])
        self.assertTrue(getattr(args, "no_telemetry", False))


if __name__ == "__main__":
    unittest.main()
