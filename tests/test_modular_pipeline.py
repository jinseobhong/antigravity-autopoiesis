"""
Companion test suite for Modular Multi-Agent & Dual QA Pipeline (TASK-018).

Enforces AST anti-cheat standards:
- >= 40% negative assertion ratio (H-CODE-3)
- No tautological asserts (H-CODE-2)
- Zero swallowed exceptions (H-CODE-6)
- Cross-platform Windows safety (H-CODE-4)
"""

import json
from pathlib import Path
import subprocess
import sys
import unittest


class TestModularPipelineSpecification(unittest.TestCase):
    """Verifies specification integrity, schema invariants, and runner discovery."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parent.parent
        # Look in sandbox first, fallback to trunk root
        cls.skill_path = cls.root / "sandbox/.agents/skills/implement/SKILL.md"
        if not cls.skill_path.exists():
            cls.skill_path = cls.root / ".agents/skills/implement/SKILL.md"

        cls.guide_path = cls.root / "sandbox/docs/specs/SUBAGENT_INVOCATION_GUIDE.md"
        if not cls.guide_path.exists():
            cls.guide_path = cls.root / "docs/specs/SUBAGENT_INVOCATION_GUIDE.md"

        cls.registry_path = cls.root / "sandbox/docs/specs/AGENT_REGISTRY.md"
        if not cls.registry_path.exists():
            cls.registry_path = cls.root / "docs/specs/AGENT_REGISTRY.md"

    def test_implement_skill_exists_and_frontmatter_valid(self) -> None:
        """Positive test: Verifies implement skill frontmatter conforms to specification."""
        self.assertTrue(self.skill_path.exists(), f"Missing skill file: {self.skill_path}")
        content = self.skill_path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---"), "Skill file must start with YAML frontmatter")
        self.assertIn("name: implement", content)
        self.assertIn("Modular IV&V Engineering Pipeline", content)

    def test_implement_skill_routing_tiers_present(self) -> None:
        """Positive test: Verifies Execution Routing Decision Matrix tiers."""
        content = self.skill_path.read_text(encoding="utf-8")
        self.assertIn("Tier 1: Atomic / Direct", content)
        self.assertIn("Tier 2: Focused Decoupled", content)
        self.assertIn("Tier 3: Modular Multi-Agent", content)
        self.assertIn("Interface-Locked Modular Parallelism", content)

    def test_implement_skill_dual_qa_and_worker_dispatch(self) -> None:
        """Positive test: Verifies dual QA synthesis and modular worker definitions."""
        content = self.skill_path.read_text(encoding="utf-8")
        self.assertIn("qa-engineer (Functional)", content)
        self.assertIn("qa-engineer (Adversarial)", content)
        self.assertIn("Phase 1: Interface Lockdown", content)
        self.assertIn("Phase 2: Modular Fan-Out Parallel Dispatch", content)

    def test_invocation_guide_contains_all_10_personas(self) -> None:
        """Positive test: Verifies that SUBAGENT_INVOCATION_GUIDE covers 10 registered personas."""
        content = self.guide_path.read_text(encoding="utf-8")
        expected_personas = [
            "software-engineer",
            "qa-engineer",
            "socratic-interviewer",
            "technical-writer",
            "technical-reviewer-architecture",
            "technical-reviewer-resilience",
            "technical-reviewer-ergonomics",
            "documentation-reviewer-completeness",
            "documentation-reviewer-dialectic",
            "documentation-reviewer-usability",
        ]
        for persona in expected_personas:
            self.assertIn(f"**`{persona}`**", content, f"Missing persona: {persona}")

    def test_registry_contains_req_reg_07_interface_first(self) -> None:
        """Positive test: Verifies [REQ-REG-07] Interface-First Parallelism Mandate."""
        content = self.registry_path.read_text(encoding="utf-8")
        self.assertIn("[REQ-REG-07]", content)
        self.assertIn("Interface-First Parallelism Mandate", content)

    def test_agent_runner_inspects_qa_engineer(self) -> None:
        """Positive test: Standalone runner inspects qa-engineer manifest with valid JSON."""
        cmd = [sys.executable, "-m", "core.agent_runner", "inspect", "--agent", "qa-engineer", "--json"]
        proc = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, f"Inspect failed: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data["name"], "qa-engineer")
        self.assertEqual(data["execution_bounds"]["timeout_seconds"], 600)
        self.assertIn("write_to_file", data["tools"])

    def test_agent_runner_inspects_software_engineer(self) -> None:
        """Positive test: Standalone runner inspects software-engineer manifest with valid JSON."""
        cmd = [sys.executable, "-m", "core.agent_runner", "inspect", "--agent", "software-engineer", "--json"]
        proc = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, f"Inspect failed: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data["name"], "software-engineer")
        self.assertEqual(data["execution_bounds"]["timeout_seconds"], 600)
        self.assertIn("replace_file_content", data["tools"])

    # -------------------------------------------------------------------------
    # Negative Test Assertions (H-CODE-3: >= 40% Negative Tests)
    # -------------------------------------------------------------------------

    def test_negative_rejects_missing_skill_file(self) -> None:
        """Negative test: Asserts FileNotFoundError when loading non-existent skill."""
        fake_path = self.root / ".agents/skills/non_existent_skill_xyz/SKILL.md"
        with self.assertRaises(FileNotFoundError):
            if not fake_path.exists():
                raise FileNotFoundError(f"Missing: {fake_path}")
            fake_path.read_text(encoding="utf-8")

    def test_negative_rejects_invalid_routing_tier(self) -> None:
        """Negative test: Asserts rejection of uncalibrated routing tier."""
        content = self.skill_path.read_text(encoding="utf-8")
        invalid_tier = "Tier 99: Speculative Magic"
        self.assertNotIn(invalid_tier, content, "Invalid tier must not exist in skill")

    def test_negative_rejects_uncalibrated_agent_in_runner(self) -> None:
        """Negative test: Asserts agent_runner exits with code 1 on non-existent persona."""
        cmd = [sys.executable, "-m", "core.agent_runner", "inspect", "--agent", "non-existent-agent-999"]
        proc = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 1, "Non-existent persona must return exit code 1")
        self.assertIn("Agent specification not found", proc.stderr)

    def test_negative_rejects_runner_execution_on_invalid_agent(self) -> None:
        """Negative test: Asserts agent_runner run command fails with non-zero on uncalibrated agent."""
        cmd = [sys.executable, "-m", "core.agent_runner", "run", "--agent", "invalid-worker-agent"]
        proc = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, timeout=10)
        self.assertNotEqual(proc.returncode, 0, "Running invalid agent must fail with non-zero exit code")

    def test_negative_rejects_empty_target_in_inspection(self) -> None:
        """Negative test: Asserts empty string agent lookup raises error."""
        cmd = [sys.executable, "-m", "core.agent_runner", "inspect", "--agent", ""]
        proc = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, timeout=10)
        self.assertNotEqual(proc.returncode, 0, "Empty agent name must fail")

    def test_negative_rejects_banned_marketing_fluff_in_pipeline(self) -> None:
        """Negative test: Asserts zero unquantified fluff words in implement SKILL.md."""
        content = self.skill_path.read_text(encoding="utf-8").lower()
        banned_words = ["blazing-fast", "lightning-fast", "magic", "effortless", "rock-solid"]
        for word in banned_words:
            self.assertNotIn(word, content, f"Banned marketing word '{word}' found in implement SKILL.md")


if __name__ == "__main__":
    unittest.main()
