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

from datetime import datetime, timezone

import structlog

from src.models.execution_feedback import ExecutionFeedback

logger = structlog.get_logger(__name__)


def _ms_to_datetime(ms: int | None) -> datetime | None:
    """Converte epoch millis (contrato portável) para BSON Date (tipo do cluster).

    execution_tickets.completed_at/started_at são gravados como Date pelos
    restantes escritores; o predictor filtra com datetime. O sink converte para
    casar com esse contrato — sem isto, o predictor não encontra os novos tickets.
    """
    if ms is None or ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        # timestamp corrompido (ex.: nanos por engano) — não cega o sink
        return None


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
            # started_at/completed_at gravados como BSON Date (tipo do cluster)
            "started_at": _ms_to_datetime(feedback.started_at),
            "completed_at": _ms_to_datetime(feedback.completed_at),
            "result_simulated": feedback.simulated,
            "feedback_persisted_at": feedback.feedback_persisted_at,
        }

        try:
            res = await self.mongodb_client.db[self.COLLECTION].update_one(
                {"ticket_id": feedback.ticket_id},
                {"$set": update},
                upsert=False,
            )
            # upsert=False: se o ticket ainda não existe no Mongo (race — worker
            # publicou antes do orchestrator gravar), o feedback perde-se. Logar
            # em vez de silenciar, para ser observável.
            if getattr(res, "matched_count", 1) == 0:
                logger.debug(
                    "feedback_sink_ticket_not_found", ticket_id=feedback.ticket_id
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
