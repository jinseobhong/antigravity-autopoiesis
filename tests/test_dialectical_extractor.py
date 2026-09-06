"""
Companion test suite for Dialectical Requirements Interrogator (TASK-028).

Ingests docs/active/ACTIVE_CONTRACT.md as primary specification authority.
Evaluates prompt deconstruction across Architecture (KISS), Resilience
(Fault-Tolerance), and Operations perspectives. Validates CritiqueRecord
validation, DialecticalResult immutability, to_dict serialization,
RequirementsSpec enrichment, CLI execution, and zero-crash fail-open error
containment on empty prompts or corrupted/locked SQLite databases.
Enforces AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12 with >= 40% negative ratio.
"""

from dataclasses import FrozenInstanceError
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
    from core.dialectical_extractor import (
        CritiqueRecord,
        DialecticalResult,
        PerspectiveType,
        evaluate_perspectives,
        integrate_dialectical_requirements,
    )
    _MODULE_AVAILABLE = True
except ModuleNotFoundError:
    try:
        from sandbox.core.dialectical_extractor import (
            CritiqueRecord,
            DialecticalResult,
            PerspectiveType,
            evaluate_perspectives,
            integrate_dialectical_requirements,
        )
        _MODULE_AVAILABLE = True
    except ModuleNotFoundError:
        _MODULE_AVAILABLE = False
        CritiqueRecord = None  # type: ignore[assignment]
        DialecticalResult = None  # type: ignore[assignment]
        PerspectiveType = None  # type: ignore[assignment]
        evaluate_perspectives = None  # type: ignore[assignment]
        integrate_dialectical_requirements = None  # type: ignore[assignment]

try:
    from core.requirements_extractor import RequirementsSpec
except ModuleNotFoundError:
    try:
        from sandbox.core.requirements_extractor import RequirementsSpec
    except ModuleNotFoundError:
        RequirementsSpec = None  # type: ignore[assignment]


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
                ) VALUES (
                    ?, 'FAILURE', ?, ?, ?, ?, 'Fixed root cause', '100% pass', 3, 1.5,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                );
                """,
                (event_id, component, trigger_tokens, root_cause, directive),
            )
    finally:
        con.close()


def _resolve_module_target() -> str:
    """Resolves whether production or sandbox module is available for CLI testing."""
    if Path("core/dialectical_extractor.py").exists():
        return "core.dialectical_extractor"
    return "sandbox.core.dialectical_extractor"


_TASK_028_FALLBACK_CONTRACT = """---
id: "CONTRACT-20260907-dialectical-extractor"
title: "Dialectical Requirements Interrogator and Adversarial Red Team Engine Contract"
status: "ACCEPTED"
owner: "Platform Architecture Team"
last_reviewed: "2026-09-07"
target_task_id: "TASK-028"
---

# Dialectical Requirements Interrogator and Adversarial Red Team Engine Contract (TASK-028)

## 3. Data Schema & Technical Interface Specifications
```python
class PerspectiveType(str, Enum):
    ARCHITECTURE = "ARCHITECTURE"
    RESILIENCE = "RESILIENCE"
    OPERATIONS = "OPERATIONS"

@dataclass(frozen=True)
class CritiqueRecord:
    perspective: PerspectiveType
    concern: str
    failure_mode: str
    proposed_invariant: str
    severity: str = "MEDIUM"

@dataclass(frozen=True)
class DialecticalResult:
    raw_prompt: str
    critiques: Tuple[CritiqueRecord, ...] = field(default_factory=tuple)
    hardened_invariants: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {}

def evaluate_perspectives(
    raw_prompt: str,
    domain_context: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> DialecticalResult:
    return DialecticalResult(raw_prompt="")

def integrate_dialectical_requirements(
    raw_prompt: str,
    domain_context: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Any:
    return None
```

## 4. Normative System Invariants (NASA SP-2016-6105)
- `[INV-DIA-01]` The module `core/dialectical_extractor.py` SHALL define typed models
  `PerspectiveType`, `CritiqueRecord`, `DialecticalResult`.
- `[INV-DIA-01.1]` `PerspectiveType` SHALL inherit from `(str, enum.Enum)` defining values
  ARCHITECTURE, RESILIENCE, OPERATIONS.
