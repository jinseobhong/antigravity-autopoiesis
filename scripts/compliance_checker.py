"""
Automated Quantitative Compliance Checker (compliance_checker.py).

Enforces repository coding conventions, ISO/IEC 5055 metrics, and NASA-grade
technical documentation standards deterministically in < 0.5s.
"""

import ast
import os
import re
import sys
from typing import Dict, List, Optional, Tuple


class CodeComplianceAuditor(ast.NodeVisitor):
    """AST auditor checking ISO/IEC 5055 and Anti-Cheat invariants."""

    def __init__(self, filename: str, content: str) -> None:
        self.filename = filename
        self.lines = content.splitlines()
        self.defects: List[Dict[str, str]] = []
        self.current_function: Optional[str] = None

    def audit(self) -> List[Dict[str, str]]:
        """Executes full AST and line-by-line quantitative analysis."""
        self._audit_line_lengths()
        try:
            tree = ast.parse("\n".join(self.lines), filename=self.filename)
            self.visit(tree)
        except SyntaxError as err:
            self.defects.append({
                "type": "SYNTAX_ERROR",
                "line": str(err.lineno or 0),
                "message": f"Syntax error: {err.msg}"
            })
        return self.defects

    def _audit_line_lengths(self) -> None:
        """Checks for lines exceeding 120 columns."""
        for idx, line in enumerate(self.lines, 1):
            if len(line) > 120:
                self.defects.append({
                    "type": "LINE_LENGTH_EXCEEDED",
                    "line": str(idx),
                    "message": f"Line exceeds 120 chars ({len(line)} cols)"
                })

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Checks parameter counts and cyclomatic complexity."""
        prev_func = self.current_function
        self.current_function = node.name

        # Parameter count check (Max 7 parameters)
        total_args = (
            len(node.args.args)
            + len(node.args.kwonlyargs)
            + (1 if node.args.vararg else 0)
            + (1 if node.args.kwarg else 0)
        )
        if total_args > 7:
            self.defects.append({
                "type": "MAX_PARAMETERS_EXCEEDED",
                "line": str(node.lineno),
                "message": f"Function '{node.name}' has {total_args} params (max 7 allowed)"
            })

        # Cyclomatic complexity check (Target <= 10)
        cc = self._calculate_cyclomatic_complexity(node)
        if cc > 10:
            self.defects.append({
                "type": "CYCLOMATIC_COMPLEXITY_EXCEEDED",
                "line": str(node.lineno),
                "message": f"Function '{node.name}' has CC={cc} (max 10 allowed)"
            })

        self.generic_visit(node)
        self.current_function = prev_func

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Pass(self, node: ast.Pass) -> None:
        """Flags lazy 'pass' statements in production logic."""
        self.defects.append({
            "type": "LAZY_STUB_PASS",
            "line": str(node.lineno),
            "message": "Lazy placeholder 'pass' statement is prohibited"
        })
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        """Flags tautological assertions like 'assert True'."""
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            self.defects.append({
                "type": "TAUTOLOGICAL_ASSERTION",
                "line": str(node.lineno),
                "message": "Tautological 'assert True' is prohibited"
            })
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        """Flags ellipsis (...) stubs outside docstrings."""
        if isinstance(node.value, ast.Constant) and node.value.value is ...:
            self.defects.append({
                "type": "LAZY_STUB_ELLIPSIS",
                "line": str(node.lineno),
                "message": "Placeholder ellipsis '...' stub is prohibited"
            })
        self.generic_visit(node)

    def _calculate_cyclomatic_complexity(self, node: ast.AST) -> int:
        """Computes McCabe cyclomatic complexity for a given AST node."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, (ast.ExceptHandler, ast.With, ast.AsyncWith)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, ast.IfExp):
                complexity += 1
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

    def __init__(self, filename: str, content: str) -> None:
        self.filename = filename
        self.content = content
        self.lines = content.splitlines()
        self.defects: List[Dict[str, str]] = []

    def audit(self) -> List[Dict[str, str]]:
        """Runs deterministic checks for metadata, banned words, and structure."""
        self._audit_frontmatter()
        self._audit_banned_adjectives()
        self._audit_single_h1()
        self._audit_atomic_normative()
        return self.defects

    def _audit_frontmatter(self) -> None:
        """Ensures document has valid YAML frontmatter appropriate for its type."""
        if not self.content.startswith("---"):
            self.defects.append({
                "type": "MISSING_FRONTMATTER",
                "line": "1",
                "message": "Document must begin with YAML frontmatter delimiter (---)"
            })
            return

        parts = self.content.split("---", 2)
        if len(parts) < 3:
            self.defects.append({
                "type": "MALFORMED_FRONTMATTER",
                "line": "1",
                "message": "Frontmatter is not closed with trailing '---'"
            })
            return

        header = parts[1]
        is_agent_config = ".agents" in self.filename or "SKILL.md" in self.filename
        
        if is_agent_config:
            required_keys = ["name:", "description:"]
        else:
            required_keys = ["id:", "status:", "owner:"]

        for key in required_keys:
            if key not in header:
                self.defects.append({
                    "type": "MISSING_METADATA_KEY",
                    "line": "1",
                    "message": f"Frontmatter missing mandatory field: {key.replace(':', '')}"
                })

    def _audit_banned_adjectives(self) -> None:
        """Flags unquantified marketing fluff and handwaving words outside rule definitions."""
        # Skip banned word check if this file is the rule defining the banned words
        if "DOCUMENTATION_TONE" in self.filename or "SKILL.md" in self.filename:
            return

        for idx, line in enumerate(self.lines, 1):
            lower = line.lower()
            for banned in self.BANNED_ADJECTIVES:
                if re.search(r"\b" + re.escape(banned) + r"\b", lower):
                    self.defects.append({
                        "type": "BANNED_HANDWAVING_WORD",
                        "line": str(idx),
                        "message": f"Unquantified adjective '{banned}' is prohibited"
                    })

    def _audit_single_h1(self) -> None:
        """Ensures document has exactly one top-level H1 header outside code blocks."""
        h1_count = 0
        in_code_block = False
        for line in self.lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if not in_code_block and line.startswith("# ") and not line.startswith("## "):
                h1_count += 1

        if h1_count == 0:
            self.defects.append({
                "type": "MISSING_H1_HEADER",
                "line": "1",
                "message": "Document must contain exactly one top-level '# ' H1 heading"
            })
        elif h1_count > 1:
            self.defects.append({
                "type": "MULTIPLE_H1_HEADERS",
                "line": "1",
                "message": f"Document contains {h1_count} H1 headings (maximum 1 allowed)"
            })

    def _audit_atomic_normative(self) -> None:
        """Flags compound requirement statements violating the NASA single-thought mandate."""
        # Skip meta-rules and skill files that explain the rule itself
        if ".agents" in self.filename or "SKILL.md" in self.filename:
            return

        for idx, line in enumerate(self.lines, 1):
            if "SHALL" in line and not line.strip().startswith("#"):
                # Detect compound SHALL with coordinating conjunctions
                if re.search(r"\bSHALL\b.+\b(and|as well as|along with)\b.+", line, re.IGNORECASE):
                    self.defects.append({
                        "type": "COMPOUND_REQUIREMENT_VIOLATION",
                        "line": str(idx),
                        "message": "Requirement contains compound conjunction; must be split into atomic SHALLs"
                    })


