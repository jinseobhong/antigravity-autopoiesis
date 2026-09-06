"""
Companion test suite for Quantitative Compliance Checker (test_compliance_checker.py).
Evaluates compliance detection with >= 30% negative test coverage.
"""

import os
import tempfile
import unittest
from unittest import mock

try:
    from sandbox.scripts.compliance_checker import (
        CodeComplianceAuditor,
        DocComplianceAuditor,
        ComplianceDefect,
        audit_file,
        _collect_target_files,
    )
except ModuleNotFoundError:
    from scripts.compliance_checker import (
        CodeComplianceAuditor,
        DocComplianceAuditor,
        ComplianceDefect,
        audit_file,
        _collect_target_files,
    )


class TestCodeComplianceAuditor(unittest.TestCase):
    """Tests for CodeComplianceAuditor AST rules."""

    def test_valid_code_passes(self) -> None:
        """Positive test: Clean, idiomatic Python code with zero defects."""
        code = (
            "def calculate_tax(amount: float, rate: float) -> float:\n"
            "    if amount < 0 or rate < 0:\n"
            "        raise ValueError('Invalid inputs')\n"
            "    return amount * rate\n"
        )
        auditor = CodeComplianceAuditor("test.py", code)
        defects = auditor.audit()
        self.assertEqual(len(defects), 0, f"Expected 0 defects, got: {defects}")

    def test_negative_lazy_pass_detected(self) -> None:
        """Negative test: Flags 'pass' placeholder stub."""
        code = (
            "def stub_function() -> None:\n"
            "    pass\n"
        )
        auditor = CodeComplianceAuditor("test.py", code)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("LAZY_STUB_PASS", types)

    def test_negative_tautological_assert_detected(self) -> None:
        """Negative test: Flags 'assert True' cheat."""
        code = (
            "def test_dummy() -> None:\n"
            "    assert True\n"
        )
        auditor = CodeComplianceAuditor("test.py", code)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("TAUTOLOGICAL_ASSERTION", types)

    def test_negative_ellipsis_stub_detected(self) -> None:
        """Negative test: Flags '...' placeholder stub."""
        code = (
            "def unfinished_task() -> None:\n"
            "    ...\n"
        )
        auditor = CodeComplianceAuditor("test.py", code)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("LAZY_STUB_ELLIPSIS", types)

    def test_negative_parameter_count_exceeded(self) -> None:
        """Negative test: Flags function with > 7 parameters."""
        code = (
            "def too_many_args(a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: int) -> int:\n"
            "    return a + b + c + d + e + f + g + h\n"
        )
        auditor = CodeComplianceAuditor("test.py", code)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("MAX_PARAMETERS_EXCEEDED", types)

    def test_negative_cyclomatic_complexity_exceeded(self) -> None:
        """Negative test: Flags function with cyclomatic complexity > 10."""
        code = (
            "def highly_complex(val: int) -> int:\n"
            "    res = 0\n"
            "    if val == 1: res += 1\n"
            "    elif val == 2: res += 2\n"
            "    elif val == 3: res += 3\n"
            "    elif val == 4: res += 4\n"
            "    elif val == 5: res += 5\n"
            "    elif val == 6: res += 6\n"
            "    elif val == 7: res += 7\n"
            "    elif val == 8: res += 8\n"
            "    elif val == 9: res += 9\n"
            "    elif val == 10: res += 10\n"
            "    elif val == 11: res += 11\n"
            "    return res\n"
        )
        auditor = CodeComplianceAuditor("test.py", code)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("CYCLOMATIC_COMPLEXITY_EXCEEDED", types)

    def test_negative_line_length_exceeded(self) -> None:
        """Negative test: Flags line exceeding 120 columns."""
        code = "x = '" + "A" * 125 + "'\n"
        auditor = CodeComplianceAuditor("test.py", code)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("LINE_LENGTH_EXCEEDED", types)

    def test_negative_ast_parse_value_error(self) -> None:
        """Negative test: Parser ValueError triggers AST_PARSE_FAILURE without crashing."""
        auditor = CodeComplianceAuditor("corrupt.py", "x = 1\n")
        with mock.patch("ast.parse", side_effect=ValueError("Corrupt null byte buffer")):
            defects = auditor.audit()
        types = [d.type for d in defects]
        self.assertIn("AST_PARSE_FAILURE", types)

    def test_negative_ast_parse_recursion_error(self) -> None:
        """Negative test: Parser RecursionError triggers AST_PARSE_FAILURE without crashing."""
        auditor = CodeComplianceAuditor("deep.py", "x = 1\n")
        with mock.patch("ast.parse", side_effect=RecursionError("Maximum recursion depth exceeded")):
            defects = auditor.audit()
        types = [d.type for d in defects]
        self.assertIn("AST_PARSE_FAILURE", types)

    def test_negative_posonlyargs_counted(self) -> None:
        """Negative test: Positional-only args are counted towards parameter limit."""
        code = "def pos_only_heavy(a, b, c, d, /, e, f, g, h):\n    return a\n"
        auditor = CodeComplianceAuditor("posonly.py", code)
        defects = auditor.audit()
        types = [d.type for d in defects]
        self.assertIn("MAX_PARAMETERS_EXCEEDED", types)




