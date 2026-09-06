"""
AI-Native Evolutionary Recombination Engine (core.evolutionary_engine).

Provides grammar-aware genetic algorithm operators (homologous crossover, body-confined mutation,
tournament selection) operating directly on Python Abstract Syntax Trees (AST).
Conforms to docs/active/ACTIVE_CONTRACT.md (TASK-030).
"""

from __future__ import annotations

import argparse
import ast
import copy
from dataclasses import dataclass
import json
from pathlib import Path
import random
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:
    from core.interfaces.evolutionary_engine_proto import (
        EvolutionConfig,
        EvolutionOutcome,
        EvolutionaryEngineProtocol,
        FitnessEvaluatorProtocol,
        GenerationReport,
        MutantCandidate,
    )
except ModuleNotFoundError:
    from sandbox.core.interfaces.evolutionary_engine_proto import (
        EvolutionConfig,
        EvolutionOutcome,
        EvolutionaryEngineProtocol,
        FitnessEvaluatorProtocol,
        GenerationReport,
        MutantCandidate,
    )

try:
    from core.ast_docking_checker import (
        _extract_impl_classes,
        _extract_protocols,
        _read_ast_tree,
        _select_candidate_class,
        _verify_single_protocol,
        verify_ast_docking,
    )
except ModuleNotFoundError:
    from sandbox.core.ast_docking_checker import (
        _extract_impl_classes,
        _extract_protocols,
        _read_ast_tree,
        _select_candidate_class,
        _verify_single_protocol,
        verify_ast_docking,
    )


# ==============================================================================
# 1. AST Homologous Splicing Locations and Helpers (INV-EVO-03, INV-EVO-04)
# ==============================================================================

@dataclass(frozen=True)
class StatementSite:
    """Location record of a statement within an AST block."""

    block: List[ast.stmt]
    index: int
    stmt: ast.stmt


@dataclass(frozen=True)
class ExpressionSite:
    """Location record of an expression within an AST node."""

    parent: ast.AST
    attr_name: str
    list_index: Optional[int]
    expr: ast.expr


def _is_protocol_class(node: ast.ClassDef) -> bool:
    """Determines whether ClassDef node represents typing.Protocol."""
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Protocol":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Protocol":
            return True
    return False


