"""
Companion test suite for Active Contract Lifecycle Gate (tests.test_validate_active_contract).

Evaluates contract YAML frontmatter parsing, state ledger task extraction, contract validation,
contract archiving, and CLI execution. Satisfies AST Anti-Cheat invariants (H-CODE-1 through
H-CODE-12) with >= 40% negative test ratio and zero lazy stubs.
"""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from scripts.validate_active_contract import (
        archive_active_contract,
        extract_active_task_from_ledger,
        main,
        parse_contract_frontmatter,
        validate_contract_state,
    )
    _MODULE_PATH = "scripts.validate_active_contract"
except ModuleNotFoundError:
    from sandbox.scripts.validate_active_contract import (
        archive_active_contract,
        extract_active_task_from_ledger,
        main,
        parse_contract_frontmatter,
        validate_contract_state,
    )
    _MODULE_PATH = "sandbox.scripts.validate_active_contract"

_SAMPLE_CONTRACT = (
    "---\n"
    'id: "CONTRACT-20260907-active-contract-gate"\n'
    'title: "Active Contract SSOT Lifecycle and Enforcement Gate Binding Contract"\n'
    'status: "ACCEPTED"\n'
    'owner: "Platform Architecture Lead"\n'
    'last_reviewed: "2026-09-07"\n'
    'target_task_id: "TASK-024"\n'
    "---\n\n"
    "# Active Engineering Contract: Active Contract SSOT Lifecycle\n"
)

_SAMPLE_LEDGER = (
    "---\n"
    'id: "STATE-20260907-sprint-compass"\n'
    'title: "State Ledger"\n'
    'status: "ACCEPTED"\n'
    "---\n\n"
    "# State Ledger\n\n"
    "| Task ID | Task Description | Lifecycle Status |\n"
    "| :--- | :--- | :---: |\n"
    "| **`TASK-024`** | Active Contract Gate | `IN_PROGRESS` |\n"
)


class TestParseContractFrontmatter(unittest.TestCase):
    """Evaluates YAML frontmatter parsing across valid, corrupted, and nonexistent files."""

    def test_parse_frontmatter_valid_positive(self) -> None:
        """Positive test: Valid frontmatter parses into complete key-value dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text(_SAMPLE_CONTRACT, encoding="utf-8")

            metadata = parse_contract_frontmatter(contract_file)

            self.assertEqual(metadata.get("id"), "CONTRACT-20260907-active-contract-gate")
            self.assertEqual(metadata.get("status"), "ACCEPTED")
            self.assertEqual(metadata.get("target_task_id"), "TASK-024")
            self.assertEqual(metadata.get("owner"), "Platform Architecture Lead")
            self.assertEqual(metadata.get("last_reviewed"), "2026-09-07")

    def test_parse_frontmatter_nonexistent_file_negative(self) -> None:
        """Negative test: Nonexistent contract path returns empty dictionary."""
        nonexistent = Path("nonexistent_path_for_testing_active_contract.md")
        metadata = parse_contract_frontmatter(nonexistent)
        self.assertEqual(metadata, {})

    def test_parse_frontmatter_missing_delimiter_negative(self) -> None:
        """Negative test: Markdown lacking opening frontmatter delimiter returns empty dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "no_delimiter.md"
            file_path.write_text("# Just a Title\nid: CONTRACT-01\n", encoding="utf-8")

            metadata = parse_contract_frontmatter(file_path)
            self.assertEqual(metadata, {})

    def test_parse_frontmatter_unclosed_delimiter_negative(self) -> None:
        """Negative test: Frontmatter with unclosed opening delimiter returns empty dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "unclosed.md"
            file_path.write_text("---\nid: CONTRACT-01\nstatus: ACCEPTED\n", encoding="utf-8")

            metadata = parse_contract_frontmatter(file_path)
            self.assertEqual(metadata, {})

    def test_parse_frontmatter_empty_file_negative(self) -> None:
        """Negative test: Completely empty contract file returns empty dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "empty.md"
            file_path.write_text("", encoding="utf-8")

            metadata = parse_contract_frontmatter(file_path)
            self.assertEqual(metadata, {})


