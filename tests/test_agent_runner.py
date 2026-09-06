"""
Companion unit test suite for core.agent_runner (TASK-014).
Validates standalone agent parsing, discovery, isolated subprocess execution,
review panel coordination, and [INV-GRILL-07] timeout fail-closed hold.
Enforces AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12 with >= 30% negative tests.
"""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

try:
    from core.agent_runner import (
        DEFAULT_AGENTS_DIR,
        EXIT_CODE_DEFECTS,
        EXIT_CODE_ERROR,
        EXIT_CODE_ON_HOLD,
        EXIT_CODE_SUCCESS,
        EXIT_CODE_TIMEOUT,
        AgentExecutionBounds,
        AgentExecutionResult,
        AgentManifest,
        execute_agent_subprocess,
        execute_review_panel,
        list_available_agents,
        main,
        parse_agent_manifest,
    )
except ModuleNotFoundError:
    from sandbox.core.agent_runner import (
        DEFAULT_AGENTS_DIR,
        EXIT_CODE_DEFECTS,
        EXIT_CODE_ERROR,
        EXIT_CODE_ON_HOLD,
        EXIT_CODE_SUCCESS,
        EXIT_CODE_TIMEOUT,
        AgentExecutionBounds,
        AgentExecutionResult,
        AgentManifest,
        execute_agent_subprocess,
        execute_review_panel,
        list_available_agents,
        main,
        parse_agent_manifest,
    )


