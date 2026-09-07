"""
Project Filesystem Topology Standards and Compliance Engine (core.fs_topology).

Enforces canonical repository structure, visibility boundaries, depth ceilings,
semantic naming conventions, and dynamic runtime persistence provisioning.
Conforms to CONTRACT-20260907-filesystem-topology-standards.
"""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


# ==============================================================================
# 1. Normative Constants and Canonical Paths (The NASA Lexicon)
# ==============================================================================

@dataclass(frozen=True)
class CanonicalPaths:
    """Canonical repository path definitions."""

    CORE: Path = Path("core")
    DOCS_ACTIVE: Path = Path("docs/active")
    DOCS_ARCHIVED: Path = Path("docs/archived")
    DOCS_RULES: Path = Path("docs/rules")
    DOCS_SPECS: Path = Path("docs/specs")
    DATA: Path = Path("data")
    DATA_CORTEX_DB: Path = Path("data/cortex.db")
    DATA_MEMORY_DB: Path = Path("data/memory.db")
    DATA_DOCUMENT_DB: Path = Path("data/document.db")
    DATA_MEMORY_SEED: Path = Path("data/memory_seed.jsonl")
    DATA_SPOOL: Path = Path("data/spool")
    DATA_CACHE: Path = Path("data/cache")
    SCRIPTS: Path = Path("scripts")
    TESTS: Path = Path("tests")
    SANDBOX: Path = Path("sandbox")
    AGENTS: Path = Path(".agents/agents")
    SKILLS: Path = Path(".agents/skills")
    LEGACY_CORTEX_DB: Path = Path(".agents/knowledge/cortex.db")


AUTHORIZED_ROOT_DIRS: Set[str] = {
    "core",
    "docs",
    "data",
    "scripts",
    "tests",
    "sandbox",
    ".agents",
}

# Standard system and development tool directories ignored by root whitelist checks
ALLOWED_SYSTEM_DIRS: Set[str] = {
    ".git",
    ".gemini",
    ".vscode",
    ".idea",
    ".pytest_cache",
    "__pycache__",
    "venv",
    ".venv",
}

AUTHORIZED_DOCS_DOMAINS: Set[str] = {
    "active",
    "archived",
    "rules",
    "specs",
}

BANNED_DIRECTORY_TOKENS: Set[str] = {
    "common",
    "utils",
    "misc",
    "helpers",
    "shared",
    "temp",
}

MAX_DIRECTORY_DEPTH: int = 4


# ==============================================================================
# 2. Typed Data Models
# ==============================================================================

@dataclass(frozen=True)
class PathViolation:
    """Details of a single filesystem invariant violation."""

    filepath: str
    rule_id: str
    depth: int
    message: str

    def to_dict(self) -> Dict[str, Any]:
        """Serializes violation to dictionary."""
        return {
            "filepath": self.filepath,
            "rule_id": self.rule_id,
            "depth": self.depth,
            "message": self.message,
        }


@dataclass(frozen=True)
class TopologyAuditResult:
    """Aggregate result of a filesystem topology compliance audit."""

    passed: bool
    scanned_count: int
    duration_ms: float
    violations: List[PathViolation]


# ==============================================================================
# 3. Path Convention and Topology Verifiers
# ==============================================================================

def _check_directory_depth(path_str: str, depth: int) -> List[PathViolation]:
    """Validates directory nesting depth ceiling [INV-FS-22]."""
    if depth > MAX_DIRECTORY_DEPTH:
        return [
            PathViolation(
                filepath=path_str,
                rule_id="INV-FS-22",
                depth=depth,
                message=f"Directory nesting depth {depth} exceeds strict ceiling of {MAX_DIRECTORY_DEPTH}",
            )
        ]
    return []


def _check_directory_banned_tokens(
    path_str: str, dir_parts: Sequence[str], depth: int
) -> List[PathViolation]:
    """Checks banned generic tokens in directory hierarchy [INV-FS-17]."""
    violations: List[PathViolation] = []
    for part in dir_parts:
        lower_part = part.lower()
        for banned in BANNED_DIRECTORY_TOKENS:
            is_match = (
                lower_part == banned
                or lower_part.startswith(f"{banned}_")
                or lower_part.endswith(f"_{banned}")
            )
            if is_match:
                violations.append(
                    PathViolation(
                        filepath=path_str,
                        rule_id="INV-FS-17",
                        depth=depth,
                        message=f"Path segment '{part}' contains banned generic token '{banned}'",
                    )
                )
                break
    return violations