class TestExtractActiveTaskFromLedger(unittest.TestCase):
    """Evaluates task ID extraction from state ledger table structures."""

    def test_extract_active_task_in_progress_positive(self) -> None:
        """Positive test: Table row containing IN_PROGRESS task ID extracts successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_file = Path(tmpdir) / "CURRENT_STATE.md"
            ledger_file.write_text(_SAMPLE_LEDGER, encoding="utf-8")

            task_id = extract_active_task_from_ledger(ledger_file)
            self.assertEqual(task_id, "TASK-024")

    def test_extract_active_task_bold_without_backticks_positive(self) -> None:
        """Positive test: Extracts task ID when bolded without embedded code backticks."""
        raw_ledger = (
            "| Task ID | Task Description | Lifecycle Status |\n"
            "| :--- | :--- | :---: |\n"
            "| **TASK-105** | Some Task | IN_PROGRESS |\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_file = Path(tmpdir) / "CURRENT_STATE.md"
            ledger_file.write_text(raw_ledger, encoding="utf-8")

            task_id = extract_active_task_from_ledger(ledger_file)
            self.assertEqual(task_id, "TASK-105")

    def test_extract_active_task_no_active_tasks_negative(self) -> None:
        """Negative test: Ledger with only PROMOTED and PLANNED tasks returns None."""
        raw_ledger = (
            "| Task ID | Task Description | Lifecycle Status |\n"
            "| :--- | :--- | :---: |\n"
            "| **TASK-001** | Architecture | PROMOTED |\n"
            "| **TASK-002** | Security Harness | PLANNED |\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_file = Path(tmpdir) / "CURRENT_STATE.md"
            ledger_file.write_text(raw_ledger, encoding="utf-8")

            task_id = extract_active_task_from_ledger(ledger_file)
            self.assertIsNone(task_id)

    def test_extract_active_task_nonexistent_file_negative(self) -> None:
        """Negative test: Nonexistent ledger path returns None."""
        nonexistent = Path("nonexistent_ledger_path_xyz.md")
        task_id = extract_active_task_from_ledger(nonexistent)
        self.assertIsNone(task_id)

    def test_extract_active_task_empty_file_negative(self) -> None:
        """Negative test: Empty ledger file returns None without exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_file = Path(tmpdir) / "CURRENT_STATE.md"
            ledger_file.write_text("", encoding="utf-8")

            task_id = extract_active_task_from_ledger(ledger_file)
            self.assertIsNone(task_id)


