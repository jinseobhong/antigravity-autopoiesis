"""
Requirements Extractor and Prompt Decomposition Engine (core.requirements_extractor).

Decomposes raw natural language prompts into typed, frozen RequirementsSpec
instances comprising CoreIntent, FunctionalRequirements (SHALL statements),
AutoImmunizedNFRs (extracted from historical cortex failures via FTS5),
and explicit NonGoals.
Conforms to:
- AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12
- [INV-REQ-01] through [INV-REQ-03]
- NASA SP-2016-6105 Rev 2 Normative Standards
"""

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence


# ==============================================================================
# 1. Typed Value Objects & Data Models
# ==============================================================================

@dataclass(frozen=True)
class CoreIntent:
    """Primary architectural objective identified from user prompt."""

    intent: str
    target_scope: str = "general"

    def __post_init__(self) -> None:
        """Enforces non-empty string invariant on intent."""
        if not self.intent or not self.intent.strip():
            raise ValueError("CoreIntent.intent must be a non-empty string.")


@dataclass(frozen=True)
class FunctionalRequirement:
    """Discrete testable assertion requirement."""

    req_id: str
    statement: str

    def __post_init__(self) -> None:
        """Enforces non-empty string invariant on requirement attributes."""
        if not self.req_id or not self.req_id.strip():
            raise ValueError("FunctionalRequirement.req_id must be non-empty.")
        if not self.statement or not self.statement.strip():
            raise ValueError("FunctionalRequirement.statement must be non-empty.")

    def __str__(self) -> str:
        """Formats requirement as readable string."""
        return f"[{self.req_id}] {self.statement}"


@dataclass(frozen=True)
class AutoImmunizedNFR:
    """Negative constraint preventing recurring failure synthesized from historical trace."""

    event_id: str
    directive: str
    component: str = "general"

    def __post_init__(self) -> None:
        """Enforces non-empty string invariant on event_id and directive."""
        if not self.event_id or not self.event_id.strip():
            raise ValueError("AutoImmunizedNFR.event_id must be non-empty.")
        if not self.directive or not self.directive.strip():
            raise ValueError("AutoImmunizedNFR.directive must be non-empty.")

    def __str__(self) -> str:
        """Formats NFR as readable string referencing originating event."""
        return f"[{self.event_id}] ({self.component}): {self.directive}"


@dataclass(frozen=True)
class NonGoal:
    """Explicit out-of-scope boundary constraining implementation scope."""

    statement: str

    def __post_init__(self) -> None:
        """Enforces non-empty string invariant on non-goal statement."""
        if not self.statement or not self.statement.strip():
            raise ValueError("NonGoal.statement must be non-empty.")

    def __str__(self) -> str:
        """Formats non-goal as readable string."""
        return self.statement


