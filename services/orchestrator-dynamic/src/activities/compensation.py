"""
Activities Temporal para compensacao automatica (Saga Pattern).

Implementa logica de compensacao para reverter operacoes falhadas
seguindo ordenacao topologica reversa das dependencias.
"""
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from temporalio import activity

from src.clients.kafka_producer import KafkaProducerClient
from src.config.settings import get_settings
from src.saga.retry_config import SagaRetryConfig
from src.saga.retry_policy import RetryError, RetryPolicy

logger = structlog.get_logger()

_config = None
_kafka_producer: KafkaProducerClient | None = None
_mongodb_client = None
_metrics = None
_retry_policy: RetryPolicy | None = None


def set_compensation_dependencies(
    config=None,
    kafka_producer: KafkaProducerClient = None,
    mongodb_client=None,
    metrics=None,
    retry_policy: RetryPolicy | None = None,
) -> None:
    """
    Injeta dependencias globais para activities de compensacao.

    Args:
        config: OrchestratorSettings
        kafka_producer: KafkaProducerClient para publicacao de tickets
        mongodb_client: MongoDBClient para persistencia
        metrics: OrchestratorMetrics para metricas
        retry_policy: RetryPolicy para retries de compensacao
    """
    global _config, _kafka_producer, _mongodb_client, _metrics, _retry_policy
    _config = config
    _kafka_producer = kafka_producer
    _mongodb_client = mongodb_client
    _metrics = metrics
    _retry_policy = retry_policy or RetryPolicy()


def _get_retry_policy() -> RetryPolicy:
    """Retorna a politica de retry ou cria uma default."""
    global _retry_policy
    if _retry_policy is None:
        config = _config or get_settings()
        retry_config = SagaRetryConfig(
            max_attempts=getattr(config, "saga_retry_max_attempts", 3),
            initial_delay_ms=getattr(config, "saga_retry_initial_delay_ms", 1000),
            max_delay_ms=getattr(config, "saga_retry_max_delay_ms", 30000),
        )
        _retry_policy = RetryPolicy(config=retry_config)
    return _retry_policy


def _get_compensation_action(task_type: str, original_params: dict[str, Any]) -> dict[str, Any]:
    """
    Determina acao de compensacao baseado no task_type original.

    Args:
        task_type: Tipo da tarefa original (BUILD, DEPLOY, TEST, etc)
        original_params: Parametros originais do ticket

    Returns:
        Dict com action e parameters para compensacao
    """
    if task_type == "BUILD":
        return {
            "action": "delete_artifacts",
            "artifact_ids": original_params.get("artifact_ids", []),
            "registry_url": original_params.get("registry_url", ""),
            "image_tag": original_params.get("image_tag", ""),
            "repository": original_params.get("repository", ""),
        }

    if task_type == "DEPLOY":
        return {
            "action": "rollback_deployment",
            "deployment_name": original_params.get("deployment_name", ""),
            "previous_revision": original_params.get("previous_revision", "HEAD~1"),
            "namespace": original_params.get("namespace", "default"),
            "provider": original_params.get("provider", "argocd"),
            "cluster_server": original_params.get("cluster_server", ""),
        }

    if task_type == "TEST":
        return {
            "action": "cleanup_test_env",
            "test_id": original_params.get("test_id", ""),
            "namespace": original_params.get("namespace", "default"),
            "resources": original_params.get("resources", []),
            "cleanup_jobs": original_params.get("cleanup_jobs", True),
        }

    if task_type == "VALIDATE":
        return {
            "action": "revert_approval",
            "approval_id": original_params.get("approval_id", ""),
            "validation_id": original_params.get("validation_id", ""),
            "revert_status": "PENDING",
        }

    if task_type == "EXECUTE":
        return {
            "action": "rollback_execution",
            "execution_id": original_params.get("execution_id", ""),
            "rollback_script": original_params.get("rollback_script", ""),
            "working_dir": original_params.get("working_dir", ""),
            "cleanup_outputs": original_params.get("cleanup_outputs", True),
        }

    return {
        "action": "generic_cleanup",
        "original_task_type": task_type,
        "original_params": original_params,
    }


