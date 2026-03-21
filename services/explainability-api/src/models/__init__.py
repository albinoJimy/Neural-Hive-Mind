"""Models package for explainability-api."""

from .seniority import (
    SeniorityLevel,
    SENIORITY_MULTIPLIERS,
    SENIORITY_ORDER,
    get_multiplier,
    get_level_rank,
)

__all__ = [
    'SeniorityLevel',
    'SENIORITY_MULTIPLIERS',
    'SENIORITY_ORDER',
    'get_multiplier',
    'get_level_rank',
]
