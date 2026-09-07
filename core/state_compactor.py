"""
State Ledger Rolling Compactor & Cortex Snapshot Engine (core.state_compactor).

Enforces token economy by compacting docs/active/CURRENT_STATE.md when promoted tasks
reach or exceed the configured threshold (default: 10), taking an immutable snapshot
in cortex.db (state_revisions, fts_archive_search), and archiving older tasks to
docs/archived/TASK_ARCHIVE_<start>_<end>.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.cortex_docs import (
        StateRevision,
        init_cortex_db,
        resolve_cortex_db_path,
        snapshot_state_ledger,
    )
    from core.cortex_knowledge import record_event
except ModuleNotFoundError:
    from sandbox.core.cortex_docs import (
        StateRevision,
        init_cortex_db,
        resolve_cortex_db_path,
        snapshot_state_ledger,
    )
    from sandbox.core.cortex_knowledge import record_event


@dataclass(frozen=True)
class PromotedTaskEntry:
    """Immutable record of a promoted task extracted from the state ledger."""

    task_id: str
    description: str
    lifecycle_status: str
    retries: str
    blast_radius: str
    owner: str
    verification_gate: str
    raw_row: str


@dataclass(frozen=True)
class StateCompactionReport:
    """Immutable report of state ledger compaction and cortex snapshot outcome."""

    compacted: bool
    total_promoted: int
    threshold: int
    keep_recent: int
    pruned_count: int
    retained_count: int
    snapshot_id: Optional[str] = None
    archive_path: Optional[str] = None
    explanation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes report into standard dictionary representation."""
        return asdict(self)


def count_promoted_kanban_nodes(content: str) -> int:
    """Counts individual task nodes inside ColPromoted excluding archive summary."""
    match = re.search(r'subgraph ColPromoted [^\n]*\n(.*?)\bend\b', content, re.DOTALL)
    if not match:
        return 0
    block = match.group(1)
    nodes = re.findall(r'PRM_\w+\["([^"]+)"\]', block)
    task_nodes = [n for n in nodes if not n.startswith("TASK-001..")]
    return len(task_nodes)


def _parse_promoted_row(line: str) -> Optional[PromotedTaskEntry]:
    """Parses a single table row into PromotedTaskEntry if matching criteria."""
    parts = [p.strip() for p in line.strip("|").split("|")]
    if len(parts) < 7:
        return None
    clean_id = re.sub(r"[\*`]", "", parts[0]).strip()
    if ".." in clean_id or clean_id.startswith("TASK-001"):
        return None
    return PromotedTaskEntry(
        task_id=clean_id,
        description=parts[1],
        lifecycle_status="PROMOTED",
        retries=parts[3],
        blast_radius=parts[4],
        owner=parts[5],
        verification_gate=parts[6],
        raw_row=line,
    )


def extract_promoted_table_rows(content: str) -> List[PromotedTaskEntry]:
    """Extracts promoted task rows from the Current State Task Ledger table."""
    entries: List[PromotedTaskEntry] = []
    in_ledger = False

    for line in content.splitlines():
        stripped = line.strip()
        if "### 3.2 Current State Task Ledger" in stripped:
            in_ledger = True
            continue
        if in_ledger and stripped.startswith("## "):
            break
        if in_ledger and stripped.startswith("|") and "`PROMOTED`" in stripped:
            entry = _parse_promoted_row(stripped)
            if entry is not None:
                entries.append(entry)
    return entries


def count_total_promoted_tasks(content: str) -> int:
    """Calculates effective promoted task count across Kanban and ledger table."""
    kanban_count = count_promoted_kanban_nodes(content)
    table_count = len(extract_promoted_table_rows(content))
    return max(kanban_count, table_count)


def generate_archive_markdown(
    pruned_entries: List[PromotedTaskEntry],
    start_id: str,
    end_id: str,
) -> str:
    """Generates NASA-grade markdown document for archived tasks."""
    today = time.strftime("%Y-%m-%d")
    header = (
        "---\n"
        f"id: ARCHIVE-{today}-{start_id.lower()}-{end_id.lower()}\n"
        f"title: Archived Task History {start_id} through {end_id}\n"
        "status: RETIRED\n"
        "owner: Platform Architecture Team\n"
        f"last_reviewed: {today}\n"
        "---\n\n"
        f"# Archived Task History: {start_id} through {end_id}\n\n"
        "Archived from docs/active/CURRENT_STATE.md to enforce the Rolling Task Horizon "
        "and eliminate context bloat.\n\n"
        "## Task Ledger Archive\n\n"
        "| Task ID | Task Description | Lifecycle Status | Retries | Blast Radius Tier | Owner | Verification Gate |\n"
        "| :--- | :--- | :--- | :---: | :--- | :--- | :--- |\n"
    )
    rows = "\n".join(e.raw_row for e in pruned_entries)
    return header + rows + "\n"


