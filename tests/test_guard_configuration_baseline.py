"""
Companion IV&V test suite for Configuration Baseline & Run Completion Hook.

Conforms to CONTRACT-20260907-configuration-baseline-hook (TASK-031).
Verifies invariants [INV-SCM-01] through [INV-SCM-07] and Anti-Cheat invariants
H-CODE-1 through H-CODE-12 with >= 40% negative assertion ratio.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import unittest
from unittest import mock

try:
    from scripts.guard_configuration_baseline import (
        ARCHITECTURE_SYNC_DIRECTIVE_MESSAGE,
        COMMIT_DIRECTIVE_MESSAGE,
        EPHEMERAL_PATTERNS,
        PREFLIGHT_FAILED_DIRECTIVE_MESSAGE,
        STATE_COMPACTION_DIRECTIVE_MESSAGE,
        ConfigurationBaselineReport,
        HookInvocationContext,
        build_cli_parser,
        check_architecture_sync,
        check_preflight_verification,
        check_state_compaction,
        evaluate_baseline,
        inspect_ledger_tasks,
        is_ephemeral_path,
        main,
        parse_git_status_lines,
        parse_invocation_context,
        query_git_status,
        read_stdin_payload,
        resolve_repo_root,
    )
except ModuleNotFoundError:
    from sandbox.scripts.guard_configuration_baseline import (
        ARCHITECTURE_SYNC_DIRECTIVE_MESSAGE,
        COMMIT_DIRECTIVE_MESSAGE,
        EPHEMERAL_PATTERNS,
        PREFLIGHT_FAILED_DIRECTIVE_MESSAGE,
        STATE_COMPACTION_DIRECTIVE_MESSAGE,
        ConfigurationBaselineReport,
        HookInvocationContext,
        build_cli_parser,
        check_architecture_sync,
        check_preflight_verification,
        check_state_compaction,
        evaluate_baseline,
        inspect_ledger_tasks,
        is_ephemeral_path,
        main,
        parse_git_status_lines,
        parse_invocation_context,
        query_git_status,
        read_stdin_payload,
        resolve_repo_root,
    )


def _resolve_guard_script_path() -> Path:
    """Locates guard_configuration_baseline.py across sandbox and production roots."""
    candidates = [
        Path(__file__).resolve().parent.parent / "scripts" / "guard_configuration_baseline.py",
        Path(__file__).resolve().parent.parent / "sandbox" / "scripts" / "guard_configuration_baseline.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _init_git_repo(repo_dir: Path, is_dirty: bool) -> None:
    """Initializes a deterministic git repository in temp directory."""
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True, timeout=5.0)
    subprocess.run(["git", "config", "user.email", "ivv@example.com"], cwd=repo_dir, check=True, timeout=5.0)
    subprocess.run(["git", "config", "user.name", "IVVTester"], cwd=repo_dir, check=True, timeout=5.0)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        timeout=5.0,
    )
    if is_dirty:
        (repo_dir / "uncommitted_drift.txt").write_text("drift content", encoding="utf-8")


class TestConfigurationBaselineDataModels(unittest.TestCase):
    """Evaluates immutability, serialization, and contract conformance of data models."""

    def test_report_instantiation_nominal(self) -> None:
        """Positive test: Instantiates ConfigurationBaselineReport with valid fields."""
        report = ConfigurationBaselineReport(
            active_tasks=("TASK-031",),
            uncommitted_files=("file1.py",),
            is_git_clean=False,
            decision="continue",
            explanation="Action required",
        )
        self.assertEqual(report.active_tasks, ("TASK-031",))
        self.assertEqual(report.uncommitted_files, ("file1.py",))
        self.assertEqual(report.is_git_clean, False)
        self.assertEqual(report.decision, "continue")
        self.assertEqual(report.explanation, "Action required")

    def test_report_to_hook_response_allow(self) -> None:
        """Positive test: Verifies allow decision returns empty dict."""
        report = ConfigurationBaselineReport(
            active_tasks=("TASK-031",),
            uncommitted_files=(),
            is_git_clean=True,
            decision="allow",
        )
        self.assertEqual(report.to_hook_response(), {})

    def test_report_to_hook_response_continue_custom_message(self) -> None:
        """Positive test: Verifies continue decision serializes explanation and reason."""
        custom_msg = "Must commit before stop."
        report = ConfigurationBaselineReport(
            active_tasks=(),
            uncommitted_files=("dirty.py",),
            is_git_clean=False,
            decision="continue",
            explanation=custom_msg,
        )
        resp = report.to_hook_response()
        self.assertEqual(resp.get("decision"), "continue")
        self.assertEqual(resp.get("explanation"), custom_msg)
        self.assertEqual(resp.get("reason"), custom_msg)

    def test_negative_report_immutability_decision_mutation(self) -> None:
        """Negative test: Mutating decision attribute on frozen report raises FrozenInstanceError."""
        report = ConfigurationBaselineReport(
            active_tasks=(),
            uncommitted_files=(),
            is_git_clean=True,
            decision="allow",
        )
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            setattr(report, "decision", "continue")

    def test_negative_report_immutability_active_tasks_mutation(self) -> None:
        """Negative test: Mutating active_tasks on frozen report raises FrozenInstanceError."""
        report = ConfigurationBaselineReport(
            active_tasks=("TASK-001",),
            uncommitted_files=(),
            is_git_clean=True,
            decision="allow",
        )
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            setattr(report, "active_tasks", ("TASK-002",))

    def test_context_instantiation_nominal(self) -> None:
        """Positive test: Instantiates HookInvocationContext with valid parameters."""
        ctx = HookInvocationContext(
            cwd="/workspace/root",
            transcript_path="/workspace/transcript.jsonl",
            stop_reason="task_completed",
        )
        self.assertEqual(ctx.cwd, "/workspace/root")
        self.assertEqual(ctx.transcript_path, "/workspace/transcript.jsonl")
        self.assertEqual(ctx.stop_reason, "task_completed")

    def test_negative_context_immutability(self) -> None:
        """Negative test: Mutating cwd on frozen context raises FrozenInstanceError."""
        ctx = HookInvocationContext(cwd="/initial")
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            setattr(ctx, "cwd", "/mutated")


class TestGitStatusParser(unittest.TestCase):
    """Evaluates porcelain status parsing, path normalization, and ephemeral filtering."""

    def test_parse_clean_porcelain_returns_empty(self) -> None:
        """Positive test: Clean working tree status returns empty tuple."""
        self.assertEqual(parse_git_status_lines(""), ())

    def test_parse_modified_and_untracked_files(self) -> None:
        """Positive test: Parses modified, untracked, and added porcelain entries."""
        text = " M core/engine.py\n?? tests/test_new.py\nA  docs/spec.md\n"
        parsed = parse_git_status_lines(text)
        self.assertEqual(parsed, ("core/engine.py", "docs/spec.md", "tests/test_new.py"))

    def test_parse_renamed_files_target_path(self) -> None:
        """Positive test: Renamed entries extract only destination path."""
        text = "R  old_file.py -> new_file.py\n"
        parsed = parse_git_status_lines(text)
        self.assertEqual(parsed, ("new_file.py",))

    def test_negative_parse_filters_ephemeral_patterns(self) -> None:
        """Negative test: Filters out coverage, pycache, temp files, and spool logs."""
        text = (
            " M .coverage\n"
            "?? __pycache__/module.cpython-312.pyc\n"
            "?? cortex_spool.jsonl\n"
            "?? temp.tmp\n"
            " M core/real_code.py\n"
        )
        parsed = parse_git_status_lines(text)
        self.assertEqual(parsed, ("core/real_code.py",))
        self.assertNotIn(".coverage", parsed)
        self.assertNotIn("cortex_spool.jsonl", parsed)

    def test_negative_parse_ignores_blank_and_short_lines(self) -> None:
        """Negative test: Discards blank, whitespace, and truncated lines."""
        text = "   \n\n\t\n?? \n  \n"
        self.assertEqual(parse_git_status_lines(text), ())

    def test_negative_is_ephemeral_path_evaluation(self) -> None:
        """Negative test: Asserts non-ephemeral paths evaluate to False."""
        self.assertEqual(is_ephemeral_path("core/engine.py"), False)
        self.assertEqual(is_ephemeral_path("scripts/guard.py"), False)
        self.assertEqual(is_ephemeral_path("docs/spec.md"), False)

    def test_is_ephemeral_path_true_patterns(self) -> None:
        """Positive test: Asserts defined ephemeral patterns evaluate to True."""
        for pattern in EPHEMERAL_PATTERNS:
            self.assertEqual(is_ephemeral_path(f"some/dir/{pattern}"), True)


class TestGitStatusQuery(unittest.TestCase):
    """Evaluates subprocess git status query with fault injection and fail-open handling."""

    def test_query_git_status_success(self) -> None:
        """Positive test: Successful git status porcelain returns parsed tuple."""
        completed = subprocess.CompletedProcess(
            args=["git", "status", "--porcelain"],
            returncode=0,
            stdout=" M core/app.py\n",
            stderr="",
        )
        with mock.patch("subprocess.run", return_value=completed):
            res = query_git_status(Path("dummy_repo"))
        self.assertEqual(res, ("core/app.py",))

    def test_negative_query_git_status_non_zero_exit_fail_open(self) -> None:
        """Negative test: Non-zero exit code (e.g. not a git repo) fails open with empty tuple."""
        completed = subprocess.CompletedProcess(
            args=["git", "status", "--porcelain"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )
        with mock.patch("subprocess.run", return_value=completed):
            res = query_git_status(Path("dummy_repo"))
        self.assertEqual(res, ())

    def test_negative_query_git_status_timeout_fail_open(self) -> None:
        """Negative test: Subprocess timeout fails open returning empty tuple."""
        timeout_err = subprocess.TimeoutExpired(cmd=["git", "status"], timeout=5.0)
        with mock.patch("subprocess.run", side_effect=timeout_err):
            res = query_git_status(Path("dummy_repo"))
        self.assertEqual(res, ())

    def test_negative_query_git_status_oserror_fail_open(self) -> None:
        """Negative test: Missing git executable or OSError fails open returning empty tuple."""
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            res = query_git_status(Path("dummy_repo"))
        self.assertEqual(res, ())

    def test_negative_query_git_status_unicode_decode_error_fail_open(self) -> None:
        """Negative test: UnicodeDecodeError fails open returning empty tuple."""
        decode_err = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        with mock.patch("subprocess.run", side_effect=decode_err):
            res = query_git_status(Path("dummy_repo"))
        self.assertEqual(res, ())


class TestCurrentStateLedgerInspection(unittest.TestCase):
    """Evaluates CURRENT_STATE.md parsing, active task detection, and capacity checks."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_ledger(self, content: str) -> Path:
        ledger_path = self.work_dir / "CURRENT_STATE.md"
        ledger_path.write_text(content, encoding="utf-8")
        return ledger_path

    def test_extract_active_tasks_in_progress(self) -> None:
        """Positive test: Extracts task IDs marked IN_PROGRESS from markdown table."""
        content = (
            "# State Ledger\n"
            "| Task ID | Description | Status |\n"
            "| :--- | :--- | :--- |\n"
            "| **`TASK-031`** | Baseline Hook | `IN_PROGRESS` |\n"
            "| **`TASK-032`** | Auxiliary Engine | IN_PROGRESS |\n"
            "| **`TASK-001`** | Antigravity | `PROMOTED` |\n"
        )
        ledger = self._create_ledger(content)
        tasks, has_active = inspect_ledger_tasks(ledger)
        self.assertEqual(tasks, ("TASK-031", "TASK-032"))
        self.assertEqual(has_active, True)

    def test_check_active_capacity_occupied_slots(self) -> None:
        """Positive test: Recognizes occupied capacity slots when capacity line reports > 0."""
        content = (
            "# State Ledger\n"
            "- Active Task Capacity: 2 of 5 slots occupied.\n"
        )
        ledger = self._create_ledger(content)
        tasks, has_active = inspect_ledger_tasks(ledger)
        self.assertEqual(tasks, ())
        self.assertEqual(has_active, True)

    def test_negative_extract_active_tasks_all_promoted(self) -> None:
        """Negative test: Returns empty tuple when all tasks are PROMOTED or VERIFIED."""
        content = (
            "# State Ledger\n"
            "- Active Task Capacity: 0 of 5\n"
            "| Task ID | Description | Status |\n"
            "| **`TASK-001`** | Constitution | `PROMOTED` |\n"
            "| **`TASK-002`** | Architecture | `VERIFIED` |\n"
        )
        ledger = self._create_ledger(content)
        tasks, has_active = inspect_ledger_tasks(ledger)
        self.assertEqual(tasks, ())
        self.assertEqual(has_active, False)

    def test_negative_check_active_capacity_zero_occupied(self) -> None:
        """Negative test: Returns False when capacity line reports 0 of 5 slots."""
        content = (
            "# State Ledger\n"
            "- Active Task Capacity: 0 of 5\n"
        )
        ledger = self._create_ledger(content)
        tasks, has_active = inspect_ledger_tasks(ledger)
        self.assertEqual(tasks, ())
        self.assertEqual(has_active, False)

    def test_negative_inspect_ledger_nonexistent_file(self) -> None:
        """Negative test: Non-existent ledger file returns empty tasks and False."""
        missing = self.work_dir / "MISSING_CURRENT_STATE.md"
        tasks, has_active = inspect_ledger_tasks(missing)
        self.assertEqual(tasks, ())
        self.assertEqual(has_active, False)

    def test_negative_inspect_ledger_directory_path(self) -> None:
        """Negative test: Ledger path pointing to directory returns empty tasks and False."""
        tasks, has_active = inspect_ledger_tasks(self.work_dir)
        self.assertEqual(tasks, ())
        self.assertEqual(has_active, False)

    def test_negative_inspect_ledger_oserror_handled(self) -> None:
        """Negative test: OSError during read fails open gracefully without exception."""
        ledger = self._create_ledger("some content")
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            tasks, has_active = inspect_ledger_tasks(ledger)
        self.assertEqual(tasks, ())
        self.assertEqual(has_active, False)


