"""
Companion test suite for Automated IV&V Lifecycle Enforcement Hook (tests.test_guard_ivv_pipeline).

Evaluates path normalization, transcript role detection, RBAC policies, and CLI I/O contracts.
Satisfies AST Anti-Cheat invariants (H-CODE-1 through H-CODE-12) with >= 30% negative test ratio.
"""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from scripts.guard_ivv_pipeline import (
        _normalize_path,
        _detect_caller_role,
        evaluate_tool_call,
        main,
    )
except ModuleNotFoundError:
    from sandbox.scripts.guard_ivv_pipeline import (
        _normalize_path,
        _detect_caller_role,
        evaluate_tool_call,
        main,
    )


class TestGuardPathNormalization(unittest.TestCase):
    """Evaluates target file path normalization across OS variants."""

    def test_normalize_relative_path(self) -> None:
        """Positive test: Verifies simple relative paths retain forward slashes."""
        res = _normalize_path("core/test_engine/worker.py")
        self.assertEqual(res, "core/test_engine/worker.py")

    def test_normalize_windows_absolute_path_with_workspace(self) -> None:
        """Positive test: Strips workspace prefix from Windows absolute path."""
        ws = ["D:/Development/projects/antigravity/autopoiesis"]
        target = "D:\\Development\\projects\\antigravity\\autopoiesis\\sandbox\\core\\logic.py"
        res = _normalize_path(target, ws)
        self.assertEqual(res, "sandbox/core/logic.py")

    def test_negative_normalize_unusual_drive_letter_stripping(self) -> None:
        """Negative test: Verifies fallback drive letter stripping when workspace is missing."""
        target = "C:\\some\\dir\\core\\kernel.py"
        res = _normalize_path(target, None)
        self.assertEqual(res, "some/dir/core/kernel.py")