@activity.defn
async def compensate_ticket(
    ticket: dict[str, Any], reason: str, retry_config: dict[str, Any] | None = None
) -> str:
    """
    Cria e publica ticket de compensacao para reverter operacao falhada.

    Usa RetryPolicy para operacoes de Kafka e MongoDB com backoff exponencial.

    Args:
        ticket: Ticket original que falhou
        reason: Motivo da compensacao (ex: 'task_failed', 'workflow_inconsistent')
        retry_config: Configuracao opcional de retry (max_attempts, initial_delay_ms, etc)

    Returns:
        ID do ticket de compensacao criado
    """
    global _config, _kafka_producer, _mongodb_client, _metrics

    _config or get_settings()
    ticket_id = ticket.get("ticket_id", "unknown")
    task_type = ticket.get("task_type", "UNKNOWN")
    original_params = ticket.get("parameters", {})

    logger.info(
        f"compensation.creating_ticket ticket_id={ticket_id} task_type={task_type} reason={reason}"
    )

    # Configurar retry policy
    retry_policy = _get_retry_policy()
    if retry_config:
        from src.saga.retry_config import SagaRetryConfig

        custom_config = SagaRetryConfig(**retry_config)
        retry_policy = RetryPolicy(config=custom_config)

    try:
        # Determinar acao de compensacao
        compensation_data = _get_compensation_action(task_type, original_params)
        compensation_data["reason"] = reason
        compensation_data["original_ticket_id"] = ticket_id
        compensation_data["original_task_type"] = task_type

        # Criar ticket de compensacao
        compensation_ticket_id = str(uuid4())
        compensation_ticket = {
            "ticket_id": compensation_ticket_id,
            "task_id": f"compensate-{ticket_id[:8]}",
            "plan_id": ticket.get("plan_id"),
            "intent_id": ticket.get("intent_id"),
            "task_type": "COMPENSATE",
            "status": "PENDING",
            "priority": ticket.get("priority", "HIGH"),
            "risk_band": ticket.get("risk_band", "high"),
            "parameters": compensation_data,
            "dependencies": [],  # Compensacao nao tem dependencias
            "compensation_ticket_id": None,  # E o ticket de compensacao
            "original_ticket_id": ticket_id,
            "sla": {"timeout_ms": 120000, "deadline": None},  # 2 minutos para compensacao
            "created_at": int(datetime.now(UTC).timestamp() * 1000),
            "metadata": {
                "compensation_reason": reason,
                "original_task_type": task_type,
                "original_status": ticket.get("status", "FAILED"),
            },
        }

        # Registrar metrica (sem retry)
        if _metrics:
            try:
                _metrics.record_compensation(reason=reason)
            except Exception as metric_err:
                logger.warning(f"compensation.metric_failed error={metric_err}")

        # Persistir no MongoDB com retry
        if _mongodb_client:

            async def persist_ticket() -> bool:
                await _mongodb_client.save_ticket(compensation_ticket)
                logger.info(f"compensation.ticket_persisted ticket_id={compensation_ticket_id}")
                return True

            try:
                await retry_policy.execute(
                    persist_ticket, operation_name="compensation_mongodb_persist"
                )
            except RetryError as mongo_err:
                logger.warning(
                    f"compensation.mongodb_persist_failed_after_retries ticket_id={compensation_ticket_id} error={mongo_err}"
                )
                # Fail-open: continuar mesmo se MongoDB falhar

        # Publicar no Kafka com retry
        if _kafka_producer:

            async def publish_to_kafka() -> bool:
                publish_result = await _kafka_producer.publish_ticket(compensation_ticket)
                if not publish_result:
                    raise ValueError("kafka_publish_returned_false")
                logger.info(f"compensation.ticket_published ticket_id={compensation_ticket_id}")
                return publish_result

            try:
                await retry_policy.execute(
                    publish_to_kafka, operation_name="compensation_kafka_publish"
                )
            except RetryError as kafka_err:
                logger.exception(
                    f"compensation.kafka_failed_after_retries ticket_id={compensation_ticket_id} error={kafka_err}"
                )
                # Fail-open: ticket foi persistido no MongoDB
        else:
            logger.warning(
                f"compensation.kafka_producer_unavailable ticket_id={compensation_ticket_id}"
            )

        logger.info(
            f'compensation.ticket_created original_ticket_id={ticket_id} compensation_ticket_id={compensation_ticket_id} action={compensation_data.get("action")}'
        )

        return compensation_ticket_id

    except Exception as e:
        logger.error(f"compensation.failed ticket_id={ticket_id} error={e}", exc_info=True)
        raise


