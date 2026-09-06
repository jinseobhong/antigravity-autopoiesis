"""
Companion test suite for Sovereign Orchestrator & Read-Only Subagent Guard Hook.

Evaluates path normalization, transcript role detection, sovereign authoring RBAC, and CLI I/O.
Satisfies AST Anti-Cheat invariants (H-CODE-1 through H-CODE-12) with >= 30% negative test ratio.
"""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.guard_ivv_pipeline import (
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
            prompt = "You are software-engineer. Review code.\n--caller-id: parent-123"
            step_data = {"step_index": 0, "content": prompt}
            transcript.write_text(json.dumps(step_data) + "\n", encoding="utf-8")
            role = _detect_caller_role(str(transcript))
            self.assertEqual(role, "software-engineer")

    def test_detect_qa_engineer_from_transcript(self) -> None:
        """Positive test: Detects qa-engineer from subagent initial prompt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript = Path(tmpdir) / "transcript.jsonl"
            prompt = "You are qa-engineer. Audit test plans.\n--caller-id: parent-123"
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


class TestSovereignAuthoringAccessPolicy(unittest.TestCase):
    """Evaluates sovereign orchestrator authoring and read-only subagent lock."""

    def test_orchestrator_allowed_core_authoring(self) -> None:
        """Positive test: Allows sovereign orchestrator to write core logic directly."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "core/cortex.py"},
            },
            "transcriptPath": None,
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

    def test_orchestrator_allowed_tests_authoring(self) -> None:
        """Positive test: Allows sovereign orchestrator to write tests directly."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "tests/test_cortex.py"},
            },
            "transcriptPath": None,
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

    def test_orchestrator_allowed_docs_and_scripts(self) -> None:
        """Positive test: Allows sovereign orchestrator to edit documentation and scripts."""
        payload = {
            "toolCall": {
                "name": "replace_file_content",
                "args": {"TargetFile": "scripts/preflight_check.py"},
            },
            "transcriptPath": None,
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "allow")
        self.assertIsNone(reason)

    @mock.patch("scripts.guard_ivv_pipeline._detect_caller_role")
    def test_negative_software_engineer_blocked_from_writing(
        self, mock_role: mock.MagicMock
    ) -> None:
        """Negative test: Strictly blocks software-engineer subagent from mutating code."""
        mock_role.return_value = "software-engineer"
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "core/module.py"},
            },
            "transcriptPath": "dummy.jsonl",
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "deny")
        self.assertIsNotNone(reason)
        self.assertIn("READ_ONLY_SUBAGENT_BLOCKED", str(reason))

    @mock.patch("scripts.guard_ivv_pipeline._detect_caller_role")
    def test_negative_qa_engineer_blocked_from_writing(
        self, mock_role: mock.MagicMock
    ) -> None:
        """Negative test: Strictly blocks qa-engineer subagent from mutating tests."""
        mock_role.return_value = "qa-engineer"
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "tests/test_module.py"},
            },
            "transcriptPath": "dummy.jsonl",
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "deny")
        self.assertIsNotNone(reason)
        self.assertIn("READ_ONLY_SUBAGENT_BLOCKED", str(reason))

    @mock.patch("scripts.guard_ivv_pipeline._detect_caller_role")
    def test_negative_technical_writer_blocked_from_writing(
        self, mock_role: mock.MagicMock
    ) -> None:
        """Negative test: Strictly blocks technical-writer subagent from mutating docs."""
        mock_role.return_value = "technical-writer"
        payload = {
            "toolCall": {
                "name": "replace_file_content",
                "args": {"TargetFile": "docs/active/CURRENT_STATE.md"},
            },
            "transcriptPath": "dummy.jsonl",
        }
        decision, reason = evaluate_tool_call(payload)
        self.assertEqual(decision, "deny")
        self.assertIn("READ_ONLY_SUBAGENT_BLOCKED", str(reason))

    def test_emergency_bypass_flag(self) -> None:
        """Positive test: Verifies IVV_BYPASS=1 allows all mutations for emergency recovery."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "core/emergency.py"},
            },
            "transcriptPath": "subagent.jsonl",
        }
        with mock.patch("scripts.guard_ivv_pipeline._detect_caller_role", return_value="software-engineer"):
            with mock.patch.dict(os.environ, {"IVV_BYPASS": "1"}):
                decision, reason = evaluate_tool_call(payload)
                self.assertEqual(decision, "allow")
                self.assertIsNone(reason)


class TestGuardCLI(unittest.TestCase):
    """Evaluates standard I/O and JSON streaming for Antigravity hook integration."""

    def test_cli_allow_positive(self) -> None:
        """Positive test: Verifies CLI returns JSON allow response for orchestrator."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "core/logic.py"},
            }
        }
        stdin_stream = io.StringIO(json.dumps(payload))
        stdout_stream = io.StringIO()

        with mock.patch("sys.stdin", stdin_stream), mock.patch("sys.stdout", stdout_stream):
            code = main()

        self.assertEqual(code, 0)
        out = json.loads(stdout_stream.getvalue())
        self.assertEqual(out["decision"], "allow")

    def test_negative_cli_deny_on_subagent(self) -> None:
        """Negative test: Verifies CLI outputs JSON deny response when subagent writes."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "core/logic.py"},
            },
            "transcriptPath": "subagent.jsonl",
        }
        stdin_stream = io.StringIO(json.dumps(payload))
        stdout_stream = io.StringIO()

        with mock.patch("scripts.guard_ivv_pipeline._detect_caller_role", return_value="software-engineer"):
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
