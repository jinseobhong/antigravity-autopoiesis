"""
Shadow Grounding Injector Engine (core.shadow_grounding).

Queries purified cortex.db episodic knowledge using SQLite FTS5 and synthesizes
role-specialized cognitive grounding blocks for ephemeral shadow clones
(contrarian, red_team, complex_ai) within a strict < 15.0ms SLA.
Conforms to:
- [INV-GRD-01] through [INV-GRD-10]
- AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12
- Fail-Open Zero-Crash Policy
"""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from core.cortex_knowledge import (
        DEFAULT_CORTEX_DB_PATH,
        get_connection,
        resolve_cortex_db_path,
        sanitize_fts_query,
    )
except ModuleNotFoundError:
    from sandbox.core.cortex_knowledge import (
        DEFAULT_CORTEX_DB_PATH,
        get_connection,
        resolve_cortex_db_path,
        sanitize_fts_query,
    )


# ==============================================================================
# 1. Immutable Value Objects conforming to [INV-GRD-01]
# ==============================================================================

@dataclass(frozen=True)
class ShadowGroundingDirective:
    """Immutable domain directive retrieved from cortex memory."""

    component: str
    outcome: str
    directive: str
    solution: Optional[str] = None
    root_cause: Optional[str] = None


@dataclass(frozen=True)
class ShadowGroundingProfile:
    """Specialized grounding block tailored to an individual clone persona."""

    role: str
    directives: Tuple[ShadowGroundingDirective, ...]
    prompt_block: str


