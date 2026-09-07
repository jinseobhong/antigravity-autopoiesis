"""
Companion test suite for Document Restoration & Cryptographic Integrity Invariants (INV-CORTEX-10..12).
Evaluates SHA-256 verification, atomic disk re-hydration, and tampered payload rejection with >= 30% negative tests.
"""

from pathlib import Path
import tempfile
import unittest

from core.cortex_docs import (
    compute_sha256,
    get_connection,
    init_cortex_db,
    restore_archive,
    trigger_contract_eviction,
)


class TestCortexRestore(unittest.TestCase):
    """Evaluates document restoration, hash auditing, and atomic file replace."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "cortex.db"
        init_cortex_db(self.db_path)
        self.contracts_dir = self.root / "contracts"
        self.contracts_dir.mkdir()

        # Seed an evicted contract
        file_path = self.contracts_dir / "target_contract.md"
        self.original_content = (
            "---\n"
            "id: 'CONTRACT-RESTORE-TEST'\n"
            "title: 'Restoration Contract Sample'\n"
            "status: 'ACCEPTED'\n"
            "---\n\n"
            "# Binding Contract Body for Verification\n"
        )
        file_path.write_text(self.original_content, encoding="utf-8")
        # Evict with capacity 0 to force archive
        trigger_contract_eviction(self.contracts_dir, capacity=0, db_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_positive_restore_archive_successful(self) -> None:
        """[INV-CORTEX-10, 11] Restores archived contract to new path with 100% hash match."""
        restore_dest = self.root / "restored" / "rehydrated_contract.md"
        self.assertFalse(restore_dest.exists())

        res = restore_archive(
            domain="contract",
            entity_id="CONTRACT-RESTORE-TEST",
            target_path=restore_dest,
            db_path=self.db_path,
        )

        self.assertTrue(res.verified)
        self.assertEqual(res.status, "RESTORED")
        self.assertEqual(res.content_hash, compute_sha256(self.original_content))
        self.assertTrue(restore_dest.exists())
        self.assertEqual(restore_dest.read_text(encoding="utf-8"), self.original_content)

    def test_negative_restore_tampered_payload_rejected(self) -> None:
        """[INV-CORTEX-12] Injected database corruption causes restore rejection without writing file."""
        # Maliciously alter raw_content in SQLite without updating content_hash
        con = get_connection(self.db_path)
        try:
            with con:
                con.execute(
                    "UPDATE contract_revisions SET raw_content = 'TAMPERED_MALICIOUS_CONTENT' "
                    "WHERE contract_id = 'CONTRACT-RESTORE-TEST';"
                )
        finally:
            con.close()

        restore_dest = self.root / "tamper_test.md"
        res = restore_archive(
            domain="contract",
            entity_id="CONTRACT-RESTORE-TEST",
            target_path=restore_dest,
            db_path=self.db_path,
        )

        self.assertFalse(res.verified)
        self.assertEqual(res.status, "HASH_MISMATCH_REJECTED")
        self.assertFalse(restore_dest.exists(), "Corrupted payload MUST NOT be written to filesystem")

    def test_negative_restore_entity_not_found(self) -> None:
        """[Negative] Restoration of non-existent entity returns ENTITY_NOT_FOUND cleanly."""
        restore_dest = self.root / "missing.md"
        res = restore_archive(
            domain="contract",
            entity_id="NON_EXISTENT_ID",
            target_path=restore_dest,
            db_path=self.db_path,
        )
        self.assertFalse(res.verified)
        self.assertEqual(res.status, "ENTITY_NOT_FOUND")
        self.assertFalse(restore_dest.exists())

    def test_negative_restore_invalid_domain(self) -> None:
        """[Negative] Request with unsupported domain returns INVALID_DOMAIN cleanly."""
        restore_dest = self.root / "invalid.md"
        res = restore_archive(
            domain="unsupported_domain",
            entity_id="CONTRACT-RESTORE-TEST",
            target_path=restore_dest,
            db_path=self.db_path,
        )
        self.assertFalse(res.verified)
        self.assertEqual(res.status, "INVALID_DOMAIN")


if __name__ == "__main__":
    unittest.main()
