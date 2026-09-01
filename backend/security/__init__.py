"""Role-based access control for API and agent tool gates."""

from backend.security.rbac import (
    Actor,
    Permission,
    Role,
    get_actor,
    require_permissions,
    role_permissions,
)

__all__ = [
    "Actor",
    "Permission",
    "Role",
    "get_actor",
    "require_permissions",
    "role_permissions",
]
