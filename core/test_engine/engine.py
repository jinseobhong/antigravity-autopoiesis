"""
Out-of-Process Test Engine and Supervisor Manager (engine.py).

Implements sub-process sandboxing, hard watchdog timeout enforcement (3.0s),
worker recycling, hanging worker diagnostics, and supervisor lifecycle.
"""

import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple
import uuid

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SANDBOX_ROOT = _REPO_ROOT / "sandbox"
if _SANDBOX_ROOT.exists() and str(_SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(_SANDBOX_ROOT))

try:
    from core.test_engine.contracts import (
        WarmRunnerProtocol,
        WarmTestRequest,
        WarmTestResult,
        WorkerStatus,
    )
except ImportError:
    from sandbox.core.test_engine.contracts import (
        WarmRunnerProtocol,
        WarmTestRequest,
        WarmTestResult,
        WorkerStatus,
    )


class WorkerHandle:
    """Manages an active out-of-process worker subprocess and its I/O threads."""

    def __init__(self, worker_id: str, proc: subprocess.Popen) -> None:
        self.worker_id = worker_id
        self.proc = proc
        self.pid = proc.pid
        self.started_at = time.time()
        self.completed_tasks = 0
        self.current_request_id: Optional[str] = None
        self._output_queue: queue.Queue = queue.Queue()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        """Continuously reads lines from worker stdout and pushes to queue."""
        while True:
            line = self.proc.stdout.readline()
            if not line:
                break
            self._output_queue.put(line)

    def is_alive(self) -> bool:
        """Returns True if the worker process is currently running."""
        return self.proc.poll() is None

    def send_request(self, request: WarmTestRequest) -> None:
        """Sends a JSON line test request to the worker stdin."""
        self.current_request_id = request.request_id
        payload = request.to_json() + "\n"
        self.proc.stdin.write(payload)
        self.proc.stdin.flush()

    def read_result(self, timeout: float) -> str:
        """Reads a result line from queue with timeout."""
        return self._output_queue.get(timeout=timeout)

    def terminate_or_kill(self, force: bool = False) -> None:
        """Terminates or kills the worker process and safely closes pipes."""
        if not self.is_alive():
            self._close_pipes()
            return
        if force:
            self.proc.kill()
        else:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._close_pipes()

    def _close_pipes(self) -> None:
        """Closes standard I/O pipes deterministically without resource leaks."""
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if stream and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    continue


class WarmRunnerManager(WarmRunnerProtocol):
    """Manages the worker pool, submits test requests, and enforces watchdogs."""

    def __init__(self, max_workers: int = 1, default_timeout: float = 3.0) -> None:
        self.max_workers = max(1, max_workers)
        self.default_timeout = default_timeout
        self.workers: Dict[str, WorkerHandle] = {}
        self._lock = threading.Lock()

    def _resolve_worker_script(self) -> Path:
        """Resolves the canonical worker script path with fallback."""
        candidates = [
            _REPO_ROOT / "core" / "test_engine" / "worker.py",
            _SANDBOX_ROOT / "core" / "test_engine" / "worker.py",
            _REPO_ROOT / "core" / "warm_runner_worker.py",
            _SANDBOX_ROOT / "core" / "warm_runner_worker.py",
        ]
        for p in candidates:
            if p.exists():
                return p
        return candidates[0]

    def _spawn_worker(self) -> WorkerHandle:
        """Spawns a new out-of-process warm worker process."""
        worker_id = f"worker_{uuid.uuid4().hex[:8]}"
        script_path = self._resolve_worker_script()

        cmd = [sys.executable, "-u", str(script_path)]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(_REPO_ROOT),
        )
        return WorkerHandle(worker_id, proc)

    def _get_or_create_worker(self) -> WorkerHandle:
        """Retrieves an alive worker or spawns a replacement."""
        with self._lock:
            for wid, handle in list(self.workers.items()):
                if not handle.is_alive():
                    del self.workers[wid]

            if self.workers:
                return next(iter(self.workers.values()))

            handle = self._spawn_worker()
            self.workers[handle.worker_id] = handle
            return handle

    def submit_test(self, request: WarmTestRequest) -> WarmTestResult:
        """Executes a test request with hard watchdog timeout enforcement."""
        handle = self._get_or_create_worker()
        watchdog_limit = request.timeout_seconds or self.default_timeout

        try:
            handle.send_request(request)
            raw_result = handle.read_result(timeout=watchdog_limit)
            result = WarmTestResult.from_json(raw_result)
            handle.completed_tasks += 1
            handle.current_request_id = None
            return result
        except queue.Empty:
            handle.terminate_or_kill(force=True)
            with self._lock:
                self.workers.pop(handle.worker_id, None)
            return WarmTestResult(
                request_id=request.request_id,
                status="TIMEOUT",
                duration_seconds=round(watchdog_limit, 4),
                tests_run=0,
                failures=[],
                errors=[f"WatchdogTimeout: Execution exceeded {watchdog_limit}s threshold. Worker killed."],
                stdout="",
                stderr="Watchdog watchdog timer fired; process forcibly terminated.",
                worker_pid=handle.pid,
            )
        except Exception as exc:
            handle.terminate_or_kill(force=True)
            with self._lock:
                self.workers.pop(handle.worker_id, None)
            return WarmTestResult(
                request_id=request.request_id,
                status="ERROR",
                duration_seconds=0.0,
                tests_run=0,
                failures=[],
                errors=[f"CommunicationError: {exc}"],
                stdout="",
                stderr="",
                worker_pid=handle.pid,
            )

    def stop_workers(self, force: bool = False) -> int:
        """Stops all active worker processes."""
        with self._lock:
            stopped_count = 0
            for handle in list(self.workers.values()):
                handle.terminate_or_kill(force=force)
                stopped_count += 1
            self.workers.clear()
            return stopped_count

    def get_status(self) -> List[WorkerStatus]:
        """Returns the health status of all workers in the pool."""
        with self._lock:
            statuses = []
            for handle in self.workers.values():
                statuses.append(
                    WorkerStatus(
                        worker_id=handle.worker_id,
                        pid=handle.pid,
                        is_alive=handle.is_alive(),
                        current_request_id=handle.current_request_id,
                        started_at=handle.started_at,
                        completed_tasks=handle.completed_tasks,
                    )
                )
            return statuses

    def diagnose_hangs(self) -> List[WorkerStatus]:
        """Identifies and reports any hanging worker processes."""
        with self._lock:
            hanging = []
            now = time.time()
            for handle in self.workers.values():
                if handle.current_request_id and (now - handle.started_at > self.default_timeout):
                    hanging.append(
                        WorkerStatus(
                            worker_id=handle.worker_id,
                            pid=handle.pid,
                            is_alive=handle.is_alive(),
                            current_request_id=handle.current_request_id,
                            started_at=handle.started_at,
                            completed_tasks=handle.completed_tasks,
                        )
                    )
            return hanging
