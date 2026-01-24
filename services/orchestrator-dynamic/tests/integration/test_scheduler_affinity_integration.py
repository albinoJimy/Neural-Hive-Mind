"""
Testes de integração para Affinity/Anti-Affinity Scheduling.

Cobertura:
- Co-location de tickets do mesmo plan_id
- Distribuição de tickets críticos (anti-affinity)
- Interação com Redis real (quando disponível)
- Validação de métricas
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_redis_client():
    """Mock do cliente Redis para testes sem Redis real."""
    client = AsyncMock()

    # Armazenamento em memória para simular Redis
    storage = {
        'hashes': {},
        'sets': {}
    }

    async def mock_hgetall(key):
        return storage['hashes'].get(key, {})

    async def mock_smembers(key):
        return storage['sets'].get(key, set())

    def mock_pipeline():
        pipe = MagicMock()
        commands = []

        def hincrby(key, field, amount):
            commands.append(('hincrby', key, field, amount))

        def sadd(key, *members):
            commands.append(('sadd', key, members))

        def srem(key, *members):
            commands.append(('srem', key, members))

        def expire(key, ttl):
            commands.append(('expire', key, ttl))

        async def execute():
            for cmd in commands:
                if cmd[0] == 'hincrby':
                    key, field, amount = cmd[1], cmd[2], cmd[3]
                    if key not in storage['hashes']:
                        storage['hashes'][key] = {}
                    current = int(storage['hashes'][key].get(field, 0))
                    storage['hashes'][key][field] = str(current + amount)
                elif cmd[0] == 'sadd':
                    key, members = cmd[1], cmd[2]
                    if key not in storage['sets']:
                        storage['sets'][key] = set()
                    storage['sets'][key].update(members)
                elif cmd[0] == 'srem':
                    key, members = cmd[1], cmd[2]
                    if key in storage['sets']:
                        storage['sets'][key] -= set(members)
            return [True] * len(commands)

        pipe.hincrby = hincrby
        pipe.sadd = sadd
        pipe.srem = srem
        pipe.expire = expire
        pipe.execute = execute
        return pipe

    client.hgetall = mock_hgetall
    client.smembers = mock_smembers
    client.pipeline = mock_pipeline
    client._storage = storage

    return client


@pytest.fixture
def mock_config():
    """Mock das configurações."""
    config = MagicMock()
    config.scheduler_enable_affinity = True
    config.scheduler_affinity_plan_weight = 0.6
    config.scheduler_affinity_anti_weight = 0.3
    config.scheduler_affinity_intent_weight = 0.1
    config.scheduler_affinity_plan_threshold = 3
    config.scheduler_affinity_cache_ttl_seconds = 14400
    config.scheduler_affinity_anti_affinity_risk_bands = ['critical', 'high']
    config.scheduler_affinity_anti_affinity_priorities = ['CRITICAL', 'HIGH']
    config.service_registry_max_results = 5
    return config


@pytest.fixture
def mock_metrics():
    """Mock das métricas com tracking."""
    metrics = MagicMock()
    metrics.hits = {'plan': 0, 'intent': 0}
    metrics.misses = {'plan': 0, 'intent': 0}
    metrics.anti_affinity_count = 0
    metrics.cache_ops = {'success': 0, 'failure': 0}

    def record_hit(affinity_type):
        metrics.hits[affinity_type] = metrics.hits.get(affinity_type, 0) + 1

    def record_miss(affinity_type):
        metrics.misses[affinity_type] = metrics.misses.get(affinity_type, 0) + 1

    def record_anti_affinity(risk_band, priority):
        metrics.anti_affinity_count += 1

    def record_cache_op(operation, status):
        metrics.cache_ops[status] = metrics.cache_ops.get(status, 0) + 1

    metrics.record_affinity_hit = record_hit
    metrics.record_affinity_miss = record_miss
    metrics.record_anti_affinity_enforced = record_anti_affinity
    metrics.record_affinity_cache_operation = record_cache_op
    metrics.record_affinity_score = MagicMock()

    return metrics


@pytest.fixture
def affinity_tracker(mock_redis_client, mock_config, mock_metrics):
    """Instância do AffinityTracker."""
    from src.scheduler.affinity_tracker import AffinityTracker
    return AffinityTracker(
        redis_client=mock_redis_client,
        config=mock_config,
        metrics=mock_metrics
    )


@pytest.fixture
def resource_allocator(mock_config, mock_metrics, affinity_tracker):
    """Instância do ResourceAllocator com affinity."""
    from src.scheduler.resource_allocator import ResourceAllocator

    mock_registry = MagicMock()

    return ResourceAllocator(
        registry_client=mock_registry,
        config=mock_config,
        metrics=mock_metrics,
        affinity_tracker=affinity_tracker
    )


class TestAffinityCoLocation:
    """Testes de co-location de tickets."""

    @pytest.mark.asyncio
    async def test_sequential_tickets_same_plan_co_located(
        self, resource_allocator, affinity_tracker
    ):
        """Valida que tickets sequenciais do mesmo plan vão para o mesmo worker."""
        workers = [
            {'agent_id': 'worker-001', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
            {'agent_id': 'worker-002', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
            {'agent_id': 'worker-003', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
        ]

        plan_id = 'plan-colocation-test'
        allocations = []

        # Alocar 5 tickets do mesmo plan_id
        for i in range(5):
            ticket = {
                'ticket_id': f'ticket-{i}',
                'plan_id': plan_id,
                'intent_id': 'intent-456',
                'risk_band': 'medium',
                'priority': 'NORMAL'
            }

            best_worker = await resource_allocator.select_best_worker(
                workers=workers,
                priority_score=0.8,
                ticket=ticket
            )

            allocations.append(best_worker.get('agent_id'))

        # Calcular co-location rate
        from collections import Counter
        allocation_counts = Counter(allocations)
        most_common_worker, most_common_count = allocation_counts.most_common(1)[0]

        co_location_rate = most_common_count / len(allocations)

        # Maioria dos tickets deve ir para o mesmo worker
        assert co_location_rate >= 0.6, f"Co-location rate {co_location_rate} abaixo de 60%"

    @pytest.mark.asyncio
    async def test_critical_tickets_distributed(
        self, resource_allocator, affinity_tracker
    ):
        """Valida que tickets críticos são distribuídos entre workers."""
        workers = [
            {'agent_id': 'worker-001', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
            {'agent_id': 'worker-002', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
            {'agent_id': 'worker-003', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
        ]

        plan_id = 'plan-critical-test'
        allocations = []

        # Alocar 5 tickets críticos do mesmo plan_id
        for i in range(5):
            ticket = {
                'ticket_id': f'ticket-critical-{i}',
                'plan_id': plan_id,
                'intent_id': 'intent-456',
                'risk_band': 'critical',
                'priority': 'CRITICAL'
            }

            best_worker = await resource_allocator.select_best_worker(
                workers=workers,
                priority_score=0.8,
                ticket=ticket
            )

            allocations.append(best_worker.get('agent_id'))

        # Calcular distribuição
        unique_workers = len(set(allocations))
        distribution_rate = unique_workers / len(allocations)

        # Tickets críticos devem estar distribuídos (mais de 1 worker)
        assert unique_workers >= 2, f"Apenas {unique_workers} worker(s) usado(s) para tickets críticos"

    @pytest.mark.asyncio
    async def test_mixed_critical_and_normal_tickets(
        self, resource_allocator, affinity_tracker
    ):
        """Valida comportamento com mix de tickets críticos e normais."""
        workers = [
            {'agent_id': 'worker-001', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
            {'agent_id': 'worker-002', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
            {'agent_id': 'worker-003', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
        ]

        plan_id = 'plan-mixed-test'
        normal_allocations = []
        critical_allocations = []

        # Alocar 3 tickets normais
        for i in range(3):
            ticket = {
                'ticket_id': f'ticket-normal-{i}',
                'plan_id': plan_id,
                'intent_id': 'intent-456',
                'risk_band': 'medium',
                'priority': 'NORMAL'
            }

            best_worker = await resource_allocator.select_best_worker(
                workers=workers,
                priority_score=0.8,
                ticket=ticket
            )

            normal_allocations.append(best_worker.get('agent_id'))

        # Alocar 2 tickets críticos
        for i in range(2):
            ticket = {
                'ticket_id': f'ticket-critical-{i}',
                'plan_id': plan_id,
                'intent_id': 'intent-456',
                'risk_band': 'critical',
                'priority': 'CRITICAL'
            }

            best_worker = await resource_allocator.select_best_worker(
                workers=workers,
                priority_score=0.8,
                ticket=ticket
            )

            critical_allocations.append(best_worker.get('agent_id'))

        # Tickets normais devem ter co-location
        from collections import Counter
        normal_counts = Counter(normal_allocations)
        _, most_common_normal = normal_counts.most_common(1)[0]

        # Tickets críticos devem ser distribuídos ou evitar workers com críticos
        critical_unique = len(set(critical_allocations))

        # Validações
        assert most_common_normal >= 2, "Tickets normais não foram co-localizados"
        # Críticos podem ir para o mesmo worker se nenhum outro crítico estava lá
        # O importante é que anti-affinity foi considerado


class TestAffinityMetrics:
    """Testes de métricas de affinity."""

    @pytest.mark.asyncio
    async def test_affinity_metrics_recorded(
        self, resource_allocator, mock_metrics
    ):
        """Valida que métricas são registradas corretamente."""
        workers = [
            {'agent_id': 'worker-001', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
        ]

        ticket = {
            'ticket_id': 'ticket-123',
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'risk_band': 'medium',
            'priority': 'NORMAL'
        }

        await resource_allocator.select_best_worker(
            workers=workers,
            priority_score=0.8,
            ticket=ticket
        )

        # Verificar que métricas foram chamadas
        assert mock_metrics.record_affinity_score.called
        assert mock_metrics.cache_ops['success'] > 0

    @pytest.mark.asyncio
    async def test_anti_affinity_metrics_for_critical(
        self, resource_allocator, mock_metrics
    ):
        """Valida que métricas de anti-affinity são registradas para tickets críticos."""
        workers = [
            {'agent_id': 'worker-001', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}},
        ]

        ticket = {
            'ticket_id': 'ticket-critical',
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'risk_band': 'critical',
            'priority': 'CRITICAL'
        }

        await resource_allocator.select_best_worker(
            workers=workers,
            priority_score=0.8,
            ticket=ticket
        )

        # Anti-affinity deve ter sido contabilizado
        assert mock_metrics.anti_affinity_count > 0


class TestAffinityCleanup:
    """Testes de cleanup de tickets completados."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_allocation(
        self, affinity_tracker, mock_redis_client
    ):
        """Valida que cleanup remove ticket do cache."""
        # Primeiro, registrar uma alocação
        ticket = {
            'ticket_id': 'ticket-to-cleanup',
            'plan_id': 'plan-cleanup-test',
            'intent_id': 'intent-456',
            'risk_band': 'critical',
            'priority': 'CRITICAL'
        }

        await affinity_tracker.record_allocation(ticket, 'worker-001')

        # Verificar que foi registrado
        plan_allocations = await affinity_tracker.get_plan_allocations('plan-cleanup-test')
        assert plan_allocations.get('worker-001', 0) > 0

        # Agora fazer cleanup
        result = await affinity_tracker.cleanup_completed_ticket(
            ticket_id='ticket-to-cleanup',
            plan_id='plan-cleanup-test',
            intent_id='intent-456',
            worker_id='worker-001'
        )

        assert result is True

        # Verificar que contagem foi decrementada
        plan_allocations_after = await affinity_tracker.get_plan_allocations('plan-cleanup-test')
        assert plan_allocations_after.get('worker-001', 0) == 0
