"""Vector / RAG API for clause and methodology retrieval."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.rag.vector_store import get_default_store
from backend.security.rbac import Actor, Permission, require_permissions

router = APIRouter(tags=["rag"])


class UpsertBody(BaseModel):
    texts: list[str] = Field(min_length=1)
    metadatas: list[dict[str, Any]] | None = None
    ids: list[str] | None = None


class SearchBody(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=-1.0, le=1.0)


class DeleteBody(BaseModel):
    ids: list[str] = Field(min_length=1)


@router.get("/stats")
async def rag_stats(_actor: Annotated[Actor, Depends(require_permissions(Permission.SEARCH_RAG))]) -> dict:
    return {"ok": True, **get_default_store().stats()}


@router.post("/upsert")
async def rag_upsert(
    body: UpsertBody,
    _actor: Annotated[Actor, Depends(require_permissions(Permission.MANAGE_RAG))],
) -> dict:
    ids = get_default_store().upsert(body.texts, metadatas=body.metadatas, ids=body.ids)
    return {"ok": True, "ids": ids, "count": len(ids)}


@router.post("/search")
async def rag_search(
    body: SearchBody,
    _actor: Annotated[Actor, Depends(require_permissions(Permission.SEARCH_RAG))],
) -> dict:
    hits = get_default_store().search(body.query, top_k=body.top_k, min_score=body.min_score)
    return {
        "ok": True,
        "query": body.query,
        "hits": [
            {"id": h.id, "text": h.text, "score": h.score, "metadata": h.metadata}
            for h in hits
        ],
    }


@router.post("/delete")
async def rag_delete(
    body: DeleteBody,
    _actor: Annotated[Actor, Depends(require_permissions(Permission.MANAGE_RAG))],
) -> dict:
    n = get_default_store().delete(body.ids)
    return {"ok": True, "removed": n}
