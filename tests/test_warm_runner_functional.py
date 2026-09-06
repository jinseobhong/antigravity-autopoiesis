"""
Functional companion test suite for Warm Runner Harness (TASK-006).

Validates happy-path contracts, valid execution states, and deterministic CLI commands.
Conforms to ISO/IEC 5055 and AST Anti-Cheat standards.
"""

from pathlib import Path
import subprocess
import sys
import unittest
import uuid

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SANDBOX_ROOT = _REPO_ROOT / "sandbox"
if _SANDBOX_ROOT.exists() and str(_SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(_SANDBOX_ROOT))

try:
    from core.warm_runner import WarmRunnerManager
    from core.warm_runner_types import WarmTestRequest
except ImportError:
    from sandbox.core.warm_runner import WarmRunnerManager
    from sandbox.core.warm_runner_types import WarmTestRequest


class TestWarmRunnerFunctional(unittest.TestCase):
    """Functional test cases evaluating nominal Warm Runner operations."""

    def setUp(self) -> None:
        self.manager = WarmRunnerManager(max_workers=1, default_timeout=5.0)

    def tearDown(self) -> None:
        self.manager.stop_workers(force=True)

    def test_submit_passing_test_case(self) -> None:
        """Functional: Verifies execution of a known passing test method."""
        req = WarmTestRequest(
            request_id=f"req_{uuid.uuid4().hex[:6]}",
            test_module="tests.test_modular_pipeline",
            test_case="TestModularPipelineSpecification.test_implement_skill_exists_and_frontmatter_valid",
            timeout_seconds=5.0,
        )
        result = self.manager.submit_test(req)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.tests_run, 1)
        self.assertEqual(len(result.failures), 0)
        self.assertEqual(len(result.errors), 0)
        self.assertGreater(result.worker_pid, 0)

    def test_worker_status_reporting(self) -> None:
        """Functional: Verifies that worker status accurately reflects active worker state."""
        # Execute one request to ensure worker is spawned
        req = WarmTestRequest(
            request_id=f"req_{uuid.uuid4().hex[:6]}",
            test_module="tests.test_modular_pipeline",
            test_case="TestModularPipelineSpecification.test_implement_skill_exists_and_frontmatter_valid",
            timeout_seconds=5.0,
        )
        self.manager.submit_test(req)

        statuses = self.manager.get_status()
        self.assertEqual(len(statuses), 1)
        worker = statuses[0]
        self.assertTrue(worker.is_alive)
        self.assertGreaterEqual(worker.completed_tasks, 1)
        self.assertIsNone(worker.current_request_id)

    def test_diagnose_hangs_when_nominal(self) -> None:
        """Functional: Asserts zero hanging workers when worker pool is nominal."""
        hangs = self.manager.diagnose_hangs()
        self.assertEqual(len(hangs), 0)

    def test_stop_workers_terminates_pool(self) -> None:
        """Functional: Asserts stop_workers stops workers and clears pool."""
        req = WarmTestRequest(
            request_id=f"req_{uuid.uuid4().hex[:6]}",
            test_module="tests.test_modular_pipeline",
            test_case="TestModularPipelineSpecification.test_implement_skill_exists_and_frontmatter_valid",
            timeout_seconds=5.0,
        )
        self.manager.submit_test(req)
        self.assertEqual(len(self.manager.get_status()), 1)

        stopped = self.manager.stop_workers(force=False)
        self.assertEqual(stopped, 1)
        self.assertEqual(len(self.manager.get_status()), 0)

    def test_cli_diagnose_hangs_subprocess(self) -> None:
        """Functional: Verifies CLI --diagnose-hangs command invocation."""
        runner_module = "core.warm_runner"
        cmd = [sys.executable, "-m", runner_module, "--diagnose-hangs"]
        proc = subprocess.run(cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Zero hanging workers detected", proc.stdout)

    def test_direct_test_engine_package_import(self) -> None:
        """Functional: Verifies core.test_engine can be imported and utilized directly."""
        from core.test_engine import (
            WarmRunnerManager as TestEngineManager,
            WarmTestRequest as DirectRequest,
            WarmTestResult as DirectResult,
            WorkerStatus as DirectStatus,
        )

        direct_mgr = TestEngineManager(max_workers=1, default_timeout=5.0)
        try:
            req = DirectRequest(
                request_id=f"direct_{uuid.uuid4().hex[:6]}",
                test_module="tests.test_modular_pipeline",
                test_case="TestModularPipelineSpecification.test_implement_skill_exists_and_frontmatter_valid",
                timeout_seconds=5.0,
            )
            result = direct_mgr.submit_test(req)
            self.assertIsInstance(result, DirectResult)
            self.assertEqual(result.status, "PASS")
            self.assertGreaterEqual(len(direct_mgr.get_status()), 1)
            self.assertIsInstance(direct_mgr.get_status()[0], DirectStatus)
        finally:
            direct_mgr.stop_workers(force=True)


if __name__ == "__main__":
    unittest.main()

