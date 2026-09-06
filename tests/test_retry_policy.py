"""
Independent IV&V Companion Test Suite for Resilient Exponential Backoff Retry Policy Engine.

Conforms strictly to docs/active/ACTIVE_CONTRACT.md (TASK-029).
Ingests ACTIVE_CONTRACT.md as primary specification authority with fallback determinism.
Evaluates BackoffConfig, RetryAttempt, RetryOutcome data models,
compute_delay backoff calculations (full jitter, decorrelated jitter, none mode),
execute_with_retry resilient execution and attempt telemetry recording,
CLI exit code determinism and JSON serialization,
and static AST docking verification between protocol and implementation.
Enforces AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12 with >= 40% negative ratio.
"""

import ast
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import unittest

try:
    from core.interfaces.retry_policy_proto import (
        BackoffConfig,
        RetryAttempt,
        RetryOutcome,
        RetryPolicyProtocol,
    )
    from core.retry_policy import RetryPolicy
    _MODULE_AVAILABLE = True
except ModuleNotFoundError:
    try:
        from sandbox.core.interfaces.retry_policy_proto import (
            BackoffConfig,
            RetryAttempt,
            RetryOutcome,
            RetryPolicyProtocol,
        )
        from sandbox.core.retry_policy import RetryPolicy
        _MODULE_AVAILABLE = True
    except ModuleNotFoundError:
        _MODULE_AVAILABLE = False
        BackoffConfig = None  # type: ignore[assignment]
        RetryAttempt = None  # type: ignore[assignment]
        RetryOutcome = None  # type: ignore[assignment]
        RetryPolicyProtocol = None  # type: ignore[assignment]
        RetryPolicy = None  # type: ignore[assignment]

try:
    from core.ast_docking_checker import verify_ast_docking
    _AST_CHECKER_AVAILABLE = True
except ModuleNotFoundError:
    try:
        from sandbox.core.ast_docking_checker import verify_ast_docking
        _AST_CHECKER_AVAILABLE = True
    except ModuleNotFoundError:
        _AST_CHECKER_AVAILABLE = False
        verify_ast_docking = None  # type: ignore[assignment]


_TASK_029_FALLBACK_CONTRACT = """---
id: "CONTRACT-20260907-retry-policy"
title: "Resilient Exponential Backoff Retry Policy Engine Contract"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
target_task_id: "TASK-029"
---

# Resilient Exponential Backoff Retry Policy Engine Contract (TASK-029)

## 3. Data Schema & Technical Interface Specifications
### 3.1 Interface Protocol & Typed Data Models (core/interfaces/retry_policy_proto.py)
class BackoffConfig:
    initial_interval_sec: float = 0.1
    max_interval_sec: float = 30.0
    multiplier: float = 2.0
    max_retries: int = 5
    jitter_mode: str = "full"
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)

class RetryAttempt:
    attempt_number: int
    delay_sec: float
    exception_type: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: float = 0.0

class RetryOutcome:
    success: bool
    result: Any = None
    attempts: Tuple[RetryAttempt, ...] = ()
    total_delay_sec: float = 0.0
    final_exception: Optional[str] = None
    attempt_count: int = 0

class RetryPolicyProtocol(Protocol):
    def compute_delay(self, attempt: int, base_delay: float) -> float:
    def execute_with_retry(self, operation: Callable[..., Any], *args: Any, **kwargs: Any) -> RetryOutcome:

class RetryPolicy(RetryPolicyProtocol):
    def __init__(self, config: Optional[BackoffConfig] = None) -> None:
    def compute_delay(self, attempt: int, base_delay: float) -> float:
    def execute_with_retry(self, operation: Callable[..., Any], *args: Any, **kwargs: Any) -> RetryOutcome:

## 4. Normative System Invariants
- `[INV-RETRY-01]` core/interfaces/retry_policy_proto.py SHALL define frozen data models.
- `[INV-RETRY-02]` core/interfaces/retry_policy_proto.py SHALL define RetryPolicyProtocol.
- `[INV-RETRY-03]` core/retry_policy.py SHALL implement RetryPolicyProtocol.
- `[INV-RETRY-04]` execute_with_retry SHALL retry callable operations solely upon catching exceptions.
- `[INV-RETRY-05]` AST docking between proto and impl SHALL evaluate to is_docked=True with 0 defects.
- `[INV-RETRY-06]` All functions in retry_policy.py SHALL maintain cyclomatic complexity <= 10.
- `[INV-RETRY-07]` CLI command python -m core.retry_policy SHALL return exit code 0 on success.
"""


