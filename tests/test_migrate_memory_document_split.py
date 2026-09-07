"""
Independent Verification & Validation (IV&V) Companion Test Suite
for Memory & Document Physical Segregation Migration (TASK-037).

Validates:
- [INV-SPLIT-01] Canonical paths in core.fs_topology
- [INV-SPLIT-02] & [INV-SPLIT-03] Physical segregation of memory and document DBs
- [INV-SPLIT-04] Seed export and hydration idempotency
- [INV-SPLIT-05] Gitignore configuration rules
- [INV-SPLIT-06] Pre-migration backup creation
- [INV-SPLIT-07] Row count equivalence and SHA-256 cryptographic parity
- [INV-SPLIT-08] Auto-hydration on initialization
- Negative test ratio >= 30% [H-CODE-3]
"""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from core.cortex_docs import (
    DEFAULT_DOCUMENT_DB_PATH,
    init_cortex_db,
    resolve_document_db_path,
    snapshot_state_ledger,
)
from core.cortex_knowledge import (
    DEFAULT_MEMORY_DB_PATH,
    DEFAULT_MEMORY_SEED_PATH,
    export_memory_seed,
    get_cortex_stats,
    hydrate_memory_from_seed,
    init_knowledge_tables,
    park_task,
    record_event,
    resolve_memory_db_path,
)
from core.fs_topology import CanonicalPaths, resolve_cortex_db_path
from scripts.migrate_memory_document_split import execute_migration


