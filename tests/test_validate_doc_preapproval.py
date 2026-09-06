"""
Companion test suite for Pre-Approval Documentation Lint Gate.
Evaluates pre-approval documentation validation with >= 30% negative test coverage.
"""

import os
import tempfile
import unittest

try:
    from scripts.validate_doc_preapproval import (
        DocPreapprovalLinter,
        PreapprovalResult,
        validate_document_preapproval,
    )
except ModuleNotFoundError:
    from sandbox.scripts.validate_doc_preapproval import (
        DocPreapprovalLinter,
        PreapprovalResult,
        validate_document_preapproval,
    )


class TestDocPreapprovalLinter(unittest.TestCase):
    """Tests for pre-approval documentation lint invariants."""

    def test_valid_document_passes(self) -> None:
        """Positive test: Fully compliant specification passes with zero defects."""
        doc = (
            "---\n"
            "id: SPEC-20260907-cache\n"
            "title: Local Cache Engine Architecture\n"
            "status: PROPOSED\n"
            "owner: Platform Lead\n"
            "last_reviewed: 2026-09-07\n"
            "---\n\n"
            "# System Architecture Blueprint\n\n"
            "The router SHALL dispatch packets within 5 milliseconds.\n"
        )
        linter = DocPreapprovalLinter("test_spec.md", doc)
        defects = linter.lint()
        self.assertEqual(len(defects), 0, f"Expected 0 defects, got: {defects}")

    def test_negative_invalid_status_enum_detected(self) -> None:
        """Negative test: Flags unauthorized status values."""
        doc = (
            "---\n"
            "id: SPEC-0001\n"
            "title: Spec Title\n"
            "status: UNKNOWN_STATUS\n"
            "owner: Platform Lead\n"
            "last_reviewed: 2026-09-07\n"
            "---\n\n"
            "# Valid Title\n\n"
            "The system SHALL run.\n"
        )
        linter = DocPreapprovalLinter("test_spec.md", doc)
        defects = linter.lint()
        types = [d.type for d in defects]
        self.assertIn("INVALID_STATUS_ENUM", types)

    def test_negative_missing_provenance_key_detected(self) -> None:
        """Negative test: Flags missing mandatory title or last_reviewed field."""
        doc = (
            "---\n"
            "id: SPEC-0002\n"
            "status: PROPOSED\n"
            "owner: Platform Lead\n"
            "---\n\n"
            "# Valid Title\n\n"
            "The system SHALL run.\n"
        )
        linter = DocPreapprovalLinter("test_spec.md", doc)
        defects = linter.lint()
        types = [d.type for d in defects]
        self.assertIn("MISSING_PROVENANCE_KEY", types)

    def test_negative_unclosed_code_block_detected(self) -> None:
        """Negative test: Flags unbalanced markdown code fences."""
        doc = (
            "---\n"
            "id: SPEC-0003\n"
            "title: Spec Title\n"
            "status: PROPOSED\n"
            "owner: Platform Lead\n"
            "last_reviewed: 2026-09-07\n"
            "---\n\n"
            "# Code Spec\n\n"
            "```python\n"
            "x = 1\n"
        )
        linter = DocPreapprovalLinter("test_spec.md", doc)
        defects = linter.lint()
        types = [d.type for d in defects]
        self.assertIn("UNCLOSED_CODE_BLOCK", types)

    def test_negative_unquoted_mermaid_label_detected(self) -> None:
        """Negative test: Flags Mermaid node labels with special chars lacking double quotes."""
        doc = (
            "---\n"
            "id: SPEC-0004\n"
            "title: Spec Title\n"
            "status: PROPOSED\n"
            "owner: Platform Lead\n"
            "last_reviewed: 2026-09-07\n"
            "---\n\n"
            "# Architecture\n\n"
            "```mermaid\n"
            "flowchart TD\n"
            "    A[Node (Unquoted)] --> B\n"
            "```\n"
        )
        linter = DocPreapprovalLinter("test_spec.md", doc)
        defects = linter.lint()
        types = [d.type for d in defects]
        self.assertIn("UNQUOTED_MERMAID_LABEL", types)

    def test_negative_missing_file_api(self) -> None:
        """Negative test: Programmatic API handles non-existent files gracefully."""
        result = validate_document_preapproval("non_existent_doc_xyz.md")
        self.assertFalse(result.passed)
        self.assertEqual(result.defects[0].type, "FILE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