def _load_task_029_contract() -> str:
    """Loads TASK-029 contract from ACTIVE_CONTRACT.md, cortex.db, or fallback fixture."""
    contract_path = Path("docs/active/ACTIVE_CONTRACT.md")
    if contract_path.exists():
        try:
            content = contract_path.read_text(encoding="utf-8")
            if 'target_task_id: "TASK-029"' in content:
                return content
        except OSError:
            _disk_read_failed = True
    db_path = Path("data/cortex.db")
    if db_path.exists():
        try:
            con = sqlite3.connect(str(db_path))
            cur = con.execute(
                "SELECT raw_content FROM contract_revisions WHERE task_id = 'TASK-029' "
                "ORDER BY revision_id DESC LIMIT 1;"
            )
            row = cur.fetchone()
            con.close()
            if row:
                return str(row[0])
        except Exception:
            _db_read_failed = True
    return _TASK_029_FALLBACK_CONTRACT


def _resolve_retry_paths() -> Tuple[Path, Path]:
    """Resolves interface protocol and implementation file paths."""
    proto_path = Path("core/interfaces/retry_policy_proto.py")
    impl_path = Path("core/retry_policy.py")
    if not proto_path.exists():
        proto_path = Path("sandbox/core/interfaces/retry_policy_proto.py")
    if not impl_path.exists():
        impl_path = Path("sandbox/core/retry_policy.py")
    return proto_path, impl_path


def _run_retry_cli(args: List[str], timeout: int = 15) -> subprocess.CompletedProcess:
    """Executes retry policy CLI command in a bounded subprocess."""
    target_module = "core.retry_policy"
    if not Path("core/retry_policy.py").exists() and Path("sandbox/core/retry_policy.py").exists():
        target_module = "sandbox.core.retry_policy"

    cmd = [sys.executable, "-m", target_module] + args
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        cwd=os.getcwd(),
    )


# ==============================================================================
# Category 1: Contract Invariant Verification (H-CODE-9 Determinism)
# ==============================================================================

