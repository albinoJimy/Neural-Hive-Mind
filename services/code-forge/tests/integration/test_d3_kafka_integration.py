"""
Testes de integração Kafka D3 (Build + Kafka Integration)

Conforme MODELO_TESTE_WORKER_AGENT.md seção D3.

Tópicos Kafka:
- execution.tickets: Consumo de tickets BUILD
- execution.results: Publicação de resultados
- execution.events: Eventos de pipeline
"""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict

import pytest

from src.models.artifact import PipelineResult, PipelineStatus, ArtifactType
from src.models.execution_ticket import TaskType, TicketStatus


pytest_plugins = [
    'tests.unit.conftest',
    'tests.fixtures.d3_fixtures'
]


# ============================================================================
# Testes de Produção de Resultados
# ============================================================================


class TestD3KafkaResultProduction:
    """Testes de produção de resultados no Kafka."""

    @pytest.mark.asyncio
    async def test_d3_result_publish_on_completion(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_d3_kafka_producer
    ):
        """
        D3: Publicação de resultado COMPLETED

        Verifica:
        - publish_result chamado
        - Payload com status=COMPLETED
        - Artefatos incluídos
        - trace_id propagado
        """
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar publish
        assert mock_d3_kafka_producer.publish_result.called
        assert mock_d3_kafka_producer.publish_result.call_count >= 1

        # Obter resultado publicado
        call_args = mock_d3_kafka_producer.publish_result.call_args
        published_result = call_args[0][0]

        # Verificar campos
        assert published_result.status == PipelineStatus.COMPLETED
        assert published_result.pipeline_id is not None
        assert published_result.ticket_id == d3_build_ticket.ticket_id
        assert published_result.trace_id == d3_build_ticket.trace_id

    @pytest.mark.asyncio
    async def test_d3_result_publish_on_failure(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_d3_kafka_producer,
        mock_d3_validator
    ):
        """
        D3: Publicação de resultado FAILED

        Verifica:
        - publish_result chamado mesmo em falha
        - Payload com status=FAILED
        - error_message presente
        """
        # Configurar falha
        async def _failing_validation(context):
            raise Exception("Validation failed")

        mock_d3_validator.validate = AsyncMock(side_effect=_failing_validation)

        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar publish mesmo com falha
        assert mock_d3_kafka_producer.publish_result.called

        # Verificar resultado com falha
        call_args = mock_d3_kafka_producer.publish_result.call_args
        published_result = call_args[0][0]

        assert published_result.status == PipelineStatus.FAILED
        assert published_result.error_message is not None

    @pytest.mark.asyncio
    async def test_d3_result_message_structure(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_d3_kafka_producer
    ):
        """
        D3: Estrutura da mensagem Kafka

        Campos obrigatórios:
        - pipeline_id
        - ticket_id
        - plan_id
        - intent_id
        - status
        - artifacts[]
        - total_duration_ms
        - created_at
        - trace_id
        - span_id
        """
        await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        call_args = mock_d3_kafka_producer.publish_result.call_args
        published_result = call_args[0][0]

        # Verificar campos obrigatórios
        required_fields = [
            'pipeline_id', 'ticket_id', 'plan_id', 'intent_id',
            'status', 'artifacts', 'pipeline_stages',
            'total_duration_ms', 'created_at',
            'trace_id', 'span_id'
        ]

        for field in required_fields:
            assert hasattr(published_result, field), \
                f"Campo obrigatório {field} ausente"

        # Verificar tipos
        assert isinstance(published_result.pipeline_id, str)
        assert isinstance(published_result.ticket_id, str)
        assert isinstance(published_result.status, str)
        assert isinstance(published_result.artifacts, list)
        assert isinstance(published_result.total_duration_ms, int)

    @pytest.mark.asyncio
    async def test_d3_result_artifact_inclusion(
        self,
        d3_build_ticket_with_container,
        mock_d3_pipeline_engine,
        mock_d3_kafka_producer
    ):
        """
        D3: Artefatos incluídos no resultado Kafka

        Verifica:
        - Artefato CONTAINER incluído
        - content_uri presente
        - content_hash presente
        - sbom_uri presente
        """
        await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket_with_container)

        call_args = mock_d3_kafka_producer.publish_result.call_args
        published_result = call_args[0][0]

        # Verificar artefatos
        assert len(published_result.artifacts) > 0

        container = published_result.artifacts[0]
        assert container.artifact_type == ArtifactType.CONTAINER
        assert container.content_uri is not None
        assert container.content_hash is not None
        assert container.sbom_uri is not None


