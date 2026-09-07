"""Companion test suite for 4-Layer Cognitive HUD telemetry and Generative UI generator.

Verifies CognitiveHudExtractorProtocol conformance, static AST docking,
multi-layer snapshot extraction, Generative UI HTML rendering, and negative containment.
"""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from core.ast_docking_checker import verify_ast_docking
from core.cognitive_hud import (
    CognitiveHudExtractor,
    _extract_l0,
    _extract_l1,
    _extract_l2,
    _extract_l3,
    _run_cmd,
)
from core.interfaces.cognitive_hud_proto import (
    CognitiveHudExtractorProtocol,
    CognitiveHudSnapshot,
    HudLayerL0,
    HudLayerL1,
    HudLayerL2,
    HudLayerL3,
    MutationQuadrantCard,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCognitiveHudDataModels(unittest.TestCase):
    """Test data model immutability and schema invariants."""

    def test_l0_frozen_immutability(self) -> None:
        """Verify HudLayerL0 is frozen and immutable (H-CODE-4)."""
        l0 = HudLayerL0(
            viability_beacon="NOMINAL",
            active_task_count=1,
            max_active_tasks=5,
            working_tree_clean=True,
            stop_hook_ready=True,
            last_commit_sha="abcdef1",
            last_commit_message="feat: initial",
        )
        self.assertEqual(l0.viability_beacon, "NOMINAL")
        with self.assertRaises(FrozenInstanceError):
            l0.active_task_count = 2  # type: ignore

    def test_l1_frozen_immutability(self) -> None:
        """Verify HudLayerL1 is frozen and immutable."""
        l1 = HudLayerL1(
            simplicity_vs_extensibility=0.85,
            latency_vs_memory=0.90,
            mutation_rate_vs_stability=0.95,
            cognitive_burden_score=2,
            friction_summary="Optimal",
        )
        self.assertEqual(l1.cognitive_burden_score, 2)
        with self.assertRaises(FrozenInstanceError):
            l1.cognitive_burden_score = 5  # type: ignore

    def test_l2_quadrant_card_immutability(self) -> None:
        """Verify MutationQuadrantCard is frozen and immutable."""
        card = MutationQuadrantCard(
            task_id="TASK-999",
            q1_phenotypic_leap="Leap",
            q2_empirical_fitness="Fitness",
            q3_ergonomic_tension="Tension",
            q4_rollback_command="git revert HEAD",
        )
        self.assertEqual(card.task_id, "TASK-999")
        with self.assertRaises(FrozenInstanceError):
            card.task_id = "TASK-000"  # type: ignore

    def test_snapshot_serialization(self) -> None:
        """Verify CognitiveHudSnapshot serialization to dictionary."""
        l0 = HudLayerL0("NOMINAL", 0, 5, True, True, "sha", "msg")
        l1 = HudLayerL1(0.8, 0.8, 0.8, 2, "ok")
        l2 = HudLayerL2((), 0)
        l3 = HudLayerL3("diff", "ok", 300, 0, 0)
        snapshot = CognitiveHudSnapshot("2026-09-07T00:00:00", "/repo", l0, l1, l2, l3)

        d = snapshot.to_dict()
        self.assertIn("l0", d)
        self.assertIn("l1", d)
        self.assertIn("l2", d)
        self.assertIn("l3", d)
        self.assertEqual(d["l0"]["viability_beacon"], "NOMINAL")
        with self.assertRaises(FrozenInstanceError):
            snapshot.timestamp = "modified"  # type: ignore


class TestCognitiveHudExtractor(unittest.TestCase):
    """Test telemetry extraction, AST docking, and Generative UI HTML rendering."""

    def test_ast_docking_closure(self) -> None:
        """Verify static AST docking between protocol and implementation."""
        proto_path = REPO_ROOT / "core" / "interfaces" / "cognitive_hud_proto.py"
        impl_path = REPO_ROOT / "core" / "cognitive_hud.py"
        report = verify_ast_docking(proto_path, impl_path)
        self.assertTrue(report.is_docked)
        self.assertEqual(len(report.defects), 0)

    def test_extract_snapshot_nominal(self) -> None:
        """Verify extraction from real repository root."""
        extractor = CognitiveHudExtractor()
        snapshot = extractor.extract_snapshot(REPO_ROOT)
        self.assertIsNotNone(snapshot.timestamp)
        self.assertIn(snapshot.l0.viability_beacon, ("NOMINAL", "DEGRADED", "ALERT"))
        self.assertGreaterEqual(snapshot.l0.active_task_count, 0)
        self.assertEqual(snapshot.l0.max_active_tasks, 5)
        self.assertGreater(len(snapshot.l2.mutation_cards), 0)
        self.assertEqual(snapshot.l3.ast_compliance_defects, 0)

    def test_render_html_conformance(self) -> None:
        """Verify rendered HTML conforms to generative_ui skill and design tokens."""
        extractor = CognitiveHudExtractor()
        snapshot = extractor.extract_snapshot(REPO_ROOT)
        html_content = extractor.render_html(snapshot)

        self.assertIn("<!DOCTYPE html>", html_content)
        self.assertIn("https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js", html_content)
        self.assertIn("var(--card)", html_content)
        self.assertIn("var(--border)", html_content)
        self.assertIn("var(--foreground)", html_content)
        self.assertIn("layer-l0", html_content)
        self.assertIn("layer-l1", html_content)
        self.assertIn("layer-l2", html_content)
        self.assertIn("layer-l3", html_content)
        self.assertIn("selectTab", html_content)

    def test_protocol_abstract_raise(self) -> None:
        """Verify protocol methods raise NotImplementedError when directly invoked (H-CODE-1)."""
        with self.assertRaises(NotImplementedError):
            CognitiveHudExtractorProtocol.extract_snapshot(None, REPO_ROOT)  # type: ignore
        with self.assertRaises(NotImplementedError):
            CognitiveHudExtractorProtocol.render_html(None, None)  # type: ignore

    def test_extract_from_empty_isolated_tempdir(self) -> None:
        """Verify fail-open extraction when repository files are missing in temporary sandbox."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            extractor = CognitiveHudExtractor()
            snapshot = extractor.extract_snapshot(tmp_path)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot.l0.active_task_count, 0)
            self.assertEqual(snapshot.l0.last_commit_sha, "unknown")

    def test_run_cmd_timeout_fail_open(self) -> None:
        """Verify subprocess helper fails open on invalid command or timeout (H-CODE-7)."""
        code, out = _run_cmd(["non_existent_binary_xyz_123"], REPO_ROOT)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_cli_json_and_output(self) -> None:
        """Verify CLI execution for --json and --output flags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "hud_test.html"
            cmd = [
                sys.executable,
                "-m",
                "core.cognitive_hud",
                "--output",
                str(out_file),
                "--repo-root",
                str(REPO_ROOT),
            ]
            res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=10.0)
            self.assertEqual(res.returncode, 0)
            self.assertTrue(out_file.exists())
            self.assertGreater(out_file.stat().st_size, 500)

            # JSON CLI test
            cmd_json = [
                sys.executable,
                "-m",
                "core.cognitive_hud",
                "--json",
                "--repo-root",
                str(REPO_ROOT),
            ]
            res_json = subprocess.run(cmd_json, cwd=REPO_ROOT, capture_output=True, text=True, timeout=10.0)
            self.assertEqual(res_json.returncode, 0)
            parsed = json.loads(res_json.stdout)
            self.assertIn("l0", parsed)
            self.assertIn("l1", parsed)


if __name__ == "__main__":
    unittest.main()
