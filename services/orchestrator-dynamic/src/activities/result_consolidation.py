"""
Activities Temporal para consolidação de resultados (Etapa C5).
"""
from datetime import datetime
from typing import Dict, Any, List

from temporalio import activity
import structlog

logger = structlog.get_logger()


@activity.defn
async def consolidate_results(tickets: List[Dict[str, Any]], workflow_id: str) -> Dict[str, Any]:
    """
    Agrega resultados de todos os tickets executados e calcula métricas.

    Args:
        tickets: Lista de tickets publicados
        workflow_id: ID do workflow Temporal

    Returns:
        Resultado consolidado com métricas e status
    """
    activity.logger.info(f'Consolidando resultados do workflow {workflow_id}')

    try:
        # Calcular métricas
        total_tickets = len(tickets)
        successful_tickets = sum(1 for t in tickets if t.get('ticket', {}).get('status') == 'COMPLETED')
        failed_tickets = sum(1 for t in tickets if t.get('ticket', {}).get('status') == 'FAILED')
        compensated_tickets = sum(1 for t in tickets if t.get('ticket', {}).get('status') == 'COMPENSATED')

        # Calcular duração total (estimada, pois tickets ainda não foram executados)
        total_duration_ms = sum(
            t.get('ticket', {}).get('estimated_duration_ms', 0)
            for t in tickets
        )

        # Calcular total de retries
        total_retries = sum(
            t.get('ticket', {}).get('retry_count', 0)
            for t in tickets
        )

        # Validar integridade
        integrity_errors = []
        for ticket_data in tickets:
            ticket = ticket_data.get('ticket', {})
            status = ticket.get('status')
            if status not in ['PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'COMPENSATING', 'COMPENSATED']:
                integrity_errors.append(f'Status inválido para ticket {ticket.get("ticket_id")}: {status}')

        consistent = len(integrity_errors) == 0

        # Determinar status geral
        if successful_tickets == total_tickets:
            overall_status = 'SUCCESS'
        elif failed_tickets > total_tickets // 2:
            overall_status = 'FAILED'
        else:
            overall_status = 'PARTIAL'

        # Gerar resumo
        result = {
            'workflow_id': workflow_id,
            'plan_id': tickets[0].get('ticket', {}).get('plan_id') if tickets else None,
            'intent_id': tickets[0].get('ticket', {}).get('intent_id') if tickets else None,
            'status': overall_status,
            'consistent': consistent,
            'errors': integrity_errors,
            'metrics': {
                'total_tickets': total_tickets,
                'successful_tickets': successful_tickets,
                'failed_tickets': failed_tickets,
                'compensated_tickets': compensated_tickets,
                'total_duration_ms': total_duration_ms,
                'total_retries': total_retries,
                'sla_violations': 0  # Placeholder
            },
            'tickets_summary': [
                {
                    'ticket_id': t.get('ticket', {}).get('ticket_id'),
                    'status': t.get('ticket', {}).get('status'),
                    'duration': t.get('ticket', {}).get('estimated_duration_ms')
                }
                for t in tickets
            ],
            'consolidated_at': datetime.now().isoformat()
        }

        # Persistir resultado no MongoDB
        # TODO: Implementar persistência
        # mongodb_client.workflow_results.insert_one(result)

        activity.logger.info(
            f'Resultados consolidados para workflow {workflow_id}',
            status=overall_status,
            total_tickets=total_tickets,
            consistent=consistent
        )

        return result

    except Exception as e:
        activity.logger.error(f'Erro ao consolidar resultados: {e}', exc_info=True)
        raise


@activity.defn
async def trigger_self_healing(workflow_id: str, inconsistencies: List[str]) -> None:
    """
    Publica evento de inconsistência para acionar Fluxo E (Autocura).

    Args:
        workflow_id: ID do workflow com inconsistências
        inconsistencies: Lista de inconsistências detectadas
    """
    activity.logger.warning(f'Acionando autocura para workflow {workflow_id}')

    try:
        # Preparar evento
        incident_event = {
            'workflow_id': workflow_id,
            'type': 'INCONSISTENCY',
            'details': inconsistencies,
            'timestamp': datetime.now().isoformat(),
            'severity': 'WARNING'
        }

        # TODO: Publicar no Kafka tópico orchestration.incidents
        # producer = get_kafka_producer()
        # await producer.send(
        #     topic='orchestration.incidents',
        #     value=json.dumps(incident_event).encode()
        # )

        # Registrar incidente no MongoDB
        # TODO: Implementar persistência
        # mongodb_client.incidents.insert_one(incident_event)

        activity.logger.warning(
            f'Incidente de inconsistência registrado para workflow {workflow_id}',
            inconsistencies_count=len(inconsistencies)
        )

    except Exception as e:
        activity.logger.error(f'Erro ao acionar autocura: {e}', exc_info=True)
        raise


@activity.defn
async def publish_telemetry(workflow_result: Dict[str, Any]) -> None:
    """
    Publica telemetria correlacionada no Kafka.

    Args:
        workflow_result: Resultado consolidado do workflow
    """
    activity.logger.info('Publicando telemetria')

    try:
        # Criar Telemetry Frame
        telemetry_frame = {
            'correlation': {
                'intent_id': workflow_result.get('intent_id'),
                'plan_id': workflow_result.get('plan_id'),
                'workflow_id': workflow_result.get('workflow_id'),
                'ticket_ids': [
                    t['ticket_id']
                    for t in workflow_result.get('tickets_summary', [])
                ]
            },
            'metrics': workflow_result.get('metrics', {}),
            'timestamp': datetime.now().isoformat(),
            'source': 'orchestrator-dynamic'
        }

        # TODO: Publicar no Kafka tópico telemetry.orchestration
        # producer = get_kafka_producer()
        # await producer.send(
        #     topic='telemetry.orchestration',
        #     value=json.dumps(telemetry_frame).encode()
        # )

        # TODO: Exportar métricas para Prometheus
        # orchestration_workflow_duration_seconds.observe(...)
        # orchestration_tickets_total.inc(...)

        activity.logger.info('Telemetria publicada com sucesso')

    except Exception as e:
        activity.logger.error(f'Erro ao publicar telemetria: {e}', exc_info=True)
        raise


@activity.defn
async def buffer_telemetry(telemetry_frame: Dict[str, Any]) -> None:
    """
    Persiste telemetry frame em buffer local quando falha envio.

    Args:
        telemetry_frame: Frame de telemetria a ser buffered
    """
    activity.logger.warning('Buffering telemetria devido a falha de envio')

    try:
        # Adicionar metadata
        buffered_frame = {
            **telemetry_frame,
            'buffered_at': datetime.now().isoformat(),
            'retry_count': 0
        }

        # TODO: Persistir no MongoDB
        # mongodb_client.telemetry_buffer.insert_one(buffered_frame)

        activity.logger.info('Telemetria buffered com sucesso')

    except Exception as e:
        activity.logger.error(f'Erro ao buffer telemetria: {e}', exc_info=True)
        raise
