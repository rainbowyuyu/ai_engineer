from __future__ import annotations

import asyncio
import threading
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from backend.jobs.models import Job, JobStatus
from backend.pydantic_compat import model_copy_update, model_to_dict
from backend.tools.beso import run_beso_job


class JobManager:
    def __init__(self, runs_root: Path):
        self._runs_root = runs_root
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._cancel_flags: Dict[str, threading.Event] = {}

    def create_job(
        self,
        user_message: str,
        inp_path: Optional[str],
        mass_goal_ratio: float,
        filter_radius: float,
        optimization_base: str,
        save_every: int,
        generated_code_files: Optional[list[str]] = None,
        selected_inputs: Optional[dict[str, Any]] = None,
    ) -> Job:
        job_id = uuid.uuid4().hex
        job_dir = (self._runs_root / job_id).resolve()
        job_dir.mkdir(parents=True, exist_ok=True)

        job = Job(
            id=job_id,
            created_at=time.time(),
            status=JobStatus.created,
            user_message=user_message,
            inp_path=inp_path,
            mass_goal_ratio=mass_goal_ratio,
            filter_radius=filter_radius,
            optimization_base=optimization_base,
            save_every=save_every,
            run_dir=str(job_dir),
            logs=[],
            latest_vtk_url=None,
            artifacts=[],
            generated_code_files=generated_code_files or [],
            selected_inputs=selected_inputs,
        )
        with self._lock:
            self._jobs[job_id] = job
            self._subscribers.setdefault(job_id, [])
            self._cancel_flags[job_id] = threading.Event()
        return job

    def get_job(self, job_id: str) -> Job:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self._jobs[job_id]

    def start_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job.status in (JobStatus.running, JobStatus.completed):
            return

        cancel_flag = self._cancel_flags[job_id]
        cancel_flag.clear()

        t = threading.Thread(target=self._run_job_thread, args=(job_id,), daemon=True)
        with self._lock:
            self._jobs[job_id] = model_copy_update(job, {"status": JobStatus.running})
        t.start()
        self._emit(job_id, {"type": "status", "status": "running"})

    def cancel_job(self, job_id: str) -> None:
        with self._lock:
            flag = self._cancel_flags.get(job_id)
        if flag:
            flag.set()
        self._emit(job_id, {"type": "status", "status": "cancelling"})

    def set_generated_code_files(self, job_id: str, files: list[str]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = model_copy_update(job, {"generated_code_files": files})

    def set_selected_inputs(self, job_id: str, selected_inputs: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = model_copy_update(job, {"selected_inputs": selected_inputs})

    async def subscribe(self, job_id: str) -> AsyncIterator[Dict[str, Any]]:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(q)
            job = self._jobs.get(job_id)
        if job:
            yield {"type": "snapshot", "job": model_to_dict(job)}
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            with self._lock:
                if job_id in self._subscribers and q in self._subscribers[job_id]:
                    self._subscribers[job_id].remove(q)

    def _emit(self, job_id: str, event: Dict[str, Any]) -> None:
        with self._lock:
            qs = list(self._subscribers.get(job_id, []))
        for q in qs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def _append_log(self, job_id: str, line: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            logs = list(job.logs)
            logs.append(line)
            self._jobs[job_id] = model_copy_update(job, {"logs": logs})
        self._emit(job_id, {"type": "log", "line": line})

    def _update_vtk(self, job_id: str, vtk_url: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = model_copy_update(job, {"latest_vtk_url": vtk_url})
        self._emit(job_id, {"type": "vtk", "url": vtk_url})

    def _emit_artifact(self, job_id: str, kind: str, url: str, name: str, meta: dict | None = None) -> None:
        evt = {"type": "artifact", "kind": kind, "url": url, "name": name}
        if meta:
            evt["meta"] = meta
        with self._lock:
            job = self._jobs[job_id]
            artifacts = list(job.artifacts)
            artifacts.append(evt)
            self._jobs[job_id] = model_copy_update(job, {"artifacts": artifacts})
        self._emit(job_id, evt)

    def _set_status(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = model_copy_update(job, {"status": status})
        self._emit(job_id, {"type": "status", "status": status.value})

    def _run_job_thread(self, job_id: str) -> None:
        job = self.get_job(job_id)
        cancel_flag = self._cancel_flags[job_id]
        run_dir = Path(job.run_dir)

        def on_log(line: str) -> None:
            self._append_log(job_id, line)

        def on_vtk(rel_path: str) -> None:
            safe_rel = rel_path.replace("\\", "/")
            url = f"/runs/{job_id}/{safe_rel}"
            self._update_vtk(job_id, url)
            # keep old event for backwards-compat
            self._emit_artifact(job_id, "mesh", url, rel_path)

        def on_artifact(payload: dict) -> None:
            kind = payload.get("kind", "mesh")
            rel_path = payload.get("path", "")
            name = payload.get("name", rel_path)
            safe_rel = str(rel_path).replace("\\", "/")
            url = f"/runs/{job_id}/{safe_rel}"
            self._emit_artifact(job_id, kind, url, name, payload.get("meta"))

        try:
            for code_name in job.generated_code_files:
                p = run_dir / code_name
                if p.exists():
                    kind = "manifest" if code_name.endswith(".json") else "code"
                    self._emit_artifact(
                        job_id,
                        kind,
                        f"/runs/{job_id}/{code_name}",
                        code_name,
                        {"group": "generated"},
                    )

            runtime_py = sorted([p for p in run_dir.glob("*.py") if p.name not in set(job.generated_code_files)])
            for p in runtime_py:
                self._emit_artifact(
                    job_id,
                    "code",
                    f"/runs/{job_id}/{p.name}",
                    p.name,
                    {"group": "runtime"},
                )

            run_beso_job(
                workspace_root=self._runs_root.parent,
                run_dir=run_dir,
                inp_path=job.inp_path,
                mass_goal_ratio=job.mass_goal_ratio,
                filter_radius=job.filter_radius,
                optimization_base=job.optimization_base,
                save_every=job.save_every,
                cancel_flag=cancel_flag,
                on_log=on_log,
                on_vtk=on_vtk,
                on_artifact=on_artifact,
            )
            if cancel_flag.is_set():
                self._set_status(job_id, JobStatus.cancelled)
            else:
                self._set_status(job_id, JobStatus.completed)
        except Exception as e:
            self._append_log(job_id, f"[ERROR] {e}")
            self._set_status(job_id, JobStatus.failed)


def _default_runs_root() -> Path:
    import os

    return Path(os.environ.get("WORKSPACE_ROOT", r"D:\python_project\beso_ai")).resolve() / "runs"


jobs = JobManager(_default_runs_root())

