from __future__ import annotations

from typing import Any


def model_to_dict(model: Any) -> dict:
    """Serialize a Pydantic model (v2: model_dump, v1: dict)."""
    md = getattr(model, "model_dump", None)
    if callable(md):
        return md()
    d = getattr(model, "dict", None)
    if callable(d):
        return d()
    raise TypeError(f"expected a Pydantic BaseModel, got {type(model)!r}")


def model_copy_update(model: Any, update: dict[str, Any]) -> Any:
    """Immutable update (v2: model_copy(update=...), v1: copy(update=...))."""
    mc = getattr(model, "model_copy", None)
    if callable(mc):
        return mc(update=update)
    cp = getattr(model, "copy", None)
    if callable(cp):
        return cp(update=update)
    raise TypeError(f"expected a Pydantic BaseModel, got {type(model)!r}")