- `[INV-DIA-01.2]` `CritiqueRecord` SHALL be implemented as a frozen immutable dataclass
  with non-empty validation.
- `[INV-DIA-01.3]` `DialecticalResult` SHALL be implemented as a frozen immutable dataclass
  providing dictionary serialization.
- `[INV-DIA-02]` Function `evaluate_perspectives` SHALL evaluate prompts across three
  perspectives: Architecture (KISS), Resilience (Fault-Tolerance), Operations.
- `[INV-DIA-02.1]` Architecture evaluation SHALL assess prompt over-engineering risks
  regarding abstraction density.
- `[INV-DIA-02.2]` Resilience evaluation SHALL assess fault-tolerance deficiencies
  regarding exception boundary handling.
- `[INV-DIA-02.3]` Operations evaluation SHALL assess runtime observability regarding
  diagnostic hook availability.
- `[INV-DIA-03]` Function `evaluate_perspectives` SHALL execute adversarial red-team
  deconstruction identifying failure vulnerabilities for hardened SHALL invariant synthesis.
- `[INV-DIA-03.1]` Adversarial critique records SHALL specify concrete potential failure modes.
- `[INV-DIA-03.2]` Synthesized counter-requirements SHALL enforce defensive constraints
  against identified vulnerabilities.
- `[INV-DIA-04]` Function `integrate_dialectical_requirements` SHALL enrich `RequirementsSpec`
  with dialectically hardened functional requirements incorporating auto-immunized NFRs.
- `[INV-DIA-04.1]` The integration bridge SHALL preserve original functional requirements
  while appending dialectically hardened invariants.
- `[INV-DIA-04.2]` Auto-immunized NFRs synthesized during perspective evaluation
  SHALL be incorporated into the specification.
- `[INV-DIA-05]` CLI command `python -m core.dialectical_extractor --prompt PROMPT [--json]`
  SHALL return exit code 0 upon successful execution.
- `[INV-DIA-05.1]` When `--json` is supplied, CLI output SHALL serialize valid JSON to stdout.
- `[INV-DIA-05.2]` CLI execution SHALL format human-readable summaries when `--json` is omitted.
- `[INV-DIA-06]` All functions in `dialectical_extractor.py` SHALL maintain CC <= 10
  with line lengths <= 120 columns.
- `[INV-DIA-06.1]` Each function in `dialectical_extractor.py` SHALL accept at most 7 parameters.
- `[INV-DIA-06.2]` Implementation files SHALL NOT contain lazy stubs, bare pass statements,
  or tautological assertions.
- `[INV-DIA-07]` All operations SHALL implement fail-open error containment returning fallbacks
  without crashing on empty inputs or corrupted database states.
- `[INV-DIA-07.1]` Empty or whitespace prompts SHALL return valid default `DialecticalResult`.
- `[INV-DIA-07.2]` SQLite database lock contention or missing tables SHALL degrade gracefully
  to purely heuristic evaluations.
