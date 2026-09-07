"""Companion test suite for scripts/guard_preinvocation_hud.py.

Verifies PreInvocation lifecycle hook execution, payload resolution,
COGNITIVE_HUD.html rendering, context injection formatting, and fail-open resilience.
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Dict
import unittest

from scripts.guard_preinvocation_hud import (
    PreInvocationHudResult,
    _format_ephemeral_message,
    _resolve_artifact_dir,
    _resolve_repo_root,
    process_preinvocation,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestGuardPreInvocationHud(unittest.TestCase):
    """Test suite for PreInvocation HUD Hook."""

    def test_resolve_repo_root_fallback(self) -> None:
        """Verify fallback to REPO_ROOT when workspacePaths is missing."""
        root = _resolve_repo_root({})
        self.assertEqual(root.resolve(), REPO_ROOT.resolve())

    def test_resolve_repo_root_custom(self) -> None:
        """Verify resolution when valid workspacePath is provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = {"workspacePaths": [tmpdir]}
            root = _resolve_repo_root(payload)
            self.assertEqual(root.resolve(), Path(tmpdir).resolve())

    def test_resolve_artifact_dir_custom(self) -> None:
        """Verify resolution of custom artifactDirectoryPath."""
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = {"artifactDirectoryPath": tmpdir}
            art = _resolve_artifact_dir(payload, REPO_ROOT)
            self.assertEqual(art.resolve(), Path(tmpdir).resolve())

    def test_resolve_artifact_dir_fallback(self) -> None:
        """Verify fallback to docs/active when no artifactDirectoryPath is given."""
        art = _resolve_artifact_dir({}, REPO_ROOT)
        expected = REPO_ROOT / "docs" / "active"
        self.assertEqual(art.resolve(), expected.resolve())

    def test_process_preinvocation_nominal(self) -> None:
        """Verify end-to-end processing with real repo root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = {
                "workspacePaths": [str(REPO_ROOT)],
                "artifactDirectoryPath": tmpdir,
            }
            inject_payload, result = process_preinvocation(payload)

            self.assertTrue(result.success)
            self.assertIn("injectSteps", inject_payload)
            steps = inject_payload["injectSteps"]
            self.assertGreater(len(steps), 0)

            msg = steps[0].get("ephemeralMessage", "")
            self.assertIn("[4-Layer Cognitive HUD PreInvocation Sync]", msg)
            self.assertIn("COGNITIVE_HUD.html", msg)
            self.assertIn("<agent-embed", msg)

            target_file = Path(tmpdir) / "COGNITIVE_HUD.html"
            self.assertTrue(target_file.exists())
            self.assertGreater(target_file.stat().st_size, 500)

    def test_cli_check_only(self) -> None:
        """Verify CLI execution with --check-only flag."""
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "guard_preinvocation_hud.py"),
            "--check-only",
        ]
        res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=10.0)
        self.assertEqual(res.returncode, 0)
        parsed = json.loads(res.stdout)
        self.assertIn("injectSteps", parsed)

    def test_cli_json_flag(self) -> None:
        """Verify CLI execution with --json flag."""
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "guard_preinvocation_hud.py"),
            "--check-only",
            "--json",
        ]
        res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=10.0)
        self.assertEqual(res.returncode, 0)
        parsed = json.loads(res.stdout)
        self.assertIn("beacon", parsed)
        self.assertTrue(parsed.get("success", False))

    # ==========================================================================
    # Negative & Edge Containment Tests (>= 30% ratio)
    # ==========================================================================

    def test_resolve_repo_root_invalid_path_fail_open(self) -> None:
        """Verify fail-open resolution when nonexistent workspacePath is given."""
        payload = {"workspacePaths": ["/non/existent/path/xyz/123"]}
        root = _resolve_repo_root(payload)
        self.assertEqual(root.resolve(), REPO_ROOT.resolve())

    def test_resolve_artifact_dir_invalid_path_fail_open(self) -> None:
        """Verify fail-open resolution when nonexistent artifact path is given."""
        payload = {"artifactDirectoryPath": "/non/existent/path/art/456"}
        art = _resolve_artifact_dir(payload, REPO_ROOT)
        self.assertEqual(art.resolve(), (REPO_ROOT / "docs" / "active").resolve())

    def test_cli_corrupted_stdin_fail_open(self) -> None:
        """Verify script handles garbage stdin without crashing."""
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "guard_preinvocation_hud.py"),
        ]
        res = subprocess.run(
            cmd,
            input="NOT_A_JSON_STRING{{{",
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        self.assertEqual(res.returncode, 0)
        parsed = json.loads(res.stdout)
        self.assertIn("injectSteps", parsed)

    def test_process_preinvocation_empty_tempdir_fail_open(self) -> None:
        """Verify graceful processing against an empty temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = {"workspacePaths": [tmpdir], "artifactDirectoryPath": tmpdir}
            inject_payload, result = process_preinvocation(payload)
            self.assertTrue(result.success)
            self.assertEqual(result.active_tasks, 0)


if __name__ == "__main__":
    unittest.main()