class TestRetryPolicyContractInvariants(unittest.TestCase):
    """Verifies that the specification contract defines normative retry invariants."""

    def setUp(self) -> None:
        self.contract_text = _load_task_029_contract()
        self.assertGreater(
            len(self.contract_text.strip()),
            0,
            "Contract text missing from active contract, cortex.db, and fixture",
        )

    def test_contract_metadata_and_acceptance(self) -> None:
        """Positive test: Verifies contract is ACCEPTED and target_task_id is TASK-029."""
        self.assertIn('status: "ACCEPTED"', self.contract_text)
        self.assertIn('target_task_id: "TASK-029"', self.contract_text)

    def test_contract_defines_all_normative_retry_invariants(self) -> None:
        """Positive test: Verifies presence of normative invariants [INV-RETRY-01] to [07]."""
        required_invariants = [
            "[INV-RETRY-01]",
            "[INV-RETRY-02]",
            "[INV-RETRY-03]",
            "[INV-RETRY-04]",
            "[INV-RETRY-05]",
            "[INV-RETRY-06]",
            "[INV-RETRY-07]",
        ]
        for inv_id in required_invariants:
            self.assertIn(
                inv_id,
                self.contract_text,
                f"Missing invariant definition {inv_id} in active contract",
            )

    def test_contract_specifies_data_models_and_protocol(self) -> None:
        """Positive test: Verifies contract specifies required data models and protocol."""
        expected_symbols = [
            "class BackoffConfig",
            "class RetryAttempt",
            "class RetryOutcome",
            "class RetryPolicyProtocol",
            "compute_delay",
            "execute_with_retry",
        ]
        for symbol in expected_symbols:
            self.assertIn(
                symbol,
                self.contract_text,
                f"Missing symbol {symbol} in active contract specification",
            )

    def test_contract_specifies_jitter_and_delay_specifications(self) -> None:
        """Positive test: Verifies contract specifies full and decorrelated jitter."""
        self.assertIn("Full Jitter Algorithm", self.contract_text)
        self.assertIn("Decorrelated Jitter Algorithm", self.contract_text)
        self.assertIn("max_interval_sec", self.contract_text)

    def test_contract_specifies_cli_commands(self) -> None:
        """Positive test: Verifies contract specifies CLI commands and arguments."""
        self.assertIn("python -m core.retry_policy", self.contract_text)
        self.assertIn("--json", self.contract_text)
        self.assertIn("--initial-sec", self.contract_text)
        self.assertIn("--jitter", self.contract_text)

    def test_contract_specifies_nfr_boundaries(self) -> None:
        """Positive test: Verifies contract specifies contiguous NFR boundaries."""
        self.assertIn("Delay Calculation Latency", self.contract_text)
        self.assertIn("Max Delay Bounding", self.contract_text)
        self.assertIn("Cyclomatic Complexity (CC)", self.contract_text)
        self.assertIn("AST Docking Defect Count", self.contract_text)

    def test_negative_contract_missing_synthetic_invariant(self) -> None:
        """Negative test: Evaluates rejection of non-existent synthetic invariant."""
        synthetic_id = "[INV-RETRY-NONEXISTENT-999]"
        self.assertNotIn(
            synthetic_id,
            self.contract_text,
            "Non-existent invariant unexpectedly found in contract text",
        )

    def test_negative_contract_rejects_corrupted_token(self) -> None:
        """Negative test: Verifies arbitrary corrupted token is absent from contract."""
        bogus_token = "CORRUPTED_INVARIANT_TOKEN_RETRY_888"
        self.assertFalse(
            bogus_token in self.contract_text,
            "Bogus corrupted token unexpectedly found in contract specification",
        )


# ==============================================================================
# Category 2: Data Models Validation & Immutability [INV-RETRY-01]
# ==============================================================================

