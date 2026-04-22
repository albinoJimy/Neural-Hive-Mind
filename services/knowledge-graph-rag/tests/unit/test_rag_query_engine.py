"""Testes para RAGQueryEngine."""

import pytest
from unittest.mock import AsyncMock, Mock

from knowledge_graph_rag.models.retrieval import RetrievalResult
from knowledge_graph_rag.services.contextual_retriever import ContextualRetriever
from knowledge_graph_rag.services.rag_query_engine import RAGQueryEngine


@pytest.fixture
def mock_neo4j():
    """Mock do cliente Neo4j."""
    neo4j = Mock()
    neo4j.find_similar_architectures = AsyncMock(
        return_value=[
            {"plan_id": "ARCH-001", "similarity": 0.85, "architecture_type": "microservices"}
        ]
    )
    neo4j.get_connections_context = AsyncMock(
        return_value=[
            {"from_id": "ARCH-001", "to_id": "COMP-001", "connection_type": "HAS_COMPONENT"}
        ]
    )
    return neo4j


@pytest.fixture
def mock_qdrant():
    """Mock do cliente Qdrant."""
    qdrant = Mock()
    qdrant.search_templates = AsyncMock(
        return_value=[{"id": "TPL-001", "score": 0.9, "payload": {"name": "REST API Template"}}]
    )
    qdrant.search_code = AsyncMock(
        return_value=[{"id": "CODE-001", "score": 0.88, "payload": {"language": "python"}}]
    )
    return qdrant


@pytest.fixture
def mock_embedder():
    """Mock do serviço de embeddings."""
    embedder = Mock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    return embedder


@pytest.fixture
def rag_engine(mock_neo4j, mock_qdrant, mock_embedder):
    """Fixture para RAGQueryEngine com mocks."""
    return RAGQueryEngine(neo4j=mock_neo4j, qdrant=mock_qdrant, embedder=mock_embedder)


@pytest.mark.asyncio
async def test_hybrid_search(rag_engine, mock_qdrant, mock_neo4j):
    """Testa busca híbrida (graph + vector)."""
    results = await rag_engine.hybrid_search(query="Create REST API for user management", alpha=0.5)

    assert len(results) > 0
    assert isinstance(results[0], RetrievalResult)
    # Verifica que ambos os clientes foram chamados
    mock_qdrant.search_templates.assert_called_once()
    mock_neo4j.find_similar_architectures.assert_called_once()


@pytest.mark.asyncio
async def test_hybrid_search_vector_only(rag_engine, mock_qdrant, mock_neo4j):
    """Testa busca apenas vectorial (alpha=1)."""
    results = await rag_engine.hybrid_search(query="Create REST API", alpha=1.0)

    assert len(results) > 0
    mock_qdrant.search_templates.assert_called_once()
    # Neo4j não deve ser chamado quando alpha=1
    mock_neo4j.find_similar_architectures.assert_not_called()


@pytest.mark.asyncio
async def test_hybrid_search_graph_only(rag_engine, mock_qdrant, mock_neo4j):
    """Testa busca apenas no grafo (alpha=0)."""
    results = await rag_engine.hybrid_search(query="microservices architecture", alpha=0.0)

    assert len(results) > 0
    mock_neo4j.find_similar_architectures.assert_called_once()
    # Qdrant não deve ser chamado quando alpha=0
    mock_qdrant.search_templates.assert_not_called()


@pytest.mark.asyncio
async def test_retrieve_context(rag_engine):
    """Testa recuperação de contexto."""
    context = await rag_engine.retrieve_context(
        query="User authentication", artifact_type="architecture"
    )

    assert context.query == "User authentication"
    assert len(context.similar_architectures) > 0
    assert len(context.connections) > 0


@pytest.mark.asyncio
async def test_retrieve_context_all_types(rag_engine, mock_qdrant):
    """Testa recuperação de contexto com todos os tipos."""
    context = await rag_engine.retrieve_context(query="API development", artifact_type="all")

    assert context.query == "API development"
    assert len(context.similar_architectures) > 0
    assert len(context.similar_templates) > 0
    assert len(context.code_snippets) > 0
    # Verifica que search_templates foi chamado
    mock_qdrant.search_templates.assert_called()


@pytest.mark.asyncio
async def test_search_templates(rag_engine, mock_qdrant):
    """Testa busca de templates."""
    results = await rag_engine.search_templates(query="REST API template", limit=5)

    assert len(results) > 0
    assert results[0].type == "template"
    assert results[0].score > 0
    mock_qdrant.search_templates.assert_called_once()


@pytest.mark.asyncio
async def test_search_code(rag_engine, mock_qdrant):
    """Testa busca de código."""
    results = await rag_engine.search_code(
        query="authentication handler", limit=5, language_filter="python"
    )

    assert len(results) > 0
    assert results[0].type == "code"
    mock_qdrant.search_code.assert_called_once()


@pytest.mark.asyncio
async def test_extract_keywords(rag_engine):
    """Testa extração de palavras-chave."""
    keywords = rag_engine._extract_keywords("Create REST API for user management")

    assert len(keywords) > 0
    assert "user" in keywords or "management" in keywords
    # Stop words devem ser removidas
    assert "create" not in keywords
    assert "for" not in keywords


