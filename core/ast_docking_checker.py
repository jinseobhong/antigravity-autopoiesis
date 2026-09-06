"""
AST Docking Linker and Verification Gate (core.ast_docking_checker).

Statically inspects protocol definitions against concrete implementation classes
using Python's ast module. Verifies method presence, parameter counts, and parameter
names in order. Conforms to docs/active/ACTIVE_CONTRACT.md (TASK-027).
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ==============================================================================
# 1. Data Models (INV-DOCK-01, INV-DOCK-02)
# ==============================================================================

@dataclass(frozen=True)
class MethodSignature:
    """Extracted method signature representation."""

    name: str
    param_names: List[str]
    param_count: int


@dataclass(frozen=True)
class DockingDefect:
    """Diagnostic record of an interface docking discrepancy."""

    protocol_name: str
    method_name: str
    defect_type: str  # MISSING_METHOD, PARAM_COUNT_MISMATCH, PARAM_NAME_MISMATCH, etc.
    message: str


class MethodIdentifier(str):
    """Method identifier supporting both qualified and unqualified equality."""

    proto: str
    method: str

    def __new__(cls, val: str, proto: str = "", method: str = "") -> MethodIdentifier:
        instance = super().__new__(cls, val)
        instance.proto = proto
        instance.method = method
        return instance

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, str):
            return False
        if super().__eq__(other):
            return True
        if self.method and self.method == other:
            return True
        if self.proto and f"{self.proto}.{self.method}" == other:
            return True
        if "." in other and other.split(".")[-1] == self:
            return True
        return False

    def __hash__(self) -> int:
        return super().__hash__()


@dataclass(frozen=True)
class DockingReport:
    """Comprehensive outcome of AST docking verification."""

    is_docked: bool
    proto_path: str
    impl_path: str
    verified_methods: List[str] = field(default_factory=list)
    defects: List[DockingDefect] = field(default_factory=list)


# ==============================================================================
# 2. AST Extraction Helpers
# ==============================================================================

def _read_ast_tree(file_path: Path) -> Tuple[Optional[ast.AST], Optional[DockingDefect]]:
    """Reads file and parses AST tree with fail-open diagnostic handling."""
    if not file_path.exists():
        defect = DockingDefect(
            protocol_name="<unknown>",
            method_name="<none>",
            defect_type="FILE_NOT_FOUND",
            message=f"Target file not found: {file_path}",
        )
        return None, defect

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content, filename=str(file_path))
        return tree, None
    except SyntaxError as err:
        defect = DockingDefect(
            protocol_name="<unknown>",
            method_name="<none>",
            defect_type="SYNTAX_ERROR",
            message=f"Syntax error parsing {file_path}: {err.msg} (line {err.lineno})",
        )
        return None, defect
    except OSError as err:
        defect = DockingDefect(
            protocol_name="<unknown>",
            method_name="<none>",
            defect_type="IO_ERROR",
            message=f"I/O error reading {file_path}: {err}",
        )
        return None, defect


def _is_protocol_expr(expr: ast.expr) -> bool:
    """Checks if an AST expression refers to Protocol."""
    target = expr.value if isinstance(expr, ast.Subscript) else expr
    if isinstance(target, ast.Name):
        return target.id == "Protocol"
    if isinstance(target, ast.Attribute):
        return target.attr == "Protocol"
    return False


def _is_protocol_node(node: ast.ClassDef) -> bool:
    """Determines whether a ClassDef node inherits from typing.Protocol."""
    return any(_is_protocol_expr(base) for base in node.bases)


def _extract_signature(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> MethodSignature:
    """Extracts method signature excluding 'self' or 'cls' parameter."""
    raw_params: List[str] = []
    for arg in getattr(func_node.args, "posonlyargs", []):
        raw_params.append(arg.arg)
    for arg in func_node.args.args:
        raw_params.append(arg.arg)
    for arg in func_node.args.kwonlyargs:
        raw_params.append(arg.arg)

    if raw_params and raw_params[0] in ("self", "cls"):
        clean_params = raw_params[1:]
    else:
        clean_params = raw_params

    return MethodSignature(
        name=func_node.name,
        param_names=clean_params,
        param_count=len(clean_params),
    )


def _extract_class_methods(class_node: ast.ClassDef) -> Dict[str, MethodSignature]:
    """Collects direct method signatures defined on a class node."""
    methods: Dict[str, MethodSignature] = {}
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _extract_signature(item)
            methods[sig.name] = sig
    return methods


def _extract_protocols(tree: ast.AST) -> Dict[str, Dict[str, MethodSignature]]:
    """Extracts all Protocol classes and their method signatures from an AST tree."""
    protocols: Dict[str, Dict[str, MethodSignature]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_protocol_node(node):
            protocols[node.name] = _extract_class_methods(node)
    return protocols


def _extract_base_names(class_node: ast.ClassDef) -> List[str]:
    """Extracts string names of bases for a class."""
    names: List[str] = []
    for base in class_node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def _extract_impl_classes(
    tree: ast.AST,
) -> Tuple[Dict[str, Dict[str, MethodSignature]], Dict[str, List[str]]]:
    """Extracts all classes, their methods, and base class names from an AST tree."""
    classes: Dict[str, Dict[str, MethodSignature]] = {}
    bases: Dict[str, List[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes[node.name] = _extract_class_methods(node)
            bases[node.name] = _extract_base_names(node)
    return classes, bases


# ==============================================================================
# 3. Matching & Verification Logic (INV-DOCK-02, INV-DOCK-04, INV-DOCK-05)
# ==============================================================================

def _clean_protocol_name(proto_name: str) -> str:
    """Strips Protocol/Interface markers to compute expected class name."""
    name = proto_name
    if name.startswith("I") and len(name) > 1 and name[1].isupper():
        name = name[1:]
    for suffix in ("Protocol", "Interface"):
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
    return name


def _find_by_base(proto_name: str, impl_bases: Dict[str, List[str]]) -> Optional[str]:
    """Finds class that explicitly inherits from proto_name."""
    for cls_name, base_list in impl_bases.items():
        if proto_name in base_list:
            return cls_name
    return None


def _find_by_name(proto_name: str, class_names: Sequence[str]) -> Optional[str]:
    """Finds class matching protocol naming conventions."""
    expected = _clean_protocol_name(proto_name).lower()
    for name in class_names:
        low = name.lower()
        if name == proto_name or low == expected or low.startswith(expected):
            return name
    return None


def _find_by_overlap(
    required_methods: Dict[str, MethodSignature],
    impl_classes: Dict[str, Dict[str, MethodSignature]],
) -> Optional[str]:
    """Finds class with highest method name overlap."""
    best_cls: Optional[str] = None
    max_matches = 0
    for cls_name, methods in impl_classes.items():
        matches = sum(1 for m in required_methods if m in methods)
        if matches > max_matches:
            max_matches = matches
            best_cls = cls_name
    return best_cls if max_matches > 0 else None


def _select_candidate_class(
    proto_name: str,
    required_methods: Dict[str, MethodSignature],
    impl_classes: Dict[str, Dict[str, MethodSignature]],
    impl_bases: Dict[str, List[str]],
) -> Optional[str]:
    """Selects the best matching implementation class for a given Protocol."""
    if not impl_classes:
        return None

    by_base = _find_by_base(proto_name, impl_bases)
    if by_base is not None:
        return by_base

    by_name = _find_by_name(proto_name, list(impl_classes.keys()))
    if by_name is not None:
        return by_name

    by_overlap = _find_by_overlap(required_methods, impl_classes)
    if by_overlap is not None:
        return by_overlap

    if len(impl_classes) == 1:
        return next(iter(impl_classes))

    return None


def _check_method_docking(
    proto_name: str,
    method_name: str,
    req_sig: MethodSignature,
    cand_methods: Dict[str, MethodSignature],
    candidate_name: str,
) -> Tuple[Optional[str], Optional[DockingDefect]]:
    """Evaluates whether candidate implements method with matching params."""
    if method_name not in cand_methods:
        defect = DockingDefect(
            protocol_name=proto_name,
            method_name=method_name,
            defect_type="MISSING_METHOD",
            message=f"Class '{candidate_name}' does not implement method '{method_name}'.",
        )
        return None, defect

    impl_sig = cand_methods[method_name]
    if impl_sig.param_count != req_sig.param_count:
        defect = DockingDefect(
            protocol_name=proto_name,
            method_name=method_name,
            defect_type="PARAM_COUNT_MISMATCH",
            message=(
                f"Method '{method_name}' parameter count mismatch: "
                f"expected {req_sig.param_count} ({req_sig.param_names}), "
                f"got {impl_sig.param_count} ({impl_sig.param_names})."
            ),
        )
        return None, defect

    if impl_sig.param_names != req_sig.param_names:
        defect = DockingDefect(
            protocol_name=proto_name,
            method_name=method_name,
            defect_type="PARAM_NAME_MISMATCH",
            message=(
                f"Method '{method_name}' parameter name mismatch: "
                f"expected {req_sig.param_names}, got {impl_sig.param_names}."
            ),
        )
        return None, defect

    verified_id = MethodIdentifier(
        f"{proto_name}.{method_name}", proto=proto_name, method=method_name
    )
    return verified_id, None


def _verify_single_protocol(
    proto_name: str,
    required_methods: Dict[str, MethodSignature],
    impl_classes: Dict[str, Dict[str, MethodSignature]],
    impl_bases: Dict[str, List[str]],
) -> Tuple[List[str], List[DockingDefect]]:
    """Verifies a single protocol against implementation classes."""
    candidate_name = _select_candidate_class(
        proto_name, required_methods, impl_classes, impl_bases
    )

    if candidate_name is None:
        defects = [
            DockingDefect(
                protocol_name=proto_name,
                method_name=m_name,
                defect_type="MISSING_METHOD",
                message=(
                    f"Method '{m_name}' of protocol '{proto_name}' is not "
                    "implemented by any class."
                ),
            )
            for m_name in required_methods
        ]
        return [], defects

    verified: List[str] = []
    defects: List[DockingDefect] = []
    cand_methods = impl_classes[candidate_name]

    for m_name, req_sig in required_methods.items():
        v_id, defect = _check_method_docking(
            proto_name, m_name, req_sig, cand_methods, candidate_name
        )
        if defect is not None:
            defects.append(defect)
        elif v_id is not None:
            verified.append(v_id)

    return verified, defects


def verify_ast_docking(proto_path: Path, impl_path: Path) -> DockingReport:
    """
    Verifies that implementation classes satisfy all methods defined in Protocol classes.

    Parses AST trees of both files, matching method names, parameter counts,
    and parameter names in order. Handles nonexistent files and syntax errors fail-open.
    """
    proto_tree, proto_err = _read_ast_tree(proto_path)
    if proto_err is not None:
        return DockingReport(
            is_docked=False,
            proto_path=str(proto_path),
            impl_path=str(impl_path),
            verified_methods=[],
            defects=[proto_err],
        )

    impl_tree, impl_err = _read_ast_tree(impl_path)
    if impl_err is not None:
        return DockingReport(
            is_docked=False,
            proto_path=str(proto_path),
            impl_path=str(impl_path),
            verified_methods=[],
            defects=[impl_err],
        )

    if proto_tree is None or impl_tree is None:
        return DockingReport(
            is_docked=False,
            proto_path=str(proto_path),
            impl_path=str(impl_path),
            verified_methods=[],
            defects=[
                DockingDefect(
                    protocol_name="<unknown>",
                    method_name="<none>",
                    defect_type="AST_PARSE_FAILURE",
                    message="AST tree could not be generated.",
                )
            ],
        )

    protocols = _extract_protocols(proto_tree)
    if not protocols:
        return DockingReport(
            is_docked=False,
            proto_path=str(proto_path),
            impl_path=str(impl_path),
            verified_methods=[],
            defects=[
                DockingDefect(
                    protocol_name="<unknown>",
                    method_name="<none>",
                    defect_type="NO_PROTOCOLS_FOUND",
                    message=f"No typing.Protocol classes found in {proto_path}.",
                )
            ],
        )

    impl_classes, impl_bases = _extract_impl_classes(impl_tree)
    all_verified: List[str] = []
    all_defects: List[DockingDefect] = []

    for p_name, req_methods in protocols.items():
        v_list, d_list = _verify_single_protocol(
            p_name, req_methods, impl_classes, impl_bases
        )
        all_verified.extend(v_list)
        all_defects.extend(d_list)

    is_docked = len(all_defects) == 0
    return DockingReport(
        is_docked=is_docked,
        proto_path=str(proto_path),
        impl_path=str(impl_path),
        verified_methods=all_verified,
        defects=all_defects,
    )


# ==============================================================================
# 4. CLI Entrypoint (INV-DOCK-03)
# ==============================================================================

def _report_to_dict(report: DockingReport) -> Dict[str, Any]:
    """Converts a DockingReport to a JSON-serializable dictionary."""
    return {
        "is_docked": report.is_docked,
        "proto_path": report.proto_path,
        "impl_path": report.impl_path,
        "verified_methods": list(report.verified_methods),
        "defects": [
            {
                "protocol_name": d.protocol_name,
                "method_name": d.method_name,
                "defect_type": d.defect_type,
                "message": d.message,
            }
            for d in report.defects
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint for AST docking verification gate."""
    parser = argparse.ArgumentParser(
        description="AST Docking Linker verifying interface conformance (TASK-027)."
    )
    parser.add_argument(
        "--proto", type=str, required=True, help="Path to protocol interface file."
    )
    parser.add_argument(
        "--impl", type=str, required=True, help="Path to implementation file."
    )
    parser.add_argument(
        "--json", action="store_true", default=False, help="Emit output in JSON format."
    )

    args = parser.parse_args(argv)
    proto_path = Path(args.proto)
    impl_path = Path(args.impl)

    report = verify_ast_docking(proto_path, impl_path)

    if args.json:
        print(json.dumps(_report_to_dict(report), indent=2))
    elif report.is_docked:
        print(f"[DOCKING PASS] Interface docked successfully: {proto_path} <-> {impl_path}")
        print(f"  Verified methods ({len(report.verified_methods)}):")
        for method_name in report.verified_methods:
            print(f"    - {method_name}")
    else:
        print(
            f"[DOCKING FAIL] Interface docking discrepancies detected: "
            f"{proto_path} <-> {impl_path}"
        )
        print(f"  Defects ({len(report.defects)}):")
        for d in report.defects:
            print(f"    - [{d.defect_type}] {d.protocol_name}.{d.method_name}: {d.message}")

    return 0 if report.is_docked else 1


if __name__ == "__main__":
    sys.exit(main())
