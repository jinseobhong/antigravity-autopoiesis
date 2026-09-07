"""
Automated Preflight Defect Diagnostics & Cortex Ingestion Engine (core.defect_diagnostics).

Normative reference: CONTRACT-20260907-defect-ingestion / TASK-025.
Categorizes preflight verification gate failures, extracts pinpoint remediation directives,
persists episodic rejection telemetry into cortex.db, and tracks gate clearance resolutions.
"""

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from core.cortex_knowledge import record_event, resolve_cortex_db_path, get_connection
except ModuleNotFoundError:
    from sandbox.core.cortex_knowledge import record_event, resolve_cortex_db_path, get_connection


class DefectCategory(str, Enum):
    """Categorized subsystem domain for preflight verification defects."""

    COMPLIANCE_CHECKER = "compliance_checker"
    FS_TOPOLOGY = "fs_topology"
    TEST_ENGINE = "test_engine"
    GENERAL_PREFLIGHT = "general_preflight"

    # Compatibility aliases for prompt & caller variants
    COMPLIANCE = "compliance_checker"
    TOPOLOGY = "fs_topology"
    TEST_FAILURE = "test_engine"
    TEST_ERROR = "test_engine"
    UNKNOWN = "general_preflight"


def _normalize_category(val: Any) -> DefectCategory:
    """Converts string or enum instance to DefectCategory."""
    if isinstance(val, DefectCategory):
        return val
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("compliance", "compliance_checker"):
            return DefectCategory.COMPLIANCE_CHECKER
        if v in ("topology", "fs_topology"):
            return DefectCategory.FS_TOPOLOGY
        if v in ("test_failure", "test_error", "test_engine"):
            return DefectCategory.TEST_ENGINE
        if v in ("unknown", "general_preflight"):
            return DefectCategory.GENERAL_PREFLIGHT
    return DefectCategory.GENERAL_PREFLIGHT


