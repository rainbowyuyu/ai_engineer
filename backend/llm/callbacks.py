from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def new_run_id(prefix: str = "llm") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def log_graph_event(run_id: str, event: str, **fields: Any) -> None:
    extra = " ".join(f"{k}={v!r}" for k, v in fields.items() if v is not None)
    logger.info("[graph:%s] %s %s", run_id, event, extra)
