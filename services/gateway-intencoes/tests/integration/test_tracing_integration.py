"""Testes de integração para trace IDs nas respostas da API"""
import pytest
import re
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# Regex para validação de formatos hexadecimais
TRACE_ID_PATTERN = re.compile(r'^[0-9a-f]{32}$')
SPAN_ID_PATTERN = re.compile(r'^[0-9a-f]{16}$')


@pytest.fixture
def mock_pipelines_and_producer():
    """Mock dos pipelines e producer para testes de endpoint"""
    from pipelines.nlu_pipeline import NLUResult, Entity

    nlu_result = NLUResult(
        domain="business",
        classification="request",
        confidence=0.88,
        processed_text="teste de intenção processada",
        entities=[
            Entity(
                entity_type="ACTION",
                value="teste",
                confidence=0.9,
                start=0,
                end=5
            )
        ],
        keywords=["teste", "intenção"],
        processing_time_ms=80.0
    )

    with patch('main.nlu_pipeline') as mock_nlu, \
         patch('main.kafka_producer') as mock_kafka, \
         patch('main.redis_client') as mock_redis, \
         patch('main.health_manager') as mock_health:

        mock_nlu.process = AsyncMock(return_value=nlu_result)
        mock_nlu.is_ready.return_value = True
        mock_nlu.confidence_threshold = 0.75

        mock_kafka.send_intent = AsyncMock(return_value=None)
        mock_kafka.is_ready.return_value = True

        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=None)

        mock_health.check_all = AsyncMock(return_value={"status": "healthy", "checks": {}})
        mock_health.get_overall_status.return_value = "healthy"

        yield {
            'nlu': mock_nlu,
            'kafka': mock_kafka,
            'redis': mock_redis,
            'health': mock_health
        }


@pytest.fixture
def mock_voice_pipelines(mock_pipelines_and_producer):
    """Mock adicional para pipeline ASR (voz)"""
    from pipelines.asr_pipeline import ASRResult

    asr_result = ASRResult(
        text="teste de intenção de áudio",
        confidence=0.95,
        language="pt-BR",
        duration=2.5,
        processing_time_ms=150.0
    )

    with patch('main.asr_pipeline') as mock_asr:
        mock_asr.process = AsyncMock(return_value=asr_result)
        mock_asr.is_ready.return_value = True

        yield {
            **mock_pipelines_and_producer,
            'asr': mock_asr
        }


@pytest.fixture
def test_client():
    """Cliente de teste FastAPI"""
    # Patch settings antes de importar app
    with patch('main.settings') as mock_settings:
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


