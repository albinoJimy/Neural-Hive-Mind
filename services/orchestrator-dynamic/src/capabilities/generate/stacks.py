"""
Registry de stacks da capacidade GENERATE (multi-linguagem-ready).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — Scope 4.

A seleção de template/builder é feita por `(language, framework)`. Hoje só a
estratégia **Python FastAPI** está registada (com os valores provados no gate
J3/BUILD), mas o contrato e o routing são stack-neutros.

PONTO DE EXTENSÃO (adicionar uma linguagem):
    Para suportar uma nova stack basta **registar uma GenerationStrategy nova**
    atrás desta mesma fronteira — sem mudar o contrato (`contract.py`) nem o
    routing (`decision_consumer`). Exemplo::

        registry = default_stack_registry()
        registry.register(
            GenerationStrategy(
                language="rust",
                framework="actix",
                template_ref="actix",
                builder="kaniko",
                health_path="/healthz",
                container_port=9090,
            )
        )

Anti-verde-falso: uma stack desconhecida levanta `UnsupportedStackError` —
NUNCA cai silenciosamente para FastAPI.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UnsupportedStackError(Exception):
    """Levantada quando nenhuma estratégia está registada para a stack pedida."""


class GenerationStrategy(BaseModel):
    """Estratégia de geração para uma stack `(language, framework)`."""

    language: str
    framework: str
    template_ref: str
    builder: str
    health_path: str
    container_port: int = Field(gt=0)


class StackRegistry:
    """
    Registry de estratégias de geração, indexado por `(language, framework)`.

    As chaves são normalizadas (case-insensitive) para evitar duplicação por
    diferenças de capitalização.
    """

    def __init__(self) -> None:
        self._strategies: dict[tuple[str, str], GenerationStrategy] = {}

    @staticmethod
    def _key(language: str, framework: str) -> tuple[str, str]:
        """Normaliza a chave (lowercase) para resolução case-insensitive."""
        return (language.strip().lower(), framework.strip().lower())

    def register(self, strategy: GenerationStrategy) -> None:
        """Regista (ou substitui) a estratégia para a sua stack."""
        self._strategies[self._key(strategy.language, strategy.framework)] = strategy

    def is_registered(self, language: str, framework: str) -> bool:
        """Indica se existe uma estratégia registada para a stack."""
        return self._key(language, framework) in self._strategies

    def resolve(self, language: str, framework: str) -> GenerationStrategy:
        """
        Resolve a estratégia para a stack pedida.

        Stack desconhecida → `UnsupportedStackError` (sem fallback silencioso).
        """
        key = self._key(language, framework)
        strategy = self._strategies.get(key)
        if strategy is None:
            raise UnsupportedStackError(
                f"stack não suportada: language='{language}', framework='{framework}'"
            )
        return strategy


def default_stack_registry() -> StackRegistry:
    """
    Constrói o registry default com a única estratégia provada: Python FastAPI.

    Valores provados no gate J3/BUILD: geração por template, build via Kaniko,
    healthcheck em `/health`, porta de contentor 8080.
    """
    registry = StackRegistry()
    registry.register(
        GenerationStrategy(
            language="python",
            framework="fastapi",
            template_ref="fastapi",
            builder="kaniko",
            health_path="/health",
            container_port=8080,
        )
    )
    return registry
