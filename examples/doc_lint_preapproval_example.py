"""
Example: Pre-Approval Documentation Lint Gate Integration.

Demonstrates how to programmatically execute quantitative lint verification on
authored markdown technical documentation before approving or dispatching peer review.

Usage:
    python examples/doc_lint_preapproval_example.py
"""

import os
from pathlib import Path
import sys
import tempfile

# Ensure repository root and sandbox roots are on sys.path
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_ROOTS = [
    os.path.abspath(os.path.join(_CURRENT_DIR, "..")),
    os.path.abspath(os.path.join(_CURRENT_DIR, "..", "..")),
]
for root in _CANDIDATE_ROOTS:
    if root not in sys.path:
        sys.path.insert(0, root)

try:
    from scripts.validate_doc_preapproval import (
        PreapprovalResult,
        validate_document_preapproval,
    )
except ModuleNotFoundError as err:
    if err.name not in ("scripts", "scripts.validate_doc_preapproval"):
        raise
    try:
        from sandbox.scripts.validate_doc_preapproval import (
            PreapprovalResult,
            validate_document_preapproval,
        )
    except ModuleNotFoundError:
        raise RuntimeError(
            "Failed to resolve 'validate_doc_preapproval' in 'scripts' or 'sandbox.scripts'"
        ) from err


# ------------------------------------------------------------------------------
# Sample Test Fixtures
# ------------------------------------------------------------------------------

NON_COMPLIANT_DOC = """---
id: SPEC-20260907-cache-faulty
title: Local Cache Engine Architecture
status: UNDER_REVIEW
owner: Platform Lead
last_reviewed: 2026-09-07
---

# Faulty Cache Engine Specification

## 1. Overview
This module provides seamless integration across database shards.

```python
def unclosed_code():
    return True
"""

COMPLIANT_DOC = """---
id: SPEC-20260907-cache-compliant
title: Local Cache Engine Architecture
status: PROPOSED
owner: Platform Lead
last_reviewed: 2026-09-07
---

# Compliant Cache Engine Specification

## 1. Overview
The cache module SHALL synchronize records within 50 milliseconds.

```python
def sample_operation() -> bool:
    return True
```
"""


# ------------------------------------------------------------------------------
# Pre-Approval Gatekeeper Pattern
# ------------------------------------------------------------------------------

def preapproval_gatekeeper(doc_path: str) -> bool:
    """
    Executes the pre-approval lint gate on an authored technical specification.

    Fails closed: captures unexpected I/O faults and returns False to protect
    enclosing workflows from uncontained exceptions.

    Returns:
        bool: True if 100% compliant and cleared for approval / peer-review;
              False if defects exist or an evaluation error occurs.
    """
    print(f"\n[LINT GATE] Evaluating document: {doc_path}")
    try:
        result: PreapprovalResult = validate_document_preapproval(doc_path)
    except Exception as err:
        print(f"  -> ERROR: Gatekeeper evaluation failed with exception: {err}", file=sys.stderr)
        print("  -> ACTION: Approval blocked. Gatekeeper failing closed.", file=sys.stderr)
        return False

    if not result.passed:
        print(f"  -> STATUS: FAIL ({len(result.defects)} defect(s) detected)")
        print("  -> ACTION: Approval blocked. Feed defects back to author for revision.")
        for defect in result.defects:
            print(f"     * L{defect.line} [{defect.type}]: {defect.message}")
        return False

    print("  -> STATUS: PASS (0 defects found)")
    print("  -> ACTION: Cleared for qualitative peer review or sovereign approval.")
    return True


def main() -> int:
    """Runs the demonstration test harness against compliant and non-compliant docs."""
    print("================================================================================")
    print("  PRE-APPROVAL DOCUMENTATION LINT GATE EXAMPLE")
    print("================================================================================")

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)

        # Case A: Non-Compliant Document (Rejection Path)
        bad_spec_path = temp_dir / "SPEC_FAULTY.md"
        bad_spec_path.write_text(NON_COMPLIANT_DOC, encoding="utf-8")

        print("\n--- Test Case 1: Non-Compliant Document ---")
        is_faulty_doc_passed = preapproval_gatekeeper(str(bad_spec_path))
        if is_faulty_doc_passed:
            raise RuntimeError("Assertion Failure: Non-compliant document must fail lint gate!")

        # Case B: Compliant Document (Approval Path)
        good_spec_path = temp_dir / "SPEC_COMPLIANT.md"
        good_spec_path.write_text(COMPLIANT_DOC, encoding="utf-8")

        print("\n--- Test Case 2: 100% Compliant Document ---")
        is_compliant_doc_passed = preapproval_gatekeeper(str(good_spec_path))
        if not is_compliant_doc_passed:
            raise RuntimeError("Assertion Failure: Compliant document must pass lint gate!")

    print("\n================================================================================")
    print("  RESULT: Pre-Approval Lint Gate verified successfully for all test paths.")
    print("================================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
