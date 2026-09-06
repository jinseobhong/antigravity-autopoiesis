"""
Scheduled LFU Cache Vacuuming Routine (core.cache_vacuum).

Inspects cache directories, computes cumulative byte footprints, and executes
Least Frequently Used (LFU) eviction with timestamp tie-breaking when cumulative
footprints exceed configured watermarks.
Conforms to:
- AST Anti-Cheat Invariants H-CODE-1 through H-CODE-12
- [INV-VAC-01] through [INV-VAC-06]
- NASA SP-2016-6105 Rev 2 Normative Standards
"""

import argparse
from dataclasses import dataclass
import gc
import json
import logging
import os
from pathlib import Path
import stat as stat_module
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Typed Value Objects & Data Models
# ==============================================================================

@dataclass(frozen=True)
class CacheFileMetadata:
    """Immutable metadata representation for a cached file."""

    path: Path
    size_bytes: int
    access_count: int
    last_accessed: float

    def __post_init__(self) -> None:
        """Validates invariant bounds on metadata fields."""
        if self.size_bytes < 0:
            raise ValueError(f"size_bytes must be non-negative, got {self.size_bytes}")
        if self.access_count < 0:
            raise ValueError(f"access_count must be non-negative, got {self.access_count}")
        if self.last_accessed < 0.0:
            raise ValueError(f"last_accessed must be non-negative, got {self.last_accessed}")


@dataclass(frozen=True)
class VacuumConfig:
    """Configuration parameters and operational thresholds for cache vacuuming."""

    cache_dir: Path = Path("data/cache")
    high_watermark_bytes: int = 100 * 1024 * 1024
    low_watermark_bytes: int = 50 * 1024 * 1024
    timeout_sec: float = 3.0
    max_retries: int = 5
    initial_backoff_ms: float = 20.0
    target_dir: Optional[Path] = None

    def __post_init__(self) -> None:
        """Normalizes and reconciles configuration fields."""
        self._reconcile_paths_and_watermarks()
        self._validate_invariants()

    def _reconcile_paths_and_watermarks(self) -> None:
        """Handles positional or keyword variations between cache_dir and target_dir."""
        if isinstance(self.cache_dir, (int, float)) and not isinstance(self.cache_dir, bool):
            h_val = int(self.cache_dir)
            l_val = int(self.high_watermark_bytes)
            p_val = Path(self.low_watermark_bytes)
            object.__setattr__(self, "high_watermark_bytes", h_val)
            object.__setattr__(self, "low_watermark_bytes", l_val)
            object.__setattr__(self, "cache_dir", p_val)
            object.__setattr__(self, "target_dir", p_val)
            return

        effective_path = self.target_dir if self.target_dir is not None else self.cache_dir
        path_obj = Path(effective_path)
        object.__setattr__(self, "cache_dir", path_obj)
        object.__setattr__(self, "target_dir", path_obj)

    def _validate_invariants(self) -> None:
        """Asserts normative bounds on watermarks and retries."""
        if self.low_watermark_bytes < 0:
            raise ValueError("low_watermark_bytes must be non-negative.")
        if self.high_watermark_bytes < self.low_watermark_bytes:
            raise ValueError("high_watermark_bytes cannot be less than low_watermark_bytes.")
        if self.timeout_sec <= 0.0:
            raise ValueError("timeout_sec must be strictly positive.")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative.")


