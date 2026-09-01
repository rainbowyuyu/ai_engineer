"""Auth / RBAC introspection endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.security.rbac import Actor, Permission, catalog, get_actor, require_permissions

router = APIRouter(tags=["security"])


@router.get("/me")
async def whoami(actor: Annotated[Actor, Depends(get_actor)]) -> dict:
    from backend.security.rbac import role_permissions

    return {
        "ok": True,
        "user_id": actor.user_id,
        "role": actor.role.value,
        "permissions": sorted(p.value for p in role_permissions(actor.role)),
    }


@router.get("/roles")
async def list_roles(_actor: Annotated[Actor, Depends(require_permissions(Permission.READ_JOBS))]) -> dict:
    return {"ok": True, **catalog()}
