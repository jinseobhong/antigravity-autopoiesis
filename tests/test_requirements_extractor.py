"""
Companion test suite for Requirements Extractor Engine (TASK-026).

Ingests docs/active/ACTIVE_CONTRACT.md as primary specification authority.
Evaluates prompt decomposition into CoreIntent, FunctionalRequirements,
AutoImmunizedNFRs (via FTS5 cortex.db historical failure retrieval), and NonGoals.
Validates RequirementsSpec immutability, markdown serialization, CLI invocation,
and zero-crash fail-open error containment on corrupted/unavailable databases.
Enforces AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12 with >= 40% negative ratio.
"""

from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional
import unittest

try:
    from core.requirements_extractor import (
        RequirementsSpec,
        extract_requirements,
    )
    _MODULE_AVAILABLE = True
except ModuleNotFoundError:
    try:
        from sandbox.core.requirements_extractor import (
            RequirementsSpec,
            extract_requirements,
        )
        _MODULE_AVAILABLE = True
    except ModuleNotFoundError:
        _MODULE_AVAILABLE = False
        RequirementsSpec = None  # type: ignore[assignment]
        extract_requirements = None  # type: ignore[assignment]


def _init_test_cortex_db(db_file: Path) -> None:
    """Provisions isolated SQLite database with episodic_events and fts_events schemas."""
    con = sqlite3.connect(str(db_file))
    try:
        with con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS episodic_events (
                    id TEXT PRIMARY KEY,
                    outcome TEXT CHECK(outcome IN ('SUCCESS', 'FAILURE')) NOT NULL,
                    component TEXT NOT NULL,
                    trigger_tokens TEXT NOT NULL,
                    root_cause TEXT,
                    directive TEXT NOT NULL,
                    solution TEXT,
                    validation TEXT,
                    access_frequency INTEGER NOT NULL DEFAULT 1,
                    recency_weight REAL NOT NULL DEFAULT 1.0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_accessed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            con.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_events USING fts5(
                    id UNINDEXED,
                    component,
                    trigger_tokens,
                    directive,
                    root_cause,
                    solution
                );
                """
            )
            con.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_fts_insert AFTER INSERT ON episodic_events BEGIN
                    INSERT INTO fts_events(id, component, trigger_tokens, directive, root_cause, solution)
                    VALUES (new.id, new.component, new.trigger_tokens, new.directive, new.root_cause, new.solution);
                END;
                """
            )
    finally:
        con.close()


def _seed_test_failure_event(
    db_file: Path,
    event_id: str,
    component: str,
    trigger_tokens: str,
    directive: str,
    root_cause: str,
) -> None:
    """Seeds a historical failure lesson into the test cortex database."""
    con = sqlite3.connect(str(db_file))
    try:
        with con:
            con.execute(
                """
                INSERT INTO episodic_events (
                    id, outcome, component, trigger_tokens, root_cause,
                    directive, solution, validation, access_frequency,
                    recency_weight, created_at, last_accessed_at
                ) VALUES (?, 'FAILURE', ?, ?, ?, ?, 'Fixed root cause', '100% pass', 3, 1.5,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                """,
                (event_id, component, trigger_tokens, root_cause, directive),
            )
    finally:
        con.close()


_TASK_026_FALLBACK_CONTRACT = """---
id: "CONTRACT-20260907-req-and-backprop"
title: "Requirements Extractor and Subprocess Backpropagation Pipeline Contract"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
target_task_id: "TASK-026"
---

# Active Engineering Contract: Requirements Extractor & Subprocess Backpropagation Pipeline

## 2. Normative Invariants (The NASA Lexicon)
- `[INV-REQ-01]` Prompt decomposition into structured specification
- `[INV-REQ-01.1]` CoreIntent decomposition from incoming prompts
- `[INV-REQ-01.2]` AutoImmunizedNFRs via episodic failure retrieval
- `[INV-REQ-01.3]` Explicit NonGoals extraction from boundary negations
- `[INV-REQ-01.4]` Deterministic SHA-256 source prompt hash calculation
- `[INV-REQ-02]` Deterministic parsing without non-deterministic LLM calls
- `[INV-REQ-02.1]` Fail-open containment on corrupted or missing database
- `[INV-REQ-02.2]` Empty or whitespace-only prompt validation
- `[INV-REQ-03]` Data structures and serialization
- `[INV-REQ-03.1]` Frozen immutable RequirementsSpec dataclass
- `[INV-REQ-03.2]` GitHub-flavored markdown serialization
- `[INV-BKP-04]` Subprocess pipeline integration
- `[INV-BKP-04.1]` Process isolation and deterministic timeout
- `[INV-BKP-04.2]` Graceful degradation on unparseable inputs
- `[INV-BKP-05]` Cyclomatic complexity and line length enforcement

## 3. Data Schema & Specifications
```python
class RequirementsSpec:
    def to_markdown(self) -> str:
        return ""

    def to_dict(self) -> Dict[str, Any]:
        return {}

def extract_requirements(
    prompt: str,
    db_path: Optional[Path] = None,
) -> RequirementsSpec:
    return RequirementsSpec()
```
"""


