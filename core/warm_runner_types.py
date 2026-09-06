"""
Value objects, data transfer schemas, and protocols for Warm Runner Harness.

Backward-compatibility facade delegating to core.test_engine.contracts.
Conforms to ISO/IEC 5055 standards and AST Anti-Cheat rules.
"""

from .test_engine.contracts import (
    WarmRunnerProtocol,
    WarmTestRequest,
    WarmTestResult,
    WorkerStatus,
)

__all__ = [
    "WarmRunnerProtocol",
    "WarmTestRequest",
    "WarmTestResult",
    "WorkerStatus",
]
