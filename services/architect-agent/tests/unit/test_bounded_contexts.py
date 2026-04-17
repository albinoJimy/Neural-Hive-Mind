"""Unit tests for BoundedContextsIdentifier."""

import pytest
from src.identifiers.bounded_contexts import BoundedContextsIdentifier
from src.models.bounded_context import (
    BoundedContext,
    BoundedContextsAnalysis,
    BoundedContextRelationship,
    UbiquitousLanguageTerm
)


@pytest.mark.asyncio
async def test_identify_bounded_contexts_simple():
    """Testa identificação de bounded contexts para sistema simples."""

    identifier = BoundedContextsIdentifier()

    requirements = """
    Sistema de e-commerce com:
    - Gestão de utilizadores e autenticação
    - Catálogo de produtos e categorias
    - Carrinho de compras e checkout
    - Processamento de pagamentos
    - Gestão de encomendas e envio
    """

    result = await identifier.identify(requirements)

    assert isinstance(result, BoundedContextsAnalysis)
    assert result.total_contexts >= 2
    assert any(ctx.name == "Identity" for ctx in result.contexts)
    assert any(ctx.name == "Catalog" for ctx in result.contexts)


@pytest.mark.asyncio
async def test_identify_bounded_contexts_returns_ubiquitous_language():
    """Testa que termos ubiquituos são identificados."""

    identifier = BoundedContextsIdentifier()

    requirements = """
    Sistema de gestão de tarefas onde:
    - Utilizadores podem criar tarefas
    - Tarefas podem ser atribuídas a membros da equipa
    - Comentários podem ser adicionados às tarefas
    """

    result = await identifier.identify(requirements)

    # Verificar que pelo menos um contexto tem termos ubiquituos
    has_terms = any(
        len(ctx.ubiquitous_language) > 0
        for ctx in result.contexts
    )
    assert has_terms


@pytest.mark.asyncio
async def test_identify_bounded_contexts_with_domain_hints():
    """Testa identificação com sugestões de contextos."""

    identifier = BoundedContextsIdentifier()

    requirements = "Sistema bancário com contas, transações e empréstimos."
    domain_hints = ["Identity", "Transactions", "Loans"]

    result = await identifier.identify(requirements, domain_hints=domain_hints)

    assert result.total_contexts >= 1
    # Pelo menos um contexto sugerido deve aparecer
    hinted_contexts = [ctx.name for ctx in result.contexts if ctx.name in domain_hints]
    assert len(hinted_contexts) > 0


def test_bounded_context_has_is_external_field():
    """Testa que BoundedContext tem o campo is_external."""
    context = BoundedContext(
        name="ExternalPayment",
        description="Sistema de pagamentos externo",
        responsibilities=["Processar pagamentos"],
        domain_models=["Payment", "Transaction"],
        is_external=True
    )
    assert context.is_external is True
    assert context.name == "ExternalPayment"


def test_bounded_context_defaults_is_external_to_false():
    """Testa que is_external default é False."""
    context = BoundedContext(
        name="Identity",
        description="Gestão de identidade",
        responsibilities=["Autenticação", "Autorização"],
        domain_models=["User", "Role"]
    )
    assert context.is_external is False


def test_bounded_context_relationship_has_direction_field():
    """Testa que BoundedContextRelationship tem o campo direction."""
    relationship = BoundedContextRelationship(
        **{"from": "Identity", "to": "Billing"},  # Usar alias com dict unpacking
        relationship_type="partnership",
        direction="outgoing",
        description="Identity usa Billing para faturação"
    )
    assert relationship.direction == "outgoing"
    assert relationship.from_context == "Identity"


def test_bounded_context_relationship_direction_is_optional():
    """Testa que direction é opcional."""
    relationship = BoundedContextRelationship(
        **{"from": "Catalog", "to": "Inventory"},  # Usar alias com dict unpacking
        relationship_type="shared_kernel"
    )
    assert relationship.direction is None


def test_bounded_context_with_relationships_and_direction():
    """Testa contexto com relacionamentos direcionados."""
    relationships = [
        BoundedContextRelationship(
            **{"from": "Identity", "to": "Orders"},
            relationship_type="partnership",
            direction="outgoing"
        ),
        BoundedContextRelationship(
            **{"from": "Payments", "to": "Orders"},
            relationship_type="partnership",
            direction="incoming"
        )
    ]

    context = BoundedContext(
        name="Orders",
        description="Gestão de encomendas",
        responsibilities=["Criar encomendas", "Gerir estado"],
        domain_models=["Order", "OrderItem"],
        relationships=relationships,
        is_external=False
    )

    assert len(context.relationships) == 2
    assert context.relationships[0].direction == "outgoing"
    assert context.relationships[1].direction == "incoming"
