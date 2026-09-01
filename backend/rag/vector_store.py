"""File-backed vector index for engineering clauses and run notes.

Uses a deterministic hashing embedder (no heavyweight ML deps) so RAG works
out of the box. Swap ``embed_fn`` for OpenAI / local sentence-transformers when needed.
Optional Chroma path: set ``BESO_VECTOR_BACKEND=chroma`` after ``pip install chromadb``.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_store_dir() -> Path:
    root = Path(os.environ.get("WORKSPACE_ROOT") or _repo_root()).resolve()
    custom = (os.environ.get("BESO_VECTOR_DIR") or "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    return root / ".beso_rag"


def hash_embed(text: str, *, dims: int = 384) -> list[float]:
    """Bag-of-tokens hashing trick → unit L2 vector (deterministic, dependency-free)."""
    vec = [0.0] * dims
    tokens = [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in (text or "")).split() if t]
    if not tokens:
        tokens = ["_empty_"]
    for tok in tokens:
        h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % dims
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
        # bigram-ish second hash for short Chinese/English mixes
        h2 = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h2 % dims] += 0.5 * (1.0 if (h2 >> 4) & 1 else -1.0)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return sum(a[i] * b[i] for i in range(n))


@dataclass
class VectorDocument:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VectorDocument":
        return cls(
            id=str(data.get("id") or ""),
            text=str(data.get("text") or ""),
            metadata=dict(data.get("metadata") or {}),
            embedding=list(data["embedding"]) if data.get("embedding") is not None else None,
            created_at=float(data.get("created_at") or time.time()),
        )


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    text: str
    score: float
    metadata: dict[str, Any]


class LocalJsonVectorStore:
    """JSONL persistence + in-memory cosine search."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        embed_fn: Callable[[str], list[float]] | None = None,
        dims: int = 384,
    ) -> None:
        self.path = Path(path or (default_store_dir() / "index.jsonl"))
        self.dims = dims
        self.embed_fn = embed_fn or (lambda t: hash_embed(t, dims=dims))
        self._lock = threading.RLock()
        self._docs: dict[str, VectorDocument] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                doc = VectorDocument.from_dict(json.loads(line))
            except Exception:
                continue
            if doc.id:
                self._docs[doc.id] = doc

    def _persist(self) -> None:
        tmp = self.path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for doc in self._docs.values():
                f.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    def upsert(
        self,
        texts: Iterable[str],
        *,
        metadatas: Iterable[dict[str, Any]] | None = None,
        ids: Iterable[str] | None = None,
    ) -> list[str]:
        text_list = [str(t).strip() for t in texts if str(t).strip()]
        meta_list = list(metadatas) if metadatas is not None else [{} for _ in text_list]
        id_list = list(ids) if ids is not None else [uuid.uuid4().hex for _ in text_list]
        while len(meta_list) < len(text_list):
            meta_list.append({})
        while len(id_list) < len(text_list):
            id_list.append(uuid.uuid4().hex)
        out: list[str] = []
        with self._lock:
            for text, meta, doc_id in zip(text_list, meta_list, id_list):
                emb = self.embed_fn(text)
                self._docs[doc_id] = VectorDocument(
                    id=doc_id,
                    text=text,
                    metadata=dict(meta or {}),
                    embedding=emb,
                )
                out.append(doc_id)
            self._persist()
        return out

    def delete(self, ids: Iterable[str]) -> int:
        removed = 0
        with self._lock:
            for doc_id in ids:
                if self._docs.pop(str(doc_id), None) is not None:
                    removed += 1
            if removed:
                self._persist()
        return removed

    def search(self, query: str, *, top_k: int = 5, min_score: float = 0.0) -> list[RetrievedChunk]:
        q = (query or "").strip()
        if not q:
            return []
        qv = self.embed_fn(q)
        scored: list[RetrievedChunk] = []
        with self._lock:
            for doc in self._docs.values():
                emb = doc.embedding or self.embed_fn(doc.text)
                score = cosine(qv, emb)
                if score < min_score:
                    continue
                scored.append(
                    RetrievedChunk(
                        id=doc.id,
                        text=doc.text,
                        score=float(score),
                        metadata=dict(doc.metadata),
                    )
                )
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[: max(1, int(top_k))]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "backend": "local_jsonl",
                "path": str(self.path),
                "count": len(self._docs),
                "dims": self.dims,
            }


_default_store: LocalJsonVectorStore | None = None
_store_lock = threading.Lock()


def get_default_store() -> LocalJsonVectorStore:
    global _default_store
    with _store_lock:
        if _default_store is None:
            _default_store = LocalJsonVectorStore()
        return _default_store


def reset_default_store() -> None:
    global _default_store
    with _store_lock:
        _default_store = None
