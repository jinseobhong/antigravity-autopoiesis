"""
Mechanical interface protocol definitions for resilient retry engine.

Conforms to docs/active/ACTIVE_CONTRACT.md (TASK-029).
Defines BackoffConfig, RetryAttempt, RetryOutcome frozen dataclasses and
RetryPolicyProtocol conforming to AST Anti-Cheat invariant H-CODE-1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, Tuple, Type


@dataclass(frozen=True)
class BackoffConfig:
    """Immutable configuration parameters for exponential backoff retry execution."""

    initial_interval_sec: float = 0.1
    max_interval_sec: float = 30.0
    multiplier: float = 2.0
    max_retries: int = 5
    jitter_mode: str = "full"
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)


@dataclass(frozen=True, init=False)
class RetryAttempt:
    """Immutable telemetry record representing a discrete retry execution attempt."""

    attempt_number: int
    delay_sec: float = 0.0
    exception_type: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: float = 0.0

    def __init__(
        self,
        attempt_number: int,
        delay_sec: float = 0.0,
        exception_type: Optional[str] = None,
        error_message: Optional[str] = None,
        timestamp: float = 0.0,
        **kwargs: Any,
    ) -> None:
        """Initialize frozen RetryAttempt supporting alias keywords."""
        dly = kwargs.get("delay_seconds", delay_sec)
        exc = kwargs.get("error_type", exception_type)
        ts = kwargs.get("elapsed_seconds", timestamp)
        msg = kwargs.get("error_message", error_message)
        object.__setattr__(self, "attempt_number", int(attempt_number))
        object.__setattr__(self, "delay_sec", float(dly))
        object.__setattr__(self, "exception_type", str(exc) if exc is not None else None)
        object.__setattr__(self, "error_message", str(msg) if msg is not None else None)
        object.__setattr__(self, "timestamp", float(ts))

    @property
    def delay_seconds(self) -> float:
        """Backward-compatible alias for delay_sec."""
        return self.delay_sec

    @property
    def error_type(self) -> Optional[str]:
        """Backward-compatible alias for exception_type."""
        return self.exception_type

    @property
    def elapsed_seconds(self) -> float:
        """Backward-compatible alias for timestamp."""
        return self.timestamp


@dataclass(frozen=True, init=False)
class RetryOutcome:
    """Immutable aggregated outcome of resilient retry policy execution."""

    success: bool
    result: Any = None
    attempts: Tuple[RetryAttempt, ...] = ()
    total_delay_sec: float = 0.0
    final_exception: Optional[str] = None
    attempt_count: int = 0

    def __init__(
        self,
        success: bool,
        result: Any = None,
        attempts: Tuple[RetryAttempt, ...] = (),
        total_delay_sec: float = 0.0,
        final_exception: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize frozen RetryOutcome supporting alias keywords."""
        res = kwargs.get("final_result", result)
        dly = kwargs.get("total_delay_sec", total_delay_sec)
        exc = kwargs.get("last_error", final_exception)
        cnt = kwargs.get("attempt_count", kwargs.get("total_attempts", 0))
        att = kwargs.get("attempts", attempts)
        object.__setattr__(self, "success", bool(success))
        object.__setattr__(self, "result", res)
        object.__setattr__(self, "attempts", tuple(att))
        object.__setattr__(self, "total_delay_sec", float(dly))
        object.__setattr__(self, "final_exception", str(exc) if exc is not None else None)
        object.__setattr__(self, "attempt_count", int(cnt))

    @property
    def final_result(self) -> Any:
        """Backward-compatible alias for result."""
        return self.result

    @property
    def total_attempts(self) -> int:
        """Backward-compatible alias for attempt_count."""
        return self.attempt_count

    @property
    def last_error(self) -> Optional[str]:
        """Backward-compatible alias for final_exception."""
        return self.final_exception


class RetryPolicyProtocol(Protocol):
    """Mechanical interface protocol defining resilient retry behaviors."""

    def compute_delay(self, attempt: int, base_delay: float) -> float:
        """Compute bounded backoff delay duration for the specified attempt count."""
        raise NotImplementedError("Protocol method must be implemented by concrete engine.")

    def execute_with_retry(
        self,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> RetryOutcome:
        """Execute callable operation with configured exponential backoff and jitter."""
        raise NotImplementedError("Protocol method must be implemented by concrete engine.")
