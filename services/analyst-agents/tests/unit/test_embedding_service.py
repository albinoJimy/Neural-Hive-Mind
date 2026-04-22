"""
Testes unitários simplificados para EmbeddingService.

Focam na lógica de negócio sem mockar dependências externas complexas.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import pytest


# Mock para sentence_transformers antes da importação
class MockSentenceTransformer:
    def __init__(self, model_name):
        self.model_name = model_name

    def encode(self, texts, convert_to_numpy=True):
        if isinstance(texts, str):
            texts = [texts]
        return np.random.rand(len(texts), 384).astype(np.float32)


sys.modules["sentence_transformers"] = MagicMock()
sys.modules["sentence_transformers"].SentenceTransformer = MockSentenceTransformer

from src.services.embedding_service import EmbeddingService


@pytest.fixture()
def mock_cache_client():
    """Mock do cliente de cache."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    return cache


@pytest.fixture()
def embedding_service(mock_cache_client):
    """Instância do EmbeddingService."""
    service = EmbeddingService(model_name="test-model", cache_client=mock_cache_client)
    return service


@pytest.fixture()
def initialized_service(embedding_service):
    """Serviço com modelo inicializado."""
    embedding_service.model = MockSentenceTransformer("test-model")
    return embedding_service


class TestEmbeddingServiceInitialization:
    """Testes para inicialização."""

    def test_initialization(self, embedding_service):
        """Testa inicialização básica."""
        assert embedding_service.model_name == "test-model"
        assert embedding_service.cache_client is not None
        assert embedding_service.dimension == 384

    @pytest.mark.asyncio()
    async def test_initialize(self, embedding_service):
        """Testa inicialização do modelo."""
        await embedding_service.initialize()

        assert embedding_service.model is not None
        assert isinstance(embedding_service.model, MockSentenceTransformer)


class TestGenerateEmbedding:
    """Testes para geração de embeddings."""

    @pytest.mark.asyncio()
    async def test_generate_success(self, initialized_service):
        """Testa geração bem-sucedida."""
        result = await initialized_service.generate_embedding("test text")

        assert result is not None
        assert isinstance(result, np.ndarray)
        assert len(result) == 384

    @pytest.mark.asyncio()
    async def test_generate_without_model(self, embedding_service):
        """Testa geração sem modelo."""
        result = await embedding_service.generate_embedding("test")

        assert result is None

    @pytest.mark.asyncio()
    async def test_generate_cache_hit(self, embedding_service):
        """Testa cache hit."""
        embedding_bytes = np.array([0.1] * 384, dtype=np.float32).tobytes()
        embedding_service.cache_client.get = AsyncMock(return_value=embedding_bytes)

        result = await embedding_service.generate_embedding("test")

        assert result is not None
        embedding_service.cache_client.set.assert_not_called()

    @pytest.mark.asyncio()
    async def test_generate_cache_miss(self, initialized_service):
        """Testa cache miss."""
        initialized_service.cache_client.get = AsyncMock(return_value=None)

        result = await initialized_service.generate_embedding("test")

        assert result is not None
        initialized_service.cache_client.set.assert_called_once()


class TestBatchGenerateEmbeddings:
    """Testes para geração em lote."""

    @pytest.mark.asyncio()
    async def test_batch_generate_success(self, initialized_service):
        """Testa geração em lote."""
        texts = ["text1", "text2", "text3"]

        result = await initialized_service.batch_generate_embeddings(texts)

        assert len(result) == 3
        assert all(isinstance(r, np.ndarray) for r in result)

    @pytest.mark.asyncio()
    async def test_batch_generate_without_model(self, embedding_service):
        """Testa batch sem modelo."""
        result = await embedding_service.batch_generate_embeddings(["test"])

        assert result == []

    @pytest.mark.asyncio()
    async def test_batch_generate_empty(self, initialized_service):
        """Testa batch com lista vazia."""
        result = await initialized_service.batch_generate_embeddings([])

        assert result == []


class TestBuildIndex:
    """Testes para construção de índice."""

    @pytest.mark.asyncio()
    async def test_build_index_success(self, initialized_service):
        """Testa construção de índice."""
        texts = ["text1", "text2"]

        with patch("src.services.embedding_service.faiss.IndexFlatL2") as mock_index_class:
            mock_index = Mock()
            mock_index_class.return_value = mock_index

            result = await initialized_service.build_index(texts)

            assert result is True
            assert initialized_service.index is not None
            assert initialized_service.indexed_texts == texts

    @pytest.mark.asyncio()
    async def test_build_index_without_model(self, embedding_service):
        """Testa construção sem modelo."""
        result = await embedding_service.build_index(["test"])

        assert result is False


