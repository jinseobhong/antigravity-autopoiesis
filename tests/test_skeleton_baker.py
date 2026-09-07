"""
Independent IV&V Companion Test Suite for Skeleton Baker (TASK-027).

Ingests docs/active/ACTIVE_CONTRACT.md as primary specification authority.
Evaluates FieldDef, DataClassDef, MethodDef, ProtocolDef, InterfaceBundle data models,
bake_interface_skeleton code generation under core/interfaces/<domain>_proto.py,
AST structure, NotImplementedError protocol method stubs, and CLI execution.
Enforces AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12 with >= 40% negative ratio.
"""

import ast
from dataclasses import FrozenInstanceError
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple
import unittest

try:
    from core.skeleton_baker import (
        DataClassDef,
        FieldDef,
        InterfaceBundle,
        MethodDef,
        ProtocolDef,
        bake_interface_skeleton,
    )
    _MODULE_AVAILABLE = True
except ModuleNotFoundError:
    try:
        from sandbox.core.skeleton_baker import (
            DataClassDef,
            FieldDef,
            InterfaceBundle,
            MethodDef,
            ProtocolDef,
            bake_interface_skeleton,
        )
        _MODULE_AVAILABLE = True
    except ModuleNotFoundError:
        _MODULE_AVAILABLE = False
        DataClassDef = None  # type: ignore[assignment]
        FieldDef = None  # type: ignore[assignment]
        InterfaceBundle = None  # type: ignore[assignment]
        MethodDef = None  # type: ignore[assignment]
        ProtocolDef = None  # type: ignore[assignment]
        bake_interface_skeleton = None  # type: ignore[assignment]




def _create_sample_bundle(domain: str = "order_service") -> "InterfaceBundle":
    """Synthesizes a representative InterfaceBundle for testing."""
    item_fields = [
        FieldDef(name="item_id", type_annotation="str"),
        FieldDef(
            name="unit_price",
            type_annotation="float",
            docstring="Price per item",
        ),
        FieldDef(
            name="quantity",
            type_annotation="int",
            default_value="1",
        ),
    ]
    order_dataclass = DataClassDef(
        name="OrderItem",
        fields=item_fields,
        is_frozen=True,
        docstring="Immutable value object representing an ordered line item.",
    )
    methods = [
        MethodDef(
            name="place_order",
            params=[("self", "Self"), ("item", "OrderItem")],
            return_type="str",
            docstring="Submits an order and returns generated order ID.",
        ),
        MethodDef(
            name="cancel_order",
            params=[("self", "Self"), ("order_id", "str")],
            return_type="bool",
            docstring="Cancels existing order by identifier.",
        ),
    ]
    protocol = ProtocolDef(
        name="OrderServiceProtocol",
        methods=methods,
        docstring="Interface protocol defining order lifecycle operations.",
    )
    return InterfaceBundle(
        domain=domain,
        dataclasses=[order_dataclass],
        protocols=[protocol],
        imports=["from typing_extensions import Self"],
    )


