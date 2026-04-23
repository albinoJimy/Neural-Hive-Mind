"""
Feedback Loop Service - Coleta de métricas e feedback pós-deploy.

Este serviço coleta dados sobre o resultado de workflows e deployments
para gerar feedback contínuo para especialistas e modelos ML.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MetricType(str, Enum):
    """Tipo de métrica."""

    PERFORMANCE = "performance"  # Response time, throughput
    RELIABILITY = "reliability"  # Uptime, error rate
    QUALITY = "quality"  # Code quality, test coverage
    USER_SATISFACTION = "user_satisfaction"  # NPS, ratings
    RESOURCE_USAGE = "resource_usage"  # CPU, memory


class FeedbackSource(str, Enum):
    """Fonte de feedback."""

    DEPLOYMENT = "deployment"  # Métricas do deployment
    MONITORING = "monitoring"  # Métricas de monitoring
    USER = "user"  # Feedback direto do usuário
    AUTOMATED = "automated"  # Testes automatizados
    SPECIALIST = "specialist"  # Feedback de especialistas


class DeploymentMetrics:
    """Métricas coletadas pós-deployment."""

    def __init__(
        self,
        deployment_id: str,
        plan_id: str,
        workflow_id: str,
        service_url: str,
    ):
        self.deployment_id = deployment_id
        self.plan_id = plan_id
        self.workflow_id = workflow_id
        self.service_url = service_url
        self.collected_at = datetime.now(timezone.utc)

        # Métricas de performance
        self.response_time_ms: float | None = None
        self.throughput_rps: float | None = None
        self.error_rate: float | None = None

        # Métricas de confiabilidade
        self.uptime_pct: float | None = None
        self.restart_count: int = 0
        self.crash_count: int = 0

        # Métricas de qualidade
        self.test_coverage: float | None = None
        self.lint_issues: int = 0
        self.security_issues: int = 0

        # Métricas de satisfação
        self.user_ratings: list[int] = []
        self.user_feedback: list[str] = []

        # Métricas de recursos
        self.avg_cpu_pct: float | None = None
        self.avg_memory_mb: float | None = None
        self.peak_memory_mb: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Converte para dict."""
        return {
            "deployment_id": self.deployment_id,
            "plan_id": self.plan_id,
            "workflow_id": self.workflow_id,
            "service_url": self.service_url,
            "collected_at": self.collected_at.isoformat(),
            "performance": {
                "response_time_ms": self.response_time_ms,
                "throughput_rps": self.throughput_rps,
                "error_rate": self.error_rate,
            },
            "reliability": {
                "uptime_pct": self.uptime_pct,
                "restart_count": self.restart_count,
                "crash_count": self.crash_count,
            },
            "quality": {
                "test_coverage": self.test_coverage,
                "lint_issues": self.lint_issues,
                "security_issues": self.security_issues,
            },
            "user_satisfaction": {
                "avg_rating": sum(self.user_ratings) / len(self.user_ratings)
                if self.user_ratings
                else None,
                "rating_count": len(self.user_ratings),
                "feedback_samples": self.user_feedback[:3],
            },
            "resource_usage": {
                "avg_cpu_pct": self.avg_cpu_pct,
                "avg_memory_mb": self.avg_memory_mb,
                "peak_memory_mb": self.peak_memory_mb,
            },
        }


class FeedbackSignal:
    """Sinal de feedback para especialistas ou modelos."""

    def __init__(
        self,
        signal_type: str,
        source: FeedbackSource,
        plan_id: str,
        workflow_id: str,
        data: dict[str, Any],
        priority: str = "normal",
        timestamp: datetime | None = None,
    ):
        self.signal_type = signal_type  # "quality_issue", "performance_problem", etc.
        self.source = source
        self.plan_id = plan_id
        self.workflow_id = workflow_id
        self.data = data
        self.priority = priority  # "low", "normal", "high", "critical"
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.processed = False

    def to_dict(self) -> dict[str, Any]:
        """Converte para dict."""
        return {
            "signal_type": self.signal_type,
            "source": self.source.value,
            "plan_id": self.plan_id,
            "workflow_id": self.workflow_id,
            "data": self.data,
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat(),
            "processed": self.processed,
        }


