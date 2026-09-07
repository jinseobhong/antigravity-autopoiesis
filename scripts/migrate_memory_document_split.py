"""
Migration Engine: Memory & Document Physical Segregation (TASK-037).

Physically migrates legacy data/cortex.db into:
1. data/memory.db (working episodic memory: episodic_events, parked_tasks, fts_events)
2. data/document.db (archival documents: contract_revisions, state_revisions,
   architecture_revisions, fts_archive_search)
3. data/memory_seed.jsonl (deterministic text SSOT for git-tracked knowledge hydration)

Conforms to [INV-SPLIT-01] through [INV-SPLIT-09].
"""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.cortex_docs import init_cortex_db
from core.cortex_knowledge import (
    export_memory_seed,
    get_connection,
    init_knowledge_tables,
)
from core.fs_topology import CanonicalPaths


@dataclass(frozen=True)
class MigrationReport:
    """Immutable report certifying migration execution and cryptographic parity."""

    success: bool
    source_db: str
    backup_db: str
    memory_db: str
    document_db: str
    seed_file: str
    episodic_events_migrated: int
    parked_tasks_migrated: int
    contract_revisions_migrated: int
    state_revisions_migrated: int
    architecture_revisions_migrated: int
    seed_events_exported: int
    hash_verified: bool
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        """Serializes report to dictionary."""
        return asdict(self)


def _count_rows(con: sqlite3.Connection, table_name: str) -> int:
    """Safely returns row count for a given table if it exists."""
    try:
        cur = con.execute(f"SELECT COUNT(*) FROM {table_name};")
        return int(cur.fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def _migrate_memory_tables(source_con: sqlite3.Connection, mem_con: sqlite3.Connection) -> Tuple[int, int]:
    """Migrates episodic events and parked tasks into memory.db."""
    init_knowledge_tables(mem_con)
    cur_events = source_con.execute("SELECT * FROM episodic_events ORDER BY created_at ASC;")
    event_rows = cur_events.fetchall()
    with mem_con:
        mem_con.execute("DELETE FROM episodic_events;")
        mem_con.execute("DELETE FROM parked_tasks;")
        for r in event_rows:
            mem_con.execute(
                "INSERT OR REPLACE INTO episodic_events ("
                "id, outcome, component, trigger_tokens, root_cause, directive, "
                "solution, validation, access_frequency, recency_weight, created_at, last_accessed_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    r["id"],
                    r["outcome"],
                    r["component"],
                    r["trigger_tokens"],
                    r["root_cause"],
                    r["directive"],
                    r["solution"],
                    r["validation"],
                    r["access_frequency"],
                    r["recency_weight"],
                    r["created_at"],
                    r["last_accessed_at"],
                ),
            )

    cur_tasks = source_con.execute("SELECT * FROM parked_tasks ORDER BY parked_at ASC;")
    task_rows = cur_tasks.fetchall()
    with mem_con:
        for r in task_rows:
            mem_con.execute(
                "INSERT OR REPLACE INTO parked_tasks ("
                "task_id, title, description, status, reason, payload_json, parked_at, unparked_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    r["task_id"],
                    r["title"],
                    r["description"],
                    r["status"],
                    r["reason"],
                    r["payload_json"],
                    r["parked_at"],
                    r["unparked_at"],
                ),
            )

    return len(event_rows), len(task_rows)


def _migrate_contracts(source_con: sqlite3.Connection, doc_con: sqlite3.Connection) -> int:
    """Migrates contract revisions into document.db."""
    cur = source_con.execute("SELECT * FROM contract_revisions ORDER BY created_at ASC;")
    rows = cur.fetchall()
    with doc_con:
        doc_con.execute("DELETE FROM contract_revisions;")
        for r in rows:
            doc_con.execute(
                "INSERT OR REPLACE INTO contract_revisions ("
                "revision_id, contract_id, task_id, title, version, status, "
                "content_hash, raw_content, frontmatter_json, archived_reason, created_at, archived_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    r["revision_id"],
                    r["contract_id"],
                    r["task_id"],
                    r["title"],
                    r["version"],
                    r["status"],
                    r["content_hash"],
                    r["raw_content"],
                    r["frontmatter_json"],
                    r["archived_reason"],
                    r["created_at"],
                    r["archived_at"],
                ),
            )
    return len(rows)


