"""Models package for explainability-api."""

from .seniority import (
    SENIORITY_MULTIPLIERS,
    SENIORITY_ORDER,
    SeniorityLevel,
    get_level_rank,
    get_multiplier,
)
from .shap_model import (
    DecisionWrapperModel,
    FeatureExtractor,
    ModelTrainer,
)

__all__ = [
    "SeniorityLevel",
    "SENIORITY_MULTIPLIERS",
    "SENIORITY_ORDER",
    "get_multiplier",
    "get_level_rank",
    "DecisionWrapperModel",
    "FeatureExtractor",
    "ModelTrainer",
]
