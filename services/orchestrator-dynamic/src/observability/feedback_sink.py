"""
FeedbackSink — ponto único transversal do loop OBSERVE→LEARN (plano-Z).

Spec: docs/specs/2026-06-22-fundacao-loop-learn — Fase 0 (Fundação).
ADR: docs/adr/ADR-0011 — princípio Fundação → Roteamento → Capacidades.

Capability-agnostic: EXECUTE/GENERATE/MIGRATE emitem o MESMO contrato
(ExecutionFeedback) através do MESMO sink. A persistência vive aqui, fora de
qualquer capacidade — não dentro do execution_result_consumer (que é EXECUTE).

Garantias:
- Idempotente: update_one por ticket_id (at-least-once safe; não duplica).
- Desacoplado: uma falha de persistência NUNCA propaga (o workflow não pode
  ficar refém de telemetria).
- Anti-verde-falso: marca result_simulated (persistido para observabilidade,
  excluído do treino pelo duration_predictor).
"""

import structlog

from src.models.execution_feedback import ExecutionFeedback

logger = structlog.get_logger(__name__)


class FeedbackSink:
    """Persiste ExecutionFeedback no corpus canónico que o loop LEARN consome."""

    # Hoje reutiliza execution_tickets (o duration_predictor já a lê).
    # Evolução futura: apontar para "execution_feedback" sem tocar nos emissores.
    COLLECTION = "execution_tickets"

    def __init__(self, mongodb_client, metrics=None):
        self.mongodb_client = mongodb_client
        self.metrics = metrics

    async def record(self, feedback: ExecutionFeedback) -> None:
        """Persiste o feedback por ticket_id. Falha de Mongo é engolida (log)."""
        if not feedback.ticket_id:
            return

        update = {
            "capability": feedback.capability,
            "journey_id": feedback.journey_id,
            "status": feedback.status,
            "actual_duration_ms": feedback.actual_duration_ms,
            "started_at": feedback.started_at,
            "completed_at": feedback.completed_at,
            "result_simulated": feedback.simulated,
            "feedback_persisted_at": feedback.feedback_persisted_at,
        }

        try:
            await self.mongodb_client.db[self.COLLECTION].update_one(
                {"ticket_id": feedback.ticket_id},
                {"$set": update},
                upsert=False,
            )
            if self.metrics is not None:
                metric = getattr(
                    self.metrics, "execution_feedback_persisted_total", None
                )
                if metric is not None:
                    metric.labels(
                        capability=feedback.capability,
                        simulated=str(feedback.simulated).lower(),
                    ).inc()
        except Exception as e:  # — telemetria nunca bloqueia o fluxo
            logger.warning(
                "feedback_sink_persist_failed",
                ticket_id=feedback.ticket_id,
                capability=feedback.capability,
                error=str(e),
            )
