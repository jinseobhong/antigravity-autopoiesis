"""
Mechanical interface protocol definitions and frozen data models for evolutionary recombination engine.

Conforms to docs/active/ACTIVE_CONTRACT.md (TASK-030).
Declares EvolutionConfig, MutantCandidate, GenerationReport, EvolutionOutcome frozen dataclasses
and FitnessEvaluatorProtocol, EvolutionaryEngineProtocol conforming to AST Anti-Cheat invariant H-CODE-1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Tuple


@dataclass(frozen=True)
class EvolutionConfig:
    """Immutable configuration parameters for genetic algorithm evolution loop."""

    population_size: int = 20
    generations: int = 10
    mutation_rate: float = 0.1
    crossover_rate: float = 0.8
    tournament_size: int = 3
    lethality_ceiling_ms: float = 5.0
    watchdog_timeout_sec: float = 3.0
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        """Validates configuration bounds to enforce fail-fast determinism."""
        if self.population_size <= 0:
            raise ValueError(f"population_size must be positive, got {self.population_size}")
        if self.generations <= 0:
            raise ValueError(f"generations must be positive, got {self.generations}")
        if not (0.0 <= self.mutation_rate <= 1.0):
            raise ValueError(f"mutation_rate must be in [0.0, 1.0], got {self.mutation_rate}")
        if not (0.0 <= self.crossover_rate <= 1.0):
            raise ValueError(f"crossover_rate must be in [0.0, 1.0], got {self.crossover_rate}")
        if self.tournament_size <= 0:
            raise ValueError(f"tournament_size must be positive, got {self.tournament_size}")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration parameters to dictionary."""
        return {
            "population_size": self.population_size,
            "generations": self.generations,
            "mutation_rate": self.mutation_rate,
            "crossover_rate": self.crossover_rate,
            "tournament_size": self.tournament_size,
            "lethality_ceiling_ms": self.lethality_ceiling_ms,
            "watchdog_timeout_sec": self.watchdog_timeout_sec,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class MutantCandidate:
    """Immutable record of an individual program candidate in the population."""

    candidate_id: str
    source_code: str
    generation: int
    parent_ids: Tuple[str, ...] = ()
    fitness_score: float = 0.0
    is_lethal: bool = False
    mutation_type: str = "seed"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize candidate record to dictionary."""
        return {
            "candidate_id": self.candidate_id,
            "source_code": self.source_code,
            "generation": self.generation,
            "parent_ids": list(self.parent_ids),
            "fitness_score": self.fitness_score,
            "is_lethal": self.is_lethal,
            "mutation_type": self.mutation_type,
        }


@dataclass(frozen=True)
class GenerationReport:
    """Immutable telemetry report summarizing population fitness metrics per generation."""

    generation_number: int
    best_fitness: float
    average_fitness: float
    lethal_count: int
    survivor_count: int
    elapsed_sec: float

    def to_dict(self) -> Dict[str, Any]:
        """Serialize generation report to dictionary."""
        return {
            "generation_number": self.generation_number,
            "best_fitness": round(self.best_fitness, 6),
            "average_fitness": round(self.average_fitness, 6),
            "lethal_count": self.lethal_count,
            "survivor_count": self.survivor_count,
            "elapsed_sec": round(self.elapsed_sec, 6),
        }


@dataclass(frozen=True)
class EvolutionOutcome:
    """Immutable terminal result of complete evolutionary optimization run."""

    success: bool
    best_candidate: MutantCandidate
    generation_reports: Tuple[GenerationReport, ...] = ()
    total_generations: int = 0
    total_candidates_evaluated: int = 0
    termination_reason: str = "max_generations"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize complete evolutionary outcome to dictionary."""
        return {
            "success": self.success,
            "best_candidate": self.best_candidate.to_dict(),
            "generation_reports": [r.to_dict() for r in self.generation_reports],
            "total_generations": self.total_generations,
            "total_candidates_evaluated": self.total_candidates_evaluated,
            "termination_reason": self.termination_reason,
        }


class FitnessEvaluatorProtocol(Protocol):
    """Protocol defining candidate code evaluation."""

    def evaluate(self, candidate_code: str) -> float:
        """Evaluate candidate code string and return numerical fitness score."""
        raise NotImplementedError("Protocol method must be implemented by concrete evaluator.")


class EvolutionaryEngineProtocol(Protocol):
    """Protocol defining genetic recombination and mutation operations."""

    def crossover(self, parent_a_code: str, parent_b_code: str) -> Tuple[str, str]:
        """Perform homologous AST crossover between two parent code representations."""
        raise NotImplementedError("Protocol method must be implemented by concrete engine.")

    def mutate(self, candidate_code: str) -> str:
        """Perform body-confined AST mutation on target candidate source code."""
        raise NotImplementedError("Protocol method must be implemented by concrete engine.")

    def evolve(
        self,
        seed_code: str,
        evaluator: FitnessEvaluatorProtocol,
        config: EvolutionConfig,
    ) -> EvolutionOutcome:
        """Execute complete genetic evolution loop starting from seed implementation."""
        raise NotImplementedError("Protocol method must be implemented by concrete engine.")
