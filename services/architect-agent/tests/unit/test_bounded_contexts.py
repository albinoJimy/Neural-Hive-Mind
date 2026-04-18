"""Unit tests for BoundedContextsIdentifier."""

from unittest.mock import AsyncMock, Mock

import pytest
from src.identifiers.bounded_contexts import BoundedContextsIdentifier
from src.models.bounded_context import (
    BoundedContext,
    BoundedContextRelationship,
    BoundedContextsAnalysis,
)


@pytest.fixture
def mock_llm_client():
    """Mock do cliente LLM."""
    client = Mock()
    response = Mock()
    choice = Mock()
    message = Mock()
    message.content = """{
      "contexts": [
        {
          "name": "Identity",
          "description": "Gestão de utilizadores e autenticação",
          "responsibilities": ["Autenticação", "Autorização"],
          "domain_models": ["User", "Role"],
          "ubiquitous_language": [{"term": "Credential", "definition": "Dados de acesso"}],
          "relationships": []
        },
        {
          "name": "Catalog",
          "description": "Gestão de catálogo de produtos",
          "responsibilities": ["CRUD produtos", "Categorias"],
          "domain_models": ["Product", "Category"],
          "ubiquitous_language": [{"term": "SKU", "definition": "Stock Keeping Unit"}],
          "relationships": []
        }
      ],
      "confidence_score": 0.9
    }"""
    choice.message = message
    response.choices = [choice]
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_identify_bounded_contexts_simple(mock_llm_client):
    """Testa identificação de bounded contexts para sistema simples."""

    identifier = BoundedContextsIdentifier(llm_client=mock_llm_client)

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
    assert result.total_contexts == 2
    assert any(ctx.name == "Identity" for ctx in result.contexts)
    assert any(ctx.name == "Catalog" for ctx in result.contexts)


@pytest.mark.asyncio
async def test_identify_bounded_contexts_returns_ubiquitous_language(mock_llm_client):
    """Testa que termos ubiquituos são identificados."""

    identifier = BoundedContextsIdentifier(llm_client=mock_llm_client)

    requirements = """
    Sistema de gestão de tarefas onde:
    - Utilizadores podem criar tarefas
    - Tarefas podem ser atribuídas a membros da equipa
    - Comentários podem ser adicionados às tarefas
    """

    result = await identifier.identify(requirements)

    # Verificar que pelo menos um contexto tem termos ubiquituos
    has_terms = any(len(ctx.ubiquitous_language) > 0 for ctx in result.contexts)
    assert has_terms


@pytest.mark.asyncio
async def test_identify_bounded_contexts_with_domain_hints(mock_llm_client):
    """Testa identificação com sugestões de contextos."""

    identifier = BoundedContextsIdentifier(llm_client=mock_llm_client)

    requirements = "Sistema bancário com contas, transações e empréstimos."
    domain_hints = ["Identity", "Transactions", "Loans"]

    result = await identifier.identify(requirements, domain_hints=domain_hints)

    assert result.total_contexts == 2


def test_bounded_context_has_is_external_field():
    """Testa que BoundedContext tem o campo is_external."""
    context = BoundedContext(
        name="ExternalPayment",
        description="Sistema de pagamentos externo",
        responsibilities=["Processar pagamentos"],
        domain_models=["Payment", "Transaction"],
        is_external=True,
    )
    assert context.is_external is True
    assert context.name == "ExternalPayment"


def test_bounded_context_defaults_is_external_to_false():
    """Testa que is_external default é False."""
    context = BoundedContext(
        name="Identity",
        description="Gestão de identidade",
        responsibilities=["Autenticação", "Autorização"],
        domain_models=["User", "Role"],
    )
    assert context.is_external is False


def test_bounded_context_relationship_has_direction_field():
    """Testa que BoundedContextRelationship tem o campo direction."""
    relationship = BoundedContextRelationship(
        **{"from": "Identity", "to": "Billing"},  # Usar alias com dict unpacking
        relationship_type="partnership",
        direction="outgoing",
        description="Identity usa Billing para faturação",
    )
    assert relationship.direction == "outgoing"
    assert relationship.from_context == "Identity"


def test_bounded_context_relationship_direction_is_optional():
    """Testa que direction é opcional."""
    relationship = BoundedContextRelationship(
        **{"from": "Catalog", "to": "Inventory"},  # Usar alias com dict unpacking
        relationship_type="shared_kernel",
    )
    assert relationship.direction is None


def test_bounded_context_with_relationships_and_direction():
    """Testa contexto com relacionamentos direcionados."""
    relationships = [
        BoundedContextRelationship(
            **{"from": "Identity", "to": "Orders"},
            relationship_type="partnership",
            direction="outgoing",
        ),
        BoundedContextRelationship(
            **{"from": "Payments", "to": "Orders"},
            relationship_type="partnership",
            direction="incoming",
        ),
    ]

    context = BoundedContext(
        name="Orders",
        description="Gestão de encomendas",
        responsibilities=["Criar encomendas", "Gerir estado"],
        domain_models=["Order", "OrderItem"],
        relationships=relationships,
        is_external=False,
    )

    assert len(context.relationships) == 2
    assert context.relationships[0].direction == "outgoing"
    assert context.relationships[1].direction == "incoming"


def test_bounded_contexts_validates_empty_requirements(mock_llm_client):
    """Testa que requirements vazio lança ValueError."""
    identifier = BoundedContextsIdentifier(llm_client=mock_llm_client)

    with pytest.raises(ValueError, match="Requirements cannot be empty"):
        # Usar sync wrapper para async
        import asyncio

        asyncio.run(identifier.identify("   "))


def test_bounded_contexts_validates_too_short_requirements(mock_llm_client):
    """Testa que requirements muito curto lança ValueError."""
    identifier = BoundedContextsIdentifier(llm_client=mock_llm_client)

    with pytest.raises(ValueError, match="Requirements too short"):
        import asyncio

        asyncio.run(identifier.identify("abc"))


def test_bounded_contexts_validates_too_long_requirements(mock_llm_client):
    """Testa que requirements muito longo lança ValueError."""
    identifier = BoundedContextsIdentifier(llm_client=mock_llm_client)

    # Criar requirements com mais de 15000 caracteres
    long_requirements = "x" * 15001

    with pytest.raises(ValueError, match="Requirements too long"):
        import asyncio

        asyncio.run(identifier.identify(long_requirements))


def test_bounded_contexts_validates_too_many_hints(mock_llm_client):
    """Testa que demasiadas hints lança ValueError."""
    identifier = BoundedContextsIdentifier(llm_client=mock_llm_client)

    # Criar 11 domain hints (limite é 10)
    too_many_hints = [f"Context{i}" for i in range(11)]

    # Requirements precisa ter pelo menos 50 caracteres para passar a validação de comprimento
    long_requirements = "Sistema de e-commerce com várias funcionalidades importantes para gestão."

    with pytest.raises(ValueError, match="Too many domain hints"):
        import asyncio

        asyncio.run(identifier.identify(long_requirements, domain_hints=too_many_hints))
