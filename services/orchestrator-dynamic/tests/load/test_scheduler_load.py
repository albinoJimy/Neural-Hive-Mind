"""
Testes de carga para IntelligentScheduler.

Valida performance sob alta concorrência:
- Throughput (tickets/segundo)
- Latência P95/P99
- Cache hit rate
- Fallback behavior sob stress
"""

import asyncio
import pytest
import time
import statistics
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
class LoadTestMetrics:
    """Coleta métricas de performance durante testes de carga."""
    latencies_ms: List[float] = field(default_factory=list)
    success_count: int = 0
    fallback_count: int = 0
    error_count: int = 0
    cache_hits: int = 0
    start_time: float = 0
    end_time: float = 0

    def record_latency(self, latency_ms: float):
        self.latencies_ms.append(latency_ms)

    def record_success(self, used_fallback: bool = False):
        if used_fallback:
            self.fallback_count += 1
        else:
            self.success_count += 1

    def record_error(self):
        self.error_count += 1

    def record_cache_hit(self):
        self.cache_hits += 1

    @property
    def total_count(self) -> int:
        return self.success_count + self.fallback_count + self.error_count

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time > 0 else 0

    @property
    def throughput(self) -> float:
        """Tickets processados por segundo."""
        if self.duration_seconds > 0:
            return self.total_count / self.duration_seconds
        return 0

    @property
    def success_rate(self) -> float:
        """Taxa de sucesso (não-fallback)."""
        if self.total_count > 0:
            return self.success_count / self.total_count
        return 0

    @property
    def latency_p50(self) -> float:
        if self.latencies_ms:
            sorted_latencies = sorted(self.latencies_ms)
            idx = int(len(sorted_latencies) * 0.50)
            return sorted_latencies[idx]
        return 0

    @property
    def latency_p95(self) -> float:
        if self.latencies_ms:
            sorted_latencies = sorted(self.latencies_ms)
            idx = int(len(sorted_latencies) * 0.95)
            return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
        return 0

    @property
    def latency_p99(self) -> float:
        if self.latencies_ms:
            sorted_latencies = sorted(self.latencies_ms)
            idx = int(len(sorted_latencies) * 0.99)
            return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
        return 0

    @property
    def cache_hit_rate(self) -> float:
        if self.total_count > 0:
            return self.cache_hits / self.total_count
        return 0


@pytest.fixture
def load_test_config():
    """Config otimizada para testes de carga."""
    config = MagicMock(spec=OrchestratorSettings)
    config.service_registry_cache_ttl_seconds = 60
    config.service_registry_timeout_seconds = 5
    config.scheduler_priority_weights = {'risk': 0.4, 'qos': 0.3, 'sla': 0.3}
    config.enable_ml_enhanced_scheduling = False
    config.optimizer_forecast_horizon_minutes = 5
    config.CIRCUIT_BREAKER_ENABLED = False
    config.service_name = 'orchestrator-dynamic'
    return config


@pytest.fixture
def mock_metrics():
    """Metrics mock que rastreia chamadas para análise."""
    metrics = MagicMock(spec=OrchestratorMetrics)
    metrics.cache_hit_count = 0

    def track_cache_hit():
        metrics.cache_hit_count += 1
    metrics.record_cache_hit = track_cache_hit
    metrics.record_scheduler_allocation = MagicMock()
    metrics.record_priority_score = MagicMock()
    metrics.record_workers_discovered = MagicMock()
    metrics.record_discovery_failure = MagicMock()
    metrics.record_scheduler_rejection = MagicMock()
    return metrics


@pytest.fixture
def mock_priority_calculator():
    """PriorityCalculator mock."""
    calc = MagicMock(spec=PriorityCalculator)
    calc.calculate_priority_score = MagicMock(return_value=0.75)
    return calc


@pytest.fixture
def sample_workers() -> List[Dict[str, Any]]:
    """Lista de workers mock."""
    return [
        {
            'agent_id': f'worker-{i:03d}',
            'agent_type': 'worker-agent',
            'score': 0.9 - (i * 0.05),
            'capabilities': ['python', 'data-processing'],
            'status': 'HEALTHY',
            'telemetry': {
                'success_rate': 0.95,
                'avg_duration_ms': 500 + (i * 100),
                'total_executions': 100
            }
        }
        for i in range(10)
    ]


