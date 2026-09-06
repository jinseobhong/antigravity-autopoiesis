"""
Tri-Domain Document Archiving and Event-Driven Eviction Engine (core.cortex_docs).

Implements segregated storage across contract_revisions, state_revisions, and
architecture_revisions in cortex.db with SQLite WAL mode, SHA-256 integrity,
and atomic file replacements.
"""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_CORTEX_DB_PATH = Path("data/cortex.db")
LEGACY_CORTEX_DB_PATH = Path(".agents/knowledge/cortex.db")
DEFAULT_SPOOL_PATH = Path("data/spool/cortex_spool.jsonl")


def resolve_cortex_db_path(configured_path: Optional[Path] = None, check_exists: bool = True) -> Path:
    """Resolves canonical cortex.db path with backward-compatible legacy fallback."""
    if configured_path is not None:
        return Path(configured_path)
    if check_exists:
        if DEFAULT_CORTEX_DB_PATH.exists():
            return DEFAULT_CORTEX_DB_PATH
        if LEGACY_CORTEX_DB_PATH.exists():
            return LEGACY_CORTEX_DB_PATH
    return DEFAULT_CORTEX_DB_PATH


@dataclass(frozen=True)
class ContractRevision:
    """Immutable record of an archived engineering binding contract."""

    revision_id: str
    contract_id: str
    task_id: str
    title: str
    version: int
    status: str
    content_hash: str
    raw_content: str
    frontmatter: Dict[str, str]
    archived_reason: str
    created_at: str
    archived_at: str


@dataclass(frozen=True)
class StateRevision:
    """Immutable record of an archived sprint and task state ledger."""

    revision_id: str
    state_id: str
    sprint_label: str
    active_tasks_count: int
    content_hash: str
    raw_content: str
    frontmatter: Dict[str, str]
    transition_trigger: str
    created_at: str
    archived_at: str


@dataclass(frozen=True)
class ArchitectureRevision:
    """Immutable record of an archived physical architecture blueprint."""

    revision_id: str
    blueprint_id: str
    version: str
    title: str
    content_hash: str
    raw_content: str
    frontmatter: Dict[str, str]
    ratification_token: str
    created_at: str
    archived_at: str


@dataclass(frozen=True)
class DomainEvictionResult:
    """Outcome of an event-driven rolling eviction pass."""

    domain: str
    evicted_files: List[str]
    retained_files: List[str]
    records_created: List[str]
    status: str


@dataclass(frozen=True)
class RestoreResult:
    """Outcome of a document restoration request."""

    domain: str
    entity_id: str
    target_path: str
    content_hash: str
    verified: bool
    status: str


def compute_sha256(content: str) -> str:
    """Computes a hexadecimal SHA-256 digest for UTF-8 encoded text."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parse_frontmatter(content: str) -> Dict[str, str]:
    """Extracts top-level key-value metadata from a markdown frontmatter block."""
    stripped_content = content.lstrip("\ufeff")
    if not stripped_content.startswith("---"):
        return {}

    parts = stripped_content.split("---", 2)
    if len(parts) < 3:
        return {}

    metadata: Dict[str, str] = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        clean_key = key.strip().strip('"').strip("'")
        clean_val = val.strip().strip('"').strip("'")
        if "#" in clean_val:
            clean_val = clean_val.split("#", 1)[0].strip().strip('"').strip("'")
        metadata[clean_key] = clean_val
    return metadata


def _spool_record(record: Dict[str, Any], spool_path: Optional[Path] = None) -> bool:
    """Appends an uncommitted record to an in-memory or on-disk ring buffer spool."""
    target_spool = Path(spool_path or DEFAULT_SPOOL_PATH)
    try:
        os.makedirs(target_spool.parent, exist_ok=True)
        with open(target_spool, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Opens a SQLite connection configured with WAL and busy timeout pragmas."""
    db_path = Path(db_path)
    os.makedirs(db_path.parent, exist_ok=True)
    con = sqlite3.connect(str(db_path), timeout=5.0)
    con.row_factory = sqlite3.Row
    with con:
        con.execute("PRAGMA journal_mode = WAL;")
        con.execute("PRAGMA busy_timeout = 5000;")
        con.execute("PRAGMA synchronous = NORMAL;")
    return con


