"""
Automated Quantitative Compliance Checker (compliance_checker.py).

Enforces repository coding conventions, ISO/IEC 5055 metrics, and NASA-grade
technical documentation standards deterministically in < 0.5s.
"""

import ast
from dataclasses import dataclass
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ComplianceDefect:
    """Immutable value object representing a quantified compliance defect."""

    type: str
    line: int
    message: str

    def __getitem__(self, item: str) -> Any:
        """Enables backward-compatible dictionary-style subscript access."""
        if item == "type":
            return self.type
        if item == "line":
            return str(self.line)
        if item == "message":
            return self.message
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        """Safe getter mimicking dict.get for backward compatibility."""
        try:
            return self[item]
        except KeyError:
            return default



class CodeComplianceAuditor(ast.NodeVisitor):
    """AST auditor checking ISO/IEC 5055 and Anti-Cheat invariants."""

    def __init__(self, filename: str, content: str) -> None:
        self.filename = filename
        self.lines = content.splitlines()
        self.defects: List[ComplianceDefect] = []

    def audit(self) -> List[ComplianceDefect]:
        """Executes full AST and line-by-line quantitative analysis."""
        self._audit_line_lengths()
        try:
            tree = ast.parse("\n".join(self.lines), filename=self.filename)
            self.visit(tree)
        except SyntaxError as err:
            self.defects.append(ComplianceDefect(
                type="SYNTAX_ERROR",
                line=err.lineno or 0,
                message=f"Syntax error: {err.msg}"
            ))
        except (ValueError, RecursionError) as err:
            self.defects.append(ComplianceDefect(
                type="AST_PARSE_FAILURE",
                line=1,
                message=f"AST parsing failed: {err}"
            ))
        return self.defects

    def _audit_line_lengths(self) -> None:
        """Checks for lines exceeding 120 columns."""
        for idx, line in enumerate(self.lines, 1):
            if len(line) > 120:
                self.defects.append(ComplianceDefect(
                    type="LINE_LENGTH_EXCEEDED",
                    line=idx,
                    message=f"Line exceeds 120 chars ({len(line)} cols)"
                ))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Checks parameter counts and cyclomatic complexity."""
        # Parameter count check (Max 7 parameters including posonlyargs)
        total_args = (
            len(node.args.args)
            + len(getattr(node.args, "posonlyargs", []))
            + len(node.args.kwonlyargs)
            + (1 if node.args.vararg else 0)
            + (1 if node.args.kwarg else 0)
        )
        if total_args > 7:
            self.defects.append(ComplianceDefect(
                type="MAX_PARAMETERS_EXCEEDED",
                line=node.lineno,
                message=f"Function '{node.name}' has {total_args} params (max 7 allowed)"
            ))

        # Cyclomatic complexity check (Target <= 10)
        cc = self._calculate_cyclomatic_complexity(node)
        if cc > 10:
            self.defects.append(ComplianceDefect(
                type="CYCLOMATIC_COMPLEXITY_EXCEEDED",
                line=node.lineno,
                message=f"Function '{node.name}' has CC={cc} (max 10 allowed)"
            ))

        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Pass(self, node: ast.Pass) -> None:
        """Flags lazy 'pass' statements in production logic."""
        self.defects.append(ComplianceDefect(
            type="LAZY_STUB_PASS",
            line=node.lineno,
            message="Lazy placeholder 'pass' statement is prohibited"
        ))
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        """Flags tautological assertions like 'assert True'."""
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            self.defects.append(ComplianceDefect(
                type="TAUTOLOGICAL_ASSERTION",
                line=node.lineno,
                message="Tautological 'assert True' is prohibited"
            ))
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        """Flags ellipsis (...) stubs outside docstrings."""
        if isinstance(node.value, ast.Constant) and node.value.value is ...:
            self.defects.append(ComplianceDefect(
                type="LAZY_STUB_ELLIPSIS",
                line=node.lineno,
                message="Placeholder ellipsis '...' stub is prohibited"
            ))
        self.generic_visit(node)

    def _calculate_cyclomatic_complexity(self, node: ast.AST) -> int:
        """Computes McCabe cyclomatic complexity for a given AST node."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                (ast.If, ast.IfExp, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler, ast.With, ast.AsyncWith),
            ):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity


