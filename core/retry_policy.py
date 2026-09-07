"""
Resilient Exponential Backoff Retry Policy Engine (core.retry_policy).

Provides exponential backoff delay computation with full and decorrelated jitter,
bounded interval clamping, selective exception filtering, and attempt telemetry.
Conforms to docs/active/ACTIVE_CONTRACT.md (TASK-029).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys
import time
from typing import Any, Callable, List, Optional, Sequence, Tuple

from core.interfaces.retry_policy_proto import (
    BackoffConfig,
    RetryAttempt,
    RetryOutcome,
    RetryPolicyProtocol,
)


class RetryPolicy(RetryPolicyProtocol):
    """Resilient exponential backoff retry engine implementing RetryPolicyProtocol."""

    def __init__(self, config: Optional[BackoffConfig] = None) -> None:
        """Initialize retry policy with given configuration or defaults."""
        cfg = config if config is not None else BackoffConfig()
        if cfg.initial_interval_sec < 0.0:
            raise ValueError(
                f"initial_interval_sec must be non-negative, got {cfg.initial_interval_sec}"
            )
        if cfg.max_interval_sec < cfg.initial_interval_sec:
            raise ValueError(
                f"max_interval_sec ({cfg.max_interval_sec}) cannot be less than "
                f"initial_interval_sec ({cfg.initial_interval_sec})"
            )
        if cfg.max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got {cfg.max_retries}")
        if cfg.multiplier <= 0.0:
            raise ValueError(f"multiplier must be positive, got {cfg.multiplier}")
        if cfg.jitter_mode not in ("full", "decorrelated", "none"):
            raise ValueError(f"Unsupported jitter mode: {cfg.jitter_mode}")
        self.config = cfg

    def compute_delay(self, attempt: int, base_delay: float) -> float:
        """
        Compute bounded backoff delay applying full, decorrelated, or no jitter.

        Clamps result to [0.0, config.max_interval_sec].
        """
        if attempt < 0:
            raise ValueError(f"attempt count must be non-negative, got {attempt}")
        if base_delay < 0.0:
            raise ValueError(f"base delay duration cannot be negative, got {base_delay}")

        cfg = self.config
        try:
            exp_factor = cfg.multiplier ** attempt
            raw_delay = base_delay * exp_factor
            exponential_base = min(cfg.max_interval_sec, raw_delay)
        except OverflowError:
            exponential_base = cfg.max_interval_sec

        mode = cfg.jitter_mode.lower()
        if mode == "full":
            delay = random.uniform(0.0, exponential_base)
        elif mode == "decorrelated":
            low = min(cfg.initial_interval_sec, base_delay * 3.0)
            high = max(cfg.initial_interval_sec, base_delay * 3.0)
            delay = min(cfg.max_interval_sec, random.uniform(low, high))
        elif mode == "none":
            delay = exponential_base
        else:
            delay = random.uniform(0.0, exponential_base)

        return max(0.0, min(cfg.max_interval_sec, delay))

    def _record_terminal_attempt(
        self,
        attempt: int,
        current_base: float,
        exc: Exception,
        attempts: List[RetryAttempt],
    ) -> RetryOutcome:
        """Records final exhausted attempt and constructs failed RetryOutcome."""
        delay = self.compute_delay(attempt, current_base)
        rec = RetryAttempt(
            attempt_number=attempt + 1,
            delay_sec=delay,
            exception_type=type(exc).__name__,
            error_message=str(exc),
            timestamp=time.time(),
        )
        attempts.append(rec)
        return RetryOutcome(
            success=False,
            result=None,
            attempts=tuple(attempts),
            total_delay_sec=sum(a.delay_sec for a in attempts),
            final_exception=str(exc),
            attempt_count=attempt + 1,
        )

    def execute_with_retry(
        self,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> RetryOutcome:
        """Execute callable target with selective exception catching and telemetry."""
        if not callable(operation):
            raise TypeError(f"Operation must be callable, got: {type(operation).__name__}")

        cfg = self.config
        ret_exc = cfg.retryable_exceptions
        max_retries = cfg.max_retries
        attempts: List[RetryAttempt] = []
        current_base = cfg.initial_interval_sec

        for attempt in range(max(1, max_retries)):
            t0 = time.time()
            try:
                result = operation(*args, **kwargs)
                return RetryOutcome(
                    success=True,
                    result=result,
                    attempts=tuple(attempts),
                    total_delay_sec=sum(a.delay_sec for a in attempts),
                    final_exception=None,
                    attempt_count=attempt + 1,
                )
            except Exception as exc:
                elapsed = time.time() - t0
                is_retryable = isinstance(exc, ret_exc)
                if not is_retryable:
                    return RetryOutcome(
                        success=False,
                        result=None,
                        attempts=(),
                        total_delay_sec=0.0,
                        final_exception=str(exc),
                        attempt_count=1,
                    )

                if attempt == max_retries - 1 or max_retries == 0:
                    return self._record_terminal_attempt(attempt, current_base, exc, attempts)

                delay = self.compute_delay(attempt, current_base)
                rec = RetryAttempt(
                    attempt_number=attempt + 1,
                    delay_sec=delay,
                    exception_type=type(exc).__name__,
                    error_message=str(exc),
                    timestamp=time.time(),
                )
                attempts.append(rec)
                current_base = delay
                if delay > 0.0:
                    time.sleep(delay)

        return RetryOutcome(
            success=False,
            result=None,
            attempts=tuple(attempts),
            total_delay_sec=sum(a.delay_sec for a in attempts),
            final_exception="Max retries exhausted",
            attempt_count=max_retries,
        )


RetryEngine = RetryPolicy


def build_parser() -> argparse.ArgumentParser:
    """Constructs CLI argument parser for retry policy execution and simulation."""
    parser = argparse.ArgumentParser(
        description="Resilient Exponential Backoff Retry Policy Engine (TASK-029)."
    )
    parser.add_argument(
        "--initial-sec",
        type=float,
        default=0.05,
        help="Initial backoff interval in seconds (default: 0.05).",
    )
    parser.add_argument(
        "--max-sec",
        type=float,
        default=2.0,
        help="Maximum bounded delay interval in seconds (default: 2.0).",
    )
    parser.add_argument(
        "--multiplier",
        type=float,
        default=2.0,
        help="Exponential backoff multiplier factor (default: 2.0).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="Maximum allowed retry attempts (default: 5).",
    )
    parser.add_argument(
        "--jitter",
        type=str,
        choices=["full", "decorrelated", "none"],
        default="full",
        help="Jitter algorithm mode (default: full).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Serialize simulation output to JSON format.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint simulating exponential backoff retry execution."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.retries < 0 or args.initial_sec < 0.0 or args.max_sec < args.initial_sec:
        sys.stderr.write("Error: Invalid retry parameter boundaries\n")
        return 2

    config = BackoffConfig(
        initial_interval_sec=args.initial_sec,
        max_interval_sec=args.max_sec,
        multiplier=args.multiplier,
        max_retries=args.retries,
        jitter_mode=args.jitter,
    )
    engine = RetryPolicy(config=config)

    transient_failures = min(2, max(0, config.max_retries - 1))
    attempts_seen = 0

    def simulated_task() -> str:
        nonlocal attempts_seen
        attempts_seen += 1
        if attempts_seen <= transient_failures:
            raise ConnectionResetError(f"Transient I/O failure on attempt {attempts_seen}")
        return "simulation_success"

    outcome = engine.execute_with_retry(simulated_task)

    if args.json:
        payload = {
            "success": outcome.success,
            "total_attempts": outcome.attempt_count,
            "total_delay_sec": round(outcome.total_delay_sec, 6),
            "result": str(outcome.result) if outcome.result else None,
            "final_exception": outcome.final_exception,
            "attempts": [
                {
                    "attempt_number": a.attempt_number,
                    "delay_sec": round(a.delay_sec, 6),
                    "exception_type": a.exception_type,
                    "error_message": a.error_message,
                    "timestamp": round(a.timestamp, 6),
                }
                for a in outcome.attempts
            ],
            "config": {
                "initial_interval_sec": config.initial_interval_sec,
                "max_interval_sec": config.max_interval_sec,
                "multiplier": config.multiplier,
                "max_retries": config.max_retries,
                "jitter_mode": config.jitter_mode,
            },
        }
        print(json.dumps(payload, indent=2))
    else:
        print("[RETRY SIMULATION SUCCESS]")
        print(f"  Success: {outcome.success}")
        print(f"  Total Attempts: {outcome.attempt_count}")
        print(f"  Total Delay: {outcome.total_delay_sec:.4f}s")
        print(f"  Result: {outcome.result}")
        print(f"  Attempts Recorded: {len(outcome.attempts)}")
        for att in outcome.attempts:
            print(
                f"    - Attempt #{att.attempt_number}: delay={att.delay_sec:.4f}s, "
                f"error={att.exception_type}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
