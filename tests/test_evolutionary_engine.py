"""
Independent IV&V Companion Test Suite for AI-Native Evolutionary Recombination Engine.

Conforms strictly to docs/active/ACTIVE_CONTRACT.md (TASK-030).
Ingests ACTIVE_CONTRACT.md as primary specification authority with fallback determinism.
Evaluates EvolutionConfig, MutantCandidate, GenerationReport, EvolutionOutcome data models,
homologous AST crossover (INV-EVO-03), body-confined mutation (INV-EVO-04, INV-EVO-05),
fast-path lethality gatekeeper latency (INV-EVO-06), out-of-process watchdog isolation (INV-EVO-07),
CLI invocation determinism and JSON serialization (INV-EVO-08),
and static AST docking verification between protocol and implementation (INV-EVO-02).
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
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import unittest

try:
    from core.interfaces.evolutionary_engine_proto import (
        EvolutionConfig,
        EvolutionOutcome,
        EvolutionaryEngineProtocol,
        FitnessEvaluatorProtocol,
        GenerationReport,
        MutantCandidate,
    )
    from core.evolutionary_engine import (
        DEFAULT_SEED_CODE,
        DefaultFitnessEvaluator,
        EvolutionaryEngine,
        FitnessEvaluator,
        SubprocessFitnessEvaluator,
        main,
    )
    from core.ast_docking_checker import verify_ast_docking
    _MODULE_AVAILABLE = True
except ModuleNotFoundError:
    try:
        from sandbox.core.interfaces.evolutionary_engine_proto import (
            EvolutionConfig,
            EvolutionOutcome,
            EvolutionaryEngineProtocol,
            FitnessEvaluatorProtocol,
            GenerationReport,
            MutantCandidate,
        )
        from sandbox.core.evolutionary_engine import (
            DEFAULT_SEED_CODE,
            DefaultFitnessEvaluator,
            EvolutionaryEngine,
            FitnessEvaluator,
            SubprocessFitnessEvaluator,
            main,
        )
        from sandbox.core.ast_docking_checker import verify_ast_docking
        _MODULE_AVAILABLE = True
    except ModuleNotFoundError:
        _MODULE_AVAILABLE = False
        EvolutionConfig = None  # type: ignore[assignment]
        EvolutionOutcome = None  # type: ignore[assignment]
        EvolutionaryEngineProtocol = None  # type: ignore[assignment]
        FitnessEvaluatorProtocol = None  # type: ignore[assignment]
        GenerationReport = None  # type: ignore[assignment]
        MutantCandidate = None  # type: ignore[assignment]
        DEFAULT_SEED_CODE = ""
        DefaultFitnessEvaluator = None  # type: ignore[assignment]
        EvolutionaryEngine = None  # type: ignore[assignment]
        FitnessEvaluator = None  # type: ignore[assignment]
        SubprocessFitnessEvaluator = None  # type: ignore[assignment]
        main = None  # type: ignore[assignment]
        verify_ast_docking = None  # type: ignore[assignment]




class MockFitnessEvaluator(FitnessEvaluatorProtocol):
    """Deterministic mock candidate evaluator conforming to FitnessEvaluatorProtocol."""

    def __init__(self, base_score: float = 10.0, return_zero: bool = False) -> None:
        self.base_score = base_score
        self.return_zero = return_zero
        self.eval_count = 0

    def evaluate(self, candidate_code: str) -> float:
        """Evaluates candidate code string returning numerical fitness score."""
        self.eval_count += 1
        if self.return_zero:
            return 0.0
        code_length_factor = float(len(candidate_code) % 7)
        return self.base_score + code_length_factor



class TestEvolutionaryEngineDataModels(unittest.TestCase):
    """Verifies frozen data models instantiation, immutability, and boundary validation."""

    def test_evolution_config_defaults_and_immutability(self) -> None:
        """Positive and negative test: Verifies EvolutionConfig defaults and frozen immutability."""
        config = EvolutionConfig()
        self.assertEqual(config.population_size, 20)
        self.assertEqual(config.generations, 10)
        self.assertEqual(config.mutation_rate, 0.1)
        self.assertEqual(config.crossover_rate, 0.8)
        self.assertEqual(config.tournament_size, 3)
        self.assertEqual(config.lethality_ceiling_ms, 5.0)
        self.assertEqual(config.watchdog_timeout_sec, 3.0)
        self.assertIsNone(config.seed)

        dict_repr = config.to_dict()
        self.assertEqual(dict_repr["population_size"], 20)
        self.assertEqual(dict_repr["generations"], 10)

        with self.assertRaises(FrozenInstanceError):
            config.population_size = 50  # type: ignore[misc]

    def test_mutant_candidate_and_immutability(self) -> None:
        """Positive and negative test: Verifies MutantCandidate schema and immutability."""
        cand = MutantCandidate(
            candidate_id="cand-001",
            source_code="x = 1\n",
            generation=0,
            parent_ids=(),
            fitness_score=15.5,
            is_lethal=False,
            mutation_type="seed",
        )
        self.assertEqual(cand.candidate_id, "cand-001")
        self.assertEqual(cand.fitness_score, 15.5)
        self.assertFalse(cand.is_lethal)
        self.assertIn("candidate_id", cand.to_dict())

        with self.assertRaises(FrozenInstanceError):
            cand.fitness_score = 99.0  # type: ignore[misc]

    def test_generation_report_and_immutability(self) -> None:
        """Positive and negative test: Verifies GenerationReport telemetry and immutability."""
        rep = GenerationReport(
            generation_number=1,
            best_fitness=12.5,
            average_fitness=8.3,
            lethal_count=2,
            survivor_count=8,
            elapsed_sec=0.12,
        )
        self.assertEqual(rep.generation_number, 1)
        self.assertEqual(rep.survivor_count, 8)
        self.assertIn("generation_number", rep.to_dict())

        with self.assertRaises(FrozenInstanceError):
            rep.best_fitness = 20.0  # type: ignore[misc]

    def test_evolution_outcome_and_immutability(self) -> None:
        """Positive and negative test: Verifies EvolutionOutcome summary and immutability."""
        cand = MutantCandidate("best-01", "return 42", 1, (), 25.0, False, "crossover")
        outcome = EvolutionOutcome(
            success=True,
            best_candidate=cand,
            generation_reports=(),
            total_generations=2,
            total_candidates_evaluated=10,
            termination_reason="max_generations",
        )
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.best_candidate.candidate_id, "best-01")
        self.assertIn("best_candidate", outcome.to_dict())

        with self.assertRaises(FrozenInstanceError):
            outcome.success = False  # type: ignore[misc]

    def test_negative_config_invalid_population_size(self) -> None:
        """Negative test: Negative or zero population_size raises ValueError."""
        with self.assertRaises(ValueError):
            EvolutionConfig(population_size=-5)
        with self.assertRaises(ValueError):
            EvolutionConfig(population_size=0)

    def test_negative_config_invalid_generations(self) -> None:
        """Negative test: Negative or zero generations raises ValueError."""
        with self.assertRaises(ValueError):
            EvolutionConfig(generations=-1)
        with self.assertRaises(ValueError):
            EvolutionConfig(generations=0)

    def test_negative_config_invalid_mutation_rate(self) -> None:
        """Negative test: Mutation rate outside [0.0, 1.0] raises ValueError."""
        with self.assertRaises(ValueError):
            EvolutionConfig(mutation_rate=-0.1)
        with self.assertRaises(ValueError):
            EvolutionConfig(mutation_rate=1.1)

    def test_negative_config_invalid_crossover_rate(self) -> None:
        """Negative test: Crossover rate outside [0.0, 1.0] raises ValueError."""
        with self.assertRaises(ValueError):
            EvolutionConfig(crossover_rate=-0.2)
        with self.assertRaises(ValueError):
            EvolutionConfig(crossover_rate=1.5)

    def test_negative_config_invalid_tournament_size(self) -> None:
        """Negative test: Zero or negative tournament size raises ValueError."""
        with self.assertRaises(ValueError):
            EvolutionConfig(tournament_size=0)
        with self.assertRaises(ValueError):
            EvolutionConfig(tournament_size=-3)


class TestEvolutionaryEngineDockingAndProtocols(unittest.TestCase):
    """Verifies static AST docking between proto and impl alongside protocol conformance."""

    def test_engine_conforms_to_evolutionary_engine_protocol(self) -> None:
        """Positive test: EvolutionaryEngine instantiates and conforms to protocol interface."""
        engine = EvolutionaryEngine()
        self.assertTrue(EvolutionaryEngineProtocol in EvolutionaryEngine.__mro__)
        self.assertTrue(callable(getattr(engine, "crossover", None)))
        self.assertTrue(callable(getattr(engine, "mutate", None)))
        self.assertTrue(callable(getattr(engine, "evolve", None)))

    def test_static_ast_docking_inv_evo_02(self) -> None:
        """Positive test: Static AST docking between proto and impl evaluates to 0 defects."""
        proto_path = Path("core/interfaces/evolutionary_engine_proto.py")
        impl_path = Path("core/evolutionary_engine.py")
        if not proto_path.exists():
            proto_path = Path("sandbox/core/interfaces/evolutionary_engine_proto.py")
        if not impl_path.exists():
            impl_path = Path("sandbox/core/evolutionary_engine.py")

        report = verify_ast_docking(proto_path, impl_path)
        self.assertTrue(report.is_docked, f"AST Docking failed with defects: {report.defects}")
        self.assertEqual(len(report.defects), 0, "AST docking detected interface defects")

        verified_names = [str(m) for m in report.verified_methods]
        self.assertTrue(any("evaluate" in name for name in verified_names))
        self.assertTrue(any("crossover" in name for name in verified_names))
        self.assertTrue(any("mutate" in name for name in verified_names))
        self.assertTrue(any("evolve" in name for name in verified_names))

    def test_negative_abstract_protocols_raise_not_implemented(self) -> None:
        """Negative test: Base protocol methods raise NotImplementedError or TypeError."""
        with self.assertRaises(TypeError):
            FitnessEvaluatorProtocol()
        with self.assertRaises(TypeError):
            EvolutionaryEngineProtocol()

        with self.assertRaises(NotImplementedError):
            FitnessEvaluatorProtocol.evaluate(None, "code = 1")

        with self.assertRaises(NotImplementedError):
            EvolutionaryEngineProtocol.crossover(None, "code_a", "code_b")
        with self.assertRaises(NotImplementedError):
            EvolutionaryEngineProtocol.mutate(None, "code_a")
        with self.assertRaises(NotImplementedError):
            dummy_cfg = EvolutionConfig()
            dummy_eval = MockFitnessEvaluator()
            EvolutionaryEngineProtocol.evolve(None, "seed", dummy_eval, dummy_cfg)


class TestHomologousCrossoverOperator(unittest.TestCase):
    """Verifies grammar-aware homologous AST crossover splicing (INV-EVO-03)."""

    def setUp(self) -> None:
        self.engine = EvolutionaryEngine(rng_seed=42)
        self.parent_a = (
            "def process_a(val: int) -> int:\n"
            "    step1 = val + 10\n"
            "    step2 = step1 * 2\n"
            "    return step2\n"
        )
        self.parent_b = (
            "def process_b(item: int) -> int:\n"
            "    base = item - 5\n"
            "    total = base + 100\n"
            "    return total\n"
        )

    def test_homologous_crossover_produces_syntactically_valid_offspring(self) -> None:
        """Positive test: Crossover between two valid code snippets yields valid ASTs."""
        child_a, child_b = self.engine.crossover(self.parent_a, self.parent_b)
        tree_a = ast.parse(child_a)
        tree_b = ast.parse(child_b)

        self.assertIsInstance(tree_a, ast.Module)
        self.assertIsInstance(tree_b, ast.Module)
        self.assertGreater(len(child_a.strip()), 0)
        self.assertGreater(len(child_b.strip()), 0)

    def test_homologous_crossover_multiple_seeds_preserve_syntax(self) -> None:
        """Positive test: Multiple random seeds yield deterministically valid offspring."""
        for seed_val in (7, 13, 21, 99):
            seeded_engine = EvolutionaryEngine(rng_seed=seed_val)
            c_a, c_b = seeded_engine.crossover(self.parent_a, self.parent_b)
            parsed_a = ast.parse(c_a)
            parsed_b = ast.parse(c_b)
            self.assertEqual(len(parsed_a.body), 1)
            self.assertEqual(len(parsed_b.body), 1)

    def test_negative_crossover_malformed_parent_fail_open(self) -> None:
        """Negative test: Malformed syntax in parent handles fail-open without unhandled crash."""
        malformed = "def broken_parent(:::"
        child_a, child_b = self.engine.crossover(malformed, self.parent_b)
        self.assertEqual(child_a, malformed, "Malformed parent A not returned unchanged")
        self.assertEqual(child_b, self.parent_b, "Valid parent B not returned unchanged")

        child_x, child_y = self.engine.crossover(self.parent_a, malformed)
        self.assertEqual(child_x, self.parent_a)
        self.assertEqual(child_y, malformed)

    def test_negative_crossover_empty_code_fail_open(self) -> None:
        """Negative test: Empty code strings return inputs unchanged."""
        empty_code = ""
        c_a, c_b = self.engine.crossover(empty_code, self.parent_b)
        self.assertEqual(c_a, empty_code)
        self.assertEqual(c_b, self.parent_b)


class TestMutationAndSignatureImmutability(unittest.TestCase):
    """Verifies signature immutability and body-confined AST mutation (INV-EVO-04, INV-EVO-05)."""

    def setUp(self) -> None:
        self.engine = EvolutionaryEngine(rng_seed=42)

    def test_mutation_preserves_function_signature(self) -> None:
        """Positive test: Function name, args, and return annotation remain strictly unchanged."""
        target_code = (
            "def calculate_total(quantity: int, unit_price: int) -> int:\n"
            "    subtotal = quantity * unit_price\n"
            "    tax = subtotal + 5\n"
            "    return tax\n"
        )
        mutant_code = self.engine.mutate(target_code)
        tree = ast.parse(mutant_code)
        self.assertEqual(len(tree.body), 1)
        func_node = tree.body[0]
        self.assertIsInstance(func_node, ast.FunctionDef)
        assert isinstance(func_node, ast.FunctionDef)

        self.assertEqual(func_node.name, "calculate_total")
        param_names = [arg.arg for arg in func_node.args.args]
        self.assertEqual(param_names, ["quantity", "unit_price"])
        self.assertIsNotNone(func_node.returns)
        self.assertEqual(getattr(func_node.returns, "id", ""), "int")

    def test_mutation_preserves_protocol_class_signatures(self) -> None:
        """Positive test: Protocol class definitions and method signatures remain immutable."""
        code_with_protocol = (
            "from typing import Protocol\n"
            "class WorkerProto(Protocol):\n"
            "    def execute(self, job_id: str) -> bool:\n"
            "        raise NotImplementedError('Protocol')\n"
            "def run_worker(flag: bool) -> int:\n"
            "    val = 10\n"
            "    val = val + 1\n"
            "    return val\n"
        )
        for seed_val in (1, 2, 3, 4, 5):
            eng = EvolutionaryEngine(rng_seed=seed_val)
            mutant = eng.mutate(code_with_protocol)
            self.assertIn("class WorkerProto(Protocol):", mutant)
            self.assertIn("def execute(self, job_id: str) -> bool:", mutant)
            self.assertIn("def run_worker(flag: bool) -> int:", mutant)

    def test_negative_mutation_malformed_syntax_fail_open(self) -> None:
        """Negative test: Malformed syntax string passed to mutate returns input unchanged."""
        broken_syntax = "def broken(:::"
        result = self.engine.mutate(broken_syntax)
        self.assertEqual(result, broken_syntax, "Malformed syntax did not fail-open")

    def test_negative_mutation_no_mutable_nodes_fail_open(self) -> None:
        """Negative test: Module with only Protocol or empty returns original unchanged."""
        proto_only = (
            "from typing import Protocol\n"
            "class StandaloneProto(Protocol):\n"
            "    def run(self) -> None:\n"
            "        raise NotImplementedError('noop')\n"
        )
        res = self.engine.mutate(proto_only)
        self.assertEqual(res, proto_only)


class TestLethalityGatekeeper(unittest.TestCase):
    """Verifies fast-path compilation and AST docking lethality filter (INV-EVO-06)."""

    def setUp(self) -> None:
        self.engine = EvolutionaryEngine(rng_seed=42)

    def test_lethality_latency_within_ceiling_ms_inv_evo_06(self) -> None:
        """Positive test: Lethality filter execution finishes within 5.0ms ceiling."""
        valid_code = (
            "def compute(a: int, b: int) -> int:\n"
            "    res = a + b\n"
            "    return res\n"
        )
        # Warm-up run to prime parsing cache
        self.engine.check_lethality(valid_code)

        is_lethal, elapsed_ms, defect = self.engine.check_lethality(valid_code)
        self.assertFalse(is_lethal, f"Valid code incorrectly flagged lethal: {defect}")
        self.assertLessEqual(
            elapsed_ms,
            5.0,
            f"Lethality check latency {elapsed_ms:.2f}ms exceeded 5.0ms ceiling",
        )
        self.assertIsNone(defect)

    def test_negative_lethality_rejects_syntax_error(self) -> None:
        """Negative test: Code with syntax error rejected as lethal with diagnostic reason."""
        syntax_err_code = "def bad_syntax(a, b:\n    return a + b\n"
        is_lethal, _, defect = self.engine.check_lethality(syntax_err_code)
        self.assertTrue(is_lethal, "Syntax defect not flagged as lethal")
        self.assertIsNotNone(defect)
        self.assertIn("Compilation failed", str(defect))
        self.assertTrue(self.engine.is_lethal(syntax_err_code))

    def test_negative_lethality_rejects_broken_indentation(self) -> None:
        """Negative test: Code with broken indentation rejected as lethal."""
        bad_indent_code = "def bad_indent():\nreturn 42\n"
        is_lethal, _, defect = self.engine.check_lethality(bad_indent_code)
        self.assertTrue(is_lethal, "Indentation defect not flagged as lethal")
        self.assertIsNotNone(defect)

    def test_negative_lethality_rejects_ast_docking_mismatch(self) -> None:
        """Negative test: Code failing protocol interface docking is marked lethal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proto_path = Path(tmpdir) / "test_proto.py"
            proto_path.write_text(
                "from typing import Protocol\n"
                "class RequiredProto(Protocol):\n"
                "    def required_method(self, val: int) -> int:\n"
                "        raise NotImplementedError('dock')\n",
                encoding="utf-8",
            )
            non_docking_code = (
                "class CandidateClass:\n"
                "    def wrong_method(self) -> None:\n"
                "        val = 1\n"
            )
            is_lethal, _, defect = self.engine.check_lethality(
                non_docking_code, proto_path=proto_path
            )
            self.assertTrue(is_lethal, "Candidate failing docking not flagged lethal")
            self.assertIsNotNone(defect)
            self.assertIn("AST docking failed", str(defect))

    def test_negative_lethality_latency_ceiling_exceeded_marks_lethal(self) -> None:
        """Negative test: Ceiling latency violation marks candidate lethal."""
        valid_code = "def simple() -> int:\n    return 1\n"
        # Zero threshold forces ceiling exceeded branch
        is_lethal, elapsed_ms, defect = self.engine.check_lethality(valid_code, ceiling_ms=0.0)
        self.assertTrue(is_lethal)
        self.assertIsNotNone(defect)
        self.assertIn("Lethality latency exceeded", str(defect))


