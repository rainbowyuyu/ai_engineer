from __future__ import annotations

import asyncio
import json
import re
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

    def _runs_job_dir(self, job_id: str) -> Path | None:
        """仅允许 runs_root 下的子目录，防止路径穿越。"""
        raw = str(job_id or "").strip()
        if not raw or "/" in raw or "\\" in raw or ".." in raw:
            return None
        run_dir = (self._runs_root / raw).resolve()
        try:
            run_dir.relative_to(self._runs_root.resolve())
        except ValueError:
            return None
        return run_dir if run_dir.is_dir() else None

    def _read_logs_from_run_dir(self, run_dir: Path) -> List[str]:
        logs: List[str] = []
        candidates = [p for p in run_dir.glob("*.log") if p.is_file()]
        if not candidates:
            return logs
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        log_path = candidates[0]
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return logs
        lines = text.splitlines()
        if len(lines) > 2500:
            lines = lines[-2500:]
        return [ln.rstrip("\r") for ln in lines]

    def _parse_beso_conf_numbers(self, run_dir: Path) -> tuple[float, float, str, int]:
        mass_goal_ratio = 0.3
        filter_radius = 2.0
        optimization_base = "failure_index"
        save_every = 5
        conf = run_dir / "beso_conf.py"
        if not conf.is_file():
            return mass_goal_ratio, filter_radius, optimization_base, save_every
        try:
            txt = conf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return mass_goal_ratio, filter_radius, optimization_base, save_every
        m = re.search(r"mass_goal_ratio\s*=\s*([\d.]+)", txt)
        if m:
            try:
                mass_goal_ratio = float(m.group(1))
            except ValueError:
                pass
        m = re.search(r"filter_list\s*=\s*\[\s*\(\s*['\"]simple['\"]\s*,\s*([\d.]+)", txt)
        if m:
            try:
                filter_radius = float(m.group(1))
            except ValueError:
                pass
        m = re.search(r"optimization_base\s*=\s*['\"]([^'\"]+)['\"]", txt)
        if m:
            optimization_base = m.group(1).strip().lower() or optimization_base
        m = re.search(r"save_iteration_results\s*=\s*(\d+)", txt)
        if m:
            try:
                save_every = max(1, int(m.group(1)))
            except ValueError:
                pass
        return mass_goal_ratio, filter_radius, optimization_base, save_every

    def _infer_status_from_disk(self, run_dir: Path, logs: List[str]) -> JobStatus:
        tail = "\n".join(logs[-160:]) if logs else ""
        low = tail.lower()
        if "[error]" in tail or "traceback" in low:
            return JobStatus.failed
        if (run_dir / "Mass.png").is_file():
            return JobStatus.completed
        if "optimization finished" in low or ("beso" in low and "finished" in low):
            return JobStatus.completed
        return JobStatus.completed

    def _artifacts_from_disk(self, job_id: str, run_dir: Path) -> List[dict[str, Any]]:
        arts: List[dict[str, Any]] = []
        gen_names = [
            "task_manifest.json",
            "input_router.py",
            "strategy.py",
            "beso_conf.py",
            "run_generated.py",
        ]
        skip_py = set(gen_names) | {"beso_main.py"}
        for name in gen_names:
            if (run_dir / name).is_file():
                kind = "manifest" if name.endswith(".json") else "code"
                arts.append(
                    {
                        "type": "artifact",
                        "kind": kind,
                        "url": f"/runs/{job_id}/{name}",
                        "name": name,
                        "meta": {"group": "generated"},
                    }
                )
        for p in sorted(run_dir.glob("*.py")):
            if p.name in skip_py:
                continue
            arts.append(
                {
                    "type": "artifact",
                    "kind": "code",
                    "url": f"/runs/{job_id}/{p.name}",
                    "name": p.name,
                    "meta": {"group": "runtime"},
                }
            )
        for img in ("Mass.png", "FI_mean.png", "FI_max.png", "FI_violated.png"):
            if (run_dir / img).is_file():
                arts.append(
                    {"type": "artifact", "kind": "image", "url": f"/runs/{job_id}/{img}", "name": img}
                )
        vtk_pat = re.compile(r"^file(\d+)\.vtk$", re.I)
        best_vtk: tuple[int, str] | None = None
        for p in run_dir.glob("file*.vtk"):
            m = vtk_pat.match(p.name)
            if not m:
                continue
            n = int(m.group(1))
            if best_vtk is None or n > best_vtk[0]:
                best_vtk = (n, p.name)
        if best_vtk:
            name = best_vtk[1]
            arts.append(
                {"type": "artifact", "kind": "mesh", "url": f"/runs/{job_id}/{name}", "name": name}
            )
        rs = run_dir / "resulting_states.vtk"
        if rs.is_file() and not best_vtk:
            arts.append(
                {
                    "type": "artifact",
                    "kind": "mesh",
                    "url": f"/runs/{job_id}/resulting_states.vtk",
                    "name": "resulting_states.vtk",
                }
            )
        return arts

    def _latest_vtk_url(self, job_id: str, run_dir: Path) -> Optional[str]:
        vtk_pat = re.compile(r"^file(\d+)\.vtk$", re.I)
        best: tuple[int, str] | None = None
        for p in run_dir.glob("file*.vtk"):
            m = vtk_pat.match(p.name)
            if not m:
                continue
            n = int(m.group(1))
            if best is None or n > best[0]:
                best = (n, p.name)
        if best:
            return f"/runs/{job_id}/{best[1]}"
        if (run_dir / "resulting_states.vtk").is_file():
            return f"/runs/{job_id}/resulting_states.vtk"
        return None

    def _build_job_from_disk(self, job_id: str) -> Optional[Job]:
        run_dir = self._runs_job_dir(job_id)
        if run_dir is None:
            return None
        manifest: dict[str, Any] = {}
        mf = run_dir / "task_manifest.json"
        if mf.is_file():
            try:
                raw = json.loads(mf.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    manifest = raw
            except (OSError, json.JSONDecodeError):
                manifest = {}
        inp_path: Optional[str] = None
        if manifest.get("primary_inp"):
            inp_path = str(manifest["primary_inp"])
        if not inp_path:
            inps = sorted([p for p in run_dir.glob("*.inp") if p.is_file()], key=lambda p: p.name)
            if inps:
                inp_path = inps[0].name
        mass_goal_ratio, filter_radius, optimization_base, save_every = self._parse_beso_conf_numbers(run_dir)
        logs = self._read_logs_from_run_dir(run_dir)
        status = self._infer_status_from_disk(run_dir, logs)
        artifacts = self._artifacts_from_disk(job_id, run_dir)
        latest_vtk = self._latest_vtk_url(job_id, run_dir)
        gen_files = [n for n in (
            "task_manifest.json",
            "input_router.py",
            "strategy.py",
            "beso_conf.py",
            "run_generated.py",
        ) if (run_dir / n).is_file()]
        selected: dict[str, Any] | None = None
        if manifest.get("primary_inp") is not None:
            selected = {
                "primary_inp": manifest.get("primary_inp"),
                "aux_inps": manifest.get("aux_inps") or {},
                "step_mapping": manifest.get("step_mapping") or {},
            }
        try:
            created_at = run_dir.stat().st_mtime
        except OSError:
            created_at = time.time()
        return Job(
            id=job_id,
            created_at=float(created_at),
            status=status,
            user_message="",
            inp_path=inp_path,
            mass_goal_ratio=mass_goal_ratio,
            filter_radius=filter_radius,
            optimization_base=optimization_base,
            save_every=save_every,
            run_dir=str(run_dir),
            logs=logs,
            latest_vtk_url=latest_vtk,
            artifacts=artifacts,
            generated_code_files=gen_files,
            selected_inputs=selected,
        )

    def _ensure_job_loaded(self, job_id: str) -> Optional[Job]:
        """内存命中，或从 runs/<job_id> 目录恢复（进程重启后历史任务仍可 GET / WebSocket）。"""
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]
        reh = self._build_job_from_disk(job_id)
        if reh is None:
            return None
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]
            self._jobs[job_id] = reh
            self._subscribers.setdefault(job_id, [])
            self._cancel_flags.setdefault(job_id, threading.Event())
        return reh

    def get_job(self, job_id: str) -> Job:
        job = self._ensure_job_loaded(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

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
        job = self._ensure_job_loaded(job_id)
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(q)
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

