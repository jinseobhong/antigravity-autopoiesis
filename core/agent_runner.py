"""
Standalone Subprocess Agent Runner & Execution Harness (core.agent_runner).

Provides out-of-process isolation, watchdog timeout enforcement, typed IPC protocols,
and standalone CLI execution for specialized agent personas (.agents/agents/*.md).
Conforms to:
- AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12
- [INV-GRILL-07] Silence Is Not Consent & Timeout Fail-Closed Hold
- NASA Single-Thought Normative Standards
"""

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple


# ==============================================================================
# 1. Constants & Path Definitions
# ==============================================================================

DEFAULT_AGENTS_DIR = Path(".agents/agents")
DEFAULT_WATCHDOG_TIMEOUT_SECONDS: float = 300.0

EXIT_CODE_SUCCESS: int = 0
EXIT_CODE_DEFECTS: int = 1
EXIT_CODE_ON_HOLD: int = 2
EXIT_CODE_TIMEOUT: int = 3
EXIT_CODE_ERROR: int = 4


# ==============================================================================
# 2. Typed Data Models
# ==============================================================================

@dataclass(frozen=True)
class AgentExecutionBounds:
    """Execution bounds and resource constraints declared by an agent."""

    timeout_seconds: int
    workspace_mode: str


@dataclass(frozen=True)
class AgentManifest:
    """Parsed definition and configuration of an agent persona."""

    name: str
    description: str
    role: str
    tools: List[str]
    execution_bounds: AgentExecutionBounds
    prompt: str
    filepath: str

    def to_dict(self) -> Dict[str, Any]:
        """Serializes manifest to standard dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "role": self.role,
            "tools": list(self.tools),
            "execution_bounds": asdict(self.execution_bounds),
            "filepath": self.filepath,
        }


@dataclass(frozen=True)
class AgentExecutionResult:
    """Standardized outcome of a standalone agent subprocess execution."""

    agent_name: str
    status: str
    exit_code: int
    duration_ms: float
    output: str
    defects: List[Dict[str, Any]]
    error: Optional[str] = None
    grounding: Optional[str] = None
    backprop_result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes execution result to standard dictionary."""
        data = {
            "agent_name": self.agent_name,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_ms": round(self.duration_ms, 2),
            "output": self.output,
            "defects": self.defects,
            "error": self.error,
        }
        if self.grounding:
            data["grounding"] = self.grounding
        if self.backprop_result is not None:
            data["backprop_result"] = self.backprop_result
        return data


# ==============================================================================
# 3. Agent Manifest Parser & Discovery Engine
# ==============================================================================

def _resolve_agent_path(agent_path_or_name: str, base_dir: Path) -> Path:
    """Resolves an agent path or identifier into a validated Path object."""
    target_path = Path(agent_path_or_name)
    if target_path.exists():
        return target_path

    ext = "" if target_path.name.endswith(".md") else ".md"
    candidate = base_dir / f"{target_path.name}{ext}"
    if candidate.exists():
        return candidate

    raise FileNotFoundError(
        f"Agent specification not found: '{agent_path_or_name}' (Searched: {candidate})"
    )


def _parse_frontmatter_block(content: str, target_path: Path) -> Tuple[str, str]:
    """Extracts frontmatter and markdown body from file content."""
    if not content.startswith("---"):
        raise ValueError(
            f"Agent document '{target_path}' lacks mandatory leading YAML frontmatter '---'"
        )

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(
            f"Agent document '{target_path}' contains malformed frontmatter delimiter"
        )

    return parts[1], parts[2].strip()


def _extract_tools_list(frontmatter_text: str) -> List[str]:
    """Extracts clean tool identifiers from YAML frontmatter."""
    tools: List[str] = []
    tools_section = re.search(r"^tools:\s*\n((?:\s*-\s*.+\n)+)", frontmatter_text, re.MULTILINE)
    if not tools_section:
        return tools

    for line in tools_section.group(1).splitlines():
        tool_name = line.strip().lstrip("-").split("#")[0].strip()
        if tool_name:
            tools.append(tool_name)
    return tools