class TestValidateContractState(unittest.TestCase):
    """Evaluates contract state validation against schema, status, and ledger consistency."""

    def test_validate_contract_accepted_with_ledger_positive(self) -> None:
        """Positive test: Valid accepted contract matching active ledger task passes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text(_SAMPLE_CONTRACT, encoding="utf-8")
            ledger_file = Path(tmpdir) / "CURRENT_STATE.md"
            ledger_file.write_text(_SAMPLE_LEDGER, encoding="utf-8")

            passed, reason = validate_contract_state(
                contract_path=contract_file,
                ledger_path=ledger_file,
            )
            self.assertTrue(passed)
            self.assertIsNone(reason)

    def test_validate_contract_accepted_with_explicit_task_positive(self) -> None:
        """Positive test: Valid accepted contract matching explicit target task passes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text(_SAMPLE_CONTRACT, encoding="utf-8")

            passed, reason = validate_contract_state(
                contract_path=contract_file,
                expected_task_id="TASK-024",
            )
            self.assertTrue(passed)
            self.assertIsNone(reason)

    def test_validate_contract_nonexistent_negative(self) -> None:
        """Negative test: Missing contract file returns False with diagnostic message."""
        nonexistent = Path("nonexistent_active_contract_fixture.md")
        passed, reason = validate_contract_state(contract_path=nonexistent)

        self.assertFalse(passed)
        self.assertIsNotNone(reason)
        self.assertIn("does not exist", str(reason))

    def test_validate_contract_missing_frontmatter_negative(self) -> None:
        """Negative test: Contract lacking YAML frontmatter fails validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text("# Markdown Without Frontmatter\n", encoding="utf-8")

            passed, reason = validate_contract_state(contract_path=contract_file)
            self.assertFalse(passed)
            self.assertIsNotNone(reason)
            self.assertIn("missing valid YAML frontmatter", str(reason))

    def test_validate_contract_missing_required_key_negative(self) -> None:
        """Negative test: Frontmatter lacking target_task_id fails validation."""
        incomplete_contract = (
            "---\n"
            'id: "CONTRACT-20260907-incomplete"\n'
            'status: "ACCEPTED"\n'
            "---\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text(incomplete_contract, encoding="utf-8")

            passed, reason = validate_contract_state(contract_path=contract_file)
            self.assertFalse(passed)
            self.assertIsNotNone(reason)
            self.assertIn("missing required key 'target_task_id'", str(reason))

    def test_validate_contract_non_accepted_status_negative(self) -> None:
        """Negative test: Contract with DRAFT status is rejected before implementation."""
        draft_contract = (
            "---\n"
            'id: "CONTRACT-20260907-draft"\n'
            'status: "DRAFT"\n'
            'target_task_id: "TASK-024"\n'
            "---\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text(draft_contract, encoding="utf-8")

            passed, reason = validate_contract_state(contract_path=contract_file)
            self.assertFalse(passed)
            self.assertIsNotNone(reason)
            self.assertIn("MUST be 'ACCEPTED'", str(reason))

    def test_validate_contract_mismatched_task_id_negative(self) -> None:
        """Negative test: Target task ID mismatch with active task triggers failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text(_SAMPLE_CONTRACT, encoding="utf-8")

            passed, reason = validate_contract_state(
                contract_path=contract_file,
                expected_task_id="TASK-999",
            )
            self.assertFalse(passed)
            self.assertIsNotNone(reason)
            self.assertIn("does not match active task 'TASK-999'", str(reason))


