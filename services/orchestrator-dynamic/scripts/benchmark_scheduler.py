#!/usr/bin/env python3
"""
Benchmark Script para IntelligentScheduler.

Executa benchmarks de performance e gera relatórios com métricas detalhadas.

Uso:
    python scripts/benchmark_scheduler.py --iterations 10 --concurrency 100
    python scripts/benchmark_scheduler.py --output results.json
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from unittest.mock import AsyncMock, MagicMock

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from scheduler.intelligent_scheduler import IntelligentScheduler
from scheduler.priority_calculator import PriorityCalculator
from scheduler.resource_allocator import ResourceAllocator
from config.settings import OrchestratorSettings
from observability.metrics import OrchestratorMetrics


@dataclass
class BenchmarkResult:
    """Resultado de uma iteração de benchmark."""
    iteration: int
    tickets_count: int
    duration_seconds: float
    throughput: float
    latency_mean_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_min_ms: float
    latency_max_ms: float
    success_count: int
    fallback_count: int
    error_count: int
    cache_hit_rate: float


@dataclass
class BenchmarkSummary:
    """Resumo consolidado dos benchmarks."""
    total_iterations: int
    total_tickets: int
    total_duration_seconds: float
    avg_throughput: float
    throughput_stdev: float
    avg_latency_p95_ms: float
    avg_latency_p99_ms: float
    avg_success_rate: float
    avg_cache_hit_rate: float
    baseline_comparison: Optional[Dict[str, Any]] = None
    meets_slos: bool = True
    slo_violations: List[str] = field(default_factory=list)


# SLOs de baseline
BASELINE_SLOS = {
    'latency_p95_ms': 200,
    'latency_p99_ms': 500,
    'throughput_min': 100,
    'success_rate_min': 0.99,
    'cache_hit_rate_min': 0.80,
}


def create_mock_config() -> OrchestratorSettings:
    """Cria configuração mock para benchmark."""
    config = MagicMock(spec=OrchestratorSettings)
    config.service_registry_cache_ttl_seconds = 60
    config.service_registry_timeout_seconds = 5
    config.scheduler_priority_weights = {'risk': 0.4, 'qos': 0.3, 'sla': 0.3}
    config.enable_ml_enhanced_scheduling = False
    config.CIRCUIT_BREAKER_ENABLED = False
    config.service_name = 'orchestrator-dynamic'
    return config


def create_mock_metrics() -> OrchestratorMetrics:
    """Cria metrics mock para benchmark."""
    metrics = MagicMock(spec=OrchestratorMetrics)
    metrics.cache_hit_count = 0

    def track_cache_hit():
        metrics.cache_hit_count += 1

    metrics.record_cache_hit = track_cache_hit
    return metrics


def create_sample_workers(count: int = 10) -> List[Dict[str, Any]]:
    """Cria lista de workers mock."""
    return [
        {
            'agent_id': f'worker-{i:03d}',
            'agent_type': 'worker-agent',
            'score': 0.9 - (i * 0.03),
            'capabilities': ['python', 'data-processing'],
            'status': 'HEALTHY',
        }
        for i in range(count)
    ]


def create_mock_allocator(
    workers: List[Dict],
    latency_ms: float = 10
) -> AsyncMock:
    """Cria ResourceAllocator mock com latência simulada."""
    allocator = AsyncMock(spec=ResourceAllocator)

    async def mock_discover(*args, **kwargs):
        await asyncio.sleep(latency_ms / 1000)
        return workers

    allocator.discover_workers = mock_discover
    allocator.select_best_worker = MagicMock(
        side_effect=lambda workers, **kwargs: workers[0] if workers else None
    )
    return allocator


def generate_tickets(count: int, patterns: int = 5) -> List[Dict[str, Any]]:
    """Gera tickets de teste."""
    capability_options = [
        ['python', 'data-processing'],
        ['python', 'ml-inference'],
        ['java', 'api-gateway'],
        ['nodejs', 'web-frontend'],
        ['go', 'microservice'],
    ]
    risk_bands = ['low', 'normal', 'high', 'critical']

    tickets = []
    for i in range(count):
        tickets.append({
            'ticket_id': f'bench-{i:06d}',
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
            'required_capabilities': capability_options[i % patterns],
            'namespace': 'default',
            'security_level': 'standard',
            'estimated_duration_ms': 1000,
            'created_at': datetime.utcnow().isoformat()
        })
    return tickets


async def run_benchmark_iteration(
    scheduler: IntelligentScheduler,
    tickets: List[Dict],
    concurrency: int,
    metrics: MagicMock
) -> BenchmarkResult:
    """Executa uma iteração de benchmark."""
    latencies = []
    success_count = 0
    fallback_count = 0
    error_count = 0
    metrics.cache_hit_count = 0

    async def process_ticket(ticket: Dict) -> tuple:
        start = time.time()
        try:
            result = await scheduler.schedule_ticket(ticket)
            latency_ms = (time.time() - start) * 1000
            method = result.get('allocation_metadata', {}).get('allocation_method')
            return latency_ms, method, None
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            return latency_ms, None, str(e)

    start_time = time.time()

    # Processar em batches para controlar concorrência
    batch_size = concurrency
    for i in range(0, len(tickets), batch_size):
        batch = tickets[i:i + batch_size]
        results = await asyncio.gather(*[process_ticket(t) for t in batch])

        for latency_ms, method, error in results:
            latencies.append(latency_ms)
            if error:
                error_count += 1
            elif method == 'intelligent_scheduler':
                success_count += 1
            else:
                fallback_count += 1

    duration = time.time() - start_time
    sorted_latencies = sorted(latencies)

    return BenchmarkResult(
        iteration=0,
        tickets_count=len(tickets),
        duration_seconds=duration,
        throughput=len(tickets) / duration if duration > 0 else 0,
        latency_mean_ms=statistics.mean(latencies) if latencies else 0,
        latency_p50_ms=sorted_latencies[int(len(sorted_latencies) * 0.50)] if latencies else 0,
        latency_p95_ms=sorted_latencies[int(len(sorted_latencies) * 0.95)] if latencies else 0,
        latency_p99_ms=sorted_latencies[min(int(len(sorted_latencies) * 0.99), len(sorted_latencies) - 1)] if latencies else 0,
        latency_min_ms=min(latencies) if latencies else 0,
        latency_max_ms=max(latencies) if latencies else 0,
        success_count=success_count,
        fallback_count=fallback_count,
        error_count=error_count,
        cache_hit_rate=metrics.cache_hit_count / len(tickets) if tickets else 0
    )


def check_slos(summary: BenchmarkSummary) -> tuple:
    """Verifica se os SLOs foram atendidos."""
    violations = []

    if summary.avg_latency_p95_ms > BASELINE_SLOS['latency_p95_ms']:
        violations.append(
            f"Latência P95 ({summary.avg_latency_p95_ms:.2f}ms) > "
            f"SLO ({BASELINE_SLOS['latency_p95_ms']}ms)"
        )

    if summary.avg_latency_p99_ms > BASELINE_SLOS['latency_p99_ms']:
        violations.append(
            f"Latência P99 ({summary.avg_latency_p99_ms:.2f}ms) > "
            f"SLO ({BASELINE_SLOS['latency_p99_ms']}ms)"
        )

    if summary.avg_throughput < BASELINE_SLOS['throughput_min']:
        violations.append(
            f"Throughput ({summary.avg_throughput:.2f} t/s) < "
            f"SLO ({BASELINE_SLOS['throughput_min']} t/s)"
        )

    if summary.avg_success_rate < BASELINE_SLOS['success_rate_min']:
        violations.append(
            f"Taxa de sucesso ({summary.avg_success_rate*100:.1f}%) < "
            f"SLO ({BASELINE_SLOS['success_rate_min']*100:.1f}%)"
        )

    if summary.avg_cache_hit_rate < BASELINE_SLOS['cache_hit_rate_min']:
        violations.append(
            f"Cache hit rate ({summary.avg_cache_hit_rate*100:.1f}%) < "
            f"SLO ({BASELINE_SLOS['cache_hit_rate_min']*100:.1f}%)"
        )

    return len(violations) == 0, violations


async def run_benchmarks(
    iterations: int,
    tickets_per_iteration: int,
    concurrency: int,
    discovery_latency_ms: float
) -> tuple:
    """Executa múltiplas iterações de benchmark."""
    config = create_mock_config()
    workers = create_sample_workers()
    results = []

    for i in range(iterations):
        print(f'Executando iteração {i + 1}/{iterations}...')

        # Criar novos mocks para cada iteração (cache limpo)
        metrics = create_mock_metrics()
        priority_calc = PriorityCalculator(config)
        allocator = create_mock_allocator(workers, discovery_latency_ms)

        scheduler = IntelligentScheduler(
            config=config,
            metrics=metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        tickets = generate_tickets(tickets_per_iteration)
        result = await run_benchmark_iteration(scheduler, tickets, concurrency, metrics)
        result.iteration = i + 1
        results.append(result)

    # Calcular resumo
    throughputs = [r.throughput for r in results]
    latencies_p95 = [r.latency_p95_ms for r in results]
    latencies_p99 = [r.latency_p99_ms for r in results]
    success_rates = [r.success_count / r.tickets_count for r in results]
    cache_hit_rates = [r.cache_hit_rate for r in results]

    summary = BenchmarkSummary(
        total_iterations=iterations,
        total_tickets=sum(r.tickets_count for r in results),
        total_duration_seconds=sum(r.duration_seconds for r in results),
        avg_throughput=statistics.mean(throughputs),
        throughput_stdev=statistics.stdev(throughputs) if len(throughputs) > 1 else 0,
        avg_latency_p95_ms=statistics.mean(latencies_p95),
        avg_latency_p99_ms=statistics.mean(latencies_p99),
        avg_success_rate=statistics.mean(success_rates),
        avg_cache_hit_rate=statistics.mean(cache_hit_rates)
    )

    # Verificar SLOs
    meets_slos, violations = check_slos(summary)
    summary.meets_slos = meets_slos
    summary.slo_violations = violations

    return results, summary


def print_report(results: List[BenchmarkResult], summary: BenchmarkSummary):
    """Imprime relatório de benchmark."""
    print('\n' + '=' * 60)
    print('RELATÓRIO DE BENCHMARK - IntelligentScheduler')
    print('=' * 60)

    print('\n--- Configuração ---')
    print(f'  Iterações: {summary.total_iterations}')
    print(f'  Total de tickets: {summary.total_tickets}')
    print(f'  Duração total: {summary.total_duration_seconds:.2f}s')

    print('\n--- Resultados por Iteração ---')
    print(f'  {"Iter":<6} {"Tickets":<10} {"Throughput":<15} {"P95 (ms)":<12} {"P99 (ms)":<12} {"Cache Hit":<12}')
    print('  ' + '-' * 67)

    for r in results:
        print(f'  {r.iteration:<6} {r.tickets_count:<10} {r.throughput:<15.2f} '
              f'{r.latency_p95_ms:<12.2f} {r.latency_p99_ms:<12.2f} {r.cache_hit_rate*100:<12.1f}%')

    print('\n--- Resumo Consolidado ---')
    print(f'  Throughput médio: {summary.avg_throughput:.2f} t/s (±{summary.throughput_stdev:.2f})')
    print(f'  Latência P95 média: {summary.avg_latency_p95_ms:.2f}ms')
    print(f'  Latência P99 média: {summary.avg_latency_p99_ms:.2f}ms')
    print(f'  Taxa de sucesso média: {summary.avg_success_rate*100:.1f}%')
    print(f'  Cache hit rate médio: {summary.avg_cache_hit_rate*100:.1f}%')

    print('\n--- Validação de SLOs ---')
    print(f'  SLOs atendidos: {"✅ SIM" if summary.meets_slos else "❌ NÃO"}')

    if summary.slo_violations:
        print('  Violações:')
        for v in summary.slo_violations:
            print(f'    - {v}')

    print('\n--- Baselines de Referência ---')
    for slo, value in BASELINE_SLOS.items():
        status = '✓' if summary.meets_slos else '?'
        print(f'  {status} {slo}: {value}')

    print('\n' + '=' * 60)


def save_results(
    results: List[BenchmarkResult],
    summary: BenchmarkSummary,
    output_path: str
):
    """Salva resultados em arquivo JSON."""
    data = {
        'timestamp': datetime.utcnow().isoformat(),
        'baselines': BASELINE_SLOS,
        'summary': asdict(summary),
        'iterations': [asdict(r) for r in results]
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f'\nResultados salvos em: {output_path}')


def main():
    parser = argparse.ArgumentParser(
        description='Benchmark do IntelligentScheduler'
    )
    parser.add_argument(
        '--iterations', '-i',
        type=int,
        default=5,
        help='Número de iterações (default: 5)'
    )
    parser.add_argument(
        '--tickets', '-t',
        type=int,
        default=500,
        help='Tickets por iteração (default: 500)'
    )
    parser.add_argument(
        '--concurrency', '-c',
        type=int,
        default=50,
        help='Concorrência (default: 50)'
    )
    parser.add_argument(
        '--discovery-latency', '-d',
        type=float,
        default=10.0,
        help='Latência de discovery simulada em ms (default: 10)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Arquivo de saída JSON'
    )

    args = parser.parse_args()

    print(f'Iniciando benchmark...')
    print(f'  Iterações: {args.iterations}')
    print(f'  Tickets/iteração: {args.tickets}')
    print(f'  Concorrência: {args.concurrency}')
    print(f'  Latência discovery: {args.discovery_latency}ms')

    results, summary = asyncio.run(
        run_benchmarks(
            iterations=args.iterations,
            tickets_per_iteration=args.tickets,
            concurrency=args.concurrency,
            discovery_latency_ms=args.discovery_latency
        )
    )

    print_report(results, summary)

    if args.output:
        save_results(results, summary, args.output)

    # Exit code baseado em SLOs
    sys.exit(0 if summary.meets_slos else 1)


if __name__ == '__main__':
    main()
