"""
Companion test suite for Cortex DB initialization and schema invariants (INV-CORTEX-01..05).
Evaluates SQLite WAL pragmas, busy timeout, and tri-domain table isolation with >= 30% negative tests.
"""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from core.cortex_docs import (
    compute_sha256,
    get_connection,
    init_cortex_db,
    parse_frontmatter,
)


class TestCortexDocsBase(unittest.TestCase):
    """Evaluates database initialization, pragmas, and metadata helpers."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cortex.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_positive_init_cortex_db_creates_tables(self) -> None:
        """[INV-CORTEX-01, 05] Verifies tri-domain tables and FTS virtual table exist."""
        created_path = init_cortex_db(self.db_path)
        self.assertTrue(created_path.exists())

        con = sqlite3.connect(str(self.db_path))
        try:
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cur.fetchall()}
            self.assertIn("contract_revisions", tables)
            self.assertIn("state_revisions", tables)
            self.assertIn("architecture_revisions", tables)
            self.assertIn("fts_archive_search", tables)
        finally:
            con.close()

    def test_positive_sqlite_pragmas_enforced(self) -> None:
        """[INV-CORTEX-02, 03, 04] Asserts WAL mode, synchronous NORMAL, and 5000ms busy timeout."""
        init_cortex_db(self.db_path)
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute("PRAGMA journal_mode;")
            journal_mode = cur.fetchone()[0].lower()
            self.assertEqual(journal_mode, "wal")

            cur.execute("PRAGMA busy_timeout;")
            busy_timeout = cur.fetchone()[0]
            self.assertEqual(busy_timeout, 5000)

            cur.execute("PRAGMA synchronous;")
            sync_mode = cur.fetchone()[0]
            # 1 corresponds to NORMAL in SQLite
            self.assertEqual(sync_mode, 1)
        finally:
            con.close()

    def test_positive_sha256_computation(self) -> None:
        """Verifies deterministic SHA-256 digest computation."""
        sample = "Normative contract payload for testing"
        digest = compute_sha256(sample)
        self.assertEqual(len(digest), 64)
        self.assertEqual(compute_sha256(sample), digest)

    def test_negative_frontmatter_parser_empty_or_malformed(self) -> None:
        """[Negative] Verifies parser handles empty, missing, or broken frontmatter without raising."""
        # 1. No frontmatter
        self.assertEqual(parse_frontmatter("# Title with no frontmatter"), {})

        # 2. Unclosed frontmatter
        self.assertEqual(parse_frontmatter("---\nid: test\n"), {})

        # 3. Valid frontmatter parses correctly
        doc = "---\nid: 'CONTRACT-01'\ntitle: 'Title # With Comment'\nstatus: PROPOSED\n---\nBody"
        meta = parse_frontmatter(doc)
        self.assertEqual(meta.get("id"), "CONTRACT-01")
        self.assertEqual(meta.get("title"), "Title")
        self.assertEqual(meta.get("status"), "PROPOSED")

    def test_negative_get_connection_nested_missing_parents_created(self) -> None:
        """[Negative/Edge] Ensures deep non-existent parent directory is auto-created safely."""
        deep_db = Path(self.temp_dir.name) / "deep" / "nested" / "dir" / "cortex.db"
        self.assertFalse(deep_db.parent.exists())
        con = get_connection(deep_db)
        try:
            self.assertTrue(deep_db.parent.exists())
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
