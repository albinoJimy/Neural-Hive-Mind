"""Testes para o NLU Service Client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from src.models.classification import NLUResult
from src.services.nlu_client import NLUServiceClient


@pytest.fixture
def mock_grpc_channel():
    """Mock para canal gRPC."""
    channel = AsyncMock()
    return channel


@pytest.fixture
def nlu_client(mock_grpc_channel):
    """Fixture para NLU Service Client com channel mockado."""
    client = NLUServiceClient(nlu_service_address="localhost:8020")
    client._channel = mock_grpc_channel
    return client


@pytest.mark.asyncio
class TestNLUServiceClient:
    """Testes do cliente NLU."""

    async def test_parse_success(self, nlu_client):
        """Testar parse com sucesso."""
        # Criar mock stub
        mock_stub = AsyncMock()
        nlu_client._stub = mock_stub

        # Mock response
        mock_response = Mock()
        mock_result = Mock()

        # Configurar resultado NLU (INV-1 compliance)
        mock_result.processed_text = "texto processado"
        mock_result.domain = 1  # BUSINESS enum value
        mock_result.confidence = 0.85
        mock_result.keywords = ["consultar", "dados"]
        mock_result.entities = []

        mock_response.result = mock_result
        mock_stub.Parse.return_value = mock_response

        # Chamar parse
        result = await nlu_client.parse("Consultar dados de vendas", language="pt")

        # Verificar resultado
        assert result.text == "Consultar dados de vendas"
        assert result.domain == "BUSINESS"
        assert result.confidence == 0.85
        assert "consultar" in result.keywords

    async def test_parse_grpc_error_fallback(self, nlu_client):
        """Testar fallback quando gRPC falha."""
        # Mock stub que lança erro
        mock_stub = AsyncMock()
        nlu_client._stub = mock_stub

        # Simular erro gRPC com exceção genérica
        mock_stub.Parse.side_effect = Exception("NLU Service unavailable")

        # Chamar parse - deve retornar fallback
        result = await nlu_client.parse("teste")

        # Verificar fallback values
        assert result.text == "teste"
        assert result.domain == "DOMAIN_UNKNOWN"
        assert result.confidence == 0.3
        assert result.entities == {}

    async def test_classify_domain_success(self, nlu_client):
        """Testar classify_domain com sucesso."""
        # Criar mock stub
        mock_stub = AsyncMock()
        nlu_client._stub = mock_stub

        # Mock response
        mock_response = Mock()
        mock_response.domain = 2  # TECHNICAL enum value
        mock_response.confidence = 0.9
        mock_response.reasoning = "Palavras-chave técnicas detectadas"

        mock_stub.ClassifyDomain.return_value = mock_response

        # Chamar classify_domain
        domain, confidence, reasoning = await nlu_client.classify_domain(
            "Gerar código",
            language="pt"
        )

        # Verificar resultado
        assert domain == "TECHNICAL"
        assert confidence == 0.9
        assert reasoning == "Palavras-chave técnicas detectadas"

    async def test_extract_entities_success(self, nlu_client):
        """Testar extract_entities com sucesso."""
        # Criar mock stub
        mock_stub = AsyncMock()
        nlu_client._stub = mock_stub

        # Mock response
        mock_response = Mock()

        # Criar entidades mock
        mock_entity1 = Mock()
        mock_entity1.type = 2  # ORG
        mock_entity1.value = "Google"
        mock_entity1.confidence = 0.9
        mock_entity1.start = 0
        mock_entity1.end = 6

        mock_entity2 = Mock()
        mock_entity2.type = 1  # PERSON
        mock_entity2.value = "João"
        mock_entity2.confidence = 0.85
        mock_entity2.start = 7
        mock_entity2.end = 11

        mock_response.entities = [mock_entity1, mock_entity2]
        mock_stub.ExtractEntities.return_value = mock_response

        # Chamar extract_entities
        entities = await nlu_client.extract_entities("João trabalha na Google")

        # Verificar resultado
        assert len(entities) == 2
        assert entities[0]["value"] == "Google"
        assert entities[0]["type"] == "ORG"
        assert entities[1]["value"] == "João"
        assert entities[1]["type"] == "PERSON"

    async def test_health_check_success(self, nlu_client):
        """Testar health_check com sucesso."""
        # Criar mock stub
        mock_stub = AsyncMock()
        nlu_client._stub = mock_stub

        # Mock response
        mock_response = Mock()
        mock_response.status = 1  # SERVING
        mock_response.details = {"model_loaded": "true"}
        mock_response.version = "1.0.0"

        mock_stub.HealthCheck.return_value = mock_response

        # Chamar health_check
        health = await nlu_client.health_check()

        # Verificar resultado
        assert health["status"] == "SERVING"
        assert health["version"] == "1.0.0"
        assert health["details"]["model_loaded"] == "true"

    async def test_health_check_failure(self, nlu_client):
        """Testar health_check com falha."""
        # Criar mock stub
        mock_stub = AsyncMock()
        nlu_client._stub = mock_stub

        # Simular erro
        mock_stub.HealthCheck.side_effect = Exception("Connection refused")

        # Chamar health_check
        health = await nlu_client.health_check()

        # Verificar resultado UNKNOWN
        assert health["status"] == "UNKNOWN"
        assert "error" in health["details"]

    async def test_close(self, nlu_client):
        """Testar fechamento da conexão."""
        # Criar channel mock
        mock_channel = AsyncMock()
        nlu_client._channel = mock_channel
        nlu_client._stub = Mock()

        # Fechar conexão
        await nlu_client.close()

        # Verificar que channel foi fechado e stub limpo
        mock_channel.close.assert_called_once()
        assert nlu_client._channel is None
        assert nlu_client._stub is None


@pytest.mark.asyncio
class TestNLUClientFallback:
    """Testes de fallback do cliente NLU."""

    async def test_fallback_nlu_result_structure(self):
        """Testar estrutura do resultado de fallback."""
        client = NLUServiceClient()
        result = client._fallback_nlu_result("teste", "pt")

        # Verificar campos INV-1
        assert isinstance(result, NLUResult)
        assert result.text == "teste"
        assert result.domain == "DOMAIN_UNKNOWN"
        assert result.confidence == 0.3
        assert result.entities == {}
        assert result.keywords == []

    async def test_convert_nlu_result_with_entities(self, nlu_client):
        """Testar conversão de resultado NLU com entidades."""
        # Import proto para valores de enum corretos
        from src.proto import nlu_pb2

        # Mock proto result com valores corretos de enum
        proto_result = Mock()
        proto_result.processed_text = "texto processado"
        proto_result.domain = nlu_pb2.UnifiedDomain.BUSINESS  # = 1
        proto_result.confidence = 0.8
        proto_result.keywords = ["teste", "dados"]

        # Mock entidades com valores corretos de enum
        mock_entity = Mock()
        mock_entity.type = nlu_pb2.EntityType.ORG  # = 2
        mock_entity.value = "Empresa X"
        proto_result.entities = [mock_entity]

        # Converter
        result = nlu_client._convert_nlu_result(proto_result, "texto original")

        # Verificar conversão
        assert result.text == "texto original"
        assert result.domain == "BUSINESS"
        assert result.confidence == 0.8
        assert "ORG" in result.entities
        assert result.entities["ORG"] == "Empresa X"
        assert "teste" in result.keywords


@pytest.mark.asyncio
class TestGetNLIClientSingleton:
    """Testes do singleton do cliente NLU."""

    async def test_singleton_returns_same_instance(self):
        """Testar que singleton retorna mesma instância."""
        from src.services.nlu_client import get_nlu_client, _nlu_client

        # Reset singleton
        import src.services.nlu_client as nlu_client_module
        nlu_client_module._nlu_client = None

        # Obter duas instâncias
        client1 = await get_nlu_client()
        client2 = await get_nlu_client()

        # Verificar que são a mesma instância
        assert client1 is client2
