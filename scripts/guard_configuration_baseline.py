"""
Configuration Baseline & Run Completion Enforcement Hook (scripts.guard_configuration_baseline).

Lifecycle interceptor executed on Stop hook events conforming to CONTRACT-20260907-configuration-baseline-hook.
Prevents unanchored mutations by requiring SCM configuration baseline commit before run conclusion
when no tasks in docs/active/CURRENT_STATE.md are IN_PROGRESS.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

COMMIT_DIRECTIVE_MESSAGE = (
    "[MANDATORY SCM COMMIT] Run concluded with uncommitted modifications. "
    "Mandatory SCM invariant: You MUST commit the configuration baseline "
    "(git add . && git commit -m '...') before concluding the run."
)

EPHEMERAL_PATTERNS: Tuple[str, ...] = (
    ".tmp",
    "__pycache__",
    ".pytest_cache",
    "cortex_spool.jsonl",
    ".coverage",
    ".ruff_cache",
    ".mypy_cache",
)


@dataclass(frozen=True)
class ConfigurationBaselineReport:
    """Immutable report of configuration baseline and task lifecycle status."""

    active_tasks: Tuple[str, ...]
    uncommitted_files: Tuple[str, ...]
    is_git_clean: bool
    decision: str
    explanation: Optional[str] = None

    def to_hook_response(self) -> Dict[str, Any]:
        """Serializes result into canonical Stop hook JSON response dictionary."""
        if self.decision == "continue":
            msg = self.explanation or COMMIT_DIRECTIVE_MESSAGE
            return {
                "decision": "continue",
                "explanation": msg,
                "reason": msg,
            }
        return {}


@dataclass(frozen=True)
class HookInvocationContext:
    """Immutable context received from Stop hook payload."""

    cwd: str
    transcript_path: Optional[str] = None
    stop_reason: Optional[str] = None


def resolve_repo_root(start_path: Optional[Path] = None) -> Path:
    """Resolves the repository root containing .git or GEMINI.md."""
    current = (start_path or Path(__file__)).resolve()
    candidates = [current] + list(current.parents)
    for directory in candidates:
        if (directory / ".git").exists() or (directory / "GEMINI.md").exists():
            return directory
    return Path(__file__).resolve().parent.parent


def is_ephemeral_path(path_str: str) -> bool:
    """Checks whether a relative path matches ephemeral or temporary file patterns."""
    norm = path_str.replace(chr(92), "/")
    for pattern in EPHEMERAL_PATTERNS:
        if pattern in norm or norm.endswith(pattern):
            return True
    return False


def parse_git_status_lines(status_text: str) -> Tuple[str, ...]:
    """Parses git status --porcelain output into filtered list of modified paths."""
    uncommitted: List[str] = []
    for line in status_text.splitlines():
        trimmed = line.strip()
        if len(trimmed) < 3:
            continue
        raw_path = line[3:].strip().strip('"')
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ")[-1].strip().strip('"')
        if raw_path and not is_ephemeral_path(raw_path):
            uncommitted.append(raw_path)
    return tuple(sorted(uncommitted))


def query_git_status(repo_root: Path, timeout: float = 5.0) -> Tuple[str, ...]:
    """Queries git status --porcelain bounded by timeout."""
    cmd = ["git", "status", "--porcelain"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            check=False,
        )
        if proc.returncode != 0:
            return ()
        return parse_git_status_lines(proc.stdout)
    except (subprocess.SubprocessError, OSError, UnicodeDecodeError):
        return ()


def inspect_ledger_tasks(ledger_path: Path) -> Tuple[Tuple[str, ...], bool]:
    """
    Parses docs/active/CURRENT_STATE.md to extract active tasks and capacity.
    Returns (active_task_ids, has_active_task_or_capacity).
    """
    if not ledger_path.exists() or not ledger_path.is_file():
        return (), False

    try:
        content = ledger_path.read_text(encoding="utf-8")
    except OSError:
        return (), False

    active_tasks = _extract_active_tasks_from_content(content)
    has_capacity = _check_active_capacity_from_content(content)
    has_active = bool(active_tasks or has_capacity)
    return active_tasks, has_active


def _extract_active_tasks_from_content(content: str) -> Tuple[str, ...]:
    """Extracts task IDs matching IN_PROGRESS lifecycle status."""
    table_pattern = r"[|]\s*\*\*`?([A-Za-z0-9_-]+)`?\*\*\s*[|][^|]*[|]\s*`?IN_PROGRESS`?\s*[|]"
    matches = re.findall(table_pattern, content, re.IGNORECASE)
    if matches:
        return tuple(sorted(set(matches)))
    return ()


def _check_active_capacity_from_content(content: str) -> bool:
    """Checks if active task capacity line reports active occupied slots."""
    cap_pattern = r"Active Task Capacity\*{0,2}:\s*(\d+)\s*of\s*(\d+)"
    match = re.search(cap_pattern, content, re.IGNORECASE)
    if match:
        occupied = int(match.group(1))
        return occupied > 0
    return False


def evaluate_baseline(
    repo_root: Path,
    ledger_path: Optional[Path] = None,
    uncommitted_override: Optional[Tuple[str, ...]] = None,
) -> ConfigurationBaselineReport:
    """Evaluates git working tree and CURRENT_STATE.md to determine hook decision."""
    effective_ledger = ledger_path or (repo_root / "docs" / "active" / "CURRENT_STATE.md")
    active_tasks, has_active = inspect_ledger_tasks(effective_ledger)

    if uncommitted_override is not None:
        uncommitted = uncommitted_override
    else:
        uncommitted = query_git_status(repo_root)

    is_clean = len(uncommitted) == 0

    if has_active or is_clean:
        return ConfigurationBaselineReport(
            active_tasks=active_tasks,
            uncommitted_files=uncommitted,
            is_git_clean=is_clean,
            decision="allow",
            explanation=None,
        )

    return ConfigurationBaselineReport(
        active_tasks=active_tasks,
        uncommitted_files=uncommitted,
        is_git_clean=False,
        decision="continue",
        explanation=COMMIT_DIRECTIVE_MESSAGE,
    )


def _check_windows_pipe_readable(fileno: int) -> bool:
    """Checks whether Windows named pipe has bytes available."""
    try:
        import msvcrt
        import ctypes

        handle = msvcrt.get_osfhandle(fileno)
        avail = ctypes.c_ulong(0)
        res = ctypes.windll.kernel32.PeekNamedPipe(
            handle, None, 0, None, ctypes.byref(avail), None
        )
        return bool(res and avail.value > 0)
    except (ImportError, OSError, ValueError):
        return True


def _check_posix_pipe_readable() -> bool:
    """Checks whether POSIX stdin stream is readable without blocking."""
    try:
        import select

        readable, _, _ = select.select([sys.stdin], [], [], 0.0)
        return bool(readable)
    except (ImportError, OSError, ValueError):
        return True


def _has_stdin_data() -> bool:
    """Non-blocking check whether stdin has data available to read."""
    if sys.stdin is None or sys.stdin.isatty():
        return False

    try:
        fileno = sys.stdin.fileno()
    except (io.UnsupportedOperation, AttributeError, OSError):
        return True

    if sys.platform == "win32":
        return _check_windows_pipe_readable(fileno)

    return _check_posix_pipe_readable()


def read_stdin_payload() -> Dict[str, Any]:
    """Reads and parses JSON payload from stdin without blocking."""
    if not _has_stdin_data():
        return {}

    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        parsed = json.loads(raw, strict=False)
        if isinstance(parsed, dict):
            return parsed
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return {}


def parse_invocation_context(payload: Dict[str, Any]) -> HookInvocationContext:
    """Extracts HookInvocationContext from hook stdin payload."""
    cwd = str(payload.get("cwd") or os.getcwd())
    transcript = payload.get("transcriptPath") or payload.get("transcript_path")
    reason = (
        payload.get("stopReason")
        or payload.get("stop_reason")
        or payload.get("terminationReason")
    )
    return HookInvocationContext(
        cwd=cwd,
        transcript_path=str(transcript) if transcript else None,
        stop_reason=str(reason) if reason else None,
    )


def build_cli_parser() -> argparse.ArgumentParser:
    """Constructs CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Configuration Baseline & Run Completion Enforcement Hook"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Exit with code 0 if stop allowed, 1 if commit required",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full ConfigurationBaselineReport JSON to stdout",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="Override repository root path",
    )
    parser.add_argument(
        "--ledger",
        type=str,
        default=None,
        help="Override CURRENT_STATE.md ledger path",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    _stdin_payload = read_stdin_payload()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else resolve_repo_root()
    ledger_path = Path(args.ledger).resolve() if args.ledger else None

    report = evaluate_baseline(repo_root, ledger_path)

    if args.check_only:
        return 1 if report.decision == "continue" else 0

    if args.json:
        full_output = {
            "active_tasks": list(report.active_tasks),
            "uncommitted_files": list(report.uncommitted_files),
            "is_git_clean": report.is_git_clean,
            "decision": report.decision,
            "explanation": report.explanation,
            "hook_response": report.to_hook_response(),
        }
        print(json.dumps(full_output, indent=2))
        return 0

    print(json.dumps(report.to_hook_response()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