def _resolve_diagnostic_init_args(
    args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Tuple[DefectCategory, str, str, str, str, str]:
    """Dispatches positional and keyword arguments to canonical field tuple."""
    if len(args) >= 6:
        if isinstance(args[0], (DefectCategory, str)) and args[0] in DefectCategory.__members__.values():
            cat = _normalize_category(args[0])
            return cat, str(args[1]), str(args[2]), str(args[3]), str(args[4]), str(args[5])
        cat = _normalize_category(args[5])
        return cat, str(args[0]), str(args[1]), str(args[2]), str(args[3]), str(args[4])

    cat_raw = kwargs.get("category")
    cat = _normalize_category(cat_raw) if cat_raw is not None else DefectCategory.GENERAL_PREFLIGHT
    comp = str(kwargs.get("component") or "general_preflight")
    trig = str(kwargs.get("trigger_tokens") or "unknown")
    root = str(kwargs.get("root_cause") or "")
    dire = str(kwargs.get("directive") or "")
    raw = str(kwargs.get("raw_diagnostic") or "")
    return cat, comp, trig, root, dire, raw


@dataclass(frozen=True, init=False)
class DefectDiagnostic:
    """Immutable parsed defect representation ready for cortex ingestion."""

    category: DefectCategory
    component: str
    trigger_tokens: str
    root_cause: str
    directive: str
    raw_diagnostic: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Flexible constructor supporting both contract and prompt positional signatures:
        - (category, component, trigger_tokens, root_cause, directive, raw_diagnostic)
        - (component, trigger_tokens, root_cause, directive, raw_diagnostic, category)
        """
        cat, comp, trig, root, dire, raw = _resolve_diagnostic_init_args(args, kwargs)
        object.__setattr__(self, "category", cat)
        object.__setattr__(self, "component", comp)
        object.__setattr__(self, "trigger_tokens", trig)
        object.__setattr__(self, "root_cause", root)
        object.__setattr__(self, "directive", dire)
        object.__setattr__(self, "raw_diagnostic", raw)

    def to_event_payload(self) -> Dict[str, Any]:
        """Serializes defect diagnostic into record_event keyword parameters."""
        return {
            "outcome": "FAILURE",
            "component": self.component,
            "trigger_tokens": self.trigger_tokens,
            "directive": self.directive,
            "root_cause": self.root_cause,
        }


def _compliance_directive(defect_type: str, msg: str) -> str:
    """Formulates actionable remediation directive for compliance defect."""
    if defect_type == "LINE_LENGTH_EXCEEDED":
        return "Refactor line length to <= 120 columns using local variable wrapping."
    if defect_type == "CYCLOMATIC_COMPLEXITY_EXCEEDED":
        return "Decompose function into smaller sub-functions to achieve CC <= 10."
    if defect_type == "MAX_PARAMETERS_EXCEEDED":
        return "Encapsulate excess function arguments into an immutable dataclass DTO."
    if defect_type in ("LAZY_STUB_PASS", "H-CODE-1"):
        return "Replace lazy stub 'pass' with valid production logic or raise exception."
    if defect_type in ("LAZY_STUB_ELLIPSIS",):
        return "Replace placeholder ellipsis '...' with concrete business logic."
    if defect_type in ("TAUTOLOGICAL_ASSERTION", "H-CODE-2"):
        return "Replace tautological assertion with meaningful verification invariant."
    if defect_type == "SYNTAX_ERROR":
        return "Correct Python syntax error at indicated line."
    return f"Remediate static compliance defect [{defect_type}]: {msg}."


def _parse_compliance_diagnostic(diag_line: str) -> Optional[DefectDiagnostic]:
    """Parses a Track A1 static compliance diagnostic line."""
    pattern = r"^\[Compliance\]\s+([^:]+):L(\d+)\s+\[([^\]]+)\]\s*(.*)$"
    match = re.match(pattern, diag_line)
    if not match:
        return None

    path, line_no, defect_type, msg = match.groups()
    directive = _compliance_directive(defect_type, msg)
    root_cause = f"Compliance defect [{defect_type}] at {path}:L{line_no}: {msg}"

    return DefectDiagnostic(
        category=DefectCategory.COMPLIANCE_CHECKER,
        component="compliance_checker",
        trigger_tokens=defect_type,
        root_cause=root_cause,
        directive=directive,
        raw_diagnostic=diag_line,
    )


def _topology_directive(rule_id: str, filepath: str, msg: str) -> str:
    """Formulates actionable remediation directive for topology violation."""
    if rule_id.startswith("R-TOPO"):
        return f"Relocate '{filepath}' to conform to root filesystem boundary rules."
    return f"Remediate filesystem topology violation for '{filepath}': {msg}."


def _parse_topology_diagnostic(diag_line: str) -> Optional[DefectDiagnostic]:
    """Parses a Track A2 filesystem topology diagnostic line."""
    pattern = r"^\[Topology\]\s+\[([^\]]+)\]\s+([^\s\(]+)(?:\s+\(depth=\d+\))?:\s*(.*)$"
    match = re.match(pattern, diag_line)
    if not match:
        return None

    rule_id, filepath, msg = match.groups()
    directive = _topology_directive(rule_id, filepath, msg)
    root_cause = f"Filesystem topology violation [{rule_id}] on '{filepath}': {msg}"

    return DefectDiagnostic(
        category=DefectCategory.FS_TOPOLOGY,
        component="fs_topology",
        trigger_tokens=rule_id,
        root_cause=root_cause,
        directive=directive,
        raw_diagnostic=diag_line,
    )


def _extract_test_trigger(err_msg: str, test_kind: str) -> str:
    """Extracts failure assertion token or error type from message."""
    if ":" in err_msg:
        first_token = err_msg.split(":", 1)[0].strip()
        if first_token:
            return first_token
    if "AssertionError" in err_msg:
        return "AssertionError"
    return "test_failure" if test_kind == "Test Failure" else "test_error"


def _test_directive(test_id: str, err_msg: str) -> str:
    """Formulates actionable remediation directive for test failure."""
    short_err = err_msg.splitlines()[0] if err_msg else "Assertion failure"
    return f"Resolve regression in '{test_id}': {short_err}."


def _parse_test_diagnostic(diag_line: str) -> Optional[DefectDiagnostic]:
    """Parses a Track B regression test failure or error diagnostic line."""
    pattern = r"^\[(Test Failure|Test Error)\]\s+([^:]+):\s*(.*)$"
    match = re.match(pattern, diag_line)
    if not match:
        return None

    test_kind, test_id, err_msg = match.groups()
    trigger_tokens = _extract_test_trigger(err_msg.strip(), test_kind)
    directive = _test_directive(test_id.strip(), err_msg.strip())
    root_cause = f"{test_kind} in {test_id.strip()}: {err_msg.strip()}"

    return DefectDiagnostic(
        category=DefectCategory.TEST_ENGINE,
        component="test_engine",
        trigger_tokens=trigger_tokens,
        root_cause=root_cause,
        directive=directive,
        raw_diagnostic=diag_line,
    )


def _parse_general_diagnostic(diag_line: str) -> DefectDiagnostic:
    """Constructs default DefectDiagnostic for unclassified strings."""
    clean_line = diag_line.strip()
    return DefectDiagnostic(
        category=DefectCategory.GENERAL_PREFLIGHT,
        component="general_preflight",
        trigger_tokens="general_preflight_defect",
        root_cause=f"Unclassified preflight diagnostic: {clean_line}",
        directive="Investigate preflight check output and resolve reported defect.",
        raw_diagnostic=clean_line,
    )


def parse_diagnostic_string(diag_line: str) -> DefectDiagnostic:
    """Parses a single preflight diagnostic string into a structured DefectDiagnostic."""
    line = diag_line.strip()
    if line.startswith("[Compliance]"):
        comp_diag = _parse_compliance_diagnostic(line)
        if comp_diag is not None:
            return comp_diag
    elif line.startswith("[Topology]"):
        topo_diag = _parse_topology_diagnostic(line)
        if topo_diag is not None:
            return topo_diag
    elif line.startswith(("[Test Failure]", "[Test Error]")):
        test_diag = _parse_test_diagnostic(line)
        if test_diag is not None:
            return test_diag
    return _parse_general_diagnostic(line)


def categorize_preflight_diagnostics(
    diagnostics: List[str],
) -> List[DefectDiagnostic]:
    """Classifies raw preflight diagnostics into categorized DefectDiagnostic objects."""
    results: List[DefectDiagnostic] = []
    for diag in diagnostics:
        clean = diag.strip()
        if clean:
            results.append(parse_diagnostic_string(clean))
    return results


# Public alias satisfying prompt requirement
diagnose_defects = categorize_preflight_diagnostics


def _is_valid_sqlite_file(db_path: Path) -> bool:
    """Checks whether existing file has a valid SQLite 3 header."""
    try:
        p = Path(db_path)
        if not p.exists() or p.stat().st_size == 0:
            return True
        with open(p, "rb") as f:
            header = f.read(16)
            return header == b"SQLite format 3\x00"
    except OSError:
        return False


def ingest_preflight_defects(
    diagnostics: List[str],
    db_path: Optional[Path] = None,
    no_telemetry: bool = False,
    spool_path: Optional[Path] = None,
) -> int:
    """
    Ingests categorized preflight defects into cortex.db via record_event.
    Returns the count of successfully recorded defect events.
    Fails open without raising exceptions if database access fails.
    """
    if no_telemetry or not diagnostics:
        return 0

    target_db = resolve_cortex_db_path(db_path, check_exists=False)
    if not _is_valid_sqlite_file(target_db):
        sys.stderr.write(f"[WARNING] Cortex DB file '{target_db}' is corrupted.\n")
        return 0

    parsed_diagnostics = categorize_preflight_diagnostics(diagnostics)
    recorded_count = 0

    for defect in parsed_diagnostics:
        if not is_substantive_directive(defect.directive, defect.root_cause):
            continue
        try:
            record_event(
                outcome="FAILURE",
                component=defect.component,
                trigger_tokens=defect.trigger_tokens,
                directive=defect.directive,
                root_cause=defect.root_cause,
                db_path=target_db,
                spool_path=spool_path,
            )
            recorded_count += 1
        except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
            sys.stderr.write(f"[WARNING] Ingesting defect telemetry failed: {exc}\n")

    return recorded_count


def is_substantive_directive(
    directive: Optional[str], root_cause: Optional[str] = None
) -> bool:
    """Evaluates whether a directive contains actionable, non-boilerplate guidance."""
    if not directive or len(directive.strip()) < 15:
        return False
    clean = directive.strip().lower()
    banned_prefixes = (
        "investigate preflight check output",
        "all verification gates cleared",
        "verified resolution",
        "quality gate cleared",
        "resolve regression in 'test_",
    )
    for pfx in banned_prefixes:
        if clean.startswith(pfx):
            return False
    return True


def _is_boilerplate_note(note: str) -> bool:
    """Checks if resolution note is an empty or generic placeholder string."""
    if not note:
        return True
    cleaned = note.strip().lower()
    return cleaned in (
        "",
        "verified resolution.",
        "verified resolution",
        "all verification gates cleared.",
        "all verification gates cleared",
        "quality gate cleared in subsequent preflight run.",
        "quality gate cleared in subsequent preflight run",
    )


_COMPLIANCE_PATTERNS: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "CYCLOMATIC",
        "complexity",
        "Resolved cyclomatic complexity violation by decomposing logic into "
        "single-responsibility helpers.",
        "Maintain function CC <= 10 and Single Level of Abstraction.",
    ),
    (
        "LINE_LENGTH",
        "line length",
        "Resolved line length violation by refactoring statements into concise local "
        "bindings.",
        "Maintain line length <= 100 columns using local variable wrapping.",
    ),
    (
        "MAX_PARAMETERS",
        "parameter",
        "Resolved excess parameter count violation by encapsulating arguments into an "
        "immutable dataclass DTO.",
        "Keep function parameter count <= 4 (max 7); encapsulate larger parameter sets into "
        "typed DTOs.",
    ),
    (
        "LAZY_STUB",
        "lazy stub",
        "Eliminated lazy stub placeholder by implementing robust production logic and error "
        "handling.",
        "Prohibit lazy stubs ('pass', '...'); implement production logic or raise explicit "
        "domain exceptions.",
    ),
    (
        "H-CODE-1",
        "h-code-1",
        "Eliminated lazy stub placeholder by implementing robust production logic and error "
        "handling.",
        "Prohibit lazy stubs ('pass', '...'); implement production logic or raise explicit "
        "domain exceptions.",
    ),
    (
        "TAUTOLOGICAL",
        "tautological",
        "Eliminated tautological assertion by replacing with substantive domain invariant checks.",
        "Verify meaningful domain invariants; prohibit tautological assertions.",
    ),
    (
        "H-CODE-2",
        "h-code-2",
        "Eliminated tautological assertion by replacing with substantive domain invariant checks.",
        "Verify meaningful domain invariants; prohibit tautological assertions.",
    ),
    (
        "SYNTAX_ERROR",
        "syntax",
        "Corrected syntax defect and verified clean AST compilation.",
        "Validate syntax and AST validity via preflight compliance checks prior to "
        "gate submission.",
    ),
)

_TOPOLOGY_PATTERNS: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "H-TOPO-1",
        "root",
        "Resolved root directory pollution by relocating artifacts to authorized paths.",
        "Maintain strict filesystem topology boundary; prohibit untracked or scratch files in "
        "repository root.",
    ),
    (
        "H-TOPO-2",
        "orphan",
        "Resolved orphaned filesystem artifacts by integrating or removing unlinked files.",
        "Ensure all repository files are referenced in architecture specifications and module "
        "graphs.",
    ),
    (
        "H-TOPO-3",
        "depth",
        "Restructured directory hierarchy to conform to maximum depth limits.",
        "Enforce directory nesting depth <= 4 levels to maintain discoverability and clean layout.",
    ),
)

_TEST_PATTERNS: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "ASSERTIONERROR",
        "assertionerror",
        "Resolved test assertion failure by aligning implementation with contract invariants.",
        "Maintain 100% test pass rate and verify behavior against contract specifications.",
    ),
    (
        "OPERATIONALERROR",
        "operationalerror",
        "Resolved database concurrency contention by adding retry backoff and deterministic "
        "cleanup.",
        "Use bounded retry loops with jitter and ensure SQLite connections are closed in "
        "finally blocks.",
    ),
    (
        "SQLITE3",
        "sqlite3",
        "Resolved database concurrency contention by adding retry backoff and deterministic "
        "cleanup.",
        "Use bounded retry loops with jitter and ensure SQLite connections are closed in "
        "finally blocks.",
    ),
    (
        "LOCK",
        "locked",
        "Resolved database concurrency contention by adding retry backoff and deterministic "
        "cleanup.",
        "Use bounded retry loops with jitter and ensure SQLite connections are closed in "
        "finally blocks.",
    ),
)


def _synthesize_compliance_lesson(
    trigger_tokens: str, root_cause: str, prior_directive: str
) -> Tuple[str, str]:
    """Synthesizes resolution solution and directive for compliance defects."""
    combined = f"{trigger_tokens} {root_cause}".lower()
    for token_kw, root_kw, base, directive in _COMPLIANCE_PATTERNS:
        if token_kw.lower() in combined or root_kw in combined:
            return base, directive

    base = (
        f"Remediated static compliance defect [{trigger_tokens}] satisfying rule requirements."
    )
    fallback_dir = f"Strictly enforce compliance rule [{trigger_tokens}] across codebase."
    directive = prior_directive.strip() or fallback_dir
    return base, directive


def _synthesize_topology_lesson(
    trigger_tokens: str, root_cause: str, prior_directive: str
) -> Tuple[str, str]:
    """Synthesizes resolution solution and directive for topology defects."""
    combined = f"{trigger_tokens} {root_cause}".lower()
    for token_kw, root_kw, base, directive in _TOPOLOGY_PATTERNS:
        if token_kw.lower() in combined or root_kw in combined:
            return base, directive

    base = f"Resolved filesystem topology violation [{trigger_tokens}]."
    fallback_dir = (
        f"Conform to repository topology rules and boundary constraints [{trigger_tokens}]."
    )
    directive = prior_directive.strip() or fallback_dir
    return base, directive


def _synthesize_test_lesson(
    trigger_tokens: str, root_cause: str, prior_directive: str
) -> Tuple[str, str]:
    """Synthesizes resolution solution and directive for test engine defects."""
    combined = f"{trigger_tokens} {root_cause}".lower()
    for token_kw, root_kw, base, directive in _TEST_PATTERNS:
        if token_kw.lower() in combined or root_kw in combined:
            return base, directive

    base = f"Resolved test failure [{trigger_tokens}] in test engine execution."
    fallback_dir = "Ensure all regression and boundary test suites pass deterministically."
    directive = prior_directive.strip() or fallback_dir
    return base, directive


def _synthesize_resolution_lesson(
    component: str,
    trigger_tokens: str,
    root_cause: Optional[str],
    prior_directive: Optional[str],
    note: str,
) -> Tuple[str, str]:
    """
    Synthesizes substantive solution and actionable directive lesson learned
    combining root cause, trigger tokens, and resolution evidence note.
    """
    root_str = str(root_cause or "")
    prior_dir_str = str(prior_directive or "")

    if component == "compliance_checker":
        base_fix, rule = _synthesize_compliance_lesson(trigger_tokens, root_str, prior_dir_str)
    elif component == "fs_topology":
        base_fix, rule = _synthesize_topology_lesson(trigger_tokens, root_str, prior_dir_str)
    elif component == "test_engine":
        base_fix, rule = _synthesize_test_lesson(trigger_tokens, root_str, prior_dir_str)
    else:
        base_fix = f"Resolved preflight defect [{trigger_tokens}] for component '{component}'."
        rule = (
            prior_dir_str.strip()
            if prior_dir_str.strip()
            else f"Maintain preflight verification gate clearance for '{component}'."
        )

    clean_base = base_fix.rstrip(".")
    if not _is_boilerplate_note(note):
        evidence = note.strip().rstrip(".")
        solution = f"{clean_base}. Evidence: {evidence}."
        directive = f"{clean_base} (Evidence: {evidence}). Directive: {rule}"
    else:
        solution = f"{clean_base}."
        directive = f"{clean_base}. Directive: {rule}"

    return solution, directive


def _fetch_unresolved_failure(
    target_db: Path, component: str
) -> Optional[Dict[str, Any]]:
    """Checks cortex.db for an unresolved recent FAILURE event for component."""
    if not target_db.exists():
        return None
    try:
        con = get_connection(target_db)
        try:
            cur = con.execute(
                """
                SELECT outcome, trigger_tokens, directive, root_cause
                FROM episodic_events
                WHERE component = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1;
                """,
                (component,),
            )
            row = cur.fetchone()
            if row and row["outcome"] == "FAILURE":
                return {
                    "trigger_tokens": row["trigger_tokens"],
                    "directive": row["directive"],
                    "root_cause": row["root_cause"],
                }
            return None
        finally:
            con.close()
    except (OSError, sqlite3.Error) as exc:
        sys.stderr.write(f"[WARNING] Querying failure resolution state failed: {exc}\n")
        return None


def _record_single_resolution(
    comp: str,
    note: str,
    prior_failure: Dict[str, Any],
    db_path: Optional[Path],
) -> bool:
    """Dispatches a SUCCESS event with substantive lesson to mark prior failure resolved."""
    if not prior_failure:
        return False
    try:
        trig = str(prior_failure.get("trigger_tokens") or "preflight_clearance")
        root = prior_failure.get("root_cause")
        prior_dir = prior_failure.get("directive")
        solution, directive = _synthesize_resolution_lesson(
            comp, trig, root, prior_dir, note
        )
        record_event(
            outcome="SUCCESS",
            component=comp,
            trigger_tokens=trig,
            directive=directive,
            root_cause=root,
            solution=solution,
            db_path=db_path,
        )
        return True
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        sys.stderr.write(f"[WARNING] Recording preflight resolution failed: {exc}\n")
        return False


def _normalize_resolution_args(
    cleared: Optional[Union[str, List[str]]],
    note_or_path: Optional[Union[str, Path]],
    db_path: Optional[Path],
    kw_comp: Optional[str],
) -> Tuple[List[str], str, Optional[Path], bool]:
    """Normalizes polymorphic resolution arguments into standard fields."""
    if kw_comp is not None:
        note_str = str(note_or_path) if isinstance(note_or_path, str) else "Verified resolution."
        return [kw_comp], note_str, db_path, True

    if isinstance(cleared, str):
        note_str = str(note_or_path) if isinstance(note_or_path, str) else "Verified resolution."
        return [cleared], note_str, db_path, True

    actual_db = note_or_path if isinstance(note_or_path, Path) else db_path
    note_str = note_or_path if isinstance(note_or_path, str) else "All verification gates cleared."
    comp_list = list(cleared) if cleared is not None else ["compliance_checker", "fs_topology", "test_engine"]
    return comp_list, note_str, actual_db, False


def _resolve_component_failures(
    target_comps: List[str],
    note: str,
    target_db: Path,
) -> int:
    """Iterates target components and resolves prior failures in cortex.db."""
    resolved_count = 0
    for comp in target_comps:
        prior = _fetch_unresolved_failure(target_db, comp)
        if prior is not None:
            if _record_single_resolution(comp, note, prior, target_db):
                resolved_count += 1
    return resolved_count


def record_preflight_resolution(
    cleared_components: Optional[Union[str, List[str]]] = None,
    resolution_note: Optional[Union[str, Path]] = None,
    db_path: Optional[Path] = None,
    no_telemetry: bool = False,
    *,
    component: Optional[str] = None,
    **kwargs: Any,
) -> Union[int, bool]:
    """
    Records resolution events (outcome='SUCCESS') ONLY for components with prior failures.
    Supports both single component (returns bool) and component list (returns int count).
    """
    is_single = component is not None or isinstance(cleared_components, str)
    if no_telemetry:
        return False if is_single else 0

    target_comps, actual_note, actual_db, _ = _normalize_resolution_args(
        cleared_components, resolution_note, db_path, component
    )
    resolved_target_db = resolve_cortex_db_path(actual_db, check_exists=False)
    if not _is_valid_sqlite_file(resolved_target_db):
        return False if is_single else 0

    resolved_count = _resolve_component_failures(
        target_comps, actual_note, resolved_target_db
    )

    if is_single:
        return resolved_count > 0
    return resolved_count