@pytest.mark.integration
class TestTracingIntegration:
    """Testes de integração para trace IDs nas respostas"""

    def test_text_intention_includes_trace_ids_when_tracing_enabled(
        self, test_client, mock_pipelines_and_producer
    ):
        """Verifica se endpoint /intentions retorna traceId e spanId quando tracing está ativo"""
        mock_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
        mock_span_id = "00f067aa0ba902b7"

        with patch('main.get_current_trace_id', return_value=mock_trace_id), \
             patch('main.get_current_span_id', return_value=mock_span_id):

            response = test_client.post(
                "/intentions",
                json={
                    "text": "Preciso de ajuda com meu projeto",
                    "language": "pt-BR"
                }
            )

            # Verificar resposta
            assert response.status_code == 200
            data = response.json()

            # Verificar presença dos campos de trace
            assert "traceId" in data
            assert "spanId" in data

            # Verificar valores
            assert data["traceId"] == mock_trace_id
            assert data["spanId"] == mock_span_id

            # Verificar formato hexadecimal
            assert TRACE_ID_PATTERN.match(data["traceId"])
            assert SPAN_ID_PATTERN.match(data["spanId"])

    def test_text_intention_trace_ids_null_when_tracing_disabled(
        self, test_client, mock_pipelines_and_producer
    ):
        """Verifica se traceId e spanId são null quando tracing está desabilitado"""
        with patch('main.get_current_trace_id', return_value=None), \
             patch('main.get_current_span_id', return_value=None):

            response = test_client.post(
                "/intentions",
                json={
                    "text": "Preciso de ajuda com meu projeto",
                    "language": "pt-BR"
                }
            )

            # Verificar resposta
            assert response.status_code == 200
            data = response.json()

            # Verificar presença dos campos de trace
            assert "traceId" in data
            assert "spanId" in data

            # Verificar que são null
            assert data["traceId"] is None
            assert data["spanId"] is None

    def test_voice_intention_includes_trace_ids_when_tracing_enabled(
        self, test_client, mock_voice_pipelines
    ):
        """Verifica se endpoint /intentions/voice retorna traceId e spanId quando tracing está ativo"""
        mock_trace_id = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
        mock_span_id = "1234567890abcdef"

        with patch('main.get_current_trace_id', return_value=mock_trace_id), \
             patch('main.get_current_span_id', return_value=mock_span_id):

            # Criar arquivo de áudio fake
            audio_content = b"fake-audio-content-for-test"

            response = test_client.post(
                "/intentions/voice",
                files={"audio_file": ("test.wav", audio_content, "audio/wav")},
                data={"language": "pt-BR"}
            )

            # Verificar resposta
            assert response.status_code == 200
            data = response.json()

            # Verificar presença dos campos de trace
            assert "traceId" in data
            assert "spanId" in data

            # Verificar valores
            assert data["traceId"] == mock_trace_id
            assert data["spanId"] == mock_span_id

            # Verificar formato hexadecimal
            assert TRACE_ID_PATTERN.match(data["traceId"])
            assert SPAN_ID_PATTERN.match(data["spanId"])

    def test_voice_intention_trace_ids_null_when_tracing_disabled(
        self, test_client, mock_voice_pipelines
    ):
        """Verifica se traceId e spanId são null para voz quando tracing está desabilitado"""
        with patch('main.get_current_trace_id', return_value=None), \
             patch('main.get_current_span_id', return_value=None):

            # Criar arquivo de áudio fake
            audio_content = b"fake-audio-content-for-test"

            response = test_client.post(
                "/intentions/voice",
                files={"audio_file": ("test.wav", audio_content, "audio/wav")},
                data={"language": "pt-BR"}
            )

            # Verificar resposta
            assert response.status_code == 200
            data = response.json()

            # Verificar presença dos campos de trace
            assert "traceId" in data
            assert "spanId" in data

            # Verificar que são null
            assert data["traceId"] is None
            assert data["spanId"] is None

    def test_trace_id_format_validation(self, test_client, mock_pipelines_and_producer):
        """Verifica formato correto dos trace IDs (W3C Trace Context)"""
        # Trace ID válido: 32 caracteres hexadecimais
        valid_trace_id = "0123456789abcdef0123456789abcdef"
        # Span ID válido: 16 caracteres hexadecimais
        valid_span_id = "0123456789abcdef"

        with patch('main.get_current_trace_id', return_value=valid_trace_id), \
             patch('main.get_current_span_id', return_value=valid_span_id):

            response = test_client.post(
                "/intentions",
                json={
                    "text": "Teste de formato de trace",
                    "language": "pt-BR"
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Trace ID deve ter exatamente 32 caracteres hexadecimais
            assert len(data["traceId"]) == 32
            assert all(c in '0123456789abcdef' for c in data["traceId"])

            # Span ID deve ter exatamente 16 caracteres hexadecimais
            assert len(data["spanId"]) == 16
            assert all(c in '0123456789abcdef' for c in data["spanId"])

    def test_response_structure_with_trace_ids(self, test_client, mock_pipelines_and_producer):
        """Verifica estrutura completa da resposta incluindo trace IDs"""
        mock_trace_id = "aaaabbbbccccddddeeeeffffgggghhhi"[:32]  # 32 chars
        mock_span_id = "1111222233334444"  # 16 chars

        with patch('main.get_current_trace_id', return_value=mock_trace_id), \
             patch('main.get_current_span_id', return_value=mock_span_id):

            response = test_client.post(
                "/intentions",
                json={
                    "text": "Verificar estrutura da resposta",
                    "language": "pt-BR"
                }
            )

            assert response.status_code == 200
            data = response.json()

            # Verificar campos obrigatórios existentes
            assert "intent_id" in data
            assert "correlation_id" in data
            assert "status" in data
            assert "confidence" in data
            assert "domain" in data

            # Verificar campos de trace
            assert "traceId" in data
            assert "spanId" in data

            # Verificar que trace IDs estão no mesmo nível que outros campos
            assert data["traceId"] == mock_trace_id
            assert data["spanId"] == mock_span_id
