"""
Mechanical Interface Skeleton Baker (core.skeleton_baker).

Synthesizes typed domain schemas into deterministic Python interface files
under core/interfaces/<domain>_proto.py containing frozen dataclasses and
typing.Protocol classes. Conforms to docs/active/ACTIVE_CONTRACT.md (TASK-027).
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import List, Optional, Sequence, Tuple


# ==============================================================================
# 1. Data Models (INV-BAKE-01)
# ==============================================================================

@dataclass(frozen=True)
class FieldDef:
    """Definition of a dataclass field attribute."""

    name: str
    type_annotation: str
    default_value: Optional[str] = None
    docstring: Optional[str] = None


@dataclass(frozen=True)
class DataClassDef:
    """Definition of a generated dataclass."""

    name: str
    fields: List[FieldDef]
    is_frozen: bool = True
    docstring: Optional[str] = None


@dataclass(frozen=True)
class MethodDef:
    """Definition of an interface protocol method signature."""

    name: str
    params: List[Tuple[str, str]]  # List of (param_name, type_annotation)
    return_type: str
    docstring: Optional[str] = None


@dataclass(frozen=True)
class ProtocolDef:
    """Definition of a typing.Protocol interface class."""

    name: str
    methods: List[MethodDef]
    docstring: Optional[str] = None


@dataclass(frozen=True)
class InterfaceBundle:
    """Aggregate bundle defining all interfaces for a specific domain."""

    domain: str
    dataclasses: List[DataClassDef]
    protocols: List[ProtocolDef]
    imports: Optional[List[str]] = None


# ==============================================================================
# 2. Code Generation Helpers
# ==============================================================================

def _generate_dataclass_code(dc: DataClassDef) -> List[str]:
    """Generates Python source lines for a dataclass definition."""
    lines: List[str] = []
    decorator = "@dataclass(frozen=True)" if dc.is_frozen else "@dataclass"
    lines.append(decorator)
    lines.append(f"class {dc.name}:")

    if dc.docstring:
        lines.append(f'    """{dc.docstring}"""')
    elif not dc.fields:
        lines.append(f'    """Data model {dc.name}."""')

    for field in dc.fields:
        if field.default_value is not None:
            lines.append(f"    {field.name}: {field.type_annotation} = {field.default_value}")
        else:
            lines.append(f"    {field.name}: {field.type_annotation}")
        if field.docstring:
            lines.append(f'    """{field.docstring}"""')

    lines.append("")
    return lines


def _format_method_params(params: List[Tuple[str, str]]) -> List[str]:
    """Formats parameter list ensuring 'self' is the first argument."""
    param_strs: List[str] = []
    has_self = len(params) > 0 and params[0][0] == "self"
    if not has_self:
        param_strs.append("self")

    for p_name, p_type in params:
        if p_name == "self" and not p_type:
            param_strs.append("self")
        elif p_type:
            param_strs.append(f"{p_name}: {p_type}")
        else:
            param_strs.append(p_name)
    return param_strs


def _generate_method_code(method: MethodDef) -> List[str]:
    """Generates Python source lines for a protocol method."""
    lines: List[str] = []
    param_strs = _format_method_params(method.params)
    joined_params = ", ".join(param_strs)
    single_line_sig = f"    def {method.name}({joined_params}) -> {method.return_type}:"

    if len(single_line_sig) <= 100:
        lines.append(single_line_sig)
    else:
        lines.append(f"    def {method.name}(")
        for p in param_strs:
            lines.append(f"        {p},")
        lines.append(f"    ) -> {method.return_type}:")

    if method.docstring:
        lines.append(f'        """{method.docstring}"""')
    lines.append(
        '        raise NotImplementedError("Protocol method must be implemented by concrete engine.")'
    )
    lines.append("")
    return lines


def _generate_protocol_code(proto: ProtocolDef) -> List[str]:
    """Generates Python source lines for a typing.Protocol class."""
    lines: List[str] = []
    lines.append(f"class {proto.name}(Protocol):")
    if proto.docstring:
        lines.append(f'    """{proto.docstring}"""')
    elif not proto.methods:
        lines.append(f'    """Interface protocol for {proto.name}."""')

    if proto.methods:
        lines.append("")
        for method in proto.methods:
            lines.extend(_generate_method_code(method))
    else:
        lines.append("")

    return lines


def _generate_bundle_code(bundle: InterfaceBundle) -> str:
    """Synthesizes complete Python module source from an InterfaceBundle."""
    base_typing = {"Any", "Dict", "List", "Optional", "Protocol", "Tuple"}
    lines: List[str] = [
        f'"""Mechanical interface protocol definitions for {bundle.domain}."""',
        "",
        "from dataclasses import dataclass",
        "from typing import Any, Dict, List, Optional, Protocol, Tuple",
    ]

    if bundle.imports:
        for imp in bundle.imports:
            cleaned = imp.strip()
            match = re.match(r"^from\s+typing\s+import\s+(.+)$", cleaned)
            if match and {s.strip() for s in match.group(1).split(",")}.issubset(base_typing):
                continue
            if cleaned and cleaned not in lines:
                lines.append(cleaned)

    lines.append("")
    lines.append("")

    for dc in bundle.dataclasses:
        lines.extend(_generate_dataclass_code(dc))
        lines.append("")

    for proto in bundle.protocols:
        lines.extend(_generate_protocol_code(proto))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _validate_synthesized_code(code: str) -> None:
    """Validates synthesized code with ast.parse and line length ceilings."""
    try:
        ast.parse(code)
    except SyntaxError as err:
        raise ValueError(f"Synthesized code failed AST validation: {err}") from err

    for idx, line in enumerate(code.splitlines(), start=1):
        if len(line) > 120:
            raise ValueError(f"Line {idx} exceeds 120 columns ({len(line)} cols): {line}")


def _resolve_default_output_dir() -> Path:
    """Deterministically resolves the core/interfaces directory."""
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / "GEMINI.md").exists() or (
            (current / "core").is_dir() and (current / "docs").is_dir()
        ):
            return current / "core" / "interfaces"
        if current.parent == current:
            break
        current = current.parent
    return Path.cwd() / "core" / "interfaces"


# ==============================================================================
# 3. Public API (INV-BAKE-02, INV-BAKE-03)
# ==============================================================================

def bake_interface_skeleton(
    bundle: InterfaceBundle,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Bakes a typed InterfaceBundle into a validated Python interface skeleton file.

    Generates core/interfaces/<domain>_proto.py containing frozen dataclasses and
    typing.Protocol classes where each method raises NotImplementedError.
    """
    if not bundle.domain or not bundle.domain.strip():
        raise ValueError("InterfaceBundle domain must be a non-empty string.")

    target_dir = Path(output_dir) if output_dir is not None else _resolve_default_output_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    init_file = target_dir / "__init__.py"
    if not init_file.exists():
        with open(init_file, "w", encoding="utf-8") as f:
            f.write('"""Mechanical interface protocol package."""\n')

    code = _generate_bundle_code(bundle)
    _validate_synthesized_code(code)

    domain_raw = bundle.domain.strip()
    if not domain_raw or not re.sub(r"[^a-zA-Z0-9_]", "", domain_raw):
        raise ValueError(f"Domain identifier must be a non-empty string, got: {bundle.domain!r}")

    domain_sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", domain_raw.lower())
    target_file = target_dir / f"{domain_sanitized}_proto.py"

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(code)

    return target_file


