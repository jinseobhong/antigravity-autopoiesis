"""
Command-Line Interface for Cortex Knowledge & Document Persistence (core.cortex).

Provides deterministic CLI commands for episodic memory recording,
FTS5 full-text queries, task parking vault, decay vacuuming, domain-segregated
document eviction, and cryptographic restoration.
"""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Callable, Dict, List, Optional

try:
    from core.cortex_docs import (
        get_connection,
        init_cortex_db,
        restore_archive,
        trigger_architecture_eviction,
        trigger_contract_eviction,
        trigger_state_eviction,
    )
    from core.cortex_knowledge import (
        export_memory_seed,
        get_cortex_stats,
        get_grounding_directives,
        hydrate_memory_from_seed,
        init_knowledge_tables,
        list_parked_tasks,
        park_task,
        query_events,
        record_event,
        resolve_memory_db_path,
        unpark_task,
        vacuum_decay,
    )
    from core.state_compactor import compact_state_ledger
except ModuleNotFoundError:
    from sandbox.core.cortex_docs import (
        get_connection,
        init_cortex_db,
        restore_archive,
        trigger_architecture_eviction,
        trigger_contract_eviction,
        trigger_state_eviction,
    )
    from sandbox.core.cortex_knowledge import (
        export_memory_seed,
        get_cortex_stats,
        get_grounding_directives,
        hydrate_memory_from_seed,
        init_knowledge_tables,
        list_parked_tasks,
        park_task,
        query_events,
        record_event,
        resolve_memory_db_path,
        unpark_task,
        vacuum_decay,
    )
    from sandbox.core.state_compactor import compact_state_ledger


