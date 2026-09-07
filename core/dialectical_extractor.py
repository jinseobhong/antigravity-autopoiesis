"""
Dialectical Requirements Interrogator & Adversarial Red Team Engine (core.dialectical_extractor).

Conforms to:
- TASK-028: Dialectical Requirements Interrogator & Adversarial Red Team Engine
- docs/active/ACTIVE_CONTRACT.md ([INV-DIA-01] through [INV-DIA-07])
- AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12
- NASA SP-2016-6105 Normative Specification Standards
"""

import argparse
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.requirements_extractor import (
    AutoImmunizedNFR,
    RequirementsSpec,
    extract_requirements,
)


# ==============================================================================
# 1. Typed Value Objects & Data Models
# ==============================================================================

class PerspectiveType(str, Enum):
    """Dialectical viewpoints evaluated during requirements interrogation."""

    ARCHITECTURE = "ARCHITECTURE"
    RESILIENCE = "RESILIENCE"
    OPERATIONS = "OPERATIONS"


def _validate_non_empty(field_name: str, value: Any) -> None:
    """Validates that a field is a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty.")


@dataclass(frozen=True)
class CritiqueRecord:
    """Discrete adversarial critique generated from a dialectical perspective."""

    perspective: PerspectiveType
    concern: str
    failure_mode: str
    proposed_invariant: str
    severity: str = "MEDIUM"

    def __post_init__(self) -> None:
        """Enforces non-empty string invariants on critique attributes."""
        if isinstance(self.perspective, str) and not isinstance(self.perspective, PerspectiveType):
            object.__setattr__(self, "perspective", PerspectiveType(self.perspective))

        _validate_non_empty("CritiqueRecord.concern", self.concern)
        _validate_non_empty("CritiqueRecord.failure_mode", self.failure_mode)
        _validate_non_empty("CritiqueRecord.proposed_invariant", self.proposed_invariant)


@dataclass(frozen=True)
class DialecticalResult:
    """Aggregated outcome of multi-perspective adversarial interrogation."""

    raw_prompt: str
    critiques: Tuple[CritiqueRecord, ...] = field(default_factory=tuple)
    hardened_invariants: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalizes mutable collections to immutable tuples."""
        if isinstance(self.critiques, list):
            object.__setattr__(self, "critiques", tuple(self.critiques))
        if isinstance(self.hardened_invariants, list):
            object.__setattr__(self, "hardened_invariants", tuple(self.hardened_invariants))

    def to_dict(self) -> Dict[str, Any]:
        """Serializes result into dictionary representation."""
        return {
            "raw_prompt": self.raw_prompt,
            "critiques": [
                {
                    "perspective": c.perspective.value if hasattr(c.perspective, "value") else str(c.perspective),
                    "concern": c.concern,
                    "failure_mode": c.failure_mode,
                    "proposed_invariant": c.proposed_invariant,
                    "severity": c.severity,
                }
                for c in self.critiques
            ],
            "hardened_invariants": list(self.hardened_invariants),
            "metadata": dict(self.metadata),
        }


# ==============================================================================
# 2. Perspective Evaluators & Red-Team Deconstructors
# ==============================================================================

_ARCH_BLOAT_KEYWORDS = (
    "generic",
    "framework",
    "abstract",
    "wrapper",
    "dynamic",
    "meta",
    "hierarchy",
    "polymorphic",
    "plugin",
    "factory",
)

_CONCURRENCY_KEYWORDS = (
    "concurrent",
    "thread",
    "async",
    "lock",
    "mutex",
    "queue",
    "parallel",
    "race",
)

_IO_KEYWORDS = (
    "network",
    "http",
    "socket",
    "db",
    "database",
    "query",
    "sql",
    "file",
    "io",
    "subprocess",
)

_BACKGROUND_KEYWORDS = (
    "background",
    "daemon",
    "worker",
    "batch",
    "cron",
    "stream",
    "pipeline",
    "service",
    "task",
)


