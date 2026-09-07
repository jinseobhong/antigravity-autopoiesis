"""
Companion IV&V test suite for Shadow Grounding Injector Engine (TASK-033).

Normative reference: CONTRACT-20260907-cortex-purification-and-grounding.
Evaluates role-specialized grounding retrieval, SLA latency bounds (< 15ms),
FTS5 sanitization, fail-open resilience, zero boilerplate invariants,
and CLI execution behavior.
Conforms to:
- AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12
- [INV-GRD-01] through [INV-GRD-10]
- Negative test assertion ratio >= 30%
"""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from core.shadow_grounding import (
    ShadowGroundingDirective,
    ShadowGroundingProfile,
    ShadowGroundingResult,
    close_cached_connections,
    get_shadow_grounding,
)


class TestShadowGroundingContractInvariants(unittest.TestCase):
    """Evaluates core contract invariants and data model immutability."""

    @classmethod
    def tearDownClass(cls) -> None:
        """Deterministic cleanup of cached database connections."""
        close_cached_connections()

    def test_value_objects_instantiation_and_immutability(self) -> None:
        """[INV-GRD-01] Evaluates frozen immutability of grounding data models."""
        directive = ShadowGroundingDirective(
            component="agent_architecture",
            outcome="SUCCESS",
            directive="Subagents are read-only clones.",
            solution="Demote to advisory.",
            root_cause="Multi-agent write conflicts.",
        )
        self.assertEqual(directive.component, "agent_architecture")
        self.assertEqual(directive.outcome, "SUCCESS")
        with self.assertRaises(Exception):
            directive.component = "mutated"  # type: ignore[misc]

        profile = ShadowGroundingProfile(
            role="contrarian",
            directives=(directive,),
            prompt_block="> [!IMPORTANT]",
        )
        self.assertEqual(profile.role, "contrarian")
        self.assertEqual(len(profile.directives), 1)
        with self.assertRaises(Exception):
            profile.role = "mutated"  # type: ignore[misc]

        result = ShadowGroundingResult(
            task_query="Test query",
            elapsed_ms=4.2,
            profiles={"contrarian": profile},
        )
        self.assertEqual(result.task_query, "Test query")
        self.assertIn("contrarian", result.profiles)
        with self.assertRaises(Exception):
            result.task_query = "mutated"  # type: ignore[misc]

    def test_positive_retrieval_and_sla(self) -> None:
        """[INV-GRD-02, 03, 04] Evaluates multi-role retrieval and 15ms SLA."""
        result = get_shadow_grounding(
            task_query="Refactor cache vacuum policy",
            roles=("contrarian", "red_team", "complex_ai"),
            limit_per_role=3,
        )
        self.assertIsInstance(result, ShadowGroundingResult)
        self.assertEqual(result.task_query, "Refactor cache vacuum policy")
        self.assertLessEqual(
            result.elapsed_ms,
            15.0,
            f"Execution time {result.elapsed_ms}ms exceeded 15.0ms SLA",
        )
        self.assertIn("contrarian", result.profiles)
        self.assertIn("red_team", result.profiles)
        self.assertIn("complex_ai", result.profiles)

    def test_zero_boilerplate_in_retrieved_directives(self) -> None:
        """[INV-GRD-06] Invariant: Grounding directives must contain zero spam."""
        result = get_shadow_grounding(
            task_query="preflight compliance test",
            roles=("contrarian", "red_team", "complex_ai"),
            limit_per_role=5,
        )
        banned_phrases = (
            "investigate preflight check output",
            "all verification gates cleared",
            "resolve regression in 'test_",
        )
        for role, profile in result.profiles.items():
            for d in profile.directives:
                lower_text = d.directive.lower()
                for banned in banned_phrases:
                    self.assertNotIn(
                        banned,
                        lower_text,
                        f"Found banned boilerplate in role {role}: {d.directive}",
                    )

    def test_positive_prompt_block_formatting(self) -> None:
        """Evaluates Markdown prompt block formatting conforming to UI standards."""
        result = get_shadow_grounding(
            task_query="Windows subprocess execution",
            roles=("red_team",),
            limit_per_role=2,
        )
        profile = result.profiles.get("red_team")
        self.assertIsNotNone(profile)
        assert profile is not None
        if profile.directives:
            self.assertIn("> [!IMPORTANT]", profile.prompt_block)
            self.assertIn("Role: red_team", profile.prompt_block)
            self.assertIn("> 1. **[", profile.prompt_block)

    def test_positive_cli_execution_and_json_payload(self) -> None:
        """[INV-GRD-07] Evaluates standalone CLI returning exit code 0 and JSON."""
        cmd = [
            sys.executable,
            "-m",
            "core.shadow_grounding",
            "--task",
            "Concurrency retry test",
            "--json",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10.0,
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertIn("task_query", data)
        self.assertIn("elapsed_ms", data)
        self.assertIn("profiles", data)
        self.assertIn("red_team", data["profiles"])


class TestShadowGroundingNegativeAndAdversarial(unittest.TestCase):
    """Adversarial fault injection and negative boundary evaluation (>= 30%)."""

    @classmethod
    def tearDownClass(cls) -> None:
        """Deterministic cleanup of cached database connections."""
        close_cached_connections()

    def test_negative_empty_task_query(self) -> None:
        """Negative test: Empty task string returns clean fallback without crash."""
        result = get_shadow_grounding(task_query="")
        self.assertEqual(result.task_query, "")
        self.assertIsInstance(result.profiles, dict)
        self.assertIn("contrarian", result.profiles)

    def test_negative_whitespace_only_query(self) -> None:
        """Negative test: Whitespace-only string handled gracefully."""
        result = get_shadow_grounding(task_query="   \t\n  ")
        self.assertEqual(result.task_query, "")
        self.assertIsInstance(result.profiles, dict)

    def test_negative_nonexistent_database_path(self) -> None:
        """Negative test: Nonexistent DB path returns empty profiles fail-open."""
        fake_db = Path("data/nonexistent_phantom_vault.db")
        result = get_shadow_grounding(
            task_query="Any task",
            db_path=fake_db,
        )
        self.assertEqual(result.profiles, {})
        self.assertLessEqual(result.elapsed_ms, 15.0)

    def test_negative_sql_injection_resilience(self) -> None:
        """Negative test: Malicious SQL injection tokens sanitized without crash."""
        malicious_input = (
            "'; DROP TABLE episodic_events; -- \" OR 1=1 MATCH '***' AND NOT"
        )
        result = get_shadow_grounding(
            task_query=malicious_input,
            roles=("red_team",),
            limit_per_role=2,
        )
        self.assertIsInstance(result, ShadowGroundingResult)
        self.assertIn("red_team", result.profiles)

    def test_negative_unknown_clone_role(self) -> None:
        """Negative test: Unregistered role returns valid profile with generic title."""
        result = get_shadow_grounding(
            task_query="Security audit",
            roles=("unregistered_quantum_hacker",),
            limit_per_role=2,
        )
        self.assertIn("unregistered_quantum_hacker", result.profiles)
        prof = result.profiles["unregistered_quantum_hacker"]
        self.assertEqual(prof.role, "unregistered_quantum_hacker")

    def test_negative_zero_or_negative_limit(self) -> None:
        """Negative test: Limit <= 0 returns zero directives gracefully."""
        result = get_shadow_grounding(
            task_query="Refactor state",
            roles=("contrarian",),
            limit_per_role=0,
        )
        prof = result.profiles.get("contrarian")
        self.assertIsNotNone(prof)
        assert prof is not None
        self.assertEqual(len(prof.directives), 0)


if __name__ == "__main__":
    unittest.main()
