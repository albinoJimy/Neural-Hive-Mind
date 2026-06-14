"""Activity para publicar eventos de otimização no Kafka."""

import logging
from typing import Any

from temporalio import activity

from src.config.settings import get_settings
from src.producers.optimization_producer import OptimizationProducer

logger = logging.getLogger(__name__)

# Producer singleton
_producer: OptimizationProducer | None = None


async def get_optimization_producer() -> OptimizationProducer:
    """Retorna instância singleton do OptimizationProducer."""
    global _producer
    if _producer is None:
        settings = get_settings()
        _producer = OptimizationProducer(settings)
        await _producer.initialize()
    return _producer


async def publish_ticket_completed_event(
    ticket: dict[str, Any], workflow_id: str
) -> dict[str, Any]:
    """
    Publica evento ticket.completed no Kafka para análise de otimização.

    Esta activity é chamada quando um ticket é completado, permitindo que
    o optimizer-agents analise a execução e gere recomendações de otimização.

    Args:
        ticket: Dados do ticket executado
        workflow_id: ID do workflow Temporal

    Returns:
        Dict com status da publicação
    """
    ticket_id = ticket.get("ticket_id", "unknown")
    status = ticket.get("status", "UNKNOWN")

    logger.info(
        f"publishing_ticket_completed ticket_id={ticket_id} "
        f"workflow_id={workflow_id} status={status}"
    )

    try:
        producer = await get_optimization_producer()

        # Extrair tarefas do ticket
        tasks = ticket.get("tasks", [])
        tasks_data = []
        for task in tasks:
            tasks_data.append(
                {
                    "task_id": task.get("task_id"),
                    "executor_type": task.get("executor_type"),
                    "duration_ms": task.get("duration_ms", 0),
                    "file_path": task.get("execution_context", {}).get("file_path"),
                    "collection": task.get("execution_context", {}).get("collection"),
                    "query": task.get("execution_context", {}).get("query"),
                }
            )

        # Publicar evento
        await producer.publish_ticket_completed(
            ticket_id=ticket_id,
            workflow_id=workflow_id,
            status=status,
            duration_ms=ticket.get("actual_duration_ms", ticket.get("estimated_duration_ms", 0)),
            peak_memory_mb=ticket.get("peak_memory_mb", 0),
            task_count=len(tasks_data),
            tasks=tasks_data,
        )

        logger.info(
            f"ticket_completed_publishedSuccessfully ticket_id={ticket_id} "
            f"workflow_id={workflow_id} task_count={len(tasks_data)}"
        )

        return {
            "success": True,
            "ticket_id": ticket_id,
            "workflow_id": workflow_id,
            "published_at": ticket.get("completed_at"),
        }

    except Exception as e:
        logger.exception(
            f"failed_to_publish_ticket_completed ticket_id={ticket_id} "
            f"workflow_id={workflow_id} error={e}"
        )
        # Não falhar o workflow se a publicação falhar
        return {
            "success": False,
            "ticket_id": ticket_id,
            "workflow_id": workflow_id,
            "error": str(e),
        }


@activity.defn
async def publish_workflow_optimization_events(
    tickets: list[dict[str, Any]], workflow_id: str
) -> dict[str, Any]:
    """
    Publica eventos ticket.completed para múltiplos tickets.

    Esta activity é chamada após a consolidação dos resultados do workflow,
    publicando eventos de otimização para todos os tickets completados.

    Args:
        tickets: Lista de tickets publicados
        workflow_id: ID do workflow Temporal

    Returns:
        Dict com contagem de publicações bem-sucedidas e falhas
    """
    logger.info(
        f"publishing_workflow_optimization_events workflow_id={workflow_id} "
        f"ticket_count={len(tickets)}"
    )

    successful_count = 0
    failed_count = 0
    results = []

    for ticket_data in tickets:
        ticket = ticket_data.get("ticket", {})
        ticket_id = ticket.get("ticket_id", "unknown")
        status = ticket.get("status", "UNKNOWN")

        # Publicar apenas tickets completados ou falhados (ignorar pendentes)
        if status not in ["COMPLETED", "FAILED", "COMPENSATED"]:
            continue

        try:
            result = await publish_ticket_completed_event(ticket, workflow_id)
            if result.get("success"):
                successful_count += 1
            else:
                failed_count += 1
            results.append(result)
        except Exception as e:
            logger.exception(
                f"exception_publishing_optimization_event ticket_id={ticket_id} error={e}"
            )
            failed_count += 1

    logger.info(
        f"optimization_events_published workflow_id={workflow_id} "
        f"successful={successful_count} failed={failed_count}"
    )

    return {
        "workflow_id": workflow_id,
        "total_tickets": len(tickets),
        "successful_count": successful_count,
        "failed_count": failed_count,
        "results": results,
    }