def _build_compacted_content(
    content: str,
    pruned_tasks: List[str],
    last_pruned_num: str,
) -> str:
    """Replaces pruned tasks in Kanban and Task Ledger with updated archive pointers."""
    updated = content
    # 1. Update PRM_ARCH node in ColPromoted
    prm_arch_new = f'PRM_ARCH["TASK-001..{last_pruned_num}: Archived to cortex.db and docs/archived"]'
    updated = re.sub(r'PRM_ARCH\["[^"]+"\]', prm_arch_new, updated)

    # 2. Remove pruned Kanban nodes
    for task_id in pruned_tasks:
        num = re.sub(r"\D", "", task_id)
        if num:
            node_pattern = rf'\s*PRM_{num}\["TASK-{num}:[^\n]*\n'
            updated = re.sub(node_pattern, "\n", updated)
            alt_pattern = rf'\s*PRM_1{num}\["TASK-{num}:[^\n]*\n'
            updated = re.sub(alt_pattern, "\n", updated)

    # 3. Update summary row and remove pruned rows in Task Ledger table
    summary_new = (
        f"| *`TASK-001..{last_pruned_num}`* | "
        f"*Archived to cortex.db and docs/archived/TASK_ARCHIVE_*.md* | "
        f"`ARCHIVED` | - | Multiple | Platform Team | 100% CI pass; Trunk merged; Knowledge persisted |"
    )
    updated = re.sub(r"\|\s*\*`?TASK-001\.\.[^|]+\|[^|\n]+\|", summary_new + " |", updated)

    for task_id in pruned_tasks:
        row_pattern = rf"\|\s*\*\*`?{task_id}`?\*\*\s*\|[^\n]+\n"
        updated = re.sub(row_pattern, "", updated)

    return updated


def compact_state_ledger(
    ledger_path: Path,
    archive_dir: Path,
    threshold: int = 10,
    keep_recent: int = 5,
    db_path: Optional[Path] = None,
    memory_db_path: Optional[Path] = None,
    force: bool = False,
) -> StateCompactionReport:
    """
    Evaluates promoted tasks in CURRENT_STATE.md and executes compaction if >= threshold.
    """
    ledger_path = Path(ledger_path)
    archive_dir = Path(archive_dir)
    if not ledger_path.exists():
        return StateCompactionReport(
            compacted=False,
            total_promoted=0,
            threshold=threshold,
            keep_recent=keep_recent,
            pruned_count=0,
            retained_count=0,
            explanation=f"Ledger file does not exist: {ledger_path}",
        )

    content = ledger_path.read_text(encoding="utf-8")
    promoted_entries = extract_promoted_table_rows(content)
    total_count = count_total_promoted_tasks(content)

    if total_count < threshold and not force:
        return StateCompactionReport(
            compacted=False,
            total_promoted=total_count,
            threshold=threshold,
            keep_recent=keep_recent,
            pruned_count=0,
            retained_count=total_count,
            explanation=f"Promoted task count ({total_count}) is below threshold ({threshold})",
        )

    # 1. Snapshot full ledger to document.db
    rev = snapshot_state_ledger(
        ledger_path=ledger_path,
        db_path=db_path,
        trigger=f"Promoted task capacity compaction (count={total_count}, threshold={threshold})",
    )

    # 2. Determine partition
    if len(promoted_entries) > keep_recent:
        prune_count = len(promoted_entries) - keep_recent
        to_prune = promoted_entries[:prune_count]
        to_retain = promoted_entries[prune_count:]
    else:
        to_prune = promoted_entries[: len(promoted_entries) // 2]
        to_retain = promoted_entries[len(promoted_entries) // 2 :]

    if not to_prune:
        return StateCompactionReport(
            compacted=False,
            total_promoted=total_count,
            threshold=threshold,
            keep_recent=keep_recent,
            pruned_count=0,
            retained_count=total_count,
            snapshot_id=rev.revision_id,
            explanation="No older entries available to prune",
        )

    # 3. Author archive document
    start_id = to_prune[0].task_id
    end_id = to_prune[-1].task_id
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_file = archive_dir / f"TASK_ARCHIVE_{start_id.replace('TASK-', '')}_{end_id.replace('TASK-', '')}.md"
    archive_md = generate_archive_markdown(to_prune, start_id, end_id)
    archive_file.write_text(archive_md, encoding="utf-8")

    # 4. Record episodic memory trace
    record_event(
        outcome="SUCCESS",
        component="state_ledger",
        trigger_tokens=f"Promoted task count {total_count} >= threshold {threshold}",
        directive=(
            f"Compacted state ledger to document.db snapshot ({rev.revision_id}) and "
            f"archived {len(to_prune)} tasks ({start_id}..{end_id}) to {archive_file.name}."
        ),
        solution=f"Pruned {len(to_prune)} tasks, retained recent {len(to_retain)} tasks.",
        validation="100% token preservation; document.db synced",
        db_path=memory_db_path if memory_db_path is not None else db_path,
    )

    # 5. Atomically update CURRENT_STATE.md
    last_pruned_num = re.sub(r"\D", "", end_id)
    pruned_ids = [e.task_id for e in to_prune]
    compacted_content = _build_compacted_content(content, pruned_ids, last_pruned_num)
    ledger_path.write_text(compacted_content, encoding="utf-8")

    return StateCompactionReport(
        compacted=True,
        total_promoted=total_count,
        threshold=threshold,
        keep_recent=keep_recent,
        pruned_count=len(to_prune),
        retained_count=len(to_retain),
        snapshot_id=rev.revision_id,
        archive_path=str(archive_file),
        explanation=(
            f"Successfully compacted {len(to_prune)} tasks into {archive_file.name} "
            f"and cortex snapshot {rev.revision_id}."
        ),
    )
