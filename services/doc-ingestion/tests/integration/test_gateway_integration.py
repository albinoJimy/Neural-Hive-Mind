"""Testes de integração com Gateway Intenções."""

import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.models.entities import EntitySet, EntityType, ExtractedEntity
from src.services.gateway_client import GatewayClient, GatewayClientError


@pytest.fixture
def gateway_settings():
    """Configurações de teste para Gateway."""
    return MagicMock(
        gateway_url="http://gateway-intencoes:8000",
        gateway_timeout=30.0,
    )


@pytest.fixture
def sample_entities():
    """Entidades de exemplo extraídas de documento."""
    return [
        ExtractedEntity(
            id=str(uuid.uuid4()),
            type=EntityType.FUNCTIONALITY,
            name="User Management",
            description="System for managing users including CRUD operations",
            source_text="The system provides comprehensive user management",
            confidence_score=0.9,
            document_id="doc-001",
        ),
        ExtractedEntity(
            id=str(uuid.uuid4()),
            type=EntityType.API,
            name="GET /api/users",
            description="Endpoint to list all users",
            source_text="GET /api/users returns a list of users",
            confidence_score=0.85,
            document_id="doc-001",
        ),
        ExtractedEntity(
            id=str(uuid.uuid4()),
            type=EntityType.REQUIREMENT,
            name="Authentication Required",
            description="All endpoints must require authentication",
            source_text="Authentication is required for all API endpoints",
            confidence_score=0.95,
            document_id="doc-001",
        ),
    ]


@pytest.fixture
def entity_set(sample_entities):
    """Conjunto de entidades."""
    return EntitySet(
        document_id="doc-001",
        entities=sample_entities,
    )


class TestGatewayClient:
    """Testes do cliente de integração com Gateway."""

    @pytest.mark.asyncio
    async def test_generate_cognitive_plan_from_entities(self, gateway_settings, entity_set):
        """Testa geração de CognitivePlan a partir de EntitySet."""
        client = GatewayClient(gateway_settings.gateway_url)
        plan = await client.generate_cognitive_plan(entity_set)

        assert plan is not None
        assert "text" in plan
        assert "document_id" in plan
        assert plan["document_id"] == "doc-001"

        # Verificar que o texto contém as entidades principais
        assert "User Management" in plan["text"]
        assert "Authentication" in plan["text"]

    @pytest.mark.asyncio
    async def test_generate_cognitive_plan_empty_entities(self, gateway_settings):
        """Testa geração de plano com entidades vazias."""
        client = GatewayClient(gateway_settings.gateway_url)
        empty_set = EntitySet(document_id="doc-001", entities=[])

        plan = await client.generate_cognitive_plan(empty_set)

        # Deve gerar plano com mensagem placeholder
        assert plan is not None
        assert "text" in plan
        assert "no entities" in plan["text"].lower() or "no information" in plan["text"].lower()

    @pytest.mark.asyncio
    async def test_send_to_gateway_success(
        self,
        gateway_settings,
        entity_set,
    ):
        """Testa envio bem-sucedido de entidades para Gateway."""
        client = GatewayClient(gateway_settings.gateway_url)

        # Mock response do Gateway
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "intent_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()),
            "status": "processing",
            "message": "Intention received",
        }

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response) as mock_post:
            result = await client.send_to_gateway(
                document_id="doc-001",
                entity_set=entity_set,
                ingestion_id="ingestion-001",
            )

            assert result["status"] == "processing"
            assert "intent_id" in result
            assert "correlation_id" in result

            # Verificar que a chamada foi feita corretamente
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "intentions" in str(call_args)

    @pytest.mark.asyncio
    async def test_send_to_gateway_http_error(self, gateway_settings, entity_set):
        """Testa tratamento de erro HTTP ao enviar para Gateway."""
        client = GatewayClient(gateway_settings.gateway_url)

        # Mock erro HTTP
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_error = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        with patch.object(httpx.AsyncClient, "post", side_effect=mock_error):
            with pytest.raises(GatewayClientError) as exc_info:
                await client.send_to_gateway(
                    document_id="doc-001",
                    entity_set=entity_set,
                )

            # A mensagem de erro deve conter indicador de falha
            assert "Failed to send" in str(exc_info.value) or "Server error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_to_gateway_timeout(self, gateway_settings, entity_set):
        """Testa tratamento de timeout ao enviar para Gateway."""
        client = GatewayClient(gateway_settings.gateway_url, timeout=0.1)

        # Mock timeout
        with patch.object(httpx.AsyncClient, "post", side_effect=httpx.TimeoutException("Timeout")):
            with pytest.raises(GatewayClientError) as exc_info:
                await client.send_to_gateway(
                    document_id="doc-001",
                    entity_set=entity_set,
                )

            assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_check_intent_status_success(self, gateway_settings):
        """Testa verificação de status de intent."""
        client = GatewayClient(gateway_settings.gateway_url)
        intent_id = str(uuid.uuid4())

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "intent_id": intent_id,
            "status": "completed",
            "data": {
                "intent": {"text": "User wants to migrate user management system"},
                "confidence": 0.85,
            },
            "cached": True,
        }

        with patch.object(httpx.AsyncClient, "get", return_value=mock_response) as mock_get:
            status = await client.check_intent_status(intent_id)

            assert status["status"] == "completed"
            assert "data" in status

            # Verificar URL correta
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert intent_id in str(call_args)

    @pytest.mark.asyncio
    async def test_check_intent_status_not_found(self, gateway_settings):
        """Testa status de intent não encontrado."""
        client = GatewayClient(gateway_settings.gateway_url)
        intent_id = str(uuid.uuid4())

        # Mock 404
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_error = httpx.HTTPStatusError("Not found", request=MagicMock(), response=mock_response)

        with patch.object(httpx.AsyncClient, "get", side_effect=mock_error):
            status = await client.check_intent_status(intent_id)

            # Deve retornar None para 404 (não é erro, apenas não encontrado)
            assert status is None

    @pytest.mark.asyncio
    async def test_build_intent_request_with_metadata(self, gateway_settings, entity_set):
        """Testa construção de IntentRequest com metadados."""
        client = GatewayClient(gateway_settings.gateway_url)

        plan = await client.generate_cognitive_plan(entity_set)
        request = client._build_intent_request(
            document_id="doc-001",
            plan=plan,
            ingestion_id="ingestion-001",
        )

        assert request["text"] == plan["text"]
        assert request["language"] == "pt-BR"
        assert request["source"] == "legacy_document"

        # Verificar metadados
        assert request["metadata"]["document_id"] == "doc-001"
        assert request["metadata"]["ingestion_id"] == "ingestion-001"
        assert request["metadata"]["entity_count"] == 3

    @pytest.mark.asyncio
    async def test_send_to_gateway_with_retry(
        self,
        gateway_settings,
        entity_set,
    ):
        """Testa retry em caso de falha temporária."""
        client = GatewayClient(gateway_settings.gateway_url, max_retries=2)

        # Primeira chamada falha, segunda sucesso
        mock_error = httpx.ConnectError("Connection refused")
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "intent_id": str(uuid.uuid4()),
            "status": "processing",
        }

        with patch.object(
            httpx.AsyncClient, "post", side_effect=[mock_error, mock_response]
        ) as mock_post:
            result = await client.send_to_gateway(
                document_id="doc-001",
                entity_set=entity_set,
            )

            assert result["status"] == "processing"
            assert mock_post.call_count == 2  # Primeira falha, retry sucesso


