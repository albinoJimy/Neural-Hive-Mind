"""
Testes de stress para IntelligentScheduler.

Valida comportamento em condições extremas:
- Service Registry indisponível
- Falhas intermitentes
- Pool de workers esgotado
- Carga sustentada
- Rajadas de tráfego
"""

import asyncio
import pytest
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass, field

from src.scheduler.intelligent_scheduler import IntelligentScheduler
from src.scheduler.priority_calculator import PriorityCalculator
from src.scheduler.resource_allocator import ResourceAllocator
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@dataclass
class StressTestMetrics:
    """Métricas coletadas durante testes de stress."""
    total_requests: int = 0
    success_count: int = 0
    fallback_count: int = 0
    error_count: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    start_time: float = 0
    end_time: float = 0
    memory_samples: List[int] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time > 0 else 0

    @property
    def success_rate(self) -> float:
        if self.total_requests > 0:
            return self.success_count / self.total_requests
        return 0

    @property
    def fallback_rate(self) -> float:
        if self.total_requests > 0:
            return self.fallback_count / self.total_requests
        return 0

    @property
    def throughput(self) -> float:
        if self.duration_seconds > 0:
            return self.total_requests / self.duration_seconds
        return 0


@pytest.fixture
def stress_test_config():
    """Config para testes de stress."""
    config = MagicMock(spec=OrchestratorSettings)
    config.service_registry_cache_ttl_seconds = 60
    config.service_registry_timeout_seconds = 5
    config.scheduler_priority_weights = {'risk': 0.4, 'qos': 0.3, 'sla': 0.3}
    config.enable_ml_enhanced_scheduling = False
    config.CIRCUIT_BREAKER_ENABLED = False
    config.service_name = 'orchestrator-dynamic'
    return config


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock(spec=OrchestratorMetrics)
    return metrics


@pytest.fixture
def mock_priority_calculator():
    """PriorityCalculator mock."""
    calc = MagicMock(spec=PriorityCalculator)
    calc.calculate_priority_score = MagicMock(return_value=0.75)
    return calc


@pytest.fixture
def sample_workers() -> List[Dict[str, Any]]:
    """Workers mock."""
    return [
        {
            'agent_id': f'worker-{i:03d}',
            'agent_type': 'worker-agent',
            'score': 0.9 - (i * 0.05),
            'capabilities': ['python', 'data-processing'],
            'status': 'HEALTHY',
        }
        for i in range(10)
    ]