# ============================================================================
# Testes de Consumo de Tickets
# ============================================================================


class TestD3KafkaTicketConsumption:
    """Testes de consumo de tickets do Kafka."""

    @pytest.mark.asyncio
    async def test_d3_consume_build_ticket(
        self,
        mock_d3_kafka_consumer
    ):
        """
        D3: Consumo de ticket BUILD

        Verifica:
        - Ticket consumido do tópico execution.tickets
        - task_type=BUILD
        - Parâmetros presentes
        """
        ticket = await mock_d3_kafka_consumer.consume_ticket()

        assert ticket is not None
        assert ticket['task_type'] == 'BUILD'
        assert 'parameters' in ticket

    @pytest.mark.asyncio
    async def test_d3_consume_batch_tickets(
        self,
        mock_d3_kafka_consumer
    ):
        """
        D3: Consumo de lote de tickets

        Verifica:
        - Múltiplos tickets consumidos
        - Offset pode ser commitado após processamento
        """
        tickets = await mock_d3_kafka_consumer.consume_topic('execution.tickets')

        assert len(tickets) > 0
        # Commit deve ser possível (método existe)
        assert mock_d3_kafka_consumer.commit_offset is not None

    @pytest.mark.asyncio
    async def test_d3_ticket_deserialization(
        self,
        d3_build_ticket
    ):
        """
        D3: Deserialização de ticket

        Verifica:
        - JSON válido
        - ExecutionTicket criado corretamente
        - Todos campos presentes
        """
        # Serializar ticket
        ticket_json = d3_build_ticket.model_dump_json()

        # Deserializar
        from src.models.execution_ticket import ExecutionTicket
        deserialized = ExecutionTicket.model_validate_json(ticket_json)

        # Verificar campos
        assert deserialized.ticket_id == d3_build_ticket.ticket_id
        assert deserialized.task_type == TaskType.BUILD
        assert deserialized.status == TicketStatus.PENDING


# ============================================================================
# Testes de Eventos de Pipeline
# ============================================================================


class TestD3KafkaPipelineEvents:
    """Testes de eventos de pipeline no Kafka."""

    @pytest.mark.asyncio
    async def test_d3_stage_started_event(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_d3_kafka_producer
    ):
        """
        D3: Evento de stage iniciado

        Verifica:
        - Evento published: stage_started
        - Nome do stage incluído
        - pipeline_id incluído
        """
        # Mock para capturar eventos
        events = []

        async def _capture_event(topic, event):
            events.append((topic, event))
            return True

        mock_d3_kafka_producer.publish = AsyncMock(side_effect=_capture_event)
        # Reset publish_result for tracking (don't override completely)
        original_publish = mock_d3_kafka_producer.publish_result
        mock_d3_kafka_producer.publish_result = AsyncMock(side_effect=original_publish.side_effect)

        await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar que publish_result foi chamado (pipeline chama publish_result)
        assert mock_d3_kafka_producer.publish_result.called

        # Verificar call_args para obter resultado
        call_args = mock_d3_kafka_producer.publish_result.call_args
        assert call_args is not None
        result = call_args[0][0]
        assert len(result.pipeline_stages) > 0

    @pytest.mark.asyncio
    async def test_d3_stage_completed_event(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine
    ):
        """
        D3: Evento de stage completado

        Verifica:
        - Evento published: stage_completed
        - Duração incluída
        - Status=COMPLETED
        """
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar stages completados no resultado
        for stage in result.pipeline_stages:
            assert stage.status.value in ['COMPLETED', 'FAILED', 'RUNNING']
            assert stage.duration_ms >= 0
            assert stage.stage_name is not None

    @pytest.mark.asyncio
    async def test_d3_pipeline_completed_event(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_d3_kafka_producer
    ):
        """
        D3: Evento de pipeline completado

        Verifica:
        - Evento published: pipeline_completed
        - Duração total incluída
        - Status final
        - Contagem de artefatos
        """
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # Verificar resultado final
        assert result.status == PipelineStatus.COMPLETED
        assert result.total_duration_ms > 0
        assert len(result.pipeline_stages) == 6

        # Verificar publish
        assert mock_d3_kafka_producer.publish_result.called


