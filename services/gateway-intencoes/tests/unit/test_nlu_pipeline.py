"""Testes unitários para NLUPipeline (versão gRPC Service)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grpc.aio import AioRpcError
from models.intent_envelope import NLUResult
from pipelines.nlu_pipeline_service import NLUPipeline

from neural_hive_domain import UnifiedDomain


@pytest.fixture()
def nlu_pipeline():
    """Fixture do pipeline NLU com adapter mockado."""
    from src.services.nlu_service_adapter import NLUServiceAdapter

    # Mock dos clientes
    mock_nlu_client = MagicMock(spec=["parse", "HealthCheck", "close"])
    mock_nlu_client.parse = AsyncMock()

    mock_pii_client = MagicMock(spec=["detect", "mask", "HealthCheck", "close"])
    mock_pii_client.mask = AsyncMock(return_value="[MASKED]text")  # Retorna texto mascarado

    adapter = NLUServiceAdapter(
        nlu_client=mock_nlu_client,
        pii_client=mock_pii_client,
    )
    pipeline = NLUPipeline()
    pipeline._adapter = adapter
    pipeline._ready = True

    # Guardar referência aos mocks para usar nos testes
    pipeline._mock_nlu = mock_nlu_client
    pipeline._mock_pii = mock_pii_client

    return pipeline


def _create_mock_nlu_response(
    domain: str = "TECHNICAL",
    confidence: float = 0.85,
    text: str = "test text",
    classification: str = "test",
    entities: list | None = None,
    keywords: list | None = None,
    requires_validation: bool = False,
) -> MagicMock:
    """Helper para criar mock response do NLU Service."""
    mock_response = MagicMock()
    mock_response.domain = domain
    mock_response.confidence = confidence
    mock_response.text = text
    mock_response.classification = classification
    mock_response.entities = entities or []
    mock_response.keywords = keywords or []
    mock_response.language = "pt"
    mock_response.requires_validation = requires_validation

    return mock_response


class TestNLUPipeline:
    """Testes para a classe NLUPipeline (gRPC version)."""

    @pytest.mark.asyncio()
    async def test_initialize_pipeline(self):
        """Teste de inicialização do pipeline."""
        with patch("grpc_clients.nlu_client.get_nlu_client") as mock_get_nlu, \
             patch("grpc_clients.pii_client.get_pii_client") as mock_get_pii:

            mock_nlu = MagicMock()
            mock_nlu.connect = AsyncMock()
            mock_pii = MagicMock()
            mock_pii.connect = AsyncMock()

            mock_get_nlu.return_value = mock_nlu
            mock_get_pii.return_value = mock_pii

            pipeline = NLUPipeline()
            await pipeline.initialize()

            assert pipeline.is_ready() is True
            mock_get_nlu.assert_called_once()
            mock_get_pii.assert_called_once()

    @pytest.mark.asyncio()
    async def test_process_text_success(self, nlu_pipeline):
        """Teste de processamento de texto bem-sucedido."""
        # Criar entidades mock
        mock_entity1 = MagicMock()
        mock_entity1.type = "PERSON"
        mock_entity1.value = "João"
        mock_entity1.start = 0
        mock_entity1.end = 4
        mock_entity1.confidence = 0.95

        mock_entity2 = MagicMock()
        mock_entity2.type = "ORG"
        mock_entity2.value = "Empresa"
        mock_entity2.start = 15
        mock_entity2.end = 22
        mock_entity2.confidence = 0.88

        mock_response = _create_mock_nlu_response(
            domain="TECHNICAL",
            confidence=0.85,
            text="João precisa implementar novo sistema na Empresa",
            classification="implementation",
            entities=[mock_entity1, mock_entity2],
            keywords=["implementar", "sistema"],
        )

        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        user_context = {"userId": "user-123", "tenantId": "tenant-456"}

        result = await nlu_pipeline.process(
            text="João precisa implementar novo sistema na Empresa",
            language="pt-BR",
            context=user_context,
        )

        assert isinstance(result, NLUResult)
        assert result.domain == UnifiedDomain.TECHNICAL
        assert result.classification == "TECHNICAL"  # domain usado como classification
        assert result.confidence == 0.85
        assert len(result.entities) == 2
        assert result.entities[0].type == "PERSON"
        assert result.entities[0].value == "João"
        assert "implementar" in result.keywords

    @pytest.mark.asyncio()
    async def test_process_text_low_confidence(self, nlu_pipeline):
        """Teste com confiança baixa."""
        mock_response = _create_mock_nlu_response(
            domain="BUSINESS",
            confidence=0.35,
            text="texto ambíguo sem contexto claro",
            classification="unknown",
            requires_validation=True,
        )

        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        result = await nlu_pipeline.process(
            text="texto ambíguo sem contexto claro",
            language="pt-BR",
            context={},
        )

        assert result.confidence == 0.35
        assert result.confidence_status == "low"
        assert result.requires_manual_validation is True

    @pytest.mark.asyncio()
    async def test_domain_mapping(self, nlu_pipeline):
        """Teste de mapeamento de domínios do gRPC para UnifiedDomain."""
        test_cases = [
            ("BUSINESS", UnifiedDomain.BUSINESS),
            ("TECHNICAL", UnifiedDomain.TECHNICAL),
            ("INFRASTRUCTURE", UnifiedDomain.INFRASTRUCTURE),
            ("SECURITY", UnifiedDomain.SECURITY),
        ]

        for grpc_domain, expected_domain in test_cases:
            mock_response = _create_mock_nlu_response(domain=grpc_domain)
            nlu_pipeline._mock_nlu.parse.return_value = mock_response

            result = await nlu_pipeline.process(text="test", language="pt-BR", context={})
            assert result.domain == expected_domain

    @pytest.mark.asyncio()
    async def test_language_normalization(self, nlu_pipeline):
        """Teste de normalização de idioma (pt-BR -> pt)."""
        mock_response = _create_mock_nlu_response(
            text="implementar",
            keywords=["implementar"],
        )
        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        # Deve enviar apenas "pt" para o serviço
        await nlu_pipeline.process(text="implementar", language="pt-BR", context={})

        call_args = nlu_pipeline._mock_nlu.parse.call_args
        assert call_args[1]["language"] == "pt"  # normalized

    @pytest.mark.asyncio()
    async def test_grpc_error_handling_with_fallback(self, nlu_pipeline):
        """Teste de tratamento de erro gRPC com fallback ativado."""
        nlu_pipeline._mock_nlu.parse.side_effect = Exception("Service unavailable")

        result = await nlu_pipeline.process(text="consultar dashboard", language="pt-BR", context={})

        # Fallback deve classificar por keywords
        assert result.domain == UnifiedDomain.BUSINESS  # "consultar" → BUSINESS
        assert result.confidence == 0.4
        assert result.confidence_status == "low"

    @pytest.mark.asyncio()
    async def test_process_not_ready(self):
        """Teste de processamento quando pipeline não está pronto."""
        pipeline = NLUPipeline()
        pipeline._ready = False

        with pytest.raises(RuntimeError, match="Pipeline NLU não inicializado"):
            await pipeline.process(text="test text", language="pt-BR", context={})

    @pytest.mark.asyncio()
    async def test_close_pipeline(self, nlu_pipeline):
        """Teste de fechamento do pipeline."""
        nlu_pipeline._ready = True
        nlu_pipeline._adapter = MagicMock()

        await nlu_pipeline.close()

        assert nlu_pipeline.is_ready() is False

    @pytest.mark.asyncio()
    async def test_context_passed_to_service(self, nlu_pipeline):
        """Teste que contexto é passado corretamente para o serviço."""
        mock_response = _create_mock_nlu_response()
        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        user_context = {"userId": "user-123", "tenantId": "tenant-456"}

        await nlu_pipeline.process(text="test", language="pt-BR", context=user_context)

        call_args = nlu_pipeline._mock_nlu.parse.call_args
        assert "context" in call_args[1]
        assert call_args[1]["context"] == user_context

    @pytest.mark.asyncio()
    async def test_empty_text_handling(self, nlu_pipeline):
        """Teste de tratamento de texto vazio."""
        mock_response = _create_mock_nlu_response(
            domain="UNKNOWN",
            confidence=0.0,
            text="",
            classification="empty",
        )
        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        # Mock PII client para retornar o mesmo texto vazio (sem mascarar)
        nlu_pipeline._mock_pii.mask.return_value = ""

        result = await nlu_pipeline.process(text="", language="pt-BR", context={})

        assert result.processed_text == ""
        assert result.confidence == 0.0

    @pytest.mark.asyncio()
    async def test_entity_conversion(self, nlu_pipeline):
        """Teste de conversão de entidades gRPC para Entity local."""
        grpc_entity = MagicMock()
        grpc_entity.type = "PERSON"
        grpc_entity.value = "João Silva"
        grpc_entity.start = 1  # Usar 1 em vez de 0 (adapter usa > 0)
        grpc_entity.end = 10
        grpc_entity.confidence = 0.92

        mock_response = _create_mock_nlu_response(
            domain="BUSINESS",
            confidence=0.88,
            text="João Silva solicitou acesso",
            classification="request",
            entities=[grpc_entity],
            keywords=["solicitou", "acesso"],
        )
        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        result = await nlu_pipeline.process(
            text="João Silva solicitou acesso",
            language="pt-BR",
            context={},
        )

        assert len(result.entities) == 1
        entity = result.entities[0]
        assert entity.type == "PERSON"
        assert entity.value == "João Silva"
        assert entity.start == 1
        assert entity.end == 10
        assert entity.confidence == 0.92

    @pytest.mark.asyncio()
    async def test_confidence_status_calculation(self, nlu_pipeline):
        """Teste de cálculo de status de confiança."""
        test_cases = [
            (0.95, "high"),
            (0.75, "high"),
            (0.55, "medium"),
            (0.35, "low"),
            (0.15, "low"),
        ]

        for confidence, expected_status in test_cases:
            mock_response = _create_mock_nlu_response(confidence=confidence)
            nlu_pipeline._mock_nlu.parse.return_value = mock_response

            result = await nlu_pipeline.process(text="test", language="pt-BR", context={})
            assert result.confidence_status == expected_status, f"Confidence {confidence} should be {expected_status}"

    @pytest.mark.asyncio()
    async def test_cache_behavior(self, nlu_pipeline):
        """Teste de comportamento com cache (delegado ao NLU Service)."""
        mock_response = _create_mock_nlu_response()
        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        # Primeira chamada
        result1 = await nlu_pipeline.process(
            text="implementar autenticação",
            language="pt-BR",
            context={},
        )

        # O adapter deve passar enable_cache=True por padrão
        call_args = nlu_pipeline._mock_nlu.parse.call_args
        assert call_args[1]["enable_cache"] is True

    @pytest.mark.asyncio()
    async def test_pii_masking(self, nlu_pipeline):
        """Teste de mascaramento de PII."""
        mock_response = _create_mock_nlu_response(
            text="Maria Silva precisa acessar maria@exemplo.com",
        )
        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        # Mock do PII client retornar texto mascarado
        nlu_pipeline._mock_pii.mask.return_value = "[PERSON] precisa acessar [EMAIL]"

        result = await nlu_pipeline.process(
            text="Maria Silva precisa acessar maria@exemplo.com",
            language="pt-BR",
            context={},
        )

        # Verificar que o PII masking foi chamado
        nlu_pipeline._mock_pii.mask.assert_called_once()
        assert "[PERSON]" in result.processed_text

    @pytest.mark.asyncio()
    async def test_pii_masking_failure_uses_original(self, nlu_pipeline):
        """Teste que falha no PII masking usa texto original."""
        mock_response = _create_mock_nlu_response(
            text="original text",
        )
        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        # Mock do PII client falhar
        nlu_pipeline._mock_pii.mask.side_effect = Exception("PII service down")

        result = await nlu_pipeline.process(
            text="original text",
            language="pt-BR",
            context={},
        )

        # Deve usar texto original quando PII falha
        assert result.processed_text == "original text"

    @pytest.mark.asyncio()
    async def test_unknown_domain_mapping(self, nlu_pipeline):
        """Teste de domínio desconhecido mapeia para UNKNOWN."""
        mock_response = _create_mock_nlu_response(domain="INVALID_DOMAIN")
        nlu_pipeline._mock_nlu.parse.return_value = mock_response

        result = await nlu_pipeline.process(text="test", language="pt-BR", context={})
        assert result.domain == UnifiedDomain.UNKNOWN
