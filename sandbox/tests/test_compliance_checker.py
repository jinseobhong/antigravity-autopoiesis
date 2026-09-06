"""
Companion test suite for Quantitative Compliance Checker (test_compliance_checker.py).
Evaluates compliance detection with >= 30% negative test coverage.
"""

import unittest
from sandbox.scripts.compliance_checker import CodeComplianceAuditor, DocComplianceAuditor


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


if __name__ == "__main__":
    unittest.main()
