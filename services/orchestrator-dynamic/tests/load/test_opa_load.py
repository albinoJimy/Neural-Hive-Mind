"""
Testes de carga para integração OPA.

Valida performance da avaliação de políticas sob alta concorrência:
- Throughput (avaliações/segundo)
- Latência P95/P99
- Cache hit rate
- Circuit breaker behavior sob stress
- Batch evaluation performance
"""

import asyncio
import os
import pytest
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any
from unittest.mock import AsyncMock, Mock
from dataclasses import dataclass, field

from src.policies.opa_client import OPAClient
from src.config.settings import OrchestratorSettings


# Flag para testes com servidor OPA real
REAL_OPA_LOAD = os.getenv("RUN_OPA_LOAD_TESTS", "").lower() == "true"


@dataclass
class OPALoadTestMetrics:
    """Coleta métricas de performance durante testes de carga OPA."""
    latencies_ms: List[float] = field(default_factory=list)
    success_count: int = 0
    cache_hit_count: int = 0
    error_count: int = 0
    circuit_breaker_rejections: int = 0
    start_time: float = 0
    end_time: float = 0

    def record_latency(self, latency_ms: float):
        self.latencies_ms.append(latency_ms)

    def record_success(self, from_cache: bool = False):
        self.success_count += 1
        if from_cache:
            self.cache_hit_count += 1

    def record_error(self):
        self.error_count += 1

    def record_circuit_breaker_rejection(self):
        self.circuit_breaker_rejections += 1

    @property
    def total_count(self) -> int:
        return self.success_count + self.error_count + self.circuit_breaker_rejections

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time > 0 else 0

    @property
    def throughput(self) -> float:
        """Avaliações por segundo."""
        if self.duration_seconds > 0:
            return self.total_count / self.duration_seconds
        return 0

    @property
    def p50_latency(self) -> float:
        if len(self.latencies_ms) > 0:
            sorted_latencies = sorted(self.latencies_ms)
            idx = len(sorted_latencies) // 2
            return sorted_latencies[idx]
        return 0

    @property
    def p95_latency(self) -> float:
        if len(self.latencies_ms) > 0:
            sorted_latencies = sorted(self.latencies_ms)
            idx = int(len(sorted_latencies) * 0.95)
            return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
        return 0

    @property
    def p99_latency(self) -> float:
        if len(self.latencies_ms) > 0:
            sorted_latencies = sorted(self.latencies_ms)
            idx = int(len(sorted_latencies) * 0.99)
            return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
        return 0

    @property
    def cache_hit_rate(self) -> float:
        if self.success_count > 0:
            return self.cache_hit_count / self.success_count
        return 0

    @property
    def error_rate(self) -> float:
        if self.total_count > 0:
            return (self.error_count + self.circuit_breaker_rejections) / self.total_count
        return 0

    def summary(self) -> Dict[str, Any]:
        return {
            'total_requests': self.total_count,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'circuit_breaker_rejections': self.circuit_breaker_rejections,
            'duration_seconds': round(self.duration_seconds, 2),
            'throughput_per_second': round(self.throughput, 2),
            'p50_latency_ms': round(self.p50_latency, 2),
            'p95_latency_ms': round(self.p95_latency, 2),
            'p99_latency_ms': round(self.p99_latency, 2),
            'cache_hit_rate': round(self.cache_hit_rate * 100, 2),
            'error_rate': round(self.error_rate * 100, 2)
        }


@pytest.fixture
def load_test_config():
    """Configuração para testes de carga."""
    config = Mock(spec=OrchestratorSettings)
    config.opa_host = os.getenv('OPA_HOST', 'localhost')
    config.opa_port = int(os.getenv('OPA_PORT', '8181'))
    config.opa_timeout_seconds = 5
    config.opa_retry_attempts = 1  # Sem retries em load test para métricas precisas
    config.opa_cache_ttl_seconds = 30
    config.opa_fail_open = False
    config.opa_circuit_breaker_enabled = True
    config.opa_circuit_breaker_failure_threshold = 10
    config.opa_circuit_breaker_reset_timeout = 30
    config.opa_max_concurrent_evaluations = 50
    return config


