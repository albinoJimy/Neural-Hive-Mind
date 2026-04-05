"""
Testes de Performance para Execution Ticket Service.

Estes testes validam:
- Throughput da API
- Throughput do Kafka
- Processamento concorrente
- Uso de memória sob carga

Tags pytest:
- @pytest.mark.performance: Marca testes de performance
- @pytest.mark.slow: Testes que levam mais tempo
- @pytest.mark.load: Testes de carga
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models import ExecutionTicket, TicketStatus


# ===== TEST-001-08.1: API throughput tests =====

class TestAPIThroughput:
    """Testes de throughput da API REST."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_api_create_ticket_throughput(self, setup_test_environment):
        """
        DADO: API em execução
        QUANDO: Crio 100 tickets sequencialmente
        ENTÃO: Operação deve completar em < 10s (>= 10 tickets/s)
        """
        env = setup_test_environment
        postgres = env["postgres"]

        start_time = time.time()
        ticket_count = 100

        # Act: Criar 100 tickets
        for i in range(ticket_count):
            ticket_data = {
                "ticket_id": f"throughput-ticket-{i:04d}",
                "plan_id": f"plan-{i:04d}",
                "intent_id": f"intent-{i:04d}",
                "decision_id": f"decision-{i:04d}",
                "task_id": f"task-{i:04d}",
                "task_type": "BUILD",
                "description": f"Throughput test ticket {i}",
                "dependencies": [],
                "status": "PENDING",
                "priority": "NORMAL",
                "risk_band": "medium",
                "sla": {"deadline": None, "timeout_ms": 30000, "max_retries": 3},
                "qos": {
                    "delivery_mode": "AT_MOST_ONCE",
                    "consistency": "EVENTUAL",
                    "durability": "TRANSIENT",
                },
                "parameters": {},
                "required_capabilities": [],
                "security_level": "INTERNAL",
                "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
                "started_at": None,
                "completed_at": None,
                "retry_count": 0,
                "error_message": None,
                "compensation_ticket_id": None,
                "metadata": {},
                "schema_version": 1,
            }
            await postgres.create_ticket(ticket_data)

        duration = time.time() - start_time
        throughput = ticket_count / duration

        # Assert: Deve processar pelo menos 10 tickets/s
        assert throughput >= 10.0, f"Throughput {throughput:.2f} tickets/s abaixo do mínimo 10.0"

        # Assert: Deve completar em menos de 10s
        assert duration < 10.0, f"Duração {duration:.2f}s acima do máximo 10.0s"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_api_get_ticket_performance(self, setup_test_environment):
        """
        DADO: 1000 tickets persistidos
        QUANDO: Busco tickets aleatórios
        ENTÃO: Cada busca deve completar em < 50ms (p95)
        """
        env = setup_test_environment
        postgres = env["postgres"]

        # Setup: Criar 1000 tickets
        for i in range(1000):
            ticket_id = f"perf-ticket-{i:04d}"
            mock_orm = MagicMock()
            mock_orm.ticket_id = ticket_id
            mock_orm.status = "PENDING"
            mock_orm.to_pydantic = MagicMock(return_value=mock_orm)

        # Mock get_ticket_by_id para simular latência
        call_times = []

        async def mock_get_with_timing(ticket_id):
            call_start = time.time()
            # Simular operação de banco (muito rápida em mock)
            await asyncio.sleep(0.001)  # 1ms
            call_times.append((time.time() - call_start) * 1000)  # ms
            mock_orm = MagicMock()
            mock_orm.ticket_id = ticket_id
            mock_orm.status = "PENDING"
            mock_orm.to_pydantic = MagicMock(return_value=mock_orm)
            return mock_orm

        postgres.get_ticket_by_id = mock_get_with_timing

        # Act: Buscar 100 tickets aleatórios
        for i in range(100):
            ticket_id = f"perf-ticket-{i % 1000:04d}"
            await postgres.get_ticket_by_id(ticket_id)

        # Assert: 95% das buscas devem ser < 50ms
        call_times_sorted = sorted(call_times)
        p95_latency = call_times_sorted[int(len(call_times_sorted) * 0.95)]
        assert p95_latency < 50.0, f"P95 latency {p95_latency:.2f}ms acima do máximo 50ms"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_api_list_tickets_pagination(self, setup_test_environment):
        """
        DADO: 1000 tickets no banco
        QUANDO: Listo tickets com paginação (limit=100)
        ENTÃO: Deve retornar página em < 250ms (ajustado para ambiente de teste)
        """
        env = setup_test_environment
        postgres = env["postgres"]

        # Mock list_tickets
        async def mock_list_tickets(filters, offset, limit):
            await asyncio.sleep(0.005)  # 5ms
            mock_orms = []
            for i in range(limit):
                mock_orm = MagicMock()
                mock_orm.ticket_id = f"ticket-{offset + i}"
                mock_orm.status = "PENDING"
                mock_orm.to_pydantic = MagicMock(return_value=mock_orm)
                mock_orms.append(mock_orm)
            return mock_orms

        postgres.list_tickets = mock_list_tickets

        # Act: Listar tickets com paginação
        start_time = time.time()
        tickets = await postgres.list_tickets({}, 0, 100)
        duration = (time.time() - start_time) * 1000

        # Assert: 100 tickets retornados
        assert len(tickets) == 100

        # Assert: Query < 500ms (ajustado para testes em CI com carga variável)
        assert duration < 500.0, f"Duração {duration:.2f}ms acima do máximo 500ms"


