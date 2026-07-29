"""Git-like file versioning scoped per task process (replan / candidate select)."""

from backend.versions.store import (
    checkout_commit,
    commit_candidate_snapshot,
    commit_files,
    commit_replan_snapshot,
    diff_commits,
    get_commit,
    list_commits,
    list_processes,
    open_process,
    process_handlers_for,
)

__all__ = [
    "open_process",
    "commit_files",
    "list_processes",
    "list_commits",
    "get_commit",
    "checkout_commit",
    "diff_commits",
    "process_handlers_for",
    "commit_replan_snapshot",
    "commit_candidate_snapshot",
]
