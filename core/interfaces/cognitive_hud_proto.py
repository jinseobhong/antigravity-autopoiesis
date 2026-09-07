"""Interface protocol and data models for the 4-Layer Cognitive HUD.

Defines the formal contracts for L0 Sovereign Cockpit, L1 Tension Radar,
L2 Mutation Cards, and L3 Genotype Deep Trace telemetry extraction and HTML generation.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Protocol, Tuple


@dataclass(frozen=True)
class HudLayerL0:
    """L0: Sovereign Cockpit telemetry (3-Second Scan)."""

    viability_beacon: str  # NOMINAL, DEGRADED, ALERT
    active_task_count: int
    max_active_tasks: int
    working_tree_clean: bool
    stop_hook_ready: bool
    last_commit_sha: str
    last_commit_message: str


@dataclass(frozen=True)
class HudLayerL1:
    """L1: Tension Radar telemetry (15-Second Scan)."""

    simplicity_vs_extensibility: float
    latency_vs_memory: float
    mutation_rate_vs_stability: float
    cognitive_burden_score: int  # 1 (Zero cognitive friction) to 10 (Mental exhaustion)
    friction_summary: str


@dataclass(frozen=True)
class MutationQuadrantCard:
    """4-Quadrant Mutation Card representation for candidate/promoted phenotype."""

    task_id: str
    q1_phenotypic_leap: str
    q2_empirical_fitness: str
    q3_ergonomic_tension: str
    q4_rollback_command: str


@dataclass(frozen=True)
class HudLayerL2:
    """L2: Mutation Card telemetry (30-Second Scan)."""

    mutation_cards: Tuple[MutationQuadrantCard, ...]
    recent_promoted_count: int


@dataclass(frozen=True)
class HudLayerL3:
    """L3: Genotype Deep Trace telemetry (On-Demand)."""

    git_diff_summary: str
    test_suite_status: str
    total_tests_passed: int
    ast_compliance_defects: int
    ast_docking_defects: int


@dataclass(frozen=True)
class CognitiveHudSnapshot:
    """Aggregated immutable snapshot across all 4 cognitive layers."""

    timestamp: str
    repo_root: str
    l0: HudLayerL0
    l1: HudLayerL1
    l2: HudLayerL2
    l3: HudLayerL3

    def to_dict(self) -> Dict[str, Any]:
        """Serialize snapshot to primitive dictionary."""
        return asdict(self)


class CognitiveHudExtractorProtocol(Protocol):
    """Protocol for extracting cognitive HUD telemetry and rendering Generative UI HTML."""

    def extract_snapshot(self, repo_root: Path) -> CognitiveHudSnapshot:
        """Extract a multi-layer telemetry snapshot from the target repository.

        Args:
            repo_root: Absolute path to the repository root.

        Returns:
            Immutable CognitiveHudSnapshot object.
        """
        raise NotImplementedError("Protocol method")

    def render_html(self, snapshot: CognitiveHudSnapshot) -> str:
        """Render self-contained Generative UI HTML widget adhering to Antigravity design tokens.

        Args:
            snapshot: Extracted CognitiveHudSnapshot.

        Returns:
            HTML source string.
        """
        raise NotImplementedError("Protocol method")