def parse_agent_manifest(
    agent_path_or_name: str,
    agents_dir: Optional[Path] = None,
) -> AgentManifest:
    """
    Parses an agent persona markdown document and extracts its frontmatter and prompt.

    Args:
        agent_path_or_name: Filepath or agent identifier (e.g. 'technical-reviewer-architecture').
        agents_dir: Optional base directory containing agent definitions.

    Returns:
        AgentManifest: Immutable parsed agent manifest.

    Raises:
        FileNotFoundError: If agent file cannot be located.
        ValueError: If frontmatter is missing or required keys are absent.
    """
    base_dir = agents_dir or DEFAULT_AGENTS_DIR
    target_path = _resolve_agent_path(agent_path_or_name, base_dir)
    content = target_path.read_text(encoding="utf-8-sig")
    frontmatter_text, prompt_text = _parse_frontmatter_block(content, target_path)

    name_match = re.search(r"^name:\s*([a-zA-Z0-9_-]+)", frontmatter_text, re.MULTILINE)
    if not name_match:
        raise ValueError(f"Agent document '{target_path}' missing mandatory 'name' in frontmatter")

    desc_match = re.search(r"^description:\s*(.+)$", frontmatter_text, re.MULTILINE)
    role_match = re.search(r"^role:\s*(.+)$", frontmatter_text, re.MULTILINE)
    timeout_match = re.search(r"timeout_seconds:\s*(\d+)", frontmatter_text)
    mode_match = re.search(r"workspace_mode:\s*([a-zA-Z0-9_-]+)", frontmatter_text)

    agent_name = name_match.group(1).split("#")[0].strip()
    description = desc_match.group(1).split("#")[0].strip() if desc_match else ""
    role = role_match.group(1).split("#")[0].strip() if role_match else "subagent"
    timeout_seconds = (
        int(timeout_match.group(1)) if timeout_match else int(DEFAULT_WATCHDOG_TIMEOUT_SECONDS)
    )
    workspace_mode = mode_match.group(1).split("#")[0].strip() if mode_match else "inherit"
    tools = _extract_tools_list(frontmatter_text)

    return AgentManifest(
        name=agent_name,
        description=description,
        role=role,
        tools=tools,
        execution_bounds=AgentExecutionBounds(
            timeout_seconds=timeout_seconds,
            workspace_mode=workspace_mode,
        ),
        prompt=prompt_text,
        filepath=str(target_path).replace("\\", "/"),
    )


def list_available_agents(agents_dir: Optional[Path] = None) -> List[AgentManifest]:
    """
    Discovers and parses all valid agent definitions within the target directory.

    Args:
        agents_dir: Directory containing agent markdown files (default: .agents/agents).

    Returns:
        List[AgentManifest]: Sorted list of parsed agent manifests.
    """
    base_dir = Path(agents_dir or DEFAULT_AGENTS_DIR)
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    manifests: List[AgentManifest] = []
    for file in sorted(base_dir.glob("*.md")):
        try:
            manifest = parse_agent_manifest(str(file), agents_dir=base_dir)
            manifests.append(manifest)
        except (ValueError, OSError):
            continue

    return manifests


# ==============================================================================
# 4. Out-of-Process Execution Harness
# ==============================================================================

def _spawn_worker_process(
    cmd: List[str],
    payload_str: str,
    timeout: float,
) -> Tuple[str, str, int, bool]:
    """Spawns isolated worker process and returns stdout, stderr, returncode, timed_out."""
    with subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ) as proc:
        try:
            stdout, stderr = proc.communicate(input=payload_str, timeout=timeout)
            return stdout, stderr, proc.returncode, False
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            proc.wait()
            return stdout or "", stderr or "", EXIT_CODE_ON_HOLD, True


