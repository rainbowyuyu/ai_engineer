"""Process-scoped file version store (git-like commits + handlers)."""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.versions.paths import (
    commit_dir,
    commit_files_dir,
    commit_meta_path,
    process_dir,
    process_meta_path,
    processes_index_path,
    task_versions_dir,
    workspace_root,
)

PROCESS_TYPES = ("replan", "candidate_select", "user_edit", "generic")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel_name(name: str) -> str:
    raw = str(name or "file").replace("\\", "/").strip().lstrip("/")
    parts = [p for p in raw.split("/") if p and p not in (".", "..")]
    return "/".join(parts) or "file.bin"


def process_handlers_for(process_type: str) -> list[dict[str, Any]]:
    """Declared handlers available for each process type (for UI / demo)."""
    pt = str(process_type or "generic").strip().lower()
    catalog: dict[str, list[dict[str, Any]]] = {
        "replan": [
            {"id": "snapshot_theta", "label": "快照 θ 参数", "when": "on_commit"},
            {"id": "persist_event", "label": "持久化 replan_event.json", "when": "on_commit"},
            {"id": "mark_rho", "label": "标记 ρₚ=1（相位闸）", "when": "after_commit"},
            {"id": "clear_rho", "label": "清除 ρₚ（旅程完成）", "when": "after_resume"},
            {"id": "resume_mesh", "label": "恢复体网格", "when": "checkout+resume"},
            {"id": "resume_beso", "label": "恢复 BESO 求解", "when": "checkout+resume"},
        ],
        "candidate_select": [
            {"id": "snapshot_registry", "label": "快照 candidates/registry.json", "when": "on_commit"},
            {"id": "register_candidate", "label": "登记候选方案", "when": "on_commit"},
            {"id": "select_best", "label": "选择最高分方案", "when": "on_commit"},
            {"id": "halt_archive", "label": "终止门通过后归档", "when": "after_select"},
            {"id": "audit_manifest", "label": "写入 SHA-256 审计清单", "when": "after_select"},
        ],
        "user_edit": [
            {"id": "snapshot_files", "label": "快照用户修改文件", "when": "on_commit"},
            {"id": "checkout_restore", "label": "检出恢复到工作区", "when": "on_demand"},
        ],
        "generic": [
            {"id": "snapshot_files", "label": "快照文件", "when": "on_commit"},
            {"id": "checkout_restore", "label": "检出恢复", "when": "on_demand"},
        ],
    }
    return list(catalog.get(pt) or catalog["generic"])


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _index_add_process(task_id: str, meta: dict[str, Any]) -> None:
    idx_path = processes_index_path(task_id)
    idx = _load_json(idx_path, {"task_id": task_id, "processes": []})
    procs = list(idx.get("processes") or [])
    procs = [p for p in procs if p.get("process_id") != meta.get("process_id")]
    procs.insert(0, {
        "process_id": meta["process_id"],
        "process_type": meta["process_type"],
        "label": meta["label"],
        "created_at": meta["created_at"],
        "HEAD": meta.get("HEAD"),
        "commit_count": meta.get("commit_count", 0),
    })
    idx["processes"] = procs
    idx["task_id"] = task_id
    idx["updated_at"] = _now_iso()
    _save_json(idx_path, idx)