class TestGatewayIngestionMarker:
    """Marcador de ingestão (J4) — Fase 4 / Task 5.1.

    Garante que a intenção construída por doc-ingestion carrega o sinal
    estruturado ``context.source == "doc-ingestion"`` (e hint opcional), que o
    Tier 1 do JourneyClassifier (STE) usa para classificar a jornada como
    J4_MIGRATE sem invocar o LLM.
    """

    @pytest.mark.asyncio
    async def test_intent_request_has_context_source_doc_ingestion(
        self, gateway_settings, entity_set
    ):
        """A intenção construída marca context.source == 'doc-ingestion'."""
        client = GatewayClient(gateway_settings.gateway_url)

        plan = await client.generate_cognitive_plan(entity_set)
        request = client._build_intent_request(
            document_id="doc-001",
            plan=plan,
            ingestion_id="ingestion-001",
        )

        # O envelope tem de expor context.source para o sinal estruturado do
        # Tier 1 (sinais, não keywords).
        assert "context" in request
        assert isinstance(request["context"], dict)
        assert request["context"]["source"] == "doc-ingestion"

    @pytest.mark.asyncio
    async def test_intent_request_has_journey_hint_migrate(self, gateway_settings, entity_set):
        """A intenção inclui o hint opcional journey_hint == 'MIGRATE'."""
        client = GatewayClient(gateway_settings.gateway_url)

        plan = await client.generate_cognitive_plan(entity_set)
        request = client._build_intent_request(
            document_id="doc-001",
            plan=plan,
            ingestion_id="ingestion-001",
        )

        metadata = request["context"].get("metadata", {})
        assert metadata.get("journey_hint") == "MIGRATE"

    @pytest.mark.asyncio
    async def test_context_source_preserves_legacy_top_level_source(
        self, gateway_settings, entity_set
    ):
        """O context.source novo não quebra o source legado top-level."""
        client = GatewayClient(gateway_settings.gateway_url)

        plan = await client.generate_cognitive_plan(entity_set)
        request = client._build_intent_request(
            document_id="doc-001",
            plan=plan,
            ingestion_id="ingestion-001",
        )

        # Compatibilidade: o campo legado mantém-se intacto.
        assert request["source"] == "legacy_document"
        # E o novo sinal estruturado é o que o Tier 1 consome.
        assert request["context"]["source"] == "doc-ingestion"

    def test_context_source_matches_classifier_tier1_marker(self):
        """O valor marcado bate certo com o marcador esperado pelo Tier 1.

        Contrato de encadeamento (sem import cross-service frágil): o Tier 1 do
        JourneyClassifier (STE) classifica J4_MIGRATE quando
        ``context.source == "doc-ingestion"``. Verificamos que o marcador
        gravado por doc-ingestion é exatamente essa string.
        """
        # Marcador canónico esperado pelo Tier 1 (STE journey_classifier).
        tier1_doc_ingestion_marker = "doc-ingestion"

        client = GatewayClient("http://gateway-intencoes:8000")
        request = client._build_intent_request(
            document_id="doc-001",
            plan={"text": "x", "entity_count": 0},
            ingestion_id="ingestion-001",
        )

        assert request["context"]["source"] == tier1_doc_ingestion_marker