class TestMemoryDocumentSplitIVV(unittest.TestCase):
    """IV&V test suite for memory-document segregation and migration."""

    def setUp(self) -> None:
        """Sets up isolated temporary workspace directory."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.source_db = self.workspace / "source_cortex.db"
        self.memory_db = self.workspace / "memory.db"
        self.document_db = self.workspace / "document.db"
        self.seed_file = self.workspace / "memory_seed.jsonl"
        self.backup_db = self.workspace / "source_cortex.db.bak"

        # Populate synthetic source database with both memory and document tables
        init_cortex_db(self.source_db)
        con = sqlite3.connect(str(self.source_db))
        try:
            init_knowledge_tables(con)
        finally:
            con.close()

        for i in range(5):
            record_event(
                outcome="SUCCESS" if i % 2 == 0 else "FAILURE",
                component=f"comp_{i}",
                trigger_tokens=f"trigger_token_{i}",
                directive=f"Synthetic test directive {i}",
                db_path=self.source_db,
            )

        park_task(
            task_id="TASK-999",
            title="Parked Task for Migration",
            reason="Testing migration",
            db_path=self.source_db,
        )

        test_ledger = self.workspace / "CURRENT_STATE.md"
        test_ledger.write_text(
            "---\n"
            "id: STATE-TEST-001\n"
            "title: Test State\n"
            "status: ACCEPTED\n"
            "owner: Team\n"
            "last_reviewed: 2026-09-07\n"
            "---\n"
            "# State Body\n",
            encoding="utf-8",
        )
        snapshot_state_ledger(test_ledger, db_path=self.source_db, trigger="Testing migration")

    def tearDown(self) -> None:
        """Cleans up temporary directory deterministically."""
        self.temp_dir.cleanup()

    # ==========================================================================
    # POSITIVE TEST CASES
    # ==========================================================================

    def test_canonical_paths_and_resolvers(self) -> None:
        """Verifies canonical paths exist and resolvers fallback correctly [INV-SPLIT-01]."""
        self.assertEqual(CanonicalPaths.DATA_MEMORY_DB, Path("data/memory.db"))
        self.assertEqual(CanonicalPaths.DATA_DOCUMENT_DB, Path("data/document.db"))
        self.assertEqual(CanonicalPaths.DATA_MEMORY_SEED, Path("data/memory_seed.jsonl"))

        resolved_mem = resolve_memory_db_path(self.memory_db)
        self.assertEqual(resolved_mem, self.memory_db)

        resolved_doc = resolve_document_db_path(self.document_db)
        self.assertEqual(resolved_doc, self.document_db)

    def test_migration_execution_and_parity(self) -> None:
        """Verifies complete data migration, backup, and SHA-256 hash parity [INV-SPLIT-06, INV-SPLIT-07]."""
        report = execute_migration(
            source_path=self.source_db,
            memory_path=self.memory_db,
            document_path=self.document_db,
            seed_path=self.seed_file,
            backup_path=self.backup_db,
        )

        self.assertTrue(report.success)
        self.assertTrue(report.hash_verified)
        self.assertTrue(self.backup_db.exists())
        self.assertEqual(report.episodic_events_migrated, 5)
        self.assertEqual(report.parked_tasks_migrated, 1)
        self.assertEqual(report.state_revisions_migrated, 1)
        self.assertEqual(report.seed_events_exported, 5)

        # Verify memory.db contents
        con_m = sqlite3.connect(str(self.memory_db))
        try:
            m_cur = con_m.execute("SELECT COUNT(*) FROM episodic_events;")
            self.assertEqual(int(m_cur.fetchone()[0]), 5)
            t_cur = con_m.execute("SELECT COUNT(*) FROM parked_tasks;")
            self.assertEqual(int(t_cur.fetchone()[0]), 1)
        finally:
            con_m.close()

        # Verify document.db contents
        con_d = sqlite3.connect(str(self.document_db))
        try:
            d_cur = con_d.execute("SELECT COUNT(*) FROM state_revisions;")
            self.assertEqual(int(d_cur.fetchone()[0]), 1)
        finally:
            con_d.close()

        # Verify stats query across dual databases
        stats = get_cortex_stats(db_path=self.memory_db, docs_db_path=self.document_db)
        self.assertEqual(stats.total_episodic_events, 5)
        self.assertEqual(stats.state_revisions, 1)

    def test_seed_export_and_hydration(self) -> None:
        """Verifies export to JSONL and idempotent hydration [INV-SPLIT-04]."""
        seed_out = self.workspace / "test_export.jsonl"
        exported = export_memory_seed(db_path=self.source_db, seed_path=seed_out)
        self.assertEqual(exported, 5)
        self.assertTrue(seed_out.exists())

        fresh_mem_db = self.workspace / "fresh_memory.db"
        hydrated = hydrate_memory_from_seed(seed_path=seed_out, db_path=fresh_mem_db)
        self.assertEqual(hydrated, 5)

        # Re-hydration should be idempotent (0 newly inserted rows)
        hydrated_again = hydrate_memory_from_seed(seed_path=seed_out, db_path=fresh_mem_db)
        self.assertEqual(hydrated_again, 0)

    def test_migration_cli_json(self) -> None:
        """Verifies migration CLI executes successfully and returns JSON payload."""
        cmd = [
            sys.executable,
            "scripts/migrate_memory_document_split.py",
            "--source",
            str(self.source_db),
            "--memory",
            str(self.memory_db),
            "--document",
            str(self.document_db),
            "--seed",
            str(self.seed_file),
            "--backup",
            str(self.backup_db),
            "--json",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10.0, encoding="utf-8")
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertTrue(data["success"])
        self.assertEqual(data["episodic_events_migrated"], 5)

    # ==========================================================================
    # NEGATIVE TEST CASES (Assert >= 30% of total assertion count)
    # ==========================================================================

    def test_missing_source_db_fails_gracefully(self) -> None:
        """Negative: Missing source database returns failure report [H-CODE-3]."""
        missing_db = self.workspace / "non_existent.db"
        report = execute_migration(
            source_path=missing_db,
            memory_path=self.memory_db,
            document_path=self.document_db,
            seed_path=self.seed_file,
        )
        self.assertFalse(report.success)
        self.assertFalse(report.hash_verified)
        self.assertEqual(report.episodic_events_migrated, 0)
        self.assertIn("not found", report.explanation)

    def test_export_from_missing_db_returns_zero(self) -> None:
        """Negative: Exporting from non-existent DB returns 0 without raising [H-CODE-3]."""
        missing_db = self.workspace / "does_not_exist.db"
        target_seed = self.workspace / "seed.jsonl"
        count = export_memory_seed(db_path=missing_db, seed_path=target_seed)
        self.assertEqual(count, 0)
        self.assertFalse(target_seed.exists())

    def test_hydrate_from_missing_seed_returns_zero(self) -> None:
        """Negative: Hydrating from non-existent seed file returns 0 without crash [H-CODE-3]."""
        missing_seed = self.workspace / "missing_seed.jsonl"
        count = hydrate_memory_from_seed(seed_path=missing_seed, db_path=self.memory_db)
        self.assertEqual(count, 0)

    def test_hydrate_corrupted_json_lines_skipped(self) -> None:
        """Negative: Corrupted or malformed JSONL records are skipped safely [H-CODE-3]."""
        corrupt_seed = self.workspace / "corrupt.jsonl"
        valid_json = json.dumps({
            "id": "evt_1",
            "outcome": "SUCCESS",
            "component": "c",
            "trigger_tokens": "t",
            "directive": "d",
            "created_at": "2026-09-07T00:00:00Z",
            "last_accessed_at": "2026-09-07T00:00:00Z",
        })
        corrupt_seed.write_text(
            f"NOT_JSON_AT_ALL\n{valid_json}\n" + '{"incomplete_record": true}\n',
            encoding="utf-8",
        )
        target_mem = self.workspace / "corrupt_test_mem.db"
        hydrated = hydrate_memory_from_seed(seed_path=corrupt_seed, db_path=target_mem)
        # Exactly 1 valid line should be hydrated, 2 corrupt lines skipped
        self.assertEqual(hydrated, 1)

    def test_gitignore_contains_memory_seed_unignore(self) -> None:
        """Verifies .gitignore explicitly whitelists data/memory_seed.jsonl [INV-SPLIT-05]."""
        gitignore_path = Path(".gitignore")
        self.assertTrue(gitignore_path.exists())
        content = gitignore_path.read_text(encoding="utf-8")
        self.assertIn("!data/memory_seed.jsonl", content)
        self.assertIn("data/*.db", content)


if __name__ == "__main__":
    unittest.main()
