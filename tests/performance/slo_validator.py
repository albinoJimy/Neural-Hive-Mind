"""
Validador de SLOs para testes de carga do Fluxo C.

Valida conformidade com SLOs definidos para latencia, taxa de sucesso,
throughput e disponibilidade.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SLOStatus(str, Enum):
    """Status de conformidade com SLO."""
    PASS = 'pass'
    FAIL = 'fail'
    WARN = 'warn'
    NOT_MEASURED = 'not_measured'


@dataclass
class SLOTarget:
    """Definicao de um SLO target."""
    name: str
    metric: str
    target_value: float
    comparison: str  # 'lt', 'lte', 'gt', 'gte', 'eq'
    unit: str
    description: str
    warning_threshold: Optional[float] = None  # Threshold para warning (mais conservador)


@dataclass
class SLOValidationResult:
    """Resultado da validacao de um SLO."""
    slo: SLOTarget
    status: SLOStatus
    actual_value: Optional[float]
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == SLOStatus.PASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            'slo_name': self.slo.name,
            'metric': self.slo.metric,
            'status': self.status.value,
            'target': self.slo.target_value,
            'actual': self.actual_value,
            'unit': self.slo.unit,
            'message': self.message,
            'passed': self.passed,
            'details': self.details,
        }


# SLOs padrao para o Fluxo C baseados nos alertas e configuracao existente
DEFAULT_SLOS = [
    SLOTarget(
        name='Latencia P95',
        metric='latency_p95_seconds',
        target_value=14400.0,  # 4 horas em segundos
        comparison='lt',
        unit='segundos',
        description='Latencia P95 end-to-end deve ser menor que 4 horas',
        warning_threshold=10800.0,  # 3 horas (warning)
    ),
    SLOTarget(
        name='Latencia P99',
        metric='latency_p99_seconds',
        target_value=21600.0,  # 6 horas em segundos
        comparison='lt',
        unit='segundos',
        description='Latencia P99 end-to-end deve ser menor que 6 horas',
        warning_threshold=18000.0,  # 5 horas (warning)
    ),
    SLOTarget(
        name='Taxa de Sucesso',
        metric='success_rate',
        target_value=0.99,  # 99%
        comparison='gte',
        unit='porcentagem',
        description='Taxa de sucesso de workflows deve ser >= 99%',
        warning_threshold=0.995,  # 99.5% (warning)
    ),
    SLOTarget(
        name='Throughput',
        metric='tickets_per_second',
        target_value=10.0,  # 10 tickets/s
        comparison='gte',
        unit='tickets/segundo',
        description='Throughput de tickets deve ser >= 10/segundo',
        warning_threshold=15.0,  # 15 tickets/s (confortavel)
    ),
    SLOTarget(
        name='Disponibilidade',
        metric='availability',
        target_value=0.999,  # 99.9%
        comparison='gte',
        unit='porcentagem',
        description='Disponibilidade do servico deve ser >= 99.9%',
        warning_threshold=0.9999,  # 99.99%
    ),
    SLOTarget(
        name='Erros por Minuto',
        metric='errors_per_minute',
        target_value=10.0,  # Max 10 erros/min
        comparison='lt',
        unit='erros/minuto',
        description='Taxa de erro deve ser menor que 10 por minuto',
        warning_threshold=5.0,  # 5 erros/min (warning)
    ),
]


@dataclass
class LoadTestMetrics:
    """Metricas coletadas durante teste de carga para validacao de SLOs."""
    # Latencia
    latency_p50_seconds: Optional[float] = None
    latency_p95_seconds: Optional[float] = None
    latency_p99_seconds: Optional[float] = None
    latency_mean_seconds: Optional[float] = None

    # Throughput
    total_workflows: int = 0
    successful_workflows: int = 0
    failed_workflows: int = 0
    total_tickets: int = 0
    test_duration_seconds: float = 0.0

    # Calculados
    @property
    def success_rate(self) -> float:
        if self.total_workflows == 0:
            return 0.0
        return self.successful_workflows / self.total_workflows

    @property
    def failure_rate(self) -> float:
        if self.total_workflows == 0:
            return 0.0
        return self.failed_workflows / self.total_workflows

    @property
    def workflows_per_second(self) -> float:
        if self.test_duration_seconds == 0:
            return 0.0
        return self.total_workflows / self.test_duration_seconds

    @property
    def tickets_per_second(self) -> float:
        if self.test_duration_seconds == 0:
            return 0.0
        return self.total_tickets / self.test_duration_seconds

    @property
    def errors_per_minute(self) -> float:
        if self.test_duration_seconds == 0:
            return 0.0
        minutes = self.test_duration_seconds / 60.0
        return self.failed_workflows / minutes if minutes > 0 else 0.0

    @property
    def availability(self) -> float:
        """Disponibilidade baseada em taxa de sucesso."""
        return self.success_rate


class SLOValidator:
    """Validador de SLOs para testes de carga."""

    def __init__(self, slos: Optional[List[SLOTarget]] = None):
        """
        Inicializa o validador.

        Args:
            slos: Lista de SLOs a validar (usa DEFAULT_SLOS se nao fornecido)
        """
        self.slos = slos or DEFAULT_SLOS.copy()
        self.results: List[SLOValidationResult] = []

    def _compare(self, actual: float, target: float, comparison: str) -> bool:
        """Compara valor atual com target."""
        comparisons = {
            'lt': actual < target,
            'lte': actual <= target,
            'gt': actual > target,
            'gte': actual >= target,
            'eq': actual == target,
        }
        return comparisons.get(comparison, False)

    def _get_comparison_symbol(self, comparison: str) -> str:
        """Retorna simbolo de comparacao para exibicao."""
        symbols = {
            'lt': '<',
            'lte': '<=',
            'gt': '>',
            'gte': '>=',
            'eq': '==',
        }
        return symbols.get(comparison, '?')

    def validate_slo(
        self,
        slo: SLOTarget,
        actual_value: Optional[float],
    ) -> SLOValidationResult:
        """
        Valida um SLO individual.

        Args:
            slo: SLO target a validar
            actual_value: Valor atual da metrica

        Returns:
            SLOValidationResult com resultado da validacao
        """
        if actual_value is None:
            return SLOValidationResult(
                slo=slo,
                status=SLOStatus.NOT_MEASURED,
                actual_value=None,
                message=f'Metrica {slo.metric} nao foi coletada',
            )

        symbol = self._get_comparison_symbol(slo.comparison)
        passed = self._compare(actual_value, slo.target_value, slo.comparison)

        # Verificar warning threshold
        is_warning = False
        if passed and slo.warning_threshold is not None:
            is_warning = not self._compare(
                actual_value, slo.warning_threshold, slo.comparison
            )

        if passed and not is_warning:
            return SLOValidationResult(
                slo=slo,
                status=SLOStatus.PASS,
                actual_value=actual_value,
                message=f'{slo.name}: {actual_value:.4f} {symbol} {slo.target_value} {slo.unit}',
            )
        elif passed and is_warning:
            return SLOValidationResult(
                slo=slo,
                status=SLOStatus.WARN,
                actual_value=actual_value,
                message=(
                    f'{slo.name}: {actual_value:.4f} {symbol} {slo.target_value} '
                    f'(proximo do limite)'
                ),
                details={'warning_threshold': slo.warning_threshold},
            )
        else:
            return SLOValidationResult(
                slo=slo,
                status=SLOStatus.FAIL,
                actual_value=actual_value,
                message=(
                    f'{slo.name}: VIOLACAO - {actual_value:.4f} nao atende '
                    f'{symbol} {slo.target_value} {slo.unit}'
                ),
            )

    def validate_latency_slo(self, metrics: LoadTestMetrics) -> List[SLOValidationResult]:
        """
        Valida SLOs de latencia.

        Args:
            metrics: Metricas coletadas

        Returns:
            Lista de resultados de validacao
        """
        results = []

        # P95
        for slo in self.slos:
            if slo.metric == 'latency_p95_seconds':
                results.append(self.validate_slo(slo, metrics.latency_p95_seconds))
            elif slo.metric == 'latency_p99_seconds':
                results.append(self.validate_slo(slo, metrics.latency_p99_seconds))

        return results

    def validate_success_rate_slo(self, metrics: LoadTestMetrics) -> SLOValidationResult:
        """
        Valida SLO de taxa de sucesso.

        Args:
            metrics: Metricas coletadas

        Returns:
            Resultado da validacao
        """
        slo = next((s for s in self.slos if s.metric == 'success_rate'), None)
        if slo is None:
            slo = SLOTarget(
                name='Taxa de Sucesso',
                metric='success_rate',
                target_value=0.99,
                comparison='gte',
                unit='porcentagem',
                description='Taxa de sucesso deve ser >= 99%',
            )

        return self.validate_slo(slo, metrics.success_rate)

    def validate_throughput_slo(self, metrics: LoadTestMetrics) -> SLOValidationResult:
        """
        Valida SLO de throughput.

        Args:
            metrics: Metricas coletadas

        Returns:
            Resultado da validacao
        """
        slo = next((s for s in self.slos if s.metric == 'tickets_per_second'), None)
        if slo is None:
            slo = SLOTarget(
                name='Throughput',
                metric='tickets_per_second',
                target_value=10.0,
                comparison='gte',
                unit='tickets/segundo',
                description='Throughput deve ser >= 10 tickets/s',
            )

        return self.validate_slo(slo, metrics.tickets_per_second)

    def validate_availability_slo(self, metrics: LoadTestMetrics) -> SLOValidationResult:
        """
        Valida SLO de disponibilidade.

        Args:
            metrics: Metricas coletadas

        Returns:
            Resultado da validacao
        """
        slo = next((s for s in self.slos if s.metric == 'availability'), None)
        if slo is None:
            slo = SLOTarget(
                name='Disponibilidade',
                metric='availability',
                target_value=0.999,
                comparison='gte',
                unit='porcentagem',
                description='Disponibilidade deve ser >= 99.9%',
            )

        return self.validate_slo(slo, metrics.availability)

    def validate_all(self, metrics: LoadTestMetrics) -> List[SLOValidationResult]:
        """
        Valida todos os SLOs.

        Args:
            metrics: Metricas coletadas

        Returns:
            Lista de resultados de validacao
        """
        self.results = []

        # Mapeamento de metricas
        metric_values = {
            'latency_p95_seconds': metrics.latency_p95_seconds,
            'latency_p99_seconds': metrics.latency_p99_seconds,
            'success_rate': metrics.success_rate,
            'tickets_per_second': metrics.tickets_per_second,
            'availability': metrics.availability,
            'errors_per_minute': metrics.errors_per_minute,
        }

        for slo in self.slos:
            actual_value = metric_values.get(slo.metric)
            result = self.validate_slo(slo, actual_value)
            self.results.append(result)

        return self.results

    def all_passed(self) -> bool:
        """Verifica se todos os SLOs passaram."""
        return all(r.status in (SLOStatus.PASS, SLOStatus.WARN) for r in self.results)

    def get_failures(self) -> List[SLOValidationResult]:
        """Retorna SLOs que falharam."""
        return [r for r in self.results if r.status == SLOStatus.FAIL]

    def get_warnings(self) -> List[SLOValidationResult]:
        """Retorna SLOs em warning."""
        return [r for r in self.results if r.status == SLOStatus.WARN]

    def generate_report(self) -> Dict[str, Any]:
        """
        Gera relatorio de conformidade com SLOs.

        Returns:
            Dict com relatorio completo
        """
        passed = [r for r in self.results if r.status == SLOStatus.PASS]
        warnings = self.get_warnings()
        failures = self.get_failures()
        not_measured = [r for r in self.results if r.status == SLOStatus.NOT_MEASURED]

        return {
            'overall_status': 'pass' if self.all_passed() else 'fail',
            'total_slos': len(self.results),
            'passed_count': len(passed),
            'warning_count': len(warnings),
            'failed_count': len(failures),
            'not_measured_count': len(not_measured),
            'compliance_rate': len(passed) / len(self.results) if self.results else 0,
            'results': [r.to_dict() for r in self.results],
            'failures': [r.to_dict() for r in failures],
            'warnings': [r.to_dict() for r in warnings],
        }

    def generate_markdown_report(self) -> str:
        """
        Gera relatorio markdown de SLOs.

        Returns:
            String com relatorio em formato markdown
        """
        lines = ['## Conformidade com SLOs', '']

        passed = [r for r in self.results if r.status == SLOStatus.PASS]
        warnings = self.get_warnings()
        failures = self.get_failures()

        status_emoji = '✅' if self.all_passed() else '❌'
        lines.append(f'**Status Geral:** {status_emoji} {"PASS" if self.all_passed() else "FAIL"}')
        lines.append('')

        lines.append('| SLO | Target | Atual | Status |')
        lines.append('|-----|--------|-------|--------|')

        status_emojis = {
            SLOStatus.PASS: '✅',
            SLOStatus.WARN: '⚠️',
            SLOStatus.FAIL: '❌',
            SLOStatus.NOT_MEASURED: '❓',
        }

        for result in self.results:
            emoji = status_emojis[result.status]
            symbol = self._get_comparison_symbol(result.slo.comparison)
            actual = f'{result.actual_value:.4f}' if result.actual_value is not None else 'N/A'
            target = f'{symbol} {result.slo.target_value}'
            lines.append(f'| {result.slo.name} | {target} | {actual} | {emoji} |')

        lines.append('')

        if failures:
            lines.append('### Violacoes de SLO')
            lines.append('')
            for f in failures:
                lines.append(f'- **{f.slo.name}**: {f.message}')
            lines.append('')

        if warnings:
            lines.append('### Warnings')
            lines.append('')
            for w in warnings:
                lines.append(f'- **{w.slo.name}**: {w.message}')
            lines.append('')

        return '\n'.join(lines)