class TestDocComplianceAuditor(unittest.TestCase):
    """Tests for DocComplianceAuditor NASA & Markdown rules."""

    def test_valid_doc_passes(self) -> None:
        """Positive test: Compliant NASA specification with valid metadata."""
        doc = (
            "---\n"
            "id: RFC-0001\n"
            "title: Architecture Blueprint\n"
            "status: PROPOSED\n"
            "owner: Platform Architecture\n"
            "---\n\n"
            "# System Architecture Specification\n\n"
            "## 1. System Invariants\n"
            "The router SHALL dispatch packets within 5 milliseconds.\n"
        )
        auditor = DocComplianceAuditor("doc.md", doc)
        defects = auditor.audit()
        self.assertEqual(len(defects), 0, f"Expected 0 defects, got: {defects}")

    def test_negative_banned_adjective_detected(self) -> None:
        """Negative test: Flags handwaving adjectives like 'seamless'."""
        doc = (
            "---\n"
            "id: RFC-0002\n"
            "status: PROPOSED\n"
            "owner: Platform Architecture\n"
            "---\n\n"
            "# Overview\n"
            "This provides seamless integration across nodes.\n"
        )
        auditor = DocComplianceAuditor("doc.md", doc)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("BANNED_HANDWAVING_WORD", types)

    def test_negative_missing_frontmatter_detected(self) -> None:
        """Negative test: Flags missing YAML frontmatter."""
        doc = "# Missing Frontmatter Document\nThis lacks metadata.\n"
        auditor = DocComplianceAuditor("doc.md", doc)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("MISSING_FRONTMATTER", types)

    def test_negative_multiple_h1_headers_detected(self) -> None:
        """Negative test: Flags multiple top-level H1 headers."""
        doc = (
            "---\n"
            "id: RFC-0003\n"
            "status: PROPOSED\n"
            "owner: Architecture\n"
            "---\n\n"
            "# First Title\n\n"
            "# Second Title\n"
        )
        auditor = DocComplianceAuditor("doc.md", doc)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("MULTIPLE_H1_HEADERS", types)

    def test_negative_compound_requirement_detected(self) -> None:
        """Negative test: Flags compound 'SHALL ... and ...' statement."""
        doc = (
            "---\n"
            "id: RFC-0004\n"
            "status: PROPOSED\n"
            "owner: Architecture\n"
            "---\n\n"
            "# Specification\n"
            "The worker SHALL process records and write them to S3.\n"
        )
        auditor = DocComplianceAuditor("doc.md", doc)
        defects = auditor.audit()
        types = [d["type"] for d in defects]
        self.assertIn("COMPOUND_REQUIREMENT_VIOLATION", types)

    def test_windows_utf8_bom_support(self) -> None:
        """Positive test: Document with Windows UTF-8 BOM is parsed cleanly without missing frontmatter."""
        doc = (
            "\ufeff---\n"
            "id: RFC-0010\n"
            "status: PROPOSED\n"
            "owner: Architecture\n"
            "---\n\n"
            "# BOM Document\n\n"
            "The system SHALL operate safely.\n"
        )
        auditor = DocComplianceAuditor("bom_doc.md", doc)
        defects = auditor.audit()
        self.assertEqual(len(defects), 0, f"Expected 0 defects with BOM, got: {defects}")

    def test_frontmatter_comment_not_counted_as_h1(self) -> None:
        """Positive test: Comments starting with '# ' inside frontmatter do not trigger multiple H1."""
        doc = (
            "---\n"
            "# Header comment inside frontmatter\n"
            "id: RFC-0011\n"
            "status: PROPOSED\n"
            "owner: Architecture\n"
            "---\n\n"
            "# Single Valid Title\n\n"
            "Content here.\n"
        )
        auditor = DocComplianceAuditor("comment_doc.md", doc)
        defects = auditor.audit()
        types = [d.type for d in defects]
        self.assertNotIn("MULTIPLE_H1_HEADERS", types)


