"""
Biblioteca de cenários de Chaos Engineering.

Cenários pré-definidos para testes comuns:
- Pod failure scenarios
- Network partition scenarios
- Resource exhaustion scenarios
- Cascading failure scenarios
"""

from .scenario_library import ScenarioLibrary

__all__ = [
    "ScenarioLibrary",
]