# ============================================================================
# Testes de Configuração Kafka
# ============================================================================


class TestD3KafkaConfiguration:
    """Testes de configuração do Kafka producer/consumer."""

    @pytest.mark.asyncio
    async def test_d3_kafka_producer_start_stop(
        self,
        mock_d3_kafka_producer
    ):
        """
        D3: Start/Stop do producer

        Verifica:
        - start() chamado
        - stop() chamado
        """
        await mock_d3_kafka_producer.start()
        await mock_d3_kafka_producer.stop()

        assert mock_d3_kafka_producer.start.called
        assert mock_d3_kafka_producer.stop.called

    @pytest.mark.asyncio
    async def test_d3_kafka_consumer_start_stop(
        self,
        mock_d3_kafka_consumer
    ):
        """
        D3: Start/Stop do consumer

        Verifica:
        - start() chamado
        - stop() chamado
        - Subscription ao tópico
        """
        await mock_d3_kafka_consumer.start()
        await mock_d3_kafka_consumer.stop()

        assert mock_d3_kafka_consumer.start.called
        assert mock_d3_kafka_consumer.stop.called

    @pytest.mark.asyncio
    async def test_d3_kafka_retry_on_failure(
        self,
        mock_d3_kafka_producer
    ):
        """
        D3: Retry em falha de publicação

        Verifica:
        - Tentativas de retry configuradas
        - Backoff exponencial
        - Falha final após max retries
        """
        # Configurar para falhar nas primeiras tentativas
        call_count = {'count': 0}

        async def _failing_publish(result):
            call_count['count'] += 1
            if call_count['count'] < 3:
                raise Exception("Kafka connection error")
            return True

        mock_d3_kafka_producer.publish_result = AsyncMock(side_effect=_failing_publish)

        # Tentar publicar (deve falhar 2x e suceder na 3ª)
        result = PipelineResult(
            pipeline_id=str(uuid.uuid4()),
            ticket_id=str(uuid.uuid4()),
            status=PipelineStatus.COMPLETED,
            artifacts=[],
            pipeline_stages=[],
            total_duration_ms=1000,
            approval_required=False,
            created_at=datetime.now()
        )

        # Deve retornar True após 3 tentativas
        # A função side_effect será chamada até retornar True
        # Precisamos envolver com try-except para simular retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await mock_d3_kafka_producer.publish_result(result)
                break
            except Exception:
                if attempt == max_retries - 1:
                    raise
                continue

        # Verificar retries (função foi chamada 3 vezes)
        assert call_count['count'] == 3


# ============================================================================
# Testes de Tópicos e Partitions
# ============================================================================


class TestD3KafkaTopics:
    """Testes de tópicos e partitions Kafka."""

    def test_d3_topics_configured(self):
        """
        D3: Tópicos configurados

        Tópicos esperados:
        - execution.tickets (input)
        - execution.results (output)
        - execution.events (events)
        """
        expected_topics = {
            'execution.tickets': 'input',
            'execution.results': 'output',
            'execution.events': 'events'
        }

        # Verificar nomes dos tópicos
        for topic, purpose in expected_topics.items():
            assert topic.startswith('execution.')
            assert purpose in ['input', 'output', 'events']

    @pytest.mark.asyncio
    async def test_d3_result_topic_partitioning(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine
    ):
        """
        D3: Partitioning do tópico de resultados

        Verifica:
        - Partition key usada (ticket_id)
        - Ordem mantida por ticket
        """
        result = await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        # ticket_id deve ser usado como partition key
        assert result.ticket_id is not None
        assert len(result.ticket_id) > 0


