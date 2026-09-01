"""Lightweight RBAC for FastAPI routes and agent tool gates.

Auth is header-based for local/dev deployments:
  - ``X-Beso-Role``: viewer | engineer | orchestrator | admin (default: engineer)
  - ``X-Beso-User``: optional actor id for audit trails
  - ``BESO_AUTH_ENABLED=true``: reject unknown roles; otherwise unknown → viewer

Production deployments should replace ``resolve_actor_from_headers`` with SSO / JWT.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Annotated, Callable

from fastapi import Depends, Header, HTTPException, status


class Role(str, Enum):
    VIEWER = "viewer"
    ENGINEER = "engineer"
    ORCHESTRATOR = "orchestrator"
    ADMIN = "admin"


class Permission(str, Enum):
    READ_JOBS = "read:jobs"
    WRITE_JOBS = "write:jobs"
    RUN_PIPELINE = "run:pipeline"
    RUN_LLM = "run:llm"
    MANAGE_RAG = "manage:rag"
    SEARCH_RAG = "search:rag"
    MANAGE_ROLES = "manage:roles"
    ADMIN = "admin:all"


_ROLE_PERMS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(
        {
            Permission.READ_JOBS,
            Permission.SEARCH_RAG,
        }
    ),
    Role.ENGINEER: frozenset(
        {
            Permission.READ_JOBS,
            Permission.WRITE_JOBS,
            Permission.RUN_LLM,
            Permission.SEARCH_RAG,
            Permission.MANAGE_RAG,
        }
    ),
    Role.ORCHESTRATOR: frozenset(
        {
            Permission.READ_JOBS,
            Permission.WRITE_JOBS,
            Permission.RUN_PIPELINE,
            Permission.RUN_LLM,
            Permission.SEARCH_RAG,
            Permission.MANAGE_RAG,
        }
    ),
    Role.ADMIN: frozenset(set(Permission)),
}


def role_permissions(role: Role) -> frozenset[Permission]:
    return _ROLE_PERMS.get(role, _ROLE_PERMS[Role.VIEWER])


def auth_enabled() -> bool:
    raw = (os.environ.get("BESO_AUTH_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def default_role() -> Role:
    raw = (os.environ.get("BESO_DEFAULT_ROLE") or "engineer").strip().lower()
    try:
        return Role(raw)
    except ValueError:
        return Role.ENGINEER


@dataclass(frozen=True)
class Actor:
    user_id: str
    role: Role

    def has(self, *perms: Permission) -> bool:
        owned = role_permissions(self.role)
        if Permission.ADMIN in owned:
            return True
        return all(p in owned for p in perms)

    def require(self, *perms: Permission) -> None:
        if not self.has(*perms):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "role": self.role.value,
                    "required": [p.value for p in perms],
                },
            )


def parse_role(raw: str | None) -> Role:
    if not raw or not str(raw).strip():
        return default_role()
    key = str(raw).strip().lower()
    try:
        return Role(key)
    except ValueError:
        if auth_enabled():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"unknown role: {raw!r}",
            )
        return Role.VIEWER


def resolve_actor_from_headers(
    *,
    x_beso_role: str | None = None,
    x_beso_user: str | None = None,
) -> Actor:
    role = parse_role(x_beso_role)
    uid = (x_beso_user or "").strip() or "anonymous"
    return Actor(user_id=uid, role=role)


async def get_actor(
    x_beso_role: Annotated[str | None, Header(alias="X-Beso-Role")] = None,
    x_beso_user: Annotated[str | None, Header(alias="X-Beso-User")] = None,
) -> Actor:
    return resolve_actor_from_headers(x_beso_role=x_beso_role, x_beso_user=x_beso_user)


def require_permissions(*perms: Permission) -> Callable[..., Actor]:
    async def _dep(actor: Annotated[Actor, Depends(get_actor)]) -> Actor:
        actor.require(*perms)
        return actor

    return _dep


@lru_cache(maxsize=1)
def catalog() -> dict:
    return {
        "roles": {r.value: sorted(p.value for p in role_permissions(r)) for r in Role},
        "permissions": [p.value for p in Permission],
        "auth_enabled": auth_enabled(),
        "default_role": default_role().value,
        "headers": ["X-Beso-Role", "X-Beso-User"],
    }


def clear_rbac_cache() -> None:
    catalog.cache_clear()