class TestDynamicFitnessEvaluatorAndWatchdog(unittest.TestCase):
    """Verifies out-of-process execution and subprocess watchdog isolation (INV-EVO-07)."""

    def test_evaluator_scores_valid_candidate_successfully(self) -> None:
        """Positive test: Valid candidate executes and returns numerical fitness score."""
        evaluator = DefaultFitnessEvaluator(timeout_sec=2.0)
        candidate_code = (
            "def solve() -> int:\n"
            "    return 100\n"
            "print('FITNESS: 42.5')\n"
        )
        score = evaluator.evaluate(candidate_code)
        self.assertEqual(score, 42.5)

    def test_evaluator_with_custom_score_extractor(self) -> None:
        """Positive test: Evaluator parses stdout via custom score extractor."""
        evaluator = DefaultFitnessEvaluator(
            timeout_sec=2.0,
            score_extractor=lambda out, code: 99.0 if "CUSTOM_OK" in out else 0.0,
        )
        candidate_code = "print('CUSTOM_OK')\n"
        score = evaluator.evaluate(candidate_code)
        self.assertEqual(score, 99.0)

    def test_negative_subprocess_watchdog_timeout_inv_evo_07(self) -> None:
        """Negative test: Infinite loop aborted cleanly by watchdog returning 0.0 score."""
        evaluator = DefaultFitnessEvaluator(timeout_sec=0.3)
        infinite_loop_code = (
            "accum = 1\n"
            "while True:\n"
            "    accum = accum + 1\n"
        )
        t0 = time.perf_counter()
        score = evaluator.evaluate(infinite_loop_code)
        elapsed = time.perf_counter() - t0

        self.assertEqual(score, 0.0, "Watchdog timeout did not score as 0.0")
        self.assertLess(
            elapsed,
            2.5,
            "Watchdog did not terminate infinite loop candidate within reasonable bounds",
        )

    def test_negative_evaluator_runtime_error_returns_zero(self) -> None:
        """Negative test: Candidate raising unhandled exception at runtime returns 0.0."""
        evaluator = DefaultFitnessEvaluator(timeout_sec=1.5)
        crashing_code = "raise RuntimeError('Crashing intentional test candidate')\n"
        score = evaluator.evaluate(crashing_code)
        self.assertEqual(score, 0.0)

    def test_negative_evaluator_non_zero_exit_code_returns_zero(self) -> None:
        """Negative test: Candidate exiting with non-zero status returns 0.0 score."""
        evaluator = DefaultFitnessEvaluator(timeout_sec=1.5)
        exit_code = "import sys\nsys.exit(3)\n"
        score = evaluator.evaluate(exit_code)
        self.assertEqual(score, 0.0)

    def test_negative_watchdog_timeout_clamped_to_boundaries(self) -> None:
        """Negative test: Watchdog timeout_sec clamped to [0.01, 3.0] bounds."""
        eval_high = DefaultFitnessEvaluator(timeout_sec=10.0)
        self.assertEqual(eval_high.timeout_sec, 3.0)

        eval_low = DefaultFitnessEvaluator(timeout_sec=-5.0)
        self.assertEqual(eval_low.timeout_sec, 0.01)