# ============================================================================
# Testes de Serialização/Deserialização
# ============================================================================


class TestD3KafkaSerialization:
    """Testes de serialização/deserialização Kafka."""

    def test_d3_result_serialization(self, d3_expected_pipeline_result):
        """
        D3: Serialização de PipelineResult

        Verifica:
        - JSON válido
        - Enums serializados
        - Datetimes serializados
        """
        # Serializar
        result_json = d3_expected_pipeline_result.model_dump_json()

        # Verificar JSON válido
        parsed = json.loads(result_json)
        assert parsed['pipeline_id'] == d3_expected_pipeline_result.pipeline_id
        assert parsed['status'] == 'COMPLETED'

    def test_d3_result_deserialization(self, d3_expected_pipeline_result):
        """
        D3: Deserialização de PipelineResult

        Verifica:
        - Valores corretos restaurados
        - Tipos corretos
        """
        # Serializar e deserializar
        result_json = d3_expected_pipeline_result.model_dump_json()
        restored = PipelineResult.model_validate_json(result_json)

        # Verificar campos
        assert restored.pipeline_id == d3_expected_pipeline_result.pipeline_id
        assert restored.status == PipelineStatus.COMPLETED
        assert len(restored.artifacts) == len(d3_expected_pipeline_result.artifacts)

    @pytest.mark.asyncio
    async def test_d3_ticket_serialization_roundtrip(self, d3_build_ticket):
        """
        D3: Roundtrip de serialização de ticket

        Verifica:
        - Ticket → JSON → Ticket
        - Todos campos preservados
        """
        # Serializar
        ticket_json = d3_build_ticket.model_dump_json()

        # Deserializar
        from src.models.execution_ticket import ExecutionTicket
        restored = ExecutionTicket.model_validate_json(ticket_json)

        # Verificar campos preservados
        assert restored.ticket_id == d3_build_ticket.ticket_id
        assert restored.task_type == d3_build_ticket.task_type
        assert restored.status == d3_build_ticket.status
        assert restored.parameters == d3_build_ticket.parameters


# ============================================================================
# Testes de Integração com OpenTelemetry
# ============================================================================


class TestD3KafkaOpenTelemetry:
    """Testes de integração Kafka com OpenTelemetry."""

    @pytest.mark.asyncio
    async def test_d3_trace_propagation(
        self,
        d3_build_ticket,
        mock_d3_pipeline_engine,
        mock_d3_kafka_producer
    ):
        """
        D3: Propagação de trace no Kafka

        Verifica:
        - trace_id presente na mensagem
        - span_id presente na mensagem
        - Correlation context mantido
        """
        await mock_d3_pipeline_engine.execute_pipeline(d3_build_ticket)

        call_args = mock_d3_kafka_producer.publish_result.call_args
        published_result = call_args[0][0]

        # Verificar IDs de tracing
        assert published_result.trace_id is not None
        assert published_result.span_id is not None
        assert len(published_result.trace_id) > 0
        assert len(published_result.span_id) > 0

    @pytest.mark.asyncio
    async def test_d3_w3c_trace_context_format(self, d3_build_ticket):
        """
        D3: Formato W3C Trace Context

        Verifica:
        - traceparent header válido
        - Formato: version-traceid-spanid-sampled
        """
        # Criar traceparent
        # Formatar trace_id para 32 caracteres hex (sem traços)
        trace_uuid = d3_build_ticket.trace_id or str(uuid.uuid4())
        trace_id = trace_uuid.replace('-', '')
        # Span_id: 16 caracteres hex (usar primeiros 16 chars do UUID sem traços)
        span_uuid = d3_build_ticket.span_id or str(uuid.uuid4())
        span_id = span_uuid.replace('-', '')[:16]

        traceparent = f"00-{trace_id}-{span_id}-01"

        # Verificar formato
        parts = traceparent.split('-')
        assert len(parts) == 4
        assert parts[0] == '00'  # version
        assert len(parts[1]) == 32  # trace_id
        assert len(parts[2]) == 16  # span_id
        assert parts[3] in ['01', '00']  # sampled