class TestGuardRoleDetection(unittest.TestCase):
    """Evaluates caller identity detection from transcript steps."""

    def test_detect_orchestrator_when_transcript_missing(self) -> None:
        """Positive test: Defaults to orchestrator when transcript path is None."""
        self.assertEqual(_detect_caller_role(None), "orchestrator")

    def test_detect_software_engineer_from_transcript(self) -> None:
        """Positive test: Detects software-engineer from subagent initial prompt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript = Path(tmpdir) / "transcript.jsonl"
            prompt = (
                "You are software-engineer. Author production logic in sandbox/core.\n"
                "--caller-id: parent-123"
            )
            step_data = {"step_index": 0, "content": prompt}
            transcript.write_text(json.dumps(step_data) + "\n", encoding="utf-8")
            role = _detect_caller_role(str(transcript))
            self.assertEqual(role, "software-engineer")

    def test_detect_qa_engineer_from_transcript(self) -> None:
        """Positive test: Detects qa-engineer from subagent initial prompt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript = Path(tmpdir) / "transcript.jsonl"
            prompt = (
                "You are qa-engineer. Synthesize adversarial verification suite.\n"
                "--caller-id: parent-123"
            )
            step_data = {"step_index": 0, "content": prompt}
            transcript.write_text(json.dumps(step_data) + "\n", encoding="utf-8")
            role = _detect_caller_role(str(transcript))
            self.assertEqual(role, "qa-engineer")

    def test_negative_corrupted_transcript_handled_gracefully(self) -> None:
        """Negative test: Recovers gracefully on unparseable corrupted transcript."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript = Path(tmpdir) / "corrupted.jsonl"
            transcript.write_text("NOT_VALID_JSON_AT_ALL\n", encoding="utf-8")
            role = _detect_caller_role(str(transcript))
            self.assertEqual(role, "orchestrator")


class TestGuardAccessControlPolicy(unittest.TestCase):
    """Evaluates RBAC rules for orchestrator, software-engineer, and qa-engineer."""

    def test_negative_orchestrator_blocked_from_core(self) -> None:
        """Negative test: Blocks orchestrator from mutating core/ files directly."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "core/cortex.py"},
            },
            "transcriptPath": None,
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "deny")
        self.assertIsNotNone(reason)
        self.assertIn("IV&V HOOK BLOCKED", str(reason))

    def test_negative_orchestrator_blocked_from_sandbox_core(self) -> None:
        """Negative test: Blocks orchestrator from writing to sandbox/core/ files."""
        payload = {
            "toolCall": {
                "name": "replace_file_content",
                "args": {"TargetFile": "sandbox/core/cache.py"},
            },
            "transcriptPath": None,
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "deny")
        self.assertIn("sandbox/core/cache.py", str(reason))

    def test_negative_orchestrator_blocked_from_tests(self) -> None:
        """Negative test: Blocks orchestrator from writing test suites directly."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "sandbox/tests/test_cache.py"},
            },
            "transcriptPath": None,
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "deny")
        self.assertIn("sandbox/tests/test_cache.py", str(reason))

    def test_orchestrator_allowed_docs_and_scripts(self) -> None:
        """Positive test: Allows orchestrator to edit documentation and state files."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "docs/active/CURRENT_STATE.md"},
            },
            "transcriptPath": None,
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

    @mock.patch("scripts.guard_ivv_pipeline.validate_contract_state", return_value=(True, None))
    @mock.patch("scripts.guard_ivv_pipeline._detect_caller_role")
    def test_software_engineer_allowed_sandbox_core(
        self, mock_role: mock.MagicMock, _mock_validate: mock.MagicMock
    ) -> None:
        """Positive test: Allows software-engineer to write to sandbox/core/."""
        mock_role.return_value = "software-engineer"
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "sandbox/core/module.py"},
            },
            "transcriptPath": "dummy.jsonl",
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

    @mock.patch("scripts.guard_ivv_pipeline.validate_contract_state", return_value=(True, None))
    @mock.patch("scripts.guard_ivv_pipeline._detect_caller_role")
    def test_negative_software_engineer_blocked_from_tests(
        self, mock_role: mock.MagicMock, _mock_validate: mock.MagicMock
    ) -> None:
        """Negative test: Blocks software-engineer from authoring verification tests."""
        mock_role.return_value = "software-engineer"
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "sandbox/tests/test_module.py"},
            },
            "transcriptPath": "dummy.jsonl",
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "deny")
        self.assertIn("software-engineer is restricted from authoring tests", str(reason))

    @mock.patch("scripts.guard_ivv_pipeline.validate_contract_state", return_value=(True, None))
    @mock.patch("scripts.guard_ivv_pipeline._detect_caller_role")
    def test_qa_engineer_allowed_sandbox_tests(
        self, mock_role: mock.MagicMock, _mock_validate: mock.MagicMock
    ) -> None:
        """Positive test: Allows qa-engineer to write to sandbox/tests/."""
        mock_role.return_value = "qa-engineer"
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "sandbox/tests/test_module.py"},
            },
            "transcriptPath": "dummy.jsonl",
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

    @mock.patch("scripts.guard_ivv_pipeline.validate_contract_state", return_value=(True, None))
    @mock.patch("scripts.guard_ivv_pipeline._detect_caller_role")
    def test_negative_qa_engineer_blocked_from_core(
        self, mock_role: mock.MagicMock, _mock_validate: mock.MagicMock
    ) -> None:
        """Negative test: Blocks qa-engineer from mutating business logic."""
        mock_role.return_value = "qa-engineer"
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "sandbox/core/module.py"},
            },
            "transcriptPath": "dummy.jsonl",
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "deny")
        self.assertIn("qa-engineer is restricted from authoring implementation", str(reason))

    @mock.patch("scripts.guard_ivv_pipeline.validate_contract_state")
    @mock.patch("scripts.guard_ivv_pipeline._detect_caller_role")
    def test_negative_subagent_blocked_when_contract_invalid(
        self, mock_role: mock.MagicMock, mock_validate: mock.MagicMock
    ) -> None:
        """Negative test: Blocks subagent when active contract state is invalid."""
        mock_role.return_value = "software-engineer"
        mock_validate.return_value = (False, "Contract missing on disk")
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "sandbox/core/module.py"},
            },
            "transcriptPath": "dummy.jsonl",
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "deny")
        self.assertIsNotNone(reason)
        self.assertIn("CONTRACT_GATE_BLOCKED", str(reason))
        self.assertIn("Contract missing on disk", str(reason))

    def test_emergency_bypass_flag(self) -> None:
        """Positive test: Verifies IVV_BYPASS=1 allows all mutations for emergency recovery."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "core/emergency.py"},
            },
            "transcriptPath": None,
        }
        with mock.patch.dict(os.environ, {"IVV_BYPASS": "1"}):
            decision, reason = evaluate_tool_call(payload)
            self.assertEqual(decision, "allow")
            self.assertIsNone(reason)


class TestGuardCLI(unittest.TestCase):
    """Evaluates standard I/O and JSON streaming for Antigravity hook integration."""

    def test_cli_allow_positive(self) -> None:
        """Positive test: Verifies CLI returns JSON allow response."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "docs/specs/SPEC-001.md"},
            }
        }
        stdin_stream = io.StringIO(json.dumps(payload))
        stdout_stream = io.StringIO()

        with mock.patch("sys.stdin", stdin_stream), mock.patch("sys.stdout", stdout_stream):
            code = main()

        self.assertEqual(code, 0)
        out = json.loads(stdout_stream.getvalue())
        self.assertEqual(out["decision"], "allow")

    def test_negative_cli_deny_on_violation(self) -> None:
        """Negative test: Verifies CLI outputs JSON deny response on policy violation."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "core/cortex.py"},
            }
        }
        stdin_stream = io.StringIO(json.dumps(payload))
        stdout_stream = io.StringIO()

        with mock.patch("sys.stdin", stdin_stream), mock.patch("sys.stdout", stdout_stream):
            code = main()

        self.assertEqual(code, 0)
        out = json.loads(stdout_stream.getvalue())
        self.assertEqual(out["decision"], "deny")
        self.assertIn("reason", out)

    def test_negative_cli_malformed_input_recovers(self) -> None:
        """Negative test: Handles invalid JSON on stdin without crashing."""
        stdin_stream = io.StringIO("MALFORMED_JSON")
        stdout_stream = io.StringIO()

        with mock.patch("sys.stdin", stdin_stream), mock.patch("sys.stdout", stdout_stream):
            code = main()

        self.assertEqual(code, 0)
        out = json.loads(stdout_stream.getvalue())
        self.assertEqual(out["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