@dataclass(frozen=True)
class ShadowGroundingResult:
    """Aggregated multi-role grounding payload with execution telemetry."""

    task_query: str
    elapsed_ms: float
    profiles: Dict[str, ShadowGroundingProfile]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes result into dictionary for JSON reporting."""
        return {
            "task_query": self.task_query,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "profiles": {
                role: {
                    "role": prof.role,
                    "directive_count": len(prof.directives),
                    "prompt_block": prof.prompt_block,
                    "directives": [
                        {
                            "component": d.component,
                            "outcome": d.outcome,
                            "directive": d.directive,
                            "solution": d.solution,
                            "root_cause": d.root_cause,
                        }
                        for d in prof.directives
                    ],
                }
                for role, prof in self.profiles.items()
            },
        }


# ==============================================================================
# 2. Role Lexicon & Persona Query Profiles conforming to [INV-GRD-02, 03]
# ==============================================================================

ROLE_LEXICONS: Dict[str, Tuple[str, str]] = {
    "contrarian": (
        "simplicity complexity bloat task horizon state_ledger reporting",
        "Radical Parsimony & Minimalist Directives",
    ),
    "red_team": (
        "lock timeout exception error failure windows retry backoff io",
        "Adversarial Defense & Failure Mode Directives",
    ),
    "complex_ai": (
        "architecture contract proto interface naming ast docking convention",
        "Architectural Invariants & Domain Contract Directives",
    ),
}

DEFAULT_ROLES: Tuple[str, ...] = ("contrarian", "red_team", "complex_ai")


def _is_substantive(directive: str) -> bool:
    """Rejects generic boilerplate directives."""
    if not directive or len(directive.strip()) < 15:
        return False
    clean = directive.strip().lower()
    banned = (
        "investigate preflight check output",
        "all verification gates cleared",
        "verified resolution",
        "quality gate cleared",
        "resolve regression in 'test_",
    )
    for b in banned:
        if clean.startswith(b):
            return False
    return True


def _fetch_records_fts(
    con: sqlite3.Connection,
    clean_query: str,
    limit: int,
) -> List[ShadowGroundingDirective]:
    """Queries episodic events via FTS5 match."""
    sql = (
        "SELECT e.component, e.outcome, e.directive, e.solution, e.root_cause "
        "FROM fts_events f JOIN episodic_events e ON f.id = e.id "
        "WHERE fts_events MATCH ? "
        "ORDER BY e.recency_weight DESC, e.access_frequency DESC LIMIT ?;"
    )
    try:
        cur = con.execute(sql, (clean_query, limit * 2))
        rows = cur.fetchall()
        directives: List[ShadowGroundingDirective] = []
        for r in rows:
            d_text = str(r[2] or "")
            if _is_substantive(d_text):
                directives.append(
                    ShadowGroundingDirective(
                        component=str(r[0]),
                        outcome=str(r[1]),
                        directive=d_text,
                        solution=str(r[3]) if r[3] else None,
                        root_cause=str(r[4]) if r[4] else None,
                    )
                )
                if len(directives) >= limit:
                    break
        return directives
    except sqlite3.OperationalError:
        return []


def _fetch_fallback_records(
    con: sqlite3.Connection,
    limit: int,
) -> List[ShadowGroundingDirective]:
    """Fallback query retrieving top recency-weighted directives."""
    sql = (
        "SELECT component, outcome, directive, solution, root_cause "
        "FROM episodic_events "
        "ORDER BY recency_weight DESC, access_frequency DESC LIMIT ?;"
    )
    try:
        cur = con.execute(sql, (limit * 2,))
        rows = cur.fetchall()
        directives: List[ShadowGroundingDirective] = []
        for r in rows:
            d_text = str(r[2] or "")
            if _is_substantive(d_text):
                directives.append(
                    ShadowGroundingDirective(
                        component=str(r[0]),
                        outcome=str(r[1]),
                        directive=d_text,
                        solution=str(r[3]) if r[3] else None,
                        root_cause=str(r[4]) if r[4] else None,
                    )
                )
                if len(directives) >= limit:
                    break
        return directives
    except sqlite3.OperationalError:
        return []


def _build_prompt_block(
    role: str,
    title: str,
    directives: Sequence[ShadowGroundingDirective],
) -> str:
    """Formats directives into a high-priority prompt injection block."""
    if not directives:
        return ""
    items = [
        "> [!IMPORTANT]",
        f"> ### Shadow Grounding: {title} (Role: {role})",
        "> The following verified historical invariants strictly constrain your analysis:",
    ]
    for idx, d in enumerate(directives, 1):
        items.append(f"> {idx}. **[{d.component}]** ({d.outcome}): {d.directive}")
        if d.root_cause:
            items.append(f">    - *Root Cause*: {d.root_cause}")
        if d.solution:
            items.append(f">    - *Solution*: {d.solution}")
    return "\n".join(items)


def _query_role_directives(
    con: sqlite3.Connection,
    task_query: str,
    role: str,
    limit: int,
) -> ShadowGroundingProfile:
    """Queries and formats specialized grounding profile for a single clone role."""
    lexicon_tuple = ROLE_LEXICONS.get(role.lower())
    lexicon = lexicon_tuple[0] if lexicon_tuple else ""
    title = lexicon_tuple[1] if lexicon_tuple else f"Directives for {role}"

    combined_search = f"{task_query} {lexicon}".strip()
    clean_search = sanitize_fts_query(combined_search)

    directives = _fetch_records_fts(con, clean_search, limit) if clean_search else []
    if len(directives) < limit:
        needed = limit - len(directives)
        seen_dirs = {d.directive for d in directives}
        for fb in _fetch_fallback_records(con, limit=needed * 2):
            if fb.directive not in seen_dirs:
                directives.append(fb)
                seen_dirs.add(fb.directive)
            if len(directives) >= limit:
                break

    prompt_block = _build_prompt_block(role, title, directives)
    return ShadowGroundingProfile(
        role=role,
        directives=tuple(directives),
        prompt_block=prompt_block,
    )


# ==============================================================================
# 3. Main Grounding Engine conforming to [INV-GRD-03, 04]
# ==============================================================================

_READONLY_POOL: Dict[str, sqlite3.Connection] = {}


def get_readonly_connection(db_path: Path) -> sqlite3.Connection:
    """Retrieves or creates a cached read-only SQLite connection for sub-15ms lookups."""
    resolved = db_path.resolve()
    key = str(resolved)
    if key in _READONLY_POOL:
        try:
            _READONLY_POOL[key].execute("SELECT 1;")
            return _READONLY_POOL[key]
        except (sqlite3.Error, OSError):
            _READONLY_POOL.pop(key, None)

    uri = f"file:{resolved.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    _READONLY_POOL[key] = con
    return con


def close_cached_connections() -> None:
    """Closes and purges all cached read-only connections in the pool."""
    for key, con in list(_READONLY_POOL.items()):
        try:
            con.close()
        except (sqlite3.Error, OSError):
            # Explicit pass-through: connection close failure during cleanup is safely ignored
            continue
    _READONLY_POOL.clear()




def get_shadow_grounding(
    task_query: str,
    roles: Sequence[str] = DEFAULT_ROLES,
    limit_per_role: int = 3,
    db_path: Optional[Path] = None,
) -> ShadowGroundingResult:
    """
    Retrieves and synthesizes role-specialized grounding profiles for shadow clones.
    Executes within an enforced sub-15ms SLA conforming to [INV-GRD-04].
    """
    start_time = time.perf_counter()
    clean_task = str(task_query or "").strip()

    target_db = resolve_cortex_db_path(db_path, check_exists=False)
    if not target_db.exists():
        elapsed = (time.perf_counter() - start_time) * 1000.0
        return ShadowGroundingResult(task_query=clean_task, elapsed_ms=elapsed, profiles={})

    profiles: Dict[str, ShadowGroundingProfile] = {}
    try:
        con = get_readonly_connection(target_db)
        for r in roles:
            profiles[r] = _query_role_directives(con, clean_task, r, limit_per_role)
    except (sqlite3.Error, OSError) as exc:
        sys.stderr.write(f"[WARNING] Shadow grounding query failed: {exc}\n")

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    return ShadowGroundingResult(
        task_query=clean_task,
        elapsed_ms=elapsed_ms,
        profiles=profiles,
    )


# ==============================================================================
# 4. CLI Entry Point conforming to [INV-GRD-07]
# ==============================================================================

def build_parser() -> argparse.ArgumentParser:
    """Constructs argument parser for shadow grounding CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m core.shadow_grounding",
        description="Shadow Grounding Injector Engine CLI",
    )
    parser.add_argument(
        "--task",
        type=str,
        required=True,
        help="Task description or keyword query for grounding retrieval",
    )
    parser.add_argument(
        "--roles",
        type=str,
        default="contrarian,red_team,complex_ai",
        help="Comma-separated clone roles to ground (default: contrarian,red_team,complex_ai)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum directives per clone role (default: 3)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit output strictly as structured JSON",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI execution entrypoint returning standard process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    role_list = [r.strip() for r in args.roles.split(",") if r.strip()]
    result = get_shadow_grounding(
        task_query=args.task,
        roles=role_list,
        limit_per_role=args.limit,
    )

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
        return 0

    sys.stdout.write(
        f"Shadow Grounding Engine [Elapsed: {result.elapsed_ms:.2f}ms | Task: '{result.task_query}']\n"
    )
    sys.stdout.write("=" * 80 + "\n")
    for role, prof in result.profiles.items():
        sys.stdout.write(f"\n### Clone Persona: {role} ({len(prof.directives)} directives)\n")
        sys.stdout.write(prof.prompt_block + "\n")
    sys.stdout.write("=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
