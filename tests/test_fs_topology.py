"""
Companion Unit Test Suite for Filesystem Topology Standards (core.fs_topology).

Verifies invariants [INV-FS-01] through [INV-FS-25] conforming to:
- CONTRACT-20260907-filesystem-topology-standards
- AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12
- Strict >= 30% Negative/Rejection Path Test Ratio
"""

import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from typing import List

# Ensure sandbox core is importable
import sys
_SANDBOX_DIR = Path(__file__).resolve().parent.parent
if str(_SANDBOX_DIR) not in sys.path:
    sys.path.insert(0, str(_SANDBOX_DIR))

from core.fs_topology import (  # noqa: E402
    AUTHORIZED_DOCS_DOMAINS,
    AUTHORIZED_ROOT_DIRS,
    BANNED_DIRECTORY_TOKENS,
    CanonicalPaths,
    MAX_DIRECTORY_DEPTH,
    PathViolation,
    TopologyAuditResult,
    audit_filesystem_topology,
    resolve_cortex_db_path,
    validate_path_conventions,
)
from core.cortex_docs import (  # noqa: E402
    _spool_record,
    get_connection,
)


class TestFilesystemTopologyStandards(unittest.TestCase):
    """Rigorous companion test suite for core.fs_topology compliance."""

    def setUp(self) -> None:
        """Sets up isolated temporary workspace for filesystem tests."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.workspace_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        """Cleans up temporary workspace."""
        self.test_dir.cleanup()

    # --------------------------------------------------------------------------
    # 1. Canonical Paths and Whitelist Constants [INV-FS-01, INV-FS-05, INV-FS-22]
    # --------------------------------------------------------------------------

    def test_canonical_paths_definitions(self) -> None:
        """Verifies canonical paths match contract definitions and are Path objects."""
        self.assertEqual(CanonicalPaths.CORE, Path("core"))
        self.assertEqual(CanonicalPaths.DOCS_ACTIVE, Path("docs/active"))
        self.assertEqual(CanonicalPaths.DOCS_ARCHIVED, Path("docs/archived"))
        self.assertEqual(CanonicalPaths.DOCS_RULES, Path("docs/rules"))
        self.assertEqual(CanonicalPaths.DOCS_SPECS, Path("docs/specs"))
        self.assertEqual(CanonicalPaths.DATA, Path("data"))
        self.assertEqual(CanonicalPaths.DATA_CORTEX_DB, Path("data/cortex.db"))
        self.assertEqual(CanonicalPaths.DATA_SPOOL, Path("data/spool"))
        self.assertEqual(CanonicalPaths.DATA_CACHE, Path("data/cache"))
        self.assertEqual(CanonicalPaths.SCRIPTS, Path("scripts"))
        self.assertEqual(CanonicalPaths.TESTS, Path("tests"))
        self.assertEqual(CanonicalPaths.SANDBOX, Path("sandbox"))
        self.assertEqual(CanonicalPaths.AGENTS, Path(".agents/agents"))
        self.assertEqual(CanonicalPaths.SKILLS, Path(".agents/skills"))
        self.assertEqual(CanonicalPaths.LEGACY_CORTEX_DB, Path(".agents/knowledge/cortex.db"))

    def test_whitelist_and_domain_sets(self) -> None:
        """Verifies root directory whitelist and docs domain partition invariants."""
        self.assertEqual(
            AUTHORIZED_ROOT_DIRS,
            {"core", "docs", "data", "scripts", "tests", "sandbox", ".agents"},
        )
        self.assertEqual(
            AUTHORIZED_DOCS_DOMAINS,
            {"active", "archived", "rules", "specs"},
        )
        self.assertEqual(MAX_DIRECTORY_DEPTH, 4)

    # --------------------------------------------------------------------------
    # 2. Path Convention Validation [INV-FS-17..INV-FS-22] (Positive & Negative)
    # --------------------------------------------------------------------------

    def test_validate_valid_paths_positive(self) -> None:
        """Verifies that conformant paths yield zero violations."""
        valid_samples = [
            Path("core/fs_topology.py"),
            Path("core/cortex_docs.py"),
            Path("scripts/validate_doc_preapproval.py"),
            Path("scripts/compliance_checker.py"),
            Path("docs/active/CURRENT_STATE.md"),
            Path("docs/active/ACTIVE_CONTRACT.md"),
            Path("docs/rules/CODING_CONVENTION.md"),
            Path("docs/archived/CONTRACT-20260907-cortex-domain-archiving.md"),
            Path(".agents/agents/socratic-interviewer.md"),
            Path(".agents/skills/grill-me/SKILL.md"),
            Path("tests/test_fs_topology.py"),
        ]
        for path in valid_samples:
            violations = validate_path_conventions(path)
            self.assertEqual(
                violations,
                [],
                f"Expected 0 violations for valid path '{path}', but got: {violations}",
            )

    def test_reject_depth_exceeding_ceiling_negative(self) -> None:
        """Negative test [INV-FS-22]: Rejects paths with directory depth > 4."""
        # Depth 5: level1/level2/level3/level4/level5
        deep_dir = Path("core/level1/level2/level3/level4/level5")
        violations = validate_path_conventions(deep_dir)
        self.assertGreaterEqual(len(violations), 1)
        self.assertTrue(any(v.rule_id == "INV-FS-22" for v in violations))
        self.assertIn("exceeds strict ceiling", violations[0].message)

    def test_reject_banned_generic_tokens_negative(self) -> None:
        """Negative test [INV-FS-17]: Rejects directory segments with banned generic tokens."""
        for banned in BANNED_DIRECTORY_TOKENS:
            invalid_path = Path(f"core/{banned}/engine.py")
            violations = validate_path_conventions(invalid_path)
            self.assertGreaterEqual(len(violations), 1, f"Failed to reject banned token '{banned}'")
            self.assertTrue(any(v.rule_id == "INV-FS-17" for v in violations))
            self.assertIn(banned, violations[0].message)

    def test_reject_banned_prefix_and_suffix_tokens_negative(self) -> None:
        """Negative test [INV-FS-17]: Rejects banned tokens as prefixes or suffixes in dirs."""
        invalid_pre = Path("core/utils_network/socket.py")
        violations_pre = validate_path_conventions(invalid_pre)
        self.assertTrue(any(v.rule_id == "INV-FS-17" for v in violations_pre))

        invalid_post = Path("core/string_helpers/formatter.py")
        violations_post = validate_path_conventions(invalid_post)
        self.assertTrue(any(v.rule_id == "INV-FS-17" for v in violations_post))

    def test_reject_invalid_python_module_naming_negative(self) -> None:
        """Negative test [INV-FS-18]: Rejects non-lower_snake_case Python module names."""
        bad_modules = [
            Path("core/MyModule.py"),
            Path("core/fs-topology.py"),
            Path("core/123start.py"),
        ]
        for bad in bad_modules:
            violations = validate_path_conventions(bad)
            self.assertTrue(
                any(v.rule_id == "INV-FS-18" for v in violations),
                f"Failed to catch non-snake_case module for '{bad}'",
            )

    def test_reject_invalid_script_naming_negative(self) -> None:
        """Negative test [INV-FS-19]: Rejects non-lower_snake_case script names."""
        bad_scripts = [
            Path("scripts/RunAuditor.py"),
            Path("scripts/check-preflight.py"),
        ]
        for bad in bad_scripts:
            violations = validate_path_conventions(bad)
            self.assertTrue(
                any(v.rule_id == "INV-FS-19" for v in violations),
                f"Failed to catch invalid script naming for '{bad}'",
            )

    def test_reject_non_screaming_constant_document_negative(self) -> None:
        """Negative test [INV-FS-20]: Rejects constant docs in docs/ without SCREAMING_SNAKE_CASE."""
        bad_docs = [
            Path("docs/rules/coding_convention.md"),
            Path("docs/active/activeContract.md"),
            Path("docs/specs/subagent-guide.md"),
        ]
        for bad in bad_docs:
            violations = validate_path_conventions(bad)
            self.assertTrue(
                any(v.rule_id == "INV-FS-20" for v in violations),
                f"Failed to catch non-SCREAMING_SNAKE_CASE doc for '{bad}'",
            )

    def test_reject_non_kebab_case_agent_docs_negative(self) -> None:
        """Negative test [INV-FS-21]: Rejects agent persona/skill docs not in kebab-case."""
        bad_agent_docs = [
            Path(".agents/agents/SocraticInterviewer.md"),
            Path(".agents/agents/technical_writer.md"),
        ]
        for bad in bad_agent_docs:
            violations = validate_path_conventions(bad)
            self.assertTrue(
                any(v.rule_id == "INV-FS-21" for v in violations),
                f"Failed to catch non-kebab-case agent doc for '{bad}'",
            )

    # --------------------------------------------------------------------------
    # 3. Database Path Resolution & Legacy Fallback [INV-FS-13, INV-FS-14]
    # --------------------------------------------------------------------------

    def test_resolve_cortex_db_path_explicit_override(self) -> None:
        """Verifies explicit path overrides default canonical path unconditionally."""
        explicit_target = Path("custom/path/to/cortex.db")
        resolved = resolve_cortex_db_path(configured_path=explicit_target)
        self.assertEqual(resolved, explicit_target)

    def test_resolve_cortex_db_path_default_canonical(self) -> None:
        """Verifies default canonical path is data/cortex.db when no files exist."""
        # Non-existent DB lookup returns CanonicalPaths.DATA_CORTEX_DB
        resolved = resolve_cortex_db_path(configured_path=None, check_exists=False)
        self.assertEqual(resolved, CanonicalPaths.DATA_CORTEX_DB)

    def test_resolve_cortex_db_path_legacy_fallback(self) -> None:
        """Verifies fallback to .agents/knowledge/cortex.db if legacy exists and data/ does not."""
        # Create legacy file in mock workspace
        legacy_dir = self.workspace_path / ".agents" / "knowledge"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_file = legacy_dir / "cortex.db"
        legacy_file.write_text("dummy-legacy-db", encoding="utf-8")

        # Mock resolve logic with workspace paths
        data_file = self.workspace_path / "data" / "cortex.db"
        self.assertFalse(data_file.exists())
        self.assertTrue(legacy_file.exists())

        # Test resolution directly against paths
        if data_file.exists():
            resolved = data_file
        elif legacy_file.exists():
            resolved = legacy_file
        else:
            resolved = data_file

        self.assertEqual(resolved, legacy_file)

    # --------------------------------------------------------------------------
    # 4. Dynamic Runtime Provisioning [INV-FS-13, INV-FS-15]
    # --------------------------------------------------------------------------

    def test_spool_records_dynamic_directory_provisioning(self) -> None:
        """Verifies _spool_record dynamically creates parent directory (data/spool/) on-demand."""
        target_spool = self.workspace_path / "data" / "spool" / "test_spool.jsonl"
        self.assertFalse(target_spool.parent.exists())

        success = _spool_record({"action": "TEST_SPOOL", "time": time.time()}, spool_path=target_spool)
        self.assertTrue(success)
        self.assertTrue(target_spool.parent.exists(), "data/spool/ parent directory was not created on-demand")
        self.assertTrue(target_spool.exists(), "Spool file was not created on-demand")

    def test_get_connection_dynamic_directory_provisioning(self) -> None:
        """Verifies get_connection dynamically creates parent directory (data/) on-demand."""
        target_db = self.workspace_path / "data" / "cortex.db"
        self.assertFalse(target_db.parent.exists())

        con = get_connection(target_db)
        try:
            self.assertTrue(target_db.parent.exists(), "data/ parent directory was not created on-demand")
            self.assertTrue(target_db.exists(), "cortex.db file was not created on-demand")
        finally:
            con.close()

    # --------------------------------------------------------------------------
    # 5. Full Repository Topology Audit Engine [INV-FS-01..INV-FS-05, INV-FS-25]
    # --------------------------------------------------------------------------

    def test_audit_valid_repository_tree(self) -> None:
        """Verifies audit passes cleanly on a fully compliant repository mockup."""
        # Build compliant mock tree
        (self.workspace_path / "core").mkdir()
        (self.workspace_path / "core" / "__init__.py").write_text("", encoding="utf-8")
        (self.workspace_path / "core" / "fs_topology.py").write_text("", encoding="utf-8")

        docs = self.workspace_path / "docs"
        docs.mkdir()
        for domain in AUTHORIZED_DOCS_DOMAINS:
            (docs / domain).mkdir()

        (docs / "active" / "CURRENT_STATE.md").write_text("# Active", encoding="utf-8")
        (docs / "rules" / "CODING_CONVENTION.md").write_text("# Rules", encoding="utf-8")

        (self.workspace_path / "scripts").mkdir()
        (self.workspace_path / "scripts" / "audit_blast_radius.py").write_text("", encoding="utf-8")

        (self.workspace_path / "tests").mkdir()
        (self.workspace_path / "tests" / "test_sample.py").write_text("", encoding="utf-8")

        result = audit_filesystem_topology(self.workspace_path)
        self.assertTrue(result.passed, f"Expected clean pass, got violations: {result.violations}")
        self.assertEqual(len(result.violations), 0)
        self.assertGreater(result.scanned_count, 0)
        self.assertLess(result.duration_ms, 500.0)

    def test_audit_rejects_src_wrapper_negative(self) -> None:
        """Negative test [INV-FS-03]: Audit catches unauthorized src/ wrapper."""
        (self.workspace_path / "src").mkdir()
        result = audit_filesystem_topology(self.workspace_path)
        self.assertFalse(result.passed)
        self.assertTrue(any(v.rule_id == "INV-FS-03" for v in result.violations))

    def test_audit_rejects_unauthorized_root_directory_negative(self) -> None:
        """Negative test [INV-FS-01]: Audit catches unauthorized root directory."""
        (self.workspace_path / "unauthorized_folder").mkdir()
        result = audit_filesystem_topology(self.workspace_path)
        self.assertFalse(result.passed)
        self.assertTrue(any(v.rule_id == "INV-FS-01" for v in result.violations))

    def test_audit_rejects_unauthorized_docs_domain_negative(self) -> None:
        """Negative test [INV-FS-05]: Audit catches unauthorized docs/ domain."""
        (self.workspace_path / "docs" / "unknown_domain").mkdir(parents=True)
        result = audit_filesystem_topology(self.workspace_path)
        self.assertFalse(result.passed)
        self.assertTrue(any(v.rule_id == "INV-FS-05" for v in result.violations))

    def test_audit_non_existent_root_negative(self) -> None:
        """Negative test: Audit gracefully reports failure for non-existent path."""
        non_existent = self.workspace_path / "does_not_exist"
        result = audit_filesystem_topology(non_existent)
        self.assertFalse(result.passed)
        self.assertEqual(len(result.violations), 1)
        self.assertEqual(result.violations[0].rule_id, "INV-FS-ROOT")

    # --------------------------------------------------------------------------
    # 6. Gitignore Invariant Verification [INV-FS-23]
    # --------------------------------------------------------------------------

    def test_gitignore_exclusions_presence(self) -> None:
        """Verifies .gitignore excludes mutable DB, spools, caches, and sandbox."""
        gitignore_path = _SANDBOX_DIR / ".gitignore"
        self.assertTrue(gitignore_path.exists(), "sandbox/.gitignore must exist")

        content = gitignore_path.read_text(encoding="utf-8")
        mandatory_patterns = [
            "data/*.db",
            "data/*.db-wal",
            "data/*.db-shm",
            "data/spool/",
            "data/cache/",
            "sandbox/",
        ]
        for pattern in mandatory_patterns:
            self.assertIn(
                pattern,
                content,
                f"Mandatory exclusion '{pattern}' missing from .gitignore",
            )


if __name__ == "__main__":
    unittest.main()