@dataclass(frozen=True)
class RequirementsSpec:
    """Immutable specification decomposed from raw user prompt."""

    core_intent: str
    functional_requirements: List[str] = field(default_factory=list)
    auto_immunized_nfrs: List[str] = field(default_factory=list)
    non_goals: List[str] = field(default_factory=list)
    source_prompt_hash: str = ""

    def to_markdown(self) -> str:
        """Serializes requirements specification to formatted markdown."""
        return format_spec_markdown(self)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes requirements specification to dictionary."""
        return {
            "core_intent": self.core_intent,
            "functional_requirements": list(self.functional_requirements),
            "auto_immunized_nfrs": list(self.auto_immunized_nfrs),
            "non_goals": list(self.non_goals),
            "source_prompt_hash": self.source_prompt_hash,
        }


# ==============================================================================
# 2. Markdown Formatter
# ==============================================================================

def format_spec_markdown(spec: RequirementsSpec) -> str:
    """Formats a RequirementsSpec instance into clean GitHub-flavored markdown."""
    lines: List[str] = [
        "# Requirements Specification",
        "",
        "## 1. Core Intent",
        spec.core_intent.strip() if spec.core_intent.strip() else "Unspecified intent.",
        "",
        "## 2. Functional Requirements",
    ]

    if spec.functional_requirements:
        for item in spec.functional_requirements:
            clean_item = str(item).strip()
            lines.append(f"- {clean_item}")
    else:
        lines.append("- The system SHALL execute the baseline requirements specification.")

    lines.extend([
        "",
        "## 3. Auto-Immunized Non-Functional Requirements (NFRs)",
    ])

    if spec.auto_immunized_nfrs:
        for item in spec.auto_immunized_nfrs:
            clean_item = str(item).strip()
            lines.append(f"- {clean_item}")
    else:
        lines.append("- No historical failure immunizations required.")

    lines.extend([
        "",
        "## 4. Non-Goals",
    ])

    if spec.non_goals:
        for item in spec.non_goals:
            clean_item = str(item).strip()
            lines.append(f"- {clean_item}")
    else:
        lines.append("- Out-of-scope tasks are governed by general repository boundary policies.")

    if spec.source_prompt_hash:
        lines.extend([
            "",
            "---",
            f"*Source Prompt Hash: `{spec.source_prompt_hash}`*",
        ])

    return "\n".join(lines)


# ==============================================================================
# 3. Prompt Decomposition & Synthesis Helpers
# ==============================================================================

def _extract_intent_summary(prompt_text: str) -> str:
    """Extracts high-level architectural objective from raw prompt."""
    lines = [line.strip() for line in prompt_text.splitlines() if line.strip()]
    if not lines:
        return "Execute requested task specification."

    first_line = lines[0]
    first_line = re.sub(r"^[#\s\*\-]+", "", first_line).strip()
    first_line = re.sub(r"^(implement|create|build|refactor|design)\s+", "", first_line, flags=re.IGNORECASE)
    cleaned = first_line.rstrip(".")
    if cleaned:
        return f"Implement {cleaned}"
    return "Execute requested architectural implementation."


def _parse_candidate_statements(lines: Sequence[str]) -> List[str]:
    """Identifies discrete task lines from numbered, bulleted, or imperative statements."""
    candidates: List[str] = []
    bullet_pattern = re.compile(r"^(\d+[\.\)]|\-|\*)\s+(.+)")

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = bullet_pattern.match(line)
        if match:
            item_text = match.group(2).strip()
            if len(item_text) > 3:
                candidates.append(item_text)
            continue

        if any(verb in line.lower() for verb in ("shall", "must", "implement", "create", "support", "ensure")):
            candidates.append(line)

    return candidates


def _format_shall_statement(index: int, statement: str) -> str:
    """Formats a raw statement into a normalized testable SHALL requirement."""
    clean_text = statement.strip().rstrip(".")
    req_id = f"REQ-{index:02d}"

    if re.match(r"^\[(INV|REQ)-", clean_text):
        return clean_text

    if "shall" in clean_text.lower():
        return f"[{req_id}] {clean_text}."

    action_verbs = ("implement", "create", "support", "provide", "enforce", "validate", "ensure", "parse")
    lower = clean_text.lower()
    for verb in action_verbs:
        if lower.startswith(verb):
            tail = clean_text[len(verb):].strip()
            return f"[{req_id}] The system SHALL {verb} {tail}."

    return f"[{req_id}] The system SHALL {clean_text}."


def _extract_functional_requirements(prompt_text: str) -> List[str]:
    """Decomposes prompt into discrete testable functional requirements."""
    lines = prompt_text.splitlines()
    candidates = _parse_candidate_statements(lines)

    if not candidates:
        summary = _extract_intent_summary(prompt_text)
        return [f"[REQ-01] The system SHALL {summary}."]

    results: List[str] = []
    for idx, cand in enumerate(candidates, start=1):
        formatted = _format_shall_statement(idx, cand)
        results.append(formatted)

    return results


def _retrieve_cortex_failures(
    keywords: str,
    db_path: Optional[Path],
) -> List[Any]:
    """Safely retrieves historical failure events from cortex.db with fail-open fallback."""
    try:
        from core.cortex_knowledge import query_events
        return query_events(
            query_str=keywords,
            outcome="FAILURE",
            limit=5,
            db_path=db_path,
        )
    except Exception:
        return []


def _synthesize_auto_immunized_nfrs(
    prompt_text: str,
    domain_context: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[str]:
    """Auto-synthesizes immunized NFRs from past failure traces and domain heuristics."""
    clean_tokens = re.findall(r"[a-zA-Z]{3,}", prompt_text.lower())
    stop_words = {"the", "and", "for", "with", "this", "that", "from", "into", "all", "are", "have"}
    filtered = [t for t in clean_tokens if t not in stop_words][:8]
    if domain_context:
        filtered.append(domain_context.lower())

    query_str = " ".join(filtered)
    records = _retrieve_cortex_failures(query_str, db_path)

    nfrs: List[str] = []
    for rec in records:
        event_id = getattr(rec, "id", "EVT-UNKNOWN")
        comp = getattr(rec, "component", "general")
        directive = getattr(rec, "directive", "Adhere to architectural boundary")
        nfr_obj = AutoImmunizedNFR(
            event_id=event_id,
            directive=f"SHALL prevent recurring failure: {directive}",
            component=comp,
        )
        nfrs.append(str(nfr_obj))

    return nfrs


def _formulate_non_goals(prompt_text: str) -> List[str]:
    """Formulates explicit non-goals to tightly constrain implementation scope."""
    non_goals: List[str] = [
        "Speculative abstractions, generic meta-programming, or single-use wrapper layers are strictly prohibited.",
        "Unbounded I/O operations without explicit timeout enforcement are prohibited.",
        "Direct unverified production root mutation outside sandbox isolation is prohibited.",
    ]

    negative_triggers = ("do not", "never", "without", "exclude", "avoid", "prohibit")
    for line in prompt_text.splitlines():
        line_clean = line.strip()
        lower = line_clean.lower()
        if any(trig in lower for trig in negative_triggers):
            sanitized = re.sub(r"^[\*\-\d\.\)]+\s*", "", line_clean)
            non_goals.append(f"Explicit out-of-scope constraint: {sanitized}")

    return non_goals


# ==============================================================================
# 4. Primary Extraction Functional API
# ==============================================================================

def extract_requirements(
    raw_prompt: Optional[str] = None,
    domain_context: Optional[str] = None,
    db_path: Optional[Path] = None,
    **kwargs: Any,
) -> RequirementsSpec:
    """
    Decomposes raw user prompt into typed, frozen RequirementsSpec.

    Extracts CoreIntent, itemizes FunctionalRequirements as discrete SHALL statements,
    queries cortex.db via FTS5 for past failure directives to auto-inject AutoImmunizedNFRs,
    and formulates explicit NonGoals to bound scope.
    Fails open with safe defaults upon database or parsing failures.
    """
    if raw_prompt is None and "prompt" not in kwargs:
        raise ValueError("Prompt must be a non-empty string, got None.")

    effective_prompt = raw_prompt if raw_prompt is not None else kwargs.get("prompt", "")
    if not isinstance(effective_prompt, str):
        raise TypeError(f"Prompt must be a string, got {type(effective_prompt).__name__}.")

    clean_prompt = effective_prompt.strip()
    if not clean_prompt:
        raise ValueError("Prompt must be a non-empty string.")

    prompt_hash = hashlib.sha256(clean_prompt.encode("utf-8")).hexdigest()

    try:
        intent = _extract_intent_summary(clean_prompt)
        functional_reqs = _extract_functional_requirements(clean_prompt)
        auto_nfrs = _synthesize_auto_immunized_nfrs(clean_prompt, domain_context, db_path)
        non_goals = _formulate_non_goals(clean_prompt)

        return RequirementsSpec(
            core_intent=intent,
            functional_requirements=functional_reqs,
            auto_immunized_nfrs=auto_nfrs,
            non_goals=non_goals,
            source_prompt_hash=prompt_hash,
        )
    except Exception as err:
        sys.stderr.write(f"Requirements extraction fallback triggered: {err}\n")
        return RequirementsSpec(
            core_intent=clean_prompt[:120],
            functional_requirements=[f"[REQ-01] The system SHALL execute: {clean_prompt[:100]}."],
            auto_immunized_nfrs=[],
            non_goals=["Avoid breaking changes."],
            source_prompt_hash=prompt_hash,
        )


# ==============================================================================
# 5. CLI Entrypoint
# ==============================================================================

def _build_cli_parser() -> argparse.ArgumentParser:
    """Constructs command line argument parser for requirements extraction."""
    parser = argparse.ArgumentParser(
        prog="core.requirements_extractor",
        description="Extracts typed requirements specification with FTS5 failure auto-immunization",
    )
    parser.add_argument("--prompt", type=str, required=True, help="Raw user prompt text")
    parser.add_argument("--domain", type=str, default=None, help="Optional domain context identifier")
    parser.add_argument("--db", "--db-path", dest="db", type=str, default=None, help="Custom path to cortex.db")
    parser.add_argument("--json", action="store_true", help="Output specification in JSON format")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI execution entrypoint."""
    parser = _build_cli_parser()
    parsed = parser.parse_args(argv)

    db_path = Path(parsed.db) if parsed.db else None
    spec = extract_requirements(
        raw_prompt=parsed.prompt,
        domain_context=parsed.domain,
        db_path=db_path,
    )

    if parsed.json:
        sys.stdout.write(json.dumps(spec.to_dict(), indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(format_spec_markdown(spec) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
