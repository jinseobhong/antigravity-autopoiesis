"""
Independent IV&V Companion Test Suite for AST Docking Linker (TASK-027).

Ingests docs/active/ACTIVE_CONTRACT.md as primary specification authority.
Evaluates MethodSignature, DockingDefect, DockingReport models,
verify_ast_docking static AST analysis against protocol and implementation files,
CLI exit code determinism (0 on match, 1 on mismatch), and fail-open resilience.
Enforces AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12 with >= 40% negative ratio.
"""

import ast
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple
import unittest

try:
    from core.ast_docking_checker import (
        DockingDefect,
        DockingReport,
        MethodSignature,
        verify_ast_docking,
    )
    _MODULE_AVAILABLE = True
except ModuleNotFoundError:
    try:
        from sandbox.core.ast_docking_checker import (
            DockingDefect,
            DockingReport,
            MethodSignature,
            verify_ast_docking,
        )
        _MODULE_AVAILABLE = True
    except ModuleNotFoundError:
        _MODULE_AVAILABLE = False
        DockingDefect = None  # type: ignore[assignment]
        DockingReport = None  # type: ignore[assignment]
        MethodSignature = None  # type: ignore[assignment]
        verify_ast_docking = None  # type: ignore[assignment]




def _write_protocol_source(
    target_path: Path,
    proto_name: str,
    methods: List[Tuple[str, List[str]]],
) -> None:
    """Synthesizes a minimal typing.Protocol source file."""
    lines = [
        "from typing import Protocol",
        "",
        f"class {proto_name}(Protocol):",
        '    """Test interface protocol specification."""',
    ]
    for m_name, params in methods:
        p_str = ", ".join(params)
        lines.append(f"    def {m_name}({p_str}) -> None:")
        lines.append(f'        raise NotImplementedError("{m_name}")')
        lines.append("")
    target_path.write_text("\n".join(lines), encoding="utf-8")


def _write_impl_source(
    target_path: Path,
    class_name: str,
    methods: List[Tuple[str, List[str]]],
    extra_methods: Optional[List[Tuple[str, List[str]]]] = None,
) -> None:
    """Synthesizes a concrete implementation source file."""
    lines = [
        f"class {class_name}:",
        '    """Test implementation candidate."""',
    ]
    for m_name, params in methods:
        p_str = ", ".join(params)
        lines.append(f"    def {m_name}({p_str}) -> None:")
        lines.append("        _handled = True")
        lines.append("")
    if extra_methods:
        for m_name, params in extra_methods:
            p_str = ", ".join(params)
            lines.append(f"    def {m_name}({p_str}) -> None:")
            lines.append("        _handled_extra = True")
            lines.append("")
    target_path.write_text("\n".join(lines), encoding="utf-8")