@pytest.fixture
def mock_metrics():
    """Mock de métricas para testes."""
    metrics = Mock()
    metrics.record_opa_validation = Mock()
    metrics.record_opa_validation_latency = Mock()
    metrics.record_opa_circuit_breaker_transition = Mock()
    metrics.record_opa_cache_miss = Mock()
    metrics.record_opa_cache_hit = Mock()
    metrics.record_opa_batch_evaluation = Mock()
    metrics.record_opa_policy_decision_duration = Mock()
    metrics.record_opa_circuit_breaker_state = Mock()
    metrics.record_opa_error = Mock()
    metrics.opa_cache_hit_ratio = Mock()
    metrics.opa_cache_hit_ratio.set = Mock()
    return metrics


def generate_resource_limits_input(ticket_id: str, risk_band: str = 'medium') -> dict:
    """Gera input válido para resource_limits."""
    return {
        'input': {
            'resource': {
                'ticket_id': ticket_id,
                'risk_band': risk_band,
                'sla': {
                    'timeout_ms': 60000,
                    'max_retries': 2
                },
                'required_capabilities': ['code_generation']
            },
            'parameters': {
                'allowed_capabilities': ['code_generation', 'testing'],
                'max_concurrent_tickets': 100
            },
            'context': {
                'total_tickets': 50
            }
        }
    }


def generate_sla_enforcement_input(ticket_id: str, deadline_offset_hours: int = 2) -> dict:
    """Gera input válido para sla_enforcement."""
    current_time = int(datetime.now().timestamp() * 1000)
    deadline = int((datetime.now() + timedelta(hours=deadline_offset_hours)).timestamp() * 1000)

    return {
        'input': {
            'resource': {
                'ticket_id': ticket_id,
                'risk_band': 'high',
                'sla': {
                    'timeout_ms': 120000,
                    'deadline': deadline
                },
                'qos': {
                    'delivery_mode': 'EXACTLY_ONCE',
                    'consistency': 'STRONG'
                },
                'priority': 'HIGH',
                'estimated_duration_ms': 60000
            },
            'context': {
                'current_time': current_time
            }
        }
    }


