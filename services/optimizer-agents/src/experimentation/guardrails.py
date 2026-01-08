# -*- coding: utf-8 -*-
"""
Sistema de Guardrails Automaticos para testes A/B.

Implementa monitoramento continuo de metricas de seguranca
e aborta experimentos automaticamente quando limites sao violados.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import structlog

from src.experimentation.statistical_analysis import StatisticalAnalyzer

logger = structlog.get_logger()


@dataclass
class GuardrailViolation:
    """Representacao de violacao de guardrail."""
    metric_name: str
    current_value: float
    baseline_value: float
    degradation_percentage: float
    threshold_percentage: float
    abort_threshold_percentage: float
    severity: str  # "warning", "critical", "abort"
    timestamp: datetime


@dataclass
class GuardrailCheckResult:
    """Resultado da verificacao de guardrails."""
    violated: bool
    violations: List[GuardrailViolation]
    should_abort: bool
    abort_reason: Optional[str]
    all_metrics_checked: List[str]
    passed_metrics: List[str]


@dataclass
class SequentialTestResult:
    """Resultado do teste sequencial (SPRT)."""
    can_stop_early: bool
    decision: str  # "continue", "reject_null", "accept_null"
    likelihood_ratio: float
    upper_boundary: float
    lower_boundary: float
    samples_analyzed: int
    minimum_samples_reached: bool


class GuardrailMonitor:
    """
    Monitor de guardrails para experimentos A/B.

    Verifica continuamente se metricas de seguranca estao
    dentro dos limites aceitaveis e aciona aborts automaticos.
    """

    def __init__(
        self,
        mongodb_client=None,
        redis_client=None,
        statistical_analyzer: Optional[StatisticalAnalyzer] = None,
        min_sample_size: int = 100,
    ):
        """
        Inicializar monitor de guardrails.

        Args:
            mongodb_client: Cliente MongoDB para persistencia
            redis_client: Cliente Redis para cache
            statistical_analyzer: Analisador estatistico
            min_sample_size: Tamanho minimo de amostra antes de abortar
        """
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.statistical_analyzer = statistical_analyzer or StatisticalAnalyzer()
        self.min_sample_size = min_sample_size

    async def check_guardrails(
        self,
        experiment_id: str,
        guardrails_config: List[Dict],
        control_metrics: Dict[str, List[float]],
        treatment_metrics: Dict[str, List[float]],
    ) -> GuardrailCheckResult:
        """
        Verificar todos os guardrails configurados.

        Args:
            experiment_id: ID do experimento
            guardrails_config: Lista de configuracoes de guardrails
            control_metrics: Metricas do grupo controle
            treatment_metrics: Metricas do grupo tratamento

        Returns:
            Resultado da verificacao com violacoes encontradas
        """
        violations = []
        all_metrics = []
        passed_metrics = []
        should_abort = False
        abort_reason = None

        for guardrail in guardrails_config:
            metric_name = guardrail.get("metric_name", "")
            max_degradation = guardrail.get("max_degradation_percentage", 0.05)
            abort_threshold = guardrail.get("abort_threshold", 0.10)

            all_metrics.append(metric_name)

            # Obter dados das metricas
            control_data = control_metrics.get(metric_name, [])
            treatment_data = treatment_metrics.get(metric_name, [])

            if not control_data or not treatment_data:
                logger.debug(
                    "guardrail_skipped_no_data",
                    metric_name=metric_name,
                    experiment_id=experiment_id,
                )
                continue

            # Calcular medias
            control_mean = float(np.mean(control_data))
            treatment_mean = float(np.mean(treatment_data))

            # Calcular degradacao
            # Assumir que "maior e pior" para metricas como latencia e error_rate
            if control_mean != 0:
                degradation = (treatment_mean - control_mean) / abs(control_mean)
            else:
                degradation = 0.0 if treatment_mean == 0 else 1.0

            # Verificar violacao
            if degradation > max_degradation:
                severity = "warning"
                if degradation > abort_threshold:
                    severity = "abort"
                    should_abort = True
                    abort_reason = f"Guardrail {metric_name} atingiu abort threshold: {degradation:.2%} > {abort_threshold:.2%}"
                elif degradation > max_degradation * 1.5:
                    severity = "critical"

                violation = GuardrailViolation(
                    metric_name=metric_name,
                    current_value=treatment_mean,
                    baseline_value=control_mean,
                    degradation_percentage=degradation,
                    threshold_percentage=max_degradation,
                    abort_threshold_percentage=abort_threshold,
                    severity=severity,
                    timestamp=datetime.utcnow(),
                )
                violations.append(violation)

                logger.warning(
                    "guardrail_violation_detected",
                    experiment_id=experiment_id,
                    metric_name=metric_name,
                    degradation=f"{degradation:.2%}",
                    severity=severity,
                )
            else:
                passed_metrics.append(metric_name)

        return GuardrailCheckResult(
            violated=len(violations) > 0,
            violations=violations,
            should_abort=should_abort,
            abort_reason=abort_reason,
            all_metrics_checked=all_metrics,
            passed_metrics=passed_metrics,
        )

    async def should_abort(
        self,
        experiment_id: str,
        guardrails_config: List[Dict],
        control_metrics: Dict[str, List[float]],
        treatment_metrics: Dict[str, List[float]],
        current_sample_size: int,
    ) -> Dict:
        """
        Verificar se experimento deve ser abortado.

        Args:
            experiment_id: ID do experimento
            guardrails_config: Configuracao dos guardrails
            control_metrics: Metricas do grupo controle
            treatment_metrics: Metricas do grupo tratamento
            current_sample_size: Tamanho atual da amostra

        Returns:
            Dict com should_abort e reason
        """
        # Verificar tamanho minimo de amostra
        if current_sample_size < self.min_sample_size:
            return {
                "should_abort": False,
                "reason": f"Amostra insuficiente: {current_sample_size} < {self.min_sample_size}",
            }

        # Verificar guardrails
        result = await self.check_guardrails(
            experiment_id=experiment_id,
            guardrails_config=guardrails_config,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
        )

        if result.should_abort:
            return {
                "should_abort": True,
                "reason": result.abort_reason,
                "violations": [
                    {
                        "metric": v.metric_name,
                        "degradation": f"{v.degradation_percentage:.2%}",
                        "threshold": f"{v.abort_threshold_percentage:.2%}",
                    }
                    for v in result.violations
                ],
            }

        return {
            "should_abort": False,
            "reason": "Todos os guardrails OK",
        }

    async def apply_sequential_testing(
        self,
        experiment_id: str,
        control_data: List[float],
        treatment_data: List[float],
        minimum_detectable_effect: float = 0.05,
        alpha: float = 0.05,
        beta: float = 0.20,
    ) -> SequentialTestResult:
        """
        Aplicar Sequential Probability Ratio Test (SPRT).

        Permite parada antecipada quando significancia e atingida,
        mantendo rigor estatistico.

        Args:
            experiment_id: ID do experimento
            control_data: Dados do grupo controle
            treatment_data: Dados do grupo tratamento
            minimum_detectable_effect: Efeito minimo detectavel (MDE)
            alpha: Erro tipo I (false positive rate)
            beta: Erro tipo II (false negative rate)

        Returns:
            Resultado com decisao de parada
        """
        n = min(len(control_data), len(treatment_data))

        if n < self.min_sample_size:
            return SequentialTestResult(
                can_stop_early=False,
                decision="continue",
                likelihood_ratio=1.0,
                upper_boundary=0.0,
                lower_boundary=0.0,
                samples_analyzed=n,
                minimum_samples_reached=False,
            )

        # Calcular boundaries do SPRT
        # A = (1 - beta) / alpha  (rejeitar H0)
        # B = beta / (1 - alpha)  (aceitar H0)
        A = (1 - beta) / alpha
        B = beta / (1 - alpha)

        upper_boundary = math.log(A)
        lower_boundary = math.log(B)

        # Calcular likelihood ratio
        control_arr = np.array(control_data[:n])
        treatment_arr = np.array(treatment_data[:n])

        control_mean = np.mean(control_arr)
        treatment_mean = np.mean(treatment_arr)
        pooled_std = np.sqrt((np.var(control_arr) + np.var(treatment_arr)) / 2)

        if pooled_std == 0:
            pooled_std = 1.0

        # Calcular log-likelihood ratio
        # Usando aproximacao normal
        effect = (treatment_mean - control_mean) / pooled_std

        # Log likelihood ratio para teste unilateral
        llr = n * (effect * minimum_detectable_effect - (minimum_detectable_effect ** 2) / 2)

        # Decisao
        decision = "continue"
        can_stop = False

        if llr >= upper_boundary:
            decision = "reject_null"  # Tratamento e melhor
            can_stop = True
            logger.info(
                "sequential_test_stop_reject_null",
                experiment_id=experiment_id,
                llr=llr,
                samples=n,
            )
        elif llr <= lower_boundary:
            decision = "accept_null"  # Sem diferenca significativa
            can_stop = True
            logger.info(
                "sequential_test_stop_accept_null",
                experiment_id=experiment_id,
                llr=llr,
                samples=n,
            )

        return SequentialTestResult(
            can_stop_early=can_stop,
            decision=decision,
            likelihood_ratio=float(llr),
            upper_boundary=float(upper_boundary),
            lower_boundary=float(lower_boundary),
            samples_analyzed=n,
            minimum_samples_reached=True,
        )

    async def get_guardrail_status(
        self,
        experiment_id: str,
    ) -> Optional[Dict]:
        """
        Obter status atual dos guardrails de um experimento.

        Args:
            experiment_id: ID do experimento

        Returns:
            Status dos guardrails ou None se nao encontrado
        """
        if not self.redis_client:
            return None

        try:
            import json

            key = f"ab_test:{experiment_id}:guardrails_status"
            cached = await self.redis_client.get(key)

            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning("failed_to_get_guardrail_status", error=str(e))

        return None

    async def save_guardrail_status(
        self,
        experiment_id: str,
        status: GuardrailCheckResult,
    ) -> None:
        """
        Salvar status dos guardrails no Redis.

        Args:
            experiment_id: ID do experimento
            status: Resultado da verificacao
        """
        if not self.redis_client:
            return

        try:
            import json

            key = f"ab_test:{experiment_id}:guardrails_status"
            data = {
                "violated": status.violated,
                "should_abort": status.should_abort,
                "abort_reason": status.abort_reason,
                "violations_count": len(status.violations),
                "violations": [
                    {
                        "metric_name": v.metric_name,
                        "degradation": v.degradation_percentage,
                        "severity": v.severity,
                    }
                    for v in status.violations
                ],
                "checked_at": datetime.utcnow().isoformat(),
            }

            await self.redis_client.setex(key, 300, json.dumps(data))  # 5 min TTL
        except Exception as e:
            logger.warning("failed_to_save_guardrail_status", error=str(e))