def open_process(
    task_id: str,
    *,
    process_type: str = "generic",
    label: str | None = None,
    process_id: str | None = None,
    meta_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or reopen a process version lane for a task."""
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id 不能为空")
    pt = str(process_type or "generic").strip().lower()
    if pt not in PROCESS_TYPES:
        pt = "generic"
    pid = str(process_id or "").strip() or uuid.uuid4().hex[:12]
    meta_path = process_meta_path(tid, pid)
    if meta_path.is_file():
        meta = _load_json(meta_path, {})
        meta["handlers"] = process_handlers_for(meta.get("process_type") or pt)
        return meta

    meta = {
        "task_id": tid,
        "process_id": pid,
        "process_type": pt,
        "label": label or f"{pt}:{pid}",
        "created_at": _now_iso(),
        "HEAD": None,
        "commit_count": 0,
        "handlers": process_handlers_for(pt),
        "extra": meta_extra or {},
    }
    process_dir(tid, pid).mkdir(parents=True, exist_ok=True)
    (process_dir(tid, pid) / "commits").mkdir(parents=True, exist_ok=True)
    _save_json(meta_path, meta)
    _index_add_process(tid, meta)
    return meta


def list_processes(task_id: str) -> list[dict[str, Any]]:
    idx = _load_json(processes_index_path(task_id), {"processes": []})
    return list(idx.get("processes") or [])


def _resolve_source(src: str | Path, *, root: Path | None = None) -> Path:
    p = Path(src)
    if not p.is_absolute():
        p = (root or workspace_root()) / p
    return p.resolve()


def commit_files(
    task_id: str,
    process_id: str,
    *,
    message: str,
    files: list[dict[str, Any]] | None = None,
    file_paths: list[str] | None = None,
    inline: dict[str, str | bytes] | None = None,
    applied_handlers: list[str] | None = None,
    parent: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create a commit under a process.

    ``files``: [{logical_path, source_path?}] or use ``file_paths`` / ``inline``.
    Content is copied into commits/<id>/files/.
    """
    tid = str(task_id or "").strip()
    pid = str(process_id or "").strip()
    if not tid or not pid:
        raise ValueError("task_id / process_id 不能为空")
    meta_path = process_meta_path(tid, pid)
    if not meta_path.is_file():
        raise FileNotFoundError(f"进程不存在: {pid}")
    meta = _load_json(meta_path, {})
    parent_id = parent if parent is not None else meta.get("HEAD")
    cid = uuid.uuid4().hex[:12]
    files_out: list[dict[str, Any]] = []
    dest_root = commit_files_dir(tid, pid, cid)
    root = workspace_root()

    specs: list[dict[str, Any]] = list(files or [])
    for fp in file_paths or []:
        specs.append({"logical_path": Path(fp).name, "source_path": fp})
    for logical, content in (inline or {}).items():
        specs.append({"logical_path": logical, "content": content})

    for spec in specs:
        logical = _safe_rel_name(str(spec.get("logical_path") or spec.get("path") or "file"))
        dest = dest_root / logical
        dest.parent.mkdir(parents=True, exist_ok=True)
        if "content" in spec and spec["content"] is not None:
            raw = spec["content"]
            data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
            dest.write_bytes(data)
            digest = _sha256_bytes(data)
            size = len(data)
            source_rel = None
        else:
            src = _resolve_source(str(spec.get("source_path") or spec.get("path") or ""), root=root)
            if not src.is_file():
                raise FileNotFoundError(f"源文件不存在: {src}")
            shutil.copy2(src, dest)
            digest = _sha256_file(dest)
            size = dest.stat().st_size
            try:
                source_rel = str(src.relative_to(root)).replace("\\", "/")
            except ValueError:
                source_rel = str(src)
        files_out.append(
            {
                "path": logical,
                "sha256": digest,
                "size": size,
                "source_path": source_rel,
            }
        )

    handlers = process_handlers_for(str(meta.get("process_type") or "generic"))
    applied = list(applied_handlers or [])
    commit = {
        "commit_id": cid,
        "task_id": tid,
        "process_id": pid,
        "process_type": meta.get("process_type"),
        "parent": parent_id,
        "message": str(message or "").strip() or "(no message)",
        "created_at": _now_iso(),
        "files": files_out,
        "handlers_available": handlers,
        "handlers_applied": applied,
        "tags": list(tags or []),
        "url": f"/runs/_versions/{tid}/{pid}/commits/{cid}/commit.json",
        "files_url": f"/runs/_versions/{tid}/{pid}/commits/{cid}/files",
    }
    _save_json(commit_meta_path(tid, pid, cid), commit)

    meta["HEAD"] = cid
    meta["commit_count"] = int(meta.get("commit_count") or 0) + 1
    meta["updated_at"] = _now_iso()
    _save_json(meta_path, meta)
    _index_add_process(tid, meta)
    return commit


def list_commits(task_id: str, process_id: str) -> list[dict[str, Any]]:
    """Walk HEAD→parent chain (newest first)."""
    tid = str(task_id or "").strip()
    pid = str(process_id or "").strip()
    meta = _load_json(process_meta_path(tid, pid), {})
    head = meta.get("HEAD")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    cur = head
    while cur and cur not in seen:
        seen.add(cur)
        c = get_commit(tid, pid, cur)
        if not c:
            break
        out.append(
            {
                "commit_id": c["commit_id"],
                "parent": c.get("parent"),
                "message": c.get("message"),
                "created_at": c.get("created_at"),
                "file_count": len(c.get("files") or []),
                "handlers_applied": c.get("handlers_applied") or [],
                "tags": c.get("tags") or [],
                "url": c.get("url"),
            }
        )
        cur = c.get("parent")
    # Also include orphan commits on disk not in chain
    commits_root = process_dir(tid, pid) / "commits"
    if commits_root.is_dir():
        for d in sorted(commits_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not d.is_dir() or d.name in seen:
                continue
            c = get_commit(tid, pid, d.name)
            if c:
                out.append(
                    {
                        "commit_id": c["commit_id"],
                        "parent": c.get("parent"),
                        "message": c.get("message"),
                        "created_at": c.get("created_at"),
                        "file_count": len(c.get("files") or []),
                        "handlers_applied": c.get("handlers_applied") or [],
                        "tags": c.get("tags") or [],
                        "url": c.get("url"),
                        "orphan": True,
                    }
                )
    return out


def get_commit(task_id: str, process_id: str, commit_id: str) -> dict[str, Any] | None:
    path = commit_meta_path(task_id, process_id, commit_id)
    if not path.is_file():
        return None
    return _load_json(path, None)


def checkout_commit(
    task_id: str,
    process_id: str,
    commit_id: str,
    *,
    dest_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Restore commit files into dest_dir (default: runs/_versions/.../checkout/<commit_id>)."""
    tid = str(task_id or "").strip()
    pid = str(process_id or "").strip()
    cid = str(commit_id or "").strip()
    commit = get_commit(tid, pid, cid)
    if not commit:
        raise FileNotFoundError(f"提交不存在: {cid}")
    src_files = commit_files_dir(tid, pid, cid)
    if dest_dir is None:
        out = task_versions_dir(tid) / "_checkout" / pid / cid
    else:
        out = Path(dest_dir)
        if not out.is_absolute():
            out = workspace_root() / out
    out.mkdir(parents=True, exist_ok=True)
    restored: list[str] = []
    for ent in commit.get("files") or []:
        rel = _safe_rel_name(str(ent.get("path") or ""))
        src = src_files / rel
        if not src.is_file():
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        restored.append(rel)
    try:
        rel_out = str(out.resolve().relative_to(workspace_root())).replace("\\", "/")
    except ValueError:
        rel_out = str(out.resolve())
    return {
        "ok": True,
        "commit_id": cid,
        "process_id": pid,
        "dest_dir": rel_out,
        "dest_url": f"/{rel_out}" if not rel_out.startswith("/") else rel_out,
        "restored": restored,
        "handlers_available": commit.get("handlers_available") or process_handlers_for(str(commit.get("process_type") or "")),
    }


def diff_commits(
    task_id: str,
    process_id: str,
    from_commit: str,
    to_commit: str,
) -> dict[str, Any]:
    """Compare file sets / hashes between two commits."""
    a = get_commit(task_id, process_id, from_commit)
    b = get_commit(task_id, process_id, to_commit)
    if not a or not b:
        raise FileNotFoundError("提交不存在")
    map_a = {f["path"]: f for f in (a.get("files") or [])}
    map_b = {f["path"]: f for f in (b.get("files") or [])}
    added = sorted(set(map_b) - set(map_a))
    removed = sorted(set(map_a) - set(map_b))
    modified = sorted(
        p for p in set(map_a) & set(map_b) if map_a[p].get("sha256") != map_b[p].get("sha256")
    )
    unchanged = sorted(
        p for p in set(map_a) & set(map_b) if map_a[p].get("sha256") == map_b[p].get("sha256")
    )
    return {
        "from": from_commit,
        "to": to_commit,
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
    }


def commit_replan_snapshot(
    task_id: str,
    *,
    event_id: str | None = None,
    theta_before: dict[str, Any] | None = None,
    theta_after: dict[str, Any] | None = None,
    event_path: str | Path | None = None,
    message: str | None = None,
    process_id: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Helper: open replan process + commit θ / event artifacts."""
    label = f"重规划 · {case_id}" if case_id else "重规划进程"
    proc = open_process(
        task_id,
        process_type="replan",
        label=label,
        process_id=process_id,
        meta_extra={"case_id": case_id, "event_id": event_id},
    )
    inline: dict[str, str] = {
        "theta_before.json": json.dumps(theta_before or {}, ensure_ascii=False, indent=2),
        "theta_after.json": json.dumps(theta_after or {}, ensure_ascii=False, indent=2),
    }
    file_paths: list[str] = []
    if event_path:
        ep = Path(event_path)
        if ep.is_file():
            file_paths.append(str(ep))
    elif event_id:
        cand = workspace_root() / "runs" / "_replan" / str(event_id) / "replan_event.json"
        if cand.is_file():
            file_paths.append(str(cand))
    commit = commit_files(
        task_id,
        proc["process_id"],
        message=message or f"replan snapshot · event={event_id or 'n/a'}",
        file_paths=file_paths,
        inline=inline,
        applied_handlers=["snapshot_theta", "persist_event"],
        tags=["replan", case_id] if case_id else ["replan"],
    )
    return {"process": proc, "commit": commit}


def commit_candidate_snapshot(
    task_id: str,
    *,
    action: str,
    candidate: dict[str, Any] | None = None,
    process_id: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Helper: open candidate_select process + commit registry + entry."""
    from backend.orchestrator.paths import candidates_registry_path

    proc = open_process(
        task_id,
        process_type="candidate_select",
        label="方案选择进程",
        process_id=process_id or "candidates",
    )
    reg_path = candidates_registry_path(task_id)
    file_paths = [str(reg_path)] if reg_path.is_file() else []
    inline: dict[str, str] = {}
    if candidate:
        inline["selected_or_registered.json"] = json.dumps(candidate, ensure_ascii=False, indent=2)
    handlers = ["snapshot_registry"]
    if action == "register":
        handlers.append("register_candidate")
    elif action == "select_best":
        handlers.append("select_best")
    commit = commit_files(
        task_id,
        proc["process_id"],
        message=message or f"candidate · {action}",
        file_paths=file_paths,
        inline=inline,
        applied_handlers=handlers,
        tags=["candidate", action],
    )
    return {"process": proc, "commit": commit}