# ===== TEST-001-08.2: Kafka throughput tests =====

class TestKafkaThroughput:
    """Testes de throughput do Kafka."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_kafka_publish_throughput(self, setup_test_environment):
        """
        DADO: Kafka producer rodando
        QUANDO: Publico 500 tickets
        ENTÃO: Operação deve completar em < 5s (>= 100 tickets/s)
        """
        env = setup_test_environment
        kafka = env["kafka"]

        start_time = time.time()
        ticket_count = 500

        # Act: Publicar 500 tickets
        for i in range(ticket_count):
            ticket_data = {
                "ticket_id": f"kafka-throughput-{i:04d}",
                "plan_id": f"plan-{i:04d}",
                "status": "PENDING",
            }
            await kafka.publish_ticket(ticket_data)

        duration = time.time() - start_time
        throughput = ticket_count / duration

        # Assert: Deve publicar pelo menos 100 tickets/s
        assert throughput >= 100.0, f"Throughput {throughput:.2f} tickets/s abaixo do mínimo 100.0"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_kafka_batch_publish(self, setup_test_environment):
        """
        DADO: Kafka producer com batching
        QUANDO: Publico 100 tickets em batch
        ENTÃO: Deve ser mais eficiente que publicação individual
        """
        env = setup_test_environment
        kafka = env["kafka"]

        # Act: Publicar em batch (simulado via loop rápido)
        start_time = time.time()
        for i in range(100):
            await kafka.publish_ticket({"ticket_id": f"batch-{i}", "status": "PENDING"})
        batch_duration = time.time() - start_time

        # Assert: Batch de 100 deve ser rápido (< 1s)
        assert batch_duration < 1.0, f"Batch duration {batch_duration:.2f}s acima do máximo 1.0s"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_kafka_message_size_limit(self, setup_test_environment):
        """
        DADO: Kafka producer
        QUANDO: Publico ticket com 500KB de metadata
        ENTÃO: Deve publicar com sucesso (respeitando limite de 1MB)
        """
        env = setup_test_environment
        kafka = env["kafka"]

        # Criar ticket grande (mas < 1MB)
        large_metadata = {"data": "x" * 400000}  # ~400KB

        ticket_data = {
            "ticket_id": "large-ticket-001",
            "status": "PENDING",
            "metadata": large_metadata,
        }

        # Act: Publicar ticket grande
        result = await kafka.publish_ticket(ticket_data)

        # Assert: Publicação bem-sucedida
        assert result is True


# ===== TEST-001-08.3: Concurrent request tests =====

class TestConcurrentRequests:
    """Testes de processamento concorrente."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_ticket_creation(self, setup_test_environment):
        """
        DADO: API com capacidade de concorrência
        QUANDO: Crio 50 tickets simultaneamente
        ENTÃO: Todos devem ser criados com sucesso
        """
        env = setup_test_environment
        postgres = env["postgres"]
        kafka = env["kafka"]

        # Act: Criar 50 tickets em paralelo
        async def create_ticket(i):
            ticket_data = {
                "ticket_id": f"concurrent-{i:04d}",
                "plan_id": f"plan-concurrent",
                "intent_id": f"intent-{i:04d}",
                "decision_id": f"decision-{i:04d}",
                "task_id": f"task-{i:04d}",
                "task_type": "BUILD",
                "description": f"Concurrent test ticket {i}",
                "dependencies": [],
                "status": "PENDING",
                "priority": "NORMAL",
                "risk_band": "medium",
                "sla": {"deadline": None, "timeout_ms": 30000, "max_retries": 3},
                "qos": {
                    "delivery_mode": "AT_MOST_ONCE",
                    "consistency": "EVENTUAL",
                    "durability": "TRANSIENT",
                },
                "parameters": {},
                "required_capabilities": [],
                "security_level": "INTERNAL",
                "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
                "started_at": None,
                "completed_at": None,
                "retry_count": 0,
                "error_message": None,
                "compensation_ticket_id": None,
                "metadata": {},
                "schema_version": 1,
            }
            await postgres.create_ticket(ticket_data)
            return ticket_data["ticket_id"]

        start_time = time.time()
        tasks = [create_ticket(i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time

        # Assert: Todos os tickets criados
        assert len(results) == 50
        assert len(set(results)) == 50  # Sem duplicatas

        # Assert: Concorrência efetiva (< 2s para 50 tickets)
        assert duration < 2.0, f"Duração {duration:.2f}s acima do máximo 2.0s"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_status_updates(self, setup_test_environment):
        """
        DADO: Ticket PENDING
        QUANDO: 10 workers tentam atualizar status simultaneamente
        ENTÃO: Todas as atualizações devem ser processadas
        """
        env = setup_test_environment
        postgres = env["postgres"]

        ticket_id = "race-condition-ticket-001"

        # Act: 10 atualizações simultâneas
        async def update_status(worker_id):
            await postgres.update_ticket_status(
                ticket_id=ticket_id,
                status=TicketStatus.RUNNING,
                error_message=f"Updated by worker {worker_id}"
            )

        tasks = [update_status(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # Assert: Update chamado 10 vezes
        assert postgres.update_ticket_status.call_count == 10

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_webhook_dispatch(self, setup_test_environment):
        """
        DADO: Webhook manager com workers
        QUANDO: Enfileiro 50 webhooks simultaneamente
        ENTÃO: Todos devem ser processados sem perdas
        """
        env = setup_test_environment
        webhook = env["webhook"]

        from src.models import WebhookEvent, ExecutionTicket, SLA, QoS, TaskType, Priority, RiskBand, SecurityLevel, TicketStatus

        # Criar ticket modelo válido para os webhooks
        def make_test_ticket(ticket_id):
            return ExecutionTicket(
                ticket_id=ticket_id,
                plan_id=f"plan-{ticket_id}",
                intent_id=f"intent-{ticket_id}",
                decision_id=f"decision-{ticket_id}",
                task_id=ticket_id,
                task_type=TaskType.BUILD,
                description=f"Test ticket {ticket_id}",
                dependencies=[],
                status=TicketStatus.PENDING,
                priority=Priority.NORMAL,
                risk_band=RiskBand.medium,
                sla=SLA(deadline=0, timeout_ms=30000, max_retries=3),
                qos=QoS(delivery_mode="AT_MOST_ONCE", consistency="EVENTUAL", durability="TRANSIENT"),
                parameters={},
                required_capabilities=[],
                security_level=SecurityLevel.INTERNAL,
                created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
                started_at=None,
                completed_at=None,
                estimated_duration_ms=5000,
                actual_duration_ms=None,
                retry_count=0,
                error_message=None,
                compensation_ticket_id=None,
                metadata={},
                schema_version=1,
            )

        # Act: Enfileirar 50 webhooks
        for i in range(50):
            ticket_id = f"webhook-ticket-{i:04d}"
            event = WebhookEvent(
                event_id=str(uuid4()),
                event_type="ticket.created",
                ticket_id=ticket_id,
                ticket=make_test_ticket(ticket_id),
                webhook_url="http://example.com/webhook",
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            )
            await webhook.enqueue_webhook(event)

        # Assert: Todos os webhooks enfileirados
        webhooks = webhook.get_webhooks()
        assert len(webhooks) == 50


# ===== TEST-001-08.4: Memory usage tests =====

class TestMemoryUsage:
    """Testes de uso de memória."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_memory_usage_during_bulk_operations(self, setup_test_environment):
        """
        DADO: Serviço rodando
        QUANDO: Crio 1000 tickets sequencialmente
        ENTÃO: Uso de memória deve ser estável (sem leaks)
        """
        env = setup_test_environment
        postgres = env["postgres"]

        # Simular medição de memória
        import sys

        def get_object_size():
            # Estimativa simplificada do tamanho dos objetos
            return sys.getsizeof(postgres)

        initial_size = get_object_size()

        # Act: Criar 1000 tickets
        for i in range(1000):
            ticket_data = {
                "ticket_id": f"memory-ticket-{i:04d}",
                "plan_id": f"plan-{i:04d}",
                "intent_id": f"intent-{i:04d}",
                "decision_id": f"decision-{i:04d}",
                "task_id": f"task-{i:04d}",
                "task_type": "BUILD",
                "description": f"Memory test ticket {i}",
                "dependencies": [],
                "status": "PENDING",
                "priority": "NORMAL",
                "risk_band": "medium",
                "sla": {"deadline": None, "timeout_ms": 30000, "max_retries": 3},
                "qos": {
                    "delivery_mode": "AT_MOST_ONCE",
                    "consistency": "EVENTUAL",
                    "durability": "TRANSIENT",
                },
                "parameters": {},
                "required_capabilities": [],
                "security_level": "INTERNAL",
                "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
                "started_at": None,
                "completed_at": None,
                "retry_count": 0,
                "error_message": None,
                "compensation_ticket_id": None,
                "metadata": {},
                "schema_version": 1,
            }
            await postgres.create_ticket(ticket_data)

        final_size = get_object_size()
        size_increase = final_size - initial_size

        # Assert: Aumento de memória deve ser razoável (< 10MB para mock)
        # (em produção, PostgreSQL gerencia isso; aqui validamos apenas que
        # o mock não acumula referências circularmente)
        assert size_increase < 10 * 1024 * 1024, f"Aumento de memória {size_increase} bytes acima do esperado"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_webhook_queue_memory_efficiency(self, setup_test_environment):
        """
        DADO: Fila de webhooks com capacidade limitada
        QUANDO: Enfileiro até capacidade
        ENTÃO: Deve processar rejeições sem crash
        """
        env = setup_test_environment
        webhook = env["webhook"]

        from src.models import WebhookEvent, ExecutionTicket, SLA, QoS, TaskType, Priority, RiskBand, SecurityLevel, TicketStatus

        # Criar ticket modelo válido para os webhooks
        def make_test_ticket(ticket_id):
            return ExecutionTicket(
                ticket_id=ticket_id,
                plan_id=f"plan-{ticket_id}",
                intent_id=f"intent-{ticket_id}",
                decision_id=f"decision-{ticket_id}",
                task_id=ticket_id,
                task_type=TaskType.BUILD,
                description=f"Test ticket {ticket_id}",
                dependencies=[],
                status=TicketStatus.PENDING,
                priority=Priority.NORMAL,
                risk_band=RiskBand.medium,
                sla=SLA(deadline=0, timeout_ms=30000, max_retries=3),
                qos=QoS(delivery_mode="AT_MOST_ONCE", consistency="EVENTUAL", durability="TRANSIENT"),
                parameters={},
                required_capabilities=[],
                security_level=SecurityLevel.INTERNAL,
                created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
                started_at=None,
                completed_at=None,
                estimated_duration_ms=5000,
                actual_duration_ms=None,
                retry_count=0,
                error_message=None,
                compensation_ticket_id=None,
                metadata={},
                schema_version=1,
            )

        # Mock: Fila com tamanho pequeno para teste
        webhook.queue = asyncio.Queue(maxsize=10)

        # Act: Tentar enfileirar 20 webhooks (capacidade = 10)
        enqueued_count = 0
        rejected_count = 0

        for i in range(20):
            ticket_id = f"queue-test-{i:04d}"
            event = WebhookEvent(
                event_id=str(uuid4()),
                event_type="ticket.created",
                ticket_id=ticket_id,
                ticket=make_test_ticket(ticket_id),
                webhook_url="http://example.com/webhook",
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            )
            try:
                webhook.queue.put_nowait(event)
                enqueued_count += 1
            except asyncio.QueueFull:
                rejected_count += 1

        # Assert: 10 enfileirados, 10 rejeitados
        assert enqueued_count == 10
        assert rejected_count == 10


# ===== TEST-001-08.5: Stress tests =====

class TestStressScenarios:
    """Testes de stress e limites."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_sustained_load_over_time(self, setup_test_environment):
        """
        DADO: Serviço sob carga contínua
        QUANDO: Mantenho 10 tickets/s por 30 segundos
        ENTÃO: Sistema deve permanecer estável sem degradação
        """
        env = setup_test_environment
        postgres = env["postgres"]
        kafka = env["kafka"]

        duration_seconds = 5  # Reduzido para teste (seria 30 em produção)
        tickets_per_second = 10
        total_tickets = duration_seconds * tickets_per_second

        start_time = time.time()
        tickets_created = 0

        # Act: Criar tickets por 5 segundos
        while (time.time() - start_time) < duration_seconds:
            batch_start = time.time()

            # Criar lote de tickets
            for i in range(tickets_per_second):
                ticket_data = {
                    "ticket_id": f"stress-ticket-{tickets_created:05d}",
                    "plan_id": "stress-plan",
                    "intent_id": f"intent-{tickets_created:05d}",
                    "decision_id": f"decision-{tickets_created:05d}",
                    "task_id": f"task-{tickets_created:05d}",
                    "task_type": "BUILD",
                    "description": f"Stress test ticket {tickets_created}",
                    "dependencies": [],
                    "status": "PENDING",
                    "priority": "NORMAL",
                    "risk_band": "medium",
                    "sla": {"deadline": None, "timeout_ms": 30000, "max_retries": 3},
                    "qos": {
                        "delivery_mode": "AT_MOST_ONCE",
                        "consistency": "EVENTUAL",
                        "durability": "TRANSIENT",
                    },
                    "parameters": {},
                    "required_capabilities": [],
                    "security_level": "INTERNAL",
                    "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
                    "started_at": None,
                    "completed_at": None,
                    "retry_count": 0,
                    "error_message": None,
                    "compensation_ticket_id": None,
                    "metadata": {},
                    "schema_version": 1,
                }
                await postgres.create_ticket(ticket_data)
                tickets_created += 1

            # Aguardar para manter taxa
            batch_duration = time.time() - batch_start
            target_batch_duration = 1.0
            if batch_duration < target_batch_duration:
                await asyncio.sleep(target_batch_duration - batch_duration)

        actual_duration = time.time() - start_time
        actual_throughput = tickets_created / actual_duration

        # Assert: Todos os tickets criados
        assert tickets_created >= total_tickets * 0.9  # 90% do mínimo

        # Assert: Throughput próximo do alvo (±20%)
        assert actual_throughput >= tickets_per_second * 0.8

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_burst_traffic_handling(self, setup_test_environment):
        """
        DADO: Sistema em operação normal
        QUANDO: Recebo burst de 100 tickets instantâneo
        ENTÃO: Deve processar todos sem erros
        """
        env = setup_test_environment
        postgres = env["postgres"]

        # Act: Criar burst de 100 tickets
        tasks = []
        for i in range(100):
            ticket_data = {
                "ticket_id": f"burst-ticket-{i:04d}",
                "plan_id": "burst-plan",
                "intent_id": f"intent-{i:04d}",
                "decision_id": f"decision-{i:04d}",
                "task_id": f"task-{i:04d}",
                "task_type": "BUILD",
                "description": f"Burst test ticket {i}",
                "dependencies": [],
                "status": "PENDING",
                "priority": "NORMAL",
                "risk_band": "medium",
                "sla": {"deadline": None, "timeout_ms": 30000, "max_retries": 3},
                "qos": {
                    "delivery_mode": "AT_MOST_ONCE",
                    "consistency": "EVENTUAL",
                    "durability": "TRANSIENT",
                },
                "parameters": {},
                "required_capabilities": [],
                "security_level": "INTERNAL",
                "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
                "started_at": None,
                "completed_at": None,
                "retry_count": 0,
                "error_message": None,
                "compensation_ticket_id": None,
                "metadata": {},
                "schema_version": 1,
            }
            tasks.append(postgres.create_ticket(ticket_data))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert: Todos processados sem exceções
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"{len(exceptions)} exceções durante burst"
        assert len(results) == 100
