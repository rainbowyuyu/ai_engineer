"""Safe construction adapter registry for the plus runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .revision import RevisionPolicy

from .engine import DesignDomainBuilder, TopologyRunner


@dataclass(frozen=True)
class ConstructionAdapter:
    name: str
    description: str
    build_domain: DesignDomainBuilder
    run_topology: TopologyRunner
    capabilities: tuple[str, ...] = ()
    input_formats: tuple[str, ...] = ()
    required_inputs: tuple[str, ...] = ()
    produced_artifacts: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    revision_policy: "RevisionPolicy | None" = None


class ConstructionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ConstructionAdapter] = {}
        self._registration_errors: list[dict[str, str]] = []

    def register(self, adapter: ConstructionAdapter) -> None:
        key = adapter.name.strip().lower()
        if not key or key in self._items:
            raise ValueError(f"construction adapter already registered: {adapter.name}")
        self._items[key] = adapter

    def get(self, name: str) -> ConstructionAdapter:
        try:
            return self._items[name.strip().lower()]
        except KeyError as exc:
            raise KeyError(f"unknown construction: {name}; available={sorted(self._items)}") from exc

    def catalog(self) -> list[dict[str, Any]]:
        return [{"name": x.name, "description": x.description,
                 "capabilities": list(x.capabilities),
                 "input_formats": list(x.input_formats),
                 "required_inputs": list(x.required_inputs),
                 "produced_artifacts": list(x.produced_artifacts),
                 "limitations": list(x.limitations),
                 "review_revision_supported": x.revision_policy is not None} for x in self._items.values()]

    def record_registration_error(self, error: Exception) -> None:
        self._registration_errors.append({"type": type(error).__name__,
                                          "message": str(error)})

    def registration_errors(self) -> list[dict[str, str]]:
        return list(self._registration_errors)


default_registry = ConstructionRegistry()
try:
    from .builtin_adapters import register_builtin_adapters
    register_builtin_adapters(default_registry)
except Exception as exc:
    # Optional solver dependencies are checked when an adapter is executed.
    # A missing dependency must not make the API itself unavailable.
    default_registry.record_registration_error(exc)


__all__ = ["ConstructionAdapter", "ConstructionRegistry", "default_registry"]