class MutableFunctionCollector(ast.NodeVisitor):
    """AST visitor collecting function definitions strictly outside Protocol classes."""

    def __init__(self) -> None:
        self.functions: List[ast.FunctionDef | ast.AsyncFunctionDef] = []
        self._in_protocol = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        was_protocol = self._in_protocol
        if _is_protocol_class(node):
            self._in_protocol = True
        self.generic_visit(node)
        self._in_protocol = was_protocol

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self._in_protocol:
            self.functions.append(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not self._in_protocol:
            self.functions.append(node)
        self.generic_visit(node)


def _collect_mutable_functions(tree: ast.AST) -> List[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Extracts all function and method AST nodes excluding Protocol classes."""
    collector = MutableFunctionCollector()
    collector.visit(tree)
    return collector.functions


def _is_docstring(stmt: ast.stmt) -> bool:
    """Checks whether given statement is a docstring constant."""
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        return isinstance(stmt.value.value, str)
    return False


def _collect_statement_sites_from_block(
    block: List[ast.stmt],
    sites: List[StatementSite],
) -> None:
    """Recursively collects statement sites from a statement list."""
    start_idx = 1 if (block and _is_docstring(block[0])) else 0
    for idx in range(start_idx, len(block)):
        stmt = block[idx]
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            sites.append(StatementSite(block=block, index=idx, stmt=stmt))
        _recurse_statement_children(stmt, sites)


def _recurse_statement_children(stmt: ast.stmt, sites: List[StatementSite]) -> None:
    """Recurses into compound statement child blocks."""
    if isinstance(stmt, ast.ClassDef) and _is_protocol_class(stmt):
        return
    for attr in ("body", "orelse", "finalbody"):
        child_block = getattr(stmt, attr, None)
        if isinstance(child_block, list) and child_block:
            _collect_statement_sites_from_block(child_block, sites)


def _collect_statement_sites(tree: ast.AST) -> List[StatementSite]:
    """Collects statement sites within function bodies, or module body as fallback."""
    sites: List[StatementSite] = []
    functions = _collect_mutable_functions(tree)
    if functions:
        for func in functions:
            _collect_statement_sites_from_block(func.body, sites)
    elif isinstance(tree, ast.Module):
        _collect_statement_sites_from_block(tree.body, sites)
    return sites


def _extract_expr_sites_from_list(
    parent: ast.AST,
    field_name: str,
    items: List[Any],
    sites: List[ExpressionSite],
) -> None:
    """Extracts expression sites residing in list attributes."""
    for idx, item in enumerate(items):
        if isinstance(item, ast.expr):
            sites.append(ExpressionSite(parent, field_name, idx, item))
            _extract_expr_sites_from_node(item, sites)


def _extract_expr_sites_from_node(node: ast.AST, sites: List[ExpressionSite]) -> None:
    """Walks AST node extracting swappable child expression sites."""
    for field_name, value in ast.iter_fields(node):
        if isinstance(value, ast.expr):
            sites.append(ExpressionSite(node, field_name, None, value))
            _extract_expr_sites_from_node(value, sites)
        elif isinstance(value, list):
            _extract_expr_sites_from_list(node, field_name, value, sites)


def _collect_expression_sites(stmt_sites: List[StatementSite]) -> List[ExpressionSite]:
    """Extracts all expression sites contained within collected statement sites."""
    expr_sites: List[ExpressionSite] = []
    for s_site in stmt_sites:
        _extract_expr_sites_from_node(s_site.stmt, expr_sites)
    return expr_sites


def swap_statements(site_a: StatementSite, site_b: StatementSite) -> None:
    """Homologously swaps statement A and statement B across AST blocks."""
    copy_a = copy.deepcopy(site_a.stmt)
    copy_b = copy.deepcopy(site_b.stmt)
    site_a.block[site_a.index] = copy_b
    site_b.block[site_b.index] = copy_a


def _set_expr_at_site(site: ExpressionSite, new_expr: ast.expr) -> None:
    """Inserts an expression AST node into target parent site."""
    if site.list_index is not None:
        target_list: List[ast.expr] = getattr(site.parent, site.attr_name)
        target_list[site.list_index] = new_expr
    else:
        setattr(site.parent, site.attr_name, new_expr)


def swap_expressions(site_a: ExpressionSite, site_b: ExpressionSite) -> None:
    """Homologously swaps expression A and expression B across AST nodes."""
    copy_a = copy.deepcopy(site_a.expr)
    copy_b = copy.deepcopy(site_b.expr)
    _set_expr_at_site(site_a, copy_b)
    _set_expr_at_site(site_b, copy_a)


# ==============================================================================
# 2. Dynamic Fitness Evaluator (INV-EVO-07)
# ==============================================================================

class DefaultFitnessEvaluator(FitnessEvaluatorProtocol):
    """
    Subprocess-isolated dynamic fitness evaluator conforming to FitnessEvaluatorProtocol.

    Executes candidate code strictly out-of-process under a 3.0s watchdog ceiling (INV-EVO-07).
    """

    def __init__(
        self,
        test_harness: Optional[str] = None,
        timeout_sec: float = 3.0,
        python_executable: Optional[str] = None,
        score_extractor: Optional[Callable[[str, int], float]] = None,
    ) -> None:
        self.test_harness = test_harness
        self.timeout_sec = min(3.0, max(0.01, timeout_sec))
        self.python_executable = python_executable or sys.executable
        self.score_extractor = score_extractor

    def evaluate(self, candidate_code: str) -> float:
        """Evaluate candidate code out-of-process returning fitness score."""
        script = candidate_code
        if self.test_harness:
            script = f"{candidate_code}\n\n{self.test_harness}"

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [self.python_executable, "-"],
                input=script,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired:
            return 0.0
        except (OSError, ValueError):
            return 0.0

        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            return 0.0

        if self.score_extractor is not None:
            return self._extract_custom_score(proc.stdout, proc.returncode)

        return self._extract_default_score(proc.stdout, elapsed)

    def _extract_custom_score(self, stdout: str, returncode: int) -> float:
        """Applies user-provided custom score extraction function."""
        try:
            if self.score_extractor:
                return float(self.score_extractor(stdout, returncode))
        except (ValueError, TypeError):
            return 0.0
        return 0.0

    def _extract_default_score(self, stdout: str, elapsed: float) -> float:
        """Parses numerical fitness score from execution stdout or defaults to timing."""
        for line in stdout.splitlines():
            line_s = line.strip()
            if line_s.startswith("FITNESS:") or line_s.startswith("SCORE:"):
                try:
                    return float(line_s.split(":", 1)[1].strip())
                except ValueError:
                    return 0.0

        try:
            return float(stdout.strip())
        except ValueError:
            return max(0.1, round(1.0 / (1.0 + elapsed), 4))


class FitnessEvaluator(DefaultFitnessEvaluator):
    """Concrete alias for default fitness evaluator."""

    def evaluate(self, candidate_code: str) -> float:
        """Evaluate candidate code string returning fitness score."""
        return super().evaluate(candidate_code)


class SubprocessFitnessEvaluator(DefaultFitnessEvaluator):
    """Concrete alias for subprocess fitness evaluator."""

    def evaluate(self, candidate_code: str) -> float:
        """Evaluate candidate code string returning fitness score."""
        return super().evaluate(candidate_code)


# ==============================================================================
# 3. Evolutionary Recombination Engine (INV-EVO-01 to INV-EVO-09)
# ==============================================================================

DEFAULT_SEED_CODE = """def target_function(x: int, y: int) -> int:
    \"\"\"Computes bounded arithmetic product.\"\"\"
    result = x + y
    return result
"""


class EvolutionaryEngine(EvolutionaryEngineProtocol):
    """
    AI-Native Evolutionary Recombination Engine implementing EvolutionaryEngineProtocol.

    Conforms to docs/active/ACTIVE_CONTRACT.md (TASK-030).
    """

    def __init__(
        self,
        proto_path: Optional[Path] = None,
        config: Optional[EvolutionConfig] = None,
        rng_seed: Optional[int] = None,
    ) -> None:
        self.proto_path = proto_path
        self.config = config if config is not None else EvolutionConfig()
        seed_val = rng_seed if rng_seed is not None else self.config.seed
        self._rng = random.Random(seed_val)
        self._cached_proto_tree: Optional[ast.AST] = None
        if self.proto_path and self.proto_path.exists():
            self._cached_proto_tree, _ = _read_ast_tree(self.proto_path)

    # --------------------------------------------------------------------------
    # Fast-Path Lethality Gatekeeper (INV-EVO-06)
    # --------------------------------------------------------------------------

    def check_lethality(
        self,
        candidate_code: str,
        proto_path: Optional[Path] = None,
        ceiling_ms: Optional[float] = None,
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Fast-path compilation and AST docking lethality filter bounded by ceiling latency.

        Returns (is_lethal, elapsed_ms, defect_reason).
        """
        t0 = time.perf_counter()
        try:
            compile(candidate_code, "<candidate>", "exec")
            impl_tree = ast.parse(candidate_code)
        except (SyntaxError, ValueError, TypeError) as err:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return True, elapsed_ms, f"Compilation failed: {err}"

        target_proto = proto_path or self.proto_path
        if target_proto is not None:
            docked, reason = self._verify_candidate_docking(target_proto, impl_tree)
            if not docked:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return True, elapsed_ms, f"AST docking failed: {reason}"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        limit_ms = ceiling_ms if ceiling_ms is not None else self.config.lethality_ceiling_ms
        if elapsed_ms > limit_ms:
            return True, elapsed_ms, f"Lethality latency exceeded ({elapsed_ms:.2f}ms > {limit_ms}ms)"

        return False, elapsed_ms, None

    def is_lethal(self, candidate_code: str, proto_path: Optional[Path] = None) -> bool:
        """Determines whether candidate code is lethal prior to dynamic execution."""
        lethal, _, _ = self.check_lethality(candidate_code, proto_path=proto_path)
        return lethal

    def _get_proto_tree(self, proto_path: Path) -> Optional[ast.AST]:
        """Retrieves cached protocol AST tree or parses from file."""
        if self._cached_proto_tree is not None:
            return self._cached_proto_tree
        if proto_path.exists():
            tree, _ = _read_ast_tree(proto_path)
            self._cached_proto_tree = tree
            return tree
        return None

    def _is_relevant_candidate(
        self,
        p_name: str,
        cand_cls: str,
        req_methods: Dict[str, Any],
        impl_classes: Dict[str, Any],
        impl_bases: Dict[str, Any],
    ) -> bool:
        """Determines if candidate class is targeted for given protocol."""
        if p_name in impl_bases.get(cand_cls, []):
            return True
        if any(m in impl_classes[cand_cls] for m in req_methods):
            return True
        expected = p_name.replace("Protocol", "").lower()
        return expected in cand_cls.lower()

    def _check_protocols_against_impl(
        self,
        protocols: Dict[str, Any],
        impl_classes: Dict[str, Any],
        impl_bases: Dict[str, Any],
    ) -> Optional[str]:
        """Checks protocols against implementation classes, returning defect message if any."""
        checked = 0
        for p_name, req_methods in protocols.items():
            cand_cls = _select_candidate_class(p_name, req_methods, impl_classes, impl_bases)
            if cand_cls is None:
                continue
            if len(impl_classes) == 1 and len(protocols) > 1:
                if not self._is_relevant_candidate(
                    p_name, cand_cls, req_methods, impl_classes, impl_bases
                ):
                    continue
            checked += 1
            _, defects = _verify_single_protocol(p_name, req_methods, impl_classes, impl_bases)
            if defects:
                return defects[0].message
        if checked == 0 and impl_classes:
            first_proto = next(iter(protocols))
            _, defects = _verify_single_protocol(
                first_proto, protocols[first_proto], impl_classes, impl_bases
            )
            if defects:
                return defects[0].message
        return None

    def _verify_candidate_docking(
        self, proto_path: Path, impl_tree: ast.AST
    ) -> Tuple[bool, Optional[str]]:
        """Verifies candidate AST tree satisfies protocol interface definitions."""
        proto_tree = self._get_proto_tree(proto_path)
        if proto_tree is None:
            return True, None

        protocols = _extract_protocols(proto_tree)
        if not protocols:
            return True, None

        impl_classes, impl_bases = _extract_impl_classes(impl_tree)
        defect_msg = self._check_protocols_against_impl(protocols, impl_classes, impl_bases)
        if defect_msg is not None:
            return False, defect_msg
        return True, None

    # --------------------------------------------------------------------------
    # Homologous AST Crossover Operator (INV-EVO-03, INV-EVO-04)
    # --------------------------------------------------------------------------

    def _choose_crossover_mode(self, can_stmt: bool, can_expr: bool) -> Optional[str]:
        """Determines crossover operator mode based on candidate site availability."""
        if can_stmt and can_expr:
            return self._rng.choice(["stmt", "expr"])
        if can_stmt:
            return "stmt"
        if can_expr:
            return "expr"
        return None

    def _apply_crossover_mode(
        self,
        mode: str,
        stmt_a: List[StatementSite],
        stmt_b: List[StatementSite],
        expr_a: List[ExpressionSite],
        expr_b: List[ExpressionSite],
    ) -> None:
        """Applies chosen crossover swap to the AST trees."""
        if mode == "stmt":
            swap_statements(self._rng.choice(stmt_a), self._rng.choice(stmt_b))
        else:
            swap_expressions(self._rng.choice(expr_a), self._rng.choice(expr_b))

    def _unparse_and_validate_pair(
        self,
        tree_a: ast.AST,
        tree_b: ast.AST,
        fallback_a: str,
        fallback_b: str,
    ) -> Tuple[str, str]:
        """Unparses and validates syntax of crossed-over AST pair."""
        ast.fix_missing_locations(tree_a)
        ast.fix_missing_locations(tree_b)
        out_a, out_b = ast.unparse(tree_a), ast.unparse(tree_b)
        try:
            compile(out_a, "<cand_a>", "exec")
            compile(out_b, "<cand_b>", "exec")
            return out_a, out_b
        except (SyntaxError, ValueError):
            return fallback_a, fallback_b

    def crossover(self, parent_a_code: str, parent_b_code: str) -> Tuple[str, str]:
        """
        Homologous AST crossover between two parent programs (INV-EVO-03, INV-EVO-04).

        Restricts statement swaps to statements, expression swaps to expressions.
        """
        try:
            tree_a = ast.parse(parent_a_code)
            tree_b = ast.parse(parent_b_code)
        except SyntaxError:
            return parent_a_code, parent_b_code

        stmt_a = _collect_statement_sites(tree_a)
        stmt_b = _collect_statement_sites(tree_b)
        expr_a = _collect_expression_sites(stmt_a)
        expr_b = _collect_expression_sites(stmt_b)

        can_stmt = bool(stmt_a and stmt_b)
        can_expr = bool(expr_a and expr_b)
        mode = self._choose_crossover_mode(can_stmt, can_expr)
        if mode is None:
            return parent_a_code, parent_b_code

        self._apply_crossover_mode(mode, stmt_a, stmt_b, expr_a, expr_b)
        return self._unparse_and_validate_pair(tree_a, tree_b, parent_a_code, parent_b_code)

    # --------------------------------------------------------------------------
    # Body-Confined AST Mutation Operator (INV-EVO-04, INV-EVO-05)
    # --------------------------------------------------------------------------

    def mutate(self, candidate_code: str) -> str:
        """
        Body-confined AST mutation strictly modifying internal method bodies (INV-EVO-05).
        """
        try:
            tree = ast.parse(candidate_code)
        except SyntaxError:
            return candidate_code

        stmt_sites = _collect_statement_sites(tree)
        expr_sites = _collect_expression_sites(stmt_sites)
        if not (stmt_sites or expr_sites):
            return candidate_code

        operators = [
            lambda: self._apply_constant_mutation(expr_sites),
            lambda: self._apply_operator_mutation(expr_sites),
            lambda: self._apply_statement_swap(stmt_sites),
            lambda: self._apply_expression_swap(expr_sites),
        ]
        self._rng.shuffle(operators)
        mutated = any(op() for op in operators)
        if not mutated:
            return candidate_code

        ast.fix_missing_locations(tree)
        out_code = ast.unparse(tree)
        try:
            compile(out_code, "<mutant>", "exec")
            return out_code
        except (SyntaxError, ValueError):
            return candidate_code

    def _apply_constant_mutation(self, expr_sites: List[ExpressionSite]) -> bool:
        """Mutates numerical or boolean constant expressions."""
        const_sites = [s for s in expr_sites if isinstance(s.expr, ast.Constant)]
        if not const_sites:
            return False
        site = self._rng.choice(const_sites)
        const = site.expr
        assert isinstance(const, ast.Constant)
        if isinstance(const.value, bool):
            _set_expr_at_site(site, ast.Constant(value=not const.value))
            return True
        if isinstance(const.value, (int, float)):
            delta = self._rng.choice([-1, 1, 2, -2, 5, -5])
            _set_expr_at_site(site, ast.Constant(value=const.value + delta))
            return True
        return False

    def _apply_operator_mutation(self, expr_sites: List[ExpressionSite]) -> bool:
        """Mutates binary or comparison operators homologously."""
        binop_sites = [s for s in expr_sites if isinstance(s.expr, ast.BinOp)]
        comp_sites = [s for s in expr_sites if isinstance(s.expr, ast.Compare)]
        if binop_sites and (not comp_sites or self._rng.random() < 0.5):
            b_site = self._rng.choice(binop_sites)
            binop = b_site.expr
            assert isinstance(binop, ast.BinOp)
            new_op = self._rng.choice([ast.Add(), ast.Sub(), ast.Mult(), ast.FloorDiv()])
            binop.op = new_op
            return True
        if comp_sites:
            c_site = self._rng.choice(comp_sites)
            comp = c_site.expr
            assert isinstance(comp, ast.Compare)
            if comp.ops:
                comp.ops[0] = self._rng.choice([ast.Lt(), ast.LtE(), ast.Gt(), ast.GtE(), ast.Eq(), ast.NotEq()])
                return True
        return False

    def _apply_statement_swap(self, stmt_sites: List[StatementSite]) -> bool:
        """Swaps two statements within the same block homologously."""
        if len(stmt_sites) < 2:
            return False
        site_a = self._rng.choice(stmt_sites)
        matching = [s for s in stmt_sites if s.block is site_a.block and s.index != site_a.index]
        if not matching:
            return False
        site_b = self._rng.choice(matching)
        swap_statements(site_a, site_b)
        return True

    def _apply_expression_swap(self, expr_sites: List[ExpressionSite]) -> bool:
        """Swaps two expressions within collected sites homologously."""
        if len(expr_sites) < 2:
            return False
        site_a, site_b = self._rng.sample(expr_sites, 2)
        swap_expressions(site_a, site_b)
        return True

    # --------------------------------------------------------------------------
    # Genetic Evolution Optimization Loop
    # --------------------------------------------------------------------------

    def evolve(
        self,
        seed_code: str,
        evaluator: FitnessEvaluatorProtocol,
        config: EvolutionConfig,
    ) -> EvolutionOutcome:
        """Complete genetic algorithm evolution loop starting from seed implementation."""
        if config.seed is not None:
            self._rng.seed(config.seed)

        population, eval_count = self._init_population(seed_code, evaluator, config)
        reports: List[GenerationReport] = []
        t0 = time.perf_counter()
        rep_0 = self._build_report(0, population, time.perf_counter() - t0)
        reports.append(rep_0)

        for gen in range(1, config.generations):
            t_gen = time.perf_counter()
            population, step_evals = self._step_generation(population, gen, evaluator, config)
            eval_count += step_evals
            rep = self._build_report(gen, population, time.perf_counter() - t_gen)
            reports.append(rep)

        best_cand = max(population, key=lambda c: c.fitness_score)
        success = best_cand.fitness_score > 0.0 and not best_cand.is_lethal
        return EvolutionOutcome(
            success=success,
            best_candidate=best_cand,
            generation_reports=tuple(reports),
            total_generations=len(reports),
            total_candidates_evaluated=eval_count,
            termination_reason="max_generations",
        )

    def _init_population(
        self,
        seed_code: str,
        evaluator: FitnessEvaluatorProtocol,
        config: EvolutionConfig,
    ) -> Tuple[List[MutantCandidate], int]:
        """Initializes candidate population using seed code and immediate mutants."""
        population: List[MutantCandidate] = []
        is_dead, _, _ = self.check_lethality(seed_code)
        seed_score = 0.0 if is_dead else evaluator.evaluate(seed_code)
        seed_cand = MutantCandidate(
            candidate_id="seed-000",
            source_code=seed_code,
            generation=0,
            parent_ids=(),
            fitness_score=seed_score,
            is_lethal=is_dead,
            mutation_type="seed",
        )
        population.append(seed_cand)
        eval_count = 1

        for i in range(1, config.population_size):
            cand_code = self.mutate(seed_code)
            is_dead_c, _, _ = self.check_lethality(cand_code)
            score = 0.0 if is_dead_c else evaluator.evaluate(cand_code)
            cand = MutantCandidate(
                candidate_id=f"init-{i:03d}",
                source_code=cand_code,
                generation=0,
                parent_ids=("seed-000",),
                fitness_score=score,
                is_lethal=is_dead_c,
                mutation_type="init_mutation",
            )
            population.append(cand)
            eval_count += 1
        return population, eval_count

    def _select_parent(
        self, population: List[MutantCandidate], tournament_size: int
    ) -> MutantCandidate:
        """Selects parent candidate via tournament selection."""
        k = min(tournament_size, len(population))
        pool = self._rng.sample(population, k)
        return max(pool, key=lambda c: c.fitness_score)

    def _step_generation(
        self,
        current_pop: List[MutantCandidate],
        gen: int,
        evaluator: FitnessEvaluatorProtocol,
        config: EvolutionConfig,
    ) -> Tuple[List[MutantCandidate], int]:
        """Executes a single generational reproduction and selection cycle."""
        next_pop: List[MutantCandidate] = []
        eval_count = 0
        sorted_pop = sorted(current_pop, key=lambda c: c.fitness_score, reverse=True)
        elitism_count = max(1, config.population_size // 10)
        next_pop.extend(sorted_pop[:elitism_count])

        child_idx = len(next_pop)
        while len(next_pop) < config.population_size:
            parent_a = self._select_parent(current_pop, config.tournament_size)
            parent_b = self._select_parent(current_pop, config.tournament_size)
            child_code, op_type = self._reproduce_pair(parent_a, parent_b, config)
            is_dead, _, _ = self.check_lethality(child_code)
            score = 0.0 if is_dead else evaluator.evaluate(child_code)
            eval_count += 1
            cand = MutantCandidate(
                candidate_id=f"gen{gen:02d}-{child_idx:03d}",
                source_code=child_code,
                generation=gen,
                parent_ids=(parent_a.candidate_id, parent_b.candidate_id),
                fitness_score=score,
                is_lethal=is_dead,
                mutation_type=op_type,
            )
            next_pop.append(cand)
            child_idx += 1
        return next_pop, eval_count

    def _reproduce_pair(
        self,
        parent_a: MutantCandidate,
        parent_b: MutantCandidate,
        config: EvolutionConfig,
    ) -> Tuple[str, str]:
        """Produces offspring candidate through crossover and mutation."""
        op_type = "clone"
        if self._rng.random() < config.crossover_rate:
            child_code, _ = self.crossover(parent_a.source_code, parent_b.source_code)
            op_type = "crossover"
        else:
            child_code = parent_a.source_code

        if self._rng.random() < config.mutation_rate:
            child_code = self.mutate(child_code)
            op_type = f"{op_type}+mutation"
        return child_code, op_type

    def _build_report(
        self, gen: int, population: List[MutantCandidate], elapsed_sec: float
    ) -> GenerationReport:
        """Constructs telemetry report summarizing generation population metrics."""
        scores = [c.fitness_score for c in population]
        best_fit = max(scores) if scores else 0.0
        avg_fit = (sum(scores) / len(scores)) if scores else 0.0
        lethal_count = sum(1 for c in population if c.is_lethal)
        survivor_count = len(population) - lethal_count
        return GenerationReport(
            generation_number=gen,
            best_fitness=best_fit,
            average_fitness=avg_fit,
            lethal_count=lethal_count,
            survivor_count=survivor_count,
            elapsed_sec=elapsed_sec,
        )


# ==============================================================================
# 4. CLI Entrypoint (INV-EVO-08)
# ==============================================================================

def _parse_cli_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parses command-line arguments for evolutionary engine CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m core.evolutionary_engine",
        description="AI-Native Evolutionary Recombination Engine CLI (TASK-030).",
    )
    parser.add_argument("--generations", type=int, default=2, help="Generations count.")
    parser.add_argument("--pop", type=int, default=4, help="Population size.")
    parser.add_argument("--mutation-rate", type=float, default=0.1, help="Mutation probability.")
    parser.add_argument("--crossover-rate", type=float, default=0.8, help="Crossover probability.")
    parser.add_argument("--seed", type=int, default=None, help="Random deterministic seed.")
    parser.add_argument("--json", action="store_true", default=False, help="Emit JSON output.")
    return parser.parse_args(argv)


def _print_human_report(outcome: EvolutionOutcome) -> None:
    """Prints formatted summary report to stdout."""
    print("================================================================================")
    print("  AI-NATIVE EVOLUTIONARY RECOMBINATION ENGINE EXECUTION SUMMARY")
    print("================================================================================")
    print(f"Status: {'SUCCESS' if outcome.success else 'FAILED'}")
    print(f"Total Generations: {outcome.total_generations}")
    print(f"Total Evaluated: {outcome.total_candidates_evaluated}")
    print(f"Best Candidate ID: {outcome.best_candidate.candidate_id}")
    print(f"Best Fitness Score: {outcome.best_candidate.fitness_score:.6f}")
    print(f"Termination Reason: {outcome.termination_reason}")
    print("--------------------------------------------------------------------------------")
    for rep in outcome.generation_reports:
        print(
            f"Gen {rep.generation_number:02d}: Best={rep.best_fitness:.4f}, "
            f"Avg={rep.average_fitness:.4f}, Lethal={rep.lethal_count}, "
            f"Survivors={rep.survivor_count} ({rep.elapsed_sec:.4f}s)"
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI execution entrypoint conforming to INV-EVO-08."""
    args = _parse_cli_args(argv)
    config = EvolutionConfig(
        population_size=args.pop,
        generations=args.generations,
        mutation_rate=args.mutation_rate,
        crossover_rate=args.crossover_rate,
        seed=args.seed,
    )
    engine = EvolutionaryEngine(config=config, rng_seed=args.seed)
    evaluator = DefaultFitnessEvaluator()

    outcome = engine.evolve(DEFAULT_SEED_CODE, evaluator, config)

    if args.json:
        print(json.dumps(outcome.to_dict(), indent=2))
    else:
        _print_human_report(outcome)

    return 0


if __name__ == "__main__":
    sys.exit(main())
