"""
Out-of-Process Warm Runner Harness and Daemon Manager (warm_runner.py).

Backward-compatibility facade delegating core execution to core.test_engine.
Retains unified CLI dispatch for `python -m core.warm_runner`.
"""

import argparse
import json
import sys
from typing import List, Optional, Tuple

from .test_engine.contracts import (
    WarmRunnerProtocol,
    WarmTestRequest,
    WarmTestResult,
    WorkerStatus,
)
from .test_engine.engine import WarmRunnerManager, WorkerHandle

__all__ = [
    "WarmRunnerProtocol",
    "WarmTestRequest",
    "WarmTestResult",
    "WorkerStatus",
    "WorkerHandle",
    "WarmRunnerManager",
    "get_warm_runner_manager",
    "main",
]

# Module-level singleton manager for CLI invocations
_GLOBAL_MANAGER: Optional[WarmRunnerManager] = None


def get_warm_runner_manager() -> WarmRunnerManager:
    """Returns the process singleton WarmRunnerManager."""
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = WarmRunnerManager()
    return _GLOBAL_MANAGER


def _handle_run_cli(args: argparse.Namespace) -> int:
    """Handles warm runner test execution CLI."""
    mgr = get_warm_runner_manager()
    import uuid

    req = WarmTestRequest(
        request_id=f"cli_{uuid.uuid4().hex[:6]}",
        test_module=args.target,
        test_case=args.case,
        timeout_seconds=args.timeout,
    )
    result = mgr.submit_test(req)
    print(json.dumps(result.to_json(), indent=2))
    return 0 if result.status == "PASS" else 1


def _handle_status_cli(args: argparse.Namespace) -> int:
    """Handles worker status inspection CLI."""
    mgr = get_warm_runner_manager()
    statuses = [s.to_dict() for s in mgr.get_status()]
    print(json.dumps(statuses, indent=2))
    return 0


def _handle_stop_cli(args: argparse.Namespace) -> int:
    """Handles worker stopping CLI."""
    mgr = get_warm_runner_manager()
    count = mgr.stop_workers(force=args.force)
    print(f"Stopped {count} worker(s).")
    return 0


def _handle_diagnose_cli(args: argparse.Namespace) -> int:
    """Handles hanging worker diagnosis CLI."""
    mgr = get_warm_runner_manager()
    hangs = [h.to_dict() for h in mgr.diagnose_hangs()]
    if hangs:
        print(f"DIAGNOSTIC: Found {len(hangs)} hanging worker(s):")
        print(json.dumps(hangs, indent=2))
        return 1
    print("DIAGNOSTIC: Zero hanging workers detected. All workers nominal.")
    return 0


def parse_cli_args(argv: list) -> Tuple[argparse.ArgumentParser, argparse.Namespace]:
    """Parses command line arguments without cyclomatic complexity overflow."""
    parser = argparse.ArgumentParser(description="Out-of-Process Warm Runner Harness (core.warm_runner)")
    parser.add_argument("--stop", action="store_true", help="Stop warm worker processes")
    parser.add_argument("--force", action="store_true", help="Force kill worker processes")
    parser.add_argument("--diagnose-hangs", action="store_true", help="Diagnose hanging workers")

    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")
    run_parser = subparsers.add_parser("run", help="Run test target")
    run_parser.add_argument("--target", required=True, help="Test module target")
    run_parser.add_argument("--case", default=None, help="Optional test case method")
    run_parser.add_argument("--timeout", type=float, default=3.0, help="Watchdog timeout in seconds")

    subparsers.add_parser("status", help="Inspect worker pool status")

    parsed = parser.parse_args(argv)
    return parser, parsed


def main(argv: Optional[List[str]] = None) -> int:
    """Dispatches CLI commands deterministically."""
    parser, args = parse_cli_args(argv or sys.argv[1:])

    if args.stop:
        return _handle_stop_cli(args)
    if args.diagnose_hangs:
        return _handle_diagnose_cli(args)
    if args.subcommand == "run":
        return _handle_run_cli(args)
    if args.subcommand == "status":
        return _handle_status_cli(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