def _check_python_filename(path_str: str, norm_path: Path, depth: int) -> List[PathViolation]:
    """Validates Python module naming rules [INV-FS-18, INV-FS-19]."""
    filename = norm_path.name
    if filename in ("__init__.py", "__main__.py", "conftest.py"):
        return []

    parent_str = str(norm_path.parent).replace("\\", "/")
    is_script = parent_str == "scripts" or parent_str.startswith("scripts/")
    if not re.match(r"^[a-z][a-z0-9_]*\.py$", filename):
        rule_id = "INV-FS-19" if is_script else "INV-FS-18"
        msg = (
            f"Script '{filename}' must use lower_snake_case with action or verb semantics"
            if is_script
            else f"Python module '{filename}' must use lower_snake_case"
        )
        return [PathViolation(filepath=path_str, rule_id=rule_id, depth=depth, message=msg)]
    return []


def _check_markdown_filename(path_str: str, norm_path: Path, depth: int) -> List[PathViolation]:
    """Validates Markdown specification naming rules [INV-FS-20, INV-FS-21]."""
    filename = norm_path.name
    stem = norm_path.stem
    parent_str = str(norm_path.parent).replace("\\", "/")

    if parent_str.startswith(".agents"):
        is_persona = filename not in ("README.md", "SKILL.md")
        is_kebab = bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$", filename))
        if is_persona and not is_kebab:
            return [
                PathViolation(
                    filepath=path_str,
                    rule_id="INV-FS-21",
                    depth=depth,
                    message=f"Agent persona or skill document '{filename}' must use kebab-case.md",
                )
            ]
        return []

    if parent_str in (".", "docs") or parent_str.startswith("docs/"):
        clean_stem = stem.lstrip(".")
        is_screaming = bool(re.match(r"^[A-Z0-9]+(_[A-Z0-9]+)*$", clean_stem))
        is_contract = bool(re.match(r"^CONTRACT-[0-9A-Za-z-]+$", clean_stem))
        is_state = bool(re.match(r"^STATE-[0-9A-Za-z-]+$", clean_stem))
        is_readme = (clean_stem == "README")

        if not (is_screaming or is_contract or is_state or is_readme):
            return [
                PathViolation(
                    filepath=path_str,
                    rule_id="INV-FS-20",
                    depth=depth,
                    message=f"System invariant constant document '{filename}' must use SCREAMING_SNAKE_CASE.md",
                )
            ]
    return []


def _check_file_naming(path_str: str, norm_path: Path, depth: int) -> List[PathViolation]:
    """Dispatches file naming validation by extension."""
    if norm_path.name.endswith(".py"):
        return _check_python_filename(path_str, norm_path, depth)
    if norm_path.name.endswith(".md"):
        return _check_markdown_filename(path_str, norm_path, depth)
    return []


def validate_path_conventions(relative_path: Path) -> List[PathViolation]:
    """
    Validates a single relative path against naming, depth, and token rules.
    Conforms to [INV-FS-17] through [INV-FS-22].
    """
    norm_path = Path(relative_path)
    rel_parts = norm_path.parts
    if not rel_parts:
        return []

    path_str = str(norm_path).replace("\\", "/")
    is_file = bool(norm_path.suffix) or "." in norm_path.name
    depth = len(rel_parts) - 1 if is_file else len(rel_parts)

    violations: List[PathViolation] = []
    violations.extend(_check_directory_depth(path_str, depth))

    dir_parts = rel_parts[:-1] if is_file else rel_parts
    violations.extend(_check_directory_banned_tokens(path_str, dir_parts, depth))

    if is_file:
        violations.extend(_check_file_naming(path_str, norm_path, depth))

    return violations


def resolve_cortex_db_path(configured_path: Optional[Path] = None, check_exists: bool = True) -> Path:
    """
    Resolves the canonical cortex.db path with backward-compatible legacy resolution.
    Conforms to [INV-FS-13] and [INV-FS-14].
    """
    if configured_path is not None:
        return Path(configured_path)

    canonical = CanonicalPaths.DATA_CORTEX_DB
    legacy = CanonicalPaths.LEGACY_CORTEX_DB

    if check_exists:
        if canonical.exists():
            return canonical
        if legacy.exists():
            return legacy

    return canonical


def resolve_memory_db_path(configured_path: Optional[Path] = None, check_exists: bool = True) -> Path:
    """
    Resolves canonical memory.db path.
    Conforms to [INV-SPLIT-01] and [INV-SPLIT-02].
    """
    if configured_path is not None:
        return Path(configured_path)
    return CanonicalPaths.DATA_MEMORY_DB


