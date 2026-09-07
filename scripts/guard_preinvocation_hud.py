"""PreInvocation Lifecycle Hook Guard for 4-Layer Cognitive HUD Telemetry Injection.

Fires before model invocations, updates COGNITIVE_HUD.html across repository and artifact
directories, and injects real-time L0-L3 telemetry and <agent-embed> directly into context.
"""

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.cognitive_hud import CognitiveHudExtractor
from core.interfaces.cognitive_hud_proto import CognitiveHudSnapshot


@dataclass(frozen=True)
class PreInvocationHudResult:
    """Immutable result of PreInvocation HUD processing."""

    success: bool
    hud_path: str
    beacon: str
    active_tasks: int
    working_tree_clean: bool
    injected_message: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return asdict(self)


def _resolve_repo_root(payload: Dict[str, Any]) -> Path:
    """Resolve repository root from payload or fallback."""
    ws_paths = payload.get("workspacePaths")
    if ws_paths and isinstance(ws_paths, list) and len(ws_paths) > 0:
        candidate = Path(ws_paths[0]).resolve()
        if candidate.exists():
            return candidate
    return REPO_ROOT


def _resolve_artifact_dir(payload: Dict[str, Any], repo_root: Path) -> Path:
    """Resolve target artifact directory for COGNITIVE_HUD.html."""
    art_path = payload.get("artifactDirectoryPath")
    if art_path and isinstance(art_path, str):
        candidate = Path(art_path).resolve()
        if candidate.exists():
            return candidate

    conv_id = payload.get("conversationId")
    if conv_id and isinstance(conv_id, str):
        app_data = Path.home() / ".gemini" / "antigravity" / "brain" / conv_id
        if app_data.exists():
            return app_data

    return repo_root / "docs" / "active"


def _format_ephemeral_message(snapshot: CognitiveHudSnapshot, hud_file_path: Path) -> str:
    """Format concise ephemeral status message for context injection."""
    l0 = snapshot.l0
    l1 = snapshot.l1
    l3 = snapshot.l3
    tree_status = "Clean" if l0.working_tree_clean else "Uncommitted Changes"
    hook_status = "Armed" if l0.stop_hook_ready else "Intercepting"
    norm_path = hud_file_path.as_posix()

    lines = [
        "[4-Layer Cognitive HUD PreInvocation Sync]",
        f"- L0 Beacon: {l0.viability_beacon} | Active Tasks: {l0.active_task_count}/{l0.max_active_tasks}",
        f"- Working Tree: {tree_status} | Stop Hook: {hook_status}",
        f"- Last Commit: {l0.last_commit_sha} ({l0.last_commit_message})",
        f"- Cognitive Burden: {l1.cognitive_burden_score}/10 | Tests Passed: {l3.total_tests_passed}",
        f"- Live HUD: file:///{norm_path}",
        f'<agent-embed src="file:///{norm_path}"></agent-embed>',
    ]
    return "\n".join(lines)


def process_preinvocation(
    payload: Dict[str, Any],
    extractor: Optional[CognitiveHudExtractor] = None,
) -> Tuple[Dict[str, Any], PreInvocationHudResult]:
    """Execute PreInvocation telemetry extraction and formulate injectSteps payload."""
    repo_root = _resolve_repo_root(payload)
    artifact_dir = _resolve_artifact_dir(payload, repo_root)

    if extractor is None:
        extractor = CognitiveHudExtractor()

    snapshot = extractor.extract_snapshot(repo_root)
    html_source = extractor.render_html(snapshot)

    # Write live HUD HTML strictly to conversation artifact directory to prevent dirtying git tree
    doc_hud = repo_root / "docs" / "active" / "COGNITIVE_HUD.html"
    target_hud = doc_hud
    if artifact_dir.resolve() != doc_hud.parent.resolve():
        art_hud = artifact_dir / "COGNITIVE_HUD.html"
        try:
            art_hud.parent.mkdir(parents=True, exist_ok=True)
            art_hud.write_text(html_source, encoding="utf-8")
            target_hud = art_hud
        except OSError:
            # Fallback to doc_hud if artifact directory cannot be written
            target_hud = doc_hud
    elif not doc_hud.exists():
        try:
            doc_hud.parent.mkdir(parents=True, exist_ok=True)
            doc_hud.write_text(html_source, encoding="utf-8")
        except OSError:
            # Gracefully handle write errors under fail-open isolation
            sys.stderr.write("[preinvocation-hud-guard] Warning: Unable to write doc_hud\n")

    msg = _format_ephemeral_message(snapshot, target_hud)

    inject_payload = {
        "injectSteps": [
            {
                "ephemeralMessage": msg,
            }
        ]
    }

    result = PreInvocationHudResult(
        success=True,
        hud_path=str(target_hud),
        beacon=snapshot.l0.viability_beacon,
        active_tasks=snapshot.l0.active_task_count,
        working_tree_clean=snapshot.l0.working_tree_clean,
        injected_message=msg,
    )
    return inject_payload, result


def main(argv: Optional[List[str]] = None) -> int:
    """CLI and Hook entrypoint for PreInvocation telemetry injection."""
    parser = argparse.ArgumentParser(description="PreInvocation 4-Layer Cognitive HUD Hook.")
    parser.add_argument("--check-only", action="store_true", help="Dry run test without stdin.")
    parser.add_argument("--json", action="store_true", help="Output debug JSON.")
    args = parser.parse_args(argv)

    payload: Dict[str, Any] = {}
    if not args.check_only:
        try:
            if not sys.stdin.isatty():
                raw = sys.stdin.read().strip()
                if raw:
                    payload = json.loads(raw)
        except Exception:
            payload = {}

    try:
        inject_payload, result = process_preinvocation(payload)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(json.dumps(inject_payload))
        return 0
    except Exception as err:
        # Strict fail-open resilience: never crash or block agent startup
        sys.stderr.write(f"[preinvocation-hud-guard] Warning fail-open: {err}\n")
        print(json.dumps({}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
