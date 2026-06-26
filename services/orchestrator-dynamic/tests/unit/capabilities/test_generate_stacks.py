"""
Testes unitários do registry de stacks da capacidade GENERATE (Task 1 / Fase 0).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — Scope 4 (Registry).

Provam que:
- a stack FastAPI está registada com os valores provados no gate J3/BUILD;
- registar uma estratégia nova é selecionada sem tocar no contrato (extensibilidade);
- uma stack desconhecida falha fechado (UnsupportedStackError) e NUNCA cai
  silenciosamente para FastAPI (anti-verde-falso).
"""

import pytest
from pydantic import ValidationError
from src.capabilities.generate.stacks import (
    GenerationStrategy,
    StackRegistry,
    UnsupportedStackError,
    default_stack_registry,
)

# =============================================================================
# FastAPI registado por omissão (valores provados no J3/BUILD)
# =============================================================================


def test_default_registry_resolve_fastapi():
    registry = default_stack_registry()
    strategy = registry.resolve("python", "fastapi")
    assert strategy.language == "python"
    assert strategy.framework == "fastapi"
    assert strategy.template_ref == "fastapi"
    assert strategy.builder == "kaniko"
    assert strategy.health_path == "/health"
    assert strategy.container_port == 8080


def test_default_registry_resolve_case_insensitive():
    registry = default_stack_registry()
    strategy = registry.resolve("Python", "FastAPI")
    assert strategy.framework == "fastapi"
    assert strategy.container_port == 8080


def test_is_registered():
    registry = default_stack_registry()
    assert registry.is_registered("python", "fastapi") is True
    assert registry.is_registered("go", "gin") is False


def test_register_e_resolve_normalizacao_simetrica():
    """register com chave em maiúsculas resolve com minúsculas (mesma normalização)."""
    registry = StackRegistry()
    strategy = GenerationStrategy(
        language="GO",
        framework="GIN",
        template_ref="gin",
        builder="kaniko",
        health_path="/healthz",
        container_port=8080,
    )
    registry.register(strategy)
    assert registry.resolve("go", "gin") is strategy
    assert registry.is_registered("go", "gin") is True


def test_generation_strategy_porta_invalida_falha():
    """container_port tem de ser > 0 (config interna válida)."""
    with pytest.raises(ValidationError):
        GenerationStrategy(
            language="python",
            framework="fastapi",
            template_ref="fastapi",
            builder="kaniko",
            health_path="/health",
            container_port=0,
        )


# =============================================================================
# Extensibilidade — registar nova estratégia sem tocar no contrato
# =============================================================================


def test_registar_estrategia_fake_e_resolver():
    registry = StackRegistry()
    fake = GenerationStrategy(
        language="rust",
        framework="actix",
        template_ref="actix",
        builder="kaniko",
        health_path="/healthz",
        container_port=9090,
    )
    registry.register(fake)
    resolved = registry.resolve("rust", "actix")
    assert resolved is fake
    assert resolved.container_port == 9090
    assert resolved.template_ref == "actix"


def test_registar_estrategia_nova_no_default_registry():
    registry = default_stack_registry()
    fake = GenerationStrategy(
        language="rust",
        framework="actix",
        template_ref="actix",
        builder="kaniko",
        health_path="/healthz",
        container_port=9090,
    )
    registry.register(fake)
    # A nova é selecionada e a FastAPI continua intacta.
    assert registry.resolve("rust", "actix") is fake
    assert registry.resolve("python", "fastapi").framework == "fastapi"


# =============================================================================
# Stack desconhecida — fail-closed, SEM fallback silencioso
# =============================================================================


def test_resolve_stack_desconhecida_levanta_erro():
    registry = default_stack_registry()
    with pytest.raises(UnsupportedStackError):
        registry.resolve("go", "gin")


def test_resolve_desconhecida_nao_devolve_fastapi():
    registry = default_stack_registry()
    try:
        resolved = registry.resolve("go", "gin")
    except UnsupportedStackError:
        resolved = None
    # Garante que NÃO houve fallback silencioso para FastAPI.
    assert resolved is None
