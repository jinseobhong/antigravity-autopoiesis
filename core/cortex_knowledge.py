"""
Persistent Cortex Knowledge & Episodic Memory Engine (core.cortex_knowledge).

Provides episodic memory persistence, FTS5 full-text keyword indexing,
decayed LFU retention scoring, task parking vault, and fail-open spooling
in SQLite WAL mode.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import math
import os
from pathlib import Path
import random
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.cortex_docs import (
        DEFAULT_SPOOL_PATH,
        get_connection,
        _spool_record,
    )
    from core.fs_topology import (
        CanonicalPaths,
        resolve_memory_db_path,
        resolve_document_db_path,
        resolve_cortex_db_path,
    )
except ModuleNotFoundError:
    from sandbox.core.cortex_docs import (
        DEFAULT_SPOOL_PATH,
        get_connection,
        _spool_record,
    )
    from sandbox.core.fs_topology import (
        CanonicalPaths,
        resolve_memory_db_path,
        resolve_document_db_path,
        resolve_cortex_db_path,
    )

DEFAULT_MEMORY_DB_PATH: Path = CanonicalPaths.DATA_MEMORY_DB
DEFAULT_MEMORY_SEED_PATH: Path = CanonicalPaths.DATA_MEMORY_SEED



class EpisodicOutcome(str, Enum):
    """Permitted outcomes for episodic events."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class ParkedTaskStatus(str, Enum):
    """Lifecycle status states for vaulted tasks."""

    PARKED = "PARKED"
    UNPARKED = "UNPARKED"


@dataclass(frozen=True)
class EpisodicRecord:
    """Immutable record of an archived episodic event or architectural lesson."""

    id: str
    outcome: str
    component: str
    trigger_tokens: str
    directive: str
    root_cause: Optional[str]
    solution: Optional[str]
    validation: Optional[str]
    access_frequency: int
    recency_weight: float
    created_at: str
    last_accessed_at: str

    def __post_init__(self) -> None:
        """Enforces domain invariants across episodic fields."""
        if not self.id or not self.id.strip():
            raise ValueError("EpisodicRecord.id must be a non-empty string.")
        clean_out = str(self.outcome).strip().upper()
        if clean_out not in (EpisodicOutcome.SUCCESS.value, EpisodicOutcome.FAILURE.value):
            raise ValueError(f"Invalid outcome: '{self.outcome}'. Expected SUCCESS or FAILURE.")
        if self.access_frequency < 1:
            raise ValueError(f"EpisodicRecord.access_frequency must be >= 1, got {self.access_frequency}.")
        if self.recency_weight < 0.0:
            raise ValueError(f"EpisodicRecord.recency_weight must be >= 0.0, got {self.recency_weight}.")


@dataclass(frozen=True)
class ParkedTaskRecord:
    """Immutable record of a task vaulted outside the active rolling horizon."""

    task_id: str
    title: str
    description: str
    status: str
    reason: str
    payload: Dict[str, Any]
    parked_at: str
    unparked_at: Optional[str]

    def __post_init__(self) -> None:
        """Enforces domain invariants across parked task fields."""
        if not self.task_id or not self.task_id.strip():
            raise ValueError("ParkedTaskRecord.task_id must be a non-empty string.")
        clean_stat = str(self.status).strip().upper()
        if clean_stat not in (ParkedTaskStatus.PARKED.value, ParkedTaskStatus.UNPARKED.value):
            raise ValueError(f"Invalid status: '{self.status}'. Expected PARKED or UNPARKED.")


@dataclass(frozen=True)
class CortexStats:
    """Aggregated operational metrics across the cortex persistence engine."""

    total_episodic_events: int
    success_events: int
    failure_events: int
    active_parked_tasks: int
    total_parked_tasks: int
    contract_revisions: int
    state_revisions: int
    architecture_revisions: int

    @classmethod
    def empty(cls) -> "CortexStats":
        """Factory for empty initial telemetry metrics."""
        return cls(0, 0, 0, 0, 0, 0, 0, 0)