def build_parser() -> argparse.ArgumentParser:
    """Constructs the command-line argument parser with knowledge and domain subcommands."""
    parser = argparse.ArgumentParser(
        prog="python -m core.cortex",
        description="Autopoiesis Cortex Knowledge & Document Persistence CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # record
    p_record = subparsers.add_parser("record", help="Persist an episodic event or architectural directive")
    p_record.add_argument("--outcome", choices=["SUCCESS", "FAILURE"], required=True, help="Trace outcome")
    p_record.add_argument("--component", type=str, required=True, help="Impacted subsystem or component")
    p_record.add_argument("--trigger", type=str, required=True, help="Trigger tokens or error description")
    p_record.add_argument("--directive", type=str, required=True, help="Architectural directive or lesson learned")
    p_record.add_argument("--root-cause", type=str, default=None, help="Root cause explanation (for failures)")
    p_record.add_argument("--solution", type=str, default=None, help="Verified solution (for successes)")
    p_record.add_argument("--validation", type=str, default=None, help="Verification evidence or test output")
    p_record.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # query
    p_query = subparsers.add_parser("query", help="Query episodic events using FTS5 keywords or indexed fields")
    p_query.add_argument("--keyword", type=str, default=None, help="Full-text search keywords")
    p_query.add_argument("--component", type=str, default=None, help="Filter by component name")
    p_query.add_argument("--outcome", choices=["SUCCESS", "FAILURE"], default=None, help="Filter by outcome")
    p_query.add_argument("--limit", type=int, default=5, help="Maximum results to return (default: 5)")
    p_query.add_argument("--json", action="store_true", help="Output results as JSON")
    p_query.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # ground
    p_ground = subparsers.add_parser("ground", help="Retrieve grounding directives for prompt injection")
    p_ground.add_argument("--keywords", type=str, required=True, help="Keywords or domain tokens to match")
    p_ground.add_argument("--limit", type=int, default=5, help="Maximum directives to retrieve (default: 5)")
    p_ground.add_argument("--db", type=str, default=None, help="Custom cortex.db path")
    p_ground.add_argument("--json", action="store_true", help="Output directives as JSON")

    # park-task
    p_park = subparsers.add_parser("park-task", help="Park an overflow task in the cortex vault")
    p_park.add_argument("--id", type=str, required=True, help="Unique Task ID (e.g. TASK-106)")
    p_park.add_argument("--title", type=str, required=True, help="Task title")
    p_park.add_argument("--reason", type=str, required=True, help="Reason for parking (e.g. Horizon capacity 5/5)")
    p_park.add_argument("--desc", type=str, default="", help="Detailed task description")
    p_park.add_argument("--payload", type=str, default="{}", help="Task payload JSON string")
    p_park.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # unpark-task
    p_unpark = subparsers.add_parser("unpark-task", help="Reactivate a task from the cortex vault")
    p_unpark.add_argument("--id", type=str, required=True, help="Task ID to unpark")
    p_unpark.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # list-parked
    p_list_parked = subparsers.add_parser("list-parked", help="List tasks currently in the cortex vault")
    p_list_parked.add_argument("--status", type=str, default="PARKED", help="Filter by status (default: PARKED)")
    p_list_parked.add_argument("--json", action="store_true", help="Output results as JSON")
    p_list_parked.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # stats
    p_stats = subparsers.add_parser("stats", help="Display aggregated telemetry across all cortex tables")
    p_stats.add_argument("--json", action="store_true", help="Output results as JSON")
    p_stats.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # vacuum
    p_vacuum = subparsers.add_parser("vacuum", help="Evaluate decayed retention weights and prune stale traces")
    p_vacuum.add_argument("--half-life", type=float, default=168.0, help="Half-life in hours (default: 168.0)")
    p_vacuum.add_argument("--min-weight", type=float, default=0.05, help="Minimum retention weight (default: 0.05)")
    p_vacuum.add_argument("--min-frequency", type=int, default=3, help="Minimum access frequency (default: 3)")
    p_vacuum.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # evict-contract
    p_contract = subparsers.add_parser("evict-contract", help="Evict excess contracts to contract_revisions")
    p_contract.add_argument(
        "--dir", type=str, required=True, help="Directory containing active contract markdown files"
    )
    p_contract.add_argument("--capacity", type=int, default=5, help="Maximum transient contracts on disk (default: 5)")
    p_contract.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # evict-state
    p_state = subparsers.add_parser("evict-state", help="Evict excess state ledgers to state_revisions")
    p_state.add_argument("--dir", type=str, required=True, help="Directory containing state ledger history files")
    p_state.add_argument("--capacity", type=int, default=5, help="Maximum transient state files on disk (default: 5)")
    p_state.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # evict-arch
    p_arch = subparsers.add_parser("evict-arch", help="Evict excess blueprints to architecture_revisions")
    p_arch.add_argument("--dir", type=str, required=True, help="Directory containing blueprint files")
    p_arch.add_argument("--capacity", type=int, default=5, help="Maximum transient blueprints on disk (default: 5)")
    p_arch.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # restore
    p_restore = subparsers.add_parser("restore", help="Restore an archived document revision with SHA-256 validation")
    p_restore.add_argument("--domain", choices=["contract", "state", "architecture"], required=True, help="Domain type")
    p_restore.add_argument("--id", type=str, required=True, help="Revision ID or Entity ID to restore")
    p_restore.add_argument("--out", type=str, required=True, help="Target destination path on disk")
    p_restore.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    # init
    p_init = subparsers.add_parser("init", help="Initialize memory.db and document.db tables and indexes")
    p_init.add_argument("--db", type=str, default=None, help="Custom database path")

    # export-seed
    p_export_seed = subparsers.add_parser("export-seed", help="Export episodic memory to JSONL seed")
    p_export_seed.add_argument("--seed", type=str, default=None, help="Target seed file path")
    p_export_seed.add_argument("--db", type=str, default=None, help="Custom memory.db path")

    # hydrate-seed
    p_hydrate_seed = subparsers.add_parser("hydrate-seed", help="Hydrate memory.db from JSONL seed")
    p_hydrate_seed.add_argument("--seed", type=str, default=None, help="Source seed file path")
    p_hydrate_seed.add_argument("--db", type=str, default=None, help="Custom memory.db path")

    # compact-ledger
    p_compact = subparsers.add_parser("compact-ledger", help="Compact state ledger and snapshot to cortex")
    p_compact.add_argument("--ledger", type=str, default="docs/active/CURRENT_STATE.md", help="Path to state ledger")
    p_compact.add_argument("--threshold", type=int, default=10, help="Compaction threshold (default: 10)")
    p_compact.add_argument("--keep", type=int, default=5, help="Recent tasks to keep (default: 5)")
    p_compact.add_argument("--archive-dir", type=str, default="docs/archived", help="Archive directory")
    p_compact.add_argument("--force", action="store_true", help="Force compaction regardless of count")
    p_compact.add_argument("--json", action="store_true", help="Output compaction report JSON")
    p_compact.add_argument("--db", type=str, default=None, help="Custom cortex.db path")

    return parser


def _handle_init(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles dual-database initialization and seed auto-hydration."""
    doc_target = init_cortex_db(db_path)
    mem_db = resolve_memory_db_path(db_path, check_exists=False)
    con = get_connection(mem_db)
    try:
        init_knowledge_tables(con)
    finally:
        con.close()
    hydrated = hydrate_memory_from_seed(db_path=mem_db)
    sys.stdout.write(
        f"CORTEX_DB_INITIALIZED: {doc_target}\n"
        f"CORTEX_INITIALIZED: memory='{mem_db}' (hydrated {hydrated} seed events), "
        f"document='{doc_target}'\n"
    )
    return 0


def _handle_export_seed(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles episodic memory export to JSONL seed."""
    seed_p = Path(args.seed) if args.seed else None
    cnt = export_memory_seed(db_path=db_path, seed_path=seed_p)
    sys.stdout.write(f"MEMORY_SEED_EXPORTED: {cnt} event(s) exported.\n")
    return 0


def _handle_hydrate_seed(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles episodic memory hydration from JSONL seed."""
    seed_p = Path(args.seed) if args.seed else None
    cnt = hydrate_memory_from_seed(seed_path=seed_p, db_path=db_path)
    sys.stdout.write(f"MEMORY_HYDRATED: {cnt} event(s) imported from seed.\n")
    return 0


def _handle_record(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles episodic trace recording subcommand."""
    rec = record_event(
        outcome=args.outcome,
        component=args.component,
        trigger_tokens=args.trigger,
        directive=args.directive,
        root_cause=args.root_cause,
        solution=args.solution,
        validation=args.validation,
        db_path=db_path,
    )
    sys.stdout.write(json.dumps(asdict(rec), ensure_ascii=False, indent=2) + "\n")
    return 0


def _handle_query(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles episodic trace querying subcommand."""
    records = query_events(
        query_str=args.keyword,
        component=args.component,
        outcome=args.outcome,
        limit=args.limit,
        db_path=db_path,
    )
    if args.json:
        sys.stdout.write(json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2) + "\n")
        return 0

    sys.stdout.write(f"Query returned {len(records)} episodic event(s):\n")
    for r in records:
        sys.stdout.write(
            f"[{r.outcome}] ID={r.id} | Component={r.component} | Weight={r.recency_weight:.2f}\n"
            f"  Trigger:   {r.trigger_tokens}\n"
            f"  Directive: {r.directive}\n"
        )
        if r.root_cause:
            sys.stdout.write(f"  Root Cause: {r.root_cause}\n")
        if r.solution:
            sys.stdout.write(f"  Solution:   {r.solution}\n")
    return 0


def _handle_ground(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles prompt grounding directives retrieval subcommand."""
    if args.json:
        records = query_events(query_str=args.keywords, limit=args.limit, db_path=db_path, touch=True)
        sys.stdout.write(json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2) + "\n")
        return 0

    directives = get_grounding_directives(keywords=args.keywords, limit=args.limit, db_path=db_path, touch=True)
    if directives:
        sys.stdout.write(directives + "\n")
    else:
        sys.stdout.write("No grounding directives found matching query.\n")
    return 0


def _handle_park(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles task parking subcommand."""
    try:
        payload_data = json.loads(args.payload)
    except json.JSONDecodeError:
        payload_data = {"raw": args.payload}
    parked = park_task(
        task_id=args.id,
        title=args.title,
        reason=args.reason,
        description=args.desc,
        payload=payload_data,
        db_path=db_path,
    )
    sys.stdout.write(json.dumps(asdict(parked), ensure_ascii=False, indent=2) + "\n")
    return 0


def _handle_unpark(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles task unparking subcommand."""
    unparked = unpark_task(task_id=args.id, db_path=db_path)
    if unparked is None:
        sys.stderr.write(f"Task '{args.id}' not found in cortex vault.\n")
        return 1
    sys.stdout.write(json.dumps(asdict(unparked), ensure_ascii=False, indent=2) + "\n")
    return 0


def _handle_list_parked(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles listing vaulted tasks subcommand."""
    tasks = list_parked_tasks(status=args.status, db_path=db_path)
    if args.json:
        sys.stdout.write(json.dumps([asdict(t) for t in tasks], ensure_ascii=False, indent=2) + "\n")
        return 0

    sys.stdout.write(f"Cortex Vault contains {len(tasks)} task(s) with status '{args.status}':\n")
    for t in tasks:
        sys.stdout.write(f"- [{t.status}] {t.task_id}: {t.title} (Reason: {t.reason})\n")
    return 0


def _handle_stats(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles telemetry statistics subcommand."""
    stats = get_cortex_stats(db_path=db_path)
    if args.json:
        sys.stdout.write(json.dumps(asdict(stats), ensure_ascii=False, indent=2) + "\n")
        return 0

    sys.stdout.write(
        "================================================================================\n"
        "  CORTEX PERSISTENCE & MEMORY TELEMETRY\n"
        "================================================================================\n"
        f"Episodic Events:       {stats.total_episodic_events} total "
        f"({stats.success_events} success, {stats.failure_events} failure)\n"
        f"Parked Tasks Vault:    {stats.active_parked_tasks} active / {stats.total_parked_tasks} total\n"
        f"Document Revisions:    {stats.contract_revisions} contracts | "
        f"{stats.state_revisions} state | {stats.architecture_revisions} architecture\n"
        "================================================================================\n"
    )
    return 0


def _handle_vacuum(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles decay vacuuming subcommand."""
    pruned = vacuum_decay(
        half_life_hours=args.half_life,
        min_weight=args.min_weight,
        min_frequency=args.min_frequency,
        db_path=db_path,
    )
    sys.stdout.write(f"VACUUM_COMPLETE: Pruned {pruned} stale trace(s)\n")
    return 0


def _handle_evict_contract(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles contract eviction subcommand."""
    res = trigger_contract_eviction(Path(args.dir), capacity=args.capacity, db_path=db_path)
    sys.stdout.write(json.dumps(res.__dict__, ensure_ascii=False, indent=2) + "\n")
    return 0


def _handle_evict_state(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles state ledger eviction subcommand."""
    res = trigger_state_eviction(Path(args.dir), capacity=args.capacity, db_path=db_path)
    sys.stdout.write(json.dumps(res.__dict__, ensure_ascii=False, indent=2) + "\n")
    return 0


def _handle_evict_arch(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles architecture blueprint eviction subcommand."""
    res = trigger_architecture_eviction(Path(args.dir), capacity=args.capacity, db_path=db_path)
    sys.stdout.write(json.dumps(res.__dict__, ensure_ascii=False, indent=2) + "\n")
    return 0


def _handle_restore(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles document restoration subcommand."""
    res = restore_archive(args.domain, args.id, Path(args.out), db_path=db_path)
    sys.stdout.write(json.dumps(res.__dict__, ensure_ascii=False, indent=2) + "\n")
    return 0 if res.verified else 1


def _handle_compact_ledger(args: argparse.Namespace, db_path: Optional[Path]) -> int:
    """Handles state ledger compaction subcommand."""
    res = compact_state_ledger(
        ledger_path=Path(args.ledger),
        archive_dir=Path(args.archive_dir),
        threshold=args.threshold,
        keep_recent=args.keep,
        db_path=db_path,
        force=args.force,
    )
    if args.json:
        sys.stdout.write(json.dumps(res.to_dict(), ensure_ascii=False, indent=2) + "\n")
        return 0
    if res.compacted:
        sys.stdout.write(
            f"STATE_COMPACTED: {res.pruned_count} task(s) archived to {res.archive_path} "
            f"(Snapshot: {res.snapshot_id})\n"
        )
    else:
        sys.stdout.write(f"STATE_SKIPPED: {res.explanation}\n")
    return 0


COMMAND_HANDLERS: Dict[str, Callable[[argparse.Namespace, Optional[Path]], int]] = {
    "init": _handle_init,
    "record": _handle_record,
    "query": _handle_query,
    "ground": _handle_ground,
    "park-task": _handle_park,
    "unpark-task": _handle_unpark,
    "list-parked": _handle_list_parked,
    "stats": _handle_stats,
    "vacuum": _handle_vacuum,
    "evict-contract": _handle_evict_contract,
    "evict-state": _handle_evict_state,
    "evict-arch": _handle_evict_arch,
    "restore": _handle_restore,
    "compact-ledger": _handle_compact_ledger,
    "export-seed": _handle_export_seed,
    "hydrate-seed": _handle_hydrate_seed,
}


def main(argv: Optional[List[str]] = None) -> int:
    """CLI execution entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.db) if getattr(args, "db", None) else None
    handler = COMMAND_HANDLERS.get(args.command)
    if handler is not None:
        return handler(args, db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
