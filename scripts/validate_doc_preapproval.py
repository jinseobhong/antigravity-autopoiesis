"""
Pre-Approval Documentation Lint Gate (validate_doc_preapproval.py).

Executes deterministic quantitative validation on authored technical documentation
prior to peer review dispatch or sovereign approval.
Enforces NASA single-thought normative syntax, YAML provenance, single H1 headers,
and Mermaid diagram syntax safety in < 0.1s.
"""

import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

# Ensure repository root is in sys.path for direct script execution
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_ROOTS = [
    os.path.abspath(os.path.join(_SCRIPT_DIR, "..")),
    os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..")),
]
for root in _CANDIDATE_ROOTS:
    if root not in sys.path:
        sys.path.insert(0, root)

from scripts.compliance_checker import ComplianceDefect, DocComplianceAuditor


ALLOWED_STATUSES: Set[str] = {"DRAFT", "PROPOSED", "ACCEPTED", "ARCHIVED"}
MAX_DOC_SIZE_BYTES: int = 2 * 1024 * 1024  # 2 MB limit for documentation


@dataclass(frozen=True)
class PreapprovalResult:
    """Immutable value object containing the pre-approval lint determination."""

    filepath: str
    passed: bool
    defects: List[ComplianceDefect]


class DocPreapprovalLinter:
    """High-rigor quantitative documentation linter for pre-approval gating."""

    def __init__(self, filepath: str, content: str) -> None:
        self.filepath = filepath
        self.content = content.lstrip("\ufeff")
        self.lines = self.content.splitlines()
        self.defects: List[ComplianceDefect] = []
        normalized = filepath.replace("\\", "/").lower()
        self.is_agent_or_skill = (
            ".agents" in normalized
            or normalized.endswith("skill.md")
            or "/rules/" in normalized
            or normalized.startswith("docs/rules")
        )

    def lint(self) -> List[ComplianceDefect]:
        """Executes quantitative base audit and enhanced pre-approval checks."""
        # 1. Base Quantitative Compliance Audit
        base_auditor = DocComplianceAuditor(self.filepath, self.content)
        self.defects.extend(base_auditor.audit())

        # 2. Enhanced Pre-Approval Verification Gates
        self._check_status_enum()
        self._check_provenance_keys()
        self._check_unclosed_code_blocks()
        self._check_mermaid_label_quotes()

        return self.defects

    def _check_status_enum(self) -> None:
        """Ensures status field uses one of the authorized lifecycle states."""
        if self.is_agent_or_skill:
            return

        for idx, line in enumerate(self.lines[:30], 1):
            stripped = line.strip()
            if stripped.startswith("status:"):
                raw_val = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                if raw_val not in ALLOWED_STATUSES:
                    self.defects.append(
                        ComplianceDefect(
                            type="INVALID_STATUS_ENUM",
                            line=idx,
                            message=(
                                f"Status '{raw_val}' is invalid; must be one of: "
                                f"{sorted(list(ALLOWED_STATUSES))}"
                            ),
                        )
                    )
                return

    def _check_provenance_keys(self) -> None:
        """Ensures mandatory provenance fields (title, last_reviewed) are present."""
        if self.is_agent_or_skill or not self.content.startswith("---"):
            return

        parts = self.content.split("---", 2)
        if len(parts) < 3:
            return

        header = parts[1]
        required_additional = ["title:", "last_reviewed:"]
        for key in required_additional:
            if key not in header:
                self.defects.append(
                    ComplianceDefect(
                        type="MISSING_PROVENANCE_KEY",
                        line=1,
                        message=f"Document frontmatter missing mandatory field: {key.replace(':', '')}",
                    )
                )

    def _check_unclosed_code_blocks(self) -> None:
        """Ensures all code fences are properly balanced and closed."""
        fence_count = 0
        last_fence_line = 1
        for idx, line in enumerate(self.lines, 1):
            if line.strip().startswith("```"):
                fence_count += 1
                last_fence_line = idx

        if fence_count % 2 != 0:
            self.defects.append(
                ComplianceDefect(
                    type="UNCLOSED_CODE_BLOCK",
                    line=last_fence_line,
                    message=f"Unclosed markdown code block starting or ending near line {last_fence_line}",
                )
            )

    def _check_mermaid_label_quotes(self) -> None:
        """Ensures Mermaid labels with special characters like () or [] are quoted."""
        in_mermaid = False
        unquoted_special_re = re.compile(r"\[[^\"\]]*?[\(\)\/][^\"\]]*?\]")

        for idx, line in enumerate(self.lines, 1):
            stripped = line.strip()
            if stripped.startswith("```mermaid"):
                in_mermaid = True
                continue
            if in_mermaid and stripped.startswith("```"):
                in_mermaid = False
                continue

            if in_mermaid and unquoted_special_re.search(line):
                self.defects.append(
                    ComplianceDefect(
                        type="UNQUOTED_MERMAID_LABEL",
                        line=idx,
                        message=(
                            "Mermaid node label containing parentheses or slashes must be wrapped in double quotes "
                            '(e.g., ["Label (Detail)"])'
                        ),
                    )
                )


def validate_document_preapproval(filepath: str) -> PreapprovalResult:
    """Programmatic API to validate a document prior to approval or peer review dispatch."""
    if not os.path.exists(filepath):
        defect = ComplianceDefect(
            type="FILE_NOT_FOUND",
            line=0,
            message=f"Target document does not exist: {filepath}",
        )
        return PreapprovalResult(filepath=filepath, passed=False, defects=[defect])

    file_size = os.path.getsize(filepath)
    if file_size > MAX_DOC_SIZE_BYTES:
        defect = ComplianceDefect(
            type="FILE_TOO_LARGE",
            line=0,
            message=f"Document size ({file_size} bytes) exceeds limit of {MAX_DOC_SIZE_BYTES} bytes",
        )
        return PreapprovalResult(filepath=filepath, passed=False, defects=[defect])

    with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
        content = f.read()

    linter = DocPreapprovalLinter(filepath, content)
    defects = linter.lint()
    return PreapprovalResult(filepath=filepath, passed=len(defects) == 0, defects=defects)


def run_cli(target_paths: List[str]) -> int:
    """CLI runner executing pre-approval documentation linting across targets."""
    total_defects = 0
    print("================================================================================")
    print("  DOCUMENTATION PRE-APPROVAL LINT GATE (Fast-Path Qualitative Preflight)")
    print("================================================================================")

    for path in target_paths:
        result = validate_document_preapproval(path)
        if result.passed:
            print(f"[PASS] {path}")
        else:
            total_defects += len(result.defects)
            print(f"\n[FAIL] {path}")
            for d in result.defects:
                print(f"  - L{d.line}: [{d.type}] {d.message}")

    print("\n--------------------------------------------------------------------------------")
    print(f"Summary: Audited {len(target_paths)} document(s) | Defects Found: {total_defects}")
    print("--------------------------------------------------------------------------------")

    if total_defects > 0:
        print("VERDICT: REJECTED (Pre-Approval Documentation Quality Gates Failed)")
        return 1

    print("VERDICT: APPROVED (100% Pre-Approval Documentation Standards Met)")
    return 0


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["docs"]
    sys.exit(run_cli(targets))
