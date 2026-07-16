"""Physics-informed neural surrogate for structural static responses."""
from backend.surrogate.inference import SurrogatePrediction, predict
from backend.surrogate.config import load_surrogate_config

__all__ = ["SurrogatePrediction", "predict", "load_surrogate_config"]