class TestAgentRunnerManifest(unittest.TestCase):
    """Evaluates agent manifest parsing, frontmatter extraction, and agent discovery."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_positive_parse_agent_manifest_valid(self) -> None:
        """Verifies parsing of an existing agent manifest from .agents/agents."""
        manifest = parse_agent_manifest("technical-reviewer-architecture")
        self.assertEqual(manifest.name, "technical-reviewer-architecture")
        self.assertEqual(manifest.role, "subagent")
        self.assertIn("view_file", manifest.tools)
        self.assertIn("grep_search", manifest.tools)
        self.assertEqual(manifest.execution_bounds.timeout_seconds, 300)
        self.assertEqual(manifest.execution_bounds.workspace_mode, "inherit")
        self.assertGreater(len(manifest.prompt), 50)
        self.assertTrue(manifest.filepath.endswith("technical-reviewer-architecture.md"))

    def test_positive_parse_agent_manifest_with_comments(self) -> None:
        """Verifies that inline comments in frontmatter fields are cleanly stripped."""
        spec_content = (
            "---\n"
            "name: custom-worker # Worker ID\n"
            "description: Custom worker agent # Description\n"
            "role: primary # Operational role\n"
            "tools:\n"
            "  - run_command # Execution\n"
            "  - view_file # Inspection\n"
            "execution_bounds:\n"
            "  timeout_seconds: 450\n"
            "  workspace_mode: isolated\n"
            "---\n\n"
            "# Custom Worker Directive\n"
            "Perform verified task execution.\n"
        )
        agent_file = self.base_dir / "custom-worker.md"
        agent_file.write_text(spec_content, encoding="utf-8")

        manifest = parse_agent_manifest(str(agent_file))
        self.assertEqual(manifest.name, "custom-worker")
        self.assertEqual(manifest.role, "primary")
        self.assertEqual(manifest.description, "Custom worker agent")
        self.assertEqual(manifest.tools, ["run_command", "view_file"])
        self.assertEqual(manifest.execution_bounds.timeout_seconds, 450)
        self.assertEqual(manifest.execution_bounds.workspace_mode, "isolated")

    def test_positive_list_available_agents(self) -> None:
        """Verifies discovery of registered agent personas in repository."""
        agents = list_available_agents()
        self.assertGreaterEqual(len(agents), 8)
        names = {a.name for a in agents}
        self.assertIn("socratic-interviewer", names)
        self.assertIn("technical-reviewer-architecture", names)
        self.assertIn("technical-reviewer-resilience", names)
        self.assertIn("technical-reviewer-ergonomics", names)

    def test_negative_parse_agent_manifest_nonexistent_file(self) -> None:
        """Rejects non-existent agent names or paths with FileNotFoundError."""
        with self.assertRaises(FileNotFoundError) as ctx:
            parse_agent_manifest("nonexistent-agent-persona-xyz")
        self.assertIn("Agent specification not found", str(ctx.exception))

    def test_negative_parse_agent_manifest_missing_frontmatter(self) -> None:
        """Rejects files lacking the mandatory leading '---' delimiter."""
        invalid_file = self.base_dir / "invalid_agent.md"
        invalid_file.write_text("# Pure Markdown Document\nNo frontmatter here.\n", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            parse_agent_manifest(str(invalid_file))
        self.assertIn("lacks mandatory leading YAML frontmatter", str(ctx.exception))

    def test_negative_parse_agent_manifest_missing_name(self) -> None:
        """Rejects frontmatter missing the mandatory 'name' key."""
        invalid_file = self.base_dir / "no_name_agent.md"
        invalid_file.write_text(
            "---\ndescription: Missing name\nrole: subagent\n---\nPrompt here.\n",
            encoding="utf-8",
        )

        with self.assertRaises(ValueError) as ctx:
            parse_agent_manifest(str(invalid_file))
        self.assertIn("missing mandatory 'name'", str(ctx.exception))

    def test_negative_list_available_agents_nonexistent_dir(self) -> None:
        """Returns an empty list when target agents directory does not exist."""
        nonexistent_path = self.base_dir / "nonexistent_subfolder"
        agents = list_available_agents(agents_dir=nonexistent_path)
        self.assertEqual(agents, [])


class TestAgentRunnerExecution(unittest.TestCase):
    """Evaluates subprocess isolation, watchdog timeouts, and review panel coordination."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_positive_execute_agent_subprocess_success(self) -> None:
        """Verifies successful out-of-process agent execution on a valid target."""
        target_file = self.base_dir / "valid_sample.py"
        target_file.write_text("# Valid source\nprint('hello')\n", encoding="utf-8")

        result = execute_agent_subprocess(
            agent_name="technical-reviewer-architecture",
            target=str(target_file),
        )

        self.assertEqual(result.exit_code, EXIT_CODE_SUCCESS)
        self.assertEqual(result.status, "APPROVED")
        self.assertGreater(result.duration_ms, 0.0)
        self.assertIn("Worker execution complete", result.output)
        self.assertEqual(result.defects, [])
        self.assertIsNone(result.error)

    def test_positive_execute_review_panel_code(self) -> None:
        """Verifies coordinated 3-reviewer parallel panel for code review."""
        target_file = self.base_dir / "code_target.py"
        target_file.write_text("# Target file\n", encoding="utf-8")

        panel_res = execute_review_panel(panel_type="code", target_path=str(target_file))
        self.assertEqual(panel_res["verdict"], "APPROVED")
        self.assertEqual(panel_res["exit_code"], EXIT_CODE_SUCCESS)
        self.assertEqual(panel_res["total_defects"], 0)
        self.assertEqual(len(panel_res["results"]), 3)

        agent_names = [r["agent_name"] for r in panel_res["results"]]
        self.assertIn("technical-reviewer-architecture", agent_names)
        self.assertIn("technical-reviewer-resilience", agent_names)
        self.assertIn("technical-reviewer-ergonomics", agent_names)

    def test_positive_execute_review_panel_doc(self) -> None:
        """Verifies coordinated 3-reviewer parallel panel for documentation review."""
        target_doc = self.base_dir / "doc_target.md"
        target_doc.write_text("# Target Document\n", encoding="utf-8")

        panel_res = execute_review_panel(panel_type="doc", target_path=str(target_doc))
        self.assertEqual(panel_res["verdict"], "APPROVED")
        self.assertEqual(panel_res["exit_code"], EXIT_CODE_SUCCESS)
        self.assertEqual(panel_res["total_defects"], 0)
        self.assertEqual(len(panel_res["results"]), 3)

        agent_names = [r["agent_name"] for r in panel_res["results"]]
        self.assertIn("documentation-reviewer-completeness", agent_names)
        self.assertIn("documentation-reviewer-dialectic", agent_names)
        self.assertIn("documentation-reviewer-usability", agent_names)

    def test_negative_execute_agent_subprocess_nonexistent_target(self) -> None:
        """Verifies error containment and EXIT_CODE_ERROR when target does not exist."""
        result = execute_agent_subprocess(
            agent_name="technical-reviewer-architecture",
            target=str(self.base_dir / "missing_file.py"),
        )
        self.assertEqual(result.exit_code, EXIT_CODE_ERROR)
        self.assertEqual(result.status, "ERROR")
        self.assertIsNotNone(result.error)
        self.assertIn("Worker target not found", result.error)

    def test_negative_execute_agent_subprocess_unknown_agent(self) -> None:
        """Verifies MANIFEST_ERROR containment when invoking unregistered agent."""
        result = execute_agent_subprocess(agent_name="completely-unknown-agent")
        self.assertEqual(result.exit_code, EXIT_CODE_ERROR)
        self.assertEqual(result.status, "MANIFEST_ERROR")
        self.assertIn("Failed to resolve agent manifest", result.error or "")

    def test_negative_execute_review_panel_invalid_type(self) -> None:
        """Rejects unsupported panel type with ValueError."""
        with self.assertRaises(ValueError) as ctx:
            execute_review_panel(panel_type="security", target_path=str(self.base_dir))
        self.assertIn("Invalid panel type 'security'", str(ctx.exception))

    def test_negative_timeout_watchdog_fail_closed_on_hold(self) -> None:
        """
        [INV-GRILL-07] Verifies watchdog timeout enforces fail-closed ON_HOLD status.
        Silence Is Not Consent: Subprocess hang triggers kill and returns exit code 2.
        """
        hang_agent = self.base_dir / "hanging-agent.md"
        hang_agent.write_text(
            "---\n"
            "name: hanging-agent\n"
            "description: Agent that simulates an unresponsive hang\n"
            "role: subagent\n"
            "tools:\n"
            "  - view_file\n"
            "execution_bounds:\n"
            "  timeout_seconds: 1\n"
            "  workspace_mode: inherit\n"
            "---\n\n"
            "# Hanging Agent\n",
            encoding="utf-8",
        )

        import subprocess
        original_popen = subprocess.Popen

        class HangingPopen(original_popen):
            def communicate(self, input=None, timeout=None):
                if timeout is not None:
                    raise subprocess.TimeoutExpired(cmd="hanging-agent", timeout=timeout)
                return ("", "")

        with patch("subprocess.Popen", side_effect=HangingPopen):
            result = execute_agent_subprocess(
                agent_name=str(hang_agent),
                timeout_override=0.1,
            )

        self.assertEqual(result.exit_code, EXIT_CODE_ON_HOLD)
        self.assertEqual(result.status, "ON_HOLD")
        self.assertIn("quarantined in ON_HOLD state per [INV-GRILL-07]", result.error or "")

    def test_positive_cli_list_json(self) -> None:
        """Verifies CLI list subcommand executes and returns exit code 0."""
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["list", "--json"])
        self.assertEqual(code, EXIT_CODE_SUCCESS)
        self.assertIn("technical-reviewer-architecture", buf.getvalue())

    def test_positive_cli_inspect_json(self) -> None:
        """Verifies CLI inspect subcommand executes and returns exit code 0."""
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["inspect", "--agent", "technical-reviewer-architecture", "--json"])
        self.assertEqual(code, EXIT_CODE_SUCCESS)
        self.assertIn("technical-reviewer-architecture", buf.getvalue())

    def test_positive_execute_agent_subprocess_grounding(self) -> None:
        """Verifies grounding directives are automatically injected into agent subprocess."""
        target_file = self.base_dir / "sample_grounding.py"
        target_file.write_text("# Target for grounding verification\n", encoding="utf-8")

        result = execute_agent_subprocess(
            agent_name="technical-reviewer-architecture",
            target=str(target_file),
            context={"custom_key": "val"},
        )
        self.assertEqual(result.exit_code, EXIT_CODE_SUCCESS)
        self.assertIsNotNone(result.grounding)
        self.assertIn("### Cognitive Grounding Directives", result.grounding or "")

    def test_negative_cli_missing_arguments(self) -> None:
        """Verifies CLI raises SystemExit when required arguments are missing."""
        import io
        from contextlib import redirect_stderr
        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit):
                main(["inspect"])


if __name__ == "__main__":
    unittest.main()
