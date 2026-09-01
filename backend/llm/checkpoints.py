"""Process-lifetime SqliteSaver helpers (from_conn_string is a context manager)."""
from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path


def open_sqlite_saver(db_path: Path):
    """Return a long-lived SqliteSaver; caller must keep the path stable."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


@lru_cache(maxsize=8)
def get_sqlite_saver_cached(db_path: str):
    return open_sqlite_saver(Path(db_path))
