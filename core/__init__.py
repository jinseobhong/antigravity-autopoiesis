"""
Core Cognitive Persistence & Runtime Kernel Package.
"""

import typing

if typing.TYPE_CHECKING:
    from .fs_topology import (
        CanonicalPaths,
        PathViolation,
        TopologyAuditResult,
        audit_filesystem_topology,
        resolve_cortex_db_path,
        validate_path_conventions,
    )
from .cortex_docs import (
    ArchitectureRevision,
    ContractRevision,
    DomainEvictionResult,
    RestoreResult,
    StateRevision,
    init_cortex_db,
    restore_archive,
    trigger_architecture_eviction,
    trigger_contract_eviction,
    trigger_state_eviction,
)

__all__ = [
    "init_cortex_db",
    "ContractRevision",
    "StateRevision",
    "ArchitectureRevision",
    "DomainEvictionResult",
    "RestoreResult",
    "trigger_contract_eviction",
    "trigger_state_eviction",
    "trigger_architecture_eviction",
    "restore_archive",
    "CanonicalPaths",
    "PathViolation",
    "TopologyAuditResult",
    "audit_filesystem_topology",
    "resolve_cortex_db_path",
    "validate_path_conventions",
]

_FS_TOPOLOGY_SYMBOLS = {
    "CanonicalPaths",
    "PathViolation",
    "TopologyAuditResult",
    "audit_filesystem_topology",
    "resolve_cortex_db_path",
    "validate_path_conventions",
}


def __getattr__(name: str) -> typing.Any:
    """Lazy-loads fs_topology symbols to avoid runpy package import collisions."""
    if name in _FS_TOPOLOGY_SYMBOLS:
        from . import fs_topology

        return getattr(fs_topology, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