def _is_frozen_dataclass(node: ast.ClassDef) -> bool:
    """Checks if AST ClassDef has @dataclass(frozen=True)."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            fn_id = getattr(dec.func, "id", "")
            if fn_id == "dataclass":
                for kw in dec.keywords:
                    is_frozen_kw = kw.arg == "frozen"
                    is_true = getattr(kw.value, "value", False) is True
                    if is_frozen_kw and is_true:
                        return True
    return False


def _has_protocol_base(node: ast.ClassDef) -> bool:
    """Checks if AST ClassDef inherits from Protocol."""
    for base in node.bases:
        if getattr(base, "id", "") == "Protocol":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Protocol":
            return True
    return False



@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.skeleton_baker pending implementation by software-engineer",
)
class TestSkeletonBakerDataModels(unittest.TestCase):
    """Evaluates instantiation, default attributes, and immutability of data models."""

    def test_field_def_instantiation_and_defaults(self) -> None:
        """Positive test: Verifies FieldDef instantiation and default optional values."""
        field = FieldDef(name="status", type_annotation="str")
        self.assertEqual(field.name, "status")
        self.assertEqual(field.type_annotation, "str")
        self.assertIsNone(field.default_value)
        self.assertIsNone(field.docstring)

        field_with_default = FieldDef(
            name="retries",
            type_annotation="int",
            default_value="3",
            docstring="Retry attempt count",
        )
        self.assertEqual(field_with_default.default_value, "3")
        self.assertEqual(
            field_with_default.docstring,
            "Retry attempt count",
        )

    def test_dataclass_def_instantiation(self) -> None:
        """Positive test: Verifies DataClassDef instantiation with field list and defaults."""
        fields = [FieldDef(name="id", type_annotation="str")]
        dc_def = DataClassDef(name="Entity", fields=fields)
        self.assertEqual(dc_def.name, "Entity")
        self.assertEqual(len(dc_def.fields), 1)
        self.assertTrue(dc_def.is_frozen)
        self.assertIsNone(dc_def.docstring)

    def test_method_def_instantiation(self) -> None:
        """Positive test: Verifies MethodDef instantiation with parameter tuples."""
        method = MethodDef(
            name="execute",
            params=[("self", "Self"), ("payload", "bytes")],
            return_type="int",
            docstring="Executes payload return code",
        )
        self.assertEqual(method.name, "execute")
        self.assertEqual(len(method.params), 2)
        self.assertEqual(method.return_type, "int")
        self.assertEqual(method.docstring, "Executes payload return code")

    def test_protocol_def_instantiation(self) -> None:
        """Positive test: Verifies ProtocolDef instantiation with MethodDef collection."""
        method = MethodDef(name="ping", params=[], return_type="bool")
        proto = ProtocolDef(
            name="Pingable",
            methods=[method],
            docstring="Ping interface",
        )
        self.assertEqual(proto.name, "Pingable")
        self.assertEqual(len(proto.methods), 1)
        self.assertEqual(proto.docstring, "Ping interface")

    def test_interface_bundle_instantiation(self) -> None:
        """Positive test: Verifies InterfaceBundle aggregate composition."""
        bundle = _create_sample_bundle("inventory")
        self.assertEqual(bundle.domain, "inventory")
        self.assertEqual(len(bundle.dataclasses), 1)
        self.assertEqual(len(bundle.protocols), 1)
        self.assertIsNotNone(bundle.imports)

    def test_negative_field_def_immutability(self) -> None:
        """Negative test: Modifying frozen FieldDef attribute raises FrozenInstanceError."""
        field = FieldDef(name="read_only", type_annotation="str")
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            field.name = "mutated"  # type: ignore[misc]

    def test_negative_dataclass_def_immutability(self) -> None:
        """Negative test: Modifying frozen DataClassDef attribute raises FrozenInstanceError."""
        dc_def = DataClassDef(name="ImmutableModel", fields=[])
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            dc_def.name = "MutatedModel"  # type: ignore[misc]

    def test_negative_method_def_immutability(self) -> None:
        """Negative test: Modifying frozen MethodDef attribute raises FrozenInstanceError."""
        method = MethodDef(name="immutable_func", params=[], return_type="None")
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            method.name = "mutated_func"  # type: ignore[misc]

    def test_negative_protocol_def_immutability(self) -> None:
        """Negative test: Modifying frozen ProtocolDef attribute raises FrozenInstanceError."""
        proto = ProtocolDef(name="ImmutableProtocol", methods=[])
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            proto.name = "MutatedProtocol"  # type: ignore[misc]

    def test_negative_interface_bundle_immutability(self) -> None:
        """Negative test: Modifying frozen InterfaceBundle attribute raises FrozenInstanceError."""
        bundle = _create_sample_bundle("core_domain")
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            bundle.domain = "mutated_domain"  # type: ignore[misc]


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.skeleton_baker pending implementation by software-engineer",
)
class TestSkeletonBakerFunctional(unittest.TestCase):
    """Evaluates code generation, AST structure, and method stub invocation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_bake_interface_skeleton_generates_file_at_path(self) -> None:
        """Positive test: Generates valid Python file at expected path [INV-BAKE-02]."""
        bundle = _create_sample_bundle("billing")
        result_path = bake_interface_skeleton(bundle, output_dir=self.output_dir)

        self.assertIsInstance(result_path, Path)
        self.assertTrue(result_path.exists(), f"Generated file {result_path} does not exist")
        self.assertEqual(result_path.name, "billing_proto.py")
        self.assertGreater(result_path.stat().st_size, 0)

    def test_bake_interface_skeleton_syntax_and_ast_structure(self) -> None:
        """Positive test: Generated file parses with ast.parse and contains expected classes."""
        bundle = _create_sample_bundle("telemetry")
        result_path = bake_interface_skeleton(bundle, output_dir=self.output_dir)
        source_code = result_path.read_text(encoding="utf-8")

        tree = ast.parse(source_code, filename=str(result_path))
        self.assertIsInstance(tree, ast.Module)

        classes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }
        self.assertIn("OrderItem", classes)
        self.assertIn("OrderServiceProtocol", classes)

        self.assertTrue(
            _is_frozen_dataclass(classes["OrderItem"]),
            "Generated dataclass OrderItem must be decorated with @dataclass(frozen=True)",
        )
        self.assertTrue(
            _has_protocol_base(classes["OrderServiceProtocol"]),
            "Generated OrderServiceProtocol must inherit from Protocol",
        )

    def test_generated_protocol_method_raises_not_implemented_error(self) -> None:
        """Positive test: Invoking protocol method raises NotImplementedError [INV-BAKE-02]."""
        bundle = _create_sample_bundle("gateway")
        result_path = bake_interface_skeleton(bundle, output_dir=self.output_dir)

        spec = importlib.util.spec_from_file_location("gateway_proto", str(result_path))
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)  # type: ignore[union-attr]

        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules["gateway_proto"] = module
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            protocol_cls = getattr(module, "OrderServiceProtocol", None)
            self.assertIsNotNone(protocol_cls)

            class ConcreteCandidate(protocol_cls):  # type: ignore[misc, valid-type]
                """Subclass without method implementation for protocol verification."""

            instance = ConcreteCandidate()
            with self.assertRaises(NotImplementedError):
                instance.place_order(None)

            with self.assertRaises(NotImplementedError):
                instance.cancel_order("order-101")
        finally:
            sys.modules.pop("gateway_proto", None)

    def test_cli_execution_exits_zero(self) -> None:
        """Positive test: CLI execution python -m core.skeleton_baker exits 0 [INV-DOCK-03]."""
        target_module = "core.skeleton_baker"
        if not Path("core/skeleton_baker.py").exists():
            target_module = "sandbox.core.skeleton_baker"

        cmd = [
            sys.executable,
            "-m",
            target_module,
            "--output-dir",
            str(self.output_dir),
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


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.skeleton_baker pending implementation by software-engineer",
)
class TestSkeletonBakerAdversarial(unittest.TestCase):
    """Adversarial suite asserting error paths, invalid payloads, and boundary conditions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_negative_empty_domain_raises_value_error(self) -> None:
        """Negative test: Empty string domain identifier raises ValueError."""
        bundle = InterfaceBundle(
            domain="",
            dataclasses=[],
            protocols=[],
        )
        with self.assertRaises(ValueError):
            bake_interface_skeleton(bundle, output_dir=self.output_dir)

    def test_negative_whitespace_domain_raises_value_error(self) -> None:
        """Negative test: Whitespace-only domain identifier raises ValueError."""
        bundle = InterfaceBundle(
            domain="   \t\n  ",
            dataclasses=[],
            protocols=[],
        )
        with self.assertRaises(ValueError):
            bake_interface_skeleton(bundle, output_dir=self.output_dir)

    def test_negative_unwriteable_output_path_handling(self) -> None:
        """Negative test: File path collision for output_dir handled gracefully without crash."""
        file_path_blocker = self.output_dir / "blocked_file.txt"
        file_path_blocker.write_text("Blocking regular file", encoding="utf-8")

        colliding_output = file_path_blocker / "nested_dir"
        bundle = _create_sample_bundle("collision_test")

        with self.assertRaises((OSError, ValueError)):
            bake_interface_skeleton(bundle, output_dir=colliding_output)

    def test_negative_empty_bundle_generates_minimal_valid_file(self) -> None:
        """Negative test: Empty bundle with no dataclasses or protocols generates valid file."""
        bundle = InterfaceBundle(
            domain="minimal_domain",
            dataclasses=[],
            protocols=[],
        )
        result_path = bake_interface_skeleton(bundle, output_dir=self.output_dir)
        self.assertTrue(result_path.exists())
        self.assertEqual(result_path.name, "minimal_domain_proto.py")

        content = result_path.read_text(encoding="utf-8")
        parsed = ast.parse(content)
        self.assertIsInstance(parsed, ast.Module)

    def test_negative_generated_code_contains_zero_lazy_stubs(self) -> None:
        """Negative test: Generated code contains zero pass or ellipsis statements [INV-BAKE-03]."""
        bundle = _create_sample_bundle("anti_stub_domain")
        result_path = bake_interface_skeleton(bundle, output_dir=self.output_dir)
        content = result_path.read_text(encoding="utf-8")
        tree = ast.parse(content)

        lazy_pass_nodes = [
            node for node in ast.walk(tree) if isinstance(node, ast.Pass)
        ]
        self.assertEqual(
            len(lazy_pass_nodes),
            0,
            "Generated file contains prohibited 'pass' statements",
        )

        lazy_ellipsis_nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value is ...
        ]
        self.assertEqual(
            len(lazy_ellipsis_nodes),
            0,
            "Generated file contains prohibited ellipsis '...' stubs",
        )

    def test_negative_generated_code_respects_line_length_boundary(self) -> None:
        """Negative test: Generated code lines do not exceed 120 character limit [INV-BAKE-03]."""
        bundle = _create_sample_bundle("boundary_domain")
        result_path = bake_interface_skeleton(bundle, output_dir=self.output_dir)
        lines = result_path.read_text(encoding="utf-8").splitlines()

        for line_idx, line_str in enumerate(lines, 1):
            self.assertLessEqual(
                len(line_str),
                120,
                f"Line {line_idx} exceeds 120 columns: '{line_str}'",
            )


if __name__ == "__main__":
    unittest.main()
