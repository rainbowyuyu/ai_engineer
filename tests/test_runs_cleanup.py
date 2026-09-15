"""Safety and retention tests for the automatic runs cleanup service."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from backend.runs_cleanup import RunsCleanupConfig, RunsCleaner


def _make_old(path: Path, *, age_seconds: float = 3 * 86400) -> None:
    now = time.time() - age_seconds
    if path.is_dir():
        for child in path.rglob("*"):
            try:
                os.utime(child, (now, now))
            except OSError:
                pass
    os.utime(path, (now, now))


def _cfg(**overrides) -> RunsCleanupConfig:
    values = {
        "enabled": True,
        "retention_days": 1,
        "interval_hours": 24,
        "startup_delay_seconds": 0,
        "include_archives": False,
        "max_items": 100,
    }
    values.update(overrides)
    return RunsCleanupConfig(**values)


def test_preview_does_not_delete_and_reports_bytes(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    old = runs / "old-job"
    old.mkdir(parents=True)
    payload = old / "large.bin"
    payload.write_bytes(b"abc")
    _make_old(old)

    report = RunsCleaner(runs).cleanup(config=_cfg(), dry_run=True)

    assert report["ok"] is True
    assert report["dry_run"] is True
    assert report["deleted_count"] == 1
    assert report["reclaimed_bytes"] == 3
    assert old.is_dir()


def test_cleanup_removes_stale_units_but_keeps_active_and_recent(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    old = runs / "old-job"
    old.mkdir(parents=True)
    (old / "result.bin").write_bytes(b"old")
    _make_old(old)

    recent = runs / "recent-job"
    recent.mkdir(parents=True)
    (recent / "result.bin").write_bytes(b"new")

    active = runs / "active-job"
    active.mkdir(parents=True)
    (active / "status.json").write_text(json.dumps({"status": "running"}), encoding="utf-8")
    _make_old(active)

    report = RunsCleaner(runs).cleanup(config=_cfg())

    assert report["deleted_count"] == 1
    assert not old.exists()
    assert recent.exists()
    assert active.exists()
    assert any(item["reason"].startswith("active_status") for item in report["skipped"])


def test_special_roots_clean_children_without_deleting_persistent_stores(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    stale_upload = runs / "_uploads" / "old-upload"
    stale_upload.mkdir(parents=True)
    (stale_upload / "model.stp").write_bytes(b"stale")
    _make_old(stale_upload)

    stale_archive = runs / "_archive" / "old-archive"
    stale_archive.mkdir(parents=True)
    (stale_archive / "archive_meta.json").write_text("{}", encoding="utf-8")
    _make_old(stale_archive)

    checkpoints = runs / "_checkpoints"
    checkpoints.mkdir(parents=True)
    checkpoint = checkpoints / "pipeline.sqlite"
    checkpoint.write_bytes(b"sqlite")
    _make_old(checkpoint)

    report = RunsCleaner(runs).cleanup(config=_cfg())

    assert not stale_upload.exists()
    assert stale_archive.exists()
    assert checkpoint.exists()
    assert any("protected_root:_archive" in x["reason"] for x in report["skipped"])
    assert any("protected_root:_checkpoints" in x["reason"] for x in report["skipped"])


def test_keep_marker_and_incomplete_conversion_are_protected(tmp_path: Path) -> None:
    runs = tmp_path / "runs"

    marked = runs / "_deliverables" / "keep-me"
    marked.mkdir(parents=True)
    (marked / ".cleanup-keep").write_text("", encoding="utf-8")
    _make_old(marked)

    converting = runs / "_cad_convert" / "conversion-1"
    converting.mkdir(parents=True)
    (converting / "status.json").write_text(
        json.dumps({"done": False, "progress": 42, "stage": "mesh"}),
        encoding="utf-8",
    )
    _make_old(converting)

    done = runs / "_cad_convert" / "conversion-2"
    done.mkdir(parents=True)
    (done / "status.json").write_text(
        json.dumps({"done": True, "progress": 100}),
        encoding="utf-8",
    )
    _make_old(done)

    report = RunsCleaner(runs).cleanup(config=_cfg())

    assert marked.exists()
    assert converting.exists()
    assert not done.exists()
    assert any(x["reason"] == "keep_marker" for x in report["skipped"])
    assert any(x["reason"] == "active_progress" for x in report["skipped"])


def test_archive_can_be_included_explicitly(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    archived = runs / "_archive" / "old-archive"
    archived.mkdir(parents=True)
    (archived / "archive_meta.json").write_text("{}", encoding="utf-8")
    _make_old(archived)

    report = RunsCleaner(runs).cleanup(config=_cfg(include_archives=True))

    assert report["deleted_count"] == 1
    assert not archived.exists()


def test_cleanup_api_preview_is_non_destructive(tmp_path: Path, monkeypatch) -> None:
    runs = tmp_path / "runs"
    old = runs / "api-old-job"
    old.mkdir(parents=True)
    (old / "result.bin").write_bytes(b"api")
    _make_old(old)

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("RUNS_CLEANUP_ENABLED", "false")
    from fastapi.testclient import TestClient

    from backend.app import app

    with TestClient(app) as client:
        response = client.post(
            "/api/runs-cleanup/preview",
            json={"retention_days": 1},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["dry_run"] is True
    assert data["deleted_count"] == 1
    assert old.exists()
