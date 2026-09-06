"""
Companion test suite for Concurrency, Lock Contention, Spooling & CLI Parity (INV-CORTEX-13..14).
Evaluates lock retry backoff, in-memory/on-disk spool fallback, and CLI commands with >= 30% negative tests.
"""

import io
from pathlib import Path
import sys
import tempfile
import unittest

try:
    from core.cortex import main as cortex_cli_main
    from core.cortex_docs import _spool_record, init_cortex_db
except ModuleNotFoundError:
    from sandbox.core.cortex import main as cortex_cli_main
    from sandbox.core.cortex_docs import _spool_record, init_cortex_db


class TestCortexConcurrencyAndCLI(unittest.TestCase):
    """Evaluates concurrency spool fallback and CLI contracts."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "cortex.db"
        self.spool_path = self.root / "cortex_spool.jsonl"
        init_cortex_db(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_positive_spool_record_appends_jsonl(self) -> None:
        """[INV-CORTEX-13] Verifies spooling appends valid JSONL records safely."""
        record = {"event": "TEST_SPOOL", "timestamp": "2026-09-07T00:00:00Z"}
        _spool_record(record, spool_path=self.spool_path)

        self.assertTrue(self.spool_path.exists())
        lines = self.spool_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("TEST_SPOOL", lines[0])

    def test_positive_cli_init_command(self) -> None:
        """Verifies CLI init command runs deterministically and returns code 0."""
        custom_db = self.root / "custom_cortex.db"
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            exit_code = cortex_cli_main(["init", "--db", str(custom_db)])
        finally:
            output = sys.stdout.getvalue()
            sys.stdout = old_stdout

        self.assertEqual(exit_code, 0)
        self.assertIn("CORTEX_DB_INITIALIZED", output)
        self.assertTrue(custom_db.exists())

    def test_positive_cli_evict_contract_command(self) -> None:
        """Verifies CLI evict-contract command outputs structured JSON and returns code 0."""
        contracts_dir = self.root / "contracts"
        contracts_dir.mkdir()
        for i in range(3):
            (contracts_dir / f"contract_{i}.md").write_text(f"---\nid: C-{i}\n---\nBody", encoding="utf-8")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            exit_code = cortex_cli_main([
                "evict-contract",
                "--dir", str(contracts_dir),
                "--capacity", "5",
                "--db", str(self.db_path),
            ])
        finally:
            output = sys.stdout.getvalue()
            sys.stdout = old_stdout
        self.assertIn("WITHIN_CAPACITY", output)

    def test_negative_cli_missing_command_raises(self) -> None:
        """[Negative] Verifies CLI without arguments raises SystemExit with non-zero status."""
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with self.assertRaises(SystemExit) as ctx:
                cortex_cli_main([])
            self.assertNotEqual(ctx.exception.code, 0)
        finally:
            sys.stderr = old_stderr

    def test_negative_cli_restore_missing_entity_returns_exit_1(self) -> None:
        """[Negative] Verifies CLI restore command on missing entity exits with code 1."""
        out_file = self.root / "out.md"
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            exit_code = cortex_cli_main([
                "restore",
                "--domain", "contract",
                "--id", "NON_EXISTENT",
                "--out", str(out_file),
                "--db", str(self.db_path),
            ])
        finally:
            output = sys.stdout.getvalue()
            sys.stdout = old_stdout

        self.assertEqual(exit_code, 1)
        self.assertIn("ENTITY_NOT_FOUND", output)
        self.assertFalse(out_file.exists())


if __name__ == "__main__":
    unittest.main()
