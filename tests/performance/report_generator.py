"""
Gerador de relatorios de performance para testes de carga do Fluxo C.

Cria relatorios detalhados em markdown com analise de throughput,
latencia, autoscaling, circuit breakers e bottlenecks.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tests.performance.bottleneck_analyzer import BottleneckAnalyzer
from tests.performance.slo_validator import SLOValidator, LoadTestMetrics

logger = logging.getLogger(__name__)


@dataclass
class ScalingEventSummary:
    """Resumo de evento de scaling."""
    timestamp: str
    event_type: str
    from_replicas: int
    to_replicas: int
    reason: Optional[str] = None


@dataclass
class StepLatencyStats:
    """Estatisticas de latencia por step."""
    step: str
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    p99_ms: Optional[float] = None
    mean_ms: Optional[float] = None
    count: int = 0


@dataclass
class PerformanceTestResults:
    """Resultados consolidados do teste de performance."""
    # Metadados
    test_name: str
    test_date: datetime
    test_duration_seconds: float
    total_workflows: int
    concurrent_workflows: int

    # Metricas principais
    metrics: LoadTestMetrics

    # Latencia por step
    step_latencies: Dict[str, StepLatencyStats] = field(default_factory=dict)

    # Autoscaling
    scaling_events: List[ScalingEventSummary] = field(default_factory=list)
    min_replicas_observed: int = 2
    max_replicas_observed: int = 2

    # Circuit Breakers
    circuit_breaker_trips: Dict[str, int] = field(default_factory=dict)
    circuit_breaker_states: Dict[str, str] = field(default_factory=dict)

    # Evictions/OOMs
    eviction_count: int = 0
    oom_count: int = 0

    # Recursos
    peak_cpu_percent: Optional[float] = None
    peak_memory_percent: Optional[float] = None
    avg_cpu_percent: Optional[float] = None
    avg_memory_percent: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'test_name': self.test_name,
            'test_date': self.test_date.isoformat(),
            'test_duration_seconds': self.test_duration_seconds,
            'total_workflows': self.total_workflows,
            'concurrent_workflows': self.concurrent_workflows,
            'metrics': {
                'latency_p50_seconds': self.metrics.latency_p50_seconds,
                'latency_p95_seconds': self.metrics.latency_p95_seconds,
                'latency_p99_seconds': self.metrics.latency_p99_seconds,
                'success_rate': self.metrics.success_rate,
                'throughput_workflows_per_second': self.metrics.workflows_per_second,
                'throughput_tickets_per_second': self.metrics.tickets_per_second,
            },
            'scaling': {
                'min_replicas': self.min_replicas_observed,
                'max_replicas': self.max_replicas_observed,
                'events_count': len(self.scaling_events),
            },
            'circuit_breakers': self.circuit_breaker_states,
            'evictions': self.eviction_count,
            'ooms': self.oom_count,
            'resources': {
                'peak_cpu_percent': self.peak_cpu_percent,
                'peak_memory_percent': self.peak_memory_percent,
            },
        }


class PerformanceReportGenerator:
    """Gerador de relatorios de performance."""

    def __init__(
        self,
        results: PerformanceTestResults,
        bottleneck_analyzer: Optional[BottleneckAnalyzer] = None,
        slo_validator: Optional[SLOValidator] = None,
    ):
        """
        Inicializa o gerador.

        Args:
            results: Resultados do teste
            bottleneck_analyzer: Analisador de bottlenecks (opcional)
            slo_validator: Validador de SLOs (opcional)
        """
        self.results = results
        self.bottleneck_analyzer = bottleneck_analyzer or BottleneckAnalyzer()
        self.slo_validator = slo_validator or SLOValidator()

    def generate_executive_summary(self) -> str:
        """Gera resumo executivo."""
        lines = ['## Resumo Executivo', '']

        # Validar SLOs
        self.slo_validator.validate_all(self.results.metrics)
        slo_passed = self.slo_validator.all_passed()

        # Status geral
        status = '✅ PASS' if slo_passed else '❌ FAIL'
        lines.append(f'**Status:** {status}')
        lines.append(f'**Data:** {self.results.test_date.strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append(f'**Duracao:** {self.results.test_duration_seconds/60:.1f} minutos')
        lines.append(f'**Total Workflows:** {self.results.total_workflows}')
        lines.append('')

        # Metricas chave
        lines.append('### Metricas Chave')
        lines.append('')

        metrics = self.results.metrics
        throughput_emoji = '✅' if metrics.tickets_per_second >= 10 else '❌'
        latency_emoji = '✅' if (metrics.latency_p95_seconds or 0) < 14400 else '❌'
        success_emoji = '✅' if metrics.success_rate >= 0.99 else '❌'

        lines.append(f'- {throughput_emoji} **Throughput:** {metrics.tickets_per_second:.2f} tickets/s (target: >= 10)')

        if metrics.latency_p95_seconds:
            lines.append(f'- {latency_emoji} **Latencia P95:** {metrics.latency_p95_seconds/3600:.2f}h (target: < 4h)')

        lines.append(f'- {success_emoji} **Taxa de Sucesso:** {metrics.success_rate*100:.2f}% (target: >= 99%)')
        lines.append(f'- **Autoscaling:** {self.results.min_replicas_observed} -> {self.results.max_replicas_observed} replicas')
        lines.append('')

        return '\n'.join(lines)

    def generate_throughput_analysis(self) -> str:
        """Gera analise de throughput."""
        lines = ['## Analise de Throughput', '']

        metrics = self.results.metrics

        lines.append('| Metrica | Valor | Target | Status |')
        lines.append('|---------|-------|--------|--------|')

        # Workflows/s
        wps = metrics.workflows_per_second
        lines.append(f'| Workflows/s | {wps:.2f} | - | - |')

        # Tickets/s
        tps = metrics.tickets_per_second
        tps_status = '✅' if tps >= 10 else '❌'
        lines.append(f'| Tickets/s | {tps:.2f} | >= 10 | {tps_status} |')

        # Totais
        lines.append(f'| Total Workflows | {metrics.total_workflows} | - | - |')
        lines.append(f'| Total Tickets | {metrics.total_tickets} | - | - |')
        lines.append(f'| Bem-sucedidos | {metrics.successful_workflows} | - | - |')
        lines.append(f'| Falhados | {metrics.failed_workflows} | - | - |')

        lines.append('')
        return '\n'.join(lines)

    def generate_latency_analysis(self) -> str:
        """Gera analise de latencia."""
        lines = ['## Analise de Latencia', '']

        metrics = self.results.metrics

        lines.append('### Latencia End-to-End')
        lines.append('')
        lines.append('| Percentil | Valor | Target | Status |')
        lines.append('|-----------|-------|--------|--------|')

        # P50
        if metrics.latency_p50_seconds:
            lines.append(f'| P50 | {metrics.latency_p50_seconds/3600:.2f}h | - | - |')

        # P95
        if metrics.latency_p95_seconds:
            p95_status = '✅' if metrics.latency_p95_seconds < 14400 else '❌'
            lines.append(f'| P95 | {metrics.latency_p95_seconds/3600:.2f}h | < 4h | {p95_status} |')

        # P99
        if metrics.latency_p99_seconds:
            p99_status = '✅' if metrics.latency_p99_seconds < 21600 else '❌'
            lines.append(f'| P99 | {metrics.latency_p99_seconds/3600:.2f}h | < 6h | {p99_status} |')

        lines.append('')

        # Latencia por step
        if self.results.step_latencies:
            lines.append('### Latencia por Step')
            lines.append('')
            lines.append('| Step | P50 | P95 | P99 |')
            lines.append('|------|-----|-----|-----|')

            for step in ['C1', 'C2', 'C3', 'C4', 'C5', 'C6']:
                if step in self.results.step_latencies:
                    stats = self.results.step_latencies[step]
                    p50 = f'{stats.p50_ms:.0f}ms' if stats.p50_ms else 'N/A'
                    p95 = f'{stats.p95_ms:.0f}ms' if stats.p95_ms else 'N/A'
                    p99 = f'{stats.p99_ms:.0f}ms' if stats.p99_ms else 'N/A'
                    lines.append(f'| {step} | {p50} | {p95} | {p99} |')

            lines.append('')

        return '\n'.join(lines)

    def generate_autoscaling_analysis(self) -> str:
        """Gera analise de autoscaling."""
        lines = ['## Comportamento de Autoscaling', '']

        lines.append(f'- **Replicas Iniciais:** {self.results.min_replicas_observed}')
        lines.append(f'- **Replicas Maximas Observadas:** {self.results.max_replicas_observed}')
        lines.append(f'- **Eventos de Scaling:** {len(self.results.scaling_events)}')
        lines.append('')

        if self.results.scaling_events:
            lines.append('### Eventos de Scaling')
            lines.append('')
            lines.append('| Timestamp | Tipo | De | Para | Razao |')
            lines.append('|-----------|------|----|----|-------|')

            for event in self.results.scaling_events[:10]:  # Limitar a 10 eventos
                reason = event.reason or '-'
                lines.append(
                    f'| {event.timestamp} | {event.event_type} | '
                    f'{event.from_replicas} | {event.to_replicas} | {reason} |'
                )

            lines.append('')

        return '\n'.join(lines)

    def generate_circuit_breaker_analysis(self) -> str:
        """Gera analise de circuit breakers."""
        lines = ['## Analise de Circuit Breakers', '']

        if not self.results.circuit_breaker_states and not self.results.circuit_breaker_trips:
            lines.append('Nenhum dado de circuit breaker disponivel.')
            lines.append('')
            return '\n'.join(lines)

        lines.append('| Componente | Estado Final | Trips |')
        lines.append('|------------|--------------|-------|')

        components = set(
            list(self.results.circuit_breaker_states.keys()) +
            list(self.results.circuit_breaker_trips.keys())
        )

        for comp in sorted(components):
            state = self.results.circuit_breaker_states.get(comp, 'N/A')
            trips = self.results.circuit_breaker_trips.get(comp, 0)
            state_emoji = '✅' if state == 'closed' else ('⚠️' if state == 'half_open' else '❌')
            lines.append(f'| {comp} | {state_emoji} {state} | {trips} |')

        lines.append('')
        return '\n'.join(lines)

    def generate_resource_analysis(self) -> str:
        """Gera analise de recursos."""
        lines = ['## Utilizacao de Recursos', '']

        lines.append('| Metrica | Pico | Media |')
        lines.append('|---------|------|-------|')

        # CPU
        peak_cpu = f'{self.results.peak_cpu_percent:.1f}%' if self.results.peak_cpu_percent else 'N/A'
        avg_cpu = f'{self.results.avg_cpu_percent:.1f}%' if self.results.avg_cpu_percent else 'N/A'
        lines.append(f'| CPU | {peak_cpu} | {avg_cpu} |')

        # Memoria
        peak_mem = f'{self.results.peak_memory_percent:.1f}%' if self.results.peak_memory_percent else 'N/A'
        avg_mem = f'{self.results.avg_memory_percent:.1f}%' if self.results.avg_memory_percent else 'N/A'
        lines.append(f'| Memoria | {peak_mem} | {avg_mem} |')

        lines.append('')

        # Evictions/OOMs
        if self.results.eviction_count > 0 or self.results.oom_count > 0:
            lines.append('### Incidentes')
            lines.append('')
            if self.results.eviction_count > 0:
                lines.append(f'- ❌ **Evictions:** {self.results.eviction_count}')
            if self.results.oom_count > 0:
                lines.append(f'- ❌ **OOM Kills:** {self.results.oom_count}')
            lines.append('')

        return '\n'.join(lines)

    def generate_recommendations(self) -> str:
        """Gera recomendacoes baseadas nos resultados."""
        lines = ['## Recomendacoes', '']

        recommendations = []

        metrics = self.results.metrics

        # Throughput baixo
        if metrics.tickets_per_second < 10:
            recommendations.append({
                'area': 'Throughput',
                'issue': f'Throughput de {metrics.tickets_per_second:.2f} tickets/s abaixo do target',
                'action': 'Aumentar maxParallelTickets ou adicionar mais workers',
            })

        # Latencia alta
        if metrics.latency_p95_seconds and metrics.latency_p95_seconds >= 14400:
            recommendations.append({
                'area': 'Latencia',
                'issue': f'Latencia P95 de {metrics.latency_p95_seconds/3600:.2f}h acima do SLO',
                'action': 'Identificar step mais lento e otimizar; considerar paralelizacao',
            })

        # Taxa de sucesso baixa
        if metrics.success_rate < 0.99:
            recommendations.append({
                'area': 'Confiabilidade',
                'issue': f'Taxa de sucesso de {metrics.success_rate*100:.2f}% abaixo do target',
                'action': 'Investigar falhas; aumentar retries ou timeout',
            })

        # CPU alta
        if self.results.peak_cpu_percent and self.results.peak_cpu_percent > 80:
            recommendations.append({
                'area': 'CPU',
                'issue': f'Pico de CPU de {self.results.peak_cpu_percent:.1f}%',
                'action': 'Aumentar CPU limits de 1600m para 2000m ou adicionar replicas',
            })

        # Memoria alta
        if self.results.peak_memory_percent and self.results.peak_memory_percent > 80:
            recommendations.append({
                'area': 'Memoria',
                'issue': f'Pico de memoria de {self.results.peak_memory_percent:.1f}%',
                'action': 'Aumentar memory limits de 3Gi para 4Gi',
            })

        # Evictions/OOMs
        if self.results.eviction_count > 0:
            recommendations.append({
                'area': 'Estabilidade',
                'issue': f'{self.results.eviction_count} pods evicted durante teste',
                'action': 'Revisar resource requests e PriorityClass',
            })

        if self.results.oom_count > 0:
            recommendations.append({
                'area': 'Estabilidade',
                'issue': f'{self.results.oom_count} OOM kills durante teste',
                'action': 'Aumentar memory limits imediatamente',
            })

        # Circuit breakers
        for comp, state in self.results.circuit_breaker_states.items():
            if state in ('open', 'half_open'):
                recommendations.append({
                    'area': f'Circuit Breaker ({comp})',
                    'issue': f'Circuit breaker {comp} em estado {state}',
                    'action': f'Verificar disponibilidade e performance do {comp}',
                })

        if not recommendations:
            lines.append('Nenhuma recomendacao critica. Sistema operando dentro dos parametros.')
        else:
            for i, rec in enumerate(recommendations, 1):
                lines.append(f'{i}. **{rec["area"]}**')
                lines.append(f'   - Problema: {rec["issue"]}')
                lines.append(f'   - Acao: {rec["action"]}')
                lines.append('')

        return '\n'.join(lines)

    def generate_full_report(self) -> str:
        """
        Gera relatorio completo de performance.

        Returns:
            String com relatorio em formato markdown
        """
        sections = [
            f'# Relatorio de Teste de Carga - Fluxo C',
            f'**Teste:** {self.results.test_name}',
            f'**Data:** {self.results.test_date.strftime("%Y-%m-%d %H:%M:%S")}',
            '',
            self.generate_executive_summary(),
            self.generate_throughput_analysis(),
            self.generate_latency_analysis(),
            self.generate_autoscaling_analysis(),
            self.generate_circuit_breaker_analysis(),
            self.generate_resource_analysis(),
        ]

        # Analise de bottlenecks
        if self.bottleneck_analyzer.bottlenecks:
            sections.append(self.bottleneck_analyzer.generate_report())

        # SLO compliance
        sections.append(self.slo_validator.generate_markdown_report())

        # Recomendacoes
        sections.append(self.generate_recommendations())

        return '\n'.join(sections)

    def save_report(
        self,
        output_path: str,
        format: str = 'markdown',
    ) -> None:
        """
        Salva relatorio em arquivo.

        Args:
            output_path: Caminho do arquivo de saida
            format: Formato ('markdown' ou 'json')
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == 'json':
            data = {
                'results': self.results.to_dict(),
                'slo_report': self.slo_validator.generate_report(),
                'bottleneck_summary': self.bottleneck_analyzer.generate_summary(),
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            report = self.generate_full_report()
            with open(path, 'w', encoding='utf-8') as f:
                f.write(report)

        logger.info(f'Relatorio salvo em {path}')


def generate_performance_report(
    results: PerformanceTestResults,
    output_path: Optional[str] = None,
) -> str:
    """
    Funcao utilitaria para gerar relatorio rapidamente.

    Args:
        results: Resultados do teste
        output_path: Caminho para salvar (opcional)

    Returns:
        Relatorio em formato markdown
    """
    generator = PerformanceReportGenerator(results)
    report = generator.generate_full_report()

    if output_path:
        generator.save_report(output_path)

    return report