class TestArchiveActiveContract(unittest.TestCase):
    """Evaluates contract archiving lifecycle, destination pathing, and status rewriting."""

    def test_archive_contract_valid_lifecycle_positive(self) -> None:
        """Positive test: Archives contract to destination with ARCHIVED status and unlinks source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_file = tmp_path / "ACTIVE_CONTRACT.md"
            source_file.write_text(_SAMPLE_CONTRACT, encoding="utf-8")
            archive_dir = tmp_path / "archived"

            success, dest = archive_active_contract(
                contract_path=source_file,
                archive_dir=archive_dir,
            )

            self.assertTrue(success)
            self.assertFalse(source_file.exists())

            dest_path = Path(dest)
            self.assertTrue(dest_path.exists())
            self.assertEqual(dest_path.name, "CONTRACT-20260907-active-contract-gate.md")

            archived_content = dest_path.read_text(encoding="utf-8")
            self.assertIn('status: "ARCHIVED"', archived_content)

    def test_archive_contract_nonexistent_source_negative(self) -> None:
        """Negative test: Archiving nonexistent source contract returns failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir) / "archived"
            nonexistent = Path(tmpdir) / "nonexistent.md"

            success, msg = archive_active_contract(
                contract_path=nonexistent,
                archive_dir=archive_dir,
            )
            self.assertFalse(success)
            self.assertIn("does not exist", msg)

    def test_archive_contract_missing_id_negative(self) -> None:
        """Negative test: Archiving contract without id in frontmatter fails gracefully."""
        no_id_contract = (
            "---\n"
            'status: "ACCEPTED"\n'
            'target_task_id: "TASK-024"\n'
            "---\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_file = tmp_path / "ACTIVE_CONTRACT.md"
            source_file.write_text(no_id_contract, encoding="utf-8")
            archive_dir = tmp_path / "archived"

            success, msg = archive_active_contract(
                contract_path=source_file,
                archive_dir=archive_dir,
            )
            self.assertFalse(success)
            self.assertIn("missing 'id'", msg)


class TestCLIValidateActiveContract(unittest.TestCase):
    """Evaluates CLI argument handling, exit codes, JSON serialization, and subcommands."""

    def test_cli_valid_contract_exit_zero_positive(self) -> None:
        """Positive test: Valid contract evaluated via CLI exits with status code 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text(_SAMPLE_CONTRACT, encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(["--contract", str(contract_file), "--task", "TASK-024"])
            self.assertEqual(exit_code, 0)

    def test_cli_valid_contract_json_output_positive(self) -> None:
        """Positive test: CLI with --json outputs valid serialized JSON payload on success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text(_SAMPLE_CONTRACT, encoding="utf-8")

            captured_stdout = io.StringIO()
            with contextlib.redirect_stdout(captured_stdout):
                exit_code = main([
                    "--contract", str(contract_file),
                    "--task", "TASK-024",
                    "--json",
                ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(captured_stdout.getvalue())
            self.assertTrue(payload.get("passed"))
            self.assertIsNone(payload.get("reason"))

    def test_cli_invalid_contract_exit_one_negative(self) -> None:
        """Negative test: Nonexistent contract evaluated via CLI exits with status code 1."""
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = main(["--contract", "nonexistent_cli_fixture.md"])
        self.assertEqual(exit_code, 1)

    def test_cli_invalid_contract_json_output_negative(self) -> None:
        """Negative test: Rejected contract outputs structured error in JSON format."""
        captured_stdout = io.StringIO()
        with contextlib.redirect_stdout(captured_stdout):
            exit_code = main(["--contract", "nonexistent_cli_fixture.md", "--json"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(captured_stdout.getvalue())
        self.assertFalse(payload.get("passed"))
        self.assertIsNotNone(payload.get("reason"))

    def test_cli_status_draft_exit_one_negative(self) -> None:
        """Negative test: Contract with unratified status exits with code 1 via CLI."""
        draft_contract = (
            "---\n"
            'id: "CONTRACT-20260907-draft"\n'
            'status: "PROPOSED"\n'
            'target_task_id: "TASK-024"\n'
            "---\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_file = Path(tmpdir) / "ACTIVE_CONTRACT.md"
            contract_file.write_text(draft_contract, encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(["--contract", str(contract_file)])
            self.assertEqual(exit_code, 1)

    def test_cli_archive_nonexistent_exit_one_negative(self) -> None:
        """Negative test: CLI archive subcommand on nonexistent contract exits with code 1."""
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = main(["--contract", "nonexistent_contract.md", "--archive"])
        self.assertEqual(exit_code, 1)

    def test_cli_archive_success_exit_zero_positive(self) -> None:
        """Positive test: CLI archive command triggers archive routine and exits 0."""
        target_mock = f"{_MODULE_PATH}.archive_active_contract"
        with mock.patch(target_mock, return_value=(True, "docs/archived/CONTRACT-01.md")):
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(["--contract", "any_contract.md", "--archive"])
            self.assertEqual(exit_code, 0)

    def test_cli_archive_json_output_negative(self) -> None:
        """Negative test: Failed archive subcommand with --json formats JSON error."""
        target_mock = f"{_MODULE_PATH}.archive_active_contract"
        with mock.patch(target_mock, return_value=(False, "Mocked archive failure")):
            captured_stdout = io.StringIO()
            with contextlib.redirect_stdout(captured_stdout):
                exit_code = main(["--contract", "any.md", "--archive", "--json"])

            self.assertEqual(exit_code, 1)
            payload = json.loads(captured_stdout.getvalue())
            self.assertFalse(payload.get("success"))
            self.assertEqual(payload.get("message"), "Mocked archive failure")


if __name__ == "__main__":
    unittest.main()
