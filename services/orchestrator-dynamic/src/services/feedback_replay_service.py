"""
Feedback-Driven Replay Service.

Gerencia workflows que falharam devido a modelos ML e dispara replay
automático quando modelos são retreinados e melhoram.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from temporalio.client import Client

from neural_hive_observability import get_tracer

logger = structlog.get_logger(__name__)


class ReplayPriority(str, Enum):
    """Prioridade de replay."""

    CRITICAL = "critical"  # Impacto direto em produção
    HIGH = "high"  # Workflows importantes de clientes
    MEDIUM = "medium"  # Workflows regulares
    LOW = "low"  # Workflows não-críticos


class ReplayStatus(str, Enum):
    """Status de um replay agendado."""

    PENDING = "pending"  # Aguardando modelo melhorar
    SCHEDULED = "scheduled"  # Agendado para execução
    RUNNING = "running"  # Executando
    COMPLETED = "completed"  # Concluído com sucesso
    FAILED = "failed"  # Falhou novamente
    CANCELLED = "cancelled"  # Cancelado


class ModelImprovement(str, Enum):
    """Nível de melhoria do modelo."""

    SIGNIFICANT = "significant"  # >20% melhoria
    MODERATE = "moderate"  # 10-20% melhoria
    MINIMAL = "minimal"  # <10% melhoria
    NONE = "none"  # Sem melhoria
    REGRESSION = "regression"  # Modelo piorou


class PendingReplay:
    """Representa um workflow aguardando replay."""

    def __init__(
        self,
        workflow_id: str,
        original_run_id: str,
        failure_reason: str,
        model_version_at_failure: str,
        plan_id: str | None = None,
        priority: ReplayPriority = ReplayPriority.MEDIUM,
        estimated_impact: float = 0.0,
        context: dict | None = None,
        created_at: datetime | None = None,
    ):
        self.workflow_id = workflow_id
        self.original_run_id = original_run_id
        self.failure_reason = failure_reason
        self.model_version_at_failure = model_version_at_failure
        self.plan_id = plan_id
        self.priority = priority
        self.estimated_impact = estimated_impact  # 0-1, impacto do negócio
        self.context = context or {}
        self.created_at = created_at or datetime.now(timezone.utc)
        self.status = ReplayStatus.PENDING
        self.replay_attempts: list[dict] = []
        self.last_model_version_checked = model_version_at_failure

    def to_dict(self) -> dict[str, Any]:
        """Converte para dict."""
        return {
            "workflow_id": self.workflow_id,
            "original_run_id": self.original_run_id,
            "failure_reason": self.failure_reason,
            "model_version_at_failure": self.model_version_at_failure,
            "plan_id": self.plan_id,
            "priority": self.priority.value,
            "estimated_impact": self.estimated_impact,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "replay_attempts": len(self.replay_attempts),
            "last_model_version_checked": self.last_model_version_checked,
        }


class FeedbackReplayService:
    """
    Serviço de Replay driven por Feedback.

    Gerencia workflows que falharam devido a modelos ML e
    dispara replay automático quando modelos são melhorados.
    """

    def __init__(
        self,
        temporal_client: Client | None = None,
        improvement_threshold: ModelImprovement = ModelImprovement.MODERATE,
        max_replay_attempts: int = 3,
        replay_queue_size: int = 1000,
    ):
        self._temporal_client = temporal_client
        self._improvement_threshold = improvement_threshold
        self._max_replay_attempts = max_replay_attempts
        self._replay_queue_size = replay_queue_size

        # Fila de replays pendentes (workflow_id -> PendingReplay)
        self._pending_replays: dict[str, PendingReplay] = {}

        # Histórico de replays executados
        self._replay_history: list[dict] = []

        # Métricas
        self._metrics = {
            "total_pending": 0,
            "total_replayed": 0,
            "total_successful": 0,
            "total_failed": 0,
            "avg_improvement_before_replay": 0.0,
        }

        self._tracer = get_tracer()

    async def register_failed_workflow(
        self,
        workflow_id: str,
        run_id: str,
        failure_reason: str,
        model_version: str,
        plan_id: str | None = None,
        priority: ReplayPriority = ReplayPriority.MEDIUM,
        estimated_impact: float = 0.0,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """
        Registra um workflow que falhou devido a modelo ML.

        Args:
            workflow_id: ID do workflow
            run_id: ID da execução
            failure_reason: Razão da falha
            model_version: Versão do modelo quando falhou
            plan_id: ID do plano (opcional)
            priority: Prioridade do replay
            estimated_impact: Impacto estimado (0-1)
            context: Contexto adicional

        Returns:
            Dict com status do registro
        """
        logger.info(
            "registering_failed_workflow",
            workflow_id=workflow_id,
            run_id=run_id,
            failure_reason=failure_reason,
            model_version=model_version,
        )

        # Verificar se já existe
        if workflow_id in self._pending_replays:
            logger.warning(
                "workflow_already_pending",
                workflow_id=workflow_id,
            )
            return {
                "status": "already_registered",
                "workflow_id": workflow_id,
                "registered_at": self._pending_replays[workflow_id].created_at.isoformat(),
            }

        # Verificar limite da fila
        if len(self._pending_replays) >= self._replay_queue_size:
            logger.error(
                "replay_queue_full",
                current_size=len(self._pending_replays),
                max_size=self._replay_queue_size,
            )
            # Evictar lowest priority
            await self._evict_lowest_priority()

        # Criar pending replay
        pending = PendingReplay(
            workflow_id=workflow_id,
            original_run_id=run_id,
            failure_reason=failure_reason,
            model_version_at_failure=model_version,
            plan_id=plan_id,
            priority=priority,
            estimated_impact=estimated_impact,
            context=context,
        )

        self._pending_replays[workflow_id] = pending
        self._metrics["total_pending"] = len(self._pending_replays)

        logger.info(
            "workflow_registered_for_replay",
            workflow_id=workflow_id,
            priority=priority.value,
            queue_size=len(self._pending_replays),
        )

        return {
            "status": "registered",
            "workflow_id": workflow_id,
            "priority": priority.value,
            "queue_position": self._get_queue_position(pending),
        }

    async def check_model_improvement(
        self,
        old_model_version: str,
        new_model_version: str,
        metrics_old: dict[str, float],
        metrics_new: dict[str, float],
    ) -> ModelImprovement:
        """
        Verifica se o novo modelo é significativamente melhor.

        Args:
            old_model_version: Versão do modelo antigo
            new_model_version: Versão do novo modelo
            metrics_old: Métricas do modelo antigo
            metrics_new: Métricas do novo modelo

        Returns:
            Nível de melhoria
        """
        # Métricas chave para comparação
        key_metrics = [
            "accuracy",
            "precision",
            "recall",
            "f1_score",
            "quality_score",
            "success_rate",
        ]

        improvements = []

        for metric in key_metrics:
            if metric in metrics_old and metric in metrics_new:
                old_val = metrics_old[metric]
                new_val = metrics_new[metric]

                if old_val > 0:
                    improvement_pct = ((new_val - old_val) / old_val) * 100
                    improvements.append(improvement_pct)

        if not improvements:
            return ModelImprovement.NONE

        avg_improvement = sum(improvements) / len(improvements)

        if avg_improvement > 20:
            return ModelImprovement.SIGNIFICANT
        elif avg_improvement > 10:
            return ModelImprovement.MODERATE
        elif avg_improvement > 0:
            return ModelImprovement.MINIMAL
        elif avg_improvement < -5:
            return ModelImprovement.REGRESSION
        else:
            return ModelImprovement.NONE

    async def on_model_updated(
        self,
        new_model_version: str,
        metrics_old: dict[str, float],
        metrics_new: dict[str, float],
    ) -> dict[str, Any]:
        """
        Callback quando modelo é retreinado.

        Verifica workflows pendentes e dispara replay se
        o modelo melhorou significativamente.

        Args:
            new_model_version: Nova versão do modelo
            metrics_old: Métricas do modelo antigo
            metrics_new: Métricas do novo modelo

        Returns:
            Dict com workflows agendados para replay
        """
        logger.info(
            "model_updated",
            new_model_version=new_model_version,
            pending_workflows=len(self._pending_replays),
        )

        # Verificar nível de melhoria
        improvement = await self.check_model_improvement(
            "", new_model_version, metrics_old, metrics_new
        )

        logger.info(
            "model_improvement_assessed",
            improvement=improvement.value,
            threshold=self._improvement_threshold.value,
        )

        # Se não houver melhoria suficiente, não fazer replay
        if improvement.value not in [
            ModelImprovement.SIGNIFICANT.value,
            ModelImprovement.MODERATE.value,
        ]:
            return {
                "status": "no_replay",
                "reason": f"Model improvement not sufficient: {improvement.value}",
                "threshold": self._improvement_threshold.value,
            }

        # Encontrar workflows que podem ser replays
        workflows_to_replay = []

        for pending in self._pending_replays.values():
            # Pular se não é devido a modelo
            if "model" not in pending.failure_reason.lower():
                continue

            # Pular se já tentou muitas vezes
            if len(pending.replay_attempts) >= self._max_replay_attempts:
                continue

            workflows_to_replay.append(pending)

        # Ordenar por prioridade e impacto
        workflows_to_replay.sort(
            key=lambda p: (
                -self._priority_score(p.priority),
                -p.estimated_impact,
                p.created_at,
            )
        )

        # Limitar número de replays simultâneos
        max_concurrent = 10
        scheduled = workflows_to_replay[:max_concurrent]

        results = []

        for pending in scheduled:
            result = await self._schedule_replay(pending, new_model_version)
            results.append(result)

        return {
            "status": "replay_scheduled",
            "improvement": improvement.value,
            "total_pending": len(self._pending_replays),
            "scheduled_count": len(scheduled),
            "workflows": [r["workflow_id"] for r in results],
        }

    async def _schedule_replay(
        self, pending: PendingReplay, new_model_version: str
    ) -> dict[str, Any]:
        """Agenda um workflow para replay."""
        logger.info(
            "scheduling_replay",
            workflow_id=pending.workflow_id,
            new_model_version=new_model_version,
        )

        pending.status = ReplayStatus.SCHEDULED
        pending.last_model_version_checked = new_model_version

        # Em produção, isso chamaria Temporal para executar o replay
        replay_id = f"replay-{pending.workflow_id}-{new_model_version}"

        result = {
            "workflow_id": pending.workflow_id,
            "replay_id": replay_id,
            "new_model_version": new_model_version,
            "status": "scheduled",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        }

        pending.replay_attempts.append(result)

        return result

    async def record_replay_result(
        self,
        workflow_id: str,
        replay_id: str,
        success: bool,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Registra resultado de um replay.

        Args:
            workflow_id: ID do workflow
            replay_id: ID do replay
            success: Se foi bem-sucedido
            result: Resultado do replay

        Returns:
            Dict com status
        """
        logger.info(
            "recording_replay_result",
            workflow_id=workflow_id,
            replay_id=replay_id,
            success=success,
        )

        pending = self._pending_replays.get(workflow_id)
        if not pending:
            logger.warning("workflow_not_found_in_pending", workflow_id=workflow_id)
            return {"status": "not_found"}

        # Atualizar último attempt
        for attempt in pending.replay_attempts:
            if attempt.get("replay_id") == replay_id:
                attempt["success"] = success
                attempt["result"] = result
                attempt["completed_at"] = datetime.now(timezone.utc).isoformat()
                break

        if success:
            pending.status = ReplayStatus.COMPLETED
            # Remover da fila de pendentes
            self._pending_replays.pop(workflow_id, None)
            self._metrics["total_successful"] += 1
        else:
            pending.status = ReplayStatus.FAILED
            self._metrics["total_failed"] += 1

            # Se excedeu tentativas, remover
            if len(pending.replay_attempts) >= self._max_replay_attempts:
                self._pending_replays.pop(workflow_id, None)

        self._metrics["total_pending"] = len(self._pending_replays)
        self._metrics["total_replayed"] += 1

        # Adicionar ao histórico
        self._replay_history.append(
            {
                "workflow_id": workflow_id,
                "replay_id": replay_id,
                "success": success,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        return {
            "status": "recorded",
            "workflow_id": workflow_id,
            "success": success,
            "remaining_attempts": (
                self._max_replay_attempts - len(pending.replay_attempts)
                if pending in self._pending_replays.values()
                else 0
            ),
        }

    def get_pending_replays(
        self, priority: ReplayPriority | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Retorna lista de replays pendentes."""
        pending = list(self._pending_replays.values())

        if priority:
            pending = [p for p in pending if p.priority == priority]

        # Ordenar por prioridade e data
        pending.sort(
            key=lambda p: (
                -self._priority_score(p.priority),
                -p.estimated_impact,
                p.created_at,
            )
        )

        return [p.to_dict() for p in pending[:limit]]

    def get_metrics(self) -> dict[str, Any]:
        """Retorna métricas do serviço."""
        return {
            **self._metrics,
            "queue_size": len(self._pending_replays),
            "total_pending": len(self._pending_replays),  # Usar tamanho atual
            "by_priority": {
                priority.value: len(
                    [p for p in self._pending_replays.values() if p.priority == priority]
                )
                for priority in ReplayPriority
            },
        }

    def _priority_score(self, priority: ReplayPriority) -> int:
        """Converte prioridade para score numérico."""
        scores = {
            ReplayPriority.CRITICAL: 4,
            ReplayPriority.HIGH: 3,
            ReplayPriority.MEDIUM: 2,
            ReplayPriority.LOW: 1,
        }
        return scores.get(priority, 0)

    async def _evict_lowest_priority(self):
        """Remove o replay de menor prioridade da fila."""
        if not self._pending_replays:
            return

        # Encontrar lowest priority
        lowest = min(
            self._pending_replays.values(),
            key=lambda p: (self._priority_score(p.priority), -p.estimated_impact),
        )

        logger.info(
            "evicting_lowest_priority_replay",
            workflow_id=lowest.workflow_id,
            priority=lowest.priority.value,
        )

        self._pending_replays.pop(lowest.workflow_id, None)

    def _get_queue_position(self, pending: PendingReplay) -> int:
        """Retorna posição na fila baseado em prioridade."""
        higher_priority = [
            p
            for p in self._pending_replays.values()
            if self._priority_score(p.priority) > self._priority_score(pending.priority)
            or (
                self._priority_score(p.priority) == self._priority_score(pending.priority)
                and p.estimated_impact > pending.estimated_impact
            )
        ]
        return len(higher_priority) + 1
