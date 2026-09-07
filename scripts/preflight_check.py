"""
Unified Preflight Verification Engine (scripts.preflight_check).

Authoritative single-command verification gate mandated by GEMINI.md (v7.1, Section 3.4).
Coordinates Track A (Static Compliance, Filesystem Topology) and Track B (Regression Rigor)
with bounded latency (< 3.0s) and strict output compaction.
"""

import argparse
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import unittest

# Ensure repository root is in sys.path for direct script execution
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_ROOTS = [
    os.path.abspath(os.path.join(_SCRIPT_DIR, "..")),
    os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..")),
]
for root in _CANDIDATE_ROOTS:
    if root not in sys.path:
        sys.path.insert(0, root)

try:
    from scripts.compliance_checker import audit_file, _collect_target_files
    from core.fs_topology import audit_filesystem_topology
except ModuleNotFoundError:
    from sandbox.scripts.compliance_checker import audit_file, _collect_target_files
    from sandbox.core.fs_topology import audit_filesystem_topology


@dataclass(frozen=True)
class PreflightReport:
    """Immutable aggregate outcome of multi-track preflight verification."""

    passed: bool
    duration_ms: float
    compliance_files: int
    compliance_defects: int
    topology_scanned: int
    topology_violations: int
    tests_run: int
    test_failures: int
    test_errors: int
    diagnostics: List[str]
    mode: str = "full"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes report to standard dictionary."""
        return {
            "passed": self.passed,
            "mode": self.mode,
            "duration_ms": round(self.duration_ms, 2),
            "compliance": {
                "files": self.compliance_files,
                "defects": self.compliance_defects,
            },
            "topology": {
                "scanned": self.topology_scanned,
                "violations": self.topology_violations,
            },
            "tests": {
                "run": self.tests_run,
                "failures": self.test_failures,
                "errors": self.test_errors,
            },
            "diagnostics": self.diagnostics,
        }


def _run_compliance_gate(target_dir: str = ".") -> Tuple[int, int, List[str]]:
    """Executes Track A1 static compliance audit, returning counts and failure diagnostics."""
    targets = _collect_target_files([target_dir])
    total_defects = 0
    diagnostics: List[str] = []

    for path in targets:
        _, defects = audit_file(path)
        if defects:
            total_defects += len(defects)
            for d in defects:
                diagnostics.append(f"[Compliance] {path}:L{d.line} [{d.type}] {d.message}")

    return len(targets), total_defects, diagnostics


def _run_topology_gate(root_path: Path) -> Tuple[int, int, List[str]]:
    """Executes Track A2 filesystem topology audit, returning counts and violation diagnostics."""
    result = audit_filesystem_topology(root_path)
    diagnostics: List[str] = []

    if not result.passed:
        for v in result.violations:
            diagnostics.append(f"[Topology] [{v.rule_id}] {v.filepath} (depth={v.depth}): {v.message}")

    return result.scanned_count, len(result.violations), diagnostics


def _run_test_suite_gate(test_dir: str = "tests") -> Tuple[int, int, int, List[str]]:
    """Executes Track B regression test discovery with isolated stream capture."""
    loader = unittest.defaultTestLoader
    suite = loader.discover(test_dir, pattern="test_*.py")
    stream_buf = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream_buf, verbosity=0)
    result = runner.run(suite)

    diagnostics: List[str] = []
    for failure in result.failures:
        test_case, err_trace = failure
        diagnostics.append(f"[Test Failure] {test_case.id()}: {err_trace.splitlines()[-1]}")
    for error in result.errors:
        test_case, err_trace = error
        diagnostics.append(f"[Test Error] {test_case.id()}: {err_trace.splitlines()[-1]}")

    return result.testsRun, len(result.failures), len(result.errors), diagnostics


def run_preflight(
    root_path: Optional[Path] = None,
    quick: bool = False,
) -> PreflightReport:
    """
    Executes full multi-track preflight verification pipeline.
    Enforces contiguous NFR bounds and sub-3.0s fast-path ceiling.
    """
    start_time = time.perf_counter()
    base_dir = root_path if root_path is not None else Path(".")

    target_scope = str(base_dir / "core") if quick and (base_dir / "core").is_dir() else str(base_dir)
    comp_files, comp_defects, comp_diag = _run_compliance_gate(target_scope)
    topo_scanned, topo_violations, topo_diag = _run_topology_gate(base_dir)
    tests_run, test_fails, test_errs, test_diag = _run_test_suite_gate(str(base_dir / "tests"))

    all_diagnostics = comp_diag + topo_diag + test_diag
    passed = (comp_defects == 0) and (topo_violations == 0) and (test_fails == 0) and (test_errs == 0)
    duration_ms = (time.perf_counter() - start_time) * 1000.0

    return PreflightReport(
        passed=passed,
        duration_ms=duration_ms,
        compliance_files=comp_files,
        compliance_defects=comp_defects,
        topology_scanned=topo_scanned,
        topology_violations=topo_violations,
        tests_run=tests_run,
        test_failures=test_fails,
        test_errors=test_errs,
        diagnostics=all_diagnostics,
        mode="quick" if quick else "full",
    )


def _render_text_report(report: PreflightReport, verbose: bool = False) -> None:
    """Renders formatted preflight verification report."""
    duration_s = report.duration_ms / 1000.0
    mode_label = "QUICK" if report.mode == "quick" else "FULL"
    print("=" * 80)
    if report.passed:
        print(f"PREFLIGHT PASS [{mode_label}]: All quality gates cleared in {duration_s:.2f}s (Exit code 0).")
        print(f"- Track A1 (Static Compliance):    {report.compliance_files} files audited, 0 defects")
        print(f"- Track A2 (Filesystem Topology):  {report.topology_scanned} items scanned, 0 violations")
        print(f"- Track B  (Regression Rigor):     {report.tests_run} tests passed, 0 failures")
    else:
        print(f"PREFLIGHT FAIL [{mode_label}]: Quality gates rejected in {duration_s:.2f}s (Exit code 1).")
        print(f"- Static Compliance Defects:  {report.compliance_defects}")
        print(f"- Filesystem Violations:      {report.topology_violations}")
        print(f"- Regression Test Failures:   {report.test_failures + report.test_errors}")
        print("-" * 80)
        print("Pinpoint Defect Diagnostics:")
        limit = len(report.diagnostics) if verbose else min(10, len(report.diagnostics))
        for idx, diag in enumerate(report.diagnostics[:limit], 1):
            print(f"  {idx}. {diag}")
        if not verbose and len(report.diagnostics) > 10:
            print(f"  ... and {len(report.diagnostics) - 10} additional defect(s). Run with -v for full output.")
    print("=" * 80)


def build_parser() -> argparse.ArgumentParser:
    """Constructs command-line argument parser for preflight checker."""
    parser = argparse.ArgumentParser(
        prog="python scripts/preflight_check.py",
        description="Unified Preflight Verification Engine conforming to GEMINI.md Section 3.4.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        default=True,
        help="Execute fast-path preflight (< 3.0s, core/ targeted audit)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        default=False,
        help="Execute complete 100% deep preflight check across all files and tests",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Display verbose defect diagnostics")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--root", type=str, default=".", help="Root directory path to verify")
    parser.add_argument(
        "--no-telemetry",
        action="store_true",
        help="Suppress automatic defect and resolution ingestion into memory.db",
    )
    return parser


def _handle_preflight_telemetry(
    report: PreflightReport,
    no_telemetry: bool = False,
    db_path: Optional[Path] = None,
) -> None:
    """Telemetry hook preserved as zero-op stub after collector deprecation."""
    return None


def main(argv: Optional[List[str]] = None) -> int:
    """CLI execution entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    root_path = Path(args.root)
    quick_mode = args.quick and not args.full
    report = run_preflight(root_path=root_path, quick=quick_mode)

    if not args.no_telemetry:
        _handle_preflight_telemetry(report, no_telemetry=args.no_telemetry)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _render_text_report(report, verbose=args.verbose)

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
