"""Unit tests for BoundedContextsIdentifier."""

import pytest
from architect.identifiers.bounded_contexts import BoundedContextsIdentifier
from architect.models.bounded_context import BoundedContext, BoundedContextsAnalysis


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