class FeedbackLoopService:
    """
    Serviço para gerenciar o loop de feedback contínuo.

    Coleta métricas pós-deploy e gera sinais de feedback para:
    - Especialistas (aprimorarem decisões)
    - Modelos ML (retreinamento)
    - Sistema (auto-correção)
    """

    def __init__(
        self,
        enable_auto_collection: bool = True,
        collection_interval_hours: int = 24,
        feedback_queue_size: int = 1000,
    ):
        """
        Inicializa o serviço.

        Args:
            enable_auto_collection: Habilitar coleta automática
            collection_interval_hours: Intervalo de coleta em horas
            feedback_queue_size: Tamanho máximo da fila de feedback
        """
        self.enable_auto_collection = enable_auto_collection
        self.collection_interval_hours = collection_interval_hours
        self.feedback_queue_size = feedback_queue_size

        # Storage de métricas e sinais
        self.metrics: dict[str, DeploymentMetrics] = {}
        self.feedback_signals: list[FeedbackSignal] = []

        # Callbacks para processamento de feedback
        self.specialist_callbacks: list[callable] = []
        self.ml_callbacks: list[callable] = []

    async def collect_deployment_metrics(
        self,
        deployment_id: str,
        plan_id: str,
        workflow_id: str,
        service_url: str,
        monitoring_data: dict[str, Any] | None = None,
    ) -> DeploymentMetrics:
        """
        Coleta métricas de um deployment.

        Args:
            deployment_id: ID do deployment
            plan_id: ID do plano
            workflow_id: ID do workflow
            service_url: URL do serviço
            monitoring_data: Dados do monitoring (Prometheus, etc.)

        Returns:
            DeploymentMetrics coletadas
        """
        logger.info(
            "collecting_deployment_metrics",
            deployment_id=deployment_id,
            plan_id=plan_id,
        )

        metrics = DeploymentMetrics(
            deployment_id=deployment_id,
            plan_id=plan_id,
            workflow_id=workflow_id,
            service_url=service_url,
        )

        # Coletar métricas de monitoring se disponível
        if monitoring_data:
            metrics = await self._enrich_from_monitoring(metrics, monitoring_data)

        # Simular coleta de métricas (em produção, viria do Prometheus/Grafana)
        metrics = await self._simulate_metrics(metrics)

        # Armazenar
        self.metrics[deployment_id] = metrics

        # Gerar sinais de feedback automaticamente
        await self._generate_feedback_signals(metrics)

        logger.info(
            "deployment_metrics_collected",
            deployment_id=deployment_id,
            response_time_ms=metrics.response_time_ms,
            error_rate=metrics.error_rate,
        )

        return metrics

    async def generate_specialist_feedback(
        self,
        deployment_id: str,
        feedback_data: dict[str, Any],
    ) -> FeedbackSignal:
        """
        Gera feedback de especialista sobre um deployment.

        Args:
            deployment_id: ID do deployment
            feedback_data: Dados do feedback (rating, comments, etc.)

        Returns:
            FeedbackSignal gerado
        """
        metrics = self.metrics.get(deployment_id)
        if not metrics:
            logger.warning(
                "metrics_not_found",
                deployment_id=deployment_id,
            )
            return None

        signal = FeedbackSignal(
            signal_type="specialist_feedback",
            source=FeedbackSource.SPECIALIST,
            plan_id=metrics.plan_id,
            workflow_id=metrics.workflow_id,
            data=feedback_data,
            priority=self._calculate_feedback_priority(feedback_data),
        )

        await self._add_feedback_signal(signal)

        logger.info(
            "specialist_feedback_generated",
            deployment_id=deployment_id,
            rating=feedback_data.get("rating"),
        )

        return signal

    async def generate_ml_training_data(
        self,
        plan_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Gera dados de treinamento para modelos ML.

        Args:
            plan_id: ID do plano para filtrar
            limit: Limite de registros

        Returns:
            Lista de exemplos de treinamento
        """
        logger.info(
            "generating_ml_training_data",
            plan_id=plan_id,
            limit=limit,
        )

        training_data = []

        # Coletar dados dos deployments relacionados ao plano
        for metrics in list(self.metrics.values())[:limit]:
            if metrics.plan_id == plan_id:
                example = {
                    "features": {
                        "response_time_ms": metrics.response_time_ms,
                        "error_rate": metrics.error_rate,
                        "test_coverage": metrics.test_coverage,
                        "uptime_pct": metrics.uptime_pct,
                        "avg_cpu_pct": metrics.avg_cpu_pct,
                    },
                    "labels": {
                        "success": metrics.error_rate < 0.05 if metrics.error_rate else True,
                        "quality": (
                            "good"
                            if (metrics.test_coverage or 0) > 0.8
                            else "needs_improvement"
                        ),
                    },
                }
                training_data.append(example)

        logger.info(
            "ml_training_data_generated",
            plan_id=plan_id,
            examples_count=len(training_data),
        )

        return training_data

    async def get_feedback_summary(
        self,
        plan_id: str | None = None,
        workflow_id: str | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """
        Obtém resumo de feedback para análise.

        Args:
            plan_id: Filtrar por plano
            workflow_id: Filtrar por workflow
            days: Número de dias para analisar

        Returns:
            Resumo agregado de feedback
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        filtered_signals = [
            s
            for s in self.feedback_signals
            if s.timestamp >= cutoff
            and (plan_id is None or s.plan_id == plan_id)
            and (workflow_id is None or s.workflow_id == workflow_id)
        ]

        # Agregar por tipo
        by_type: dict[str, int] = {}
        by_priority: dict[str, int] = {}

        for signal in filtered_signals:
            by_type[signal.signal_type] = by_type.get(signal.signal_type, 0) + 1
            by_priority[signal.priority] = by_priority.get(signal.priority, 0) + 1

        return {
            "period_days": days,
            "total_signals": len(filtered_signals),
            "by_type": by_type,
            "by_priority": by_priority,
            "pending_signals": sum(1 for s in filtered_signals if not s.processed),
        }

    async def _enrich_from_monitoring(
        self,
        metrics: DeploymentMetrics,
        monitoring_data: dict[str, Any],
    ) -> DeploymentMetrics:
        """Enriquece métricas com dados do monitoring."""
        # Exemplo: extrair do Prometheus/Grafana
        if "response_time" in monitoring_data:
            metrics.response_time_ms = monitoring_data["response_time"]
        if "error_rate" in monitoring_data:
            metrics.error_rate = monitoring_data["error_rate"]
        if "uptime" in monitoring_data:
            metrics.uptime_pct = monitoring_data["uptime"]
        return metrics

    async def _simulate_metrics(
        self,
        metrics: DeploymentMetrics,
    ) -> DeploymentMetrics:
        """Simula coleta de métricas (placeholder)."""
        # Em produção, viria do Prometheus/Grafana/Datadog
        metrics.response_time_ms = 150.0
        metrics.throughput_rps = 45.0
        metrics.error_rate = 0.001
        metrics.uptime_pct = 99.9
        metrics.restart_count = 0
        metrics.test_coverage = 0.85
        metrics.lint_issues = 3
        metrics.security_issues = 0
        metrics.avg_cpu_pct = 35.0
        metrics.avg_memory_mb = 256.0
        metrics.peak_memory_mb = 512.0
        return metrics

    async def _generate_feedback_signals(
        self,
        metrics: DeploymentMetrics,
    ):
        """Gera sinais de feedback automaticamente baseado nas métricas."""

        # Verificar performance
        if metrics.response_time_ms and metrics.response_time_ms > 500:
            await self._add_feedback_signal(
                FeedbackSignal(
                    signal_type="performance_issue",
                    source=FeedbackSource.AUTOMATED,
                    plan_id=metrics.plan_id,
                    workflow_id=metrics.workflow_id,
                    data={
                        "issue": "high_response_time",
                        "value_ms": metrics.response_time_ms,
                        "threshold_ms": 500,
                    },
                    priority="high",
                )
            )

        # Verificar erros
        if metrics.error_rate and metrics.error_rate > 0.05:
            await self._add_feedback_signal(
                FeedbackSignal(
                    signal_type="reliability_issue",
                    source=FeedbackSource.AUTOMATED,
                    plan_id=metrics.plan_id,
                    workflow_id=metrics.workflow_id,
                    data={
                        "issue": "high_error_rate",
                        "value": metrics.error_rate,
                        "threshold": 0.05,
                    },
                    priority="critical",
                )
            )

        # Verificar testes
        if metrics.test_coverage and metrics.test_coverage < 0.7:
            await self._add_feedback_signal(
                FeedbackSignal(
                    signal_type="quality_issue",
                    source=FeedbackSource.AUTOMATED,
                    plan_id=metrics.plan_id,
                    workflow_id=metrics.workflow_id,
                    data={
                        "issue": "low_test_coverage",
                        "value": metrics.test_coverage,
                        "threshold": 0.7,
                    },
                    priority="normal",
                )
            )

    async def _add_feedback_signal(self, signal: FeedbackSignal):
        """Adiciona sinal à fila de feedback."""
        self.feedback_signals.append(signal)

        # Limitar tamanho da fila
        if len(self.feedback_signals) > self.feedback_queue_size:
            self.feedback_signals = self.feedback_signals[-self.feedback_queue_size :]

        # Processar callbacks
        await self._process_signal(signal)

    async def _process_signal(self, signal: FeedbackSignal):
        """Processa sinal através de callbacks registrados."""
        for callback in self.specialist_callbacks:
            try:
                await callback(signal)
            except Exception as e:
                logger.exception(
                    "specialist_callback_failed",
                    signal_type=signal.signal_type,
                    error=str(e),
                )

        for callback in self.ml_callbacks:
            try:
                await callback(signal)
            except Exception as e:
                logger.exception(
                    "ml_callback_failed",
                    signal_type=signal.signal_type,
                    error=str(e),
                )

        signal.processed = True

    def _calculate_feedback_priority(self, feedback_data: dict[str, Any]) -> str:
        """Calcula prioridade do feedback."""
        rating = feedback_data.get("rating", 5)

        if rating <= 2:
            return "critical"
        elif rating == 3:
            return "high"
        elif rating == 4:
            return "normal"
        else:
            return "low"

    def register_specialist_callback(self, callback: callable):
        """Registra callback para feedback de especialista."""
        self.specialist_callbacks.append(callback)

    def register_ml_callback(self, callback: callable):
        """Registra callback para retreinamento ML."""
        self.ml_callbacks.append(callback)


# Singleton instance
_default_service: FeedbackLoopService | None = None


def get_feedback_loop_service() -> FeedbackLoopService:
    """Retorna o serviço de feedback loop (singleton)."""
    global _default_service
    if _default_service is None:
        _default_service = FeedbackLoopService()
    return _default_service