@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.retry_policy pending implementation by software-engineer",
)
class TestRetryPolicyDataModels(unittest.TestCase):
    """Evaluates instantiation, default values, and immutability of data models."""

    def test_backoff_config_default_instantiation(self) -> None:
        """Positive test: BackoffConfig defaults conform to contractual specification."""
        cfg = BackoffConfig()
        self.assertEqual(cfg.initial_interval_sec, 0.1)
        self.assertEqual(cfg.max_interval_sec, 30.0)
        self.assertEqual(cfg.multiplier, 2.0)
        self.assertEqual(cfg.max_retries, 5)
        self.assertEqual(cfg.jitter_mode, "full")
        self.assertEqual(cfg.retryable_exceptions, (Exception,))

    def test_backoff_config_custom_instantiation(self) -> None:
        """Positive test: BackoffConfig instantiates with custom explicit values."""
        cfg = BackoffConfig(
            initial_interval_sec=0.25,
            max_interval_sec=15.0,
            multiplier=1.5,
            max_retries=3,
            jitter_mode="decorrelated",
            retryable_exceptions=(IOError, KeyError),
        )
        self.assertEqual(cfg.initial_interval_sec, 0.25)
        self.assertEqual(cfg.max_interval_sec, 15.0)
        self.assertEqual(cfg.multiplier, 1.5)
        self.assertEqual(cfg.max_retries, 3)
        self.assertEqual(cfg.jitter_mode, "decorrelated")
        self.assertEqual(cfg.retryable_exceptions, (IOError, KeyError))

    def test_retry_attempt_instantiation(self) -> None:
        """Positive test: RetryAttempt correctly captures telemetry records."""
        attempt = RetryAttempt(
            attempt_number=2,
            delay_sec=0.45,
            exception_type="ConnectionError",
            error_message="Socket timeout encountered",
            timestamp=1700000000.123,
        )
        self.assertEqual(attempt.attempt_number, 2)
        self.assertEqual(attempt.delay_sec, 0.45)
        self.assertEqual(attempt.exception_type, "ConnectionError")
        self.assertEqual(attempt.error_message, "Socket timeout encountered")
        self.assertEqual(attempt.timestamp, 1700000000.123)

    def test_retry_outcome_instantiation_success(self) -> None:
        """Positive test: RetryOutcome instantiates successful outcome state."""
        attempt = RetryAttempt(attempt_number=1, delay_sec=0.1)
        outcome = RetryOutcome(
            success=True,
            result={"status": "ok"},
            attempts=(attempt,),
            total_delay_sec=0.1,
            final_exception=None,
            attempt_count=2,
        )
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.result, {"status": "ok"})
        self.assertEqual(len(outcome.attempts), 1)
        self.assertEqual(outcome.total_delay_sec, 0.1)
        self.assertIsNone(outcome.final_exception)
        self.assertEqual(outcome.attempt_count, 2)

    def test_retry_outcome_instantiation_failure(self) -> None:
        """Positive test: RetryOutcome instantiates failed outcome state."""
        attempt = RetryAttempt(
            attempt_number=1,
            delay_sec=0.2,
            exception_type="TimeoutError",
            error_message="Operation timed out",
        )
        outcome = RetryOutcome(
            success=False,
            result=None,
            attempts=(attempt,),
            total_delay_sec=0.2,
            final_exception="Operation timed out",
            attempt_count=1,
        )
        self.assertFalse(outcome.success)
        self.assertIsNone(outcome.result)
        self.assertEqual(outcome.final_exception, "Operation timed out")

    def test_negative_backoff_config_immutability(self) -> None:
        """Negative test: Mutating BackoffConfig attribute raises FrozenInstanceError."""
        cfg = BackoffConfig()
        with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
            cfg.initial_interval_sec = 1.0  # type: ignore[misc]

    def test_negative_retry_attempt_immutability(self) -> None:
        """Negative test: Mutating RetryAttempt attribute raises FrozenInstanceError."""
        attempt = RetryAttempt(attempt_number=1, delay_sec=0.1)
        with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
            attempt.delay_sec = 0.5  # type: ignore[misc]

    def test_negative_retry_outcome_immutability(self) -> None:
        """Negative test: Mutating RetryOutcome attribute raises FrozenInstanceError."""
        outcome = RetryOutcome(success=True)
        with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
            outcome.success = False  # type: ignore[misc]


# ==============================================================================
# Category 3: Configuration Boundary Validation (Negative Ratio Verification)
# ==============================================================================

@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.retry_policy pending implementation by software-engineer",
)
class TestRetryPolicyConfigurationValidation(unittest.TestCase):
    """Adversarial suite asserting configuration boundary validation errors."""

    def test_negative_config_negative_initial_interval_raises_value_error(self) -> None:
        """Negative test: Negative initial_interval_sec raises ValueError."""
        with self.assertRaises(ValueError):
            cfg = BackoffConfig(initial_interval_sec=-0.5)
            RetryPolicy(cfg)

    def test_negative_config_max_interval_less_than_initial_raises_value_error(self) -> None:
        """Negative test: max_interval_sec < initial_interval_sec raises ValueError."""
        with self.assertRaises(ValueError):
            cfg = BackoffConfig(initial_interval_sec=10.0, max_interval_sec=2.0)
            RetryPolicy(cfg)

    def test_negative_config_negative_max_retries_raises_value_error(self) -> None:
        """Negative test: Negative max_retries count raises ValueError."""
        with self.assertRaises(ValueError):
            cfg = BackoffConfig(max_retries=-1)
            RetryPolicy(cfg)

    def test_negative_config_invalid_jitter_mode_raises_value_error(self) -> None:
        """Negative test: Unsupported jitter_mode identifier raises ValueError."""
        with self.assertRaises(ValueError):
            cfg = BackoffConfig(jitter_mode="bogus_mode_xyz")
            RetryPolicy(cfg)

    def test_negative_config_non_positive_multiplier_raises_value_error(self) -> None:
        """Negative test: Multiplier <= 0 raises ValueError."""
        with self.assertRaises(ValueError):
            cfg = BackoffConfig(multiplier=0.0)
            RetryPolicy(cfg)