def resolve_document_db_path(configured_path: Optional[Path] = None, check_exists: bool = True) -> Path:
    """
    Resolves canonical document.db path.
    Conforms to [INV-SPLIT-01] and [INV-SPLIT-03].
    """
    if configured_path is not None:
        return Path(configured_path)
    return CanonicalPaths.DATA_DOCUMENT_DB


def _audit_root_entries(root: Path) -> Tuple[List[PathViolation], int]:
    """Audits root entries against src/ prohibition and whitelist [INV-FS-01, INV-FS-03]."""
    violations: List[PathViolation] = []
    root_entries = list(root.iterdir())
    for entry in root_entries:
        if not entry.is_dir():
            continue
        name = entry.name
        if name == "src":
            violations.append(
                PathViolation(
                    filepath=name,
                    rule_id="INV-FS-03",
                    depth=1,
                    message="Repository root SHALL NOT contain a src/ wrapper directory",
                )
            )
        elif name not in AUTHORIZED_ROOT_DIRS and name not in ALLOWED_SYSTEM_DIRS:
            allowed = sorted(AUTHORIZED_ROOT_DIRS)
            violations.append(
                PathViolation(
                    filepath=name,
                    rule_id="INV-FS-01",
                    depth=1,
                    message=f"Root directory '{name}' is not in authorized whitelist: {allowed}",
                )
            )
    return violations, len(root_entries)


def _audit_docs_domains(root: Path) -> Tuple[List[PathViolation], int]:
    """Audits docs/ subdirectories against authorized domain whitelist [INV-FS-04, INV-FS-05]."""
    violations: List[PathViolation] = []
    docs_dir = root / "docs"
    if not (docs_dir.exists() and docs_dir.is_dir()):
        return violations, 0

    scanned = 0
    for doc_entry in docs_dir.iterdir():
        scanned += 1
        if doc_entry.is_dir() and doc_entry.name not in AUTHORIZED_DOCS_DOMAINS:
            rel_str = str(doc_entry.relative_to(root)).replace("\\", "/")
            allowed = sorted(AUTHORIZED_DOCS_DOMAINS)
            violations.append(
                PathViolation(
                    filepath=rel_str,
                    rule_id="INV-FS-05",
                    depth=2,
                    message=f"docs/ domain '{doc_entry.name}' is not in authorized domains: {allowed}",
                )
            )
    return violations, scanned


def _audit_recursive_paths(root: Path) -> Tuple[List[PathViolation], int]:
    """Traverses repository files and directories validating naming and depth invariants."""
    skip_dir_names = {
        ".git",
        ".gemini",
        ".vscode",
        ".idea",
        "__pycache__",
        "sandbox",
        "cache",
        "spool",
        "venv",
        ".venv",
        ".pytest_cache",
    }
    violations: List[PathViolation] = []
    scanned_count = 0

    for current_dir, dirnames, filenames in os.walk(root):
        rel_dir = Path(current_dir).relative_to(root)
        parts = rel_dir.parts

        # Filter out skipped subdirectories in-place to avoid unnecessary traversal
        dirnames[:] = [d for d in dirnames if d not in skip_dir_names and not d.startswith(".git")]

        # If current directory is within a skipped tree, skip validation
        if parts and any(p in skip_dir_names for p in parts):
            continue

        # Validate directory path conventions if not repository root
        if parts:
            violations.extend(validate_path_conventions(rel_dir))

        for fname in filenames:
            scanned_count += 1
            # Skip hidden metadata/temp files (e.g., .gitignore)
            if not fname.startswith("."):
                rel_file_path = rel_dir / fname
                violations.extend(validate_path_conventions(rel_file_path))

    return violations, scanned_count


def audit_filesystem_topology(root_path: Path) -> TopologyAuditResult:
    """
    Scans and audits the entire repository filesystem against canonical topology invariants.
    Completes deterministically with < 100ms benchmark target [INV-FS-25].
    """
    start_time = time.perf_counter()
    root = Path(root_path).resolve()

    if not root.exists() or not root.is_dir():
        duration_ms = (time.perf_counter() - start_time) * 1000
        return TopologyAuditResult(
            passed=False,
            scanned_count=0,
            duration_ms=duration_ms,
            violations=[
                PathViolation(
                    filepath=str(root),
                    rule_id="INV-FS-ROOT",
                    depth=0,
                    message=f"Root directory '{root}' does not exist or is not a directory",
                )
            ],
        )

    try:
        root_violations, root_scanned = _audit_root_entries(root)
    except OSError as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return TopologyAuditResult(
            passed=False,
            scanned_count=0,
            duration_ms=duration_ms,
            violations=[
                PathViolation(
                    filepath=str(root),
                    rule_id="INV-FS-IO",
                    depth=0,
                    message=f"Failed to list root directory: {e}",
                )
            ],
        )

    docs_violations, docs_scanned = _audit_docs_domains(root)
    tree_violations, tree_scanned = _audit_recursive_paths(root)

    violations = root_violations + docs_violations + tree_violations
    scanned_count = root_scanned + docs_scanned + tree_scanned
    duration_ms = (time.perf_counter() - start_time) * 1000

    return TopologyAuditResult(
        passed=len(violations) == 0,
        scanned_count=scanned_count,
        duration_ms=duration_ms,
        violations=violations,
    )