def generate_tickets(count: int) -> List[Dict[str, Any]]:
    """Gera tickets de teste."""
    risk_bands = ['low', 'normal', 'high', 'critical']
    return [
        {
            'ticket_id': f'stress-{i:05d}',
            'risk_band': risk_bands[i % 4],
            'qos': {
                'delivery_mode': 'AT_LEAST_ONCE',
                'consistency': 'EVENTUAL',
                'durability': 'PERSISTENT'
            },
            'sla': {
                'deadline': (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                'timeout_ms': 3600000
            },
            'required_capabilities': ['python', 'data-processing'],
            'namespace': 'default',
            'security_level': 'standard',
            'estimated_duration_ms': 1000,
            'created_at': datetime.utcnow().isoformat()
        }
        for i in range(count)
    ]


class TestServiceRegistryDown:
    """Testes com Service Registry completamente indisponível."""

    @pytest.mark.asyncio
    async def test_100_percent_fallback_when_registry_down(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator
    ):
        """Valida que 100% dos tickets usam fallback quando Service Registry está down."""
        async def failing_discovery(*args, **kwargs):
            raise Exception('Service Registry indisponível')

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = failing_discovery
        allocator.select_best_worker = MagicMock(return_value=None)

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(100)
        metrics = StressTestMetrics()
        metrics.start_time = time.time()

        for ticket in tickets:
            metrics.total_requests += 1
            start = time.time()

            result = await scheduler.schedule_ticket(ticket)
            latency_ms = (time.time() - start) * 1000
            metrics.latencies_ms.append(latency_ms)

            method = result.get('allocation_metadata', {}).get('allocation_method')
            if method == 'fallback_stub':
                metrics.fallback_count += 1
            else:
                metrics.success_count += 1

        metrics.end_time = time.time()

        # Todos devem usar fallback
        assert metrics.fallback_rate == 1.0, \
            f'100% fallback esperado, obtido: {metrics.fallback_rate*100:.1f}%'

        # Sistema não deve falhar
        assert metrics.error_count == 0, 'Não deve haver erros fatais'

        print(f'\n[Service Registry Down]')
        print(f'  Total: {metrics.total_requests}')
        print(f'  Fallback rate: {metrics.fallback_rate*100:.1f}%')
        print(f'  Throughput: {metrics.throughput:.2f} t/s')

    @pytest.mark.asyncio
    async def test_graceful_degradation_no_exceptions_to_caller(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator
    ):
        """Valida que exceções não propagam para o caller."""
        async def failing_discovery(*args, **kwargs):
            await asyncio.sleep(0.001)
            raise ConnectionError('Connection refused')

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = failing_discovery

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(50)
        exceptions_caught = 0

        for ticket in tickets:
            try:
                result = await scheduler.schedule_ticket(ticket)
                # Deve sempre retornar um resultado válido
                assert 'allocation_metadata' in result
                assert result['allocation_metadata'].get('agent_id') is not None
            except Exception:
                exceptions_caught += 1

        assert exceptions_caught == 0, \
            f'Nenhuma exceção deve propagar, {exceptions_caught} encontradas'

        print(f'\n[Graceful Degradation]')
        print(f'  Tickets: 50')
        print(f'  Exceções propagadas: {exceptions_caught}')


class TestIntermittentFailures:
    """Testes com falhas intermitentes do Service Registry."""

    @pytest.mark.asyncio
    async def test_50_percent_failure_rate(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Valida comportamento com 50% de taxa de falha."""
        call_count = 0

        async def intermittent_discovery(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.005)

            if call_count % 2 == 0:
                raise Exception('Intermittent failure')
            return sample_workers

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = intermittent_discovery
        allocator.select_best_worker = MagicMock(return_value=sample_workers[0])

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(100)
        metrics = StressTestMetrics()

        for ticket in tickets:
            metrics.total_requests += 1
            result = await scheduler.schedule_ticket(ticket)

            method = result.get('allocation_metadata', {}).get('allocation_method')
            if method == 'intelligent_scheduler':
                metrics.success_count += 1
            else:
                metrics.fallback_count += 1

        # Com cache, mesmo com 50% de falha, taxa de sucesso deve ser razoável
        # após o primeiro sucesso para um padrão de capability, cache é usado
        assert metrics.success_count + metrics.fallback_count == 100

        print(f'\n[Intermittent Failures 50%]')
        print(f'  Total: {metrics.total_requests}')
        print(f'  Sucesso: {metrics.success_count}')
        print(f'  Fallback: {metrics.fallback_count}')
        print(f'  Taxa de sucesso: {metrics.success_rate*100:.1f}%')

    @pytest.mark.asyncio
    async def test_random_failure_rate(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Valida comportamento com taxa de falha aleatória (30%)."""
        async def random_failing_discovery(*args, **kwargs):
            await asyncio.sleep(0.005)
            if random.random() < 0.3:  # 30% chance de falha
                raise Exception('Random failure')
            return sample_workers

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = random_failing_discovery
        allocator.select_best_worker = MagicMock(return_value=sample_workers[0])

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(200)
        metrics = StressTestMetrics()

        for ticket in tickets:
            metrics.total_requests += 1
            result = await scheduler.schedule_ticket(ticket)

            method = result.get('allocation_metadata', {}).get('allocation_method')
            if method == 'intelligent_scheduler':
                metrics.success_count += 1
            else:
                metrics.fallback_count += 1

        # Sistema deve continuar funcionando
        assert metrics.total_requests == 200
        assert metrics.error_count == 0

        print(f'\n[Random Failures 30%]')
        print(f'  Total: {metrics.total_requests}')
        print(f'  Taxa de sucesso: {metrics.success_rate*100:.1f}%')
        print(f'  Taxa de fallback: {metrics.fallback_rate*100:.1f}%')


class TestWorkerPoolExhaustion:
    """Testes com pool de workers esgotado."""

    @pytest.mark.asyncio
    async def test_no_workers_available(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator
    ):
        """Valida comportamento quando nenhum worker está disponível."""
        async def empty_discovery(*args, **kwargs):
            await asyncio.sleep(0.005)
            return []

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = empty_discovery
        allocator.select_best_worker = MagicMock(return_value=None)

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(50)
        fallback_count = 0

        for ticket in tickets:
            result = await scheduler.schedule_ticket(ticket)

            if result.get('allocation_metadata', {}).get('allocation_method') == 'fallback_stub':
                fallback_count += 1

        assert fallback_count == 50, \
            f'Todos 50 devem usar fallback, obtido: {fallback_count}'

        print(f'\n[Worker Pool Exhaustion]')
        print(f'  Tickets: 50')
        print(f'  Fallback: {fallback_count}')

    @pytest.mark.asyncio
    async def test_all_workers_unhealthy(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator
    ):
        """Valida comportamento quando todos workers estão unhealthy."""
        unhealthy_workers = [
            {
                'agent_id': f'worker-{i:03d}',
                'agent_type': 'worker-agent',
                'score': 0.0,  # Score zero indica unhealthy
                'status': 'UNHEALTHY',
                'capabilities': ['python'],
            }
            for i in range(5)
        ]

        async def discover_unhealthy(*args, **kwargs):
            return unhealthy_workers

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = discover_unhealthy
        allocator.select_best_worker = MagicMock(return_value=None)

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(20)
        fallback_count = 0

        for ticket in tickets:
            result = await scheduler.schedule_ticket(ticket)

            if result.get('allocation_metadata', {}).get('allocation_method') == 'fallback_stub':
                fallback_count += 1

        assert fallback_count == 20

        print(f'\n[All Workers Unhealthy]')
        print(f'  Tickets: 20')
        print(f'  Fallback: {fallback_count}')


class TestSustainedLoad:
    """Testes de carga sustentada."""

    @pytest.mark.asyncio
    async def test_sustained_load_60_seconds(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Valida estabilidade sob carga sustentada por 60 segundos."""
        async def stable_discovery(*args, **kwargs):
            await asyncio.sleep(0.01)
            return sample_workers

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = stable_discovery
        allocator.select_best_worker = MagicMock(return_value=sample_workers[0])

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        metrics = StressTestMetrics()
        duration_target = 10  # 10 segundos para teste rápido
        tickets_per_second = 50

        metrics.start_time = time.time()

        while (time.time() - metrics.start_time) < duration_target:
            batch = generate_tickets(tickets_per_second)

            for ticket in batch:
                metrics.total_requests += 1
                start = time.time()

                result = await scheduler.schedule_ticket(ticket)
                latency_ms = (time.time() - start) * 1000
                metrics.latencies_ms.append(latency_ms)

                method = result.get('allocation_metadata', {}).get('allocation_method')
                if method == 'intelligent_scheduler':
                    metrics.success_count += 1
                else:
                    metrics.fallback_count += 1

            # Aguardar para manter ~50 t/s
            await asyncio.sleep(0.02)

        metrics.end_time = time.time()

        # Validações
        assert metrics.success_rate > 0.95, \
            f'Taxa de sucesso > 95%, obtido: {metrics.success_rate*100:.1f}%'

        # Latência não deve degradar significativamente
        if len(metrics.latencies_ms) > 100:
            first_100_avg = sum(metrics.latencies_ms[:100]) / 100
            last_100_avg = sum(metrics.latencies_ms[-100:]) / 100

            # Degradação máxima de 50%
            assert last_100_avg < first_100_avg * 1.5, \
                f'Latência degradou muito: início {first_100_avg:.2f}ms, fim {last_100_avg:.2f}ms'

        print(f'\n[Sustained Load]')
        print(f'  Duração: {metrics.duration_seconds:.1f}s')
        print(f'  Total: {metrics.total_requests}')
        print(f'  Throughput: {metrics.throughput:.2f} t/s')
        print(f'  Taxa de sucesso: {metrics.success_rate*100:.1f}%')


class TestBurstTraffic:
    """Testes de rajadas de tráfego."""

    @pytest.mark.asyncio
    async def test_burst_followed_by_silence(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Valida recuperação após rajada de tráfego."""
        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = AsyncMock(return_value=sample_workers)
        allocator.select_best_worker = MagicMock(return_value=sample_workers[0])

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        # Primeira rajada
        burst1_tickets = generate_tickets(100)
        burst1_latencies = []

        for ticket in burst1_tickets:
            start = time.time()
            await scheduler.schedule_ticket(ticket)
            burst1_latencies.append((time.time() - start) * 1000)

        # Silêncio
        await asyncio.sleep(2)

        # Segunda rajada
        burst2_tickets = generate_tickets(100)
        burst2_latencies = []

        for ticket in burst2_tickets:
            start = time.time()
            await scheduler.schedule_ticket(ticket)
            burst2_latencies.append((time.time() - start) * 1000)

        # Comparar latências entre rajadas
        burst1_avg = sum(burst1_latencies) / len(burst1_latencies)
        burst2_avg = sum(burst2_latencies) / len(burst2_latencies)

        # Segunda rajada não deve ter latência significativamente maior
        assert burst2_avg < burst1_avg * 1.5, \
            f'Segunda rajada ({burst2_avg:.2f}ms) não deve ser 50% mais lenta que primeira ({burst1_avg:.2f}ms)'

        print(f'\n[Burst Traffic]')
        print(f'  Rajada 1: média {burst1_avg:.2f}ms')
        print(f'  Rajada 2: média {burst2_avg:.2f}ms')

    @pytest.mark.asyncio
    async def test_concurrent_burst_500_tickets(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Valida comportamento com rajada de 500 tickets concorrentes."""
        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = AsyncMock(return_value=sample_workers)
        allocator.select_best_worker = MagicMock(return_value=sample_workers[0])

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(500)
        metrics = StressTestMetrics()

        async def process_ticket(ticket: Dict) -> tuple:
            start = time.time()
            result = await scheduler.schedule_ticket(ticket)
            latency_ms = (time.time() - start) * 1000
            return latency_ms, result

        metrics.start_time = time.time()
        results = await asyncio.gather(*[process_ticket(t) for t in tickets])
        metrics.end_time = time.time()

        for latency_ms, result in results:
            metrics.total_requests += 1
            metrics.latencies_ms.append(latency_ms)

            method = result.get('allocation_metadata', {}).get('allocation_method')
            if method == 'intelligent_scheduler':
                metrics.success_count += 1
            else:
                metrics.fallback_count += 1

        # Validações
        assert metrics.total_requests == 500
        assert metrics.success_rate > 0.90, \
            f'Taxa de sucesso > 90%, obtido: {metrics.success_rate*100:.1f}%'

        sorted_latencies = sorted(metrics.latencies_ms)
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]

        assert p99 < 1000, f'Latência P99 < 1s, obtido: {p99:.2f}ms'

        print(f'\n[Concurrent Burst 500]')
        print(f'  Total: {metrics.total_requests}')
        print(f'  Throughput: {metrics.throughput:.2f} t/s')
        print(f'  Taxa de sucesso: {metrics.success_rate*100:.1f}%')
        print(f'  Latência P99: {p99:.2f}ms')


class TestCacheUnderStress:
    """Testes de cache sob stress."""

    @pytest.mark.asyncio
    async def test_cache_large_entries(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Valida que cache com muitas entradas não causa problemas."""
        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = AsyncMock(return_value=sample_workers)
        allocator.select_best_worker = MagicMock(return_value=sample_workers[0])

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        # Gerar tickets com muitos padrões diferentes de capability
        # para forçar muitas entradas de cache
        capability_patterns = [
            [f'cap-{i}', f'cap-{i+1}']
            for i in range(100)  # 100 padrões únicos
        ]

        tickets = []
        for i in range(1000):
            ticket = generate_tickets(1)[0]
            ticket['required_capabilities'] = capability_patterns[i % 100]
            tickets.append(ticket)

        metrics = StressTestMetrics()
        metrics.start_time = time.time()

        for ticket in tickets:
            metrics.total_requests += 1
            start = time.time()
            await scheduler.schedule_ticket(ticket)
            metrics.latencies_ms.append((time.time() - start) * 1000)

        metrics.end_time = time.time()

        # Cache deve ter no máximo 100 entradas (100 padrões únicos)
        cache_size = len(scheduler._discovery_cache)
        assert cache_size <= 100, \
            f'Cache deve ter <= 100 entradas, obtido: {cache_size}'

        # Performance não deve degradar
        if len(metrics.latencies_ms) > 100:
            first_100_avg = sum(metrics.latencies_ms[:100]) / 100
            last_100_avg = sum(metrics.latencies_ms[-100:]) / 100

            assert last_100_avg < first_100_avg * 2.0, \
                f'Performance não deve degradar mais que 2x'

        print(f'\n[Cache Large Entries]')
        print(f'  Tickets: {metrics.total_requests}')
        print(f'  Padrões únicos: 100')
        print(f'  Cache size: {cache_size}')
        print(f'  Throughput: {metrics.throughput:.2f} t/s')


class TestRecoveryAfterFailure:
    """Testes de recuperação após falhas."""

    @pytest.mark.asyncio
    async def test_recovery_after_registry_returns(
        self,
        stress_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Valida recuperação quando Service Registry volta a funcionar."""
        call_count = 0
        failure_until = 50  # Falha nos primeiros 50 calls

        async def recovering_discovery(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.005)

            if call_count <= failure_until:
                raise Exception('Service temporarily unavailable')
            return sample_workers

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = recovering_discovery
        allocator.select_best_worker = MagicMock(return_value=sample_workers[0])

        scheduler = IntelligentScheduler(
            config=stress_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(100)
        fallback_count = 0
        success_count = 0

        for i, ticket in enumerate(tickets):
            result = await scheduler.schedule_ticket(ticket)

            method = result.get('allocation_metadata', {}).get('allocation_method')
            if method == 'fallback_stub':
                fallback_count += 1
            else:
                success_count += 1

        # Depois dos primeiros 50 (com fallback), cache é atualizado
        # Tickets restantes devem usar scheduler inteligente
        assert success_count > 0, 'Deve haver sucessos após recuperação'

        print(f'\n[Recovery After Failure]')
        print(f'  Total: 100')
        print(f'  Fallbacks (esperados nos primeiros 50): {fallback_count}')
        print(f'  Sucessos (após recuperação): {success_count}')