class DocComplianceAuditor:
    """Quantitative auditor for NASA-grade technical documentation standards."""

    BANNED_ADJECTIVES = [
        "seamless",
        "effortless",
        "blazing-fast",
        "lightning-fast",
        "infinitely scalable",
        "ultra-low latency",
        "easy to use",
    ]

    BANNED_PATTERN = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in BANNED_ADJECTIVES) + r")\b",
        re.IGNORECASE,
    )
    COMPOUND_SHALL_PATTERN = re.compile(r"\bSHALL\b.+\b(and|as well as|along with)\b.+")

    def __init__(self, filename: str, content: str) -> None:
        self.filename = filename
        normalized = filename.replace("\\", "/").lower()
        self.is_constitution = normalized.endswith("gemini.md")
        self.is_agent_or_skill = (
            ".agents" in normalized
            or normalized.endswith("skill.md")
            or "/rules/" in normalized
            or normalized.startswith("docs/rules")
        )
        self.is_rule_def = "documentation_tone" in normalized or "rules" in normalized or self.is_agent_or_skill
        self.content = content.lstrip("\ufeff")
        self.lines = self.content.splitlines()
        self.defects: List[ComplianceDefect] = []

    def audit(self) -> List[ComplianceDefect]:
        """Runs deterministic checks for metadata, banned words, and structure."""
        self._audit_frontmatter()
        self._audit_banned_adjectives()
        self._audit_single_h1()
        self._audit_atomic_normative()
        return self.defects

    def _audit_frontmatter(self) -> None:
        """Ensures document has valid YAML frontmatter appropriate for its type."""
        if self.is_constitution:
            return

        if not self.content.startswith("---"):
            self.defects.append(ComplianceDefect(
                type="MISSING_FRONTMATTER",
                line=1,
                message="Document must begin with YAML frontmatter delimiter (---)"
            ))
            return

        parts = self.content.split("---", 2)
        if len(parts) < 3:
            self.defects.append(ComplianceDefect(
                type="MALFORMED_FRONTMATTER",
                line=1,
                message="Frontmatter is not closed with trailing '---'"
            ))
            return

        header = parts[1]
        if self.is_agent_or_skill:
            required_keys = ["name:", "description:"]
        else:
            required_keys = ["id:", "status:", "owner:"]

        for key in required_keys:
            if key not in header:
                self.defects.append(ComplianceDefect(
                    type="MISSING_METADATA_KEY",
                    line=1,
                    message=f"Frontmatter missing mandatory field: {key.replace(':', '')}"
                ))

    def _audit_banned_adjectives(self) -> None:
        """Flags unquantified marketing fluff and handwaving words outside rule definitions."""
        if self.is_rule_def:
            return

        for idx, line in enumerate(self.lines, 1):
            match = self.BANNED_PATTERN.search(line)
            if match:
                self.defects.append(ComplianceDefect(
                    type="BANNED_HANDWAVING_WORD",
                    line=idx,
                    message=f"Unquantified adjective '{match.group(0).lower()}' is prohibited"
                ))

    def _strip_frontmatter_lines(self) -> List[str]:
        """Returns lines with frontmatter stripped if present."""
        if not self.lines or self.lines[0].strip() != "---":
            return self.lines
        for idx in range(1, len(self.lines)):
            if self.lines[idx].strip() == "---":
                return self.lines[idx + 1 :]
        return self.lines

    def _extract_prose_lines(self) -> List[str]:
        """Extracts lines outside of fenced code blocks."""
        body_lines = self._strip_frontmatter_lines()
        prose: List[str] = []
        in_fence = False
        fence_marker = ""

        for line in body_lines:
            stripped = line.strip()
            if not in_fence and stripped.startswith("```"):
                in_fence = True
                match = re.match(r"^`+", stripped)
                fence_marker = match.group(0) if match else "```"
                continue
            if in_fence and stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
                continue
            if not in_fence:
                prose.append(line)
        return prose

    def _count_h1_headings(self) -> int:
        """Counts top-level H1 headings excluding frontmatter and code blocks."""
        return sum(1 for line in self._extract_prose_lines() if line.startswith("# "))

    def _audit_single_h1(self) -> None:
        """Ensures document has exactly one top-level H1 header outside code blocks."""
        h1_count = self._count_h1_headings()
        if h1_count == 0:
            self.defects.append(ComplianceDefect(
                type="MISSING_H1_HEADER",
                line=1,
                message="Document must contain exactly one top-level '# ' H1 heading"
            ))
        elif h1_count > 1:
            self.defects.append(ComplianceDefect(
                type="MULTIPLE_H1_HEADERS",
                line=1,
                message=f"Document contains {h1_count} H1 headings (maximum 1 allowed)"
            ))

    def _audit_atomic_normative(self) -> None:
        """Flags compound requirement statements violating the NASA single-thought mandate."""
        if self.is_agent_or_skill:
            return

        for idx, line in enumerate(self.lines, 1):
            stripped = line.strip()
            if "SHALL" not in line or stripped.startswith("#"):
                continue
            if self.COMPOUND_SHALL_PATTERN.search(line):
                self.defects.append(ComplianceDefect(
                    type="COMPOUND_REQUIREMENT_VIOLATION",
                    line=idx,
                    message="Requirement contains compound conjunction; must be split into atomic SHALLs"
                ))


MAX_AUDIT_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB safety ceiling
IGNORED_DIRECTORIES = {
    ".git", ".hg", ".svn", ".venv", "venv", "env",
    "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "build", "dist", ".eggs"
}