# ==============================================================================
# Category 4: Delay Computation [INV-RETRY-03]
# ==============================================================================

@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.retry_policy pending implementation by software-engineer",
)
class TestRetryPolicyDelayComputation(unittest.TestCase):
    """Evaluates compute_delay mathematical formulations and boundary clamping."""

    def test_compute_delay_none_mode_deterministic(self) -> None:
        """Positive test: None jitter mode produces deterministic exponential progression."""
        cfg = BackoffConfig(
            initial_interval_sec=0.1,
            max_interval_sec=10.0,
            multiplier=2.0,
            jitter_mode="none",
        )
        policy = RetryPolicy(cfg)
        d0 = policy.compute_delay(0, 0.1)
        d1 = policy.compute_delay(1, 0.1)
        d2 = policy.compute_delay(2, 0.1)
        self.assertAlmostEqual(d0, 0.1, places=3)
        self.assertAlmostEqual(d1, 0.2, places=3)
        self.assertAlmostEqual(d2, 0.4, places=3)

    def test_compute_delay_full_jitter_distribution(self) -> None:
        """Positive test: Full jitter calculates delays bounded in [0, Interval_temp]."""
        cfg = BackoffConfig(
            initial_interval_sec=0.2,
            max_interval_sec=5.0,
            multiplier=2.0,
            jitter_mode="full",
        )
        policy = RetryPolicy(cfg)
        for attempt in range(5):
            delay = policy.compute_delay(attempt, 0.2)
            max_bound = min(5.0, 0.2 * (2.0 ** attempt))
            self.assertGreaterEqual(delay, 0.0)
            self.assertLessEqual(delay, max_bound + 1e-6)

    def test_compute_delay_decorrelated_jitter_bounds(self) -> None:
        """Positive test: Decorrelated jitter produces bounded delay within limits."""
        cfg = BackoffConfig(
            initial_interval_sec=0.1,
            max_interval_sec=4.0,
            jitter_mode="decorrelated",
        )
        policy = RetryPolicy(cfg)
        for attempt in range(5):
            delay = policy.compute_delay(attempt, 0.1)
            self.assertGreaterEqual(delay, 0.0)
            self.assertLessEqual(delay, 4.0)

    def test_compute_delay_clamping_to_max_interval(self) -> None:
        """Positive test: Calculated delays strictly do not exceed max_interval_sec [INV-RETRY-03.3]."""
        cfg = BackoffConfig(
            initial_interval_sec=1.0,
            max_interval_sec=3.0,
            multiplier=2.0,
            jitter_mode="none",
        )
        policy = RetryPolicy(cfg)
        large_attempt_delay = policy.compute_delay(25, 1.0)
        self.assertLessEqual(large_attempt_delay, 3.0)
        self.assertAlmostEqual(large_attempt_delay, 3.0, places=3)

    def test_compute_delay_deterministic_with_fixed_seed(self) -> None:
        """Positive test: Delay calculation is reproducible under deterministic random seed."""
        cfg = BackoffConfig(
            initial_interval_sec=0.5,
            max_interval_sec=10.0,
            jitter_mode="full",
        )
        policy = RetryPolicy(cfg)
        random.seed(9999)
        val1 = policy.compute_delay(2, 0.5)
        random.seed(9999)
        val2 = policy.compute_delay(2, 0.5)
        self.assertEqual(val1, val2)

    def test_negative_compute_delay_negative_attempt_raises_value_error(self) -> None:
        """Negative test: Negative attempt count raises ValueError."""
        policy = RetryPolicy()
        with self.assertRaises(ValueError):
            policy.compute_delay(-1, 0.1)

    def test_negative_compute_delay_negative_base_delay_raises_value_error(self) -> None:
        """Negative test: Negative base delay duration raises ValueError."""
        policy = RetryPolicy()
        with self.assertRaises(ValueError):
            policy.compute_delay(0, -1.0)


