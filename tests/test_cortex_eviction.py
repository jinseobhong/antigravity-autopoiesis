"""
Companion test suite for Tri-Domain Event-Driven Eviction Invariants (INV-CORTEX-06..09).
Evaluates 5-document ceiling, FIFO eviction order, and post-commit unlinking with >= 30% negative tests.
"""

from pathlib import Path
import time
import tempfile
import unittest

try:
    from core.cortex_docs import (
        get_connection,
        init_cortex_db,
        trigger_architecture_eviction,
        trigger_contract_eviction,
        trigger_state_eviction,
    )
except ModuleNotFoundError:
    from sandbox.core.cortex_docs import (
        get_connection,
        init_cortex_db,
        trigger_architecture_eviction,
        trigger_contract_eviction,
        trigger_state_eviction,
    )


class TestCortexEviction(unittest.TestCase):
    """Evaluates domain-segregated event-driven rolling eviction engines."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "cortex.db"
        init_cortex_db(self.db_path)
        self.contracts_dir = self.root / "contracts"
        self.states_dir = self.root / "states"
        self.arch_dir = self.root / "arch"
        self.contracts_dir.mkdir()
        self.states_dir.mkdir()
        self.arch_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_mock_markdowns(self, target_dir: Path, count: int, prefix: str) -> None:
        """Helper to create sequentially timestamped markdown files."""
        for i in range(1, count + 1):
            file_path = target_dir / f"{prefix}_{i:02d}.md"
            doc_content = (
                f"---\n"
                f"id: '{prefix.upper()}-{i:02d}'\n"
                f"title: '{prefix.capitalize()} {i}'\n"
                f"status: 'ACCEPTED'\n"
                f"---\n\n"
                f"# Content for {prefix} {i}\n"
            )
            file_path.write_text(doc_content, encoding="utf-8")
            time.sleep(0.01)

    def test_positive_contract_eviction_exceeding_capacity(self) -> None:
        """[INV-CORTEX-06..09] 7 contracts created; capacity 5 -> 2 oldest evicted and unlinked."""
        self._create_mock_markdowns(self.contracts_dir, 7, "contract")
        self.assertEqual(len(list(self.contracts_dir.glob("*.md"))), 7)

        result = trigger_contract_eviction(self.contracts_dir, capacity=5, db_path=self.db_path)

        self.assertEqual(result.domain, "contract")
        self.assertEqual(result.status, "EVICTION_EXECUTED")
        self.assertEqual(len(result.evicted_files), 2)
        self.assertEqual(len(result.retained_files), 5)
        # Oldest first (contract_01.md, contract_02.md)
        self.assertIn("contract_01.md", result.evicted_files)
        self.assertIn("contract_02.md", result.evicted_files)

        # Unlinked from disk
        remaining_on_disk = [p.name for p in self.contracts_dir.glob("*.md")]
        self.assertEqual(len(remaining_on_disk), 5)
        self.assertNotIn("contract_01.md", remaining_on_disk)
        self.assertNotIn("contract_02.md", remaining_on_disk)

        # Verified in SQLite database
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM contract_revisions;")
            count = cur.fetchone()[0]
            self.assertEqual(count, 2)
        finally:
            con.close()

    def test_positive_state_eviction_within_capacity(self) -> None:
        """[INV-CORTEX-06] 4 state files created; capacity 5 -> no eviction triggered."""
        self._create_mock_markdowns(self.states_dir, 4, "state")
        result = trigger_state_eviction(self.states_dir, capacity=5, db_path=self.db_path)

        self.assertEqual(result.status, "WITHIN_CAPACITY")
        self.assertEqual(len(result.evicted_files), 0)
        self.assertEqual(len(result.retained_files), 4)
        self.assertEqual(len(list(self.states_dir.glob("*.md"))), 4)

    def test_positive_architecture_eviction_boundary(self) -> None:
        """[INV-CORTEX-06..09] 6 architecture blueprints; capacity 5 -> exactly 1 evicted to architecture_revisions."""
        self._create_mock_markdowns(self.arch_dir, 6, "arch")
        result = trigger_architecture_eviction(self.arch_dir, capacity=5, db_path=self.db_path)

        self.assertEqual(result.status, "EVICTION_EXECUTED")
        self.assertEqual(len(result.evicted_files), 1)
        self.assertEqual(result.evicted_files[0], "arch_01.md")
        self.assertEqual(len(list(self.arch_dir.glob("*.md"))), 5)

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM architecture_revisions;")
            count = cur.fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            con.close()

    def test_negative_eviction_non_existent_directory(self) -> None:
        """[Negative] Verifies eviction on non-existent directory yields zero evictions cleanly."""
        bogus_dir = self.root / "does_not_exist"
        result = trigger_contract_eviction(bogus_dir, capacity=5, db_path=self.db_path)
        self.assertEqual(result.status, "WITHIN_CAPACITY")
        self.assertEqual(len(result.evicted_files), 0)
        self.assertEqual(len(result.retained_files), 0)

    def test_negative_eviction_empty_directory(self) -> None:
        """[Negative] Verifies empty directory yields zero evictions without errors."""
        empty_dir = self.root / "empty_dir"
        empty_dir.mkdir()
        result = trigger_state_eviction(empty_dir, capacity=5, db_path=self.db_path)
        self.assertEqual(result.status, "WITHIN_CAPACITY")
        self.assertEqual(len(result.evicted_files), 0)


if __name__ == "__main__":
    unittest.main()