def create_demo_bundle() -> InterfaceBundle:
    """Creates a demonstration interface bundle for CLI testing."""
    return InterfaceBundle(
        domain="demo",
        dataclasses=[
            DataClassDef(
                name="DemoPayload",
                fields=[
                    FieldDef("payload_id", "str", docstring="Unique payload identifier."),
                    FieldDef("content", "str", default_value="''", docstring="Payload content."),
                ],
                is_frozen=True,
                docstring="Demo payload data container.",
            )
        ],
        protocols=[
            ProtocolDef(
                name="DemoProcessorProtocol",
                methods=[
                    MethodDef(
                        name="process",
                        params=[("payload", "DemoPayload")],
                        return_type="bool",
                        docstring="Process the demo payload.",
                    ),
                    MethodDef(
                        name="reset",
                        params=[],
                        return_type="None",
                        docstring="Reset processor state.",
                    ),
                ],
                docstring="Demo processor interface protocol.",
            )
        ],
        imports=["from typing import Optional"],
    )


# ==============================================================================
# 4. CLI Entrypoint (INV-DOCK-03)
# ==============================================================================

def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint for mechanical interface skeleton baker."""
    parser = argparse.ArgumentParser(
        description="Mechanical Interface Skeleton Baker conforming to TASK-027."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=False,
        help="Bake demonstration interface bundle.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional destination directory for interface files.",
    )

    args = parser.parse_args(argv)
    output_path = Path(args.output_dir) if args.output_dir else None

    bundle = create_demo_bundle()
    target_file = bake_interface_skeleton(bundle, output_path)
    print(f"[BAKE SUCCESS] Interface skeleton baked: {target_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
