"""Execution policy and explicitly supplied ownership/workspace dependencies."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from auth import ExecutionUnavailable, OwnershipStore, auth_mode, registration_enabled
from .network import NETWORK_TOOLS
from .embeddings import TOOLS as EMBEDDING_TOOLS

SERVICE_TOOLS = frozenset({'knowledge_ingest', 'knowledge_status', 'knowledge_retrieve'})


@dataclass(frozen=True)
class WorkspaceAccess:
    """Trusted dependencies supplied by the application, never by tool arguments."""

    ownership: OwnershipStore
    workspaces_root: Path

    @property
    def metadata_root(self) -> Path:
        return self.ownership.root

    def workspace(self, session_id: str) -> Path:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', session_id):
            raise ValueError('Invalid session_id.')
        self.ownership.require(session_id)
        root = self.workspaces_root / session_id
        if root.is_symlink():
            raise ValueError('Workspace roots cannot be symbolic links.')
        return root


IMAGE = 'bioagent-worker:local'
from .limits import setting
WORKER_TIMEOUT = setting('WORKER_TIMEOUT_SECONDS', 180)
# Functions execute in disposable containers. Public retrieval uses a bounded
# provider protocol over stdin/stdout; containers still have no network interface.
OFFLINE_TOOLS = frozenset({
    'file_inspection', 'document_read', 'workspace_search', 'report_write',
    'code_inspection', 'code_edit', 'code_test', 'python_execute',
    'table_profile', 'table_group', 'table_plot',
    'sequence_stats', 'sequence_find_orfs', 'sequence_translate', 'sequence_reverse_complement',
    'structure_inspect', 'genome_read_features', 'genome_render_map',
})
SPECIALISTS = frozenset({'coding_specialist', 'document_specialist', 'data_analysis_specialist', 'website_guide_specialist', 'research_specialist', 'report_review', 'report_synthesize'})
ISOLATED_TOOLS = OFFLINE_TOOLS | NETWORK_TOOLS | EMBEDDING_TOOLS | SERVICE_TOOLS


def isolated_execution() -> bool:
    default = 'docker' if auth_mode() != 'local' else 'local'
    backend = os.getenv('AGENT_WORKER_BACKEND', default)
    if backend not in {'docker', 'local'}:
        raise ExecutionUnavailable('AGENT_WORKER_BACKEND must be docker or local.')
    return backend == 'docker'


def require_execution_policy() -> None:
    if auth_mode() == "local":
        return
    from .supervisor import ensure_available
    if isolated_execution():
        ensure_available()
        return
    if registration_enabled() or os.getenv("AGENT_ALLOW_SHARED_EXECUTION") != "true":
        raise ExecutionUnavailable(
            "Multi-user execution requires Docker workers. Shared execution requires disabled registration "
            "and AGENT_ALLOW_SHARED_EXECUTION=true for trusted accounts only."
        )
