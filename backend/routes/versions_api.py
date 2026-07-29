"""Per-process git-like file versioning API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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

router = APIRouter(tags=["versions"])


class OpenProcessIn(BaseModel):
    task_id: str
    process_type: str = Field(default="generic", description="replan | candidate_select | user_edit | generic")
    label: str | None = None
    process_id: str | None = None


class CommitIn(BaseModel):
    task_id: str
    process_id: str
    message: str = ""
    file_paths: list[str] = Field(default_factory=list)
    inline: dict[str, str] = Field(default_factory=dict)
    applied_handlers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    parent: str | None = None


class CheckoutIn(BaseModel):
    task_id: str
    process_id: str
    commit_id: str
    dest_dir: str | None = None


class DiffIn(BaseModel):
    task_id: str
    process_id: str
    from_commit: str
    to_commit: str


class DemoSeedIn(BaseModel):
    """Demo hub: seed replan + candidate version lanes with sample commits."""
    task_id: str
    include_replan: bool = True
    include_candidates: bool = True


@router.post("/processes")
def versions_open_process(body: OpenProcessIn) -> dict[str, Any]:
    try:
        meta = open_process(
            body.task_id,
            process_type=body.process_type,
            label=body.label,
            process_id=body.process_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "process": meta}


@router.get("/processes")
def versions_list_processes(task_id: str) -> dict[str, Any]:
    return {"ok": True, "task_id": task_id, "processes": list_processes(task_id)}


@router.get("/handlers")
def versions_handlers(process_type: str = "generic") -> dict[str, Any]:
    return {"ok": True, "process_type": process_type, "handlers": process_handlers_for(process_type)}


@router.post("/commit")
def versions_commit(body: CommitIn) -> dict[str, Any]:
    try:
        commit = commit_files(
            body.task_id,
            body.process_id,
            message=body.message,
            file_paths=body.file_paths,
            inline=body.inline,
            applied_handlers=body.applied_handlers,
            tags=body.tags,
            parent=body.parent,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "commit": commit}


@router.get("/log")
def versions_log(task_id: str, process_id: str) -> dict[str, Any]:
    try:
        commits = list_commits(task_id, process_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "task_id": task_id, "process_id": process_id, "commits": commits}


@router.get("/show")
def versions_show(task_id: str, process_id: str, commit_id: str) -> dict[str, Any]:
    commit = get_commit(task_id, process_id, commit_id)
    if not commit:
        raise HTTPException(status_code=404, detail="提交不存在")
    return {"ok": True, "commit": commit}


@router.post("/checkout")
def versions_checkout(body: CheckoutIn) -> dict[str, Any]:
    try:
        result = checkout_commit(
            body.task_id,
            body.process_id,
            body.commit_id,
            dest_dir=body.dest_dir,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return result


@router.post("/diff")
def versions_diff(body: DiffIn) -> dict[str, Any]:
    try:
        diff = diff_commits(body.task_id, body.process_id, body.from_commit, body.to_commit)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "diff": diff}


@router.get("/tree")
def versions_tree(task_id: str) -> dict[str, Any]:
    """Aggregate all process lanes into a git-like tree for UI."""
    from backend.demo.beso7_live_pipeline import build_task_version_tree

    try:
        return build_task_version_tree(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/demo/seed")
def versions_demo_seed(body: DemoSeedIn) -> dict[str, Any]:
    """
    Seed version lanes for demo hub:
    - replan process with baseline → after-replan commits
    - candidate_select process with register → select_best commits
    """
    tid = str(body.task_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="task_id 不能为空")
    out: dict[str, Any] = {"task_id": tid, "processes": []}

    if body.include_replan:
        proc = open_process(tid, process_type="replan", label="重规划进程 · demo", process_id="replan-demo")
        c0 = commit_files(
            tid,
            proc["process_id"],
            message="v1 baseline · θ before mesh refine",
            inline={
                "theta.json": '{"characteristic_length_max": 2.5}',
                "notes.txt": "mesh quality failure — awaiting replan",
            },
            applied_handlers=["snapshot_theta"],
            tags=["baseline", "replan"],
        )
        c1 = commit_files(
            tid,
            proc["process_id"],
            message="v2 after replan · refine_mesh applied",
            inline={
                "theta.json": '{"characteristic_length_max": 1.2}',
                "notes.txt": "rho cleared after resume; handlers: mark_rho→clear_rho",
                "handlers.json": '["snapshot_theta","persist_event","mark_rho","clear_rho"]',
            },
            applied_handlers=["snapshot_theta", "persist_event", "mark_rho", "clear_rho"],
            tags=["after_replan"],
        )
        out["processes"].append({"process": proc, "commits": [c0, c1]})

    if body.include_candidates:
        from backend.candidates.registry import register_candidate

        register_candidate(tid, label="方案 A · 保守型", overall_score=82.0)
        snap_a = commit_candidate_snapshot(
            tid,
            action="register",
            candidate={"label": "方案 A · 保守型", "overall_score": 82.0},
            process_id="candidates",
            message="v1 register · 方案 A",
        )
        best = register_candidate(tid, label="方案 B · 推荐型", overall_score=88.5)
        snap_b = commit_candidate_snapshot(
            tid,
            action="register",
            candidate=best,
            process_id="candidates",
            message="v2 register · 方案 B",
        )
        snap_sel = commit_candidate_snapshot(
            tid,
            action="select_best",
            candidate=best,
            process_id="candidates",
            message="v3 select-best · 方案 B",
        )
        out["processes"].append(
            {
                "process": snap_a["process"],
                "commits": [snap_a["commit"], snap_b["commit"], snap_sel["commit"]],
            }
        )

    out["process_list"] = list_processes(tid)
    return {"ok": True, **out}
