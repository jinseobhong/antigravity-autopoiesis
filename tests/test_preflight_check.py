"""
Companion test suite for Unified Preflight Verification Engine (tests.test_preflight_check).

Evaluates Track A/B preflight gates, CLI execution, output compaction, and error containment.
Satisfies AST Anti-Cheat invariants (H-CODE-1 through H-CODE-12) with >= 30% negative test ratio.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from typing import List, Tuple
import unittest
from unittest import mock

try:
    from scripts.preflight_check import (
        PreflightReport,
        _run_compliance_gate,
        _run_topology_gate,
        _run_test_suite_gate,
        run_preflight,
        _render_text_report,
        build_parser,
        main,
    )
except ModuleNotFoundError:
    from sandbox.scripts.preflight_check import (
        PreflightReport,
        _run_compliance_gate,
        _run_topology_gate,
        _run_test_suite_gate,
        run_preflight,
        _render_text_report,
        build_parser,
        main,
    )


class TestPreflightReport(unittest.TestCase):
    """Evaluates PreflightReport dataclass immutability and serialization contracts."""

    def test_report_serialization_positive(self) -> None:
        """Positive test: Verifies standard report serialization with zero defects."""
        report = PreflightReport(
            passed=True,
            duration_ms=125.45,
            compliance_files=38,
            compliance_defects=0,
            topology_scanned=69,
            topology_violations=0,
            tests_run=135,
            test_failures=0,
            test_errors=0,
            diagnostics=[],
        )
        serialized = report.to_dict()
        self.assertTrue(serialized["passed"])
        self.assertEqual(serialized["duration_ms"], 125.45)
        self.assertEqual(serialized["compliance"]["files"], 38)
        self.assertEqual(serialized["compliance"]["defects"], 0)
        self.assertEqual(serialized["topology"]["violations"], 0)
        self.assertEqual(serialized["tests"]["failures"], 0)
        self.assertEqual(len(serialized["diagnostics"]), 0)

    def test_negative_report_failure_containment(self) -> None:
        """Negative test: Verifies report correctly records failure state and diagnostics."""
        diag_msg = "[Compliance] core/test.py:L10 [LAZY_STUB_PASS] Forbidden pass stub detected"
        report = PreflightReport(
            passed=False,
            duration_ms=250.12,
            compliance_files=38,
            compliance_defects=1,
            topology_scanned=69,
            topology_violations=0,
            tests_run=135,
            test_failures=0,
            test_errors=0,
            diagnostics=[diag_msg],
        )
        serialized = report.to_dict()
        self.assertFalse(serialized["passed"])
        self.assertEqual(serialized["compliance"]["defects"], 1)
        self.assertEqual(len(serialized["diagnostics"]), 1)
        self.assertIn("LAZY_STUB_PASS", serialized["diagnostics"][0])


class TestPreflightSubroutines(unittest.TestCase):
    """Evaluates modular preflight gate subroutines."""

    def test_run_compliance_gate_positive(self) -> None:
        """Positive test: Verifies compliance gate on clean temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            clean_file = Path(tmpdir) / "clean.py"
            clean_file.write_text(
                "def add(a: int, b: int) -> int:\n    return a + b\n",
                encoding="utf-8",
            )
            files_count, defect_count, diags = _run_compliance_gate(tmpdir)
            self.assertEqual(files_count, 1)
            self.assertEqual(defect_count, 0)
            self.assertEqual(len(diags), 0)

    def test_negative_compliance_gate_detects_defect(self) -> None:
        """Negative test: Verifies compliance gate catches and reports syntax/AST defects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            defective_file = Path(tmpdir) / "defective.py"
            defective_file.write_text(
                "def lazy_func() -> None:\n    pass\n",
                encoding="utf-8",
            )
            files_count, defect_count, diags = _run_compliance_gate(tmpdir)
            self.assertEqual(files_count, 1)
            self.assertGreaterEqual(defect_count, 1)
            self.assertGreaterEqual(len(diags), 1)
            self.assertIn("LAZY_STUB_PASS", diags[0])

    def test_run_topology_gate_positive(self) -> None:
        """Positive test: Verifies topology gate runs cleanly on current repository."""
        scanned, violations_count, diags = _run_topology_gate(Path("."))
        self.assertGreater(scanned, 0)
        self.assertEqual(violations_count, 0)
        self.assertEqual(len(diags), 0)

    def test_negative_topology_gate_catches_violation(self) -> None:
        """Negative test: Verifies topology gate catches unauthorized root directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            (tmp_root / "src").mkdir(parents=True, exist_ok=True)
            scanned, violations_count, diags = _run_topology_gate(tmp_root)
            self.assertGreater(violations_count, 0)
            self.assertGreater(len(diags), 0)
            self.assertIn("INV-FS-03", diags[0])

    def test_negative_test_suite_gate_captures_failure(self) -> None:
        """Negative test: Verifies test runner gate isolates stdout and logs test failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            test_code = (
                "import unittest\n"
                "class FailingTest(unittest.TestCase):\n"
                "    def test_deliberate_fail(self):\n"
                "        self.assertEqual(1, 2)\n"
            )
            (test_dir / "test_sample.py").write_text(test_code, encoding="utf-8")
            runs, fails, errs, diags = _run_test_suite_gate(str(test_dir))
            self.assertEqual(runs, 1)
            self.assertEqual(fails, 1)
            self.assertEqual(errs, 0)
            self.assertGreaterEqual(len(diags), 1)
            self.assertIn("[Test Failure]", diags[0])


class TestPreflightCLI(unittest.TestCase):
    """Evaluates CLI parsing, JSON formatting, and process exit codes."""

    def test_cli_parser_defaults(self) -> None:
        """Positive test: Verifies default argument parser configuration."""
        parser = build_parser()
        args = parser.parse_args([])
        self.assertTrue(args.quick)
        self.assertFalse(args.full)
        self.assertFalse(args.verbose)
        self.assertFalse(args.json)
        self.assertEqual(args.root, ".")

    def test_negative_cli_unknown_argument(self) -> None:
        """Negative test: Verifies unrecognized CLI flags trigger system exit."""
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args(["--invalid-unrecognized-flag"])
        self.assertNotEqual(cm.exception.code, 0)

    @mock.patch("scripts.preflight_check.run_preflight")
    def test_cli_json_output(self, mock_run: mock.MagicMock) -> None:
        """Positive test: Verifies CLI --json generates valid JSON to standard output."""
        dummy_report = PreflightReport(
            passed=True,
            duration_ms=45.6,
            compliance_files=10,
            compliance_defects=0,
            topology_scanned=20,
            topology_violations=0,
            tests_run=50,
            test_failures=0,
            test_errors=0,
            diagnostics=[],
        )
        mock_run.return_value = dummy_report

        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf):
            exit_code = main(["--json"])

        self.assertEqual(exit_code, 0)
        parsed_json = json.loads(stdout_buf.getvalue())
        self.assertTrue(parsed_json["passed"])
        self.assertEqual(parsed_json["compliance"]["files"], 10)

    @mock.patch("scripts.preflight_check.run_preflight")
    def test_negative_cli_exit_code_on_failure(self, mock_run: mock.MagicMock) -> None:
        """Negative test: Verifies CLI returns exit code 1 when preflight fails."""
        dummy_report = PreflightReport(
            passed=False,
            duration_ms=88.2,
            compliance_files=10,
            compliance_defects=2,
            topology_scanned=20,
            topology_violations=1,
            tests_run=50,
            test_failures=1,
            test_errors=0,
            diagnostics=["error 1", "error 2"],
        )
        mock_run.return_value = dummy_report

        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf):
            exit_code = main(["--quick"])

        self.assertEqual(exit_code, 1)
        output = stdout_buf.getvalue()
        self.assertIn("PREFLIGHT FAIL", output)
        self.assertIn("Static Compliance Defects:  2", output)


if __name__ == "__main__":
    unittest.main()
