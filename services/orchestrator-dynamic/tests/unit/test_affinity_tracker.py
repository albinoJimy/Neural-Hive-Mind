"""
Testes unitários para AffinityTracker.

Cobertura:
- Operações de get/set no cache Redis
- Cálculo de affinity scores
- Tratamento de erros (fail-open)
- Integração com métricas
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAffinityTracker:
    """Testes para AffinityTracker."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock do cliente Redis."""
        client = AsyncMock()
        client.hgetall = AsyncMock(return_value={})
        client.smembers = AsyncMock(return_value=set())
        client.pipeline = MagicMock()

        # Mock do pipeline
        pipe = AsyncMock()
        pipe.hincrby = MagicMock()
        pipe.sadd = MagicMock()
        pipe.srem = MagicMock()
        pipe.expire = MagicMock()
        pipe.execute = AsyncMock(return_value=[])
        client.pipeline.return_value = pipe

        return client

    @pytest.fixture
    def mock_config(self):
        """Mock das configurações."""
        config = MagicMock()
        config.scheduler_affinity_cache_ttl_seconds = 14400
        config.scheduler_affinity_anti_affinity_risk_bands = ['critical', 'high']
        config.scheduler_affinity_anti_affinity_priorities = ['CRITICAL', 'HIGH']
        return config

    @pytest.fixture
    def mock_metrics(self):
        """Mock das métricas."""
        metrics = MagicMock()
        metrics.record_affinity_cache_operation = MagicMock()
        return metrics

    @pytest.fixture
    def affinity_tracker(self, mock_redis_client, mock_config, mock_metrics):
        """Instância do AffinityTracker com mocks."""
        from src.scheduler.affinity_tracker import AffinityTracker
        return AffinityTracker(
            redis_client=mock_redis_client,
            config=mock_config,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_get_plan_allocations_empty(self, affinity_tracker, mock_redis_client):
        """Retorna dict vazio para plan_id novo."""
        mock_redis_client.hgetall.return_value = {}

        result = await affinity_tracker.get_plan_allocations('plan-123')

        assert result == {}
        mock_redis_client.hgetall.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_plan_allocations_with_data(self, affinity_tracker, mock_redis_client):
        """Retorna contagens corretas de alocações."""
        mock_redis_client.hgetall.return_value = {
            'worker-001': '3',
            'worker-002': '1'
        }

        result = await affinity_tracker.get_plan_allocations('plan-123')

        assert result == {'worker-001': 3, 'worker-002': 1}

    @pytest.mark.asyncio
    async def test_get_plan_allocations_none_plan_id(self, affinity_tracker):
        """Retorna dict vazio quando plan_id é None."""
        result = await affinity_tracker.get_plan_allocations(None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_intent_allocations_with_data(self, affinity_tracker, mock_redis_client):
        """Retorna contagens corretas para intent_id."""
        mock_redis_client.hgetall.return_value = {'worker-001': '2'}

        result = await affinity_tracker.get_intent_allocations('intent-456')

        assert result == {'worker-001': 2}

    @pytest.mark.asyncio
    async def test_get_critical_tickets_on_worker(self, affinity_tracker, mock_redis_client):
        """Retorna set de ticket_ids críticos."""
        mock_redis_client.smembers.return_value = {'ticket-1', 'ticket-2'}

        result = await affinity_tracker.get_critical_tickets_on_worker('worker-001')

        assert result == {'ticket-1', 'ticket-2'}

    @pytest.mark.asyncio
    async def test_record_allocation_increments_count(self, affinity_tracker, mock_redis_client):
        """Incrementa contador no Redis ao registrar alocação."""
        ticket = {
            'ticket_id': 'ticket-123',
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'risk_band': 'medium',
            'priority': 'NORMAL'
        }

        result = await affinity_tracker.record_allocation(ticket, 'worker-001')

        assert result is True
        pipe = mock_redis_client.pipeline.return_value
        pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_allocation_critical_ticket(self, affinity_tracker, mock_redis_client):
        """Registra ticket crítico no set de críticos."""
        ticket = {
            'ticket_id': 'ticket-critical',
            'plan_id': 'plan-123',
            'intent_id': 'intent-456',
            'risk_band': 'critical',
            'priority': 'CRITICAL'
        }

        result = await affinity_tracker.record_allocation(ticket, 'worker-001')

        assert result is True
        pipe = mock_redis_client.pipeline.return_value
        # Verifica que sadd foi chamado para ticket crítico
        assert pipe.sadd.called

    @pytest.mark.asyncio
    async def test_cleanup_completed_ticket(self, affinity_tracker, mock_redis_client):
        """Remove ticket do cache ao completar."""
        result = await affinity_tracker.cleanup_completed_ticket(
            ticket_id='ticket-123',
            plan_id='plan-123',
            intent_id='intent-456',
            worker_id='worker-001'
        )

        assert result is True
        pipe = mock_redis_client.pipeline.return_value
        pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_failure_fail_open_get_plan(self, affinity_tracker, mock_redis_client, mock_metrics):
        """Retorna dict vazio em caso de falha do Redis (fail-open)."""
        mock_redis_client.hgetall.side_effect = Exception("Redis connection failed")

        result = await affinity_tracker.get_plan_allocations('plan-123')

        assert result == {}
        mock_metrics.record_affinity_cache_operation.assert_called_with('get_plan', 'failure')

    @pytest.mark.asyncio
    async def test_redis_failure_fail_open_record(self, affinity_tracker, mock_redis_client, mock_metrics):
        """Retorna False em caso de falha ao registrar (fail-open)."""
        pipe = mock_redis_client.pipeline.return_value
        pipe.execute.side_effect = Exception("Redis write failed")

        ticket = {'ticket_id': 'ticket-123', 'plan_id': 'plan-123'}
        result = await affinity_tracker.record_allocation(ticket, 'worker-001')

        assert result is False
        mock_metrics.record_affinity_cache_operation.assert_called_with('record', 'failure')

    def test_is_ticket_critical_risk_band(self, affinity_tracker):
        """Verifica detecção de ticket crítico por risk_band."""
        ticket_critical = {'risk_band': 'critical', 'priority': 'NORMAL'}
        ticket_high = {'risk_band': 'high', 'priority': 'NORMAL'}
        ticket_medium = {'risk_band': 'medium', 'priority': 'NORMAL'}

        assert affinity_tracker.is_ticket_critical(ticket_critical) is True
        assert affinity_tracker.is_ticket_critical(ticket_high) is True
        assert affinity_tracker.is_ticket_critical(ticket_medium) is False

    def test_is_ticket_critical_priority(self, affinity_tracker):
        """Verifica detecção de ticket crítico por priority."""
        ticket_critical = {'risk_band': 'medium', 'priority': 'CRITICAL'}
        ticket_high = {'risk_band': 'medium', 'priority': 'HIGH'}
        ticket_normal = {'risk_band': 'medium', 'priority': 'NORMAL'}

        assert affinity_tracker.is_ticket_critical(ticket_critical) is True
        assert affinity_tracker.is_ticket_critical(ticket_high) is True
        assert affinity_tracker.is_ticket_critical(ticket_normal) is False


class TestResourceAllocatorAffinity:
    """Testes de integração de affinity no ResourceAllocator."""

    @pytest.fixture
    def mock_config(self):
        """Mock das configurações com affinity habilitado."""
        config = MagicMock()
        config.scheduler_enable_affinity = True
        config.scheduler_affinity_plan_weight = 0.6
        config.scheduler_affinity_anti_weight = 0.3
        config.scheduler_affinity_intent_weight = 0.1
        config.scheduler_affinity_plan_threshold = 3
        config.scheduler_affinity_anti_affinity_risk_bands = ['critical', 'high']
        config.scheduler_affinity_anti_affinity_priorities = ['CRITICAL', 'HIGH']
        config.service_registry_max_results = 5
        return config

    @pytest.fixture
    def mock_metrics(self):
        """Mock das métricas."""
        metrics = MagicMock()
        metrics.record_affinity_hit = MagicMock()
        metrics.record_affinity_miss = MagicMock()
        metrics.record_anti_affinity_enforced = MagicMock()
        metrics.record_affinity_score = MagicMock()
        return metrics

    @pytest.fixture
    def mock_affinity_tracker(self):
        """Mock do AffinityTracker."""
        tracker = AsyncMock()
        tracker.get_plan_allocations = AsyncMock(return_value={})
        tracker.get_intent_allocations = AsyncMock(return_value={})
        tracker.get_critical_tickets_on_worker = AsyncMock(return_value=set())
        tracker.record_allocation = AsyncMock(return_value=True)
        return tracker

    @pytest.fixture
    def resource_allocator(self, mock_config, mock_metrics, mock_affinity_tracker):
        """Instância do ResourceAllocator com mocks."""
        from src.scheduler.resource_allocator import ResourceAllocator

        mock_registry = MagicMock()

        return ResourceAllocator(
            registry_client=mock_registry,
            config=mock_config,
            metrics=mock_metrics,
            affinity_tracker=mock_affinity_tracker
        )

    def test_calculate_affinity_score_plan_hit(self, resource_allocator, mock_metrics):
        """Score alto quando worker tem tickets do mesmo plan."""
        agent = {'agent_id': 'worker-001', 'status': 'HEALTHY'}
        ticket = {'plan_id': 'plan-123', 'intent_id': 'intent-456', 'risk_band': 'medium', 'priority': 'NORMAL'}
        plan_allocations = {'worker-001': 3}  # Worker já tem 3 tickets do plan
        intent_allocations = {}
        critical_tickets = set()

        score = resource_allocator._calculate_affinity_score(
            agent, ticket, plan_allocations, intent_allocations, critical_tickets
        )

        # Plan score = 1.0 (3 tickets >= threshold 3)
        # Anti score = 0.5 (não é crítico - neutro)
        # Intent score = 0.5 (neutro)
        # Score = 0.6*1.0 + 0.3*0.5 + 0.1*0.5 = 0.8
        assert score >= 0.75
        # NOTA: Métricas são registradas em select_best_worker, não em _calculate_affinity_score

    def test_calculate_affinity_score_plan_miss(self, resource_allocator, mock_metrics):
        """Score neutro quando worker não tem tickets do plan."""
        agent = {'agent_id': 'worker-002', 'status': 'HEALTHY'}
        ticket = {'plan_id': 'plan-123', 'intent_id': 'intent-456', 'risk_band': 'medium', 'priority': 'NORMAL'}
        plan_allocations = {'worker-001': 3}  # Outro worker tem tickets, não este
        intent_allocations = {}
        critical_tickets = set()

        score = resource_allocator._calculate_affinity_score(
            agent, ticket, plan_allocations, intent_allocations, critical_tickets
        )

        # Plan score = 0.5 (neutro - worker-002 não tem tickets)
        # Anti score = 0.5 (não é crítico - neutro)
        # Intent score = 0.5 (neutro)
        # Score = 0.6*0.5 + 0.3*0.5 + 0.1*0.5 = 0.5
        assert 0.45 <= score <= 0.55
        # NOTA: Métricas são registradas em select_best_worker, não em _calculate_affinity_score

    def test_calculate_affinity_score_anti_affinity_critical(self, resource_allocator, mock_metrics):
        """Score penalizado para worker com tickets críticos quando ticket é crítico."""
        agent = {'agent_id': 'worker-001', 'status': 'HEALTHY'}
        ticket = {'plan_id': 'plan-123', 'intent_id': 'intent-456', 'risk_band': 'critical', 'priority': 'CRITICAL'}
        plan_allocations = {'worker-001': 2}  # Worker tem 2 tickets do plan (plan_score alto)
        intent_allocations = {}
        critical_tickets = {'ticket-critical-1'}  # Worker já tem ticket crítico

        score = resource_allocator._calculate_affinity_score(
            agent, ticket, plan_allocations, intent_allocations, critical_tickets
        )

        # Anti score = 0.0 (worker já tem críticos, evitar)
        # Plan score = 0.5 + 0.5 * (2/3) = 0.833
        # Intent score = 0.5 (neutro)
        # Score = 0.6 * 0.833 + 0.3 * 0.0 + 0.1 * 0.5 = 0.55
        # Score é penalizado mas não bloqueado (anti_affinity é um fator, não veto)
        assert score < 0.7  # Menor que sem anti-affinity
        # NOTA: Métricas são registradas em select_best_worker, não em _calculate_affinity_score

    def test_calculate_affinity_score_anti_affinity_no_criticals(self, resource_allocator, mock_metrics):
        """Score alto para worker sem tickets críticos quando ticket é crítico."""
        agent = {'agent_id': 'worker-002', 'status': 'HEALTHY'}
        ticket = {'plan_id': 'plan-123', 'intent_id': 'intent-456', 'risk_band': 'critical', 'priority': 'CRITICAL'}
        plan_allocations = {}
        intent_allocations = {}
        critical_tickets = set()  # Worker não tem tickets críticos

        score = resource_allocator._calculate_affinity_score(
            agent, ticket, plan_allocations, intent_allocations, critical_tickets
        )

        # Anti score = 1.0 (worker limpo, preferir)
        # Score final deve ser razoável
        assert score >= 0.5

    def test_calculate_affinity_score_intent_affinity(self, resource_allocator, mock_metrics):
        """Score moderado para mesmo intent_id."""
        agent = {'agent_id': 'worker-001', 'status': 'HEALTHY'}
        ticket = {'plan_id': 'plan-123', 'intent_id': 'intent-456', 'risk_band': 'medium', 'priority': 'NORMAL'}
        plan_allocations = {}
        intent_allocations = {'worker-001': 2}  # Worker tem tickets do mesmo intent
        critical_tickets = set()

        score = resource_allocator._calculate_affinity_score(
            agent, ticket, plan_allocations, intent_allocations, critical_tickets
        )

        # Plan score = 0.5 (neutro)
        # Anti score = 0.5 (não é crítico - neutro)
        # Intent score = 0.5 + 0.5 * (2/3) = 0.833
        # Score = 0.6*0.5 + 0.3*0.5 + 0.1*0.833 = 0.533
        # Intent score contribui positivamente comparado a score totalmente neutro (0.5)
        assert score > 0.5
        # NOTA: Métricas são registradas em select_best_worker, não em _calculate_affinity_score

    @pytest.mark.asyncio
    async def test_select_best_worker_with_affinity_enabled(
        self, resource_allocator, mock_affinity_tracker
    ):
        """Valida integração completa com affinity habilitado."""
        workers = [
            {'agent_id': 'worker-001', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.95}},
            {'agent_id': 'worker-002', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.90}}
        ]
        ticket = {'ticket_id': 'ticket-123', 'plan_id': 'plan-123', 'risk_band': 'medium'}

        # Worker-001 já tem tickets do mesmo plan
        mock_affinity_tracker.get_plan_allocations.return_value = {'worker-001': 3}

        best_worker = await resource_allocator.select_best_worker(
            workers=workers,
            priority_score=0.8,
            ticket=ticket
        )

        assert best_worker is not None
        assert best_worker.get('affinity_applied') is True
        mock_affinity_tracker.record_allocation.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_best_worker_affinity_disabled(self, mock_config, mock_metrics):
        """Comportamento sem affinity habilitado."""
        from src.scheduler.resource_allocator import ResourceAllocator

        mock_config.scheduler_enable_affinity = False
        mock_registry = MagicMock()

        allocator = ResourceAllocator(
            registry_client=mock_registry,
            config=mock_config,
            metrics=mock_metrics,
            affinity_tracker=None
        )

        workers = [
            {'agent_id': 'worker-001', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.95}},
        ]
        ticket = {'ticket_id': 'ticket-123', 'plan_id': 'plan-123'}

        best_worker = await allocator.select_best_worker(
            workers=workers,
            priority_score=0.8,
            ticket=ticket
        )

        assert best_worker is not None
        assert best_worker.get('affinity_applied', False) is False

    @pytest.mark.asyncio
    async def test_affinity_tracker_failure_graceful_degradation(
        self, resource_allocator, mock_affinity_tracker
    ):
        """Continua sem affinity se tracker falhar."""
        mock_affinity_tracker.get_plan_allocations.side_effect = Exception("Redis down")

        workers = [
            {'agent_id': 'worker-001', 'status': 'HEALTHY', 'telemetry': {'success_rate': 0.95}},
        ]
        ticket = {'ticket_id': 'ticket-123', 'plan_id': 'plan-123'}

        # Não deve lançar exceção
        best_worker = await resource_allocator.select_best_worker(
            workers=workers,
            priority_score=0.8,
            ticket=ticket
        )

        assert best_worker is not None