def _evaluate_architecture_perspective(prompt_lower: str) -> List[CritiqueRecord]:
    """Evaluates prompt against architecture KISS and anti-bloat principles."""
    has_bloat = any(kw in prompt_lower for kw in _ARCH_BLOAT_KEYWORDS)
    if has_bloat:
        return [
            CritiqueRecord(
                perspective=PerspectiveType.ARCHITECTURE,
                concern="High abstraction density and risk of speculative wrapper hierarchies violating KISS/YAGNI.",
                failure_mode="Premature generalization causing cognitive overhead, indirection, and leaky boundaries.",
                proposed_invariant=(
                    "The implementation SHALL prohibit speculative abstractions, "
                    "generic meta-programming, and single-use wrapper layers (KISS/YAGNI)."
                ),
                severity="HIGH",
            )
        ]
    return [
        CritiqueRecord(
            perspective=PerspectiveType.ARCHITECTURE,
            concern="Risk of unconstrained abstraction density and premature generalization.",
            failure_mode="Unnecessary intermediate interfaces and coupling without proven multi-consumer need.",
            proposed_invariant=(
                "The implementation SHALL implement minimal viable architecture "
                "with cyclomatic complexity <= 10 and max 7 parameters per function."
            ),
            severity="MEDIUM",
        )
    ]


def _build_cortex_resilience_critiques(cortex_records: Sequence[Any]) -> List[CritiqueRecord]:
    """Translates historical cortex failure events into resilience critiques."""
    critiques: List[CritiqueRecord] = []
    for rec in cortex_records[:2]:
        event_id = getattr(rec, "id", "EVT-HISTORICAL")
        comp = getattr(rec, "component", "subsystem")
        directive = getattr(rec, "directive", "Enforce defensive failure containment")
        root_cause = getattr(rec, "root_cause", None) or "Recurrence of historical defect under edge conditions"
        critiques.append(CritiqueRecord(
            perspective=PerspectiveType.RESILIENCE,
            concern=f"Historical failure pattern identified in {comp} [{event_id}].",
            failure_mode=str(root_cause),
            proposed_invariant=f"The system SHALL enforce historical defense [{event_id}]: {directive}.",
            severity="HIGH",
        ))
    return critiques


def _evaluate_resilience_perspective(
    prompt_lower: str,
    cortex_records: Sequence[Any],
) -> List[CritiqueRecord]:
    """Evaluates prompt against fault-tolerance and error containment principles."""
    critiques: List[CritiqueRecord] = []
    has_concurrency = any(kw in prompt_lower for kw in _CONCURRENCY_KEYWORDS)
    has_io = any(kw in prompt_lower for kw in _IO_KEYWORDS)

    if has_concurrency:
        critiques.append(CritiqueRecord(
            perspective=PerspectiveType.RESILIENCE,
            concern="Concurrency and synchronization hazards without bounded wait times.",
            failure_mode="Deadlock or thread starvation under contention due to unbounded lock acquisition.",
            proposed_invariant=(
                "The system SHALL bound all lock acquisitions and synchronization "
                "primitives with explicit timeouts."
            ),
            severity="HIGH",
        ))

    if has_io:
        critiques.append(CritiqueRecord(
            perspective=PerspectiveType.RESILIENCE,
            concern="Unbounded external I/O and resource starvation without timeout budgets.",
            failure_mode="Resource exhaustion and process hangs during downstream failure or connection drops.",
            proposed_invariant=(
                "The system SHALL enforce explicit timeouts and deterministic context-managed "
                "resource cleanup on all I/O operations."
            ),
            severity="HIGH",
        ))

    if not has_concurrency and not has_io:
        critiques.append(CritiqueRecord(
            perspective=PerspectiveType.RESILIENCE,
            concern="Absence of explicit exception boundaries and fail-safe default containment.",
            failure_mode="Unhandled exceptions crossing module boundaries causing cascade process termination.",
            proposed_invariant=(
                "The system SHALL establish isolated exception boundaries with typed error "
                "handling and fail-open fallbacks."
            ),
            severity="MEDIUM",
        ))

    critiques.extend(_build_cortex_resilience_critiques(cortex_records))
    return critiques


def _evaluate_operations_perspective(prompt_lower: str) -> List[CritiqueRecord]:
    """Evaluates prompt against observability, telemetry, and diagnostics principles."""
    has_bg = any(kw in prompt_lower for kw in _BACKGROUND_KEYWORDS)
    if has_bg:
        return [
            CritiqueRecord(
                perspective=PerspectiveType.OPERATIONS,
                concern="Background execution lacks health check probes and runtime telemetry.",
                failure_mode="Silent worker failure or unobserved crash without operational alerting.",
                proposed_invariant=(
                    "The system SHALL provide operational health probes and heartbeat "
                    "telemetry for background execution."
                ),
                severity="HIGH",
            )
        ]
    return [
        CritiqueRecord(
            perspective=PerspectiveType.OPERATIONS,
            concern="Deficiency in runtime observability, structured diagnostics, and on-call visibility.",
            failure_mode="Inability to diagnose production faults due to missing structured diagnostics.",
            proposed_invariant=(
                "The system SHALL emit structured diagnostics and expose inspection "
                "hooks for runtime telemetry."
            ),
            severity="MEDIUM",
        )
    ]


