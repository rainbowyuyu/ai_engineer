"""Age-based cleanup for generated data under ``WORKSPACE_ROOT/runs``.

The cleaner works on complete run units (usually a task/session directory)
instead of deleting arbitrary files from an active job.  Persistent stores such
as archives and SQLite checkpoints are protected by default.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ACTIVE_STATUSES = frozenset({"running", "cancelling", "queued", "pending", "in_progress"})
_KEEP_MARKERS = frozenset({".cleanup-keep", ".keep", ".retain", ".no-cleanup"})
_PROTECTED_ROOTS = frozenset({"_archive", "_checkpoints", "_surrogate_models"})
_PROTECTED_FILES = {
    "_tasks": frozenset({"index.json"}),
}
_DEFAULT_RETENTION_DAYS = 30.0
_DEFAULT_INTERVAL_HOURS = 24.0
_DEFAULT_STARTUP_DELAY_SECONDS = 60.0
_DEFAULT_MAX_ITEMS = 1000
_LOCK_NAME = ".runs_cleanup.lock"
_LOCK_STALE_AFTER_SECONDS = 6 * 60 * 60


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, *, minimum: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if raw:
        try:
            return max(minimum, float(raw))
        except ValueError:
            logger.warning("Invalid %s=%r; using %s", name, raw, default)
    return default


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if raw:
        try:
            return max(minimum, min(maximum, int(raw)))
        except ValueError:
            logger.warning("Invalid %s=%r; using %s", name, raw, default)
    return default


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _parse_iso(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def default_runs_root() -> Path:
    """Resolve the same runs directory used by the web application."""
    root = Path(os.environ.get("WORKSPACE_ROOT", str(_REPO_ROOT))).expanduser().resolve()
    return root / "runs"


@dataclass(frozen=True)
class RunsCleanupConfig:
    enabled: bool = True
    retention_days: float = _DEFAULT_RETENTION_DAYS
    interval_hours: float = _DEFAULT_INTERVAL_HOURS
    startup_delay_seconds: float = _DEFAULT_STARTUP_DELAY_SECONDS
    include_archives: bool = False
    max_items: int = _DEFAULT_MAX_ITEMS

    @classmethod
    def from_env(cls) -> "RunsCleanupConfig":
        return cls(
            enabled=_env_bool("RUNS_CLEANUP_ENABLED", True),
            retention_days=_env_float(
                "RUNS_CLEANUP_RETENTION_DAYS",
                _DEFAULT_RETENTION_DAYS,
                minimum=0.01,
            ),
            interval_hours=_env_float(
                "RUNS_CLEANUP_INTERVAL_HOURS",
                _DEFAULT_INTERVAL_HOURS,
                minimum=0.01,
            ),
            startup_delay_seconds=_env_float(
                "RUNS_CLEANUP_STARTUP_DELAY_SECONDS",
                _DEFAULT_STARTUP_DELAY_SECONDS,
                minimum=0.0,
            ),
            include_archives=_env_bool("RUNS_CLEANUP_INCLUDE_ARCHIVES", False),
            max_items=_env_int(
                "RUNS_CLEANUP_MAX_ITEMS",
                _DEFAULT_MAX_ITEMS,
                minimum=1,
                maximum=100_000,
            ),
        )

    def with_overrides(self, **overrides: Any) -> "RunsCleanupConfig":
        values = asdict(self)
        for key in ("retention_days", "interval_hours", "startup_delay_seconds"):
            if overrides.get(key) is not None:
                values[key] = max(0.01 if key != "startup_delay_seconds" else 0.0, float(overrides[key]))
        if overrides.get("include_archives") is not None:
            values["include_archives"] = bool(overrides["include_archives"])
        if overrides.get("max_items") is not None:
            values["max_items"] = max(1, min(100_000, int(overrides["max_items"])))
        return RunsCleanupConfig(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _PathInfo:
    path: Path
    kind: str
    size_bytes: int
    latest_mtime: float


class RunsCleaner:
    """Preview and remove stale run units with conservative safety guards."""

    def __init__(self, runs_root: Path | None = None):
        self.runs_root = (runs_root or default_runs_root()).expanduser().resolve()
        self._run_lock = threading.Lock()

    def _validate_root(self) -> None:
        if self.runs_root.name.lower() != "runs":
            raise ValueError(f"Refusing to clean a directory that is not named runs: {self.runs_root}")
        if self.runs_root == self.runs_root.parent:
            raise ValueError(f"Invalid runs root: {self.runs_root}")
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def _under_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.runs_root)
            return True
        except ValueError:
            return False

    def _path_info(self, path: Path) -> _PathInfo | None:
        try:
            if path.is_symlink():
                return None
            stat = path.stat()
        except OSError:
            return None

        latest = float(stat.st_mtime)
        total = int(stat.st_size) if path.is_file() else 0
        if path.is_dir():
            try:
                for child in path.rglob("*"):
                    if child.is_symlink():
                        continue
                    try:
                        child_stat = child.stat()
                    except OSError:
                        continue
                    latest = max(latest, float(child_stat.st_mtime))
                    if child.is_file():
                        total += int(child_stat.st_size)
            except OSError:
                pass
            kind = "directory"
        elif path.is_file():
            kind = "file"
        else:
            return None
        return _PathInfo(path=path, kind=kind, size_bytes=total, latest_mtime=latest)

    def _json_objects(self, path: Path) -> Iterator[dict[str, Any]]:
        if path.is_file() and path.name.lower() in {"status.json", "retention.json", "session.json"}:
            candidates = [path]
        elif path.is_dir():
            candidates = []
            for name in ("status.json", "retention.json", "session.json"):
                candidates.extend(path.rglob(name))
        else:
            candidates = []
        for candidate in candidates:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError, TypeError):
                continue
            if isinstance(raw, dict):
                yield raw

    def _has_keep_marker(self, path: Path) -> bool:
        if path.name in _KEEP_MARKERS:
            return True
        if not path.is_dir():
            return False
        try:
            return any(item.name in _KEEP_MARKERS for item in path.rglob("*"))
        except OSError:
            return False

    def _is_protected(self, path: Path, *, config: RunsCleanupConfig) -> tuple[bool, str]:
        if not self._under_root(path):
            return True, "outside_runs_root"
        rel_parts = path.relative_to(self.runs_root).parts
        if not rel_parts:
            return True, "runs_root"
        root_name = rel_parts[0]
        if root_name in _PROTECTED_ROOTS:
            if root_name == "_archive" and config.include_archives:
                pass
            else:
                return True, f"protected_root:{root_name}"
        if path.is_file() and path.name in _PROTECTED_FILES.get(root_name, frozenset()):
            return True, f"protected_file:{root_name}/{path.name}"
        if path.name == _LOCK_NAME:
            return True, "cleanup_lock"
        if self._has_keep_marker(path):
            return True, "keep_marker"

        for meta in self._json_objects(path):
            if bool(meta.get("keep")) or bool(meta.get("retain")):
                return True, "retention_keep"
            keep_until = _parse_iso(meta.get("keep_until") or meta.get("retain_until"))
            if keep_until is not None and keep_until > time.time():
                return True, "retention_keep_until"
            status = str(meta.get("status") or "").strip().lower()
            if status in _ACTIVE_STATUSES:
                return True, f"active_status:{status}"
            if meta.get("done") is False and ("progress" in meta or "stage" in meta):
                return True, "active_progress"
            if any(bool(meta.get(key)) for key in ("active", "running", "in_progress")):
                return True, "active_metadata"

        if path.is_dir():
            for marker in (".running", ".active", "RUNNING"):
                if (path / marker).exists():
                    return True, f"active_marker:{marker}"
        return False, ""

    def _candidate_paths(self, *, config: RunsCleanupConfig) -> Iterator[Path]:
        try:
            top_level = sorted(self.runs_root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return

        for entry in top_level:
            if entry.is_symlink():
                continue
            if entry.name in _PROTECTED_ROOTS and not (
                entry.name == "_archive" and config.include_archives
            ):
                yield entry
                continue
            if entry.is_dir() and entry.name.startswith("_"):
                try:
                    children = sorted(entry.iterdir(), key=lambda p: p.name.lower())
                except OSError:
                    continue
                for child in children:
                    if child.name in _PROTECTED_FILES.get(entry.name, frozenset()):
                        continue
                    if not child.is_symlink():
                        yield child
            else:
                yield entry

    @contextmanager
    def _process_lock(self) -> Iterator[bool]:
        lock_path = self.runs_root / _LOCK_NAME
        acquired = False
        fd: int | None = None
        try:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    stale = time.time() - lock_path.stat().st_mtime > _LOCK_STALE_AFTER_SECONDS
                except OSError:
                    stale = False
                if stale:
                    try:
                        lock_path.unlink()
                        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    except (FileExistsError, OSError):
                        fd = None
                if fd is None:
                    yield False
                    return
            os.write(fd, f"pid={os.getpid()}\ncreated_at={_iso(time.time())}\n".encode("ascii"))
            acquired = True
            yield True
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if acquired:
                try:
                    lock_path.unlink()
                except OSError:
                    pass

    def _report_base(
        self,
        *,
        config: RunsCleanupConfig,
        now: float,
        dry_run: bool,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "runs_root": str(self.runs_root),
            "started_at": _iso(now),
            "finished_at": None,
            "dry_run": dry_run,
            "retention_days": config.retention_days,
            "cutoff_at": _iso(now - config.retention_days * 86400),
            "include_archives": config.include_archives,
            "deleted_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "reclaimed_bytes": 0,
            "items": [],
            "skipped": [],
            "errors": [],
        }

    def cleanup(
        self,
        *,
        config: RunsCleanupConfig | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Delete stale items, or return the exact deletion plan when dry-running."""
        cfg = config or RunsCleanupConfig.from_env()
        with self._run_lock:
            self._validate_root()
            started = time.time()
            report = self._report_base(config=cfg, now=started, dry_run=dry_run)
            cutoff = started - cfg.retention_days * 86400

            lock_context = self._process_lock() if not dry_run else nullcontext(True)
            with lock_context as lock_acquired:
                if not lock_acquired:
                    report["ok"] = False
                    report["errors"].append("另一个清理进程正在运行，本次未执行")
                    report["finished_at"] = _iso(time.time())
                    return report

                for candidate in self._candidate_paths(config=cfg):
                    if report["deleted_count"] + report["failed_count"] >= cfg.max_items:
                        report["skipped"].append(
                            {"path": str(candidate), "reason": "max_items_reached"}
                        )
                        report["skipped_count"] += 1
                        continue
                    if not self._under_root(candidate):
                        report["skipped"].append(
                            {"path": str(candidate), "reason": "outside_runs_root"}
                        )
                        report["skipped_count"] += 1
                        continue
                    protected, reason = self._is_protected(candidate, config=cfg)
                    if protected:
                        report["skipped"].append({"path": str(candidate), "reason": reason})
                        report["skipped_count"] += 1
                        continue
                    info = self._path_info(candidate)
                    if info is None:
                        report["skipped"].append(
                            {"path": str(candidate), "reason": "unreadable_or_symlink"}
                        )
                        report["skipped_count"] += 1
                        continue
                    if info.latest_mtime >= cutoff:
                        report["skipped"].append(
                            {
                                "path": str(candidate),
                                "reason": "still_within_retention",
                                "last_modified_at": _iso(info.latest_mtime),
                            }
                        )
                        report["skipped_count"] += 1
                        continue

                    item = {
                        "path": str(candidate),
                        "kind": info.kind,
                        "bytes": info.size_bytes,
                        "last_modified_at": _iso(info.latest_mtime),
                        "reason": "older_than_retention",
                    }
                    if dry_run:
                        report["items"].append(item)
                        report["deleted_count"] += 1
                        report["reclaimed_bytes"] += info.size_bytes
                        continue

                    # Re-check the aggregate mtime immediately before removal so
                    # a job updated during a long scan is not deleted.
                    latest = self._path_info(candidate)
                    if latest is None or latest.latest_mtime >= cutoff:
                        report["skipped"].append(
                            {"path": str(candidate), "reason": "changed_during_cleanup"}
                        )
                        report["skipped_count"] += 1
                        continue
                    try:
                        if latest.kind == "directory":
                            shutil.rmtree(candidate)
                        else:
                            candidate.unlink()
                        report["items"].append(item)
                        report["deleted_count"] += 1
                        report["reclaimed_bytes"] += latest.size_bytes
                    except OSError as exc:
                        report["failed_count"] += 1
                        report["errors"].append(f"{candidate}: {exc}")

            report["finished_at"] = _iso(time.time())
            return report