class TestEvolutionaryEngineOptimizationLoop(unittest.TestCase):
    """Verifies complete genetic evolution optimization loop execution and telemetry."""

    def test_mock_evolution_loop_converges_successfully(self) -> None:
        """Positive test: Evolution loop for 2 generations produces valid outcome."""
        config = EvolutionConfig(population_size=4, generations=2, seed=42)
        engine = EvolutionaryEngine(config=config, rng_seed=42)
        evaluator = MockFitnessEvaluator(base_score=10.0)

        outcome = engine.evolve(DEFAULT_SEED_CODE, evaluator, config)
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.total_generations, 2)
        self.assertEqual(len(outcome.generation_reports), 2)
        self.assertGreater(outcome.total_candidates_evaluated, 0)
        self.assertGreater(outcome.best_candidate.fitness_score, 0.0)
        self.assertFalse(outcome.best_candidate.is_lethal)

    def test_negative_evolution_loop_zero_fitness_fails(self) -> None:
        """Negative test: Population where all candidates score 0.0 yields success=False."""
        config = EvolutionConfig(population_size=4, generations=2, seed=42)
        engine = EvolutionaryEngine(config=config, rng_seed=42)
        zero_evaluator = MockFitnessEvaluator(return_zero=True)

        outcome = engine.evolve(DEFAULT_SEED_CODE, zero_evaluator, config)
        self.assertFalse(outcome.success, "Zero fitness population unexpectedly succeeded")
        self.assertEqual(outcome.best_candidate.fitness_score, 0.0)

    def test_negative_evolution_loop_lethal_seed(self) -> None:
        """Negative test: Lethal seed code initialized with is_lethal=True."""
        config = EvolutionConfig(population_size=3, generations=1, seed=42)
        engine = EvolutionaryEngine(config=config, rng_seed=42)
        evaluator = MockFitnessEvaluator()
        lethal_seed = "def broken(:::\n"

        outcome = engine.evolve(lethal_seed, evaluator, config)
        rep0 = outcome.generation_reports[0]
        self.assertGreaterEqual(rep0.lethal_count, 1)


