"""
Activities Temporal para compensacao automatica (Saga Pattern).

Implementa logica de compensacao para reverter operacoes falhadas
seguindo ordenacao topologica reversa das dependencias.
"""
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4

from temporalio import activity
import structlog

from src.config.settings import get_settings
from src.clients.kafka_producer import KafkaProducerClient

logger = structlog.get_logger()

_config = None
_kafka_producer: Optional[KafkaProducerClient] = None
_mongodb_client = None
_metrics = None


def set_compensation_dependencies(
    config=None,
    kafka_producer: KafkaProducerClient = None,
    mongodb_client=None,
    metrics=None
) -> None:
    """
    Injeta dependencias globais para activities de compensacao.

    Args:
        config: OrchestratorSettings
        kafka_producer: KafkaProducerClient para publicacao de tickets
        mongodb_client: MongoDBClient para persistencia
        metrics: OrchestratorMetrics para metricas
    """
    global _config, _kafka_producer, _mongodb_client, _metrics
    _config = config
    _kafka_producer = kafka_producer
    _mongodb_client = mongodb_client
    _metrics = metrics


def _get_compensation_action(task_type: str, original_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Determina acao de compensacao baseado no task_type original.

    Args:
        task_type: Tipo da tarefa original (BUILD, DEPLOY, TEST, etc)
        original_params: Parametros originais do ticket

    Returns:
        Dict com action e parameters para compensacao
    """
    if task_type == 'BUILD':
        return {
            'action': 'delete_artifacts',
            'artifact_ids': original_params.get('artifact_ids', []),
            'registry_url': original_params.get('registry_url', ''),
            'image_tag': original_params.get('image_tag', ''),
            'repository': original_params.get('repository', '')
        }

    elif task_type == 'DEPLOY':
        return {
            'action': 'rollback_deployment',
            'deployment_name': original_params.get('deployment_name', ''),
            'previous_revision': original_params.get('previous_revision', 'HEAD~1'),
            'namespace': original_params.get('namespace', 'default'),
            'provider': original_params.get('provider', 'argocd'),
            'cluster_server': original_params.get('cluster_server', '')
        }

    elif task_type == 'TEST':
        return {
            'action': 'cleanup_test_env',
            'test_id': original_params.get('test_id', ''),
            'namespace': original_params.get('namespace', 'default'),
            'resources': original_params.get('resources', []),
            'cleanup_jobs': original_params.get('cleanup_jobs', True)
        }

    elif task_type == 'VALIDATE':
        return {
            'action': 'revert_approval',
            'approval_id': original_params.get('approval_id', ''),
            'validation_id': original_params.get('validation_id', ''),
            'revert_status': 'PENDING'
        }

    elif task_type == 'EXECUTE':
        return {
            'action': 'rollback_execution',
            'execution_id': original_params.get('execution_id', ''),
            'rollback_script': original_params.get('rollback_script', ''),
            'working_dir': original_params.get('working_dir', ''),
            'cleanup_outputs': original_params.get('cleanup_outputs', True)
        }

    else:
        return {
            'action': 'generic_cleanup',
            'original_task_type': task_type,
            'original_params': original_params
        }


@activity.defn
async def compensate_ticket(
    ticket: Dict[str, Any],
    reason: str
) -> str:
    """
    Cria e publica ticket de compensacao para reverter operacao falhada.

    Args:
        ticket: Ticket original que falhou
        reason: Motivo da compensacao (ex: 'task_failed', 'workflow_inconsistent')

    Returns:
        ID do ticket de compensacao criado
    """
    global _config, _kafka_producer, _mongodb_client, _metrics

    config = _config or get_settings()
    ticket_id = ticket.get('ticket_id', 'unknown')
    task_type = ticket.get('task_type', 'UNKNOWN')
    original_params = ticket.get('parameters', {})

    logger.info(
        f'compensation.creating_ticket ticket_id={ticket_id} task_type={task_type} reason={reason}'
    )

    try:
        # Determinar acao de compensacao
        compensation_data = _get_compensation_action(task_type, original_params)
        compensation_data['reason'] = reason
        compensation_data['original_ticket_id'] = ticket_id
        compensation_data['original_task_type'] = task_type

        # Criar ticket de compensacao
        compensation_ticket_id = str(uuid4())
        compensation_ticket = {
            'ticket_id': compensation_ticket_id,
            'task_id': f'compensate-{ticket_id[:8]}',
            'plan_id': ticket.get('plan_id'),
            'intent_id': ticket.get('intent_id'),
            'task_type': 'COMPENSATE',
            'status': 'PENDING',
            'priority': ticket.get('priority', 'HIGH'),
            'risk_band': ticket.get('risk_band', 'high'),
            'parameters': compensation_data,
            'dependencies': [],  # Compensacao nao tem dependencias
            'compensation_ticket_id': None,  # E o ticket de compensacao
            'original_ticket_id': ticket_id,
            'sla': {
                'timeout_ms': 120000,  # 2 minutos para compensacao
                'deadline': None
            },
            'created_at': int(datetime.utcnow().timestamp() * 1000),
            'metadata': {
                'compensation_reason': reason,
                'original_task_type': task_type,
                'original_status': ticket.get('status', 'FAILED')
            }
        }

        # Registrar metrica
        if _metrics:
            try:
                _metrics.record_compensation(reason=reason)
            except Exception as metric_err:
                logger.warning(
                    f'compensation.metric_failed error={metric_err}'
                )

        # Persistir no MongoDB (fail-open)
        if _mongodb_client:
            try:
                await _mongodb_client.save_ticket(compensation_ticket)
                logger.info(
                    f'compensation.ticket_persisted ticket_id={compensation_ticket_id}'
                )
            except Exception as mongo_err:
                logger.warning(
                    f'compensation.mongodb_persist_failed ticket_id={compensation_ticket_id} error={mongo_err}'
                )

        # Publicar no Kafka
        if _kafka_producer:
            try:
                publish_result = await _kafka_producer.publish_ticket(compensation_ticket)
                if publish_result:
                    logger.info(
                        f'compensation.ticket_published ticket_id={compensation_ticket_id}'
                    )
                else:
                    logger.warning(
                        f'compensation.kafka_publish_failed ticket_id={compensation_ticket_id}'
                    )
            except Exception as kafka_err:
                logger.error(
                    f'compensation.kafka_error ticket_id={compensation_ticket_id} error={kafka_err}'
                )
                # Fail-open: ticket foi persistido no MongoDB
        else:
            logger.warning(
                f'compensation.kafka_producer_unavailable ticket_id={compensation_ticket_id}'
            )

        logger.info(
            f'compensation.ticket_created original_ticket_id={ticket_id} compensation_ticket_id={compensation_ticket_id} action={compensation_data.get("action")}'
        )

        return compensation_ticket_id

    except Exception as e:
        logger.error(
            f'compensation.failed ticket_id={ticket_id} error={e}',
            exc_info=True
        )
        raise


@activity.defn
async def build_compensation_order(
    failed_tickets: List[Dict[str, Any]],
    all_tickets: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
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
        f'compensation.building_order failed_count={len(failed_tickets)} total_count={len(all_tickets)}'
    )

    try:
        # Construir mapa de tickets por ID
        ticket_map: Dict[str, Dict[str, Any]] = {}
        for t in all_tickets:
            ticket_data = t.get('ticket', t)
            ticket_id = ticket_data.get('ticket_id')
            if ticket_id:
                ticket_map[ticket_id] = ticket_data

        # Construir grafo de dependencias (ticket_id -> dependentes)
        dependents: Dict[str, List[str]] = {}
        for ticket_id in ticket_map:
            dependents[ticket_id] = []

        for ticket_id, ticket_data in ticket_map.items():
            dependencies = ticket_data.get('dependencies', [])
            for dep_id in dependencies:
                if dep_id in dependents:
                    dependents[dep_id].append(ticket_id)

        # Identificar tickets a compensar
        # Incluir tickets falhados e seus predecessores (que podem ter sido executados)
        tickets_to_compensate: List[str] = []
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
            dependencies = ticket_data.get('dependencies', [])
            for dep_id in dependencies:
                collect_predecessors(dep_id)

        # Coletar a partir de tickets falhados
        for failed in failed_tickets:
            failed_data = failed.get('ticket', failed)
            failed_id = failed_data.get('ticket_id')
            if failed_id:
                collect_predecessors(failed_id)

        # Ordenar por ordem topologica reversa (DFS pos-order reverso)
        # Tickets executados por ultimo devem ser compensados primeiro
        order: List[str] = []
        visited_order: set = set()

        def dfs_post_order(ticket_id: str):
            if ticket_id in visited_order:
                return
            visited_order.add(ticket_id)

            # Visitar dependencias primeiro
            ticket_data = ticket_map.get(ticket_id)
            if ticket_data:
                for dep_id in ticket_data.get('dependencies', []):
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
                status = ticket_data.get('status', 'PENDING')
                # Compensar tickets que foram executados (COMPLETED, FAILED, RUNNING)
                if status in ['COMPLETED', 'FAILED', 'RUNNING', 'COMPENSATING']:
                    result.append(ticket_data)

        logger.info(
            f'compensation.order_built total_to_compensate={len(result)} order={[t.get("ticket_id", "?")[:8] for t in result]}'
        )

        return result

    except Exception as e:
        logger.error(
            f'compensation.build_order_failed error={e}',
            exc_info=True
        )
        # Fallback: retornar tickets falhados na ordem original
        return [t.get('ticket', t) for t in failed_tickets]


@activity.defn
async def update_ticket_compensation_status(
    ticket_id: str,
    compensation_ticket_id: str
) -> bool:
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
        f'compensation.updating_original_ticket ticket_id={ticket_id} compensation_ticket_id={compensation_ticket_id}'
    )

    try:
        if _mongodb_client:
            await _mongodb_client.update_ticket_compensation(
                ticket_id=ticket_id,
                compensation_ticket_id=compensation_ticket_id,
                status='COMPENSATING'
            )
            logger.info(
                f'compensation.original_ticket_updated ticket_id={ticket_id}'
            )
            return True
        else:
            logger.warning(
                f'compensation.mongodb_unavailable ticket_id={ticket_id}'
            )
            return False

    except Exception as e:
        logger.error(
            f'compensation.update_failed ticket_id={ticket_id} error={e}'
        )
        return False
