"""
Módulo de validação para Neural Hive Specialists.

Contém validadores compartilhados para qualidade de descrições de tarefas
usados tanto em runtime (STE) quanto em geração de datasets de treinamento.
"""

from .description_validator import (
    DescriptionQualityValidator,
    get_validator,
)

__all__ = [
    'DescriptionQualityValidator',
    'get_validator',
]
