"""
Playbook Validator para Chaos Engineering.

Valida a eficácia dos playbooks de remediação através de experimentos
de chaos e medição de métricas de recuperação.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from time import perf_counter
import structlog
from prometheus_client import Counter, Histogram, Gauge

from ..chaos_models import (
    ChaosExperiment,
    ChaosExperimentStatus,
    FaultInjection,
    ValidationCriteria,
    ValidationResult,
)

logger = structlog.get_logger(__name__)

# Métricas Prometheus para validação de playbooks
PLAYBOOK_VALIDATION_TOTAL = Counter(
    'chaos_playbook_validation_total',
    'Total de validações de playbook executadas',
    ['playbook', 'status']
)

PLAYBOOK_RECOVERY_DURATION = Histogram(
    'chaos_playbook_recovery_duration_seconds',
    'Tempo de recuperação usando playbook',
    ['playbook'],
    buckets=[5, 10, 30, 60, 120, 300, 600]
)

PLAYBOOK_VALIDATION_FAILURES = Counter(
    'chaos_playbook_validation_failures_total',
    'Total de falhas de validação de playbook',
    ['playbook', 'failure_reason']
)

PLAYBOOK_EFFECTIVENESS_SCORE = Gauge(
    'chaos_playbook_effectiveness_score',
    'Score de eficácia do playbook (0-100)',
    ['playbook']
)


class PlaybookValidator:
    """
    Validador de eficácia de playbooks de remediação.

    Executa experimentos de chaos, monitora a execução automática
    dos playbooks pelo Self-Healing Engine, e valida se a recuperação
    atende aos critérios especificados.
    """

    def __init__(
        self,
        playbook_executor,
        prometheus_client=None,
        sla_management_client=None,
    ):
        """
        Inicializa o validador de playbooks.

        Args:
            playbook_executor: Instância do PlaybookExecutor
            prometheus_client: Cliente para queries Prometheus (opcional)
            sla_management_client: Cliente do SLA Management System (opcional)
        """
        self.playbook_executor = playbook_executor
        self.prometheus_client = prometheus_client
        self.sla_management_client = sla_management_client
        self._validation_history: Dict[str, List[ValidationResult]] = {}

    async def validate_playbook_effectiveness(
        self,
        playbook_name: str,
        injection: FaultInjection,
        criteria: ValidationCriteria,
        context: Dict[str, Any],
    ) -> ValidationResult:
        """
        Valida a eficácia de um playbook após injeção de falha.

        Monitora a recuperação e verifica se os critérios foram atendidos.

        Args:
            playbook_name: Nome do playbook a validar
            injection: Injeção de falha executada
            criteria: Critérios de validação
            context: Contexto adicional para execução

        Returns:
            ValidationResult com resultados detalhados
        """
        start_time = perf_counter()
        observations = []
        criteria_met = {}

        logger.info(
            "playbook_validator.starting_validation",
            playbook=playbook_name,
            injection_id=injection.id,
            fault_type=injection.fault_type.value
        )

        try:
            # Capturar métricas iniciais
            initial_metrics = await self._capture_metrics(context)

            # Aguardar detecção e execução automática do playbook
            playbook_executed = await self._wait_for_playbook_execution(
                playbook_name,
                context,
                timeout_seconds=criteria.max_recovery_time_seconds
            )

            if not playbook_executed:
                observations.append(
                    f"Playbook '{playbook_name}' não foi executado automaticamente"
                )
                PLAYBOOK_VALIDATION_FAILURES.labels(
                    playbook=playbook_name,
                    failure_reason="not_triggered"
                ).inc()

                return ValidationResult(
                    playbook_name=playbook_name,
                    success=False,
                    recovery_time_seconds=perf_counter() - start_time,
                    criteria_met={"playbook_executed": False},
                    observations=observations,
                    metrics_snapshot=initial_metrics
                )

            # Medir tempo de recuperação
            recovery_time = perf_counter() - start_time
            PLAYBOOK_RECOVERY_DURATION.labels(playbook=playbook_name).observe(recovery_time)

            # Validar tempo de recuperação
            max_recovery = criteria.max_recovery_time_seconds
            recovery_ok = recovery_time <= max_recovery
            criteria_met["recovery_time"] = recovery_ok

            if not recovery_ok:
                observations.append(
                    f"Tempo de recuperação ({recovery_time:.1f}s) excedeu "
                    f"limite ({max_recovery}s)"
                )

            # Capturar métricas após recuperação
            await asyncio.sleep(5)  # Aguardar estabilização
            final_metrics = await self._capture_metrics(context)

            # Validar disponibilidade
            availability = await self._measure_availability(
                context,
                injection.start_time,
                datetime.utcnow()
            )
            availability_ok = availability >= criteria.min_availability_percent
            criteria_met["availability"] = availability_ok

            if not availability_ok:
                observations.append(
                    f"Disponibilidade ({availability:.1f}%) abaixo do mínimo "
                    f"({criteria.min_availability_percent}%)"
                )

            # Validar taxa de erros
            error_rate = await self._measure_error_rate(
                context,
                injection.start_time,
                datetime.utcnow()
            )
            error_rate_ok = error_rate <= criteria.max_error_rate_percent
            criteria_met["error_rate"] = error_rate_ok

            if not error_rate_ok:
                observations.append(
                    f"Taxa de erros ({error_rate:.1f}%) acima do máximo "
                    f"({criteria.max_error_rate_percent}%)"
                )

            # Validar latência se especificada
            if criteria.max_latency_p95_ms:
                latency_p95 = await self._measure_latency_p95(context)
                latency_ok = latency_p95 <= criteria.max_latency_p95_ms
                criteria_met["latency_p95"] = latency_ok

                if not latency_ok:
                    observations.append(
                        f"Latência P95 ({latency_p95:.0f}ms) acima do máximo "
                        f"({criteria.max_latency_p95_ms}ms)"
                    )

            # Calcular resultado geral
            all_criteria_met = all(criteria_met.values())

            if all_criteria_met:
                observations.append("Todos os critérios de validação atendidos")
                PLAYBOOK_VALIDATION_TOTAL.labels(
                    playbook=playbook_name,
                    status="success"
                ).inc()
            else:
                PLAYBOOK_VALIDATION_TOTAL.labels(
                    playbook=playbook_name,
                    status="failed"
                ).inc()
                for criterion, met in criteria_met.items():
                    if not met:
                        PLAYBOOK_VALIDATION_FAILURES.labels(
                            playbook=playbook_name,
                            failure_reason=criterion
                        ).inc()

            # Calcular e registrar score de eficácia
            effectiveness_score = self._calculate_effectiveness_score(
                criteria_met,
                recovery_time,
                criteria
            )
            PLAYBOOK_EFFECTIVENESS_SCORE.labels(playbook=playbook_name).set(
                effectiveness_score
            )

            result = ValidationResult(
                playbook_name=playbook_name,
                success=all_criteria_met,
                recovery_time_seconds=recovery_time,
                availability_percent=availability,
                error_rate_percent=error_rate,
                latency_p95_ms=await self._measure_latency_p95(context)
                if criteria.max_latency_p95_ms else None,
                criteria_met=criteria_met,
                observations=observations,
                metrics_snapshot={
                    "initial": initial_metrics,
                    "final": final_metrics,
                    "effectiveness_score": effectiveness_score
                }
            )

            # Armazenar no histórico
            if playbook_name not in self._validation_history:
                self._validation_history[playbook_name] = []
            self._validation_history[playbook_name].append(result)

            logger.info(
                "playbook_validator.validation_complete",
                playbook=playbook_name,
                success=result.success,
                recovery_time=recovery_time,
                effectiveness_score=effectiveness_score
            )

            return result

        except Exception as e:
            logger.error(
                "playbook_validator.validation_failed",
                playbook=playbook_name,
                error=str(e)
            )
            PLAYBOOK_VALIDATION_TOTAL.labels(
                playbook=playbook_name,
                status="error"
            ).inc()

            return ValidationResult(
                playbook_name=playbook_name,
                success=False,
                recovery_time_seconds=perf_counter() - start_time,
                observations=[f"Erro durante validação: {str(e)}"],
                criteria_met={}
            )

    async def measure_mttr(
        self,
        playbook_name: str,
        num_samples: int = 5,
    ) -> Dict[str, float]:
        """
        Calcula Mean Time To Recovery (MTTR) para um playbook.

        Usa histórico de validações ou executa novas medições.

        Args:
            playbook_name: Nome do playbook
            num_samples: Número de amostras para cálculo

        Returns:
            Dicionário com MTTR médio, mínimo, máximo e P95
        """
        history = self._validation_history.get(playbook_name, [])
        recovery_times = [
            r.recovery_time_seconds
            for r in history
            if r.recovery_time_seconds is not None
        ][-num_samples:]

        if not recovery_times:
            return {
                "mttr_avg": 0,
                "mttr_min": 0,
                "mttr_max": 0,
                "mttr_p95": 0,
                "sample_count": 0
            }

        import statistics

        sorted_times = sorted(recovery_times)
        p95_index = int(len(sorted_times) * 0.95)

        return {
            "mttr_avg": statistics.mean(recovery_times),
            "mttr_min": min(recovery_times),
            "mttr_max": max(recovery_times),
            "mttr_p95": sorted_times[p95_index] if sorted_times else 0,
            "sample_count": len(recovery_times)
        }

    async def check_blast_radius(
        self,
        injection: FaultInjection,
        expected_affected: List[str],
    ) -> Dict[str, Any]:
        """
        Verifica se a falha ficou contida no blast radius esperado.

        Args:
            injection: Injeção de falha executada
            expected_affected: Lista de recursos esperados como afetados

        Returns:
            Dicionário com resultado da verificação de blast radius
        """
        actual_affected = injection.affected_pods or []

        # Verificar se há recursos afetados não esperados
        unexpected = [r for r in actual_affected if r not in expected_affected]

        # Verificar se blast radius está dentro do limite
        blast_radius = len(actual_affected)
        limit = injection.rollback_data.get("blast_radius_limit", 5)

        contained = len(unexpected) == 0 and blast_radius <= limit

        return {
            "contained": contained,
            "expected_affected": expected_affected,
            "actual_affected": actual_affected,
            "unexpected_affected": unexpected,
            "blast_radius": blast_radius,
            "blast_radius_limit": limit
        }

    async def generate_validation_report(
        self,
        playbook_name: str,
        experiment: ChaosExperiment,
        validations: List[ValidationResult],
    ) -> Dict[str, Any]:
        """
        Gera relatório detalhado de validação de playbook.

        Args:
            playbook_name: Nome do playbook validado
            experiment: Experimento de chaos executado
            validations: Lista de resultados de validação

        Returns:
            Relatório detalhado com métricas e recomendações
        """
        successful = [v for v in validations if v.success]
        failed = [v for v in validations if not v.success]

        mttr_stats = await self.measure_mttr(playbook_name)

        # Agregar critérios não atendidos
        failed_criteria = {}
        for v in failed:
            for criterion, met in v.criteria_met.items():
                if not met:
                    failed_criteria[criterion] = failed_criteria.get(criterion, 0) + 1

        # Gerar recomendações
        recommendations = self._generate_recommendations(
            playbook_name,
            mttr_stats,
            failed_criteria
        )

        return {
            "playbook_name": playbook_name,
            "experiment_id": experiment.id,
            "experiment_name": experiment.name,
            "validation_count": len(validations),
            "success_count": len(successful),
            "failure_count": len(failed),
            "success_rate": len(successful) / len(validations) * 100
            if validations else 0,
            "mttr_stats": mttr_stats,
            "failed_criteria_frequency": failed_criteria,
            "recommendations": recommendations,
            "generated_at": datetime.utcnow().isoformat()
        }

    async def _wait_for_playbook_execution(
        self,
        playbook_name: str,
        context: Dict[str, Any],
        timeout_seconds: int,
    ) -> bool:
        """Aguarda execução automática do playbook pelo Self-Healing Engine."""
        # Em um sistema real, monitoraríamos eventos Kafka ou métricas
        # Para esta implementação, verificamos periodicamente

        start = perf_counter()
        check_interval = 5  # segundos

        while perf_counter() - start < timeout_seconds:
            # Verificar se playbook foi executado
            # Isso seria feito via query no MongoDB ou métricas Prometheus

            if self.prometheus_client:
                # Query para verificar execução recente do playbook
                query = (
                    f'increase(self_healing_playbook_execution_total'
                    f'{{playbook="{playbook_name}"}}[5m]) > 0'
                )
                try:
                    result = await self.prometheus_client.query(query)
                    if result and len(result) > 0:
                        logger.info(
                            "playbook_validator.playbook_executed",
                            playbook=playbook_name,
                            elapsed_seconds=perf_counter() - start
                        )
                        return True
                except Exception as e:
                    logger.warning(
                        "playbook_validator.prometheus_query_failed",
                        error=str(e)
                    )

            await asyncio.sleep(check_interval)

        return False

    async def _capture_metrics(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Captura snapshot de métricas atuais."""
        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
        }

        if self.prometheus_client:
            service_name = context.get("service_name", "unknown")

            try:
                # Capturar métricas principais
                queries = {
                    "request_rate": f'sum(rate(http_requests_total{{service="{service_name}"}}[1m]))',
                    "error_rate": f'sum(rate(http_requests_total{{service="{service_name}",status=~"5.."}}[1m]))',
                    "latency_p50": f'histogram_quantile(0.5, rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[1m]))',
                    "latency_p95": f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[1m]))',
                }

                for metric_name, query in queries.items():
                    try:
                        result = await self.prometheus_client.query(query)
                        if result:
                            metrics[metric_name] = result[0].get("value", [None, None])[1]
                    except Exception:
                        pass

            except Exception as e:
                logger.warning(
                    "playbook_validator.metrics_capture_failed",
                    error=str(e)
                )

        return metrics

    async def _measure_availability(
        self,
        context: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
    ) -> float:
        """Mede disponibilidade durante o período especificado."""
        if not self.prometheus_client:
            return 99.9  # Valor default se Prometheus não disponível

        service_name = context.get("service_name", "unknown")
        duration = (end_time - start_time).total_seconds()

        try:
            # Query para calcular disponibilidade
            query = (
                f'avg_over_time('
                f'(sum(up{{service="{service_name}"}}) > 0)[{int(duration)}s:]'
                f') * 100'
            )

            result = await self.prometheus_client.query(query)
            if result:
                return float(result[0].get("value", [None, 99.9])[1])

        except Exception as e:
            logger.warning(
                "playbook_validator.availability_measurement_failed",
                error=str(e)
            )

        return 99.9

    async def _measure_error_rate(
        self,
        context: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
    ) -> float:
        """Mede taxa de erros durante o período especificado."""
        if not self.prometheus_client:
            return 0.1  # Valor default se Prometheus não disponível

        service_name = context.get("service_name", "unknown")
        duration = (end_time - start_time).total_seconds()

        try:
            # Query para calcular taxa de erros
            query = (
                f'sum(increase(http_requests_total{{service="{service_name}",status=~"5.."}}[{int(duration)}s])) / '
                f'sum(increase(http_requests_total{{service="{service_name}"}}[{int(duration)}s])) * 100'
            )

            result = await self.prometheus_client.query(query)
            if result:
                return float(result[0].get("value", [None, 0.1])[1])

        except Exception as e:
            logger.warning(
                "playbook_validator.error_rate_measurement_failed",
                error=str(e)
            )

        return 0.1

    async def _measure_latency_p95(self, context: Dict[str, Any]) -> float:
        """Mede latência P95 atual."""
        if not self.prometheus_client:
            return 100.0  # 100ms default

        service_name = context.get("service_name", "unknown")

        try:
            query = (
                f'histogram_quantile(0.95, '
                f'rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[5m])) * 1000'
            )

            result = await self.prometheus_client.query(query)
            if result:
                return float(result[0].get("value", [None, 100.0])[1])

        except Exception as e:
            logger.warning(
                "playbook_validator.latency_measurement_failed",
                error=str(e)
            )

        return 100.0

    def _calculate_effectiveness_score(
        self,
        criteria_met: Dict[str, bool],
        recovery_time: float,
        criteria: ValidationCriteria,
    ) -> float:
        """
        Calcula score de eficácia do playbook (0-100).

        Considera:
        - Critérios atendidos (peso 60%)
        - Tempo de recuperação vs limite (peso 40%)
        """
        # Score baseado em critérios atendidos
        if not criteria_met:
            criteria_score = 0
        else:
            criteria_score = sum(criteria_met.values()) / len(criteria_met) * 60

        # Score baseado em tempo de recuperação
        max_time = criteria.max_recovery_time_seconds
        if recovery_time <= max_time * 0.5:
            time_score = 40  # Recuperação muito rápida
        elif recovery_time <= max_time:
            time_score = 40 * (1 - (recovery_time / max_time) * 0.5)
        else:
            time_score = 0  # Excedeu limite

        return round(criteria_score + time_score, 1)

    def _generate_recommendations(
        self,
        playbook_name: str,
        mttr_stats: Dict[str, float],
        failed_criteria: Dict[str, int],
    ) -> List[str]:
        """Gera recomendações baseadas nos resultados de validação."""
        recommendations = []

        # Recomendações baseadas em MTTR
        if mttr_stats["mttr_avg"] > 300:  # 5 minutos
            recommendations.append(
                f"MTTR médio de {mttr_stats['mttr_avg']:.0f}s está alto. "
                "Considere otimizar o playbook para ação mais rápida."
            )

        if mttr_stats["mttr_p95"] > mttr_stats["mttr_avg"] * 2:
            recommendations.append(
                "Alta variância no tempo de recuperação. "
                "Investigue casos outliers para melhorar consistência."
            )

        # Recomendações baseadas em critérios falhos
        if "availability" in failed_criteria:
            recommendations.append(
                "Falhas de disponibilidade detectadas. "
                "Considere adicionar réplicas ou melhorar health checks."
            )

        if "error_rate" in failed_criteria:
            recommendations.append(
                "Taxa de erros elevada durante recuperação. "
                "Verifique circuit breakers e retry policies."
            )

        if "latency_p95" in failed_criteria:
            recommendations.append(
                "Latência alta durante recuperação. "
                "Considere warm-up de conexões e caches."
            )

        if not recommendations:
            recommendations.append(
                f"Playbook '{playbook_name}' está performando bem. "
                "Continue monitorando métricas de eficácia."
            )

        return recommendations

    def get_validation_history(
        self,
        playbook_name: str,
        limit: int = 10
    ) -> List[ValidationResult]:
        """Retorna histórico de validações para um playbook."""
        history = self._validation_history.get(playbook_name, [])
        return history[-limit:]

    def clear_validation_history(self, playbook_name: Optional[str] = None):
        """Limpa histórico de validações."""
        if playbook_name:
            self._validation_history.pop(playbook_name, None)
        else:
            self._validation_history.clear()
