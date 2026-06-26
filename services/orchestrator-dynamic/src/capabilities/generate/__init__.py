"""
Capacidade GENERATE — contrato e registry de stacks (Task 1 / Fase 0).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate.

Exporta os símbolos públicos do contrato e do registry. A lógica de
orquestração (capability/routing) é introduzida em fases posteriores.
"""

from src.capabilities.generate.contract import (
    DeploymentInfo,
    GenerateRequest,
    GenerateResult,
    GenerateTarget,
)
from src.capabilities.generate.stacks import (
    GenerationStrategy,
    StackRegistry,
    UnsupportedStackError,
    default_stack_registry,
)

__all__ = [
    "DeploymentInfo",
    "GenerateRequest",
    "GenerateResult",
    "GenerateTarget",
    "GenerationStrategy",
    "StackRegistry",
    "UnsupportedStackError",
    "default_stack_registry",
]