# ==============================================================================
# 4. CLI Interface
# ==============================================================================

def _handle_audit(parsed: argparse.Namespace) -> int:
    """Handles audit subcommand output rendering."""
    root_path = Path(parsed.root)
    result = audit_filesystem_topology(root_path)

    if parsed.json:
        output = {
            "passed": result.passed,
            "scanned_count": result.scanned_count,
            "duration_ms": round(result.duration_ms, 2),
            "violations": [v.to_dict() for v in result.violations],
        }
        print(json.dumps(output, indent=2))
        return 0 if result.passed else 1

    if parsed.compact:
        if result.passed:
            msg = (
                f"[PASS] Filesystem: {result.scanned_count} items scanned "
                f"in {result.duration_ms:.2f}ms (0 violations)"
            )
            print(msg)
            return 0
        hdr = (
            f"[FAIL] Filesystem: {len(result.violations)} violation(s) "
            f"detected across {result.scanned_count} items:"
        )
        print(hdr)
        for idx, v in enumerate(result.violations, 1):
            print(f"  {idx}. [{v.rule_id}] {v.filepath} (depth={v.depth}): {v.message}")
        return 1

    print("=" * 80)
    print(f"  FILESYSTEM TOPOLOGY AUDIT REPORT (Root: {root_path.resolve()})")
    print("=" * 80)
    print(f"Scanned Items: {result.scanned_count} | Scan Duration: {result.duration_ms:.2f}ms")
    print("-" * 80)

    if result.passed:
        print("[PASS] All canonical topology and naming invariants satisfied.")
        print("=" * 80)
        return 0

    print(f"[FAIL] Detected {len(result.violations)} filesystem topology violation(s):")
    for idx, v in enumerate(result.violations, 1):
        print(f"  {idx}. [{v.rule_id}] {v.filepath} (depth={v.depth}): {v.message}")
    print("=" * 80)
    return 1


def _handle_resolve_db(parsed: argparse.Namespace) -> int:
    """Handles resolve-db subcommand execution."""
    configured = Path(parsed.path) if parsed.path else None
    resolved = resolve_cortex_db_path(configured, check_exists=parsed.check_exists)
    print(str(resolved))
    return 0


def _handle_check_path(parsed: argparse.Namespace) -> int:
    """Handles check-path subcommand validation."""
    target = Path(parsed.path)
    violations = validate_path_conventions(target)
    if not violations:
        print(f"[PASS] Path '{target}' satisfies all naming and depth invariants.")
        return 0

    print(f"[FAIL] Path '{target}' violated {len(violations)} invariant(s):")
    for idx, v in enumerate(violations, 1):
        print(f"  {idx}. [{v.rule_id}] (depth={v.depth}): {v.message}")
    return 1


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for filesystem topology management."""
    parser = argparse.ArgumentParser(
        prog="core.fs_topology",
        description="Project Filesystem Principles & Directory Topology Enforcement Engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: audit
    p_audit = subparsers.add_parser("audit", help="Audit repository filesystem against canonical topology")
    p_audit.add_argument("--root", type=str, default=".", help="Root directory path to audit (default: .)")
    p_audit.add_argument("--json", action="store_true", help="Output audit results in JSON format")
    p_audit.add_argument("--compact", "-q", action="store_true", help="Output concise single-line status")

    # Subcommand: resolve-db
    p_resolve = subparsers.add_parser("resolve-db", help="Resolve canonical cortex.db path with fallback")
    p_resolve.add_argument("--path", type=str, default=None, help="Explicitly configured database path")
    p_resolve.add_argument(
        "--check-exists",
        action="store_true",
        default=True,
        help="Check existence for legacy fallback",
    )

    # Subcommand: check-path
    p_check = subparsers.add_parser("check-path", help="Validate naming and depth conventions for a single path")
    p_check.add_argument("--path", type=str, required=True, help="Relative path to evaluate")

    parsed = parser.parse_args(args)

    if parsed.command == "audit":
        return _handle_audit(parsed)
    if parsed.command == "resolve-db":
        return _handle_resolve_db(parsed)
    if parsed.command == "check-path":
        return _handle_check_path(parsed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