def _query_cortex_lessons(
    query_text: str,
    db_path: Optional[Path] = None,
) -> List[Any]:
    """Retrieves historical failure events from cortex database with fail-open fallback."""
    if not query_text or not query_text.strip():
        return []
    try:
        clean_tokens = re.findall(r"[a-zA-Z]{3,}", query_text.lower())
        stop_words = {"the", "and", "for", "with", "this", "that", "from", "into", "all", "are", "have"}
        filtered = [t for t in clean_tokens if t not in stop_words][:6]
        if not filtered:
            return []
        fts_query = " ".join(filtered)
        from core.cortex_knowledge import query_events
        return query_events(
            query_str=fts_query,
            outcome="FAILURE",
            limit=3,
            db_path=db_path,
        )
    except Exception:
        return []


def _synthesize_hardened_invariants(critiques: Sequence[CritiqueRecord]) -> Tuple[str, ...]:
    """Synthesizes unique hardened SHALL invariants from dialectical critiques."""
    invariants: List[str] = []
    seen: set = set()
    for c in critiques:
        inv = c.proposed_invariant.strip()
        if inv and inv not in seen:
            seen.add(inv)
            invariants.append(inv)
    return tuple(invariants)


def _build_empty_fallback(raw_prompt: str) -> DialecticalResult:
    """Builds safe default DialecticalResult for empty or whitespace prompts."""
    return DialecticalResult(
        raw_prompt=raw_prompt,
        critiques=(),
        hardened_invariants=(),
        metadata={"status": "EMPTY_PROMPT_FALLBACK", "critique_count": 0},
    )


# ==============================================================================
# 3. Primary Evaluation API
# ==============================================================================