class RunsCleanupScheduler:
    """One background cleanup loop per application process."""

    def __init__(self, runs_root: Path | None = None):
        self.runs_root = (runs_root or default_runs_root()).expanduser().resolve()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._last_report: dict[str, Any] | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def last_report(self) -> dict[str, Any] | None:
        with self._state_lock:
            return dict(self._last_report) if self._last_report else None

    def start(self) -> None:
        if self.running:
            return
        cfg = RunsCleanupConfig.from_env()
        if not cfg.enabled:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="runs-cleanup",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(RunsCleanupConfig.from_env().startup_delay_seconds):
            cfg = RunsCleanupConfig.from_env()
            if cfg.enabled:
                try:
                    report = RunsCleaner(self.runs_root).cleanup(config=cfg)
                    with self._state_lock:
                        self._last_report = report
                    logger.info(
                        "runs cleanup finished: deleted=%s reclaimed_bytes=%s failed=%s",
                        report.get("deleted_count"),
                        report.get("reclaimed_bytes"),
                        report.get("failed_count"),
                    )
                except Exception:
                    logger.exception("runs cleanup failed")
            interval = max(1.0, RunsCleanupConfig.from_env().interval_hours * 3600.0)
            if self._stop.wait(interval):
                return

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None


_SCHEDULERS: dict[str, RunsCleanupScheduler] = {}
_SCHEDULERS_LOCK = threading.Lock()


def scheduler_for(runs_root: Path | None = None) -> RunsCleanupScheduler:
    root = (runs_root or default_runs_root()).expanduser().resolve()
    key = str(root).lower()
    with _SCHEDULERS_LOCK:
        scheduler = _SCHEDULERS.get(key)
        if scheduler is None:
            scheduler = RunsCleanupScheduler(root)
            _SCHEDULERS[key] = scheduler
        return scheduler


@contextmanager
def nullcontext(value: Any) -> Iterator[Any]:
    """Small local equivalent so this module keeps its Python 3.10 compatibility."""
    yield value


__all__ = [
    "RunsCleanupConfig",
    "RunsCleaner",
    "RunsCleanupScheduler",
    "default_runs_root",
    "scheduler_for",
]