class TestBaselineEvaluationCore(unittest.TestCase):
    """Evaluates core baseline evaluation logic satisfying V-Matrix INV-SCM-01 through INV-SCM-04."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.active_ledger = self.work_dir / "active_state.md"
        self.active_ledger.write_text(
            "# State\nActive Task Capacity: 1 of 5\n| **`TASK-031`** | Hook | `IN_PROGRESS` |\n",
            encoding="utf-8",
        )
        self.idle_ledger = self.work_dir / "idle_state.md"
        self.idle_ledger.write_text(
            "# State\nActive Task Capacity: 0 of 5\n| **`TASK-001`** | Init | `PROMOTED` |\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_status_inspection(self) -> None:
        """[INV-SCM-01] Status inspection completes within 100ms latency threshold."""
        start = time.perf_counter()
        report = evaluate_baseline(
            repo_root=self.work_dir,
            ledger_path=self.idle_ledger,
            uncommitted_override=(),
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        self.assertLessEqual(duration_ms, 100.0)
        self.assertEqual(report.decision, "allow")
        self.assertEqual(report.is_git_clean, True)

    def test_negative_dirty_no_active_task(self) -> None:
        """[INV-SCM-02] Negative test: Dirty working tree with no active tasks returns continue."""
        report = evaluate_baseline(
            repo_root=self.work_dir,
            ledger_path=self.idle_ledger,
            uncommitted_override=("tests/drift.py",),
        )
        self.assertEqual(report.decision, "continue")
        self.assertEqual(report.is_git_clean, False)
        self.assertIn("uncommitted modifications", str(report.explanation))
        resp = report.to_hook_response()
        self.assertEqual(resp.get("decision"), "continue")
        self.assertIn("[MANDATORY SCM COMMIT]", str(resp.get("reason")))
        self.assertIn("[MANDATORY SCM COMMIT]", str(resp.get("explanation")))

    def test_active_task_permits_stop(self) -> None:
        """[INV-SCM-03] Positive test: Active task permits turn completion even if dirty."""
        report = evaluate_baseline(
            repo_root=self.work_dir,
            ledger_path=self.active_ledger,
            uncommitted_override=("tests/in_flight.py",),
        )
        self.assertEqual(report.decision, "allow")
        self.assertEqual(report.active_tasks, ("TASK-031",))
        self.assertEqual(report.to_hook_response(), {})

    def test_clean_status_permits_stop(self) -> None:
        """[INV-SCM-04] Positive test: Clean git status permits turn completion without active task."""
        report = evaluate_baseline(
            repo_root=self.work_dir,
            ledger_path=self.idle_ledger,
            uncommitted_override=(),
        )
        self.assertEqual(report.decision, "allow")
        self.assertEqual(report.is_git_clean, True)
        self.assertEqual(report.to_hook_response(), {})

    def test_negative_dirty_uncommitted_override_multiple_files(self) -> None:
        """Negative test: Multiple uncommitted files without active tasks require commit."""
        report = evaluate_baseline(
            repo_root=self.work_dir,
            ledger_path=self.idle_ledger,
            uncommitted_override=("tests/a.py", "sandbox/b.py"),
        )
        self.assertEqual(report.decision, "continue")
        self.assertEqual(len(report.uncommitted_files), 2)
        self.assertEqual(report.is_git_clean, False)


class TestStdinAndContextParsing(unittest.TestCase):
    """Evaluates non-blocking stdin handling, context extraction, and error resilience."""

    def test_parse_invocation_context_nominal(self) -> None:
        """Positive test: Extracts cwd, transcriptPath, and stopReason from payload."""
        payload = {
            "cwd": "/project/root",
            "transcriptPath": "/project/transcript.jsonl",
            "stopReason": "agent_finished",
        }
        ctx = parse_invocation_context(payload)
        self.assertEqual(ctx.cwd, "/project/root")
        self.assertEqual(ctx.transcript_path, "/project/transcript.jsonl")
        self.assertEqual(ctx.stop_reason, "agent_finished")

    def test_parse_invocation_context_fallback_defaults(self) -> None:
        """Positive test: Missing fields fallback to current working directory and None."""
        ctx = parse_invocation_context({})
        self.assertEqual(ctx.cwd, str(os.getcwd()))
        self.assertIsNone(ctx.transcript_path)
        self.assertIsNone(ctx.stop_reason)

    def test_negative_read_stdin_empty_stream(self) -> None:
        """Negative test: Empty stdin returns empty dict."""
        with mock.patch("sys.stdin", io.StringIO("")):
            res = read_stdin_payload()
        self.assertEqual(res, {})

    def test_negative_read_stdin_corrupted_json(self) -> None:
        """Negative test: Malformed JSON string on stdin fails open returning empty dict."""
        with mock.patch("sys.stdin", io.StringIO("MALFORMED_JSON_{")):
            res = read_stdin_payload()
        self.assertEqual(res, {})

    def test_negative_read_stdin_whitespace_only(self) -> None:
        """Negative test: Whitespace-only stdin returns empty dict."""
        with mock.patch("sys.stdin", io.StringIO("   \n\t   \n")):
            res = read_stdin_payload()
        self.assertEqual(res, {})

    def test_negative_read_stdin_json_list_returns_empty(self) -> None:
        """Negative test: Non-dict JSON payload returns empty dict."""
        with mock.patch("sys.stdin", io.StringIO('["not", "a", "dict"]')):
            res = read_stdin_payload()
        self.assertEqual(res, {})


class TestGuardCLI(unittest.TestCase):
    """Evaluates CLI arguments, check-only exit codes, and JSON serialization."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.clean_ledger = self.work_dir / "clean_ledger.md"
        self.clean_ledger.write_text(
            "# State\nActive Task Capacity: 1 of 5\n| **`TASK-031`** | Hook | `IN_PROGRESS` |\n",
            encoding="utf-8",
        )
        self.idle_ledger = self.work_dir / "idle_ledger.md"
        self.idle_ledger.write_text(
            "# State\nActive Task Capacity: 0 of 5\n| **`TASK-001`** | Done | `PROMOTED` |\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_clean_stop_permitted(self) -> None:
        """Positive test: Standard CLI invocation on clean repo outputs empty JSON and exits 0."""
        stdout_buf = io.StringIO()
        with mock.patch("sys.stdout", stdout_buf), mock.patch("sys.stdin", io.StringIO("")):
            code = main(["--repo-root", str(self.work_dir), "--ledger", str(self.clean_ledger)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout_buf.getvalue()), {})

    def test_cli_check_only_clean_exits_0(self) -> None:
        """Positive test: CLI with --check-only on clean repo returns exit code 0."""
        with mock.patch("sys.stdin", io.StringIO("")):
            code = main([
                "--check-only",
                "--repo-root",
                str(self.work_dir),
                "--ledger",
                str(self.clean_ledger),
            ])
        self.assertEqual(code, 0)

    def test_negative_cli_check_only_dirty_idle_exits_1(self) -> None:
        """Negative test: CLI with --check-only on dirty idle repo returns exit code 1."""
        dirty_dir = self.work_dir / "dirty_repo"
        dirty_dir.mkdir(parents=True, exist_ok=True)
        _init_git_repo(dirty_dir, is_dirty=True)

        with mock.patch("sys.stdin", io.StringIO("")):
            code = main([
                "--check-only",
                "--repo-root",
                str(dirty_dir),
                "--ledger",
                str(self.idle_ledger),
            ])
        self.assertEqual(code, 1)

    def test_cli_json_flag_outputs_valid_schema(self) -> None:
        """Positive test: CLI with --json outputs complete ConfigurationBaselineReport JSON."""
        stdout_buf = io.StringIO()
        with mock.patch("sys.stdout", stdout_buf), mock.patch("sys.stdin", io.StringIO("")):
            code = main([
                "--json",
                "--repo-root",
                str(self.work_dir),
                "--ledger",
                str(self.clean_ledger),
            ])
        self.assertEqual(code, 0)
        parsed = json.loads(stdout_buf.getvalue())
        self.assertIn("active_tasks", parsed)
        self.assertIn("uncommitted_files", parsed)
        self.assertIn("is_git_clean", parsed)
        self.assertIn("decision", parsed)
        self.assertIn("explanation", parsed)
        self.assertIn("hook_response", parsed)

    def test_negative_cli_stdin_corrupted_fail_open(self) -> None:
        """Negative test: CLI with corrupted stdin payload executes cleanly without crash."""
        stdout_buf = io.StringIO()
        with mock.patch("sys.stdout", stdout_buf), mock.patch("sys.stdin", io.StringIO("{broken")):
            code = main(["--repo-root", str(self.work_dir), "--ledger", str(self.clean_ledger)])
        self.assertEqual(code, 0)

    def test_cli_subprocess_check_only_clean_exit_0(self) -> None:
        """Positive test: Direct subprocess invocation with --check-only on clean repo exits 0."""
        script_path = _resolve_guard_script_path()
        proc = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--check-only",
                "--repo-root",
                str(self.work_dir),
                "--ledger",
                str(self.clean_ledger),
            ],
            capture_output=True,
            text=True,
            timeout=5.0,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(proc.returncode, 0)

    def test_negative_cli_subprocess_check_only_dirty_idle_exit_1(self) -> None:
        """Negative test: Direct subprocess invocation with --check-only on dirty idle repo exits 1."""
        script_path = _resolve_guard_script_path()
        dirty_dir = self.work_dir / "dirty_sub_repo"
        dirty_dir.mkdir(parents=True, exist_ok=True)
        _init_git_repo(dirty_dir, is_dirty=True)

        proc = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--check-only",
                "--repo-root",
                str(dirty_dir),
                "--ledger",
                str(self.idle_ledger),
            ],
            capture_output=True,
            text=True,
            timeout=5.0,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(proc.returncode, 1)


