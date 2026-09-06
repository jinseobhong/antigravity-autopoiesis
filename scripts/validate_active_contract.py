"""
Active Contract Lifecycle and Invariant Validation Gate (scripts.validate_active_contract).

Enforces that docs/active/ACTIVE_CONTRACT.md exists, contains valid YAML frontmatter,
holds ACCEPTED status, and matches the active task in docs/active/CURRENT_STATE.md.
Provides programmatic contract archiving to docs/archived/.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_ROOTS = [
    os.path.abspath(os.path.join(_SCRIPT_DIR, "..")),
    os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..")),
]
for root in _CANDIDATE_ROOTS:
    if root not in sys.path:
        sys.path.insert(0, root)


def parse_contract_frontmatter(contract_path: Path) -> Dict[str, str]:
    """Parses YAML frontmatter from markdown contract file."""
    if not contract_path.exists() or not contract_path.is_file():
        return {}

    try:
        content = contract_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    if not content.startswith("---"):
        return {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}

    frontmatter_text = parts[1]
    metadata: Dict[str, str] = {}
    for line in frontmatter_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            clean_val = val.strip().strip('"').strip("'")
            metadata[key.strip()] = clean_val

    return metadata


def extract_active_task_from_ledger(ledger_path: Path) -> Optional[str]:
    """Extracts the first IN_PROGRESS task ID from CURRENT_STATE.md."""
    if not ledger_path.exists() or not ledger_path.is_file():
        return None

    try:
        content = ledger_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Search for table rows with IN_PROGRESS status
    pattern = r"\|\s*\*\*`?(TASK-\d+)`?\*\*\s*\|[^|]*\|\s*`?IN_PROGRESS`?\s*\|"
    match = re.search(pattern, content)
    if match:
        return match.group(1)

    return None


def validate_contract_state(
    contract_path: Path = Path("docs/active/ACTIVE_CONTRACT.md"),
    ledger_path: Path = Path("docs/active/CURRENT_STATE.md"),
    expected_task_id: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validates that active contract exists, has valid metadata, is ACCEPTED,
    and corresponds to the active task.
    """
    if not contract_path.exists() or not contract_path.is_file():
        return False, f"Active contract file '{contract_path}' does not exist"

    metadata = parse_contract_frontmatter(contract_path)
    if not metadata:
        return False, f"Contract '{contract_path}' is missing valid YAML frontmatter"

    required_keys = ["id", "status", "target_task_id"]
    for key in required_keys:
        if key not in metadata:
            return False, f"Contract frontmatter is missing required key '{key}'"

    status = metadata.get("status", "").upper()
    if status != "ACCEPTED":
        return False, f"Contract status is '{status}'; MUST be 'ACCEPTED' before implementation"

    contract_task = metadata.get("target_task_id", "")
    active_task = expected_task_id or extract_active_task_from_ledger(ledger_path)

    if active_task and contract_task != active_task:
        return (
            False,
            f"Contract target_task_id '{contract_task}' does not match active task '{active_task}'",
        )

    return True, None


def _archive_to_database(
    contract_path: Path,
    metadata: Dict[str, str],
    contract_id: str,
    db_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Ingests contract into cortex.db and removes file from disk."""
    try:
        from core.cortex_docs import init_cortex_db, compute_sha256, _execute_with_retry
    except ModuleNotFoundError:
        from sandbox.core.cortex_docs import init_cortex_db, compute_sha256, _execute_with_retry

    try:
        content = contract_path.read_text(encoding="utf-8")
    except OSError as err:
        return False, f"Failed to read contract: {err}"

    task_id = metadata.get("target_task_id", metadata.get("task_id", "TASK-UNASSIGNED"))
    title = metadata.get("title", contract_path.stem)
    content_hash = compute_sha256(content)
    rev_id = f"REV-CONTRACT-{int(time.time() * 1000)}-{contract_path.stem}"
    target_db = init_cortex_db(db_path)

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
        1,
        "ARCHIVED",
        content_hash,
        content,
        json.dumps(metadata, ensure_ascii=False),
        "Task promoted to production",
    )
    spool = {"table": "contract_revisions", "rev_id": rev_id}

    if _execute_with_retry(target_db, "insert_contract", sql, params, spool):
        fts_sql = "INSERT INTO fts_archive_search (domain_type, entity_id, title, raw_content) VALUES (?, ?, ?, ?);"
        _execute_with_retry(target_db, "fts_sync", fts_sql, ("contract", contract_id, title, content), spool)
        contract_path.unlink(missing_ok=True)
        return True, f"cortex.db (revision={rev_id}, id={contract_id})"

    return False, "Failed to persist contract into cortex.db"


def _archive_to_filesystem(
    contract_path: Path,
    archive_dir: Path,
    contract_id: str,
) -> Tuple[bool, str]:
    """Writes archived markdown copy to archive_dir and unlinks original."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest_path = archive_dir / f"{contract_id}.md"
    try:
        content = contract_path.read_text(encoding="utf-8")
        archived_content = re.sub(
            r'status:\s*["\']?[A-Za-z]+["\']?',
            'status: "ARCHIVED"',
            content,
            count=1,
        )
        dest_path.write_text(archived_content, encoding="utf-8")
        contract_path.unlink()
        return True, str(dest_path)
    except OSError as err:
        return False, f"Failed to archive contract to filesystem: {err}"


def archive_active_contract(
    contract_path: Path = Path("docs/active/ACTIVE_CONTRACT.md"),
    archive_dir: Optional[Path] = None,
    to_db: bool = True,
    db_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """
    Archives active contract directly into cortex.db and unlinks from disk.
    If to_db is False and archive_dir is provided, writes markdown copy to archive_dir.
    """
    if not contract_path.exists():
        return False, f"Source contract '{contract_path}' does not exist"

    metadata = parse_contract_frontmatter(contract_path)
    contract_id = metadata.get("id", "")
    if not contract_id:
        return False, "Contract missing 'id' in frontmatter; cannot name archive record"

    if to_db and archive_dir is None:
        return _archive_to_database(contract_path, metadata, contract_id, db_path)

    target_dir = archive_dir or Path("docs/archived")
    return _archive_to_filesystem(contract_path, target_dir, contract_id)


def build_parser() -> argparse.ArgumentParser:
    """Constructs CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python scripts/validate_active_contract.py",
        description="Active Contract Lifecycle and Invariant Validation Gate.",
    )
    parser.add_argument("--contract", type=str, default="docs/active/ACTIVE_CONTRACT.md")
    parser.add_argument("--ledger", type=str, default="docs/active/CURRENT_STATE.md")
    parser.add_argument("--task", type=str, default=None, help="Explicit active task ID to check")
    parser.add_argument("--archive", action="store_true", help="Archive current active contract to docs/archived/")
    parser.add_argument("--json", action="store_true", help="Output result in JSON format")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    contract_path = Path(args.contract)
    ledger_path = Path(args.ledger)

    if args.archive:
        ok, msg = archive_active_contract(contract_path)
        if args.json:
            print(json.dumps({"success": ok, "message": msg}))
        else:
            status_str = "[PASS]" if ok else "[FAIL]"
            print(f"{status_str} Archive: {msg}")
        return 0 if ok else 1

    passed, reason = validate_contract_state(
        contract_path=contract_path,
        ledger_path=ledger_path,
        expected_task_id=args.task,
    )

    if args.json:
        print(json.dumps({"passed": passed, "reason": reason}))
    else:
        if passed:
            print(f"[PASS] Active Contract '{contract_path}' satisfies all lifecycle invariants.")
        else:
            print(f"[FAIL] Active Contract rejected: {reason}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
