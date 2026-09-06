"""
Test Engine Out-of-Process Worker Daemon (worker.py).

Executes unittest targets in an isolated sub-process with stdout/stderr capture,
teardown isolation, and JSON line IPC.
"""

import io
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Dict, List, Optional, Tuple
import unittest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SANDBOX_ROOT = _REPO_ROOT / "sandbox"
if _SANDBOX_ROOT.exists() and str(_SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(_SANDBOX_ROOT))

try:
    from core.test_engine.contracts import WarmTestRequest, WarmTestResult
except ImportError:
    from sandbox.core.test_engine.contracts import WarmTestRequest, WarmTestResult


def _apply_env_overrides(overrides: Dict[str, str]) -> Dict[str, Optional[str]]:
    """Applies environment overrides and captures previous values."""
    original_env: Dict[str, Optional[str]] = {}
    for key, value in overrides.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    return original_env


def _restore_env_overrides(original_env: Dict[str, Optional[str]]) -> None:
    """Restores previous environment values."""
    for key, orig_val in original_env.items():
        if orig_val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_val


def _execute_test_suite(target: str, captured_out: io.StringIO) -> Tuple[str, int, List[str], List[str]]:
    """Loads and executes the target test suite, capturing failures and errors."""
    suite = unittest.defaultTestLoader.loadTestsFromName(target)
    runner = unittest.TextTestRunner(stream=captured_out, verbosity=1)
    res = runner.run(suite)
    status = "PASS"
    failures = []
    errors = []
    if res.failures:
        status = "FAIL"
        failures = [f"{test.id()}: {err}" for test, err in res.failures]
    if res.errors:
        status = "ERROR"
        errors = [f"{test.id()}: {err}" for test, err in res.errors]
    return status, res.testsRun, failures, errors


def execute_single_request(request: WarmTestRequest, worker_pid: int) -> WarmTestResult:
    """Executes a single test request in isolation and captures execution results."""
    target = request.test_module
    if request.test_case:
        target = f"{request.test_module}.{request.test_case}"

    original_env = _apply_env_overrides(request.env_overrides)
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    start_time = time.perf_counter()
    status = "PASS"
    tests_run = 0
    failures: List[str] = []
    errors: List[str] = []

    try:
        sys.stdout = captured_out
        sys.stderr = captured_err
        status, tests_run, failures, errors = _execute_test_suite(target, captured_out)
        duration = time.perf_counter() - start_time
    except Exception as exc:
        duration = time.perf_counter() - start_time
        status = "ERROR"
        errors = [f"RunnerException: {exc}\n{traceback.format_exc()}"]
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        _restore_env_overrides(original_env)

    return WarmTestResult(
        request_id=request.request_id,
        status=status,
        duration_seconds=round(duration, 4),
        tests_run=tests_run,
        failures=failures,
        errors=errors,
        stdout=captured_out.getvalue(),
        stderr=captured_err.getvalue(),
        worker_pid=worker_pid,
    )


def worker_main_loop(stream_in=None, stream_out=None) -> int:
    """Main event loop processing JSON line requests from stdin and writing to stdout."""
    in_stream = stream_in or sys.stdin
    out_stream = stream_out or sys.stdout
    worker_pid = os.getpid()

    while True:
        line = in_stream.readline()
        if not line:
            break
        line_str = line.strip()
        if not line_str:
            continue

        try:
            req = WarmTestRequest.from_json(line_str)
            res = execute_single_request(req, worker_pid)
        except Exception as err:
            res = WarmTestResult(
                request_id="unknown_error",
                status="ERROR",
                duration_seconds=0.0,
                tests_run=0,
                failures=[],
                errors=[f"InvalidPayloadError: {err}"],
                stdout="",
                stderr=traceback.format_exc(),
                worker_pid=worker_pid,
            )

        out_stream.write(res.to_json() + "\n")
        out_stream.flush()

    return 0


if __name__ == "__main__":
    sys.exit(worker_main_loop())