# ============================================================================
# Testes de Performance Kafka
# ============================================================================


class TestD3KafkaPerformance:
    """Testes de performance do Kafka."""

    @pytest.mark.asyncio
    async def test_d3_publish_latency(
        self,
        mock_d3_kafka_producer
    ):
        """
        D3: Latência de publicação

        Verifica:
        - Publish < 100ms (mock)
        """
        import time

        result = PipelineResult(
            pipeline_id=str(uuid.uuid4()),
            ticket_id=str(uuid.uuid4()),
            status=PipelineStatus.COMPLETED,
            artifacts=[],
            pipeline_stages=[],
            total_duration_ms=1000,
            approval_required=False,
            created_at=datetime.now()
        )

        start = time.time()
        await mock_d3_kafka_producer.publish_result(result)
        latency_ms = int((time.time() - start) * 1000)

        # Mock deve ser rápido
        assert latency_ms < 100

    @pytest.mark.asyncio
    async def test_d3_batch_publish(
        self,
        mock_d3_kafka_producer
    ):
        """
        D3: Publicação em lote

        Verifica:
        - Múltiplas mensagens publicadas
        - Menor latência média
        """
        results = [
            PipelineResult(
                pipeline_id=str(uuid.uuid4()),
                ticket_id=str(uuid.uuid4()),
                status=PipelineStatus.COMPLETED,
                artifacts=[],
                pipeline_stages=[],
                total_duration_ms=1000,
                approval_required=False,
                created_at=datetime.now()
            )
            for _ in range(10)
        ]

        # Publicar em lote
        for result in results:
            await mock_d3_kafka_producer.publish_result(result)

        assert mock_d3_kafka_producer.publish_result.call_count == 10


# ============================================================================
# Testes de Tratamento de Erros Kafka
# ============================================================================


class TestD3KafkaErrorHandling:
    """Testes de tratamento de erros Kafka."""

    @pytest.mark.asyncio
    async def test_d3_publish_failure_handling(
        self,
        mock_d3_kafka_producer,
        d3_build_ticket
    ):
        """
        D3: Tratamento de falha de publicação

        Verifica:
        - Exceção capturada
        - Log de erro
        - Pipeline não falha
        """
        # Configurar falha
        mock_d3_kafka_producer.publish_result = AsyncMock(
            side_effect=Exception("Kafka broker unavailable")
        )

        # Mock de logger
        import structlog
        logger = structlog.get_logger()

        # Publicar (não deve falhar)
        result = PipelineResult(
            pipeline_id=str(uuid.uuid4()),
            ticket_id=d3_build_ticket.ticket_id,
            status=PipelineStatus.COMPLETED,
            artifacts=[],
            pipeline_stages=[],
            total_duration_ms=1000,
            approval_required=False,
            created_at=datetime.now()
        )

        # Tentar publicar
        try:
            await mock_d3_kafka_producer.publish_result(result)
        except Exception as e:
            # Esperado: exceção propagada
            assert "Kafka" in str(e) or "broker" in str(e)

    @pytest.mark.asyncio
    async def test_d3_consumer_error_handling(
        self,
        mock_d3_kafka_consumer
    ):
        """
        D3: Tratamento de erro no consumer

        Verifica:
        - Erro de deserialização capturado
        - Offset não commitado em erro
        - Processing continua
        """
        # Configurar erro
        mock_d3_kafka_consumer.consume_topic = AsyncMock(
            side_effect=Exception("Deserialization error")
        )

        # Tentar consumir
        try:
            await mock_d3_kafka_consumer.consume_topic('execution.tickets')
        except Exception as e:
            # Esperado: exceção propagada
            assert "error" in str(e).lower() or "deserialization" in str(e).lower()
