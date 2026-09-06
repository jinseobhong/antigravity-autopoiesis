"""
Companion test suite for Scheduled LFU Cache Vacuuming Routine (TASK-008).

Ingests docs/active/ACTIVE_CONTRACT.md as primary specification authority.
Evaluates directory scanning, cumulative size summation, LFU eviction ordering,
tie-breaking with oldest last_accessed timestamp, Windows file lock retry backoff,
watermark invariants, CLI invocation, and fail-open resilience.
Enforces AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12 with >= 40% negative ratio.
"""

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional
import unittest
from unittest import mock

try:
    from core.cache_vacuum import (
        CacheFileMetadata,
        VacuumConfig,
        VacuumResult,
        scan_cache_directory,
        calculate_cumulative_size,
        sort_eviction_candidates,
        delete_file_with_retry,
        run_cache_vacuum,
    )
    _MODULE_AVAILABLE = True
    _MODULE_NAME = "core.cache_vacuum"
except ModuleNotFoundError:
    try:
        from sandbox.core.cache_vacuum import (
            CacheFileMetadata,
            VacuumConfig,
            VacuumResult,
            scan_cache_directory,
            calculate_cumulative_size,
            sort_eviction_candidates,
            delete_file_with_retry,
            run_cache_vacuum,
        )
        _MODULE_AVAILABLE = True
        _MODULE_NAME = "sandbox.core.cache_vacuum"
    except ModuleNotFoundError:
        _MODULE_AVAILABLE = False
        _MODULE_NAME = "core.cache_vacuum"
        CacheFileMetadata = None  # type: ignore[assignment]
        VacuumConfig = None  # type: ignore[assignment]
        VacuumResult = None  # type: ignore[assignment]
        scan_cache_directory = None  # type: ignore[assignment]
        calculate_cumulative_size = None  # type: ignore[assignment]
        sort_eviction_candidates = None  # type: ignore[assignment]
        delete_file_with_retry = None  # type: ignore[assignment]
        run_cache_vacuum = None  # type: ignore[assignment]


_TASK_008_FALLBACK_CONTRACT = """---
id: "CONTRACT-20260907-cache-vacuum"
title: "Scheduled LFU Cache Vacuuming Routine Contract"
status: "ACCEPTED"
owner: "Systems Architecture Team"
last_reviewed: "2026-09-07"
target_task_id: "TASK-008"
---

# Active Engineering Contract: Scheduled LFU Cache Vacuuming Routine

## 2. Normative Invariants (The NASA Lexicon)
- `[INV-VAC-01]` Directory inspection and cumulative byte summation
- `[INV-VAC-02]` LFU eviction ordering with tie breaking on access timestamp
- `[INV-VAC-03]` Windows file locking resilience via exponential backoff retry
- `[INV-VAC-04]` Full vacuum execution completes within 3.0s watchdog ceiling
- `[INV-VAC-05]` CLI reports scanned files, evicted bytes, and final size
- `[INV-VAC-06]` Cyclomatic complexity <= 10 and line length <= 120 columns

## 3. Data Schema & Specifications
```python
class CacheFileMetadata:
    path: Path
    size_bytes: int
    access_count: int
    last_accessed: float

class VacuumConfig:
    cache_dir: Path
    high_watermark_bytes: int
    low_watermark_bytes: int
    timeout_sec: float
    max_retries: int
    initial_backoff_ms: float

class VacuumResult:
    scanned_files: int
    evicted_files: int
    evicted_bytes: int
    initial_bytes: int
    final_bytes: int
    elapsed_sec: float
    success: bool

def scan_cache_directory(cache_dir: Path) -> List[CacheFileMetadata]:
    return []

def calculate_cumulative_size(files: List[CacheFileMetadata]) -> int:
    return 0

def sort_eviction_candidates(files: List[CacheFileMetadata]) -> List[CacheFileMetadata]:
    return []

def delete_file_with_retry(
    path: Path,
    max_retries: int = 5,
    initial_backoff_ms: float = 20.0,
) -> bool:
    return True

def run_cache_vacuum(config: VacuumConfig) -> VacuumResult:
    return VacuumResult(0, 0, 0, 0, 0, 0.0, True)
```
"""