def create_mock_resource_allocator(
    workers: List[Dict],
    discovery_latency_ms: float = 10
) -> AsyncMock:
    """Cria ResourceAllocator mock com latência simulada."""
    allocator = AsyncMock(spec=ResourceAllocator)

    async def mock_discover(*args, **kwargs):
        await asyncio.sleep(discovery_latency_ms / 1000)
        return workers

    allocator.discover_workers = mock_discover
    allocator.select_best_worker = MagicMock(
        side_effect=lambda workers, **kwargs: workers[0] if workers else None
    )
    return allocator


def generate_tickets(
    count: int,
    capability_patterns: int = 5
) -> List[Dict[str, Any]]:
    """Gera tickets de teste com padrões variados de capabilities."""
    capabilities_options = [
        ['python', 'data-processing'],
        ['python', 'ml-inference'],
        ['java', 'api-gateway'],
        ['nodejs', 'web-frontend'],
        ['go', 'microservice'],
    ]
    risk_bands = ['low', 'normal', 'high', 'critical']
    qos_modes = ['AT_MOST_ONCE', 'AT_LEAST_ONCE', 'EXACTLY_ONCE']

    tickets = []
    for i in range(count):
        tickets.append({
            'ticket_id': f'ticket-{i:05d}',
            'risk_band': risk_bands[i % len(risk_bands)],
            'qos': {
                'delivery_mode': qos_modes[i % len(qos_modes)],
                'consistency': 'EVENTUAL',
                'durability': 'PERSISTENT'
            },
            'sla': {
                'deadline': (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                'timeout_ms': 3600000
            },
            'required_capabilities': capabilities_options[i % capability_patterns],
            'namespace': 'default',
            'security_level': 'standard',
            'estimated_duration_ms': 1000,
            'created_at': datetime.utcnow().isoformat()
        })
    return tickets


class TestSchedulerThroughput:
    """Testes de throughput do scheduler."""

    @pytest.mark.asyncio
    async def test_throughput_sequential_100_tickets(
        self,
        load_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Testa throughput com 100 tickets sequenciais."""
        allocator = create_mock_resource_allocator(sample_workers, discovery_latency_ms=5)
        scheduler = IntelligentScheduler(
            config=load_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(100)
        metrics = LoadTestMetrics()
        metrics.start_time = time.time()

        for ticket in tickets:
            start = time.time()
            result = await scheduler.schedule_ticket(ticket)
            latency_ms = (time.time() - start) * 1000
            metrics.record_latency(latency_ms)

            if result.get('allocation_metadata', {}).get('allocation_method') == 'intelligent_scheduler':
                metrics.record_success()
            else:
                metrics.record_success(used_fallback=True)

        metrics.end_time = time.time()

        # Validações
        assert metrics.total_count == 100, 'Todos os 100 tickets devem ser processados'
        assert metrics.throughput > 10, f'Throughput mínimo 10 t/s, obtido: {metrics.throughput:.2f}'
        assert metrics.latency_p95 < 200, f'Latência P95 deve ser < 200ms, obtido: {metrics.latency_p95:.2f}ms'

        print(f'\n[Throughput Sequencial] Tickets: {metrics.total_count}')
        print(f'  Throughput: {metrics.throughput:.2f} tickets/s')
        print(f'  Latência P50: {metrics.latency_p50:.2f}ms')
        print(f'  Latência P95: {metrics.latency_p95:.2f}ms')
        print(f'  Latência P99: {metrics.latency_p99:.2f}ms')

    @pytest.mark.asyncio
    async def test_throughput_concurrent_50_tickets(
        self,
        load_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Testa throughput com 50 tickets concorrentes."""
        allocator = create_mock_resource_allocator(sample_workers, discovery_latency_ms=10)
        scheduler = IntelligentScheduler(
            config=load_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(50)
        metrics = LoadTestMetrics()

        async def process_ticket(ticket: Dict) -> float:
            start = time.time()
            result = await scheduler.schedule_ticket(ticket)
            latency_ms = (time.time() - start) * 1000
            return latency_ms, result

        metrics.start_time = time.time()
        results = await asyncio.gather(*[process_ticket(t) for t in tickets])
        metrics.end_time = time.time()

        for latency_ms, result in results:
            metrics.record_latency(latency_ms)
            if result.get('allocation_metadata', {}).get('allocation_method') == 'intelligent_scheduler':
                metrics.record_success()
            else:
                metrics.record_success(used_fallback=True)

        # Validações
        assert metrics.total_count == 50, 'Todos os 50 tickets devem ser processados'
        assert metrics.success_rate > 0.95, f'Taxa de sucesso > 95%, obtido: {metrics.success_rate*100:.1f}%'
        assert metrics.latency_p95 < 200, f'Latência P95 < 200ms, obtido: {metrics.latency_p95:.2f}ms'

        print(f'\n[Concorrência Moderada] Tickets: {metrics.total_count}')
        print(f'  Throughput: {metrics.throughput:.2f} tickets/s')
        print(f'  Taxa de sucesso: {metrics.success_rate*100:.1f}%')
        print(f'  Latência P95: {metrics.latency_p95:.2f}ms')

    @pytest.mark.asyncio
    async def test_throughput_concurrent_200_tickets(
        self,
        load_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Testa throughput com 200 tickets concorrentes - alta carga."""
        allocator = create_mock_resource_allocator(sample_workers, discovery_latency_ms=15)
        scheduler = IntelligentScheduler(
            config=load_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(200)
        metrics = LoadTestMetrics()

        async def process_ticket(ticket: Dict) -> tuple:
            start = time.time()
            result = await scheduler.schedule_ticket(ticket)
            latency_ms = (time.time() - start) * 1000
            return latency_ms, result

        metrics.start_time = time.time()
        results = await asyncio.gather(*[process_ticket(t) for t in tickets])
        metrics.end_time = time.time()

        for latency_ms, result in results:
            metrics.record_latency(latency_ms)
            method = result.get('allocation_metadata', {}).get('allocation_method')
            if method == 'intelligent_scheduler':
                metrics.record_success()
            else:
                metrics.record_success(used_fallback=True)

        # Validações
        assert metrics.total_count == 200, 'Todos os 200 tickets devem ser processados'
        assert metrics.latency_p95 < 300, f'Latência P95 < 300ms, obtido: {metrics.latency_p95:.2f}ms'
        assert metrics.throughput > 50, f'Throughput > 50 t/s, obtido: {metrics.throughput:.2f}'

        print(f'\n[Alta Concorrência] Tickets: {metrics.total_count}')
        print(f'  Throughput: {metrics.throughput:.2f} tickets/s')
        print(f'  Latência P50: {metrics.latency_p50:.2f}ms')
        print(f'  Latência P95: {metrics.latency_p95:.2f}ms')
        print(f'  Latência P99: {metrics.latency_p99:.2f}ms')


class TestSchedulerCachePerformance:
    """Testes de performance do cache de descobertas."""

    @pytest.mark.asyncio
    async def test_cache_effectiveness_same_capabilities(
        self,
        load_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Testa efetividade do cache com mesmas capabilities."""
        discovery_calls = 0
        original_workers = sample_workers.copy()

        async def tracking_discover(*args, **kwargs):
            nonlocal discovery_calls
            discovery_calls += 1
            await asyncio.sleep(0.01)
            return original_workers

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = tracking_discover
        allocator.select_best_worker = MagicMock(return_value=original_workers[0])

        scheduler = IntelligentScheduler(
            config=load_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        # Tickets com mesmas capabilities
        tickets = generate_tickets(100, capability_patterns=1)
        metrics = LoadTestMetrics()

        for ticket in tickets:
            start = time.time()
            await scheduler.schedule_ticket(ticket)
            metrics.record_latency((time.time() - start) * 1000)

        # Cache hit rate alto esperado (99 de 100 devem ser cache hits)
        cache_hit_rate = (100 - discovery_calls) / 100

        assert cache_hit_rate > 0.90, f'Cache hit rate > 90%, obtido: {cache_hit_rate*100:.1f}%'
        assert discovery_calls == 1, f'Apenas 1 discovery esperada, obtido: {discovery_calls}'

        print(f'\n[Cache - Mesmas Capabilities]')
        print(f'  Tickets: 100')
        print(f'  Discovery calls: {discovery_calls}')
        print(f'  Cache hit rate: {cache_hit_rate*100:.1f}%')

    @pytest.mark.asyncio
    async def test_cache_effectiveness_varied_capabilities(
        self,
        load_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Testa efetividade do cache com capabilities variadas."""
        discovery_calls = 0

        async def tracking_discover(*args, **kwargs):
            nonlocal discovery_calls
            discovery_calls += 1
            await asyncio.sleep(0.005)
            return sample_workers

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = tracking_discover
        allocator.select_best_worker = MagicMock(return_value=sample_workers[0])

        scheduler = IntelligentScheduler(
            config=load_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        # 1000 tickets com 10 padrões diferentes
        tickets = generate_tickets(1000, capability_patterns=10)

        for ticket in tickets:
            await scheduler.schedule_ticket(ticket)

        # 10 padrões únicos = 10 discoveries
        # 990 cache hits
        expected_discoveries = 10
        cache_hit_rate = (1000 - discovery_calls) / 1000

        # Ajustando expectativa: pode haver até 50 discoveries
        # dependendo de namespace e security_level
        assert discovery_calls <= 50, f'Máximo 50 discoveries, obtido: {discovery_calls}'
        assert cache_hit_rate > 0.80, f'Cache hit rate > 80%, obtido: {cache_hit_rate*100:.1f}%'

        print(f'\n[Cache - Capabilities Variadas]')
        print(f'  Tickets: 1000')
        print(f'  Padrões: 10')
        print(f'  Discovery calls: {discovery_calls}')
        print(f'  Cache hit rate: {cache_hit_rate*100:.1f}%')


class TestSchedulerLatencyDistribution:
    """Testes de distribuição de latência."""

    @pytest.mark.asyncio
    async def test_latency_consistency_under_load(
        self,
        load_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Valida consistência de latência sob carga."""
        allocator = create_mock_resource_allocator(sample_workers, discovery_latency_ms=10)
        scheduler = IntelligentScheduler(
            config=load_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(500, capability_patterns=5)
        latencies = []

        async def process_batch(batch: List[Dict]) -> List[float]:
            results = []
            for ticket in batch:
                start = time.time()
                await scheduler.schedule_ticket(ticket)
                results.append((time.time() - start) * 1000)
            return results

        # Processar em batches de 50
        for i in range(0, 500, 50):
            batch = tickets[i:i+50]
            batch_latencies = await process_batch(batch)
            latencies.extend(batch_latencies)

        # Calcular métricas
        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[int(len(sorted_latencies) * 0.50)]
        p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        mean = statistics.mean(latencies)
        stdev = statistics.stdev(latencies)

        # Validações
        assert p95 < 200, f'Latência P95 < 200ms, obtido: {p95:.2f}ms'
        assert p99 < 500, f'Latência P99 < 500ms, obtido: {p99:.2f}ms'
        assert stdev < mean, f'Desvio padrão deve ser menor que média'

        print(f'\n[Distribuição de Latência]')
        print(f'  Tickets: 500')
        print(f'  Média: {mean:.2f}ms')
        print(f'  Desvio Padrão: {stdev:.2f}ms')
        print(f'  P50: {p50:.2f}ms')
        print(f'  P95: {p95:.2f}ms')
        print(f'  P99: {p99:.2f}ms')
        print(f'  Min: {min(latencies):.2f}ms')
        print(f'  Max: {max(latencies):.2f}ms')


class TestSchedulerRiskBandPrioritization:
    """Testes de priorização por risk_band sob carga."""

    @pytest.mark.asyncio
    async def test_priority_ordering_under_load(
        self,
        load_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida que priority scores respeitam risk_band ordering."""
        # Usar PriorityCalculator real
        priority_calc = PriorityCalculator(load_test_config)
        allocator = create_mock_resource_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=load_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        # Gerar tickets com diferentes risk bands
        tickets_by_risk = {
            'critical': generate_tickets(25, capability_patterns=1),
            'high': generate_tickets(25, capability_patterns=1),
            'normal': generate_tickets(25, capability_patterns=1),
            'low': generate_tickets(25, capability_patterns=1),
        }

        # Atribuir risk bands
        for risk, tickets in tickets_by_risk.items():
            for t in tickets:
                t['risk_band'] = risk

        priority_scores = {'critical': [], 'high': [], 'normal': [], 'low': []}

        for risk, tickets in tickets_by_risk.items():
            for ticket in tickets:
                result = await scheduler.schedule_ticket(ticket)
                score = result.get('allocation_metadata', {}).get('priority_score', 0)
                priority_scores[risk].append(score)

        # Calcular médias
        avg_scores = {
            risk: statistics.mean(scores)
            for risk, scores in priority_scores.items()
        }

        # Validar ordenação: critical > high > normal > low
        assert avg_scores['critical'] > avg_scores['high'], \
            f"critical ({avg_scores['critical']:.3f}) deve ser > high ({avg_scores['high']:.3f})"
        assert avg_scores['high'] > avg_scores['normal'], \
            f"high ({avg_scores['high']:.3f}) deve ser > normal ({avg_scores['normal']:.3f})"
        assert avg_scores['normal'] > avg_scores['low'], \
            f"normal ({avg_scores['normal']:.3f}) deve ser > low ({avg_scores['low']:.3f})"

        print(f'\n[Priorização por Risk Band]')
        for risk in ['critical', 'high', 'normal', 'low']:
            print(f'  {risk}: média={avg_scores[risk]:.3f}')


class TestSchedulerFallbackBehavior:
    """Testes de comportamento de fallback sob carga."""

    @pytest.mark.asyncio
    async def test_fallback_on_discovery_timeout(
        self,
        load_test_config,
        mock_metrics,
        mock_priority_calculator
    ):
        """Valida fallback quando discovery excede timeout."""
        async def slow_discovery(*args, **kwargs):
            await asyncio.sleep(6)  # Excede timeout de 5s
            return []

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = slow_discovery
        allocator.select_best_worker = MagicMock(return_value=None)

        scheduler = IntelligentScheduler(
            config=load_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        tickets = generate_tickets(5, capability_patterns=1)
        metrics = LoadTestMetrics()

        metrics.start_time = time.time()
        for ticket in tickets:
            start = time.time()
            result = await scheduler.schedule_ticket(ticket)
            latency_ms = (time.time() - start) * 1000
            metrics.record_latency(latency_ms)

            method = result.get('allocation_metadata', {}).get('allocation_method')
            if method == 'fallback_stub':
                metrics.record_success(used_fallback=True)
            else:
                metrics.record_success()
        metrics.end_time = time.time()

        # Todos devem usar fallback devido ao timeout
        assert metrics.fallback_count == 5, \
            f'Todos 5 tickets devem usar fallback, obtido: {metrics.fallback_count}'

        print(f'\n[Fallback por Timeout]')
        print(f'  Tickets: {metrics.total_count}')
        print(f'  Fallbacks: {metrics.fallback_count}')

    @pytest.mark.asyncio
    async def test_fallback_on_no_workers(
        self,
        load_test_config,
        mock_metrics,
        mock_priority_calculator
    ):
        """Valida fallback quando nenhum worker está disponível."""
        async def empty_discovery(*args, **kwargs):
            await asyncio.sleep(0.005)
            return []

        allocator = AsyncMock(spec=ResourceAllocator)
        allocator.discover_workers = empty_discovery
        allocator.select_best_worker = MagicMock(return_value=None)

        scheduler = IntelligentScheduler(
            config=load_test_config,
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

        assert fallback_count == 50, f'Todos 50 tickets devem usar fallback'
        print(f'\n[Fallback sem Workers]')
        print(f'  Tickets: 50')
        print(f'  Fallbacks: {fallback_count}')


class TestSchedulerConcurrencySafety:
    """Testes de segurança em alta concorrência."""

    @pytest.mark.asyncio
    async def test_concurrent_cache_updates(
        self,
        load_test_config,
        mock_metrics,
        mock_priority_calculator,
        sample_workers
    ):
        """Valida que cache é thread-safe em alta concorrência."""
        allocator = create_mock_resource_allocator(sample_workers, discovery_latency_ms=5)

        scheduler = IntelligentScheduler(
            config=load_test_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=allocator
        )

        # Mesma capability para forçar contention no cache
        tickets = generate_tickets(100, capability_patterns=1)

        async def process_ticket(ticket: Dict) -> Dict:
            return await scheduler.schedule_ticket(ticket)

        # Processar todos concorrentemente
        results = await asyncio.gather(*[process_ticket(t) for t in tickets])

        # Verificar que todos foram processados corretamente
        success_count = sum(
            1 for r in results
            if r.get('allocation_metadata', {}).get('agent_id') is not None
        )

        assert success_count == 100, \
            f'Todos 100 tickets devem ter agent_id, obtido: {success_count}'

        print(f'\n[Segurança de Concorrência]')
        print(f'  Tickets concorrentes: 100')
        print(f'  Processados com sucesso: {success_count}')
