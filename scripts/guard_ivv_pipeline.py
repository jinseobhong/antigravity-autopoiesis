"""
Sovereign Orchestrator & Read-Only Subagent Guard Hook (scripts.guard_ivv_pipeline).

PreToolUse hook interceptor enforcing Sovereign Authoring Architecture:
- Primary Orchestrator is the sole authorized writer for all files (code, tests, docs).
- All subagents operate strictly in read-only review/auditing mode and cannot mutate files directly.
"""

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple


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
    for candidate in (
        "software-engineer",
        "qa-engineer",
        "technical-writer",
        "socratic-interviewer",
        "autopoiesist-founder",
        "autopoiesist-cpo",
        "autopoiesist-architect",
        "autopoiesist-dx-lead",
        "autopoiesist-red-team",
        "autopoiesist-complex-ai",
        "autopoiesist-sre",
        "autopoiesist-contrarian",
        "autopoiesist-token-economist",
    ):
        if candidate in lower:
            return candidate
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


def evaluate_tool_call(payload: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Evaluates PreToolUse payload against Sovereign Authoring rules."""
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
        # Sovereign Orchestrator has full direct authoring authority
        return "allow", None

    # Subagents are strictly read-only reviewers/analysts
    reason = (
        f"[READ_ONLY_SUBAGENT_BLOCKED] Subagent '{role}' is restricted to read-only review and analysis. "
        f"Direct file mutation on '{rel_path}' is prohibited. "
        f"All code and test authoring must be performed directly by the Primary Orchestrator."
    )
    return "deny", reason


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