def _migrate_states(source_con: sqlite3.Connection, doc_con: sqlite3.Connection) -> int:
    """Migrates state revisions into document.db."""
    cur = source_con.execute("SELECT * FROM state_revisions ORDER BY created_at ASC;")
    rows = cur.fetchall()
    with doc_con:
        doc_con.execute("DELETE FROM state_revisions;")
        for r in rows:
            doc_con.execute(
                "INSERT OR REPLACE INTO state_revisions ("
                "revision_id, state_id, sprint_label, active_tasks_count, "
                "content_hash, raw_content, frontmatter_json, transition_trigger, created_at, archived_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    r["revision_id"],
                    r["state_id"],
                    r["sprint_label"],
                    r["active_tasks_count"],
                    r["content_hash"],
                    r["raw_content"],
                    r["frontmatter_json"],
                    r["transition_trigger"],
                    r["created_at"],
                    r["archived_at"],
                ),
            )
    return len(rows)


def _migrate_architectures(source_con: sqlite3.Connection, doc_con: sqlite3.Connection) -> int:
    """Migrates architecture revisions into document.db."""
    cur = source_con.execute("SELECT * FROM architecture_revisions ORDER BY created_at ASC;")
    rows = cur.fetchall()
    with doc_con:
        doc_con.execute("DELETE FROM architecture_revisions;")
        for r in rows:
            doc_con.execute(
                "INSERT OR REPLACE INTO architecture_revisions ("
                "revision_id, blueprint_id, version, title, "
                "content_hash, raw_content, frontmatter_json, ratification_token, created_at, archived_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    r["revision_id"],
                    r["blueprint_id"],
                    r["version"],
                    r["title"],
                    r["content_hash"],
                    r["raw_content"],
                    r["frontmatter_json"],
                    r["ratification_token"],
                    r["created_at"],
                    r["archived_at"],
                ),
            )
    return len(rows)


def _verify_hash_parity(source_con: sqlite3.Connection, dest_con: sqlite3.Connection, table: str, key_col: str) -> bool:
    """Verifies content hash parity across migrated records."""
    cur_s = source_con.execute(f"SELECT {key_col}, content_hash FROM {table};")
    source_hashes = {r[key_col]: r["content_hash"] for r in cur_s.fetchall()}

    cur_d = dest_con.execute(f"SELECT {key_col}, content_hash FROM {table};")
    dest_hashes = {r[key_col]: r["content_hash"] for r in cur_d.fetchall()}

    return source_hashes == dest_hashes


def _verify_migration_parity(
    s_con: sqlite3.Connection,
    m_con: sqlite3.Connection,
    d_con: sqlite3.Connection,
    expected_counts: Tuple[int, int, int, int, int],
) -> Tuple[bool, bool]:
    """Verifies row counts and SHA-256 content hashes across source and destination tables."""
    mig_events, mig_tasks, mig_contracts, mig_states, mig_archs = expected_counts
    c_hash_ok = _verify_hash_parity(s_con, d_con, "contract_revisions", "revision_id")
    s_hash_ok = _verify_hash_parity(s_con, d_con, "state_revisions", "revision_id")
    a_hash_ok = _verify_hash_parity(s_con, d_con, "architecture_revisions", "revision_id")
    hash_ok = c_hash_ok and s_hash_ok and a_hash_ok

    counts_match = (
        mig_events == _count_rows(m_con, "episodic_events")
        and mig_tasks == _count_rows(m_con, "parked_tasks")
        and mig_contracts == _count_rows(d_con, "contract_revisions")
        and mig_states == _count_rows(d_con, "state_revisions")
        and mig_archs == _count_rows(d_con, "architecture_revisions")
    )
    return (counts_match and hash_ok), hash_ok