def evaluate_perspectives(
    raw_prompt: str,
    domain_context: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> DialecticalResult:
    """
    Evaluates raw prompt across Architecture, Resilience, and Operations perspectives.
    Executes adversarial red-team deconstruction to identify concrete failure vulnerabilities
    and synthesize hardened invariants. Employs fail-open error containment on errors.
    """
    if not raw_prompt or not isinstance(raw_prompt, str) or not raw_prompt.strip():
        return _build_empty_fallback(raw_prompt if isinstance(raw_prompt, str) else "")

    clean_prompt = raw_prompt.strip()
    prompt_lower = clean_prompt.lower()
    if domain_context:
        prompt_lower = f"{prompt_lower} {domain_context.lower()}"

    cortex_records = _query_cortex_lessons(clean_prompt, db_path)

    critiques: List[CritiqueRecord] = []
    critiques.extend(_evaluate_architecture_perspective(prompt_lower))
    critiques.extend(_evaluate_resilience_perspective(prompt_lower, cortex_records))
    critiques.extend(_evaluate_operations_perspective(prompt_lower))

    hardened_invariants = _synthesize_hardened_invariants(critiques)
    metadata: Dict[str, Any] = {
        "perspectives_evaluated": [p.value for p in PerspectiveType],
        "critique_count": len(critiques),
        "hardened_invariant_count": len(hardened_invariants),
        "domain_context": domain_context or "general",
        "cortex_events_queried": len(cortex_records),
    }

    return DialecticalResult(
        raw_prompt=clean_prompt,
        critiques=tuple(critiques),
        hardened_invariants=hardened_invariants,
        metadata=metadata,
    )


# ==============================================================================
# 4. Requirements Integration Bridge
# ==============================================================================

def _build_empty_spec_fallback() -> RequirementsSpec:
    """Returns fallback RequirementsSpec for empty or invalid prompts."""
    return RequirementsSpec(
        core_intent="Unspecified intent.",
        functional_requirements=[
            "[REQ-01] The system SHALL execute the baseline requirements specification."
        ],
        auto_immunized_nfrs=[],
        non_goals=["Avoid breaking changes."],
        source_prompt_hash="",
    )


def _safe_extract_requirements(
    raw_prompt: str,
    domain_context: Optional[str],
    db_path: Optional[Path],
) -> RequirementsSpec:
    """Invokes core.requirements_extractor.extract_requirements with fail-open fallback."""
    try:
        return extract_requirements(
            raw_prompt=raw_prompt,
            domain_context=domain_context,
            db_path=db_path,
        )
    except Exception as err:
        sys.stderr.write(f"Requirements extraction fallback triggered: {err}\n")
        return RequirementsSpec(
            core_intent=raw_prompt.strip()[:120],
            functional_requirements=[
                f"[REQ-01] The system SHALL execute: {raw_prompt.strip()[:100]}."
            ],
            auto_immunized_nfrs=[],
            non_goals=["Avoid breaking changes."],
            source_prompt_hash="",
        )


def _synthesize_failure_nfrs(critiques: Sequence[CritiqueRecord]) -> List[str]:
    """Synthesizes auto-immunized NFR strings from red-team critique failure modes."""
    nfrs: List[str] = []
    seen: set = set()
    for c in critiques:
        mode = c.failure_mode.strip()
        if not mode or mode in seen:
            continue
        seen.add(mode)
        event_id = f"DIA-{c.perspective.value[:4]}"
        comp = c.perspective.value.lower()
        directive = f"SHALL prevent failure mode: {mode}"
        try:
            nfr_obj = AutoImmunizedNFR(event_id=event_id, directive=directive, component=comp)
            nfrs.append(str(nfr_obj))
        except Exception:
            nfrs.append(f"[{event_id}] ({comp}): {directive}")
    return nfrs


def integrate_dialectical_requirements(
    raw_prompt: str,
    domain_context: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Any:
    """
    Decomposes raw prompt and enriches RequirementsSpec with dialectically hardened
    functional requirements and auto-immunized NFRs synthesized from red-team interrogation.
    """
    if not raw_prompt or not isinstance(raw_prompt, str) or not raw_prompt.strip():
        return _build_empty_spec_fallback()

    base_spec = _safe_extract_requirements(raw_prompt, domain_context, db_path)
    dialectic_result = evaluate_perspectives(
        raw_prompt=raw_prompt,
        domain_context=domain_context,
        db_path=db_path,
    )

    enriched_reqs = list(base_spec.functional_requirements) + list(dialectic_result.hardened_invariants)
    synthesized_nfrs = _synthesize_failure_nfrs(dialectic_result.critiques)
    enriched_nfrs = list(base_spec.auto_immunized_nfrs) + synthesized_nfrs

    return RequirementsSpec(
        core_intent=base_spec.core_intent,
        functional_requirements=enriched_reqs,
        auto_immunized_nfrs=enriched_nfrs,
        non_goals=list(base_spec.non_goals),
        source_prompt_hash=base_spec.source_prompt_hash,
    )


# ==============================================================================
# 5. CLI Formatting & Entrypoint
# ==============================================================================

def format_dialectical_summary(result: DialecticalResult) -> str:
    """Formats DialecticalResult into readable markdown summary."""
    lines: List[str] = [
        "# Dialectical Requirements Interrogation Summary",
        "",
        f"Prompt: {result.raw_prompt.strip() if result.raw_prompt else 'Empty prompt'}",
        "",
        "## 1. Dialectical Critiques & Vulnerabilities",
    ]
    if result.critiques:
        for c in result.critiques:
            lines.append(f"- [{c.perspective.value}] ({c.severity}) Concern: {c.concern}")
            lines.append(f"  Failure Mode: {c.failure_mode}")
            lines.append(f"  Proposed Invariant: {c.proposed_invariant}")
    else:
        lines.append("- No critiques identified.")

    lines.extend([
        "",
        "## 2. Synthesized Hardened Invariants",
    ])
    if result.hardened_invariants:
        for inv in result.hardened_invariants:
            lines.append(f"- {inv}")
    else:
        lines.append("- No hardened invariants synthesized.")

    return "\n".join(lines)


def _build_cli_parser() -> argparse.ArgumentParser:
    """Constructs command line argument parser for dialectical interrogation."""
    parser = argparse.ArgumentParser(
        prog="core.dialectical_extractor",
        description="Dialectical Requirements Interrogator & Adversarial Red Team Engine",
    )
    parser.add_argument("--prompt", type=str, required=True, help="Raw user prompt text")
    parser.add_argument("--domain", type=str, default=None, help="Optional domain context identifier")
    parser.add_argument("--db", "--db-path", dest="db", type=str, default=None, help="Custom path to cortex.db")
    parser.add_argument("--json", action="store_true", help="Output specification in JSON format")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI execution entrypoint."""
    parser = _build_cli_parser()
    parsed = parser.parse_args(argv)

    db_path = Path(parsed.db) if parsed.db else None
    result = evaluate_perspectives(
        raw_prompt=parsed.prompt,
        domain_context=parsed.domain,
        db_path=db_path,
    )

    if parsed.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(format_dialectical_summary(result) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