def audit_file(filepath: str) -> Tuple[str, List[Dict[str, str]]]:
    """Audits a single file based on its extension."""
    if not os.path.exists(filepath):
        return filepath, [{"type": "FILE_NOT_FOUND", "line": "0", "message": f"File not found: {filepath}"}]

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if filepath.endswith(".py"):
        auditor = CodeComplianceAuditor(filepath, content)
        return filepath, auditor.audit()
    if filepath.endswith(".md"):
        auditor_doc = DocComplianceAuditor(filepath, content)
        return filepath, auditor_doc.audit()

    return filepath, []


def _collect_target_files(paths: List[str]) -> List[str]:
    """Collects all .py and .md files from paths deterministically."""
    collected = []
    for path in paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    if file.endswith((".py", ".md")):
                        collected.append(os.path.join(root, file))
        elif os.path.exists(path):
            collected.append(path)
    return collected


def run_cli(target_paths: List[str]) -> int:
    """CLI runner executing compliance audit across paths."""
    total_defects = 0
    targets = _collect_target_files(target_paths)

    print("================================================================================")
    print("  FAST-PATH QUANTITATIVE COMPLIANCE AUDITOR (Tier 1)")
    print("================================================================================")

    for path in targets:
        _, defects = audit_file(path)
        if defects:
            total_defects += len(defects)
            print(f"\n[FAIL] {path}")
            for d in defects:
                print(f"  - L{d['line']}: [{d['type']}] {d['message']}")
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


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["."]
    sys.exit(run_cli(targets))