class TestArchitectureSyncGuard(unittest.TestCase):
    """Evaluates mechanical Architecture Sync Guard enforcing ARCHITECTURE.md synchronization."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.active_ledger = self.work_dir / "active_state.md"
        self.active_ledger.write_text(
            "# State\nActive Task Capacity: 1 of 5\n| **`TASK-035`** | Arch Sync | `IN_PROGRESS` |\n",
            encoding="utf-8",
        )
        self.idle_ledger = self.work_dir / "idle_state.md"
        self.idle_ledger.write_text(
            "# State\nActive Task Capacity: 0 of 5\n| **`TASK-001`** | Init | `PROMOTED` |\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_arch_sync_no_core_changes_allows(self) -> None:
        """Positive test: Non-core changes (e.g. tests/, docs/specs/) bypass architecture sync."""
        is_synced, msg = check_architecture_sync(("tests/test_foo.py", "docs/specs/bar.md"))
        self.assertEqual(is_synced, True)
        self.assertIsNone(msg)

    def test_arch_sync_core_and_doc_modified_allows(self) -> None:
        """Positive test: Modifying core/ accompanied by ARCHITECTURE.md satisfies sync check."""
        is_synced, msg = check_architecture_sync((
            "core/shadow_grounding.py",
            "docs/active/ARCHITECTURE.md",
        ))
        self.assertEqual(is_synced, True)
        self.assertIsNone(msg)

    def test_negative_arch_sync_core_modified_without_arch_doc(self) -> None:
        """Negative test: Modifying core/ without ARCHITECTURE.md triggers sync directive."""
        is_synced, msg = check_architecture_sync(("core/shadow_grounding.py", "tests/test_shadow.py"))
        self.assertEqual(is_synced, False)
        self.assertEqual(msg, ARCHITECTURE_SYNC_DIRECTIVE_MESSAGE)
        self.assertIn("[ARCHITECTURE SYNC REQUIRED]", str(msg))

    def test_negative_arch_sync_blocks_stop_even_with_active_task(self) -> None:
        """Negative test: Core modifications block turn completion even when a task is IN_PROGRESS."""
        report = evaluate_baseline(
            repo_root=self.work_dir,
            ledger_path=self.active_ledger,
            uncommitted_override=("core/evolutionary_engine.py",),
        )
        self.assertEqual(report.decision, "continue")
        self.assertEqual(report.explanation, ARCHITECTURE_SYNC_DIRECTIVE_MESSAGE)
        resp = report.to_hook_response()
        self.assertEqual(resp.get("decision"), "continue")
        self.assertIn("[ARCHITECTURE SYNC REQUIRED]", str(resp.get("reason")))

    def test_arch_sync_permits_stop_when_arch_doc_present_with_active_task(self) -> None:
        """Positive test: Core modifications permit turn stop if ARCHITECTURE.md is present."""
        report = evaluate_baseline(
            repo_root=self.work_dir,
            ledger_path=self.active_ledger,
            uncommitted_override=(
                "core/evolutionary_engine.py",
                "docs/active/ARCHITECTURE.md",
            ),
        )
        self.assertEqual(report.decision, "allow")
        self.assertEqual(report.to_hook_response(), {})

    def test_negative_arch_sync_windows_path_delimiters_normalized(self) -> None:
        """Negative test: Windows backslashes in paths are normalized and properly flagged."""
        is_synced, msg = check_architecture_sync((r"core\submodule\feature.py",))
        self.assertEqual(is_synced, False)
        self.assertIn("[ARCHITECTURE SYNC REQUIRED]", str(msg))


class TestStateCompactionGuard(unittest.TestCase):
    """Evaluates Stop Hook enforcement of state ledger compaction when promoted tasks >= 10."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.compact_ledger = self.work_dir / "compact_state.md"
        self.compact_ledger.write_text(
            "# State\n"
            "Active Task Capacity: 0 of 5\n"
            "| **`TASK-031`** | Hook | `PROMOTED` | 0/2 | Tier 2 | Eng | Pass |\n"
            "| **`TASK-032`** | Agent | `PROMOTED` | 0/2 | Tier 2 | Eng | Pass |\n",
            encoding="utf-8",
        )
        rows = "\n".join(
            f"| **`TASK-0{i}`** | Desc {i} | `PROMOTED` | 0/2 | Tier 2 | Eng | Pass |"
            for i in range(10, 20)
        )
        self.bloated_ledger = self.work_dir / "bloated_state.md"
        self.bloated_ledger.write_text(
            f"# State\nActive Task Capacity: 0 of 5\n### 3.2 Current State Task Ledger\n\n{rows}\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_compaction_guard_allows_when_under_threshold(self) -> None:
        """Positive test: Ledger with 2 tasks (< 10 threshold) clears compaction check."""
        is_compact, msg = check_state_compaction(self.compact_ledger, threshold=10)
        self.assertEqual(is_compact, True)
        self.assertIsNone(msg)

    def test_negative_compaction_guard_blocks_when_at_or_above_threshold(self) -> None:
        """Negative test: Ledger with 10 promoted tasks returns continue directive."""
        is_compact, msg = check_state_compaction(self.bloated_ledger, threshold=10)
        self.assertEqual(is_compact, False)
        self.assertIsNotNone(msg)
        self.assertIn("[STATE COMPACTION REQUIRED]", str(msg))

    def test_negative_baseline_evaluation_blocks_turn_when_compaction_needed(self) -> None:
        """Negative test: evaluate_baseline intercepts turn completion when compaction required."""
        report = evaluate_baseline(
            repo_root=self.work_dir,
            ledger_path=self.bloated_ledger,
            uncommitted_override=(),
            compaction_threshold=10,
        )
        self.assertEqual(report.decision, "continue")
        self.assertIn("[STATE COMPACTION REQUIRED]", str(report.explanation))
        resp = report.to_hook_response()
        self.assertEqual(resp.get("decision"), "continue")
        self.assertIn("[STATE COMPACTION REQUIRED]", str(resp.get("reason")))

    def test_negative_compaction_guard_nonexistent_ledger_fail_open(self) -> None:
        """Negative test: Non-existent ledger file fails open cleanly without raising exception."""
        is_compact, msg = check_state_compaction(self.work_dir / "MISSING.md", threshold=10)
        self.assertEqual(is_compact, True)
        self.assertIsNone(msg)


class TestHookGovernanceAndVerificationMatrix(unittest.TestCase):
    """Evaluates hook registration and AST anti-cheat compliance (INV-SCM-06, INV-SCM-07)."""

    def test_hooks_registration(self) -> None:
        """[INV-SCM-06] Verifies .agents/hooks.json registers configuration-baseline-guard under Stop."""
        repo_root = resolve_repo_root()
        hooks_path = repo_root / ".agents" / "hooks.json"
        self.assertEqual(hooks_path.exists(), True)

        raw = hooks_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        self.assertIn("configuration-baseline-guard", parsed)

        guard_config = parsed["configuration-baseline-guard"]
        self.assertIn("Stop", guard_config)
        stop_entries = guard_config["Stop"]
        self.assertGreater(len(stop_entries), 0)

        entry = stop_entries[0]
        self.assertEqual(entry.get("type"), "command")
        command = entry.get("command", "")
        self.assertIn("guard_configuration_baseline.py", command)
        self.assertGreaterEqual(entry.get("timeout", 0), 5)

    def test_negative_assertion_ratio(self) -> None:
        """[INV-SCM-07] Verifies test suite maintains elevated negative assertion ratio >= 30%."""
        test_path = Path(__file__).resolve()
        tree = ast.parse(test_path.read_text(encoding="utf-8"))

        total_assertions = 0
        negative_assertions = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                is_negative = node.name.startswith("test_negative_")
                for subnode in ast.walk(node):
                    if isinstance(subnode, ast.Call):
                        func = subnode.func
                        if isinstance(func, ast.Attribute) and func.attr.startswith("assert"):
                            total_assertions += 1
                            if is_negative:
                                negative_assertions += 1

        self.assertGreater(total_assertions, 0)
        ratio = negative_assertions / total_assertions
        self.assertGreaterEqual(
            ratio,
            0.30,
            f"Negative assertion ratio {ratio:.2%} violates >= 30% contract minimum (INV-SCM-07)",
        )
        self.assertGreaterEqual(
            ratio,
            0.40,
            f"Negative assertion ratio {ratio:.2%} violates >= 40% adversarial standard (H-CODE-3)",
        )


class TestConfigurationBaselinePreflight(unittest.TestCase):
    """Evaluates Stop hook preflight verification integration and gating."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.repo_dir = Path(self.temp_dir.name)
        _init_git_repo(self.repo_dir, is_dirty=False)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_check_preflight_no_tests_directory_passes(self) -> None:
        """Positive test: When repo has no tests/ directory, preflight verification passes."""
        passed, diag = check_preflight_verification(self.repo_dir)
        self.assertTrue(passed)
        self.assertIsNone(diag)

    def test_check_preflight_with_custom_runner_success(self) -> None:
        """Positive test: Custom passing preflight runner returns True."""
        mock_runner = mock.MagicMock(return_value=(True, ""))
        passed, diag = check_preflight_verification(self.repo_dir, runner=mock_runner)
        self.assertTrue(passed)
        self.assertIsNone(diag)

    def test_evaluate_baseline_allows_when_preflight_passes(self) -> None:
        """Positive test: evaluate_baseline allows stop when preflight runner succeeds."""
        mock_runner = mock.MagicMock(return_value=(True, ""))
        report = evaluate_baseline(
            self.repo_dir,
            check_preflight=True,
            preflight_runner=mock_runner,
        )
        self.assertTrue(report.is_git_clean)
        self.assertEqual(report.decision, "allow")
        self.assertIsNone(report.explanation)

    def test_negative_check_preflight_with_custom_runner_failure(self) -> None:
        """Negative test: Custom failing preflight runner returns False with formatted message."""
        mock_runner = mock.MagicMock(return_value=(False, "1 failure, 2 defects"))
        (self.repo_dir / "tests").mkdir(parents=True, exist_ok=True)
        passed, diag = check_preflight_verification(self.repo_dir, runner=mock_runner)
        self.assertFalse(passed)
        self.assertIsNotNone(diag)
        self.assertIn("[PREFLIGHT VERIFICATION FAILED]", str(diag))
        self.assertIn("1 failure, 2 defects", str(diag))

    def test_negative_check_preflight_runner_exception_handling(self) -> None:
        """Negative test: Preflight runner exception is handled fail-open/containment."""
        mock_runner = mock.MagicMock(side_effect=RuntimeError("Subprocess timeout"))
        (self.repo_dir / "tests").mkdir(parents=True, exist_ok=True)
        passed, diag = check_preflight_verification(self.repo_dir, runner=mock_runner)
        self.assertFalse(passed)
        self.assertIsNotNone(diag)
        self.assertIn("[PREFLIGHT EXECUTION ERROR]", str(diag))
        self.assertIn("Subprocess timeout", str(diag))

    def test_negative_evaluate_baseline_blocks_when_preflight_fails(self) -> None:
        """Negative test: evaluate_baseline returns continue when preflight check fails."""
        mock_runner = mock.MagicMock(return_value=(False, "3 test failures"))
        (self.repo_dir / "tests").mkdir(parents=True, exist_ok=True)
        report = evaluate_baseline(
            self.repo_dir,
            check_preflight=True,
            preflight_runner=mock_runner,
        )
        self.assertTrue(report.is_git_clean)
        self.assertEqual(report.decision, "continue")
        self.assertIsNotNone(report.explanation)
        self.assertIn("[PREFLIGHT VERIFICATION FAILED]", str(report.explanation))
        self.assertIn("3 test failures", str(report.explanation))

    def test_negative_evaluate_baseline_preflight_skip_flag(self) -> None:
        """Negative test: When check_preflight is False, failing runner is bypassed."""
        mock_runner = mock.MagicMock(return_value=(False, "Should be skipped"))
        report = evaluate_baseline(
            self.repo_dir,
            check_preflight=False,
            preflight_runner=mock_runner,
        )
        self.assertEqual(report.decision, "allow")
        self.assertIsNone(report.explanation)
        mock_runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
