"""
Core Test Execution Engine Package (core.test_engine).

Provides process-isolated test runner daemons, watchdog supervision,
and structured test execution results.
"""

from .contracts import (
    WarmRunnerProtocol,
    WarmTestRequest,
    WarmTestResult,
    WorkerStatus,
)
from .engine import WarmRunnerManager
from .worker import worker_main_loop

__all__ = [
    "WarmRunnerProtocol",
    "WarmTestRequest",
    "WarmTestResult",
    "WorkerStatus",
    "WarmRunnerManager",
    "worker_main_loop",
]