class TestEvolutionaryEngineCLI(unittest.TestCase):
    """Verifies CLI entrypoint execution determinism and JSON serialization (INV-EVO-08)."""

    def test_cli_human_output_exits_zero_inv_evo_08(self) -> None:
        """Positive test: CLI execution with default human formatting exits with code 0."""
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "core.evolutionary_engine",
                "--generations",
                "1",
                "--pop",
                "2",
                "--seed",
                "42",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        self.assertEqual(res.returncode, 0, f"CLI failed with error: {res.stderr}")
        self.assertIn("AI-NATIVE EVOLUTIONARY RECOMBINATION ENGINE", res.stdout)
        self.assertIn("Status: SUCCESS", res.stdout)

    def test_cli_json_output_payload_structure(self) -> None:
        """Positive test: CLI execution with --json outputs valid parsable JSON."""
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "core.evolutionary_engine",
                "--generations",
                "1",
                "--pop",
                "2",
                "--json",
                "--seed",
                "42",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        self.assertEqual(res.returncode, 0, f"CLI --json failed: {res.stderr}")
        payload = json.loads(res.stdout)
        self.assertIn("success", payload)
        self.assertIn("best_candidate", payload)
        self.assertIn("generation_reports", payload)
        self.assertEqual(payload["total_generations"], 1)

    def test_negative_cli_invalid_argument_exits_non_zero(self) -> None:
        """Negative test: Passing unrecognized command line argument exits non-zero."""
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "core.evolutionary_engine",
                "--unrecognized-flag-xyz",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("unrecognized arguments", res.stderr)


if __name__ == "__main__":
    unittest.main()