@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.ast_docking_checker pending implementation by software-engineer",
)
class TestAstDockingDataModels(unittest.TestCase):
    """Evaluates instantiation, default attributes, and immutability of docking models."""

    def test_method_signature_instantiation_and_properties(self) -> None:
        """Positive test: Verifies MethodSignature instantiation and attribute values."""
        sig = MethodSignature(
            name="send_payload",
            param_names=["self", "data", "timeout"],
            param_count=3,
        )
        self.assertEqual(sig.name, "send_payload")
        self.assertEqual(sig.param_names, ["self", "data", "timeout"])
        self.assertEqual(sig.param_count, 3)

    def test_docking_defect_instantiation_and_properties(self) -> None:
        """Positive test: Verifies DockingDefect instantiation with defect types."""
        defect = DockingDefect(
            protocol_name="SenderProto",
            method_name="send_payload",
            defect_type="MISSING_METHOD",
            message="Method send_payload not implemented",
        )
        self.assertEqual(defect.protocol_name, "SenderProto")
        self.assertEqual(defect.method_name, "send_payload")
        self.assertEqual(defect.defect_type, "MISSING_METHOD")
        self.assertIn("not implemented", defect.message)

    def test_docking_report_instantiation_and_properties(self) -> None:
        """Positive test: Verifies DockingReport nominal instantiation."""
        report = DockingReport(
            is_docked=True,
            proto_path="/path/to/proto.py",
            impl_path="/path/to/impl.py",
            verified_methods=["send_payload"],
            defects=[],
        )
        self.assertTrue(report.is_docked)
        self.assertEqual(report.proto_path, "/path/to/proto.py")
        self.assertEqual(report.impl_path, "/path/to/impl.py")
        self.assertEqual(report.verified_methods, ["send_payload"])
        self.assertEqual(len(report.defects), 0)

    def test_negative_method_signature_immutability(self) -> None:
        """Negative test: Modifying frozen MethodSignature attribute raises FrozenInstanceError."""
        sig = MethodSignature(name="compute", param_names=["self"], param_count=1)
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            sig.name = "mutated_compute"  # type: ignore[misc]

    def test_negative_docking_defect_immutability(self) -> None:
        """Negative test: Modifying frozen DockingDefect attribute raises FrozenInstanceError."""
        defect = DockingDefect(
            protocol_name="P",
            method_name="m",
            defect_type="MISSING_METHOD",
            message="err",
        )
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            defect.defect_type = "PARAM_COUNT_MISMATCH"  # type: ignore[misc]

    def test_negative_docking_report_immutability(self) -> None:
        """Negative test: Modifying frozen DockingReport attribute raises FrozenInstanceError."""
        report = DockingReport(
            is_docked=True,
            proto_path="p",
            impl_path="i",
        )
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            report.is_docked = False  # type: ignore[misc]


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.ast_docking_checker pending implementation by software-engineer",
)
class TestAstDockingFunctional(unittest.TestCase):
    """Evaluates nominal AST docking, multi-method verification, and CLI invocations."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_matching_protocol_and_impl_returns_docked_true(self) -> None:
        """Positive test: Matching Protocol and Implementation file returns is_docked=True."""
        proto_path = self.work_dir / "auth_proto.py"
        impl_path = self.work_dir / "auth_impl.py"
        methods = [
            ("authenticate", ["self", "username", "password"]),
            ("logout", ["self", "session_id"]),
        ]
        _write_protocol_source(proto_path, "AuthProtocol", methods)
        _write_impl_source(impl_path, "AuthService", methods)

        report = verify_ast_docking(proto_path, impl_path)

        self.assertIsInstance(report, DockingReport)
        self.assertTrue(report.is_docked)
        self.assertEqual(len(report.defects), 0)
        self.assertEqual(report.proto_path, str(proto_path))
        self.assertEqual(report.impl_path, str(impl_path))
        self.assertIn("authenticate", report.verified_methods)
        self.assertIn("logout", report.verified_methods)

    def test_multiple_methods_all_docked_successfully(self) -> None:
        """Positive test: Multiple protocol methods with additional impl methods dock cleanly."""
        proto_path = self.work_dir / "store_proto.py"
        impl_path = self.work_dir / "store_impl.py"
        proto_methods = [
            ("get_item", ["self", "key"]),
            ("put_item", ["self", "key", "val"]),
            ("delete_item", ["self", "key"]),
        ]
        impl_extras = [
            ("_internal_cache_lookup", ["self", "key"]),
            ("_evict_expired", ["self"]),
        ]
        _write_protocol_source(proto_path, "StorageProtocol", proto_methods)
        _write_impl_source(
            impl_path,
            "StorageBackend",
            proto_methods,
            extra_methods=impl_extras,
        )

        report = verify_ast_docking(proto_path, impl_path)

        self.assertTrue(report.is_docked)
        self.assertEqual(len(report.defects), 0)
        self.assertEqual(len(report.verified_methods), 3)

    def test_cli_matching_files_exits_zero(self) -> None:
        """Positive test: CLI python -m core.ast_docking_checker --proto ... exits 0."""
        proto_path = self.work_dir / "cli_proto.py"
        impl_path = self.work_dir / "cli_impl.py"
        methods = [("run_task", ["self", "task_id"])]
        _write_protocol_source(proto_path, "TaskProtocol", methods)
        _write_impl_source(impl_path, "TaskRunner", methods)

        target_module = "core.ast_docking_checker"
        if not Path("core/ast_docking_checker.py").exists():
            target_module = "sandbox.core.ast_docking_checker"

        cmd = [
            sys.executable,
            "-m",
            target_module,
            "--proto",
            str(proto_path),
            "--impl",
            str(impl_path),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=os.getcwd(),
        )
        self.assertEqual(
            result.returncode,
            0,
            f"CLI exited with non-zero status {result.returncode}: {result.stderr}",
        )

    def test_cli_json_flag_outputs_valid_json_payload(self) -> None:
        """Positive test: CLI with --json outputs valid structured JSON payload."""
        proto_path = self.work_dir / "json_proto.py"
        impl_path = self.work_dir / "json_impl.py"
        methods = [("serialize", ["self", "target"])]
        _write_protocol_source(proto_path, "JsonProtocol", methods)
        _write_impl_source(impl_path, "JsonSerializer", methods)

        target_module = "core.ast_docking_checker"
        if not Path("core/ast_docking_checker.py").exists():
            target_module = "sandbox.core.ast_docking_checker"

        cmd = [
            sys.executable,
            "-m",
            target_module,
            "--proto",
            str(proto_path),
            "--impl",
            str(impl_path),
            "--json",
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=os.getcwd(),
        )
        self.assertEqual(result.returncode, 0)

        payload = json.loads(result.stdout)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload.get("is_docked"), True)
        self.assertEqual(payload.get("defects"), [])
        has_serialize = any(
            "serialize" in method_name
            for method_name in payload.get("verified_methods", [])
        )
        self.assertTrue(has_serialize)


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.ast_docking_checker pending implementation by software-engineer",
)
class TestAstDockingAdversarial(unittest.TestCase):
    """Adversarial suite asserting signature defects, malformed files, and CLI errors."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_negative_missing_method_in_impl_returns_undocked(self) -> None:
        """Negative test: Missing method in impl returns is_docked=False & MISSING_METHOD."""
        proto_path = self.work_dir / "miss_proto.py"
        impl_path = self.work_dir / "miss_impl.py"
        proto_methods = [
            ("existing_method", ["self"]),
            ("missing_method", ["self", "arg"]),
        ]
        impl_methods = [("existing_method", ["self"])]
        _write_protocol_source(proto_path, "MissProto", proto_methods)
        _write_impl_source(impl_path, "MissImpl", impl_methods)

        report = verify_ast_docking(proto_path, impl_path)

        self.assertFalse(report.is_docked)
        self.assertGreater(len(report.defects), 0)
        missing_defects = [
            d for d in report.defects if d.defect_type == "MISSING_METHOD"
        ]
        self.assertGreater(len(missing_defects), 0)
        self.assertEqual(missing_defects[0].method_name, "missing_method")

    def test_negative_parameter_count_mismatch_returns_undocked(self) -> None:
        """Negative test: Parameter count mismatch returns PARAM_COUNT_MISMATCH."""
        proto_path = self.work_dir / "count_proto.py"
        impl_path = self.work_dir / "count_impl.py"
        _write_protocol_source(
            proto_path,
            "CountProto",
            [("calculate", ["self", "x", "y"])],
        )
        _write_impl_source(
            impl_path,
            "CountImpl",
            [("calculate", ["self", "x"])],
        )

        report = verify_ast_docking(proto_path, impl_path)

        self.assertFalse(report.is_docked)
        count_defects = [
            d for d in report.defects if d.defect_type == "PARAM_COUNT_MISMATCH"
        ]
        self.assertGreater(len(count_defects), 0)
        self.assertEqual(count_defects[0].method_name, "calculate")

    def test_negative_parameter_name_mismatch_returns_undocked(self) -> None:
        """Negative test: Parameter name mismatch returns PARAM_NAME_MISMATCH."""
        proto_path = self.work_dir / "name_proto.py"
        impl_path = self.work_dir / "name_impl.py"
        _write_protocol_source(
            proto_path,
            "NameProto",
            [("search", ["self", "query_string"])],
        )
        _write_impl_source(
            impl_path,
            "NameImpl",
            [("search", ["self", "search_term"])],
        )

        report = verify_ast_docking(proto_path, impl_path)

        self.assertFalse(report.is_docked)
        name_defects = [
            d for d in report.defects if d.defect_type == "PARAM_NAME_MISMATCH"
        ]
        self.assertGreater(len(name_defects), 0)
        self.assertEqual(name_defects[0].method_name, "search")

    def test_negative_nonexistent_proto_file_fail_open(self) -> None:
        """Negative test: Nonexistent proto file fails open with diagnostic defect [INV-DOCK-05]."""
        missing_proto = self.work_dir / "nonexistent_proto.py"
        valid_impl = self.work_dir / "valid_impl.py"
        _write_impl_source(valid_impl, "Impl", [("m", ["self"])])

        report = verify_ast_docking(missing_proto, valid_impl)

        self.assertIsInstance(report, DockingReport)
        self.assertFalse(report.is_docked)
        self.assertGreater(len(report.defects), 0)

    def test_negative_nonexistent_impl_file_fail_open(self) -> None:
        """Negative test: Nonexistent impl file fails open with diagnostic defect [INV-DOCK-05]."""
        valid_proto = self.work_dir / "valid_proto.py"
        missing_impl = self.work_dir / "nonexistent_impl.py"
        _write_protocol_source(valid_proto, "Proto", [("m", ["self"])])

        report = verify_ast_docking(valid_proto, missing_impl)

        self.assertIsInstance(report, DockingReport)
        self.assertFalse(report.is_docked)
        self.assertGreater(len(report.defects), 0)

    def test_negative_malformed_syntax_in_proto_file_fail_open(self) -> None:
        """Negative test: Malformed syntax in proto file fails open with defect [INV-DOCK-05]."""
        corrupted_proto = self.work_dir / "corrupt_proto.py"
        corrupted_proto.write_text("class Def (Invalid Syntax ;:\n", encoding="utf-8")
        valid_impl = self.work_dir / "valid_impl.py"
        _write_impl_source(valid_impl, "Impl", [("m", ["self"])])

        report = verify_ast_docking(corrupted_proto, valid_impl)

        self.assertIsInstance(report, DockingReport)
        self.assertFalse(report.is_docked)
        self.assertGreater(len(report.defects), 0)

    def test_negative_malformed_syntax_in_impl_file_fail_open(self) -> None:
        """Negative test: Malformed syntax in impl file fails open with defect [INV-DOCK-05]."""
        valid_proto = self.work_dir / "valid_proto.py"
        _write_protocol_source(valid_proto, "Proto", [("m", ["self"])])
        corrupted_impl = self.work_dir / "corrupt_impl.py"
        corrupted_impl.write_text("def unclosed_function(:\n", encoding="utf-8")

        report = verify_ast_docking(valid_proto, corrupted_impl)

        self.assertIsInstance(report, DockingReport)
        self.assertFalse(report.is_docked)
        self.assertGreater(len(report.defects), 0)

    def test_negative_cli_mismatch_exits_code_one(self) -> None:
        """Negative test: CLI invocation on signature mismatch exits code 1 [INV-DOCK-03]."""
        proto_path = self.work_dir / "cli_mismatch_proto.py"
        impl_path = self.work_dir / "cli_mismatch_impl.py"
        _write_protocol_source(proto_path, "P", [("do_work", ["self"])])
        _write_impl_source(impl_path, "I", [("do_other_work", ["self"])])

        target_module = "core.ast_docking_checker"
        if not Path("core/ast_docking_checker.py").exists():
            target_module = "sandbox.core.ast_docking_checker"

        cmd = [
            sys.executable,
            "-m",
            target_module,
            "--proto",
            str(proto_path),
            "--impl",
            str(impl_path),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=os.getcwd(),
        )
        self.assertEqual(
            result.returncode,
            1,
            "CLI on signature divergence should exit with status 1",
        )

    def test_negative_cli_json_mismatch_outputs_valid_json(self) -> None:
        """Negative test: CLI --json on signature mismatch exits 1 and emits valid JSON."""
        proto_path = self.work_dir / "json_mismatch_proto.py"
        impl_path = self.work_dir / "json_mismatch_impl.py"
        _write_protocol_source(proto_path, "P", [("render", ["self", "view"])])
        _write_impl_source(impl_path, "I", [("render", ["self", "component"])])

        target_module = "core.ast_docking_checker"
        if not Path("core/ast_docking_checker.py").exists():
            target_module = "sandbox.core.ast_docking_checker"

        cmd = [
            sys.executable,
            "-m",
            target_module,
            "--proto",
            str(proto_path),
            "--impl",
            str(impl_path),
            "--json",
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=os.getcwd(),
        )
        self.assertEqual(result.returncode, 1)

        payload = json.loads(result.stdout)
        self.assertEqual(payload.get("is_docked"), False)
        self.assertGreater(len(payload.get("defects", [])), 0)

    def test_negative_multiple_divergent_defects_aggregated(self) -> None:
        """Negative test: Aggregates multiple defects (missing + parameter count mismatch)."""
        proto_path = self.work_dir / "multi_defect_proto.py"
        impl_path = self.work_dir / "multi_defect_impl.py"
        _write_protocol_source(
            proto_path,
            "MultiDefectProto",
            [
                ("method_missing", ["self"]),
                ("method_mismatched", ["self", "a", "b"]),
            ],
        )
        _write_impl_source(
            impl_path,
            "MultiDefectImpl",
            [("method_mismatched", ["self", "a"])],
        )

        report = verify_ast_docking(proto_path, impl_path)

        self.assertFalse(report.is_docked)
        self.assertGreaterEqual(
            len(report.defects),
            2,
            "Expected at least 2 distinct defects aggregated in report",
        )
        defect_types = {d.defect_type for d in report.defects}
        self.assertIn("MISSING_METHOD", defect_types)
        self.assertIn("PARAM_COUNT_MISMATCH", defect_types)


if __name__ == "__main__":
    unittest.main()
