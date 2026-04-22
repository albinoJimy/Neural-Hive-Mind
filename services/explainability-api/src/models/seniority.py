"""
Modelo de Senioridade - cópia local para Explainability API v3.

Valores sincronizados com consensus-engine/src/models/seniority.py
"""

from enum import Enum


class SeniorityLevel(str, Enum):
    """Níveis de senioridade dos especialistas."""

    TRAINEE = "trainee"
    JUNIOR = "junior"
    MID_LEVEL = "mid_level"
    SENIOR = "senior"
    EXPERT = "expert"


# Multiplicadores de peso por nível (sincronizado com consensus-engine)
SENIORITY_MULTIPLIERS: dict[str, float] = {
    SeniorityLevel.TRAINEE: 0.5,
    SeniorityLevel.JUNIOR: 0.75,
    SeniorityLevel.MID_LEVEL: 1.0,
    SeniorityLevel.SENIOR: 1.5,
    SeniorityLevel.EXPERT: 2.0,
}

# Ordem de senioridade (para comparações)
SENIORITY_ORDER = [
    SeniorityLevel.TRAINEE,
    SeniorityLevel.JUNIOR,
    SeniorityLevel.MID_LEVEL,
    SeniorityLevel.SENIOR,
    SeniorityLevel.EXPERT,
]


def get_multiplier(level: str) -> float:
    """Retorna o multiplicador para um nível de senioridade."""
    return SENIORITY_MULTIPLIERS.get(level, 1.0)


def get_level_rank(level: str) -> int:
    """Retorna a ordem de rank (0=mais baixo, 4=mais alto)."""
    try:
        return SENIORITY_ORDER.index(SeniorityLevel(level))
    except (ValueError, IndexError):
        return 2  # Default to mid_level
