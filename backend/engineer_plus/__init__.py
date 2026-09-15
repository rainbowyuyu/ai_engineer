"""Generic verification-closed engineering-agent runtime."""

from .engine import ClosedLoopEngine, DesignCandidate, DesignRequest, LoopResult
from .adapters import existing_halt_gate, real_reviewer
from .registry import ConstructionAdapter, ConstructionRegistry, default_registry

__all__ = ["ClosedLoopEngine", "DesignCandidate", "DesignRequest", "LoopResult",
           "existing_halt_gate", "real_reviewer", "ConstructionAdapter",
           "ConstructionRegistry", "default_registry"]
