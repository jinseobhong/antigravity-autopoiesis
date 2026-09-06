"""
Core Cognitive Persistence & Runtime Kernel Package.
"""

import typing

if typing.TYPE_CHECKING:
    from .agent_runner import (
        EXIT_CODE_DEFECTS,
        EXIT_CODE_ERROR,
        EXIT_CODE_ON_HOLD,
        EXIT_CODE_SUCCESS,
        EXIT_CODE_TIMEOUT,
        AgentExecutionBounds,
        AgentExecutionResult,
        AgentManifest,
        execute_agent_subprocess,
        execute_review_panel,
        list_available_agents,
        parse_agent_manifest,
    )
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
    "AgentExecutionBounds",
    "AgentManifest",
    "AgentExecutionResult",
    "parse_agent_manifest",
    "list_available_agents",
    "execute_agent_subprocess",
    "execute_review_panel",
    "EXIT_CODE_SUCCESS",
    "EXIT_CODE_DEFECTS",
    "EXIT_CODE_ON_HOLD",
    "EXIT_CODE_TIMEOUT",
    "EXIT_CODE_ERROR",
]

_AGENT_RUNNER_SYMBOLS = {
    "EXIT_CODE_DEFECTS",
    "EXIT_CODE_ERROR",
    "EXIT_CODE_ON_HOLD",
    "EXIT_CODE_SUCCESS",
    "EXIT_CODE_TIMEOUT",
    "AgentExecutionBounds",
    "AgentExecutionResult",
    "AgentManifest",
    "execute_agent_subprocess",
    "execute_review_panel",
    "list_available_agents",
    "parse_agent_manifest",
}


_FS_TOPOLOGY_SYMBOLS = {
    "CanonicalPaths",
    "PathViolation",
    "TopologyAuditResult",
    "audit_filesystem_topology",
    "resolve_cortex_db_path",
    "validate_path_conventions",
}


def __getattr__(name: str) -> typing.Any:
    """Lazy-loads agent_runner and fs_topology symbols to avoid runpy package import collisions."""
    if name in _AGENT_RUNNER_SYMBOLS:
        from . import agent_runner

        return getattr(agent_runner, name)
    if name in _FS_TOPOLOGY_SYMBOLS:
        from . import fs_topology

        return getattr(fs_topology, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