def init_cortex_db(db_path: Optional[Path] = None) -> Path:
    """Initializes domain-segregated tables and FTS virtual indexes in cortex.db."""
    target_path = resolve_cortex_db_path(db_path)
    con = get_connection(target_path)
    try:
        with con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS contract_revisions (
                    revision_id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    raw_content TEXT NOT NULL,
                    frontmatter_json TEXT NOT NULL,
                    archived_reason TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS state_revisions (
                    revision_id TEXT PRIMARY KEY,
                    state_id TEXT NOT NULL,
                    sprint_label TEXT NOT NULL,
                    active_tasks_count INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    raw_content TEXT NOT NULL,
                    frontmatter_json TEXT NOT NULL,
                    transition_trigger TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS architecture_revisions (
                    revision_id TEXT PRIMARY KEY,
                    blueprint_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    raw_content TEXT NOT NULL,
                    frontmatter_json TEXT NOT NULL,
                    ratification_token TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            con.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_archive_search USING fts5(
                    domain_type,
                    entity_id,
                    title,
                    raw_content
                );
                """
            )
    finally:
        con.close()
    return target_path


def _execute_with_retry(
    db_path: Path,
    operation_name: str,
    sql: str,
    params: Tuple[Any, ...],
    spool_payload: Dict[str, Any],
) -> bool:
    """Executes a SQL modification with exponential backoff retry on lock contention."""
    max_retries = 5
    base_delay = 0.05
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            con = get_connection(db_path)
            try:
                with con:
                    con.execute(sql, params)
                return True
            finally:
                con.close()
        except sqlite3.OperationalError as err:
            last_error = err
            if "locked" in str(err) or "busy" in str(err):
                jitter = random.uniform(0.01, 0.05)
                time.sleep(base_delay * (2 ** attempt) + jitter)
                continue
            raise

    _spool_record(spool_payload)
    if last_error:
        return False
    return False


def _collect_domain_files(target_dir: Path) -> List[Path]:
    """Collects markdown files sorted chronologically by modification time (oldest first)."""
    target_dir = Path(target_dir)
    if not target_dir.exists():
        return []
    files = [p for p in target_dir.glob("*.md") if not p.name.startswith(".")]
    files.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return files


def trigger_contract_eviction(
    contracts_dir: Path,
    capacity: int = 5,
    db_path: Optional[Path] = None,
    archived_reason: str = "Capacity ceiling eviction on contract transition",
) -> DomainEvictionResult:
    """Evicts contracts exceeding capacity into contract_revisions and unlinks them from disk."""
    target_db = init_cortex_db(db_path)
    files = _collect_domain_files(contracts_dir)

    if len(files) <= capacity:
        retained = [f.name for f in files]
        return DomainEvictionResult(
            domain="contract",
            evicted_files=[],
            retained_files=retained,
            records_created=[],
            status="WITHIN_CAPACITY",
        )

    evict_candidates = files[: len(files) - capacity]
    retained_files = [f.name for f in files[len(files) - capacity :]]
    evicted_names: List[str] = []
    created_ids: List[str] = []

    for file_path in evict_candidates:
        content = file_path.read_text(encoding="utf-8")
        meta = parse_frontmatter(content)
        content_hash = compute_sha256(content)
        rev_id = f"REV-CONTRACT-{int(time.time()*1000)}-{file_path.stem}"
        contract_id = meta.get("id", file_path.stem)
        task_id = meta.get("target_task_id", meta.get("task_id", "TASK-UNASSIGNED"))
        title = meta.get("title", file_path.stem)
        version = int(meta.get("version", "1")) if meta.get("version", "").isdigit() else 1
        status = meta.get("status", "ARCHIVED")

        sql = """
            INSERT INTO contract_revisions (
                revision_id, contract_id, task_id, title, version,
                status, content_hash, raw_content, frontmatter_json, archived_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            rev_id,
            contract_id,
            task_id,
            title,
            version,
            status,
            content_hash,
            content,
            json.dumps(meta, ensure_ascii=False),
            archived_reason,
        )
        spool_data = {
            "table": "contract_revisions",
            "rev_id": rev_id,
            "entity_id": contract_id,
            "content_hash": content_hash,
        }

        success = _execute_with_retry(target_db, "insert_contract", sql, params, spool_data)
        if success:
            # Sync to FTS index
            fts_sql = "INSERT INTO fts_archive_search (domain_type, entity_id, title, raw_content) VALUES (?, ?, ?, ?);"
            _execute_with_retry(
                target_db,
                "fts_sync",
                fts_sql,
                ("contract", contract_id, title, content),
                spool_data,
            )
            file_path.unlink(missing_ok=True)
            evicted_names.append(file_path.name)
            created_ids.append(rev_id)

    return DomainEvictionResult(
        domain="contract",
        evicted_files=evicted_names,
        retained_files=retained_files,
        records_created=created_ids,
        status="EVICTION_EXECUTED",
    )


def trigger_state_eviction(
    states_dir: Path,
    capacity: int = 5,
    db_path: Optional[Path] = None,
    transition_trigger: str = "State ledger task lifecycle transition",
) -> DomainEvictionResult:
    """Evicts state snapshots exceeding capacity into state_revisions and unlinks them from disk."""
    target_db = init_cortex_db(db_path)
    files = _collect_domain_files(states_dir)

    if len(files) <= capacity:
        retained = [f.name for f in files]
        return DomainEvictionResult(
            domain="state",
            evicted_files=[],
            retained_files=retained,
            records_created=[],
            status="WITHIN_CAPACITY",
        )

    evict_candidates = files[: len(files) - capacity]
    retained_files = [f.name for f in files[len(files) - capacity :]]
    evicted_names: List[str] = []
    created_ids: List[str] = []

    for file_path in evict_candidates:
        content = file_path.read_text(encoding="utf-8")
        meta = parse_frontmatter(content)
        content_hash = compute_sha256(content)
        rev_id = f"REV-STATE-{int(time.time()*1000)}-{file_path.stem}"
        state_id = meta.get("id", file_path.stem)
        sprint_label = meta.get("sprint_horizon", meta.get("title", "Sprint-Active"))
        active_count = int(meta.get("active_tasks_count", "0")) if meta.get("active_tasks_count", "").isdigit() else 0

        sql = """
            INSERT INTO state_revisions (
                revision_id, state_id, sprint_label, active_tasks_count,
                content_hash, raw_content, frontmatter_json, transition_trigger
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            rev_id,
            state_id,
            sprint_label,
            active_count,
            content_hash,
            content,
            json.dumps(meta, ensure_ascii=False),
            transition_trigger,
        )
        spool_data = {
            "table": "state_revisions",
            "rev_id": rev_id,
            "entity_id": state_id,
            "content_hash": content_hash,
        }

        success = _execute_with_retry(target_db, "insert_state", sql, params, spool_data)
        if success:
            fts_sql = "INSERT INTO fts_archive_search (domain_type, entity_id, title, raw_content) VALUES (?, ?, ?, ?);"
            _execute_with_retry(
                target_db,
                "fts_sync",
                fts_sql,
                ("state", state_id, sprint_label, content),
                spool_data,
            )
            file_path.unlink(missing_ok=True)
            evicted_names.append(file_path.name)
            created_ids.append(rev_id)

    return DomainEvictionResult(
        domain="state",
        evicted_files=evicted_names,
        retained_files=retained_files,
        records_created=created_ids,
        status="EVICTION_EXECUTED",
    )


def trigger_architecture_eviction(
    arch_dir: Path,
    capacity: int = 5,
    db_path: Optional[Path] = None,
    ratification_token: str = "SOVEREIGN_RATIFIED_V2",
) -> DomainEvictionResult:
    """Evicts blueprint revisions exceeding capacity into architecture_revisions."""
    target_db = init_cortex_db(db_path)
    files = _collect_domain_files(arch_dir)

    if len(files) <= capacity:
        retained = [f.name for f in files]
        return DomainEvictionResult(
            domain="architecture",
            evicted_files=[],
            retained_files=retained,
            records_created=[],
            status="WITHIN_CAPACITY",
        )

    evict_candidates = files[: len(files) - capacity]
    retained_files = [f.name for f in files[len(files) - capacity :]]
    evicted_names: List[str] = []
    created_ids: List[str] = []

    for file_path in evict_candidates:
        content = file_path.read_text(encoding="utf-8")
        meta = parse_frontmatter(content)
        content_hash = compute_sha256(content)
        rev_id = f"REV-ARCH-{int(time.time()*1000)}-{file_path.stem}"
        blueprint_id = meta.get("id", file_path.stem)
        version = meta.get("version", "v1.0")
        title = meta.get("title", file_path.stem)

        sql = """
            INSERT INTO architecture_revisions (
                revision_id, blueprint_id, version, title,
                content_hash, raw_content, frontmatter_json, ratification_token
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            rev_id,
            blueprint_id,
            version,
            title,
            content_hash,
            content,
            json.dumps(meta, ensure_ascii=False),
            ratification_token,
        )
        spool_data = {
            "table": "architecture_revisions",
            "rev_id": rev_id,
            "entity_id": blueprint_id,
            "content_hash": content_hash,
        }

        success = _execute_with_retry(target_db, "insert_arch", sql, params, spool_data)
        if success:
            fts_sql = "INSERT INTO fts_archive_search (domain_type, entity_id, title, raw_content) VALUES (?, ?, ?, ?);"
            _execute_with_retry(
                target_db,
                "fts_sync",
                fts_sql,
                ("architecture", blueprint_id, title, content),
                spool_data,
            )
            file_path.unlink(missing_ok=True)
            evicted_names.append(file_path.name)
            created_ids.append(rev_id)

    return DomainEvictionResult(
        domain="architecture",
        evicted_files=evicted_names,
        retained_files=retained_files,
        records_created=created_ids,
        status="EVICTION_EXECUTED",
    )


def restore_archive(
    domain: str,
    entity_id: str,
    target_path: Path,
    db_path: Optional[Path] = None,
) -> RestoreResult:
    """Restores an archived entity from cortex.db to disk with cryptographic SHA-256 verification."""
    target_path = Path(target_path)
    target_db = init_cortex_db(db_path)
    domain_table_map = {
        "contract": ("contract_revisions", "contract_id"),
        "state": ("state_revisions", "state_id"),
        "architecture": ("architecture_revisions", "blueprint_id"),
    }

    if domain not in domain_table_map:
        return RestoreResult(
            domain=domain,
            entity_id=entity_id,
            target_path=str(target_path),
            content_hash="",
            verified=False,
            status="INVALID_DOMAIN",
        )

    table_name, id_col = domain_table_map[domain]
    con = get_connection(target_db)
    row = None
    try:
            query = (
                f"SELECT raw_content, content_hash FROM {table_name} "
                f"WHERE revision_id = ? OR {id_col} = ? "
                "ORDER BY created_at DESC LIMIT 1;"
            )
            cur = con.execute(query, (entity_id, entity_id))
            row = cur.fetchone()
    finally:
        con.close()

    if row is None:
        return RestoreResult(
            domain=domain,
            entity_id=entity_id,
            target_path=str(target_path),
            content_hash="",
            verified=False,
            status="ENTITY_NOT_FOUND",
        )

    raw_content = row["raw_content"]
    stored_hash = row["content_hash"]
    computed_hash = compute_sha256(raw_content)

    if computed_hash != stored_hash:
        return RestoreResult(
            domain=domain,
            entity_id=entity_id,
            target_path=str(target_path),
            content_hash=computed_hash,
            verified=False,
            status="HASH_MISMATCH_REJECTED",
        )

    # Atomic write to filesystem
    os.makedirs(target_path.parent, exist_ok=True)
    temp_target = target_path.with_suffix(f"{target_path.suffix}.tmp_{os.getpid()}_{int(time.time()*1000)}")
    try:
        with open(temp_target, "w", encoding="utf-8") as f:
            f.write(raw_content)
        os.replace(temp_target, target_path)
    except OSError as err:
        if temp_target.exists():
            temp_target.unlink(missing_ok=True)
        return RestoreResult(
            domain=domain,
            entity_id=entity_id,
            target_path=str(target_path),
            content_hash=computed_hash,
            verified=False,
            status=f"IO_WRITE_FAILURE: {err}",
        )

    return RestoreResult(
        domain=domain,
        entity_id=entity_id,
        target_path=str(target_path),
        content_hash=computed_hash,
        verified=True,
        status="RESTORED",
    )
