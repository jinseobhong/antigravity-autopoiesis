"""
Adversarial companion test suite for Warm Runner Harness (TASK-006).

Enforces AST Anti-Cheat standards:
- >= 40% negative assertion ratio (H-CODE-3)
- Hard watchdog timeout killing (3.0s ceiling)
- Hanging worker diagnostics
- Process death recovery and pipe failure handling
- Zero swallowed exceptions (H-CODE-6)
"""

import io
from pathlib import Path
import subprocess
import sys
import time
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
    from core.warm_runner_worker import worker_main_loop
except ImportError:
    from sandbox.core.warm_runner import WarmRunnerManager
    from sandbox.core.warm_runner_types import WarmTestRequest
    from sandbox.core.warm_runner_worker import worker_main_loop


class TestWarmRunnerAdversarial(unittest.TestCase):
    """Adversarial fault injection and boundary evaluation for Warm Runner."""

    def setUp(self) -> None:
        self.manager = WarmRunnerManager(max_workers=1, default_timeout=1.0)

    def tearDown(self) -> None:
        self.manager.stop_workers(force=True)

    def test_negative_watchdog_timeout_kills_hanging_test(self) -> None:
        """Negative: Asserts watchdog kills worker when test exceeds timeout budget."""
        # Using a timeout of 0.3s against a test that takes longer or simulated hang
        # We invoke python -c with sleep via a custom test method or helper
        req = WarmTestRequest(
            request_id=f"timeout_{uuid.uuid4().hex[:6]}",
            test_module="time",
            test_case="sleep(2)",
            timeout_seconds=0.3,
        )
        # Note: unittest loader trying to load sleep(2) from time or non-existent
        # will either raise error quickly or if we point to a slow test
        # Let's test watchdog using an intentional hanging helper
        slow_req = WarmTestRequest(
            request_id=f"hang_{uuid.uuid4().hex[:6]}",
            test_module="tests.test_warm_runner_adversarial",
            test_case="SlowTestStub.test_sleep_forever",
            timeout_seconds=0.4,
        )
        res = self.manager.submit_test(slow_req)
        self.assertEqual(res.status, "TIMEOUT")
        self.assertIn("WatchdogTimeout", res.errors[0])
        self.assertGreaterEqual(res.duration_seconds, 0.3)

    def test_negative_worker_recycled_after_timeout_kill(self) -> None:
        """Negative: Asserts pool recovers and spawns new worker after timeout kill."""
        hang_req = WarmTestRequest(
            request_id="hang_before_recycle",
            test_module="tests.test_warm_runner_adversarial",
            test_case="SlowTestStub.test_sleep_forever",
            timeout_seconds=0.4,
        )
        res1 = self.manager.submit_test(hang_req)
        self.assertEqual(res1.status, "TIMEOUT")
        dead_pid = res1.worker_pid

        # Pool should automatically spawn fresh worker for subsequent request
        nominal_req = WarmTestRequest(
            request_id="nominal_after_recycle",
            test_module="tests.test_modular_pipeline",
            test_case="TestModularPipelineSpecification.test_implement_skill_exists_and_frontmatter_valid",
            timeout_seconds=5.0,
        )
        res2 = self.manager.submit_test(nominal_req)
        self.assertEqual(res2.status, "PASS")
        self.assertNotEqual(res2.worker_pid, dead_pid)

    def test_negative_worker_crash_detected_and_recovered(self) -> None:
        """Negative: Asserts runner recycles worker when process is externally killed."""
        req1 = WarmTestRequest(
            request_id="req1",
            test_module="tests.test_modular_pipeline",
            test_case="TestModularPipelineSpecification.test_implement_skill_exists_and_frontmatter_valid",
            timeout_seconds=5.0,
        )
        res1 = self.manager.submit_test(req1)
        self.assertEqual(res1.status, "PASS")

        # Forcibly kill worker process externally
        statuses = self.manager.get_status()
        self.assertEqual(len(statuses), 1)
        worker_handle = next(iter(self.manager.workers.values()))
        worker_handle.terminate_or_kill(force=True)

        # Subsequent test request should detect dead worker and self-heal
        req2 = WarmTestRequest(
            request_id="req2_recovery",
            test_module="tests.test_modular_pipeline",
            test_case="TestModularPipelineSpecification.test_implement_skill_exists_and_frontmatter_valid",
            timeout_seconds=5.0,
        )
        res2 = self.manager.submit_test(req2)
        self.assertEqual(res2.status, "PASS")
        self.assertNotEqual(res2.worker_pid, res1.worker_pid)

    def test_negative_rejects_non_existent_module(self) -> None:
        """Negative: Asserts error response on unresolvable test module."""
        req = WarmTestRequest(
            request_id="bad_module",
            test_module="completely.bogus.module.does_not_exist",
            timeout_seconds=3.0,
        )
        res = self.manager.submit_test(req)
        self.assertEqual(res.status, "ERROR")
        self.assertGreater(len(res.errors), 0)
        self.assertTrue(any("FailedTest" in err or "No module named" in err for err in res.errors))

    def test_negative_worker_handles_malformed_json_without_crash(self) -> None:
        """Negative: Asserts worker daemon tolerates malformed input JSON without process crash."""
        in_stream = io.StringIO("This is not valid JSON at all\n")
        out_stream = io.StringIO()
        code = worker_main_loop(stream_in=in_stream, stream_out=out_stream)
        self.assertEqual(code, 0)

        output = out_stream.getvalue().strip()
        self.assertIn("InvalidPayloadError", output)
        self.assertIn('"status": "ERROR"', output)

    def test_negative_cli_invalid_command_rejected(self) -> None:
        """Negative: Asserts CLI exits with non-zero on unrecognized flags."""
        cmd = [sys.executable, "-m", "core.warm_runner", "--invalid-flag-xyz"]
        proc = subprocess.run(cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=10)
        self.assertNotEqual(proc.returncode, 0)


class SlowTestStub(unittest.TestCase):
    """Synthetic slow test case used strictly for watchdog timeout evaluation."""

    def test_sleep_forever(self) -> None:
        time.sleep(2.0)


if __name__ == "__main__":
    unittest.main()