class TestOPALoadSinglePolicy:
    """Testes de carga para avaliação de política única."""

    @pytest.mark.asyncio
    async def test_sequential_evaluations(self, load_test_config, mock_metrics):
        """Testa avaliações sequenciais para baseline de latência."""
        client = OPAClient(load_test_config, metrics=mock_metrics)
        await client.initialize()

        metrics = OPALoadTestMetrics()
        num_requests = 100
        policy_path = 'neuralhive/orchestrator/resource_limits'

        metrics.start_time = time.perf_counter()

        for i in range(num_requests):
            input_data = generate_resource_limits_input(f'load-seq-{i}')
            start = time.perf_counter()

            try:
                result = await client.evaluate_policy(policy_path, input_data)
                latency_ms = (time.perf_counter() - start) * 1000
                metrics.record_latency(latency_ms)
                metrics.record_success()
            except Exception:
                metrics.record_error()

        metrics.end_time = time.perf_counter()
        await client.close()

        summary = metrics.summary()
        print(f"\nSequential Load Test Summary: {summary}")

        # Assertions de performance
        assert metrics.error_rate < 0.1, "Taxa de erro muito alta"
        assert metrics.p95_latency < 500, "P95 latency muito alta"

    @pytest.mark.asyncio
    async def test_concurrent_evaluations(self, load_test_config, mock_metrics):
        """Testa avaliações concorrentes para throughput."""
        client = OPAClient(load_test_config, metrics=mock_metrics)
        await client.initialize()

        metrics = OPALoadTestMetrics()
        num_requests = 200
        concurrency = 20
        policy_path = 'neuralhive/orchestrator/resource_limits'

        async def evaluate_once(idx: int):
            input_data = generate_resource_limits_input(f'load-conc-{idx}')
            start = time.perf_counter()
            try:
                await client.evaluate_policy(policy_path, input_data)
                latency_ms = (time.perf_counter() - start) * 1000
                metrics.record_latency(latency_ms)
                metrics.record_success()
            except Exception:
                metrics.record_error()

        metrics.start_time = time.perf_counter()

        # Executar em batches de concurrency
        for batch_start in range(0, num_requests, concurrency):
            batch_end = min(batch_start + concurrency, num_requests)
            tasks = [evaluate_once(i) for i in range(batch_start, batch_end)]
            await asyncio.gather(*tasks)

        metrics.end_time = time.perf_counter()
        await client.close()

        summary = metrics.summary()
        print(f"\nConcurrent Load Test Summary: {summary}")

        # Assertions de performance
        assert metrics.throughput > 10, "Throughput muito baixo"
        assert metrics.error_rate < 0.1, "Taxa de erro muito alta"

    @pytest.mark.asyncio
    async def test_cache_effectiveness(self, load_test_config, mock_metrics):
        """Testa efetividade do cache com inputs repetidos."""
        client = OPAClient(load_test_config, metrics=mock_metrics)
        await client.initialize()

        metrics = OPALoadTestMetrics()
        policy_path = 'neuralhive/orchestrator/resource_limits'

        # Usar apenas 10 inputs diferentes para 100 requests
        unique_inputs = [
            generate_resource_limits_input(f'load-cache-{i}')
            for i in range(10)
        ]

        metrics.start_time = time.perf_counter()

        for i in range(100):
            input_data = unique_inputs[i % 10]
            start = time.perf_counter()

            try:
                await client.evaluate_policy(policy_path, input_data)
                latency_ms = (time.perf_counter() - start) * 1000
                metrics.record_latency(latency_ms)
                metrics.record_success()
            except Exception:
                metrics.record_error()

        metrics.end_time = time.perf_counter()

        # Obter estatísticas de cache do client
        cache_stats = client.get_cache_stats()
        await client.close()

        summary = metrics.summary()
        print(f"\nCache Effectiveness Test Summary: {summary}")
        print(f"Cache Stats: {cache_stats}")

        # Com 10 inputs únicos e 100 requests, esperamos ~90% cache hit
        assert cache_stats['hit_ratio'] > 0.8, "Cache hit ratio muito baixo"


class TestOPALoadBatchEvaluation:
    """Testes de carga para batch evaluation."""

    @pytest.mark.asyncio
    async def test_batch_evaluation_throughput(self, load_test_config, mock_metrics):
        """Testa throughput de batch evaluation."""
        client = OPAClient(load_test_config, metrics=mock_metrics)
        await client.initialize()

        metrics = OPALoadTestMetrics()
        num_batches = 20
        batch_size = 10

        metrics.start_time = time.perf_counter()

        for batch_idx in range(num_batches):
            evaluations = [
                (
                    'neuralhive/orchestrator/resource_limits',
                    generate_resource_limits_input(f'batch-{batch_idx}-{i}')
                )
                for i in range(batch_size)
            ]

            start = time.perf_counter()
            try:
                results = await client.batch_evaluate(evaluations)
                latency_ms = (time.perf_counter() - start) * 1000
                metrics.record_latency(latency_ms)

                # Contar sucessos e erros no batch
                for result in results:
                    if 'error' in result:
                        metrics.record_error()
                    else:
                        metrics.record_success()
            except Exception:
                for _ in range(batch_size):
                    metrics.record_error()

        metrics.end_time = time.perf_counter()
        await client.close()

        summary = metrics.summary()
        print(f"\nBatch Evaluation Load Test Summary: {summary}")

        # Assertions
        assert metrics.error_rate < 0.1, "Taxa de erro muito alta"

    @pytest.mark.asyncio
    async def test_mixed_policy_batch(self, load_test_config, mock_metrics):
        """Testa batch com múltiplas políticas diferentes."""
        client = OPAClient(load_test_config, metrics=mock_metrics)
        await client.initialize()

        metrics = OPALoadTestMetrics()
        num_batches = 10

        policies = [
            'neuralhive/orchestrator/resource_limits',
            'neuralhive/orchestrator/sla_enforcement',
            'neuralhive/orchestrator/feature_flags',
            'neuralhive/orchestrator/security_constraints'
        ]

        metrics.start_time = time.perf_counter()

        for batch_idx in range(num_batches):
            evaluations = []
            for i, policy in enumerate(policies):
                if policy == 'neuralhive/orchestrator/resource_limits':
                    input_data = generate_resource_limits_input(f'mixed-{batch_idx}-{i}')
                elif policy == 'neuralhive/orchestrator/sla_enforcement':
                    input_data = generate_sla_enforcement_input(f'mixed-{batch_idx}-{i}')
                else:
                    input_data = {
                        'input': {
                            'resource': {'ticket_id': f'mixed-{batch_idx}-{i}'},
                            'context': {'current_time': int(datetime.now().timestamp() * 1000)}
                        }
                    }
                evaluations.append((policy, input_data))

            start = time.perf_counter()
            try:
                results = await client.batch_evaluate(evaluations)
                latency_ms = (time.perf_counter() - start) * 1000
                metrics.record_latency(latency_ms)

                for result in results:
                    if 'error' in result:
                        metrics.record_error()
                    else:
                        metrics.record_success()
            except Exception:
                for _ in range(len(policies)):
                    metrics.record_error()

        metrics.end_time = time.perf_counter()
        await client.close()

        summary = metrics.summary()
        print(f"\nMixed Policy Batch Load Test Summary: {summary}")