def audit_file(filepath: str) -> Tuple[str, List[ComplianceDefect]]:
    """Audits a single file based on its extension."""
    try:
        if not os.path.exists(filepath):
            return filepath, [ComplianceDefect(
                type="FILE_NOT_FOUND",
                line=0,
                message=f"File not found: {filepath}"
            )]

        file_size = os.path.getsize(filepath)
        if file_size > MAX_AUDIT_FILE_SIZE_BYTES:
            return filepath, [ComplianceDefect(
                type="FILE_TOO_LARGE",
                line=0,
                message=f"File size ({file_size} bytes) exceeds limit of {MAX_AUDIT_FILE_SIZE_BYTES} bytes"
            )]

        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            content = f.read()

        if filepath.endswith(".py"):
            auditor = CodeComplianceAuditor(filepath, content)
            return filepath, auditor.audit()
        if filepath.endswith(".md"):
            auditor_doc = DocComplianceAuditor(filepath, content)
            return filepath, auditor_doc.audit()

        return filepath, []
    except OSError as err:
        return filepath, [ComplianceDefect(
            type="IO_READ_ERROR",
            line=0,
            message=f"Cannot read file: {err}"
        )]
    except Exception as err:
        return filepath, [ComplianceDefect(
            type="AUDITOR_INTERNAL_ERROR",
            line=0,
            message=f"Unexpected auditor error: {err}"
        )]


def _walk_directory_files(directory: str) -> List[str]:
    """Recursively collects Python and Markdown files while skipping ignored trees."""
    collected = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES and not d.startswith(".")]
        for file in files:
            if file.endswith((".py", ".md")):
                collected.append(os.path.join(root, file))
    return collected


def _collect_target_files(paths: List[str]) -> List[str]:
    """Collects all .py and .md files from paths deterministically."""
    collected: List[str] = []
    for path in paths:
        if os.path.isdir(path):
            collected.extend(_walk_directory_files(path))
        else:
            # Pass through non-directory (including non-existent files) so audit_file reports errors
            collected.append(path)
    return sorted(collected)


def _print_compact_report(
    targets: List[str],
    failing_files: List[Tuple[str, List[ComplianceDefect]]],
    duration: float,
) -> int:
    """Outputs single-line pass or concise defect coordinates."""
    total_defects = sum(len(defs) for _, defs in failing_files)
    if total_defects == 0:
        print(f"[PASS] Compliance Gate: {len(targets)} files audited (0 defects) in {duration:.2f}s")
        return 0

    print(f"[FAIL] Compliance Gate: {total_defects} defect(s) detected across {len(failing_files)} file(s):")
    for path, defects in failing_files:
        print(f"  {path}:")
        for d in defects:
            print(f"    - L{d.line}: [{d.type}] {d.message}")
    return 1


def _print_standard_report(
    targets: List[str],
    failing_files: List[Tuple[str, List[ComplianceDefect]]],
) -> int:
    """Outputs verbose per-file audit report and summary banner."""
    total_defects = sum(len(defs) for _, defs in failing_files)
    print("================================================================================")
    print("  FAST-PATH QUANTITATIVE COMPLIANCE AUDITOR (Tier 1)")
    print("================================================================================")

    failing_map = dict(failing_files)
    for path in targets:
        if path in failing_map:
            print(f"\n[FAIL] {path}")
            for d in failing_map[path]:
                print(f"  - L{d.line}: [{d.type}] {d.message}")
        else:
            print(f"[PASS] {path}")

    print("\n--------------------------------------------------------------------------------")
    print(f"Summary: Audited {len(targets)} file(s) | Defects Found: {total_defects}")
    print("--------------------------------------------------------------------------------")

    if total_defects > 0:
        print("VERDICT: REJECTED (Quantitative Compliance Gates Failed)")
        return 1

    print("VERDICT: APPROVED (100% Quantitative Compliance Passed)")
    return 0


def run_cli(target_paths: Optional[List[str]] = None) -> int:
    """CLI runner executing compliance audit across paths."""
    args = target_paths if target_paths is not None else sys.argv[1:]
    compact_mode = False
    clean_paths: List[str] = []
    for a in args:
        if a in ("--compact", "-q", "--quiet"):
            compact_mode = True
        else:
            clean_paths.append(a)

    targets = _collect_target_files(clean_paths if clean_paths else ["."])
    failing_files: List[Tuple[str, List[ComplianceDefect]]] = []
    start_time = time.perf_counter()

    for path in targets:
        _, defects = audit_file(path)
        if defects:
            failing_files.append((path, defects))

    duration = time.perf_counter() - start_time
    if compact_mode:
        return _print_compact_report(targets, failing_files, duration)
    return _print_standard_report(targets, failing_files)


if __name__ == "__main__":
    sys.exit(run_cli())