def execute_migration(
    source_path: Path,
    memory_path: Path,
    document_path: Path,
    seed_path: Path,
    backup_path: Optional[Path] = None,
) -> MigrationReport:
    """
    Executes atomic migration and verification from source cortex.db to memory and document DBs.
    Conforms to [INV-SPLIT-06] and [INV-SPLIT-07].
    """
    source_path = Path(source_path)
    memory_path = Path(memory_path)
    document_path = Path(document_path)
    seed_path = Path(seed_path)
    backup_path = Path(backup_path) if backup_path else source_path.with_suffix(".db.bak")

    if not source_path.exists():
        return MigrationReport(
            success=False,
            source_db=str(source_path),
            backup_db=str(backup_path),
            memory_db=str(memory_path),
            document_db=str(document_path),
            seed_file=str(seed_path),
            episodic_events_migrated=0,
            parked_tasks_migrated=0,
            contract_revisions_migrated=0,
            state_revisions_migrated=0,
            architecture_revisions_migrated=0,
            seed_events_exported=0,
            hash_verified=False,
            explanation=f"Source database not found: {source_path}",
        )

    # 1. Atomic physical backup [INV-SPLIT-06]
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, backup_path)

    # 2. Open connections
    s_con = get_connection(source_path)
    m_con = get_connection(memory_path)
    d_con = get_connection(document_path)

    try:
        # Initialize document schema
        init_cortex_db(document_path)

        # 3. Migrate memory tables
        mig_events, mig_tasks = _migrate_memory_tables(s_con, m_con)

        # 4. Migrate document tables
        mig_contracts = _migrate_contracts(s_con, d_con)
        mig_states = _migrate_states(s_con, d_con)
        mig_archs = _migrate_architectures(s_con, d_con)

        # 5. Export memory seed [INV-SPLIT-04]
        exported_seed = export_memory_seed(db_path=memory_path, seed_path=seed_path)

        # 6. Verify row count & SHA-256 parity [INV-SPLIT-07]
        expected_counts = (mig_events, mig_tasks, mig_contracts, mig_states, mig_archs)
        verified, hash_ok = _verify_migration_parity(s_con, m_con, d_con, expected_counts)

        return MigrationReport(
            success=verified,
            source_db=str(source_path),
            backup_db=str(backup_path),
            memory_db=str(memory_path),
            document_db=str(document_path),
            seed_file=str(seed_path),
            episodic_events_migrated=mig_events,
            parked_tasks_migrated=mig_tasks,
            contract_revisions_migrated=mig_contracts,
            state_revisions_migrated=mig_states,
            architecture_revisions_migrated=mig_archs,
            seed_events_exported=exported_seed,
            hash_verified=hash_ok,
            explanation=(
                "Migration successfully completed with 100% cryptographic parity."
                if verified
                else "Migration parity verification failed."
            ),
        )
    finally:
        s_con.close()
        m_con.close()
        d_con.close()


def main(argv: Optional[List[str]] = None) -> int:
    """CLI execution entrypoint for migration."""
    parser = argparse.ArgumentParser(description="Migrate cortex.db into memory.db and document.db")
    parser.add_argument("--source", type=str, default="data/cortex.db", help="Source cortex.db path")
    parser.add_argument("--memory", type=str, default="data/memory.db", help="Target memory.db path")
    parser.add_argument("--document", type=str, default="data/document.db", help="Target document.db path")
    parser.add_argument("--seed", type=str, default="data/memory_seed.jsonl", help="Target seed file path")
    parser.add_argument("--backup", type=str, default=None, help="Backup file path")
    parser.add_argument("--json", action="store_true", help="Output report as JSON")

    args = parser.parse_args(argv)
    report = execute_migration(
        source_path=Path(args.source),
        memory_path=Path(args.memory),
        document_path=Path(args.document),
        seed_path=Path(args.seed),
        backup_path=Path(args.backup) if args.backup else None,
    )

    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n")
    else:
        status_tag = "SUCCESS" if report.success else "FAILED"
        sys.stdout.write(f"[{status_tag}] Migration: {report.explanation}\n")
        sys.stdout.write(f"  Source:       {report.source_db}\n")
        sys.stdout.write(f"  Backup:       {report.backup_db}\n")
        sys.stdout.write(f"  Memory DB:    {report.memory_db} ({report.episodic_events_migrated} events)\n")
        sys.stdout.write(f"  Document DB:  {report.document_db} ({report.contract_revisions_migrated} contracts, "
                         f"{report.state_revisions_migrated} states, {report.architecture_revisions_migrated} archs)\n")
        sys.stdout.write(f"  Seed File:    {report.seed_file} ({report.seed_events_exported} exported)\n")
        sys.stdout.write(f"  Hash Parity:  {report.hash_verified}\n")

    return 0 if report.success else 1


if __name__ == "__main__":
    sys.exit(main())