class TestOPALoadCircuitBreaker:
    """Testes de carga para circuit breaker behavior."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_under_failures(self, load_test_config, mock_metrics):
        """Testa comportamento do circuit breaker sob falhas."""
        # Configurar para abrir circuit breaker rapidamente
        load_test_config.opa_circuit_breaker_failure_threshold = 3
        load_test_config.opa_circuit_breaker_reset_timeout = 2

        client = OPAClient(load_test_config, metrics=mock_metrics)
        await client.initialize()

        metrics = OPALoadTestMetrics()

        # Simular falhas forçando timeout muito baixo temporariamente
        original_timeout = client.timeout
        client.timeout = aiohttp.ClientTimeout(total=0.001)  # 1ms - vai falhar

        metrics.start_time = time.perf_counter()

        for i in range(20):
            input_data = generate_resource_limits_input(f'cb-test-{i}')
            try:
                await client.evaluate_policy(
                    'neuralhive/orchestrator/resource_limits',
                    input_data
                )
                metrics.record_success()
            except Exception as e:
                if 'Circuit breaker' in str(e):
                    metrics.record_circuit_breaker_rejection()
                else:
                    metrics.record_error()

        metrics.end_time = time.perf_counter()

        # Restaurar timeout
        client.timeout = original_timeout

        cb_state = client.get_circuit_breaker_state()
        await client.close()

        summary = metrics.summary()
        print(f"\nCircuit Breaker Load Test Summary: {summary}")
        print(f"Circuit Breaker State: {cb_state}")

        # Circuit breaker deve ter aberto após falhas
        assert cb_state['state'] in ('open', 'half_open'), "Circuit breaker deveria estar aberto ou half_open"


class TestOPALoadStress:
    """Testes de stress para limites do sistema."""

    @pytest.mark.asyncio
    async def test_high_concurrency_stress(self, load_test_config, mock_metrics):
        """Testa sob alta concorrência para encontrar limites."""
        client = OPAClient(load_test_config, metrics=mock_metrics)
        await client.initialize()

        metrics = OPALoadTestMetrics()
        num_requests = 500
        concurrency = 50
        policy_path = 'neuralhive/orchestrator/resource_limits'

        semaphore = asyncio.Semaphore(concurrency)

        async def evaluate_with_semaphore(idx: int):
            async with semaphore:
                input_data = generate_resource_limits_input(f'stress-{idx}')
                start = time.perf_counter()
                try:
                    await client.evaluate_policy(policy_path, input_data)
                    latency_ms = (time.perf_counter() - start) * 1000
                    metrics.record_latency(latency_ms)
                    metrics.record_success()
                except Exception:
                    metrics.record_error()

        metrics.start_time = time.perf_counter()

        tasks = [evaluate_with_semaphore(i) for i in range(num_requests)]
        await asyncio.gather(*tasks)

        metrics.end_time = time.perf_counter()
        await client.close()

        summary = metrics.summary()
        print(f"\nHigh Concurrency Stress Test Summary: {summary}")

        # Assertions mais relaxadas para stress test
        assert metrics.error_rate < 0.2, "Taxa de erro muito alta em stress test"

    @pytest.mark.asyncio
    async def test_sustained_load(self, load_test_config, mock_metrics):
        """Testa carga sustentada por período estendido."""
        client = OPAClient(load_test_config, metrics=mock_metrics)
        await client.initialize()

        metrics = OPALoadTestMetrics()
        duration_seconds = 10  # 10 segundos de carga sustentada
        requests_per_second = 20
        policy_path = 'neuralhive/orchestrator/resource_limits'

        metrics.start_time = time.perf_counter()
        request_idx = 0

        while (time.perf_counter() - metrics.start_time) < duration_seconds:
            batch_start = time.perf_counter()

            # Executar batch de requests
            tasks = []
            for _ in range(requests_per_second):
                input_data = generate_resource_limits_input(f'sustained-{request_idx}')
                request_idx += 1

                async def evaluate_once(data):
                    start = time.perf_counter()
                    try:
                        await client.evaluate_policy(policy_path, data)
                        latency_ms = (time.perf_counter() - start) * 1000
                        metrics.record_latency(latency_ms)
                        metrics.record_success()
                    except Exception:
                        metrics.record_error()

                tasks.append(evaluate_once(input_data))

            await asyncio.gather(*tasks)

            # Ajustar para manter rate
            elapsed = time.perf_counter() - batch_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

        metrics.end_time = time.perf_counter()
        await client.close()

        summary = metrics.summary()
        print(f"\nSustained Load Test Summary: {summary}")

        # Verificar que throughput está próximo do target
        expected_requests = duration_seconds * requests_per_second
        actual_throughput = metrics.throughput

        assert actual_throughput > requests_per_second * 0.8, "Throughput muito abaixo do target"
        assert metrics.error_rate < 0.1, "Taxa de erro muito alta em carga sustentada"


# Testes com servidor OPA real
@pytest.mark.skipif(not REAL_OPA_LOAD, reason="RUN_OPA_LOAD_TESTS not enabled")
class TestOPARealServerLoad:
    """Testes de carga com servidor OPA real."""

    @pytest.mark.asyncio
    async def test_real_server_throughput(self, load_test_config, mock_metrics):
        """Testa throughput real contra servidor OPA."""
        client = OPAClient(load_test_config, metrics=mock_metrics)
        await client.initialize()

        # Verificar saúde primeiro
        healthy = await client.health_check()
        if not healthy:
            pytest.skip("Servidor OPA não está saudável")

        metrics = OPALoadTestMetrics()
        num_requests = 100
        policy_path = 'neuralhive/orchestrator/resource_limits'

        metrics.start_time = time.perf_counter()

        for i in range(num_requests):
            input_data = generate_resource_limits_input(f'real-{i}')
            start = time.perf_counter()

            try:
                result = await client.evaluate_policy(policy_path, input_data)
                latency_ms = (time.perf_counter() - start) * 1000
                metrics.record_latency(latency_ms)

                if 'result' in result:
                    metrics.record_success()
                else:
                    metrics.record_error()
            except Exception:
                metrics.record_error()

        metrics.end_time = time.perf_counter()
        await client.close()

        summary = metrics.summary()
        print(f"\nReal Server Load Test Summary: {summary}")

        # Métricas devem ser razoáveis
        assert metrics.throughput > 5, "Throughput muito baixo"
        assert metrics.p99_latency < 1000, "P99 latency muito alta"


# Import necessário para test_circuit_breaker_under_failures
try:
    import aiohttp
except ImportError:
    aiohttp = None