class TestSearchSimilar:
    """Testes para busca similar."""

    @pytest.mark.asyncio()
    async def test_search_without_index(self, initialized_service):
        """Testa busca sem índice."""
        result = await initialized_service.search_similar("query")

        assert result == []

    @pytest.mark.asyncio()
    async def test_search_with_index(self, initialized_service):
        """Testa busca com índice."""
        initialized_service.indexed_texts = ["text1", "text2"]
        initialized_service.index = Mock()
        initialized_service.index.search = Mock(
            return_value=(np.array([[0.1, 0.2]]), np.array([0, 1]))
        )

        result = await initialized_service.search_similar("query", top_k=2)

        assert isinstance(result, list)


class TestCalculateSimilarity:
    """Testes para cálculo de similaridade."""

    @pytest.mark.asyncio()
    async def test_calculate_similarity_success(self, initialized_service):
        """Testa cálculo bem-sucedido."""
        with patch("src.services.embedding_service.cosine", return_value=0.5):
            result = await initialized_service.calculate_similarity("text1", "text2")

            assert result == 0.5

    @pytest.mark.asyncio()
    async def test_calculate_similarity_without_model(self, embedding_service):
        """Testa sem modelo."""
        result = await embedding_service.calculate_similarity("a", "b")

        assert result == 0.0


class TestClusterTexts:
    """Testes para clustering."""

    @pytest.mark.asyncio()
    async def test_cluster_texts_empty(self, initialized_service):
        """Testa clustering vazio."""
        result = await initialized_service.cluster_texts([])

        assert result == []

    @pytest.mark.asyncio()
    async def test_cluster_texts_success(self, initialized_service):
        """Testa clustering bem-sucedido."""
        texts = ["text1", "text2"]

        with patch("src.services.embedding_service.DBSCAN") as mock_dbscan:
            clustering = Mock()
            clustering.fit_predict = Mock(return_value=np.array([0, 0]))
            mock_dbscan.return_value = clustering

            result = await initialized_service.cluster_texts(texts)

            assert len(result) >= 1


class TestDetectSemanticDrift:
    """Testes para deteção de drift."""

    @pytest.mark.asyncio()
    async def test_detect_drift_insufficient_data(self, embedding_service):
        """Testa com dados insuficientes."""
        result = await embedding_service.detect_semantic_drift([], ["current"])

        assert result["drift_detected"] is False

    @pytest.mark.asyncio()
    async def test_detect_drift_success(self, initialized_service):
        """Testa deteção bem-sucedida."""
        with patch("src.services.embedding_service.cosine", return_value=0.1):
            with patch(
                "src.services.embedding_service.np.mean",
                side_effect=[np.array([0.1]), np.array([0.2])],
            ):
                result = await initialized_service.detect_semantic_drift(
                    ["baseline"], ["current"], threshold=0.5
                )

                assert "drift_detected" in result


class TestFindOutliers:
    """Testes para detecção de outliers."""

    @pytest.mark.asyncio()
    async def test_find_outliers_insufficient(self, initialized_service):
        """Testa com dados insuficientes."""
        result = await initialized_service.find_outliers(["one"])

        assert result == []

    @pytest.mark.asyncio()
    async def test_find_outliers_success(self, initialized_service):
        """Testa detecção bem-sucedida."""
        texts = ["text1", "text2", "text3"]

        with patch("src.services.embedding_service.cosine", side_effect=[0.1, 0.1, 0.8]):
            with patch("src.services.embedding_service.np.percentile", return_value=0.5):
                result = await initialized_service.find_outliers(texts)

                assert isinstance(result, list)


class TestClose:
    """Testes para cleanup."""

    @pytest.mark.asyncio()
    async def test_close(self, initialized_service):
        """Testa limpeza de recursos."""
        initialized_service.model = Mock()
        initialized_service.index = Mock()
        initialized_service.indexed_texts = ["t1", "t2"]

        await initialized_service.close()

        assert initialized_service.model is None
        assert initialized_service.index is None
        assert initialized_service.indexed_texts == []
