"""Persist replan audit events under runs/_replan/."""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from backend.replan.models import ReplanEvent

_REPO_ROOT = Path(__file__).resolve().parents[2]


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT", str(_REPO_ROOT))).resolve()


def replan_root() -> Path:
    root = workspace_root() / "runs" / "_replan"
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_event_id() -> str:
    return uuid.uuid4().hex


def save_event(event: ReplanEvent) -> Path:
    eid = event.event_id or new_event_id()
    event.event_id = eid
    if not event.created_at:
        event.created_at = ReplanEvent.now_iso()
    out_dir = replan_root() / eid
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "replan_event.json"
    path.write_text(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return path.resolve()


def load_event(event_id: str) -> ReplanEvent | None:
    eid = str(event_id or "").strip()
    if not eid or not re.fullmatch(r"[a-f0-9]{32}", eid):
        return None
    path = replan_root() / eid / "replan_event.json"
    if not path.is_file():
        return None
    return ReplanEvent.model_validate(json.loads(path.read_text(encoding="utf-8")))