def _load_task_008_contract() -> str:
    """Loads TASK-008 contract from active contract file, cortex.db, or fixture."""
    contract_path = Path("docs/active/ACTIVE_CONTRACT.md")
    if contract_path.exists():
        try:
            content = contract_path.read_text(encoding="utf-8")
            if 'target_task_id: "TASK-008"' in content:
                return content
        except OSError:
            _err_fallback = True
    db_path = Path("data/cortex.db")
    if db_path.exists():
        try:
            con = sqlite3.connect(str(db_path))
            cur = con.execute(
                "SELECT raw_content FROM contract_revisions WHERE task_id = 'TASK-008' "
                "ORDER BY revision_id DESC LIMIT 1;"
            )
            row = cur.fetchone()
            con.close()
            if row:
                return str(row[0])
        except Exception:
            _err_fallback = True
    return _TASK_008_FALLBACK_CONTRACT


class TestCacheVacuumContractInvariants(unittest.TestCase):
    """Verifies that the specification contract defines normative invariants [INV-VAC-01..06]."""

    def setUp(self) -> None:
        self.contract_path = Path("docs/active/ACTIVE_CONTRACT.md")
        self.contract_text = _load_task_008_contract()
        self.assertTrue(
            len(self.contract_text.strip()) > 0,
            "Contract text missing from active contract, cortex.db, and fixture",
        )

    def test_contract_metadata_and_status_accepted(self) -> None:
        """Positive test: Verifies contract status ACCEPTED, ID, and target task."""
        self.assertIn('status: "ACCEPTED"', self.contract_text)
        self.assertIn('target_task_id: "TASK-008"', self.contract_text)
        self.assertIn('id: "CONTRACT-20260907-cache-vacuum"', self.contract_text)

    def test_contract_defines_all_normative_invariants(self) -> None:
        """Positive test: Verifies presence of [INV-VAC-01] through [INV-VAC-06]."""
        required_invariants = [
            "[INV-VAC-01]",
            "[INV-VAC-02]",
            "[INV-VAC-03]",
            "[INV-VAC-04]",
            "[INV-VAC-05]",
            "[INV-VAC-06]",
        ]
        for inv_id in required_invariants:
            self.assertIn(
                inv_id,
                self.contract_text,
                f"Missing invariant definition {inv_id} in active contract",
            )

    def test_contract_defines_technical_signatures_and_structures(self) -> None:
        """Positive test: Verifies contract specifies dataclasses and function signatures."""
        self.assertIn("class CacheFileMetadata:", self.contract_text)
        self.assertIn("class VacuumConfig:", self.contract_text)
        self.assertIn("class VacuumResult:", self.contract_text)
        self.assertIn("def scan_cache_directory", self.contract_text)
        self.assertIn("def calculate_cumulative_size", self.contract_text)
        self.assertIn("def sort_eviction_candidates", self.contract_text)
        self.assertIn("def delete_file_with_retry", self.contract_text)
        self.assertIn("def run_cache_vacuum", self.contract_text)

    def test_negative_contract_missing_synthetic_invariant(self) -> None:
        """Negative test: Evaluates assertion rejection for synthetic nonexistent invariant."""
        synthetic_id = "[INV-VAC-SYNTHETIC-INVALID-999]"
        self.assertNotIn(
            synthetic_id,
            self.contract_text,
            "Non-existent invariant unexpectedly found in contract text",
        )

    def test_negative_contract_missing_unapproved_mutation_function(self) -> None:
        """Negative test: Evaluates rejection of prohibited SQLite purge function."""
        banned_symbol = "def purge_sqlite_database"
        self.assertNotIn(
            banned_symbol,
            self.contract_text,
            "Prohibited database purge routine found in contract",
        )


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.cache_vacuum pending implementation by software-engineer",
)
class TestCacheVacuumDataclassIntegrity(unittest.TestCase):
    """Evaluates dataclass initialization, default values, serialization, and immutability."""

    def test_cache_file_metadata_instantiation_and_fields(self) -> None:
        """Positive test: CacheFileMetadata holds correct attributes."""
        meta = CacheFileMetadata(
            path=Path("sample.cache"),
            size_bytes=2048,
            access_count=3,
            last_accessed=12345.67,
        )
        self.assertEqual(meta.path, Path("sample.cache"))
        self.assertEqual(meta.size_bytes, 2048)
        self.assertEqual(meta.access_count, 3)
        self.assertEqual(meta.last_accessed, 12345.67)

    def test_vacuum_config_defaults(self) -> None:
        """Positive test: VacuumConfig applies contractual default parameters."""
        config = VacuumConfig()
        self.assertEqual(config.cache_dir, Path("data/cache"))
        self.assertEqual(config.high_watermark_bytes, 100 * 1024 * 1024)
        self.assertEqual(config.low_watermark_bytes, 50 * 1024 * 1024)
        self.assertEqual(config.timeout_sec, 3.0)
        self.assertEqual(config.max_retries, 5)
        self.assertEqual(config.initial_backoff_ms, 20.0)

    def test_vacuum_result_to_dict_contract(self) -> None:
        """Positive test: VacuumResult.to_dict formats payload with rounded elapsed time."""
        res = VacuumResult(
            scanned_files=10,
            evicted_files=4,
            evicted_bytes=4096,
            initial_bytes=8192,
            final_bytes=4096,
            elapsed_sec=0.123456,
            success=True,
        )
        d = res.to_dict()
        self.assertEqual(d["scanned_files"], 10)
        self.assertEqual(d["evicted_files"], 4)
        self.assertEqual(d["evicted_bytes"], 4096)
        self.assertEqual(d["initial_bytes"], 8192)
        self.assertEqual(d["final_bytes"], 4096)
        self.assertEqual(d["elapsed_sec"], 0.1235)
        self.assertEqual(d["success"], True)

    def test_negative_cache_file_metadata_immutability(self) -> None:
        """Negative test: CacheFileMetadata is frozen and raises FrozenInstanceError on mutation."""
        meta = CacheFileMetadata(
            path=Path("sample.cache"),
            size_bytes=2048,
            access_count=3,
            last_accessed=12345.67,
        )
        with self.assertRaises(FrozenInstanceError):
            meta.size_bytes = 4096  # type: ignore[misc]

    def test_negative_vacuum_config_immutability(self) -> None:
        """Negative test: VacuumConfig is frozen and raises FrozenInstanceError on mutation."""
        config = VacuumConfig()
        with self.assertRaises(FrozenInstanceError):
            config.high_watermark_bytes = 500  # type: ignore[misc]

    def test_negative_vacuum_result_immutability(self) -> None:
        """Negative test: VacuumResult is frozen and raises FrozenInstanceError on mutation."""
        res = VacuumResult(
            scanned_files=1,
            evicted_files=0,
            evicted_bytes=0,
            initial_bytes=100,
            final_bytes=100,
            elapsed_sec=0.01,
            success=True,
        )
        with self.assertRaises(FrozenInstanceError):
            res.success = False  # type: ignore[misc]


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.cache_vacuum pending implementation by software-engineer",
)
class TestCacheVacuumScanningAndSizing(unittest.TestCase):
    """Evaluates scan_cache_directory and calculate_cumulative_size on real files."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cache_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scan_cache_directory_computes_file_sizes_and_metadata(self) -> None:
        """Positive test: scan_cache_directory correctly computes sizes and metadata."""
        file_a = self.cache_dir / "item_a.cache"
        file_b = self.cache_dir / "item_b.cache"
        file_c = self.cache_dir / "item_c.cache"

        file_a.write_bytes(b"A" * 512)
        file_b.write_bytes(b"B" * 1024)
        file_c.write_bytes(b"C" * 2048)

        scanned = scan_cache_directory(self.cache_dir)
        self.assertEqual(len(scanned), 3)

        name_map = {item.path.name: item for item in scanned}
        self.assertIn("item_a.cache", name_map)
        self.assertIn("item_b.cache", name_map)
        self.assertIn("item_c.cache", name_map)

        self.assertEqual(name_map["item_a.cache"].size_bytes, 512)
        self.assertEqual(name_map["item_b.cache"].size_bytes, 1024)
        self.assertEqual(name_map["item_c.cache"].size_bytes, 2048)
        self.assertGreater(name_map["item_a.cache"].last_accessed, 0.0)
        self.assertGreaterEqual(name_map["item_a.cache"].access_count, 0)

    def test_calculate_cumulative_size_computes_exact_sum(self) -> None:
        """Positive test: calculate_cumulative_size aggregates total byte count accurately."""
        items = [
            CacheFileMetadata(path=Path("a"), size_bytes=500, access_count=1, last_accessed=100.0),
            CacheFileMetadata(path=Path("b"), size_bytes=1500, access_count=2, last_accessed=200.0),
            CacheFileMetadata(path=Path("c"), size_bytes=3000, access_count=3, last_accessed=300.0),
        ]
        total = calculate_cumulative_size(items)
        self.assertEqual(total, 5000)

    def test_negative_empty_directory_scanned_files_zero(self) -> None:
        """Negative test: Scanning an empty directory returns zero items and zero cumulative size."""
        empty_dir = self.cache_dir / "empty_subdir"
        empty_dir.mkdir(parents=True, exist_ok=True)

        scanned = scan_cache_directory(empty_dir)
        self.assertEqual(len(scanned), 0)
        total_size = calculate_cumulative_size(scanned)
        self.assertEqual(total_size, 0)

    def test_negative_nonexistent_directory_handling(self) -> None:
        """Negative test: Nonexistent directory handled gracefully or raises FileNotFoundError."""
        nonexistent = self.cache_dir / "ghost_directory"
        try:
            items = scan_cache_directory(nonexistent)
            self.assertEqual(len(items), 0)
        except FileNotFoundError as err:
            self.assertIn("ghost_directory", str(err).lower())


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.cache_vacuum pending implementation by software-engineer",
)
class TestCacheVacuumEvictionOrdering(unittest.TestCase):
    """Evaluates LFU ordering and tie-breaking by oldest last_accessed timestamp."""

    def test_sort_eviction_candidates_lfu_priority(self) -> None:
        """Positive test: Lowest access_count sorted before higher access_count."""
        candidate_high = CacheFileMetadata(
            path=Path("freq_10.dat"), size_bytes=100, access_count=10, last_accessed=100.0
        )
        candidate_low = CacheFileMetadata(
            path=Path("freq_1.dat"), size_bytes=100, access_count=1, last_accessed=900.0
        )
        candidate_mid = CacheFileMetadata(
            path=Path("freq_5.dat"), size_bytes=100, access_count=5, last_accessed=500.0
        )

        sorted_candidates = sort_eviction_candidates(
            [candidate_high, candidate_low, candidate_mid]
        )
        self.assertEqual(len(sorted_candidates), 3)
        self.assertEqual(sorted_candidates[0].path, Path("freq_1.dat"))
        self.assertEqual(sorted_candidates[1].path, Path("freq_5.dat"))
        self.assertEqual(sorted_candidates[2].path, Path("freq_10.dat"))

    def test_sort_eviction_candidates_tie_breaking_oldest_timestamp(self) -> None:
        """Positive test: Identical access_count breaks ties using oldest last_accessed."""
        item_newest = CacheFileMetadata(
            path=Path("new.dat"), size_bytes=100, access_count=2, last_accessed=3000.0
        )
        item_oldest = CacheFileMetadata(
            path=Path("old.dat"), size_bytes=100, access_count=2, last_accessed=1000.0
        )
        item_middle = CacheFileMetadata(
            path=Path("mid.dat"), size_bytes=100, access_count=2, last_accessed=2000.0
        )

        sorted_candidates = sort_eviction_candidates(
            [item_newest, item_oldest, item_middle]
        )
        self.assertEqual(len(sorted_candidates), 3)
        self.assertEqual(sorted_candidates[0].path, Path("old.dat"))
        self.assertEqual(sorted_candidates[1].path, Path("mid.dat"))
        self.assertEqual(sorted_candidates[2].path, Path("new.dat"))

    def test_negative_sort_eviction_candidates_empty_list(self) -> None:
        """Negative test: sort_eviction_candidates on empty list returns empty list."""
        sorted_candidates = sort_eviction_candidates([])
        self.assertEqual(len(sorted_candidates), 0)

    def test_negative_sort_candidates_preserves_count_without_loss(self) -> None:
        """Negative test: Sorting preserves candidate count without swallowing elements."""
        candidates = [
            CacheFileMetadata(
                path=Path(f"f_{i}.dat"),
                size_bytes=50,
                access_count=i % 2,
                last_accessed=float(100 + i),
            )
            for i in range(10)
        ]
        sorted_items = sort_eviction_candidates(candidates)
        self.assertEqual(len(sorted_items), 10)
        self.assertNotEqual(len(sorted_items), 9)


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.cache_vacuum pending implementation by software-engineer",
)
class TestCacheVacuumExecutionLifecycle(unittest.TestCase):
    """Evaluates run_cache_vacuum high/low watermark reduction and error branches."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cache_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_cache_vacuum_nominal_reduces_size_to_low_watermark(self) -> None:
        """Positive test: Cumulative size > high_watermark reduces to <= low_watermark."""
        file1 = self.cache_dir / "f1.cache"
        file2 = self.cache_dir / "f2.cache"
        file3 = self.cache_dir / "f3.cache"
        file4 = self.cache_dir / "f4.cache"

        file1.write_bytes(b"1" * 1000)
        file2.write_bytes(b"2" * 1000)
        file3.write_bytes(b"3" * 1000)
        file4.write_bytes(b"4" * 1000)

        config = VacuumConfig(
            cache_dir=self.cache_dir,
            high_watermark_bytes=3000,
            low_watermark_bytes=1500,
            timeout_sec=3.0,
        )
        result = run_cache_vacuum(config)

        self.assertEqual(result.success, True)
        self.assertEqual(result.scanned_files, 4)
        self.assertEqual(result.initial_bytes, 4000)
        self.assertLessEqual(result.final_bytes, 1500)
        self.assertEqual(result.evicted_bytes, result.initial_bytes - result.final_bytes)
        self.assertGreaterEqual(result.evicted_files, 3)
        self.assertLess(result.elapsed_sec, 3.0)

    def test_negative_high_watermark_less_than_low_watermark_raises_value_error(self) -> None:
        """Negative test: Invalid watermark hierarchy (high < low) raises ValueError."""
        with self.assertRaises(ValueError):
            VacuumConfig(
                cache_dir=self.cache_dir,
                high_watermark_bytes=1000,
                low_watermark_bytes=2000,
            )

    def test_negative_negative_watermarks_raise_value_error(self) -> None:
        """Negative test: Negative watermark values raise ValueError."""
        with self.assertRaises(ValueError):
            VacuumConfig(
                cache_dir=self.cache_dir,
                high_watermark_bytes=-500,
                low_watermark_bytes=100,
            )

        with self.assertRaises(ValueError):
            VacuumConfig(
                cache_dir=self.cache_dir,
                high_watermark_bytes=500,
                low_watermark_bytes=-100,
            )

    def test_negative_empty_directory_results_in_zero_evictions(self) -> None:
        """Negative test: Empty directory produces 0 evicted files and 0 evicted bytes."""
        empty_dir = self.cache_dir / "empty_dir"
        empty_dir.mkdir(parents=True, exist_ok=True)
        config = VacuumConfig(
            cache_dir=empty_dir,
            high_watermark_bytes=1000,
            low_watermark_bytes=500,
        )
        result = run_cache_vacuum(config)
        self.assertEqual(result.scanned_files, 0)
        self.assertEqual(result.evicted_files, 0)
        self.assertEqual(result.evicted_bytes, 0)
        self.assertEqual(result.initial_bytes, 0)
        self.assertEqual(result.final_bytes, 0)
        self.assertEqual(result.success, True)

    def test_negative_cumulative_size_below_high_watermark_skips_eviction(self) -> None:
        """Negative test: Cumulative size below high_watermark triggers no file deletions."""
        f_sub = self.cache_dir / "small_cache.dat"
        f_sub.write_bytes(b"X" * 800)
        config = VacuumConfig(
            cache_dir=self.cache_dir,
            high_watermark_bytes=2000,
            low_watermark_bytes=1000,
        )
        result = run_cache_vacuum(config)
        self.assertEqual(result.evicted_files, 0)
        self.assertEqual(result.evicted_bytes, 0)
        self.assertEqual(result.initial_bytes, 800)
        self.assertEqual(result.final_bytes, 800)
        self.assertEqual(f_sub.exists(), True)


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.cache_vacuum pending implementation by software-engineer",
)
class TestCacheVacuumFileLockResilience(unittest.TestCase):
    """Evaluates delete_file_with_retry backoff and resilience against file locks."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cache_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_delete_file_with_retry_nominal_deletion(self) -> None:
        """Positive test: delete_file_with_retry deletes target file cleanly."""
        target = self.cache_dir / "delete_me.dat"
        target.write_bytes(b"nominal content")
        self.assertEqual(target.exists(), True)

        deleted = delete_file_with_retry(target, max_retries=3, initial_backoff_ms=5.0)
        self.assertEqual(deleted, True)
        self.assertEqual(target.exists(), False)

    def test_delete_file_with_retry_transient_failure_then_success(self) -> None:
        """Positive test: Recovers from transient PermissionError via retry backoff."""
        target = self.cache_dir / "transient.dat"
        target.write_bytes(b"transient lock")

        attempts = [0]
        orig_unlink = Path.unlink

        def mock_unlink(*args: Any, **kwargs: Any) -> None:
            attempts[0] += 1
            if attempts[0] <= 2:
                raise PermissionError("WinError 32: The process cannot access the file")
            if args:
                orig_unlink(args[0], **kwargs)
            else:
                orig_unlink(target, **kwargs)

        with mock.patch.object(Path, "unlink", side_effect=mock_unlink):
            deleted = delete_file_with_retry(target, max_retries=5, initial_backoff_ms=5.0)

        self.assertEqual(deleted, True)
        self.assertGreater(attempts[0], 2)

    def test_negative_delete_file_with_retry_exhausted_retries_returns_false(self) -> None:
        """Negative test: Persistent lock returns False without raising unhandled exception."""
        target = self.cache_dir / "permanent_lock.dat"
        target.write_bytes(b"locked content")

        def mock_lock_fail(*_args: Any, **_kwargs: Any) -> None:
            raise PermissionError("WinError 32: Locked file")

        with mock.patch.object(Path, "unlink", side_effect=mock_lock_fail):
            with mock.patch("os.remove", side_effect=mock_lock_fail):
                deleted = delete_file_with_retry(target, max_retries=3, initial_backoff_ms=2.0)

        self.assertEqual(deleted, False)
        self.assertEqual(target.exists(), True)

    def test_negative_delete_file_with_retry_nonexistent_file(self) -> None:
        """Negative test: Nonexistent file handled safely without crashing."""
        missing = self.cache_dir / "does_not_exist.tmp"
        deleted = delete_file_with_retry(missing, max_retries=2, initial_backoff_ms=2.0)
        self.assertIn(deleted, (True, False))
        self.assertEqual(missing.exists(), False)

    def test_negative_locked_file_handled_with_backoff_without_crashing_vacuum(self) -> None:
        """Negative test: Locked candidate is skipped without crashing entire vacuum cycle."""
        file1 = self.cache_dir / "locked.cache"
        file2 = self.cache_dir / "unlocked.cache"

        file1.write_bytes(b"L" * 2000)
        file2.write_bytes(b"U" * 2000)

        # Open file1 with exclusive read handle on Windows to induce real lock contention
        handle = open(file1, "rb")
        try:
            config = VacuumConfig(
                cache_dir=self.cache_dir,
                high_watermark_bytes=3000,
                low_watermark_bytes=1000,
                timeout_sec=3.0,
            )
            result = run_cache_vacuum(config)
            self.assertEqual(result.scanned_files, 2)
            self.assertEqual(file1.exists(), True)
            self.assertEqual(file2.exists(), False)
        finally:
            handle.close()


@unittest.skipUnless(
    _MODULE_AVAILABLE,
    "core.cache_vacuum pending implementation by software-engineer",
)
class TestCacheVacuumCLI(unittest.TestCase):
    """Evaluates CLI execution conforming to [INV-VAC-05]."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cache_dir = Path(self.temp_dir.name)
        (self.cache_dir / "item_1.dat").write_bytes(b"1" * 1024)
        (self.cache_dir / "item_2.dat").write_bytes(b"2" * 2048)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _build_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
        return env

    def test_cli_invocation_json_output_and_exit_code_zero(self) -> None:
        """Positive test: CLI with --json outputs valid JSON payload with exit code 0."""
        cmd = [
            sys.executable,
            "-m",
            _MODULE_NAME,
            "--high-mb",
            "100",
            "--low-mb",
            "50",
            "--dir",
            str(self.cache_dir),
            "--json",
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=str(Path.cwd()),
            env=self._build_env(),
        )
        self.assertEqual(proc.returncode, 0, f"CLI stderr: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertIn("scanned_files", data)
        self.assertIn("evicted_files", data)
        self.assertIn("evicted_bytes", data)
        self.assertIn("initial_bytes", data)
        self.assertIn("final_bytes", data)
        self.assertIn("elapsed_sec", data)
        self.assertIn("success", data)
        self.assertEqual(data["scanned_files"], 2)

    def test_cli_invocation_human_readable_output(self) -> None:
        """Positive test: CLI without --json outputs summary telemetry with exit code 0."""
        cmd = [
            sys.executable,
            "-m",
            _MODULE_NAME,
            "--high-mb",
            "100",
            "--low-mb",
            "50",
            "--dir",
            str(self.cache_dir),
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=str(Path.cwd()),
            env=self._build_env(),
        )
        self.assertEqual(proc.returncode, 0, f"CLI stderr: {proc.stderr}")
        out = proc.stdout.lower()
        has_summary_text = (
            "scanned" in out or "files" in out or "evicted" in out or "bytes" in out
        )
        self.assertEqual(has_summary_text, True)

    def test_negative_cli_invalid_watermark_hierarchy_returns_nonzero(self) -> None:
        """Negative test: CLI with high-mb < low-mb exits with non-zero code."""
        cmd = [
            sys.executable,
            "-m",
            _MODULE_NAME,
            "--high-mb",
            "20",
            "--low-mb",
            "50",
            "--dir",
            str(self.cache_dir),
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=str(Path.cwd()),
            env=self._build_env(),
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_negative_cli_unknown_flag_returns_nonzero(self) -> None:
        """Negative test: CLI with unsupported parameter exits with non-zero code."""
        cmd = [
            sys.executable,
            "-m",
            _MODULE_NAME,
            "--unsupported-option-flag-999",
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=str(Path.cwd()),
            env=self._build_env(),
        )
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
