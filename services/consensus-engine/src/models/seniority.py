"""
Modelo de senioridade para especialistas do Neural Hive Mind.

Define níveis hierárquicos de especialização e seus multiplicadores
de peso no processo de consenso.
"""

from enum import Enum
from typing import Dict


class SeniorityLevel(str, Enum):
    """
    Nível de senioridade do especialista.

    Cada nível tem um multiplicador associado que é aplicado ao peso
    do especialista no processo de consenso hierárquico.

    Multiplicadores:
    - TRAINEE: 0.5x (aprendiz, opinião tem metade do peso)
    - JUNIOR: 0.75x (júnior, opinião tem 75% do peso base)
    - MID_LEVEL: 1.0x (pleno, peso base de referência)
    - SENIOR: 1.5x (sénior, opinião tem 50% mais peso)
    - EXPERT: 2.0x (especialista, opinião tem o dobro do peso)
    """
    TRAINEE = "trainee"
    JUNIOR = "junior"
    MID_LEVEL = "mid_level"
    SENIOR = "senior"
    EXPERT = "expert"


# Multiplicadores de peso por nível de senioridade
SENIORITY_MULTIPLIERS: Dict[SeniorityLevel, float] = {
    SeniorityLevel.TRAINEE: 0.5,
    SeniorityLevel.JUNIOR: 0.75,
    SeniorityLevel.MID_LEVEL: 1.0,
    SeniorityLevel.SENIOR: 1.5,
    SeniorityLevel.EXPERT: 2.0,
}


# Descrições humanas dos níveis
SENIORITY_DESCRIPTIONS: Dict[SeniorityLevel, str] = {
    SeniorityLevel.TRAINEE: "Aprendiz em treinamento",
    SeniorityLevel.JUNIOR: "Especialista júnior com experiência básica",
    SeniorityLevel.MID_LEVEL: "Especialista pleno com experiência consolidada",
    SeniorityLevel.SENIOR: "Especialista sénior com experiência avançada",
    SeniorityLevel.EXPERT: "Especialista de referência na sua área",
}


# Ordem de senioridade (para comparações)
SENIORITY_ORDER: list[SeniorityLevel] = [
    SeniorityLevel.TRAINEE,
    SeniorityLevel.JUNIOR,
    SeniorityLevel.MID_LEVEL,
    SeniorityLevel.SENIOR,
    SeniorityLevel.EXPERT,
]


def get_seniority_multiplier(level: SeniorityLevel) -> float:
    """
    Retorna o multiplicador de peso para um nível de senioridade.

    Args:
        level: Nível de senioridade

    Returns:
        Multiplicador de peso (0.5 a 2.0)

    Raises:
        ValueError: Se nível não for reconhecido
    """
    if level not in SENIORITY_MULTIPLIERS:
        raise ValueError(f"Unknown seniority level: {level}")
    return SENIORITY_MULTIPLIERS[level]


def get_seniority_description(level: SeniorityLevel) -> str:
    """
    Retorna descrição humana do nível de senioridade.

    Args:
        level: Nível de senioridade

    Returns:
        Descrição do nível
    """
    return SENIORITY_DESCRIPTIONS.get(level, "Nível não especificado")


def parse_seniority_level(value: str) -> SeniorityLevel:
    """
    Parse string para SeniorityLevel.

    Args:
        value: String representando o nível (case-insensitive)

    Returns:
        SeniorityLevel correspondente

    Raises:
        ValueError: Se string não corresponder a um nível válido
    """
    try:
        return SeniorityLevel(value.lower())
    except ValueError:
        valid_levels = [level.value for level in SeniorityLevel]
        raise ValueError(
            f"Invalid seniority level: {value}. "
            f"Valid levels: {', '.join(valid_levels)}"
        )


def compare_seniority(level1: SeniorityLevel, level2: SeniorityLevel) -> int:
    """
    Compara dois níveis de senioridade.

    Args:
        level1: Primeiro nível
        level2: Segundo nível

    Returns:
        -1 se level1 < level2
         0 se level1 == level2
         1 se level1 > level2
    """
    idx1 = SENIORITY_ORDER.index(level1)
    idx2 = SENIORITY_ORDER.index(level2)

    if idx1 < idx2:
        return -1
    elif idx1 > idx2:
        return 1
    return 0