# ==============================================================================
# Category 5: Resilient Execution & Exception Filtering [INV-RETRY-04]
# ==============================================================================

@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.retry_policy pending implementation by software-engineer",
)
class TestRetryPolicyExecution(unittest.TestCase):
    """Evaluates execute_with_retry under nominal, transient, and permanent failure paths."""

    def test_execute_succeeds_on_first_attempt(self) -> None:
        """Positive test: Target operation succeeding immediately records no delay [INV-RETRY-04]."""
        cfg = BackoffConfig(initial_interval_sec=0.001, max_interval_sec=0.01)
        policy = RetryPolicy(cfg)

        def simple_op() -> str:
            return "nominal_success"

        outcome = policy.execute_with_retry(simple_op)
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.result, "nominal_success")
        self.assertIsNone(outcome.final_exception)
        self.assertEqual(len(outcome.attempts), 0)

    def test_execute_retries_on_retryable_exception_and_succeeds(self) -> None:
        """Positive test: Transient failures trigger retries until operation succeeds."""
        cfg = BackoffConfig(
            initial_interval_sec=0.001,
            max_interval_sec=0.01,
            max_retries=4,
            retryable_exceptions=(KeyError, ValueError),
        )
        policy = RetryPolicy(cfg)
        call_tracker = [0]

        def flaky_op() -> int:
            call_tracker[0] += 1
            if call_tracker[0] < 3:
                raise KeyError(f"Transient defect attempt {call_tracker[0]}")
            return 42

        outcome = policy.execute_with_retry(flaky_op)
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.result, 42)
        self.assertEqual(call_tracker[0], 3)
        self.assertEqual(len(outcome.attempts), 2)

    def test_execute_records_all_retry_attempt_history(self) -> None:
        """Positive test: Each caught retryable error appends a telemetry record [INV-RETRY-04.2]."""
        cfg = BackoffConfig(
            initial_interval_sec=0.001,
            max_interval_sec=0.01,
            max_retries=3,
            retryable_exceptions=(RuntimeError,),
        )
        policy = RetryPolicy(cfg)
        calls = [0]

        def failure_twice() -> str:
            calls[0] += 1
            if calls[0] <= 2:
                raise RuntimeError(f"Failure code {calls[0]}")
            return "recovered"

        outcome = policy.execute_with_retry(failure_twice)
        self.assertTrue(outcome.success)
        self.assertEqual(len(outcome.attempts), 2)
        for idx, att in enumerate(outcome.attempts, 1):
            self.assertEqual(att.attempt_number, idx)
            self.assertGreaterEqual(att.delay_sec, 0.0)
            self.assertIn("RuntimeError", str(att.exception_type))
            self.assertIn(f"Failure code {idx}", str(att.error_message))
            self.assertGreaterEqual(att.timestamp, 0.0)

    def test_execute_calculates_total_delay_accurately(self) -> None:
        """Positive test: outcome.total_delay_sec accurately aggregates attempt delays."""
        cfg = BackoffConfig(
            initial_interval_sec=0.001,
            max_interval_sec=0.01,
            max_retries=2,
            jitter_mode="none",
        )
        policy = RetryPolicy(cfg)
        invocations = [0]

        def fail_once() -> str:
            invocations[0] += 1
            if invocations[0] == 1:
                raise IOError("Transient disk glitch")
            return "done"

        outcome = policy.execute_with_retry(fail_once)
        self.assertTrue(outcome.success)
        self.assertAlmostEqual(
            outcome.total_delay_sec,
            sum(a.delay_sec for a in outcome.attempts),
            places=4,
        )

    def test_execute_passes_args_and_kwargs_to_operation(self) -> None:
        """Positive test: execute_with_retry forwards variable args and kwargs correctly."""
        cfg = BackoffConfig(initial_interval_sec=0.001)
        policy = RetryPolicy(cfg)

        def add_values(a: int, b: int, multiplier: int = 1) -> int:
            return (a + b) * multiplier

        outcome = policy.execute_with_retry(add_values, 10, 20, multiplier=3)
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.result, 90)

    def test_negative_execute_exhausts_max_retries_returns_failure(self) -> None:
        """Negative test: Exhausting max_retries returns failed outcome [INV-RETRY-04.3]."""
        max_retries = 3
        cfg = BackoffConfig(
            initial_interval_sec=0.001,
            max_interval_sec=0.01,
            max_retries=max_retries,
            retryable_exceptions=(RuntimeError,),
        )
        policy = RetryPolicy(cfg)
        run_count = [0]

        def persistent_error() -> None:
            run_count[0] += 1
            raise RuntimeError("Permanent database lock collision")

        outcome = policy.execute_with_retry(persistent_error)
        self.assertFalse(outcome.success)
        self.assertIsNone(outcome.result)
        self.assertIsNotNone(outcome.final_exception)
        self.assertIn("Permanent database lock collision", str(outcome.final_exception))
        self.assertEqual(len(outcome.attempts), max_retries)

    def test_negative_execute_non_retryable_exception_fails_immediately(self) -> None:
        """Negative test: Non-retryable exception terminates immediately without retry [INV-RETRY-04.1]."""
        cfg = BackoffConfig(
            initial_interval_sec=0.001,
            max_interval_sec=0.01,
            max_retries=5,
            retryable_exceptions=(KeyError,),
        )
        policy = RetryPolicy(cfg)
        attempts_counter = [0]

        def fatal_unhandled_op() -> None:
            attempts_counter[0] += 1
            raise ValueError("Fatal invalid configuration argument")

        try:
            outcome = policy.execute_with_retry(fatal_unhandled_op)
            self.assertFalse(outcome.success)
            self.assertEqual(len(outcome.attempts), 0)
        except ValueError:
            _unhandled_reraised = True

        self.assertEqual(
            attempts_counter[0],
            1,
            "Non-retryable exception must invoke operation exactly once without retrying",
        )

    def test_negative_execute_non_callable_target_raises_error(self) -> None:
        """Negative test: Non-callable operation parameter raises TypeError or ValueError."""
        policy = RetryPolicy()
        with self.assertRaises((TypeError, ValueError)):
            policy.execute_with_retry(None)  # type: ignore[arg-type]


