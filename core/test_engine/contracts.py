"""
Value objects, data transfer schemas, and protocols for Test Execution Engine.

Conforms to ISO/IEC 5055 standards and AST Anti-Cheat rules.
"""

from dataclasses import asdict, dataclass, field
import json
import time
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class WarmTestRequest:
    """Immutable request payload for executing a test inside an out-of-process worker."""

    request_id: str
    test_module: str
    test_case: Optional[str] = None
    timeout_seconds: float = 3.0
    env_overrides: Dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serializes request to JSON line string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "WarmTestRequest":
        """Deserializes JSON line string to WarmTestRequest."""
        data = json.loads(raw)
        return cls(
            request_id=data["request_id"],
            test_module=data["test_module"],
            test_case=data.get("test_case"),
            timeout_seconds=float(data.get("timeout_seconds", 3.0)),
            env_overrides=dict(data.get("env_overrides", {})),
        )


@dataclass(frozen=True)
class WarmTestResult:
    """Immutable test execution result returned by an out-of-process worker."""

    request_id: str
    status: str  # "PASS", "FAIL", "ERROR", "TIMEOUT"
    duration_seconds: float
    tests_run: int
    failures: List[str]
    errors: List[str]
    stdout: str
    stderr: str
    worker_pid: int

    def to_json(self) -> str:
        """Serializes result to JSON line string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "WarmTestResult":
        """Deserializes JSON line string to WarmTestResult."""
        data = json.loads(raw)
        return cls(
            request_id=data["request_id"],
            status=data["status"],
            duration_seconds=float(data["duration_seconds"]),
            tests_run=int(data["tests_run"]),
            failures=list(data.get("failures", [])),
            errors=list(data.get("errors", [])),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            worker_pid=int(data.get("worker_pid", 0)),
        )


@dataclass(frozen=True)
class WorkerStatus:
    """Snapshot of a worker process's health and operational statistics."""

    worker_id: str
    pid: int
    is_alive: bool
    current_request_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    completed_tasks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Converts status to standard dictionary."""
        return asdict(self)


class WarmRunnerProtocol(Protocol):
    """Structural typing interface for test runner managers."""

    def submit_test(self, request: WarmTestRequest) -> WarmTestResult:
        """Submits a test request to the worker pool with bounded watchdog timeout."""
        raise NotImplementedError("Protocol method must be implemented by concrete class")

    def stop_workers(self, force: bool = False) -> int:
        """Stops all active worker processes."""
        raise NotImplementedError("Protocol method must be implemented by concrete class")

    def get_status(self) -> List[WorkerStatus]:
        """Returns the health status of all workers in the pool."""
        raise NotImplementedError("Protocol method must be implemented by concrete class")

    def diagnose_hangs(self) -> List[WorkerStatus]:
        """Identifies and reports any hanging worker processes."""
        raise NotImplementedError("Protocol method must be implemented by concrete class")
