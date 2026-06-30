"""Teste de integração: propagação de `source` do corpo /intentions -> IntentEnvelope.context.

Spec journey-router Fase 4 (Crítico 1). O `doc-ingestion` envia
`context.source="doc-ingestion"` (e, por conveniência, pode enviar `source` no topo
do corpo). O gateway DEVE propagar esse marcador para `IntentEnvelope.context.source`,
pois o JourneyClassifier do STE lê `context.get("source")` e resolve J4_MIGRATE.

Anteriormente o `IntentRequest` (Pydantic) não tinha campo `source` -> extra ignorado
-> marcador descartado -> J4 nunca disparava por este caminho.

Este teste exercita o endpoint REAL `/intentions` (TestClient) e inspeciona o
`IntentEnvelope` efetivamente publicado em `kafka_producer.send_intent`, validando
tanto o atributo do modelo (`envelope.context.source`) como a forma serializada
(`to_avro_dict()["context"]["source"]`) que é o que chega ao STE.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))


@pytest.fixture()
def mock_pipelines_and_producer():
    from models.intent_envelope import Entity, NLUResult

    # Confiança alta -> caminho que publica o envelope normalmente.
    nlu_result = NLUResult(
        domain="business",
        classification="request",
        confidence=0.95,
        processed_text="migrar sistema legado",
        entities=[Entity(type="ACTION", value="migrar", confidence=0.9, start=0, end=6)],
        keywords=["migrar", "legado"],
        processing_time_ms=80.0,
    )

    # Pular validação de autenticação (mesmo padrão de test_tracing_integration).
    async def mock_dispatch(self, request, call_next):
        request.state.authenticated = True
        request.state.user = {
            "user_id": "test-user",
            "username": "test-user",
            "client_id": "test-tenant",
            "roles": ["user"],
        }
        return await call_next(request)

    with (
        patch("main.nlu_pipeline") as mock_nlu,
        patch("main.kafka_producer") as mock_kafka,
        patch("main.redis_client") as mock_redis,
        patch("main.health_manager") as mock_health,
        patch("middleware.auth_middleware.AuthMiddleware.dispatch", mock_dispatch),
    ):
        mock_nlu.process = AsyncMock(return_value=nlu_result)
        mock_nlu.is_ready.return_value = True
        mock_nlu.confidence_threshold = 0.75

        mock_kafka.send_intent = AsyncMock(return_value=None)
        mock_kafka.is_ready.return_value = True

        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=None)

        mock_health.check_all = AsyncMock(return_value={"status": "healthy", "checks": {}})
        mock_health.get_overall_status.return_value = "healthy"

        yield {"nlu": mock_nlu, "kafka": mock_kafka, "redis": mock_redis}


@pytest.fixture()
def test_client():
    with patch("main.settings") as mock_settings:
        mock_settings.environment = "test"
        mock_settings.token_validation_enabled = False
        mock_settings.otel_enabled = False
        mock_settings.nlu_adaptive_threshold_enabled = False
        mock_settings.nlu_routing_threshold_high = 0.8
        mock_settings.nlu_routing_threshold_low = 0.5
        mock_settings.nlu_routing_use_adaptive_for_decisions = False
        mock_settings.redis_default_ttl = 3600

        from main import app

        client = TestClient(app, raise_server_exceptions=False)
        yield client


@pytest.mark.integration()
class TestIntentSourcePropagation:
    """O marcador `source` do corpo deve sobreviver até IntentEnvelope.context.source."""

    def test_doc_ingestion_source_reaches_envelope_context(
        self, test_client, mock_pipelines_and_producer
    ):
        response = test_client.post(
            "/intentions",
            json={
                "text": "Migrar sistema legado a partir de documentacao",
                "language": "pt-BR",
                "source": "doc-ingestion",
            },
            headers={"Authorization": "Bearer test-token", "Host": "localhost"},
        )

        assert response.status_code == 200, response.text

        # Capturar o IntentEnvelope efetivamente publicado.
        mock_kafka = mock_pipelines_and_producer["kafka"]
        assert mock_kafka.send_intent.await_count >= 1
        published_envelope = mock_kafka.send_intent.await_args.args[0]

        # 1) Atributo do modelo.
        assert published_envelope.context is not None
        assert published_envelope.context.source == "doc-ingestion"

        # 2) Forma serializada (o que chega ao STE via Avro/JSON).
        avro = published_envelope.to_avro_dict()
        assert avro["context"]["source"] == "doc-ingestion"

    def test_absent_source_keeps_context_source_none(
        self, test_client, mock_pipelines_and_producer
    ):
        """Sem `source` no corpo -> context.source fica None (não inventa marcador)."""
        response = test_client.post(
            "/intentions",
            json={"text": "Preciso de ajuda com o projeto", "language": "pt-BR"},
            headers={"Authorization": "Bearer test-token", "Host": "localhost"},
        )

        assert response.status_code == 200, response.text

        mock_kafka = mock_pipelines_and_producer["kafka"]
        published_envelope = mock_kafka.send_intent.await_args.args[0]

        assert published_envelope.context is not None
        assert getattr(published_envelope.context, "source", None) is None
        assert published_envelope.to_avro_dict()["context"]["source"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