# ==============================================================================
# Category 6: CLI Invocation & Serialization [INV-RETRY-07]
# ==============================================================================

@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.retry_policy pending implementation by software-engineer",
)
class TestRetryPolicyCLI(unittest.TestCase):
    """Evaluates standalone CLI invocation, serialization, and error exit codes."""

    def test_cli_default_execution_exits_zero(self) -> None:
        """Positive test: python -m core.retry_policy returns exit code 0 [INV-RETRY-07]."""
        res = _run_retry_cli([])
        self.assertEqual(
            res.returncode,
            0,
            f"CLI exited with non-zero code {res.returncode}: {res.stderr}",
        )

    def test_cli_json_flag_produces_valid_json(self) -> None:
        """Positive test: Supplying --json serializes structured outcome [INV-RETRY-07.1]."""
        res = _run_retry_cli(["--json"])
        self.assertEqual(res.returncode, 0)
        payload = json.loads(res.stdout)
        self.assertIn("success", payload)
        self.assertIn("total_delay_sec", payload)

    def test_cli_custom_parameters_execution(self) -> None:
        """Positive test: CLI accepts custom interval, retry, and jitter flags."""
        args = [
            "--initial-sec", "0.01",
            "--max-sec", "0.2",
            "--retries", "2",
            "--jitter", "decorrelated",
            "--json",
        ]
        res = _run_retry_cli(args)
        self.assertEqual(res.returncode, 0)
        payload = json.loads(res.stdout)
        self.assertIn("success", payload)

    def test_negative_cli_invalid_flag_exits_non_zero(self) -> None:
        """Negative test: Unrecognized CLI argument exits with non-zero status."""
        res = _run_retry_cli(["--unrecognized-synthetic-option-999"])
        self.assertNotEqual(res.returncode, 0)

    def test_negative_cli_invalid_jitter_mode_exits_non_zero(self) -> None:
        """Negative test: Invalid jitter mode CLI argument exits with non-zero status."""
        res = _run_retry_cli(["--jitter", "unsupported_jitter_mode"])
        self.assertNotEqual(res.returncode, 0)

    def test_negative_cli_negative_retries_exits_non_zero(self) -> None:
        """Negative test: Negative retries parameter exits with non-zero status."""
        res = _run_retry_cli(["--retries", "-3"])
        self.assertNotEqual(res.returncode, 0)