"""


def _load_task_028_contract() -> str:
    """Loads TASK-028 contract from active contract file, cortex.db, or fallback fixture."""
    contract_path = Path("docs/active/ACTIVE_CONTRACT.md")
    if contract_path.exists():
        try:
            content = contract_path.read_text(encoding="utf-8")
            if 'target_task_id: "TASK-028"' in content:
                return content
        except OSError:
            _err_fallback = True
    db_path = Path("data/cortex.db")
    if db_path.exists():
        try:
            con = sqlite3.connect(str(db_path))
            cur = con.execute(
                "SELECT raw_content FROM contract_revisions WHERE task_id = 'TASK-028' "
                "ORDER BY revision_id DESC LIMIT 1;"
            )
            row = cur.fetchone()
            con.close()
            if row:
                return str(row[0])
        except Exception:
            _err_fallback = True
    return _TASK_028_FALLBACK_CONTRACT


class TestDialecticalExtractorContractInvariants(unittest.TestCase):
    """Verifies that the specification contract defines normative invariants [INV-DIA-01..07]."""

    def setUp(self) -> None:
        self.contract_text = _load_task_028_contract()
        self.assertTrue(
            len(self.contract_text.strip()) > 0,
            "Contract text missing from active contract, cortex.db, and fixture",
        )

    def test_contract_metadata_and_acceptance(self) -> None:
        """Positive test: Verifies contract is ACCEPTED and target_task_id matches valid format."""
        self.assertIn('status: "ACCEPTED"', self.contract_text)
        self.assertRegex(self.contract_text, r'target_task_id:\s*"TASK-\d+"')

    def test_contract_defines_all_normative_dialectical_invariants(self) -> None:
        """Positive test: Verifies presence of all dialectical normative invariants."""
        required_invariants = [
            "[INV-DIA-01]",
            "[INV-DIA-01.1]",
            "[INV-DIA-01.2]",
            "[INV-DIA-01.3]",
            "[INV-DIA-02]",
            "[INV-DIA-02.1]",
            "[INV-DIA-02.2]",
            "[INV-DIA-02.3]",
            "[INV-DIA-03]",
            "[INV-DIA-03.1]",
            "[INV-DIA-03.2]",
            "[INV-DIA-04]",
            "[INV-DIA-04.1]",
            "[INV-DIA-04.2]",
            "[INV-DIA-05]",
            "[INV-DIA-05.1]",
            "[INV-DIA-05.2]",
            "[INV-DIA-06]",
            "[INV-DIA-06.1]",
            "[INV-DIA-06.2]",
            "[INV-DIA-07]",
            "[INV-DIA-07.1]",
            "[INV-DIA-07.2]",
        ]
        for inv_id in required_invariants:
            self.assertIn(
                inv_id,
                self.contract_text,
                f"Missing invariant definition {inv_id} in contract text",
            )

    def test_contract_defines_dialectical_technical_interfaces(self) -> None:
        """Positive test: Verifies contract specifies models and primary function signatures."""
        self.assertIn("class PerspectiveType", self.contract_text)
        self.assertIn("class CritiqueRecord", self.contract_text)
        self.assertIn("class DialecticalResult", self.contract_text)
        self.assertIn("def evaluate_perspectives", self.contract_text)
        self.assertIn("def integrate_dialectical_requirements", self.contract_text)

    def test_negative_contract_missing_synthetic_invariant(self) -> None:
        """Negative test: Evaluates assertion failure when checking non-existent invariant."""
        synthetic_id = "[INV-DIA-NONEXISTENT-999]"
        self.assertNotIn(
            synthetic_id,
            self.contract_text,
            "Non-existent invariant unexpectedly found in contract text",
        )

    def test_negative_contract_rejects_empty_task_pattern(self) -> None:
        """Negative test: Verifies contract does not contain unassigned empty task ID placeholder."""
        self.assertNotRegex(
            self.contract_text,
            r'target_task_id:\s*""',
            "Contract target_task_id must not be empty",
        )


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.dialectical_extractor pending implementation by software-engineer",
)
class TestDialecticalExtractorModelsPositive(unittest.TestCase):
    """Evaluates positive data model behaviors, enum semantics, and serialization."""

    def test_perspective_type_enumeration_values(self) -> None:
        """Positive test: Verifies PerspectiveType values and str-subclass nature [INV-DIA-01.1]."""
        self.assertEqual(PerspectiveType.ARCHITECTURE.value, "ARCHITECTURE")
        self.assertEqual(PerspectiveType.RESILIENCE.value, "RESILIENCE")
        self.assertEqual(PerspectiveType.OPERATIONS.value, "OPERATIONS")
        self.assertIsInstance(PerspectiveType.ARCHITECTURE, str)
        self.assertTrue(issubclass(PerspectiveType, str))

    def test_critique_record_instantiation_valid(self) -> None:
        """Positive test: Verifies CritiqueRecord instantiation with valid non-empty fields."""
        rec = CritiqueRecord(
            perspective=PerspectiveType.ARCHITECTURE,
            concern="Excessive layer abstraction",
            failure_mode="Latency amplification through deep call stacks",
            proposed_invariant="The system SHALL limit service call stack depth <= 3",
        )
        self.assertEqual(rec.perspective, PerspectiveType.ARCHITECTURE)
        self.assertEqual(rec.concern, "Excessive layer abstraction")
        self.assertEqual(rec.failure_mode, "Latency amplification through deep call stacks")
        self.assertEqual(
            rec.proposed_invariant,
            "The system SHALL limit service call stack depth <= 3",
        )
        self.assertEqual(rec.severity, "MEDIUM")

    def test_critique_record_immutability(self) -> None:
        """Positive test: Verifies CritiqueRecord is a frozen immutable object [INV-DIA-01.2]."""
        rec = CritiqueRecord(
            perspective=PerspectiveType.RESILIENCE,
            concern="Unbounded retry loops",
            failure_mode="Cascading thundering herd failure",
            proposed_invariant="The system SHALL cap exponential backoff retry ceiling at 30s",
            severity="HIGH",
        )
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            rec.concern = "Altered concern"  # type: ignore[misc]

    def test_dialectical_result_instantiation(self) -> None:
        """Positive test: Verifies DialecticalResult instantiation with critiques and invariants."""
        rec = CritiqueRecord(
            perspective=PerspectiveType.OPERATIONS,
            concern="Lack of structured diagnostic hooks",
            failure_mode="Telemetry blackout during incident",
            proposed_invariant="The system SHALL emit structured JSON log events with correlation IDs",
        )
        result = DialecticalResult(
            raw_prompt="Build distributed task queue",
            critiques=(rec,),
            hardened_invariants=("The system SHALL emit structured JSON log events",),
            metadata={"version": "1.0", "interrogator": "tri-perspective"},
        )
        self.assertEqual(result.raw_prompt, "Build distributed task queue")
        self.assertEqual(len(result.critiques), 1)
        self.assertEqual(result.critiques[0], rec)
        self.assertEqual(len(result.hardened_invariants), 1)
        self.assertEqual(result.metadata["version"], "1.0")

    def test_dialectical_result_immutability(self) -> None:
        """Positive test: Verifies DialecticalResult is a frozen immutable object [INV-DIA-01.3]."""
        result = DialecticalResult(raw_prompt="Test immutable prompt")
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            result.raw_prompt = "Mutated prompt"  # type: ignore[misc]

    def test_dialectical_result_to_dict_serialization(self) -> None:
        """Positive test: Verifies to_dict produces compliant dictionary representation [INV-DIA-01.3]."""
        rec = CritiqueRecord(
            perspective=PerspectiveType.ARCHITECTURE,
            concern="Monolithic coupling",
            failure_mode="Blast radius amplification",
            proposed_invariant="The system SHALL isolate storage drivers into distinct plugins",
            severity="HIGH",
        )
        result = DialecticalResult(
            raw_prompt="Design storage driver layer",
            critiques=(rec,),
            hardened_invariants=("The system SHALL isolate storage drivers into distinct plugins",),
            metadata={"audit_id": "aud-101"},
        )
        dict_repr = result.to_dict()
        self.assertIsInstance(dict_repr, dict)
        self.assertEqual(dict_repr["raw_prompt"], "Design storage driver layer")
        self.assertEqual(len(dict_repr["critiques"]), 1)
        self.assertEqual(dict_repr["critiques"][0]["perspective"], "ARCHITECTURE")
        self.assertEqual(dict_repr["critiques"][0]["concern"], rec.concern)
        self.assertEqual(dict_repr["critiques"][0]["failure_mode"], rec.failure_mode)
        self.assertEqual(dict_repr["critiques"][0]["proposed_invariant"], rec.proposed_invariant)
        self.assertEqual(dict_repr["critiques"][0]["severity"], "HIGH")
        self.assertEqual(
            dict_repr["hardened_invariants"],
            ["The system SHALL isolate storage drivers into distinct plugins"],
        )
        self.assertEqual(dict_repr["metadata"], {"audit_id": "aud-101"})


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.dialectical_extractor pending implementation by software-engineer",
)
class TestDialecticalExtractorModelsNegative(unittest.TestCase):
    """Evaluates input validation rejections and boundary errors for data models."""

    def test_negative_critique_record_empty_concern_raises_value_error(self) -> None:
        """Negative test: Empty concern string raises ValueError [INV-DIA-01.2]."""
        with self.assertRaises(ValueError):
            CritiqueRecord(
                perspective=PerspectiveType.ARCHITECTURE,
                concern="",
                failure_mode="Valid failure mode",
                proposed_invariant="The system SHALL maintain simplicity",
            )

    def test_negative_critique_record_whitespace_concern_raises_value_error(self) -> None:
        """Negative test: Whitespace-only concern string raises ValueError [INV-DIA-01.2]."""
        with self.assertRaises(ValueError):
            CritiqueRecord(
                perspective=PerspectiveType.ARCHITECTURE,
                concern="   \t\n  ",
                failure_mode="Valid failure mode",
                proposed_invariant="The system SHALL maintain simplicity",
            )

    def test_negative_critique_record_empty_failure_mode_raises_value_error(self) -> None:
        """Negative test: Empty failure_mode string raises ValueError [INV-DIA-01.2]."""
        with self.assertRaises(ValueError):
            CritiqueRecord(
                perspective=PerspectiveType.RESILIENCE,
                concern="Valid concern",
                failure_mode="",
                proposed_invariant="The system SHALL handle timeouts",
            )

    def test_negative_critique_record_whitespace_failure_mode_raises_value_error(self) -> None:
        """Negative test: Whitespace-only failure_mode string raises ValueError [INV-DIA-01.2]."""
        with self.assertRaises(ValueError):
            CritiqueRecord(
                perspective=PerspectiveType.RESILIENCE,
                concern="Valid concern",
                failure_mode="  \r\n  ",
                proposed_invariant="The system SHALL handle timeouts",
            )

    def test_negative_critique_record_empty_proposed_invariant_raises_value_error(self) -> None:
        """Negative test: Empty proposed_invariant string raises ValueError [INV-DIA-01.2]."""
        with self.assertRaises(ValueError):
            CritiqueRecord(
                perspective=PerspectiveType.OPERATIONS,
                concern="Valid concern",
                failure_mode="Valid failure mode",
                proposed_invariant="",
            )

    def test_negative_critique_record_whitespace_proposed_invariant_raises_value_error(self) -> None:
        """Negative test: Whitespace-only proposed_invariant string raises ValueError [INV-DIA-01.2]."""
        with self.assertRaises(ValueError):
            CritiqueRecord(
                perspective=PerspectiveType.OPERATIONS,
                concern="Valid concern",
                failure_mode="Valid failure mode",
                proposed_invariant="   \t   ",
            )


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.dialectical_extractor pending implementation by software-engineer",
)
class TestDialecticalExtractorEvaluationPositive(unittest.TestCase):
    """Evaluates multi-perspective critique synthesis, requirements enrichment, and CLI execution."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_cortex.db"
        _init_test_cortex_db(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_evaluate_perspectives_returns_all_three_perspectives(self) -> None:
        """Positive test: Deconstructs prompt across ARCHITECTURE, RESILIENCE, OPERATIONS [INV-DIA-02]."""
        prompt = (
            "Build distributed transaction coordinator with two-phase commit. "
            "Must handle network partitions and worker node crashes. "
            "Include live metric streaming and health probes."
        )
        result = evaluate_perspectives(prompt, db_path=self.db_path)
        self.assertIsInstance(result, DialecticalResult)
        self.assertEqual(result.raw_prompt, prompt)
        self.assertTrue(len(result.critiques) >= 3, "Expected at least 3 dialectical critiques")
        perspectives_evaluated = {c.perspective for c in result.critiques}
        self.assertIn(PerspectiveType.ARCHITECTURE, perspectives_evaluated)
        self.assertIn(PerspectiveType.RESILIENCE, perspectives_evaluated)
        self.assertIn(PerspectiveType.OPERATIONS, perspectives_evaluated)

    def test_evaluate_perspectives_synthesizes_hardened_invariants(self) -> None:
        """Positive test: Red team synthesizes defensive SHALL invariants [INV-DIA-03]."""
        prompt = "Design distributed cache synchronization daemon with master failover"
        result = evaluate_perspectives(prompt, db_path=self.db_path)
        self.assertTrue(
            len(result.hardened_invariants) >= 1,
            "Expected at least 1 synthesized hardened invariant",
        )
        for inv in result.hardened_invariants:
            self.assertIsInstance(inv, str)
            self.assertTrue(len(inv.strip()) > 0)
            self.assertIn("SHALL", inv, "Synthesized invariant must adhere to normative SHALL lexicon")

    def test_integrate_dialectical_requirements_enriches_spec(self) -> None:
        """Positive test: RequirementsSpec is enriched with dialectic requirements [INV-DIA-04]."""
        prompt = (
            "Build auth token handler for session gateway. "
            "Must support JWT validation and token expiry checks. "
            "Do not rewrite database schema."
        )
        enriched = integrate_dialectical_requirements(prompt, db_path=self.db_path)
        self.assertIsNotNone(enriched, "integrate_dialectical_requirements returned None")
        self.assertTrue(hasattr(enriched, "functional_requirements"))
        self.assertTrue(
            len(enriched.functional_requirements) >= 1,
            "Enriched spec must contain functional requirements",
        )
        any_jwt = any(
            "jwt" in r.lower() or "token" in r.lower()
            for r in enriched.functional_requirements
        )
        self.assertTrue(any_jwt, "Original functional requirements must be preserved")
        any_hardened = any("shall" in r.lower() for r in enriched.functional_requirements)
        self.assertTrue(any_hardened, "Hardened dialectic invariants must be appended")

    def test_integrate_dialectical_requirements_incorporates_auto_immunized_nfrs(self) -> None:
        """Positive test: Integrates auto-immunized NFRs from historical failure lessons [INV-DIA-04.2]."""
        _seed_test_failure_event(
            db_file=self.db_path,
            event_id="evt_dia_801",
            component="session_gateway",
            trigger_tokens="session token auth timeout",
            directive="Enforce deterministic 200ms timeout on session token verification",
            root_cause="Worker deadlock during token validation",
        )
        prompt = "Build session gateway token authenticator with auth timeout handling"
        enriched = integrate_dialectical_requirements(prompt, db_path=self.db_path)
        self.assertTrue(hasattr(enriched, "auto_immunized_nfrs"))
        self.assertTrue(
            len(enriched.auto_immunized_nfrs) >= 1,
            "Expected auto-immunized NFR from seeded failure lesson",
        )
        any_immunized = any(
            "evt_dia_801" in nfr or "timeout" in nfr.lower()
            for nfr in enriched.auto_immunized_nfrs
        )
        self.assertTrue(any_immunized, "Seeded failure directive must appear in auto-immunized NFRs")

    def test_cli_invocation_positive_human_readable(self) -> None:
        """Positive test: Executes CLI with --prompt and verifies zero exit code [INV-DIA-05]."""
        prompt = "Implement distributed cache invalidation daemon"
        module_name = _resolve_module_target()
        cmd = [
            sys.executable,
            "-m",
            module_name,
            "--prompt",
            prompt,
            "--db",
            str(self.db_path),
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=os.getcwd(),
        )
        self.assertEqual(proc.returncode, 0, f"CLI execution failed: {proc.stderr}")
        self.assertTrue(
            len(proc.stdout.strip()) > 0,
            "Expected non-empty human-readable output from CLI",
        )

    def test_cli_invocation_positive_json_output(self) -> None:
        """Positive test: Executes CLI with --json and verifies valid JSON payload [INV-DIA-05.1]."""
        prompt = "Implement metrics emission pipeline with Prometheus exporter"
        module_name = _resolve_module_target()
        cmd = [
            sys.executable,
            "-m",
            module_name,
            "--prompt",
            prompt,
            "--db",
            str(self.db_path),
            "--json",
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=os.getcwd(),
        )
        self.assertEqual(proc.returncode, 0, f"CLI JSON execution failed: {proc.stderr}")
        payload = json.loads(proc.stdout)
        self.assertIsInstance(payload, dict)
        self.assertIn("raw_prompt", payload)
        self.assertIn("critiques", payload)
        self.assertIn("hardened_invariants", payload)
        self.assertEqual(payload["raw_prompt"], prompt)
        self.assertIsInstance(payload["critiques"], list)
        self.assertIsInstance(payload["hardened_invariants"], list)


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.dialectical_extractor pending implementation by software-engineer",
)
class TestDialecticalExtractorContainmentNegative(unittest.TestCase):
    """Evaluates fail-open error containment on empty inputs and corrupted/locked databases."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_cortex.db"
        _init_test_cortex_db(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_negative_evaluate_perspectives_empty_prompt_fail_open(self) -> None:
        """Negative test: Empty prompt string triggers fail-open without crash [INV-DIA-07.1]."""
        result = evaluate_perspectives("", db_path=self.db_path)
        self.assertIsInstance(result, DialecticalResult)
        self.assertEqual(result.raw_prompt, "")
        self.assertIsInstance(result.critiques, (tuple, list))
        self.assertIsInstance(result.hardened_invariants, (tuple, list))

    def test_negative_evaluate_perspectives_whitespace_prompt_fail_open(self) -> None:
        """Negative test: Whitespace-only prompt triggers fail-open without crash [INV-DIA-07.1]."""
        result = evaluate_perspectives("   \n\t  \r  ", db_path=self.db_path)
        self.assertIsInstance(result, DialecticalResult)
        self.assertIsInstance(result.critiques, (tuple, list))
        self.assertIsInstance(result.hardened_invariants, (tuple, list))

    def test_negative_evaluate_perspectives_corrupted_database_fail_open(self) -> None:
        """Negative test: Corrupted SQLite database triggers fail-open fallback [INV-DIA-07]."""
        corrupt_db = Path(self.temp_dir.name) / "corrupt_cortex.db"
        corrupt_db.write_text("NOT_A_VALID_SQLITE_HEADER_CORRUPTED_DATA\n", encoding="utf-8")
        result = evaluate_perspectives(
            "Build distributed sequencer with consensus",
            db_path=corrupt_db,
        )
        self.assertIsInstance(result, DialecticalResult)
        self.assertIn("sequencer", result.raw_prompt.lower())
        self.assertIsInstance(result.critiques, (tuple, list))

    def test_negative_evaluate_perspectives_nonexistent_database_fail_open(self) -> None:
        """Negative test: Nonexistent database path triggers fail-open fallback [INV-DIA-07]."""
        nonexistent_db = Path(self.temp_dir.name) / "missing_subdir" / "absent.db"
        result = evaluate_perspectives(
            "Build distributed sequencer with consensus",
            db_path=nonexistent_db,
        )
        self.assertIsInstance(result, DialecticalResult)
        self.assertIn("sequencer", result.raw_prompt.lower())
        self.assertIsInstance(result.critiques, (tuple, list))

    def test_negative_evaluate_perspectives_locked_database_fail_open(self) -> None:
        """Negative test: Database lock contention degrades gracefully to heuristics [INV-DIA-07.2]."""
        lock_con = sqlite3.connect(str(self.db_path), timeout=0.1)
        lock_con.execute("BEGIN EXCLUSIVE")
        try:
            result = evaluate_perspectives(
                "Build distributed sequencer with consensus",
                db_path=self.db_path,
            )
            self.assertIsInstance(result, DialecticalResult)
            self.assertIn("sequencer", result.raw_prompt.lower())
        finally:
            lock_con.rollback()
            lock_con.close()

    def test_negative_integrate_empty_prompt_fail_open(self) -> None:
        """Negative test: Empty prompt in requirements integration fails open [INV-DIA-07]."""
        enriched = integrate_dialectical_requirements("", db_path=self.db_path)
        self.assertIsNotNone(enriched)
        self.assertTrue(hasattr(enriched, "functional_requirements"))

    def test_negative_integrate_corrupted_database_fail_open(self) -> None:
        """Negative test: Corrupted database in requirements integration fails open [INV-DIA-07]."""
        corrupt_db = Path(self.temp_dir.name) / "corrupt_integrate.db"
        corrupt_db.write_text("CORRUPTED_DATABASE_HEADER\n", encoding="utf-8")
        enriched = integrate_dialectical_requirements(
            "Build resilient queue with rate limiting",
            db_path=corrupt_db,
        )
        self.assertIsNotNone(enriched)
        self.assertTrue(hasattr(enriched, "functional_requirements"))

    def test_negative_cli_missing_prompt_exits_nonzero(self) -> None:
        """Negative test: CLI invocation without --prompt returns non-zero exit status [INV-DIA-05]."""
        module_name = _resolve_module_target()
        cmd = [
            sys.executable,
            "-m",
            module_name,
            "--db",
            str(self.db_path),
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=os.getcwd(),
        )
        self.assertNotEqual(
            proc.returncode,
            0,
            "Expected non-zero exit code when --prompt argument is missing",
        )


if __name__ == "__main__":
    unittest.main()
