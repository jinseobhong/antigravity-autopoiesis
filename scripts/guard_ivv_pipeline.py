"""
Automated IV&V Lifecycle Enforcement Hook (scripts.guard_ivv_pipeline).

PreToolUse hook interceptor enforcing Decoupled Independent Verification and Validation.
Blocks primary orchestrator from direct code/test mutation and isolates software-engineer
and qa-engineer file authoring domains conforming to CONTRACT-20260907.
"""

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure repository root is in sys.path for direct execution from any CWD
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_ROOTS = [
    os.path.abspath(os.path.join(_SCRIPT_DIR, "..")),
    os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..")),
]
for root in _CANDIDATE_ROOTS:
    if root not in sys.path:
        sys.path.insert(0, root)

try:
    from scripts.validate_active_contract import validate_contract_state
except ModuleNotFoundError:
    from sandbox.scripts.validate_active_contract import validate_contract_state


def _normalize_path(target_file: str, workspace_paths: Optional[List[str]] = None) -> str:
    """Normalizes target path to forward-slash relative path."""
    p = Path(target_file)
    norm = p.as_posix()
    if workspace_paths:
        for ws in workspace_paths:
            ws_norm = Path(ws).as_posix()
            if norm.startswith(ws_norm):
                norm = norm[len(ws_norm):].lstrip("/")
    if ":" in norm:
        norm = norm.split(":")[-1].lstrip("/\\")
    return norm.replace("\\", "/").lstrip("/")


def _parse_role_from_content(content: str) -> str:
    """Extracts agent role from prompt content string."""
    if "--caller-id:" not in content:
        return "orchestrator"
    lower = content.lower()
    if "qa-engineer" in lower or "qa engineer" in lower:
        return "qa-engineer"
    if "software-engineer" in lower or "software engineer" in lower:
        return "software-engineer"
    return "subagent"


def _read_first_transcript_step(path: Path) -> Optional[Dict[str, Any]]:
    """Reads and parses first step from transcript file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            return json.loads(first_line) if first_line else None
    except (OSError, json.JSONDecodeError):
        return None


def _detect_caller_role(transcript_path: Optional[str]) -> str:
    """Detects caller role from transcript initial step."""
    if not transcript_path:
        return "orchestrator"
    p = Path(transcript_path)
    if not p.exists() or not p.is_file():
        return "orchestrator"
    step = _read_first_transcript_step(p)
    if not step:
        return "orchestrator"
    return _parse_role_from_content(step.get("content", ""))


def _check_orchestrator_policy(rel_path: str) -> Tuple[str, Optional[str]]:
    """
    Enforces strict Conductor-only discipline.
    Orchestrator is strictly prohibited from authoring ANY Python code or scripts.
    Only documentation and contracts in docs/ are permitted.
    """
    is_code_file = rel_path.endswith(".py")
    is_code_tree = rel_path.startswith(("core/", "tests/", "scripts/", "sandbox/"))

    if is_code_file or is_code_tree:
        reason = (
            f"[IV&V HOOK BLOCKED] Primary Orchestrator is restricted from direct code authoring on '{rel_path}'. "
            f"You are the Conductor, not a manual worker. You MUST dispatch 'software-engineer' or 'qa-engineer' "
            f"via invoke_subagent."
        )
        return "deny", reason

    return "allow", None


def _is_qa_prohibited_path(rel_path: str, is_core: bool) -> bool:
    """Checks if target path is prohibited for qa-engineer authoring."""
    return is_core or rel_path.startswith("scripts/")


def _is_contract_enforced_path(rel_path: str, is_core: bool, is_test: bool) -> bool:
    """Checks if target path requires an active contract before mutation."""
    return is_test or _is_qa_prohibited_path(rel_path, is_core)


def _check_role_domain_isolation(
    role: str, rel_path: str, is_core: bool, is_test: bool
) -> Tuple[str, Optional[str]]:
    """Enforces domain isolation between software-engineer and qa-engineer."""
    if role == "software-engineer" and is_test:
        reason = (
            f"[IV&V HOOK BLOCKED] software-engineer is restricted from authoring tests on '{rel_path}'. "
            f"Adversarial tests must be synthesized independently by qa-engineer."
        )
        return "deny", reason

    if role == "qa-engineer" and _is_qa_prohibited_path(rel_path, is_core):
        reason = (
            f"[IV&V HOOK BLOCKED] qa-engineer is restricted from authoring implementation code on '{rel_path}'. "
            f"Business logic must be authored by software-engineer."
        )
        return "deny", reason

    return "allow", None


def _check_contract_requirement(
    role: str, rel_path: str, is_core: bool, is_test: bool
) -> Tuple[str, Optional[str]]:
    """Enforces active contract prerequisite for subagent code mutations."""
    if role not in ("software-engineer", "qa-engineer"):
        return "allow", None

    if not _is_contract_enforced_path(rel_path, is_core, is_test):
        return "allow", None

    valid, contract_err = validate_contract_state()
    if not valid:
        reason = (
            f"[CONTRACT_GATE_BLOCKED] Subagent '{role}' cannot mutate '{rel_path}': {contract_err}. "
            f"You MUST establish an ACCEPTED contract in docs/active/ACTIVE_CONTRACT.md before implementation."
        )
        return "deny", reason

    return "allow", None


def _check_subagent_policy(
    role: str, rel_path: str, is_core: bool, is_test: bool
) -> Tuple[str, Optional[str]]:
    """Enforces software-engineer vs qa-engineer separation and contract prerequisite."""
    decision, reason = _check_role_domain_isolation(role, rel_path, is_core, is_test)
    if decision != "allow":
        return decision, reason

    return _check_contract_requirement(role, rel_path, is_core, is_test)


def evaluate_tool_call(payload: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Evaluates PreToolUse payload against IV&V access control rules."""
    if os.environ.get("IVV_BYPASS") == "1":
        return "allow", None

    tool_call = payload.get("toolCall", {})
    if tool_call.get("name") not in ("write_to_file", "replace_file_content"):
        return "allow", None

    args = tool_call.get("args", {})
    target_raw = args.get("TargetFile") or args.get("target_file") or ""
    if not target_raw:
        return "allow", None

    rel_path = _normalize_path(target_raw, payload.get("workspacePaths", []))
    role = _detect_caller_role(payload.get("transcriptPath"))

    if role == "orchestrator":
        return _check_orchestrator_policy(rel_path)

    is_core = rel_path.startswith("core/") or rel_path.startswith("sandbox/core/")
    is_test = rel_path.startswith("tests/") or rel_path.startswith("sandbox/tests/")

    return _check_subagent_policy(role, rel_path, is_core, is_test)


def main() -> int:
    """CLI entrypoint reading stdin JSON payload and outputting decision."""
    try:
        raw_input = sys.stdin.read().strip()
        payload = json.loads(raw_input, strict=False) if raw_input else {}
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"decision": "allow", "reason": f"Input parse error: {e}"}))
        return 0

    decision, reason = evaluate_tool_call(payload)
    output: Dict[str, Any] = {"decision": decision}
    if reason:
        output["reason"] = reason

    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