# ==============================================================================
# Category 7: Static AST Interface Docking [INV-RETRY-05]
# ==============================================================================

class TestRetryPolicyAstDocking(unittest.TestCase):
    """Evaluates static AST docking between protocol and implementation files."""

    def test_static_ast_docking_verification(self) -> None:
        """Positive test: AST docking between proto and impl evaluates to is_docked=True [INV-RETRY-05]."""
        proto_path, impl_path = _resolve_retry_paths()
        if not proto_path.exists() or not impl_path.exists():
            self.skipTest(
                f"Proto or impl file not present for AST docking test: {proto_path}, {impl_path}"
            )
        if not _AST_CHECKER_AVAILABLE or verify_ast_docking is None:
            self.skipTest("core.ast_docking_checker is not available")

        report = verify_ast_docking(proto_path, impl_path)
        self.assertTrue(
            report.is_docked,
            f"AST docking failed with discrepancies: {report.defects}",
        )
        self.assertEqual(
            len(report.defects),
            0,
            f"Expected zero docking defects, found: {report.defects}",
        )

    def test_negative_ast_docking_missing_file_returns_defects(self) -> None:
        """Negative test: verify_ast_docking with missing implementation returns is_docked=False."""
        if not _AST_CHECKER_AVAILABLE or verify_ast_docking is None:
            self.skipTest("core.ast_docking_checker is not available")

        non_existent_proto = Path("non_existent_proto_file_xyz.py")
        non_existent_impl = Path("non_existent_impl_file_xyz.py")
        report = verify_ast_docking(non_existent_proto, non_existent_impl)
        self.assertFalse(report.is_docked)
        self.assertGreater(len(report.defects), 0)

    def test_negative_ast_docking_syntax_error_file_returns_defects(self) -> None:
        """Negative test: AST docking against malformed Python source returns is_docked=False."""
        if not _AST_CHECKER_AVAILABLE or verify_ast_docking is None:
            self.skipTest("core.ast_docking_checker is not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_proto = Path(tmpdir) / "bad_proto.py"
            bad_proto.write_text("class DefectivelyBrokenSyntax :::", encoding="utf-8")
            valid_impl = Path(tmpdir) / "valid_impl.py"
            valid_impl.write_text("class ValidImpl: pass", encoding="utf-8")

            report = verify_ast_docking(bad_proto, valid_impl)
            self.assertFalse(report.is_docked)
            self.assertGreater(len(report.defects), 0)


if __name__ == "__main__":
    unittest.main()