def _parse_timestamp(iso_str: str) -> datetime:
    """Parses timestamp strings, guaranteeing offset-aware UTC datetimes."""
    clean = str(iso_str).replace("Z", "+00:00")
    for fmt_fn in (
        datetime.fromisoformat,
        lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc),
    ):
        try:
            dt = fmt_fn(clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            continue
    raise ValueError(f"Invalid created_at timestamp '{iso_str}'. Expected valid ISO-8601 or '%Y-%m-%d %H:%M:%S'.")


def calculate_decay_weight(
    created_at_iso: str,
    access_frequency: int,
    half_life_hours: float = 168.0,
    alpha: float = 0.15,
) -> float:
    """
    Computes decayed LFU retention weight:
    W(t) = W0 * 2^(-delta_t / t_half) + alpha * log(f)
    where f = max(1, access_frequency). When f=1 (initial state), log(1) == 0.
    """
    dt_created = _parse_timestamp(created_at_iso)
    now = datetime.now(timezone.utc)
    delta_hours = max(0.0, (now - dt_created).total_seconds() / 3600.0)
    base_weight = 1.0 * math.pow(2.0, -delta_hours / max(1.0, half_life_hours))
    effective_freq = max(1, access_frequency)
    frequency_bonus = alpha * math.log(effective_freq)
    return round(base_weight + frequency_bonus, 4)


def sanitize_fts_query(query_str: str) -> str:
    """Sanitizes raw query string for safe FTS5 MATCH evaluation using regex word matching."""
    clean_tokens = re.findall(r"[\w-]+", query_str)
    valid_tokens = [t.strip("-") for t in clean_tokens if t.strip("-")]
    if not valid_tokens:
        return ""
    return " OR ".join(f'"{t}"*' for t in valid_tokens)


def init_knowledge_tables(con: sqlite3.Connection) -> None:
    """Provisions episodic_events, fts_events, and parked_tasks tables and triggers."""
    with con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS episodic_events (
                id TEXT PRIMARY KEY,
                outcome TEXT CHECK(outcome IN ('SUCCESS', 'FAILURE')) NOT NULL,
                component TEXT NOT NULL,
                trigger_tokens TEXT NOT NULL,
                root_cause TEXT,
                directive TEXT NOT NULL,
                solution TEXT,
                validation TEXT,
                access_frequency INTEGER NOT NULL DEFAULT 1,
                recency_weight REAL NOT NULL DEFAULT 1.0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_accessed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_episodic_comp_outcome ON episodic_events(component, outcome);"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_episodic_created ON episodic_events(created_at);"
        )
        con.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_events USING fts5(
                id UNINDEXED,
                component,
                trigger_tokens,
                directive,
                root_cause,
                solution
            );
            """
        )
        con.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_fts_insert AFTER INSERT ON episodic_events BEGIN
                INSERT INTO fts_events(id, component, trigger_tokens, directive, root_cause, solution)
                VALUES (new.id, new.component, new.trigger_tokens, new.directive, new.root_cause, new.solution);
            END;
            """
        )
        con.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_fts_delete AFTER DELETE ON episodic_events BEGIN
                DELETE FROM fts_events WHERE id = old.id;
            END;
            """
        )
        con.execute("DROP TRIGGER IF EXISTS trg_fts_update;")
        con.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_fts_update
            AFTER UPDATE OF component, trigger_tokens, directive, root_cause, solution ON episodic_events
            BEGIN
                DELETE FROM fts_events WHERE id = old.id;
                INSERT INTO fts_events(id, component, trigger_tokens, directive, root_cause, solution)
                VALUES (new.id, new.component, new.trigger_tokens, new.directive, new.root_cause, new.solution);
            END;
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS parked_tasks (
                task_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PARKED',
                reason TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                parked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                unparked_at TIMESTAMP
            );
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_parked_tasks_status ON parked_tasks(status);"
        )


def _validate_record_inputs(
    outcome: str, component: str, trigger_tokens: str, directive: str
) -> str:
    """Validates mandatory input fields for episodic record creation."""
    clean_outcome = outcome.strip().upper()
    if clean_outcome not in (EpisodicOutcome.SUCCESS.value, EpisodicOutcome.FAILURE.value):
        raise ValueError(f"Invalid outcome '{outcome}'. Expected 'SUCCESS' or 'FAILURE'.")
    if not component or not component.strip():
        raise ValueError("Component must be a non-empty string.")
    if not trigger_tokens or not trigger_tokens.strip():
        raise ValueError("Trigger tokens must be a non-empty string.")
    if not directive or not directive.strip():
        raise ValueError("Directive must be a non-empty string.")
    return clean_outcome


INSERT_EVENT_SQL = """
INSERT INTO episodic_events (
    id, outcome, component, trigger_tokens, root_cause,
    directive, solution, validation, access_frequency,
    recency_weight, created_at, last_accessed_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""


def _persist_with_retry(
    target_db: Path,
    record_dict: Dict[str, Any],
    spool_path: Optional[Path] = None,
) -> bool:
    """Inserts record into sqlite with exponential backoff on lock contention."""
    max_retries = 5
    base_delay = 0.05
    record_tuple = (
        record_dict["id"],
        record_dict["outcome"],
        record_dict["component"],
        record_dict["trigger_tokens"],
        record_dict["root_cause"],
        record_dict["directive"],
        record_dict["solution"],
        record_dict["validation"],
        record_dict["access_frequency"],
        record_dict["recency_weight"],
        record_dict["created_at"],
        record_dict["last_accessed_at"],
    )

    for attempt in range(max_retries):
        try:
            con = get_connection(target_db)
            try:
                init_knowledge_tables(con)
                with con:
                    con.execute(INSERT_EVENT_SQL, record_tuple)
                return True
            finally:
                con.close()
        except sqlite3.OperationalError:
            jitter = random.uniform(0.8, 1.2)
            sleep_duration = min(0.5, (base_delay * (2 ** attempt)) * jitter)
            time.sleep(sleep_duration)

    _spool_record(record_dict, spool_path=spool_path)
    return False


def record_event(
    outcome: str,
    component: str,
    trigger_tokens: str,
    directive: str,
    db_path: Optional[Path] = None,
    **kwargs: Any,
) -> EpisodicRecord:
    """
    Persists an episodic event or architectural directive to cortex.db.
    Additional keyword arguments may include root_cause, solution, validation, spool_path.
    """
    clean_outcome = _validate_record_inputs(outcome, component, trigger_tokens, directive)

    now_iso = datetime.now(timezone.utc).isoformat()
    random_suffix = "".join(random.choices("0123456789abcdef", k=8))
    event_id = f"evt_{int(time.time())}_{random_suffix}"

    root_cause = kwargs.get("root_cause")
    solution = kwargs.get("solution")
    validation = kwargs.get("validation")

    record_dict = {
        "id": event_id,
        "outcome": clean_outcome,
        "component": component.strip(),
        "trigger_tokens": trigger_tokens.strip(),
        "directive": directive.strip(),
        "root_cause": str(root_cause).strip() if root_cause else None,
        "solution": str(solution).strip() if solution else None,
        "validation": str(validation).strip() if validation else None,
        "access_frequency": 1,
        "recency_weight": 1.0,
        "created_at": now_iso,
        "last_accessed_at": now_iso,
    }

    target_db = resolve_memory_db_path(db_path, check_exists=False)
    spool_path = kwargs.get("spool_path")
    _persist_with_retry(target_db, record_dict, spool_path=spool_path)

    return EpisodicRecord(**record_dict)


def _build_event_query(
    query_str: Optional[str],
    component: Optional[str],
    outcome: Optional[str],
    limit: int,
) -> Tuple[str, List[Any]]:
    """Constructs SQL query and parameters for keyword or indexed episodic searches."""
    fts_match = sanitize_fts_query(query_str) if query_str else None
    params: List[Any] = []
    pfx = "e." if fts_match else ""
    from_clause = "fts_events f JOIN episodic_events e ON f.id = e.id" if fts_match else "episodic_events"
    conditions: List[str] = []

    if fts_match:
        conditions.append("fts_events MATCH ?")
        params.append(fts_match)

    if component:
        conditions.append(f"{pfx}component = ?")
        params.append(component.strip())

    if outcome:
        conditions.append(f"{pfx}outcome = ?")
        params.append(outcome.strip().upper())

    where_str = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    order_str = f" ORDER BY {pfx}recency_weight DESC, {pfx}access_frequency DESC LIMIT ?"
    params.append(limit)

    return f"SELECT {pfx}* FROM {from_clause}{where_str}{order_str};", params


def _bump_event_access(con: sqlite3.Connection, ids_to_bump: List[Tuple[str, int, str]]) -> None:
    """Updates access frequency and lazily recalculates recency weights for queried rows."""
    if not ids_to_bump:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    with con:
        for eid, new_freq, created_iso in ids_to_bump:
            new_weight = calculate_decay_weight(created_iso, new_freq)
            con.execute(
                """
                UPDATE episodic_events
                SET access_frequency = ?, recency_weight = ?, last_accessed_at = ?
                WHERE id = ?;
                """,
                (new_freq, new_weight, now_iso, eid),
            )


def _fetch_event_rows(con: sqlite3.Connection, sql: str, params: List[Any]) -> List[sqlite3.Row]:
    """Executes search query against sqlite, initializing tables on cold-start."""
    try:
        cur = con.execute(sql, tuple(params))
        return cur.fetchall()
    except sqlite3.OperationalError:
        init_knowledge_tables(con)
        cur = con.execute(sql, tuple(params))
        return cur.fetchall()


def _convert_rows_to_records(
    rows: List[sqlite3.Row], touch: bool
) -> Tuple[List[EpisodicRecord], List[Tuple[str, int, str]]]:
    """Converts raw rows to EpisodicRecord objects, generating touch bump tuples."""
    results: List[EpisodicRecord] = []
    ids_to_bump: List[Tuple[str, int, str]] = []
    for r in rows:
        freq = r["access_frequency"] + 1 if touch else r["access_frequency"]
        weight = calculate_decay_weight(str(r["created_at"]), freq) if touch else r["recency_weight"]
        rec = EpisodicRecord(
            id=r["id"],
            outcome=r["outcome"],
            component=r["component"],
            trigger_tokens=r["trigger_tokens"],
            directive=r["directive"],
            root_cause=r["root_cause"],
            solution=r["solution"],
            validation=r["validation"],
            access_frequency=freq,
            recency_weight=weight,
            created_at=str(r["created_at"]),
            last_accessed_at=str(r["last_accessed_at"]),
        )
        results.append(rec)
        if touch:
            ids_to_bump.append((rec.id, freq, rec.created_at))
    return results, ids_to_bump


def query_events(
    query_str: Optional[str] = None,
    component: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = 5,
    db_path: Optional[Path] = None,
    touch: bool = False,
) -> List[EpisodicRecord]:
    """
    Executes read-only keyword or indexed query across episodic events.
    When touch=True, performs best-effort updates to access frequency and recency.
    """
    if limit <= 0:
        raise ValueError(f"Limit must be a positive integer, got {limit}")

    target_db = resolve_memory_db_path(db_path, check_exists=True)
    if not target_db.exists():
        return []

    con = get_connection(target_db)
    try:
        sql, params = _build_event_query(query_str, component, outcome, limit)
        rows = _fetch_event_rows(con, sql, params)
        results, ids_to_bump = _convert_rows_to_records(rows, touch)

        if touch and ids_to_bump:
            try:
                _bump_event_access(con, ids_to_bump)
            except sqlite3.OperationalError:
                return results
        return results
    finally:
        con.close()


def get_grounding_directives(
    keywords: str,
    limit: int = 5,
    db_path: Optional[Path] = None,
    touch: bool = True,
) -> str:
    """
    Retrieves relevant episodic directives from cortex.db using FTS5 keyword matching
    and formats them as an enforceable markdown instruction block for prompt grounding.
    """
    if not keywords or not keywords.strip():
        return ""

    records = query_events(
        query_str=keywords.strip(),
        limit=limit,
        db_path=db_path,
        touch=touch,
    )
    if not records:
        return ""

    lines = [
        "### Cognitive Grounding Directives (Retrieved from Cortex Memory):",
        "> The following binding invariants and historical directives apply to this task:",
    ]
    for idx, rec in enumerate(records, 1):
        lines.append(f"{idx}. **[{rec.component}]** ({rec.outcome}): {rec.directive}")
        if rec.root_cause:
            lines.append(f"   - *Root Cause*: {rec.root_cause}")
        if rec.solution:
            lines.append(f"   - *Solution*: {rec.solution}")
    return "\n".join(lines)


def _validate_park_inputs(task_id: str, title: str, reason: str) -> None:
    """Validates required non-empty string arguments for task parking."""
    if not task_id or not task_id.strip():
        raise ValueError("task_id must be a non-empty string.")
    if not title or not title.strip():
        raise ValueError("title must be a non-empty string.")
    if not reason or not reason.strip():
        raise ValueError("reason must be a non-empty string.")


PARK_TASK_SQL = """
INSERT INTO parked_tasks (
    task_id, title, description, status, reason, payload_json, parked_at, unparked_at
) VALUES (?, ?, ?, 'PARKED', ?, ?, ?, NULL)
ON CONFLICT(task_id) DO UPDATE SET
    title = excluded.title,
    description = excluded.description,
    status = 'PARKED',
    reason = excluded.reason,
    payload_json = excluded.payload_json,
    parked_at = excluded.parked_at,
    unparked_at = NULL;
"""


def _persist_park_task_with_retry(
    target_db: Path,
    params: Tuple[str, str, str, str, str, str],
) -> None:
    """Executes task parking with exponential backoff on lock contention."""
    max_retries = 5
    base_delay = 0.05
    for attempt in range(max_retries):
        try:
            con = get_connection(target_db)
            try:
                init_knowledge_tables(con)
                with con:
                    con.execute(PARK_TASK_SQL, params)
                return
            finally:
                con.close()
        except sqlite3.OperationalError:
            if attempt == max_retries - 1:
                raise
            jitter = random.uniform(0.8, 1.2)
            time.sleep(min(0.5, (base_delay * (2 ** attempt)) * jitter))


def park_task(
    task_id: str,
    title: str,
    reason: str,
    description: str = "",
    payload: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> ParkedTaskRecord:
    """Parks an overflow task in the cortex vault with backoff retry on lock contention."""
    _validate_park_inputs(task_id, title, reason)

    target_db = resolve_memory_db_path(db_path, check_exists=False)
    now_iso = datetime.now(timezone.utc).isoformat()
    payload_dict = payload if payload is not None else {}
    payload_str = json.dumps(payload_dict, ensure_ascii=False, default=str)

    params = (
        task_id.strip(),
        title.strip(),
        description.strip(),
        reason.strip(),
        payload_str,
        now_iso,
    )
    _persist_park_task_with_retry(target_db, params)

    return ParkedTaskRecord(
        task_id=task_id.strip(),
        title=title.strip(),
        description=description.strip(),
        status="PARKED",
        reason=reason.strip(),
        payload=payload_dict,
        parked_at=now_iso,
        unparked_at=None,
    )


def unpark_task(task_id: str, db_path: Optional[Path] = None) -> Optional[ParkedTaskRecord]:
    """Reactivates a vaulted task atomically; rejects illegal UNPARKED to UNPARKED transitions."""
    if not task_id or not task_id.strip():
        raise ValueError("task_id must be a non-empty string.")

    target_db = resolve_memory_db_path(db_path, check_exists=True)
    if not target_db.exists():
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    con = get_connection(target_db)
    record: Optional[ParkedTaskRecord] = None

    try:
        with con:
            cur_update = con.execute(
                """
                UPDATE parked_tasks
                SET status = 'UNPARKED', unparked_at = ?
                WHERE task_id = ? AND status = 'PARKED';
                """,
                (now_iso, task_id.strip()),
            )
            if cur_update.rowcount == 0:
                cur_check = con.execute(
                    "SELECT status FROM parked_tasks WHERE task_id = ?;",
                    (task_id.strip(),),
                )
                row_check = cur_check.fetchone()
                if row_check is not None and row_check["status"] == "UNPARKED":
                    raise ValueError(f"Task '{task_id.strip()}' is already UNPARKED; cannot transition again.")
                return None

            cur_select = con.execute("SELECT * FROM parked_tasks WHERE task_id = ?;", (task_id.strip(),))
            row = cur_select.fetchone()
            if row is None:
                return None

        try:
            payload_data = json.loads(row["payload_json"])
        except (ValueError, TypeError):
            payload_data = {}

        record = ParkedTaskRecord(
            task_id=row["task_id"],
            title=row["title"],
            description=row["description"],
            status="UNPARKED",
            reason=row["reason"],
            payload=payload_data,
            parked_at=str(row["parked_at"]),
            unparked_at=now_iso,
        )
    finally:
        con.close()

    return record


def list_parked_tasks(
    status: str = "PARKED",
    db_path: Optional[Path] = None,
) -> List[ParkedTaskRecord]:
    """Retrieves list of tasks from the cortex vault filtered by status."""
    target_db = resolve_memory_db_path(db_path, check_exists=True)
    if not target_db.exists():
        return []

    con = get_connection(target_db)
    tasks: List[ParkedTaskRecord] = []

    try:
        cur = con.execute(
            "SELECT * FROM parked_tasks WHERE status = ? ORDER BY parked_at ASC;",
            (status.strip().upper(),),
        )
        rows = cur.fetchall()
        for r in rows:
            try:
                payload_data = json.loads(r["payload_json"])
            except (ValueError, TypeError):
                payload_data = {}
            tasks.append(
                ParkedTaskRecord(
                    task_id=r["task_id"],
                    title=r["title"],
                    description=r["description"],
                    status=r["status"],
                    reason=r["reason"],
                    payload=payload_data,
                    parked_at=str(r["parked_at"]),
                    unparked_at=str(r["unparked_at"]) if r["unparked_at"] else None,
                )
            )
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()

    return tasks


def vacuum_decay(
    half_life_hours: float = 168.0,
    min_weight: float = 0.05,
    min_frequency: int = 3,
    db_path: Optional[Path] = None,
) -> int:
    """
    Evaluates decayed weights across episodic events and purges rows
    falling below both min_weight and min_frequency thresholds atomically.
    """
    target_db = resolve_memory_db_path(db_path, check_exists=True)
    if not target_db.exists():
        return 0

    con = get_connection(target_db)
    evicted_count = 0

    try:
        cur = con.execute("SELECT id, created_at, access_frequency FROM episodic_events;")
        candidates: List[Tuple[str, int]] = []

        for r in cur:
            current_weight = calculate_decay_weight(
                str(r["created_at"]),
                int(r["access_frequency"]),
                half_life_hours=half_life_hours,
            )
            if current_weight < min_weight and int(r["access_frequency"]) < min_frequency:
                candidates.append((r["id"], int(r["access_frequency"])))

        if candidates:
            with con:
                for eid, max_freq in candidates:
                    res = con.execute(
                        "DELETE FROM episodic_events WHERE id = ? AND access_frequency <= ?;",
                        (eid, max_freq),
                    )
                    evicted_count += res.rowcount
    except sqlite3.OperationalError:
        return 0
    finally:
        con.close()

    return evicted_count


def _count_table(con: sqlite3.Connection, name: str, condition: str = "1=1") -> int:
    """Safely counts records in specified table if table exists."""
    try:
        cur = con.execute(f"SELECT COUNT(*) FROM {name} WHERE {condition};")
        return int(cur.fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def get_cortex_stats(
    db_path: Optional[Path] = None,
    docs_db_path: Optional[Path] = None,
) -> CortexStats:
    """Gathers summary statistics across all knowledge and document archive tables."""
    mem_db = resolve_memory_db_path(db_path, check_exists=True)
    doc_db = resolve_document_db_path(docs_db_path, check_exists=True)

    if not mem_db.exists() and not doc_db.exists():
        return CortexStats.empty()

    tot_events, succ_events, fail_events = 0, 0, 0
    active_parked, tot_parked = 0, 0
    c_revs, s_revs, a_revs = 0, 0, 0

    if mem_db.exists():
        con_mem = get_connection(mem_db)
        try:
            tot_events = _count_table(con_mem, "episodic_events")
            succ_events = _count_table(con_mem, "episodic_events", "outcome = 'SUCCESS'")
            fail_events = _count_table(con_mem, "episodic_events", "outcome = 'FAILURE'")
            active_parked = _count_table(con_mem, "parked_tasks", "status = 'PARKED'")
            tot_parked = _count_table(con_mem, "parked_tasks")
            c_revs = _count_table(con_mem, "contract_revisions")
            s_revs = _count_table(con_mem, "state_revisions")
            a_revs = _count_table(con_mem, "architecture_revisions")
        finally:
            con_mem.close()

    if doc_db.exists() and doc_db != mem_db:
        con_doc = get_connection(doc_db)
        try:
            c_revs = _count_table(con_doc, "contract_revisions")
            s_revs = _count_table(con_doc, "state_revisions")
            a_revs = _count_table(con_doc, "architecture_revisions")
        finally:
            con_doc.close()

    return CortexStats(
        total_episodic_events=tot_events,
        success_events=succ_events,
        failure_events=fail_events,
        active_parked_tasks=active_parked,
        total_parked_tasks=tot_parked,
        contract_revisions=c_revs,
        state_revisions=s_revs,
        architecture_revisions=a_revs,
    )


def export_memory_seed(
    db_path: Optional[Path] = None,
    seed_path: Optional[Path] = None,
) -> int:
    """
    Exports episodic memory records to a deterministic, line-delimited JSONL seed file.
    Conforms to [INV-SPLIT-04] and [INV-SPLIT-05].
    """
    target_db = resolve_memory_db_path(db_path, check_exists=True)
    if not target_db.exists():
        return 0

    target_seed = Path(seed_path) if seed_path is not None else DEFAULT_MEMORY_SEED_PATH
    target_seed.parent.mkdir(parents=True, exist_ok=True)

    con = get_connection(target_db)
    try:
        init_knowledge_tables(con)
        cur = con.execute(
            "SELECT id, outcome, component, trigger_tokens, root_cause, directive, "
            "solution, validation, access_frequency, recency_weight, created_at, last_accessed_at "
            "FROM episodic_events ORDER BY created_at ASC;"
        )
        rows = cur.fetchall()
        lines: List[str] = []
        for r in rows:
            entry = {
                "id": r["id"],
                "outcome": r["outcome"],
                "component": r["component"],
                "trigger_tokens": r["trigger_tokens"],
                "root_cause": r["root_cause"],
                "directive": r["directive"],
                "solution": r["solution"],
                "validation": r["validation"],
                "access_frequency": r["access_frequency"],
                "recency_weight": r["recency_weight"],
                "created_at": r["created_at"],
                "last_accessed_at": r["last_accessed_at"],
            }
            lines.append(json.dumps(entry, ensure_ascii=False))

        with open(target_seed, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")

        return len(lines)
    finally:
        con.close()


def hydrate_memory_from_seed(
    seed_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> int:
    """
    Hydrates episodic events from JSONL seed into memory.db idempotently.
    Conforms to [INV-SPLIT-04] and [INV-SPLIT-08].
    """
    target_seed = Path(seed_path) if seed_path is not None else DEFAULT_MEMORY_SEED_PATH
    if not target_seed.exists():
        return 0

    target_db = resolve_memory_db_path(db_path, check_exists=False)
    target_db.parent.mkdir(parents=True, exist_ok=True)

    con = get_connection(target_db)
    hydrated_count = 0
    try:
        init_knowledge_tables(con)
        with open(target_seed, "r", encoding="utf-8") as f:
            raw_lines = [line.strip() for line in f if line.strip()]

        with con:
            for line in raw_lines:
                try:
                    entry = json.loads(line)
                    tuple_val = (
                        entry["id"],
                        entry["outcome"],
                        entry["component"],
                        entry["trigger_tokens"],
                        entry.get("root_cause"),
                        entry["directive"],
                        entry.get("solution"),
                        entry.get("validation"),
                        entry.get("access_frequency", 1),
                        entry.get("recency_weight", 1.0),
                        entry["created_at"],
                        entry["last_accessed_at"],
                    )
                    res = con.execute(
                        "INSERT OR IGNORE INTO episodic_events ("
                        "id, outcome, component, trigger_tokens, root_cause, "
                        "directive, solution, validation, access_frequency, "
                        "recency_weight, created_at, last_accessed_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                        tuple_val,
                    )
                    if res.rowcount > 0:
                        hydrated_count += 1
                except (json.JSONDecodeError, KeyError):
                    continue
        return hydrated_count
    finally:
        con.close()

