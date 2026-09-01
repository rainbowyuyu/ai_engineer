"""Tests for RBAC, vector store, and agent concurrency helpers."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException


def test_rbac_role_ladder(monkeypatch):
    monkeypatch.delenv("BESO_AUTH_ENABLED", raising=False)
    from backend.security.rbac import Permission, clear_rbac_cache, resolve_actor_from_headers

    clear_rbac_cache()
    eng = resolve_actor_from_headers(x_beso_role="engineer", x_beso_user="u1")
    assert eng.has(Permission.RUN_LLM)
    assert not eng.has(Permission.RUN_PIPELINE)

    orch = resolve_actor_from_headers(x_beso_role="orchestrator")
    assert orch.has(Permission.RUN_PIPELINE)

    viewer = resolve_actor_from_headers(x_beso_role="viewer")
    with pytest.raises(HTTPException) as ei:
        viewer.require(Permission.MANAGE_RAG)
    assert ei.value.status_code == 403


def test_rbac_unknown_role_soft_vs_hard(monkeypatch):
    from backend.security.rbac import Role, clear_rbac_cache, resolve_actor_from_headers

    monkeypatch.setenv("BESO_AUTH_ENABLED", "false")
    clear_rbac_cache()
    soft = resolve_actor_from_headers(x_beso_role="nope")
    assert soft.role == Role.VIEWER

    monkeypatch.setenv("BESO_AUTH_ENABLED", "true")
    clear_rbac_cache()
    with pytest.raises(HTTPException) as ei:
        resolve_actor_from_headers(x_beso_role="nope")
    assert ei.value.status_code == 401


def test_vector_store_roundtrip(tmp_path: Path):
    from backend.rag.vector_store import LocalJsonVectorStore

    store = LocalJsonVectorStore(tmp_path / "idx.jsonl")
    ids = store.upsert(
        ["OC4 jacket design space is light blue", "BESO topology optimization with CalculiX"],
        metadatas=[{"source": "clause"}, {"source": "method"}],
    )
    assert len(ids) == 2
    hits = store.search("topology optimization CalculiX", top_k=2)
    assert hits
    assert "BESO" in hits[0].text or hits[0].score > 0
    assert store.stats()["count"] == 2
    assert store.delete([ids[0]]) == 1
    assert store.stats()["count"] == 1


def test_gather_limited_respects_cap(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_CONCURRENT", "2")
    from backend.llm.config import get_llm_settings
    from backend.llm.concurrency import gather_limited, reset_concurrency_state

    get_llm_settings.cache_clear()
    reset_concurrency_state()

    peak = {"n": 0, "max": 0}
    lock = asyncio.Lock()

    async def job(i: int) -> int:
        async with lock:
            peak["n"] += 1
            peak["max"] = max(peak["max"], peak["n"])
        await asyncio.sleep(0.05)
        async with lock:
            peak["n"] -= 1
        return i

    async def run():
        return await gather_limited([lambda i=i: job(i) for i in range(6)], limit=2)

    out = asyncio.run(run())
    assert out == list(range(6))
    assert peak["max"] <= 2