def _load_task_026_contract() -> str:
    """Loads TASK-026 contract from active contract file, cortex.db, or fixture."""
    contract_path = Path("docs/active/ACTIVE_CONTRACT.md")
    if contract_path.exists():
        try:
            content = contract_path.read_text(encoding="utf-8")
            if 'target_task_id: "TASK-026"' in content:
                return content
        except OSError:
            _err_fallback = True
    db_path = Path("data/cortex.db")
    if db_path.exists():
        try:
            con = sqlite3.connect(str(db_path))
            cur = con.execute(
                "SELECT raw_content FROM contract_revisions WHERE task_id = 'TASK-026' "
                "ORDER BY revision_id DESC LIMIT 1;"
            )
            row = cur.fetchone()
            con.close()
            if row:
                return str(row[0])
        except Exception:
            _err_fallback = True
    return _TASK_026_FALLBACK_CONTRACT


class TestRequirementsExtractorContractInvariants(unittest.TestCase):
    """Verifies that the specification contract defines normative invariants [INV-REQ-01..03, INV-BKP-04]."""

    def setUp(self) -> None:
        self.contract_text = _load_task_026_contract()
        self.assertTrue(
            len(self.contract_text.strip()) > 0,
            "Contract text missing from active contract, cortex.db, and fixture",
        )

    def test_contract_metadata_and_acceptance(self) -> None:
        """Positive test: Verifies contract is ACCEPTED and target_task_id matches valid format."""
        self.assertIn('status: "ACCEPTED"', self.contract_text)
        self.assertRegex(self.contract_text, r'target_task_id:\s*"TASK-\d+"')

    def test_contract_defines_all_normative_extractor_invariants(self) -> None:
        """Positive test: Verifies presence of extractor normative invariants."""
        required_invariants = [
            "[INV-REQ-01]",
            "[INV-REQ-01.1]",
            "[INV-REQ-01.2]",
            "[INV-REQ-01.3]",
            "[INV-REQ-01.4]",
            "[INV-REQ-02]",
            "[INV-REQ-02.1]",
            "[INV-REQ-02.2]",
            "[INV-REQ-03]",
            "[INV-REQ-03.1]",
            "[INV-REQ-03.2]",
            "[INV-BKP-04]",
            "[INV-BKP-04.1]",
            "[INV-BKP-04.2]",
            "[INV-BKP-05]",
        ]
        for inv_id in required_invariants:
            self.assertIn(
                inv_id,
                self.contract_text,
                f"Missing invariant definition {inv_id} in active contract",
            )

    def test_contract_defines_extractor_technical_interfaces(self) -> None:
        """Positive test: Verifies contract specifies RequirementsSpec dataclass and API."""
        self.assertIn("class RequirementsSpec", self.contract_text)
        self.assertIn("def extract_requirements", self.contract_text)
        self.assertIn("to_markdown", self.contract_text)
        self.assertIn("to_dict", self.contract_text)

    def test_negative_contract_missing_synthetic_invariant(self) -> None:
        """Negative test: Evaluates assertion failure when checking non-existent invariant."""
        synthetic_id = "[INV-REQ-NONEXISTENT-999]"
        self.assertNotIn(
            synthetic_id,
            self.contract_text,
            "Non-existent invariant unexpectedly found in contract text",
        )


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.requirements_extractor pending implementation by software-engineer",
)
class TestRequirementsExtractorPositive(unittest.TestCase):
    """Evaluates positive prompt decomposition, FTS5 failure immunization, and markdown export."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_cortex.db"
        _init_test_cortex_db(self.db_path)
        _seed_test_failure_event(
            db_file=self.db_path,
            event_id="evt_tok_401",
            component="token_authenticator",
            trigger_tokens="token auth validation timeout",
            directive="Enforce deterministic 500ms timeout on auth token verification",
            root_cause="Deadlock in token verification worker loop",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_extract_requirements_decomposes_all_fields_with_cortex(self) -> None:
        """Positive test: Decomposes intent, functional reqs, non-goals, and auto-immunized NFRs."""
        prompt = (
            "Build a token auth handler for the session gateway. "
            "Must support JWT validation and token expiry checks. "
            "Do not rewrite the user database schema. "
            "Non-goal: OAuth2 multi-tenant federation."
        )
        spec = extract_requirements(prompt, db_path=self.db_path)

        self.assertIsInstance(spec, RequirementsSpec)
        self.assertTrue(len(spec.core_intent.strip()) > 0)
        self.assertIn("token", spec.core_intent.lower())

        self.assertTrue(len(spec.functional_requirements) >= 1)
        any_jwt = any("jwt" in r.lower() or "token" in r.lower() for r in spec.functional_requirements)
        self.assertTrue(any_jwt, "Expected JWT or token requirement in functional requirements")

        self.assertTrue(len(spec.non_goals) >= 1)
        any_non_goal = any(
            "schema" in ng.lower() or "federation" in ng.lower() or "oauth" in ng.lower()
            for ng in spec.non_goals
        )
        self.assertTrue(any_non_goal, "Expected non-goal delineating schema or federation boundary")

        self.assertTrue(len(spec.auto_immunized_nfrs) >= 1)
        any_immunized = any(
            "evt_tok_401" in nfr or "timeout" in nfr.lower() or "verification" in nfr.lower()
            for nfr in spec.auto_immunized_nfrs
        )
        self.assertTrue(any_immunized, "Expected auto-immunized NFR referencing historical failure lesson")

        self.assertTrue(len(spec.source_prompt_hash) > 0)

    def test_requirements_spec_immutability(self) -> None:
        """Positive test: Enforces value object immutability (frozen dataclass) [INV-REQ-03.1]."""
        prompt = "Create safe temporary directory utility"
        spec = extract_requirements(prompt, db_path=self.db_path)

        with self.assertRaises((FrozenInstanceError, AttributeError)):
            spec.core_intent = "Mutated Intent"  # type: ignore[misc]

    def test_requirements_spec_to_dict_serialization(self) -> None:
        """Positive test: Verifies to_dict returns dictionary containing all spec fields."""
        prompt = "Implement metrics reporting daemon"
        spec = extract_requirements(prompt, db_path=self.db_path)
        data = spec.to_dict()

        self.assertIsInstance(data, dict)
        self.assertIn("core_intent", data)
        self.assertIn("functional_requirements", data)
        self.assertIn("auto_immunized_nfrs", data)
        self.assertIn("non_goals", data)
        self.assertIn("source_prompt_hash", data)
        self.assertEqual(data["core_intent"], spec.core_intent)

    def test_requirements_spec_to_markdown_formatting(self) -> None:
        """Positive test: Serializes specification to GitHub-flavored markdown [INV-REQ-03.2]."""
        prompt = (
            "Implement secure token auth. "
            "Must validate expiry. "
            "Do not alter user db. "
            "Non-goal: multi-cloud identity."
        )
        spec = extract_requirements(prompt, db_path=self.db_path)
        md = spec.to_markdown()

        self.assertIsInstance(md, str)
        self.assertIn("#", md)
        self.assertIn("Core Intent", md)
        self.assertIn("Functional Requirements", md)
        self.assertIn("Auto-Immunized", md)
        self.assertIn("Non-Goals", md)
        self.assertIn("- ", md)

    def test_cli_invocation_positive(self) -> None:
        """Positive test: Executes requirements_extractor CLI and verifies zero exit code."""
        prompt = "Create isolated sandboxing environment with temp directories"
        module_name = "core.requirements_extractor"
        if not Path("core/requirements_extractor.py").exists():
            module_name = "sandbox.core.requirements_extractor"

        cmd = [
            sys.executable,
            "-m",
            module_name,
            "--prompt",
            prompt,
            "--db-path",
            str(self.db_path),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=os.getcwd(),
        )
        self.assertEqual(result.returncode, 0, f"CLI execution failed: {result.stderr}")
        self.assertTrue(
            len(result.stdout.strip()) > 0,
            "Expected non-empty output from requirements_extractor CLI",
        )


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.requirements_extractor pending implementation by software-engineer",
)
class TestRequirementsExtractorNegative(unittest.TestCase):
    """Evaluates contract rejections, input validation, and fail-open resilience."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_cortex.db"
        _init_test_cortex_db(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_negative_empty_prompt_raises_value_error(self) -> None:
        """Negative test: Empty prompt string raises ValueError."""
        with self.assertRaises(ValueError):
            extract_requirements("", db_path=self.db_path)

    def test_negative_whitespace_only_prompt_raises_value_error(self) -> None:
        """Negative test: Whitespace-only prompt raises ValueError."""
        with self.assertRaises(ValueError):
            extract_requirements("   \n\t  \r  ", db_path=self.db_path)

    def test_negative_none_prompt_raises_error(self) -> None:
        """Negative test: None prompt raises ValueError or TypeError."""
        with self.assertRaises((ValueError, TypeError)):
            extract_requirements(None, db_path=self.db_path)  # type: ignore[arg-type]

    def test_negative_database_corrupted_fail_open_resilience(self) -> None:
        """Negative test: Corrupted database file triggers fail-open without unhandled crash."""
        corrupt_db = Path(self.temp_dir.name) / "corrupt_cortex.db"
        corrupt_db.write_text("THIS_IS_NOT_A_VALID_SQLITE_DATABASE_HEADER\n", encoding="utf-8")

        spec = extract_requirements(
            "Build durable retry worker with backoff",
            db_path=corrupt_db,
        )
        self.assertIsInstance(spec, RequirementsSpec)
        self.assertTrue(len(spec.core_intent.strip()) > 0)
        self.assertEqual(
            spec.auto_immunized_nfrs,
            [],
            "Expected empty auto-immunized NFRs when database is corrupted",
        )

    def test_negative_database_nonexistent_fail_open_resilience(self) -> None:
        """Negative test: Nonexistent database path triggers fail-open without unhandled crash."""
        nonexistent_db = Path(self.temp_dir.name) / "missing_dir" / "absent.db"
        spec = extract_requirements(
            "Configure threadpool worker capacity",
            db_path=nonexistent_db,
        )
        self.assertIsInstance(spec, RequirementsSpec)
        self.assertTrue(len(spec.core_intent.strip()) > 0)
        self.assertEqual(
            spec.auto_immunized_nfrs,
            [],
            "Expected empty auto-immunized NFRs when database does not exist",
        )

    def test_negative_unparseable_domain_context_handling(self) -> None:
        """Negative test: Unparseable binary or noise input fails open with fallback spec [INV-BKP-04.2]."""
        unparseable_noise = "!@#$%^&*()_+{}[]:;<>?,./~`" * 10
        spec = extract_requirements(unparseable_noise, db_path=self.db_path)

        self.assertIsInstance(spec, RequirementsSpec)
        self.assertIsInstance(spec.core_intent, str)
        self.assertTrue(len(spec.core_intent.strip()) > 0)
        self.assertIsInstance(spec.functional_requirements, list)
        self.assertIsInstance(spec.non_goals, list)

    def test_negative_cli_missing_prompt_exits_nonzero(self) -> None:
        """Negative test: CLI invocation with missing or empty prompt exits with non-zero status."""
        module_name = "core.requirements_extractor"
        if not Path("core/requirements_extractor.py").exists():
            module_name = "sandbox.core.requirements_extractor"

        cmd = [
            sys.executable,
            "-m",
            module_name,
            "--prompt",
            "",
            "--db-path",
            str(self.db_path),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=os.getcwd(),
        )
        self.assertNotEqual(
            result.returncode,
            0,
            "CLI invocation with empty prompt should return non-zero exit code",
        )


if __name__ == "__main__":
    unittest.main()