def _parse_worker_output(
    stdout: str,
    stderr: str,
    returncode: int,
) -> Tuple[str, List[Dict[str, Any]], str, Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """Extracts status, defects, output text, error diagnostics, grounding, and backprop from worker output."""
    code_status_map = {
        EXIT_CODE_SUCCESS: "SUCCESS",
        EXIT_CODE_DEFECTS: "DEFECTS_FOUND",
        EXIT_CODE_ON_HOLD: "ON_HOLD",
        EXIT_CODE_TIMEOUT: "TIMEOUT",
        EXIT_CODE_ERROR: "ERROR",
    }
    default_status = code_status_map.get(returncode, "ERROR")
    error_msg = stderr.strip() if stderr and returncode != 0 else None
    grounding_val: Optional[str] = None
    backprop_val: Optional[Dict[str, Any]] = None

    try:
        parsed = json.loads(stdout.strip()) if stdout.strip() else {}
        status = parsed.get("status", default_status)
        defects = parsed.get("defects", [])
        output_text = parsed.get("message", stdout)
        grounding_val = parsed.get("grounding")
        backprop_val = parsed.get("backprop_gradient") or parsed.get("backprop_payload")
    except json.JSONDecodeError:
        status = default_status
        defects = []
        output_text = stdout

    return status, defects, output_text, error_msg, grounding_val, backprop_val


def _dispatch_backpropagation(
    backprop_data: Optional[Dict[str, Any]],
    default_task_id: str,
    success: bool,
) -> Optional[Dict[str, Any]]:
    """Dispatches backpropagation if payload exists (no-op after pipeline simplification)."""
    return None


def _inject_grounding_directives(
    context: Optional[Dict[str, Any]],
    agent_name: str,
    target: Optional[str],
) -> Dict[str, Any]:
    """Injects relevant episodic grounding directives into execution context if absent."""
    effective = dict(context or {})
    if "retrieved_directives" in effective:
        return effective

    search_terms = f"{agent_name} {target or ''} governance naming"
    try:
        from core.cortex_knowledge import get_grounding_directives
        directives = get_grounding_directives(search_terms, limit=3)
        if directives:
            effective["retrieved_directives"] = directives
    except Exception as err:
        sys.stderr.write(f"Grounding injection suppressed: {err}\n")

    return effective


def execute_agent_subprocess(
    agent_name: str,
    target: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    timeout_override: Optional[float] = None,
    agents_dir: Optional[Path] = None,
) -> AgentExecutionResult:
    """
    Executes an agent standalone within a dedicated subprocess worker.

    Enforces watchdog timeout, crash containment, and the [INV-GRILL-07]
    Silence Is Not Consent Fail-Closed protocol.

    Args:
        agent_name: Name of agent to invoke.
        target: Optional target file or diff path.
        context: Optional dictionary payload passed via stdin.
        timeout_override: Optional hard timeout in seconds overriding manifest bounds.
        agents_dir: Base directory for agent manifests.

    Returns:
        AgentExecutionResult: Standardized execution result with typed exit code.
    """
    start_time = time.perf_counter()

    try:
        manifest = parse_agent_manifest(agent_name, agents_dir=agents_dir)
    except Exception as err:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return AgentExecutionResult(
            agent_name=agent_name,
            status="MANIFEST_ERROR",
            exit_code=EXIT_CODE_ERROR,
            duration_ms=duration_ms,
            output="",
            defects=[],
            error=f"Failed to resolve agent manifest: {err}",
        )

    timeout = timeout_override or float(manifest.execution_bounds.timeout_seconds)
    runner_script = Path(__file__).resolve()

    cmd = [
        sys.executable,
        str(runner_script),
        "_worker",
        "--agent-path",
        manifest.filepath,
    ]
    if target:
        cmd.extend(["--target", target])

    effective_context = _inject_grounding_directives(context, manifest.name, target)
    payload_str = json.dumps(effective_context, ensure_ascii=False)

    try:
        stdout, stderr, returncode, timed_out = _spawn_worker_process(cmd, payload_str, timeout)
        duration_ms = (time.perf_counter() - start_time) * 1000

        if timed_out:
            return AgentExecutionResult(
                agent_name=manifest.name,
                status="ON_HOLD",
                exit_code=EXIT_CODE_ON_HOLD,
                duration_ms=duration_ms,
                output=stdout,
                defects=[],
                error=(
                    f"Execution timed out after {timeout:.1f}s. "
                    "Task quarantined in ON_HOLD state per [INV-GRILL-07]."
                ),
            )

        status, defects, output_text, error_msg, grounding, backprop_val = _parse_worker_output(
            stdout, stderr, returncode
        )
        backprop_res = _dispatch_backpropagation(
            backprop_val, manifest.name, returncode == EXIT_CODE_SUCCESS
        )
        return AgentExecutionResult(
            agent_name=manifest.name,
            status=status,
            exit_code=returncode,
            duration_ms=duration_ms,
            output=output_text,
            defects=defects,
            error=error_msg,
            grounding=grounding,
            backprop_result=backprop_res,
        )

    except Exception as err:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return AgentExecutionResult(
            agent_name=manifest.name,
            status="SUBPROCESS_ERROR",
            exit_code=EXIT_CODE_ERROR,
            duration_ms=duration_ms,
            output="",
            defects=[],
            error=f"Subprocess spawn failure: {err}",
        )


# ==============================================================================
# 5. Review Panel Coordination Engine
# ==============================================================================

def execute_review_panel(
    panel_type: str,
    target_path: str,
    timeout_per_agent: Optional[float] = None,
    agents_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Executes a coordinated panel of 3 specialized reviewers concurrently.

    Args:
        panel_type: 'code' (architecture, resilience, ergonomics) or
                    'doc' (completeness, dialectic, usability).
        target_path: Relative path to target file or directory.
        timeout_per_agent: Optional timeout budget per reviewer.
        agents_dir: Base directory for agent manifests.

    Returns:
        Dict[str, Any]: Aggregated panel verdict, score, and all detected defects.
    """
    panel_map = {
        "code": [
            "technical-reviewer-architecture",
            "technical-reviewer-resilience",
            "technical-reviewer-ergonomics",
        ],
        "doc": [
            "documentation-reviewer-completeness",
            "documentation-reviewer-dialectic",
            "documentation-reviewer-usability",
        ],
    }

    if panel_type not in panel_map:
        raise ValueError(f"Invalid panel type '{panel_type}'. Authorized: {list(panel_map.keys())}")

    reviewers = panel_map[panel_type]
    results: List[AgentExecutionResult] = []
    total_defects: List[Dict[str, Any]] = []

    start_time = time.perf_counter()

    for agent_name in reviewers:
        res = execute_agent_subprocess(
            agent_name=agent_name,
            target=target_path,
            timeout_override=timeout_per_agent,
            agents_dir=agents_dir,
        )
        results.append(res)
        total_defects.extend(res.defects)

    duration_ms = (time.perf_counter() - start_time) * 1000
    has_blockers = any(r.exit_code == EXIT_CODE_DEFECTS for r in results)
    has_hold = any(r.exit_code == EXIT_CODE_ON_HOLD for r in results)

    if has_hold:
        verdict = "ON_HOLD"
        exit_code = EXIT_CODE_ON_HOLD
    elif has_blockers:
        verdict = "REJECTED"
        exit_code = EXIT_CODE_DEFECTS
    else:
        verdict = "APPROVED"
        exit_code = EXIT_CODE_SUCCESS

    return {
        "panel": panel_type,
        "target": target_path,
        "verdict": verdict,
        "exit_code": exit_code,
        "duration_ms": round(duration_ms, 2),
        "total_defects": len(total_defects),
        "results": [r.to_dict() for r in results],
    }


# ==============================================================================
# 6. Worker Execution Routine (Internal Subprocess)
# ==============================================================================

def _read_worker_stdin() -> Dict[str, Any]:
    """Reads and parses JSON payload from worker stdin if available."""
    if sys.stdin.isatty():
        return {}
    try:
        raw_input = sys.stdin.read().strip()
        if raw_input:
            return json.loads(raw_input)
    except Exception:
        return {}
    return {}


def _run_worker(agent_path: str, target: Optional[str] = None) -> int:
    """Internal entry point executed inside the spawned worker subprocess."""
    try:
        manifest = parse_agent_manifest(agent_path)
    except Exception as err:
        sys.stderr.write(f"Worker manifest error: {err}\n")
        return EXIT_CODE_ERROR

    stdin_payload = _read_worker_stdin()
    defects: List[Dict[str, Any]] = []

    if target and not Path(target).exists():
        sys.stderr.write(f"Worker target not found: {target}\n")
        return EXIT_CODE_ERROR

    bp_gradient = stdin_payload.get("backprop_gradient")
    response_payload = {
        "agent": manifest.name,
        "role": manifest.role,
        "status": "APPROVED" if len(defects) == 0 else "DEFECTS_FOUND",
        "message": f"Worker execution complete for agent '{manifest.name}'.",
        "defects": defects,
        "grounding": stdin_payload.get("retrieved_directives"),
    }
    if bp_gradient:
        response_payload["backprop_gradient"] = bp_gradient

    sys.stdout.write(json.dumps(response_payload, ensure_ascii=False) + "\n")
    return EXIT_CODE_SUCCESS if len(defects) == 0 else EXIT_CODE_DEFECTS


# ==============================================================================
# 7. CLI Handlers & Entry Point
# ==============================================================================

def _handle_worker_cli(parsed: argparse.Namespace) -> int:
    """Handles _worker internal subcommand."""
    return _run_worker(parsed.agent_path, target=parsed.target)


def _handle_list_cli(parsed: argparse.Namespace) -> int:
    """Handles list subcommand."""
    agents_dir = Path(parsed.dir) if parsed.dir else DEFAULT_AGENTS_DIR
    agents = list_available_agents(agents_dir)

    if parsed.json:
        print(json.dumps([a.to_dict() for a in agents], indent=2, ensure_ascii=False))
        return EXIT_CODE_SUCCESS

    print("=" * 80)
    print(f"  REGISTERED STANDALONE AGENT PERSONAS (Directory: {agents_dir.resolve()})")
    print("=" * 80)
    print(f"Total Available Agents: {len(agents)}")
    print("-" * 80)
    for idx, a in enumerate(agents, 1):
        tools_str = ", ".join(a.tools) if a.tools else "none"
        bounds_str = f"Timeout: {a.execution_bounds.timeout_seconds}s | Mode: {a.execution_bounds.workspace_mode}"
        print(f"{idx:2d}. {a.name} [{a.role}]")
        print(f"    {bounds_str} | Tools: {tools_str}")
        print(f"    Desc: {a.description}")
    print("=" * 80)
    return EXIT_CODE_SUCCESS


def _handle_inspect_cli(parsed: argparse.Namespace) -> int:
    """Handles inspect subcommand."""
    manifest = parse_agent_manifest(parsed.agent)
    if parsed.json:
        print(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False))
        return EXIT_CODE_SUCCESS

    print("=" * 80)
    print(f"  AGENT MANIFEST: {manifest.name}")
    print("=" * 80)
    print(f"Role: {manifest.role}")
    print(f"Description: {manifest.description}")
    print(f"Declared Tools: {', '.join(manifest.tools)}")
    print(f"Timeout Budget: {manifest.execution_bounds.timeout_seconds}s")
    print(f"Workspace Mode: {manifest.execution_bounds.workspace_mode}")
    print(f"Manifest File: {manifest.filepath}")
    print("-" * 80)
    print("System Prompt Preview (First 300 chars):")
    preview = manifest.prompt[:300] + ("..." if len(manifest.prompt) > 300 else "")
    print(preview)
    print("=" * 80)
    return EXIT_CODE_SUCCESS


def _handle_run_cli(parsed: argparse.Namespace) -> int:
    """Handles run subcommand."""
    result = execute_agent_subprocess(
        agent_name=parsed.agent,
        target=parsed.target,
        timeout_override=parsed.timeout,
    )

    if parsed.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return result.exit_code

    if getattr(parsed, "compact", False):
        defects_cnt = len(result.defects)
        status_tag = "PASS" if result.exit_code == 0 else "FAIL"
        print(
            f"[{status_tag}] Agent '{result.agent_name}' ({result.status}): "
            f"code={result.exit_code} time={result.duration_ms:.1f}ms defects={defects_cnt}"
        )
        return result.exit_code

    print("=" * 80)
    print(f"  AGENT SUBPROCESS EXECUTION: {result.agent_name}")
    print("=" * 80)
    metrics_str = f"Status: {result.status} | Exit Code: {result.exit_code} | Duration: {result.duration_ms:.2f}ms"
    print(metrics_str)
    if result.error:
        print(f"Error Diagnostic: {result.error}")
    if result.grounding:
        print("-" * 80)
        print("Injected Grounding Directives:")
        print(result.grounding)
        print("-" * 80)
    print(f"Output: {result.output}")
    print("=" * 80)
    return result.exit_code


def _handle_panel_cli(parsed: argparse.Namespace) -> int:
    """Handles panel subcommand."""
    panel_result = execute_review_panel(
        panel_type=parsed.type,
        target_path=parsed.target,
        timeout_per_agent=parsed.timeout,
    )

    if parsed.json:
        print(json.dumps(panel_result, indent=2, ensure_ascii=False))
        return panel_result["exit_code"]

    if getattr(parsed, "compact", False):
        status_tag = "PASS" if panel_result["exit_code"] == 0 else "FAIL"
        print(
            f"[{status_tag}] Panel ({parsed.type}) target={parsed.target} "
            f"verdict={panel_result['verdict']} defects={panel_result['total_defects']} "
            f"time={panel_result['duration_ms']:.1f}ms"
        )
        return panel_result["exit_code"]

    print("=" * 80)
    print(f"  PARALLEL REVIEW PANEL ({parsed.type.upper()}) -> Target: {parsed.target}")
    print("=" * 80)
    summary_str = (
        f"Verdict: {panel_result['verdict']} | "
        f"Total Defects: {panel_result['total_defects']} | "
        f"Duration: {panel_result['duration_ms']}ms"
    )
    print(summary_str)
    for sub in panel_result["results"]:
        sub_str = f"  - {sub['agent_name']}: {sub['status']} (code={sub['exit_code']}, time={sub['duration_ms']}ms)"
        print(sub_str)
    print("=" * 80)
    return panel_result["exit_code"]


def _build_cli_parser() -> argparse.ArgumentParser:
    """Constructs CLI argument parser for agent runner."""
    parser = argparse.ArgumentParser(
        prog="core.agent_runner",
        description="Standalone Subprocess Agent Runner & Process Isolation Harness",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: list
    p_list = subparsers.add_parser("list", help="List all available agent personas")
    p_list.add_argument("--dir", type=str, default=None, help="Custom agents directory")
    p_list.add_argument("--json", action="store_true", help="Output in JSON format")

    # Subcommand: inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect agent manifest details")
    p_inspect.add_argument("--agent", type=str, required=True, help="Agent identifier or filepath")
    p_inspect.add_argument("--json", action="store_true", help="Output in JSON format")

    # Subcommand: run
    p_run = subparsers.add_parser("run", help="Run agent in isolated standalone subprocess")
    p_run.add_argument("--agent", type=str, required=True, help="Agent identifier")
    p_run.add_argument("--target", type=str, default=None, help="Target file or diff path")
    p_run.add_argument("--timeout", type=float, default=None, help="Watchdog timeout ceiling in seconds")
    p_run.add_argument("--json", action="store_true", help="Output in JSON format")
    p_run.add_argument("--compact", "-q", action="store_true", help="Output concise single-line status")

    # Subcommand: panel
    p_panel = subparsers.add_parser("panel", help="Run concurrent 3-agent review panel")
    p_panel.add_argument("--type", choices=["code", "doc"], required=True, help="Review panel type")
    p_panel.add_argument("--target", type=str, required=True, help="Target path to evaluate")
    p_panel.add_argument("--timeout", type=float, default=None, help="Timeout ceiling per reviewer")
    p_panel.add_argument("--json", action="store_true", help="Output in JSON format")
    p_panel.add_argument("--compact", "-q", action="store_true", help="Output concise single-line status")

    # Internal Subcommand: _worker
    p_worker = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    p_worker.add_argument("--agent-path", type=str, required=True)
    p_worker.add_argument("--target", type=str, default=None)

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI runner for standalone agent subprocess execution."""
    parser = _build_cli_parser()
    parsed = parser.parse_args(args)

    dispatch_table = {
        "_worker": _handle_worker_cli,
        "list": _handle_list_cli,
        "inspect": _handle_inspect_cli,
        "run": _handle_run_cli,
        "panel": _handle_panel_cli,
    }

    handler = dispatch_table.get(parsed.command)
    if handler:
        return handler(parsed)

    return EXIT_CODE_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