@pytest.mark.asyncio
async def test_combine_results_vector_only(rag_engine):
    """Testa combinação apenas com resultados vectoriais."""
    vector_results = [{"id": "V-001", "score": 0.9, "payload": {"type": "template"}}]
    graph_results = []

    combined = rag_engine._combine_results(vector_results, graph_results, alpha=0.7)

    assert len(combined) == 1
    assert combined[0].id == "V-001"
    assert combined[0].type == "vector"


@pytest.mark.asyncio
async def test_combine_results_hybrid(rag_engine):
    """Testa combinação híbrida de resultados."""
    vector_results = [{"id": "V-001", "score": 0.9, "payload": {"type": "template"}}]
    graph_results = [{"plan_id": "V-001", "similarity": 0.8, "architecture_type": "microservices"}]

    combined = rag_engine._combine_results(vector_results, graph_results, alpha=0.5)

    assert len(combined) == 1
    assert combined[0].id == "V-001"
    assert combined[0].type == "hybrid"
    # Score deve combinar ambos
    assert combined[0].score > 0


@pytest.mark.asyncio
async def test_contextual_retriever_code_generation(rag_engine):
    """Testa recuperação de contexto para geração de código."""
    retriever = ContextualRetriever(rag_engine)

    context = await retriever.retrieve_for_code_generation(
        requirements=["Create REST API", "Add authentication", "User management"],
        tech_stack={"framework": "FastAPI", "language": "python"},
    )

    assert "query" in context
    assert "tech_stack" in context
    assert context["tech_stack"]["framework"] == "FastAPI"
    assert "similar_architectures" in context
    assert "similar_templates" in context


@pytest.mark.asyncio
async def test_contextual_retriever_architecture_design(rag_engine):
    """Testa recuperação de contexto para design de arquitetura."""
    retriever = ContextualRetriever(rag_engine)

    context = await retriever.retrieve_for_architecture_design(
        requirements=["High availability", "Scalability"],
        constraints=["Use microservices", "Cloud native"],
    )

    assert "requirements" in context
    assert "constraints" in context
    assert len(context["requirements"]) == 2
    assert "similar_architectures" in context


@pytest.mark.asyncio
async def test_contextual_retriever_retrieve_context(rag_engine):
    """Testa método retrieve_context do ContextualRetriever."""
    retriever = ContextualRetriever(rag_engine)

    context = await retriever.retrieve_context(query="Database design", context_type="architecture")

    assert context.query == "Database design"
    assert len(context.similar_architectures) > 0


@pytest.mark.asyncio
async def test_contextual_retriever_with_filters(rag_engine, mock_qdrant):
    """Testa recuperação com filtros."""
    retriever = ContextualRetriever(rag_engine)

    context = await retriever.retrieve_with_filters(
        query="API endpoint", filters={"language": "python", "stack": "FastAPI"}, limit=5
    )

    assert context.query == "API endpoint"
    # Verifica que search_code foi chamado com language filter
    mock_qdrant.search_code.assert_called_once()


@pytest.mark.asyncio
async def test_search_templates_empty_results(rag_engine, mock_qdrant):
    """Testa busca de templates com resultados vazios."""
    mock_qdrant.search_templates = AsyncMock(return_value=[])

    results = await rag_engine.search_templates(query="unknown template")

    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_code_with_language_filter(rag_engine, mock_qdrant):
    """Testa busca de código com filtro de linguagem."""
    results = await rag_engine.search_code(query="handler", language_filter="python")

    # Verifica que o filtro foi passado
    call_args = mock_qdrant.search_code.call_args
    assert call_args.kwargs["language_filter"] == "python"
    assert len(results) > 0


@pytest.mark.asyncio
async def test_hybrid_search_limit(rag_engine):
    """Testa que busca híbrida respeita o limite."""
    # Configurar mocks para retornar mais resultados que o limite
    rag_engine.qdrant.search_templates = AsyncMock(
        return_value=[
            {"id": f"TPL-{i:03d}", "score": 0.9 - i * 0.05, "payload": {}} for i in range(20)
        ]
    )
    rag_engine.neo4j.find_similar_architectures = AsyncMock(
        return_value=[{"plan_id": f"ARCH-{i:03d}", "similarity": 0.8 - i * 0.05} for i in range(15)]
    )

    results = await rag_engine.hybrid_search(query="test", limit=5)

    assert len(results) <= 5


@pytest.mark.asyncio
async def test_retrieve_context_code_artifact_type(rag_engine, mock_qdrant):
    """Testa retrieve_context com artifact_type='code'."""
    context = await rag_engine.retrieve_context(query="algorithm", artifact_type="code")

    assert len(context.code_snippets) > 0
    # Templates não devem ser buscados
    mock_qdrant.search_code.assert_called()


@pytest.mark.asyncio
async def test_extract_keywords_empty_query(rag_engine):
    """Testa extração de palavras-chave com query simples."""
    keywords = rag_engine._extract_keywords("the and or")

    # Apenas stop words
    assert len(keywords) == 0


@pytest.mark.asyncio
async def test_combine_results_score_calculation(rag_engine):
    """Testa cálculo de score na combinação."""
    vector_results = [{"id": "V-001", "score": 1.0, "payload": {}}]
    graph_results = [{"plan_id": "V-001", "similarity": 0.8, "type": "arch"}]

    # Com alpha=0.5, score deve ser 0.5*1.0 + 0.5*0.8 = 0.9
    combined = rag_engine._combine_results(vector_results, graph_results, alpha=0.5)

    assert abs(combined[0].score - 0.9) < 0.01
