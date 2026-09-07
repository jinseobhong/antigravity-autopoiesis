"""
Companion IV&V Test Suite for State Ledger Rolling Compactor & Cortex Snapshot Engine.

Evaluates core.state_compactor and core.cortex_docs.snapshot_state_ledger
conforming to NASA SP-2016-6105 and AST Anti-Cheat H-CODE-1..12 with >= 40% negative assertion ratio.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Dict, List
import unittest

try:
    from core.cortex_docs import init_cortex_db, snapshot_state_ledger
    from core.state_compactor import (
        _build_compacted_content,
        _parse_promoted_row,
        compact_state_ledger,
        count_promoted_kanban_nodes,
        count_total_promoted_tasks,
        extract_promoted_table_rows,
        generate_archive_markdown,
    )
except ModuleNotFoundError:
    from sandbox.core.cortex_docs import init_cortex_db, snapshot_state_ledger
    from sandbox.core.state_compactor import (
        _build_compacted_content,
        _parse_promoted_row,
        compact_state_ledger,
        count_promoted_kanban_nodes,
        count_total_promoted_tasks,
        extract_promoted_table_rows,
        generate_archive_markdown,
    )


SAMPLE_LEDGER_HEADER = (
    "---\n"
    'id: "STATE-20260907-test"\n'
    'title: "Test Sprint Compass"\n'
    'status: "ACCEPTED"\n'
    'owner: "Platform Architecture Team"\n'
    'last_reviewed: "2026-09-07"\n'
    "---\n\n"
    "# Test Sprint Compass\n\n"
    "## 3. Active Sprint Radar & Kanban Board\n\n"
    "```mermaid\n"
    "flowchart TD\n"
    '    subgraph ColPromoted ["5. PROMOTED (Recent 5 Active Horizon)"]\n'
    '        PRM_ARCH["TASK-001..026: Archived to document.db (state_revisions)"]\n'
)

SAMPLE_KANBAN_NODES = (
    '        PRM_127["TASK-027: Baker Linker (v1.0)"]\n'
    '        PRM_128["TASK-028: Interrogator Engine (v1.0)"]\n'
    '        PRM_129["TASK-029: Retry Policy (v1.0)"]\n'
    '        PRM_130["TASK-030: Evolutionary Engine (v1.0)"]\n'
    '        PRM_131["TASK-031: Baseline Hook (v1.0)"]\n'
    '        PRM_132["TASK-032: Advisory Agents (v1.0)"]\n'
    '        PRM_133["TASK-033: Shadow Grounding (v1.0)"]\n'
    '        PRM_134["TASK-034: Redundant Duplicates (v1.0)"]\n'
    '        PRM_135["TASK-035: Living Architecture (v1.0)"]\n'
    '        PRM_136["TASK-036: State Compactor (v1.0)"]\n'
    "    end\n"
    "```\n\n"
    "### 3.2 Current State Task Ledger\n\n"
    "| Task ID | Task Description | Lifecycle Status | Retries | Blast Radius Tier | Owner | Verification Gate |\n"
    "| :--- | :--- | :--- | :---: | :--- | :--- | :--- |\n"
    "| *`TASK-001..026`* | *Archived* | `ARCHIVED` | - | Multiple | Team | Merged |\n"
    "| **`TASK-027`** | Baker Linker | `PROMOTED` | 0/2 | Tier 2 | Lead | Pass |\n"
    "| **`TASK-028`** | Interrogator Engine | `PROMOTED` | 0/2 | Tier 2 | Lead | Pass |\n"
    "| **`TASK-029`** | Retry Policy | `PROMOTED` | 0/2 | Tier 2 | Engineer | Pass |\n"
    "| **`TASK-030`** | Evolutionary Engine | `PROMOTED` | 0/2 | Tier 2 | Engineer | Pass |\n"
    "| **`TASK-031`** | Baseline Hook | `PROMOTED` | 0/2 | Tier 2 | Engineer | Pass |\n"
    "| **`TASK-032`** | Advisory Agents | `PROMOTED` | 0/2 | Tier 2 | Engineer | Pass |\n"
    "| **`TASK-033`** | Shadow Grounding | `PROMOTED` | 0/2 | Tier 2 | Engineer | Pass |\n"
    "| **`TASK-034`** | Redundant Duplicates | `PROMOTED` | 0/2 | Tier 3 | Architect | Pass |\n"
    "| **`TASK-035`** | Living Architecture | `PROMOTED` | 0/2 | Tier 2 | Architect | Pass |\n"
    "| **`TASK-036`** | State Compactor | `PROMOTED` | 0/2 | Tier 2 | Architect | Pass |\n"
)


class TestStateCompactorUnit(unittest.TestCase):
    """Evaluates core state compaction and parsing operations."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.db_path = self.work_dir / "test_cortex.db"
        self.archive_dir = self.work_dir / "docs" / "archived"
        self.ledger_path = self.work_dir / "CURRENT_STATE.md"
        init_cortex_db(self.db_path)

        self.sample_content = SAMPLE_LEDGER_HEADER + SAMPLE_KANBAN_NODES
        self.ledger_path.write_text(self.sample_content, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_count_promoted_tasks_nominal(self) -> None:
        """Positive test: Correctly counts 10 promoted tasks across Kanban and table."""
        kanban_count = count_promoted_kanban_nodes(self.sample_content)
        self.assertEqual(kanban_count, 10)
        total_count = count_total_promoted_tasks(self.sample_content)
        self.assertEqual(total_count, 10)

    def test_extract_promoted_table_rows_nominal(self) -> None:
        """Positive test: Extracts 10 PromotedTaskEntry items from table."""
        entries = extract_promoted_table_rows(self.sample_content)
        self.assertEqual(len(entries), 10)
        self.assertEqual(entries[0].task_id, "TASK-027")
        self.assertEqual(entries[-1].task_id, "TASK-036")

    def test_snapshot_state_ledger_creates_revision(self) -> None:
        """Positive test: snapshot_state_ledger persists full state into cortex.db."""
        rev = snapshot_state_ledger(self.ledger_path, db_path=self.db_path)
        self.assertTrue(rev.revision_id.startswith("REV-STATE-"))
        self.assertEqual(rev.state_id, "STATE-20260907-test")

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.cursor()
            cur.execute("SELECT count(*) FROM state_revisions WHERE revision_id=?", (rev.revision_id,))
            self.assertEqual(cur.fetchone()[0], 1)
            cur.execute("SELECT count(*) FROM fts_archive_search WHERE domain_type='state'")
            self.assertGreaterEqual(cur.fetchone()[0], 1)
        finally:
            con.close()

    def test_compact_state_ledger_at_threshold(self) -> None:
        """Positive test: Compacts ledger when promoted tasks >= 10, pruning older 5 tasks."""
        report = compact_state_ledger(
            ledger_path=self.ledger_path,
            archive_dir=self.archive_dir,
            threshold=10,
            keep_recent=5,
            db_path=self.db_path,
        )
        self.assertTrue(report.compacted)
        self.assertEqual(report.pruned_count, 5)
        self.assertEqual(report.retained_count, 5)
        self.assertIsNotNone(report.snapshot_id)
        self.assertIsNotNone(report.archive_path)

        # Verify archive file exists on disk
        archive_file = Path(report.archive_path)  # type: ignore
        self.assertTrue(archive_file.exists())
        archive_content = archive_file.read_text(encoding="utf-8")
        self.assertIn("TASK-027", archive_content)
        self.assertIn("TASK-031", self.ledger_path.read_text(encoding="utf-8"))

        # Verify compacted ledger has only 5 promoted rows remaining
        remaining_entries = extract_promoted_table_rows(self.ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(len(remaining_entries), 5)

    def test_compact_state_ledger_without_archive_dir(self) -> None:
        """Positive test: Compacts ledger and snapshots to DB without creating markdown files."""
        report = compact_state_ledger(
            ledger_path=self.ledger_path,
            archive_dir=None,
            threshold=10,
            keep_recent=5,
            db_path=self.db_path,
        )
        self.assertTrue(report.compacted)
        self.assertEqual(report.pruned_count, 5)
        self.assertEqual(report.retained_count, 5)
        self.assertIsNotNone(report.snapshot_id)
        self.assertEqual(report.archive_path, "document.db (state_revisions)")

        # Verify no files created in archive_dir
        self.assertFalse(self.archive_dir.exists())

        # Verify compacted ledger has only 5 promoted rows remaining
        remaining_entries = extract_promoted_table_rows(self.ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(len(remaining_entries), 5)
        ledger_text = self.ledger_path.read_text(encoding="utf-8")
        self.assertIn("TASK-001..031: Archived to document.db (state_revisions)", ledger_text)

    def test_generate_archive_markdown_format(self) -> None:
        """Positive test: Verifies archive markdown conforms to YAML frontmatter standard."""
        entries = extract_promoted_table_rows(self.sample_content)[:2]
        md = generate_archive_markdown(entries, "TASK-027", "TASK-028")
        self.assertTrue(md.startswith("---"))
        self.assertIn("id: ARCHIVE-", md)
        self.assertIn("TASK-027", md)
        self.assertIn("TASK-028", md)

    def test_negative_compact_skips_when_under_threshold(self) -> None:
        """Negative test: Compaction skips without mutating when promoted count < threshold."""
        short_content = (
            SAMPLE_LEDGER_HEADER
            + '        PRM_135["TASK-035: Arch (v1.0)"]\n    end\n```\n\n'
            + "### 3.2 Current State Task Ledger\n\n"
            + "| Task ID | Task Description | Lifecycle Status | Retries | Blast Radius Tier | Owner | Gate |\n"
            + "| :--- | :--- | :--- | :---: | :--- | :--- | :--- |\n"
            + "| **`TASK-035`** | Arch | `PROMOTED` | 0/2 | Tier 2 | Architect | Pass |\n"
        )
        self.ledger_path.write_text(short_content, encoding="utf-8")
        report = compact_state_ledger(
            ledger_path=self.ledger_path,
            archive_dir=self.archive_dir,
            threshold=10,
            keep_recent=5,
            db_path=self.db_path,
        )
        self.assertFalse(report.compacted)
        self.assertEqual(report.pruned_count, 0)
        self.assertIn("below threshold", str(report.explanation))

    def test_negative_compact_nonexistent_file_fail_open(self) -> None:
        """Negative test: Non-existent ledger path fails open cleanly without raising exception."""
        missing_path = self.work_dir / "NONEXISTENT_STATE.md"
        report = compact_state_ledger(
            ledger_path=missing_path,
            archive_dir=self.archive_dir,
            threshold=10,
            keep_recent=5,
            db_path=self.db_path,
        )
        self.assertFalse(report.compacted)
        self.assertEqual(report.pruned_count, 0)
        self.assertIn("does not exist", str(report.explanation))

    def test_negative_parse_promoted_row_malformed(self) -> None:
        """Negative test: Truncated or non-promoted row returns None."""
        self.assertIsNone(_parse_promoted_row("| not enough cols |"))
        self.assertIsNone(_parse_promoted_row("| TASK-001..026 | Archived | ARCHIVED | - | M | T | P |"))
        self.assertIsNone(_parse_promoted_row("plain text line without pipes"))
        self.assertIsNone(_parse_promoted_row(""))

    def test_negative_count_promoted_kanban_nodes_empty(self) -> None:
        """Negative test: Content without ColPromoted returns 0."""
        self.assertEqual(count_promoted_kanban_nodes("No mermaid chart here"), 0)
        self.assertEqual(count_promoted_kanban_nodes("```mermaid\nflowchart TD\n```"), 0)

    def test_negative_extract_promoted_rows_empty_table(self) -> None:
        """Negative test: Content without ledger table or only active tasks returns empty."""
        empty_table = (
            "### 3.2 Current State Task Ledger\n\n"
            "| Task ID | Desc | Status | Retries | Tier | Owner | Gate |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| **TASK-100** | In flight | IN_PROGRESS | 0/2 | Tier 2 | Eng | Gate |\n"
        )
        self.assertEqual(len(extract_promoted_table_rows(empty_table)), 0)
        self.assertEqual(len(extract_promoted_table_rows("")), 0)
        self.assertEqual(len(extract_promoted_table_rows("No table header here")), 0)
        self.assertEqual(len(extract_promoted_table_rows("### 3.2 Current State Task Ledger\n| only header |")), 0)

    def test_negative_compact_empty_or_whitespace_ledger(self) -> None:
        """Negative test: Compacting empty or whitespace ledger handles fail-open without crash."""
        empty_file = self.work_dir / "EMPTY_STATE.md"
        empty_file.write_text("   \n\n   ", encoding="utf-8")
        report = compact_state_ledger(
            ledger_path=empty_file,
            archive_dir=None,
            threshold=10,
            keep_recent=5,
            db_path=self.db_path,
        )
        self.assertFalse(report.compacted)
        self.assertEqual(report.pruned_count, 0)
        self.assertEqual(report.retained_count, 0)
        self.assertIsNone(report.snapshot_id)
        self.assertIn("below threshold", str(report.explanation))

    def test_negative_assertion_ratio(self) -> None:
        """Verifies test suite maintains elevated negative assertion ratio >= 30%."""
        test_path = Path(__file__).resolve()
        tree = ast.parse(test_path.read_text(encoding="utf-8"))

        total_assertions = 0
        negative_assertions = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                is_negative = node.name.startswith("test_negative_")
                for subnode in ast.walk(node):
                    if isinstance(subnode, ast.Call):
                        func = subnode.func
                        if isinstance(func, ast.Attribute) and func.attr.startswith("assert"):
                            total_assertions += 1
                            if is_negative:
                                negative_assertions += 1

        self.assertGreater(total_assertions, 0)
        ratio = negative_assertions / total_assertions
        self.assertGreaterEqual(
            ratio,
            0.30,
            f"Negative assertion ratio {ratio:.2%} violates >= 30% contract minimum",
        )
        self.assertGreaterEqual(
            ratio,
            0.40,
            f"Negative assertion ratio {ratio:.2%} violates >= 40% adversarial standard (H-CODE-3)",
        )


if __name__ == "__main__":
    unittest.main()