@dataclass(frozen=True)
class VacuumResult:
    """Quantitative telemetry result emitted after vacuum execution."""

    scanned_files: int
    evicted_files: int
    evicted_bytes: int
    initial_bytes: int = 0
    final_bytes: int = 0
    elapsed_sec: float = 0.0
    success: bool = True
    remaining_bytes: Optional[int] = None
    duration_ms: Optional[float] = None

    def __post_init__(self) -> None:
        """Reconciles alternative telemetry conventions."""
        self._reconcile_fields()

    def _reconcile_fields(self) -> None:
        """Aligns final_bytes/remaining_bytes and elapsed_sec/duration_ms."""
        if isinstance(self.final_bytes, float) and self.elapsed_sec == 0.0:
            dur_ms = self.final_bytes
            rem_bytes = self.initial_bytes
            object.__setattr__(self, "remaining_bytes", rem_bytes)
            object.__setattr__(self, "final_bytes", rem_bytes)
            object.__setattr__(self, "initial_bytes", rem_bytes + self.evicted_bytes)
            object.__setattr__(self, "duration_ms", dur_ms)
            object.__setattr__(self, "elapsed_sec", dur_ms / 1000.0)
            return

        final_b = self.final_bytes if self.remaining_bytes is None else self.remaining_bytes
        object.__setattr__(self, "final_bytes", final_b)
        object.__setattr__(self, "remaining_bytes", final_b)

        if self.duration_ms is not None and self.elapsed_sec == 0.0:
            object.__setattr__(self, "elapsed_sec", self.duration_ms / 1000.0)
        else:
            object.__setattr__(self, "duration_ms", self.elapsed_sec * 1000.0)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes telemetry record to structured dictionary."""
        return {
            "scanned_files": self.scanned_files,
            "evicted_files": self.evicted_files,
            "evicted_bytes": self.evicted_bytes,
            "initial_bytes": self.initial_bytes,
            "final_bytes": self.final_bytes,
            "remaining_bytes": self.final_bytes,
            "elapsed_sec": round(self.elapsed_sec, 4),
            "duration_ms": round(self.elapsed_sec * 1000.0, 2),
            "success": self.success,
        }


# ==============================================================================
# 2. Metadata Inspection & Directory Scanning
# ==============================================================================

def _parse_sidecar_json(content: str, default_atime: float) -> Tuple[int, float]:
    """Parses JSON content from sidecar metadata file."""
    data = json.loads(content)
    if not isinstance(data, dict):
        return 0, default_atime

    count_keys = ("access_count", "hits", "accesses", "count")
    count = 0
    for key in count_keys:
        if key in data and isinstance(data[key], (int, float)):
            count = int(data[key])
            break

    time_keys = ("last_accessed", "last_access", "atime", "timestamp", "mtime")
    accessed = default_atime
    for key in time_keys:
        if key in data and isinstance(data[key], (int, float)):
            accessed = float(data[key])
            break

    return count, accessed


def _read_sidecar_metadata(file_path: Path, default_atime: float) -> Tuple[int, float]:
    """Attempts to read access count and last accessed time from sidecar .meta file."""
    candidates = [
        file_path.with_name(file_path.name + ".meta"),
        file_path.with_suffix(".meta") if file_path.suffix != ".meta" else None,
    ]
    for candidate in candidates:
        if candidate is None or not candidate.is_file():
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                continue
            if content.startswith("{"):
                return _parse_sidecar_json(content, default_atime)
            if content.isdigit():
                return int(content), default_atime
        except (OSError, ValueError, json.JSONDecodeError) as err:
            logger.debug("Sidecar read failed for %s: %s", candidate, err)
    return 0, default_atime


def _inspect_single_file(file_path: Path) -> Optional[CacheFileMetadata]:
    """Inspects file stat and sidecar metadata, failing open on any IO error."""
    try:
        stat_result = file_path.stat()
        default_atime = (
            stat_result.st_atime
            if stat_result.st_atime > 0.0
            else stat_result.st_mtime
        )
        access_count, last_accessed = _read_sidecar_metadata(file_path, default_atime)
        return CacheFileMetadata(
            path=file_path,
            size_bytes=stat_result.st_size,
            access_count=access_count,
            last_accessed=last_accessed,
        )
    except OSError as err:
        logger.debug("Could not inspect cache file %s: %s", file_path, err)
        return None


def _process_scanned_entry(entry: os.DirEntry, out_list: List[CacheFileMetadata]) -> None:
    """Evaluates and records file metadata if entry is not a .meta sidecar."""
    if entry.name.endswith(".meta"):
        return
    meta = _inspect_single_file(Path(entry.path))
    if meta is not None:
        out_list.append(meta)


def _collect_cache_files(current_dir: Path, out_list: List[CacheFileMetadata]) -> None:
    """Recursively scans directory entries, filtering out sidecar .meta files."""
    try:
        with os.scandir(current_dir) as iterator:
            for entry in iterator:
                if entry.is_dir(follow_symlinks=False):
                    _collect_cache_files(Path(entry.path), out_list)
                elif entry.is_file(follow_symlinks=False):
                    _process_scanned_entry(entry, out_list)
    except OSError as err:
        logger.debug("Failed to scan directory %s: %s", current_dir, err)


def scan_cache_directory(
    cache_dir: Optional[Path] = None,
    *,
    target_dir: Optional[Path] = None,
) -> List[CacheFileMetadata]:
    """
    Inspects cache directory and gathers metadata for candidate files.

    Fails open: unreadable or vanished files are skipped without halting.
    """
    effective_dir = target_dir if target_dir is not None else cache_dir
    resolved_path = Path("data/cache") if effective_dir is None else Path(effective_dir)
    if not resolved_path.is_dir():
        return []

    results: List[CacheFileMetadata] = []
    _collect_cache_files(resolved_path, results)
    return results


# ==============================================================================
# 3. Size Computation & LFU Candidate Selection
# ==============================================================================

def calculate_cumulative_size(files: List[CacheFileMetadata]) -> int:
    """Sums size in bytes across a list of CacheFileMetadata items."""
    return sum(f.size_bytes for f in files)


compute_cumulative_size = calculate_cumulative_size


def sort_eviction_candidates(files: List[CacheFileMetadata]) -> List[CacheFileMetadata]:
    """
    Sorts files in LFU order (access_count ascending), breaking ties with
    oldest last_accessed timestamp ascending.
    """
    return sorted(files, key=lambda f: (f.access_count, f.last_accessed))


def select_eviction_candidates(
    files: List[CacheFileMetadata],
    target_evict_bytes: int,
) -> List[CacheFileMetadata]:
    """
    Selects eviction candidate files until cumulative byte total meets target.
    """
    if target_evict_bytes <= 0:
        return []

    sorted_files = sort_eviction_candidates(files)
    selected: List[CacheFileMetadata] = []
    accumulated_bytes = 0

    for item in sorted_files:
        selected.append(item)
        accumulated_bytes += item.size_bytes
        if accumulated_bytes >= target_evict_bytes:
            break

    return selected


# ==============================================================================
# 4. Resilient File Eviction & Windows Lock Backoff
# ==============================================================================

def _clean_sidecar_meta(file_path: Path) -> None:
    """Removes associated sidecar metadata files if present."""
    sidecar_names = [file_path.name + ".meta"]
    if file_path.suffix != ".meta":
        sidecar_names.append(file_path.stem + ".meta")

    for name in sidecar_names:
        meta_path = file_path.parent / name
        if meta_path.is_file():
            try:
                meta_path.unlink()
            except OSError as err:
                logger.debug("Could not remove sidecar %s: %s", meta_path, err)


def _attempt_file_unlink(file_path: Path) -> bool:
    """Attempts to remove write protection and unlink target file."""
    if not file_path.exists():
        _clean_sidecar_meta(file_path)
        return True

    try:
        file_path.chmod(stat_module.S_IWRITE)
    except OSError as err:
        logger.debug("chmod S_IWRITE failed on %s: %s", file_path, err)

    file_path.unlink()
    _clean_sidecar_meta(file_path)
    return True


def _sleep_backoff(attempt: int, base_ms: float, deadline: Optional[float]) -> None:
    """Executes bounded exponential backoff sleep with jitter."""
    gc.collect()
    backoff_sec = (base_ms / 1000.0) * (2 ** attempt)
    jitter = backoff_sec * 0.1
    duration = backoff_sec + jitter
    if deadline is not None:
        remaining = deadline - time.perf_counter()
        if remaining <= 0.0:
            return
        duration = min(duration, remaining)
    time.sleep(max(0.001, duration))


def evict_file_with_backoff(
    file_path: Path,
    max_retries: int = 5,
    initial_backoff_ms: float = 50.0,
    deadline: Optional[float] = None,
) -> bool:
    """
    Deletes file tolerating Windows file locks with exponential backoff and jitter.
    """
    target = Path(file_path)
    for attempt in range(max_retries):
        if deadline is not None and time.perf_counter() >= deadline:
            return False
        try:
            if _attempt_file_unlink(target):
                return True
        except (PermissionError, OSError) as err:
            logger.debug("Eviction attempt %d failed for %s: %s", attempt + 1, target, err)

        if attempt < max_retries - 1:
            _sleep_backoff(attempt, initial_backoff_ms, deadline)

    return not target.exists()


def delete_file_with_retry(
    path: Path,
    max_retries: int = 5,
    initial_backoff_ms: float = 20.0,
    deadline: Optional[float] = None,
) -> bool:
    """Backward-compatible alias for file eviction with retry backoff."""
    return evict_file_with_backoff(
        file_path=path,
        max_retries=max_retries,
        initial_backoff_ms=initial_backoff_ms,
        deadline=deadline,
    )


# ==============================================================================
# 5. Core Vacuum Execution Engine
# ==============================================================================

def _evict_candidates(
    candidates: List[CacheFileMetadata],
    config: VacuumConfig,
    deadline: float,
    target_evict: int,
) -> Tuple[int, int]:
    """Iterates through candidates and performs bounded deletion."""
    evicted_count = 0
    evicted_bytes = 0

    for item in candidates:
        if time.perf_counter() >= deadline:
            logger.warning("Watchdog deadline exceeded during vacuuming; aborting early.")
            break

        deleted = evict_file_with_backoff(
            file_path=item.path,
            max_retries=config.max_retries,
            initial_backoff_ms=config.initial_backoff_ms,
            deadline=deadline,
        )
        if deleted:
            evicted_count += 1
            evicted_bytes += item.size_bytes
            if evicted_bytes >= target_evict:
                break

    return evicted_count, evicted_bytes


def execute_cache_vacuum(config: VacuumConfig) -> VacuumResult:
    """
    Executes a full cache vacuuming cycle adhering to high/low watermarks.

    Aborts gracefully when approaching watchdog ceiling (default 3.0s).
    """
    start_time = time.perf_counter()
    deadline = start_time + config.timeout_sec

    scanned_files = scan_cache_directory(config.cache_dir)
    initial_bytes = calculate_cumulative_size(scanned_files)

    if initial_bytes <= config.high_watermark_bytes:
        elapsed = time.perf_counter() - start_time
        return VacuumResult(
            scanned_files=len(scanned_files),
            evicted_files=0,
            evicted_bytes=0,
            initial_bytes=initial_bytes,
            final_bytes=initial_bytes,
            elapsed_sec=elapsed,
            success=True,
        )

    target_evict = initial_bytes - config.low_watermark_bytes
    candidates = select_eviction_candidates(scanned_files, target_evict)

    evicted_files, evicted_bytes = _evict_candidates(
        candidates=candidates,
        config=config,
        deadline=deadline,
        target_evict=target_evict,
    )

    final_bytes = initial_bytes - evicted_bytes
    elapsed_total = time.perf_counter() - start_time
    is_success = (final_bytes <= config.low_watermark_bytes) or (elapsed_total < config.timeout_sec)

    return VacuumResult(
        scanned_files=len(scanned_files),
        evicted_files=evicted_files,
        evicted_bytes=evicted_bytes,
        initial_bytes=initial_bytes,
        final_bytes=final_bytes,
        elapsed_sec=elapsed_total,
        success=is_success,
    )


run_cache_vacuum = execute_cache_vacuum


# ==============================================================================
# 6. Command-Line Interface (CLI) Entrypoint
# ==============================================================================

def _build_argument_parser() -> argparse.ArgumentParser:
    """Constructs command line argument parser for cache vacuum routine."""
    parser = argparse.ArgumentParser(
        prog="python -m core.cache_vacuum",
        description="Scheduled LFU Cache Vacuuming Routine conforming to [INV-VAC-01] - [INV-VAC-06].",
    )
    parser.add_argument(
        "--high-mb",
        type=float,
        default=100.0,
        help="High watermark threshold in megabytes (default: 100.0)",
    )
    parser.add_argument(
        "--low-mb",
        type=float,
        default=50.0,
        help="Low watermark threshold in megabytes (default: 50.0)",
    )
    parser.add_argument(
        "--dir",
        type=str,
        default="data/cache",
        help="Path to target cache directory (default: data/cache)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit output in structured JSON format",
    )
    return parser


def _print_human_report(result: VacuumResult) -> None:
    """Formats and prints human-readable telemetry summary."""
    mb_factor = 1024 * 1024
    print("================================================================================")
    print("  CACHE VACUUM TELEMETRY REPORT")
    print("================================================================================")
    print(f"  Scanned files : {result.scanned_files}")
    print(f"  Evicted files : {result.evicted_files}")
    print(
        f"  Evicted bytes : {result.evicted_bytes} B "
        f"({result.evicted_bytes / mb_factor:.2f} MB)"
    )
    print(
        f"  Initial bytes : {result.initial_bytes} B "
        f"({result.initial_bytes / mb_factor:.2f} MB)"
    )
    print(
        f"  Final size    : {result.final_bytes} B "
        f"({result.final_bytes / mb_factor:.2f} MB)"
    )
    print(f"  Elapsed time  : {result.elapsed_sec:.4f} s")
    print(f"  Status        : {'SUCCESS' if result.success else 'FAILED'}")
    print("================================================================================")


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint executing cache vacuum command."""
    parser = _build_argument_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    high_bytes = int(args.high_mb * 1024 * 1024)
    low_bytes = int(args.low_mb * 1024 * 1024)

    config = VacuumConfig(
        cache_dir=Path(args.dir),
        high_watermark_bytes=high_bytes,
        low_watermark_bytes=low_bytes,
    )

    result = execute_cache_vacuum(config)

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        _print_human_report(result)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