class TestSystemComplianceRunner(unittest.TestCase):
    """Integration and boundary tests for runner functions and defect models."""

    def test_compliance_defect_immutability_and_subscript(self) -> None:
        """Evaluates ComplianceDefect value object immutability and backward-compatible indexing."""
        defect = ComplianceDefect(type="SAMPLE_DEFECT", line=42, message="Sample description")
        self.assertEqual(defect.type, "SAMPLE_DEFECT")
        self.assertEqual(defect.line, 42)
        self.assertEqual(defect["type"], "SAMPLE_DEFECT")
        self.assertEqual(defect["line"], "42")
        self.assertEqual(defect["message"], "Sample description")
        self.assertEqual(defect.get("non_existent", "fallback"), "fallback")

    def test_negative_audit_file_missing_target(self) -> None:
        """Negative test: Non-existent file path produces FILE_NOT_FOUND defect."""
        _, defects = audit_file("non_existent_file_xyz_123.py")
        types = [d.type for d in defects]
        self.assertIn("FILE_NOT_FOUND", types)

    def test_negative_audit_file_too_large(self) -> None:
        """Negative test: Files exceeding safety threshold trigger FILE_TOO_LARGE defect."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            # Mock getsize or test threshold
            with mock.patch("os.path.getsize", return_value=6 * 1024 * 1024):
                _, defects = audit_file(tmp_path)
                types = [d.type for d in defects]
                self.assertIn("FILE_TOO_LARGE", types)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_collect_target_files_ignores_vendor_directories(self) -> None:
        """Evaluates directory filtering: vendor and cache directories are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = os.path.join(tmpdir, ".git")
            node_dir = os.path.join(tmpdir, "node_modules")
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(git_dir)
            os.makedirs(node_dir)
            os.makedirs(src_dir)

            with open(os.path.join(git_dir, "leak.py"), "w", encoding="utf-8") as f:
                f.write("x = 1\n")
            with open(os.path.join(node_dir, "vendor.py"), "w", encoding="utf-8") as f:
                f.write("x = 1\n")
            with open(os.path.join(src_dir, "valid.py"), "w", encoding="utf-8") as f:
                f.write("x = 1\n")

            collected = _collect_target_files([tmpdir])
            self.assertEqual(len(collected), 1)
            self.assertTrue(collected[0].endswith("valid.py"))

    def test_collect_target_files_preserves_missing_paths(self) -> None:
        """Evaluates fail-closed behavior: explicit missing paths are retained."""
        missing = "missing_explicit_target.py"
        collected = _collect_target_files([missing])
        self.assertIn(missing, collected)


if __name__ == "__main__":
    unittest.main()