@activity.defn
async def build_compensation_order(
    failed_tickets: list[dict[str, Any]], all_tickets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Constroi ordem de compensacao usando ordenacao topologica reversa.

    Tickets que dependem de outros devem ser compensados primeiro.
    Exemplo: Se A -> B -> C e C falhou, compensar na ordem: C, B, A

    Args:
        failed_tickets: Tickets que falharam
        all_tickets: Todos os tickets publicados

    Returns:
        Lista de tickets ordenada para compensacao (ordem reversa de execucao)
    """
    logger.info(
        f"compensation.building_order failed_count={len(failed_tickets)} total_count={len(all_tickets)}"
    )

    try:
        # Construir mapa de tickets por ID
        ticket_map: dict[str, dict[str, Any]] = {}
        for t in all_tickets:
            ticket_data = t.get("ticket", t)
            ticket_id = ticket_data.get("ticket_id")
            if ticket_id:
                ticket_map[ticket_id] = ticket_data

        # Construir grafo de dependencias (ticket_id -> dependentes)
        dependents: dict[str, list[str]] = {}
        for ticket_id in ticket_map:
            dependents[ticket_id] = []

        for ticket_id, ticket_data in ticket_map.items():
            dependencies = ticket_data.get("dependencies", [])
            for dep_id in dependencies:
                if dep_id in dependents:
                    dependents[dep_id].append(ticket_id)

        # Identificar tickets a compensar
        # Incluir tickets falhados e seus predecessores (que podem ter sido executados)
        tickets_to_compensate: list[str] = []
        visited: set = set()

        def collect_predecessors(ticket_id: str):
            """Coleta ticket e todos seus predecessores recursivamente."""
            if ticket_id in visited:
                return
            visited.add(ticket_id)

            ticket_data = ticket_map.get(ticket_id)
            if not ticket_data:
                return

            # Adicionar ticket atual
            tickets_to_compensate.append(ticket_id)

            # Coletar predecessores (dependencias)
            dependencies = ticket_data.get("dependencies", [])
            for dep_id in dependencies:
                collect_predecessors(dep_id)

        # Coletar a partir de tickets falhados
        for failed in failed_tickets:
            failed_data = failed.get("ticket", failed)
            failed_id = failed_data.get("ticket_id")
            if failed_id:
                collect_predecessors(failed_id)

        # Ordenar por ordem topologica reversa (DFS pos-order reverso)
        # Tickets executados por ultimo devem ser compensados primeiro
        order: list[str] = []
        visited_order: set = set()

        def dfs_post_order(ticket_id: str):
            if ticket_id in visited_order:
                return
            visited_order.add(ticket_id)

            # Visitar dependencias primeiro
            ticket_data = ticket_map.get(ticket_id)
            if ticket_data:
                for dep_id in ticket_data.get("dependencies", []):
                    if dep_id in tickets_to_compensate:
                        dfs_post_order(dep_id)

            # Adicionar apos visitar dependencias
            order.append(ticket_id)

        for ticket_id in tickets_to_compensate:
            dfs_post_order(ticket_id)

        # Reverter ordem (ultimo executado primeiro)
        order.reverse()

        # Filtrar apenas tickets que foram executados (status != PENDING)
        result = []
        for ticket_id in order:
            ticket_data = ticket_map.get(ticket_id)
            if ticket_data:
                status = ticket_data.get("status", "PENDING")
                # Compensar tickets que foram executados (COMPLETED, FAILED, RUNNING)
                if status in ["COMPLETED", "FAILED", "RUNNING", "COMPENSATING"]:
                    result.append(ticket_data)

        logger.info(
            f'compensation.order_built total_to_compensate={len(result)} order={[t.get("ticket_id", "?")[:8] for t in result]}'
        )

        return result

    except Exception as e:
        logger.error(f"compensation.build_order_failed error={e}", exc_info=True)
        # Fallback: retornar tickets falhados na ordem original
        return [t.get("ticket", t) for t in failed_tickets]


@activity.defn
async def update_ticket_compensation_status(ticket_id: str, compensation_ticket_id: str) -> bool:
    """
    Atualiza ticket original com referencia ao ticket de compensacao.

    Args:
        ticket_id: ID do ticket original
        compensation_ticket_id: ID do ticket de compensacao criado

    Returns:
        True se atualizado com sucesso
    """
    global _mongodb_client

    logger.info(
        f"compensation.updating_original_ticket ticket_id={ticket_id} compensation_ticket_id={compensation_ticket_id}"
    )

    try:
        if _mongodb_client:
            await _mongodb_client.update_ticket_compensation(
                ticket_id=ticket_id,
                compensation_ticket_id=compensation_ticket_id,
                status="COMPENSATING",
            )
            logger.info(f"compensation.original_ticket_updated ticket_id={ticket_id}")
            return True
        logger.warning(f"compensation.mongodb_unavailable ticket_id={ticket_id}")
        return False

    except Exception as e:
        logger.exception(f"compensation.update_failed ticket_id={ticket_id} error={e}")
        return False
