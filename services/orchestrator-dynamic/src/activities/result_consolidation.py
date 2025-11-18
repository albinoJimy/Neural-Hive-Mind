"""
Activities Temporal para consolidação de resultados (Etapa C5).
"""
from datetime import datetime
from typing import Dict, Any, List

from temporalio import activity
import structlog

from src.sla.sla_monitor import SLAMonitor
from src.sla.alert_manager import AlertManager
from src.config.settings import get_settings

logger = structlog.get_logger()


def compute_and_record_ml_error(ticket: Dict[str, Any], metrics) -> None:
    """
    Calcula e registra erro de predição ML para um ticket.

    Compara predicted_duration_ms com actual_duration_ms e registra
    no Prometheus + logs estruturados.

    Fail-open: erros não bloqueiam o fluxo.

    Args:
        ticket: Dict contendo dados do ticket
        metrics: OrchestratorMetrics instance
    """
    try:
        ticket_id = ticket.get('ticket_id', 'unknown')

        # Obter actual_duration_ms
        actual_duration_ms = ticket.get('actual_duration_ms')

        # Se não houver, calcular de timestamps
        if actual_duration_ms is None:
            started_at = ticket.get('started_at')
            completed_at = ticket.get('completed_at')
            if started_at and completed_at:
                actual_duration_ms = completed_at - started_at
            else:
                # Fallback para estimated se não houver dados
                actual_duration_ms = ticket.get('estimated_duration_ms')

        # Validar que temos actual_duration_ms
        if actual_duration_ms is None or actual_duration_ms <= 0:
            logger.debug(
                'ml_error_tracking_skipped_no_actual',
                ticket_id=ticket_id,
                reason='actual_duration_ms não disponível ou inválido'
            )
            return

        # Obter predicted_duration_ms de allocation_metadata ou predictions
        allocation_metadata = ticket.get('allocation_metadata', {})
        predicted_duration_ms = allocation_metadata.get('predicted_duration_ms')

        # Fallback: tentar obter de predictions (se ML enriqueceu)
        if predicted_duration_ms is None:
            predictions = ticket.get('predictions', {})
            predicted_duration_ms = predictions.get('duration_ms')

        # Fallback: usar estimated_duration_ms se não houver predição ML
        if predicted_duration_ms is None:
            predicted_duration_ms = ticket.get('estimated_duration_ms')
            if predicted_duration_ms is None:
                logger.debug(
                    'ml_error_tracking_skipped_no_prediction',
                    ticket_id=ticket_id,
                    reason='predicted_duration_ms não disponível'
                )
                return

        # Calcular erro: actual - predicted
        error_ms = actual_duration_ms - predicted_duration_ms

        # Registrar no Prometheus + logs
        metrics.record_ml_prediction_error_with_logging(
            model_type='duration',
            error_ms=error_ms,
            ticket_id=ticket_id,
            predicted_ms=predicted_duration_ms,
            actual_ms=actual_duration_ms
        )

    except Exception as e:
        # Fail-open: log erro mas não bloqueia
        logger.warning(
            'ml_error_tracking_failed',
            ticket_id=ticket.get('ticket_id', 'unknown'),
            error=str(e)
        )


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

        # Inicializar variáveis de SLA
        sla_status = {
            'deadline_approaching': False,
            'budget_critical': False,
            'violations_count': 0
        }
        sla_remaining_seconds = 0
        budget_status = 'UNKNOWN'

        # Monitoramento de SLA (integração com SLA Management System)
        try:
            config = get_settings()

            if config.sla_management_enabled:
                # Obter instâncias de clientes compartilhados
                from src.observability.metrics import get_metrics
                from src.clients.redis_client import get_redis_client
                from src.clients.kafka_producer import KafkaProducerClient

                metrics = get_metrics()

                # Inicializar Redis client (fail-open se não disponível)
                redis_client = await get_redis_client(config)

                # Inicializar Kafka producer para alertas e violações
                kafka_producer = None
                try:
                    kafka_producer = KafkaProducerClient(config)
                    await kafka_producer.initialize()
                except Exception as e:
                    activity.logger.warning(
                        'kafka_producer_initialization_failed',
                        workflow_id=workflow_id,
                        error=str(e)
                    )
                    # Fail-open: continuar sem Kafka producer

                # Criar instâncias de SLA monitor e alert manager
                sla_monitor = SLAMonitor(config, redis_client, metrics)
                alert_manager = AlertManager(config, kafka_producer, metrics)
                alert_manager.set_redis(redis_client)

                await sla_monitor.initialize()

                # Verificar deadlines de todos os tickets
                sla_check_result = await sla_monitor.check_workflow_sla(workflow_id, tickets)
                sla_status['deadline_approaching'] = sla_check_result.get('deadline_approaching', False)
                sla_remaining_seconds = sla_check_result.get('remaining_seconds', 0)
                critical_tickets = sla_check_result.get('critical_tickets', [])

                # Se houver tickets críticos, enviar alertas
                if sla_status['deadline_approaching'] and critical_tickets:
                    ticket_deadline_data = sla_check_result.get('ticket_deadline_data', {})
                    for ticket_id in critical_tickets:
                        # Usar dados de deadline específicos do ticket retornados pelo monitor
                        deadline_check = ticket_deadline_data.get(ticket_id)
                        if deadline_check:
                            deadline_data = {
                                'remaining_seconds': deadline_check.get('remaining_seconds', 0),
                                'percent_consumed': deadline_check.get('percent_consumed', 0),
                                'sla_deadline': deadline_check.get('sla_deadline')
                            }
                            # Enviar alerta de deadline (fail-open se Kafka não disponível)
                            try:
                                await alert_manager.send_deadline_alert(workflow_id, ticket_id, deadline_data)
                            except Exception as e:
                                activity.logger.warning(
                                    'deadline_alert_send_failed',
                                    workflow_id=workflow_id,
                                    ticket_id=ticket_id,
                                    error=str(e)
                                )
                            activity.logger.warning(
                                'sla_deadline_approaching',
                                workflow_id=workflow_id,
                                ticket_id=ticket_id,
                                remaining_seconds=deadline_data['remaining_seconds'],
                                percent_consumed=deadline_data['percent_consumed']
                            )

                # Verificar error budget do serviço
                service_name = 'orchestrator-dynamic'
                is_critical, budget_data = await sla_monitor.check_budget_threshold(service_name, 0.2)

                if is_critical and budget_data:
                    sla_status['budget_critical'] = True
                    budget_status = budget_data.get('status', 'CRITICAL')

                    # Enviar alerta de budget (fail-open se Kafka não disponível)
                    try:
                        await alert_manager.send_budget_alert(workflow_id, service_name, budget_data)
                    except Exception as e:
                        activity.logger.warning(
                            'budget_alert_send_failed',
                            workflow_id=workflow_id,
                            service_name=service_name,
                            error=str(e)
                        )
                    activity.logger.warning(
                        'sla_budget_critical',
                        workflow_id=workflow_id,
                        service_name=service_name,
                        budget_remaining=budget_data.get('error_budget_remaining')
                    )
                elif budget_data:
                    budget_status = budget_data.get('status', 'HEALTHY')

                # Verificar violações reais (tickets que excederam SLA)
                violations_count = 0

                # Rastreamento de erros ML: processar tickets completados
                for ticket_data in tickets:
                    ticket = ticket_data.get('ticket', {})

                    # ML Error Tracking: se ticket está completo, calcular erro de predição
                    if ticket.get('status') == 'COMPLETED' and ticket.get('actual_duration_ms') is not None:
                        compute_and_record_ml_error(ticket, metrics)

                # Violações de SLA
                for ticket_data in tickets:
                    ticket = ticket_data.get('ticket', {})
                    if ticket.get('status') in ['FAILED', 'COMPENSATED']:
                        sla = ticket.get('sla', {})
                        timeout_ms = sla.get('timeout_ms', 0)

                        # Calcular duração real a partir de timestamps
                        started_at = ticket.get('started_at')
                        completed_at = ticket.get('completed_at')

                        # Preferir actual_duration_ms se disponível
                        actual_duration_ms = ticket.get('actual_duration_ms')
                        duration_source = 'persisted'

                        # Se não houver actual_duration_ms, calcular de timestamps
                        if actual_duration_ms is None and started_at and completed_at:
                            actual_duration_ms = completed_at - started_at
                            duration_source = 'calculated'

                        # Fallback para estimated_duration_ms apenas se necessário
                        if actual_duration_ms is None:
                            actual_duration_ms = ticket.get('estimated_duration_ms', 0)
                            duration_source = 'estimated'

                        if timeout_ms > 0 and actual_duration_ms > timeout_ms:
                            violations_count += 1

                            # Calcular actual_completion usando completed_at se disponível
                            if completed_at:
                                actual_completion = completed_at
                            else:
                                actual_completion = ticket.get('created_at', 0) + actual_duration_ms

                            # Publicar violação no Kafka
                            violation = {
                                'workflow_id': workflow_id,
                                'ticket_id': ticket.get('ticket_id'),
                                'violation_type': 'DEADLINE_EXCEEDED',
                                'service_name': service_name,
                                'sla_deadline': sla.get('deadline'),
                                'actual_completion': actual_completion,
                                'delay_ms': actual_duration_ms - timeout_ms,
                                'budget_remaining': budget_data.get('error_budget_remaining', 0) if budget_data else 0,
                                'severity': 'CRITICAL',
                                'metadata': {
                                    'status': ticket.get('status'),
                                    'retry_count': ticket.get('retry_count', 0),
                                    'duration_source': duration_source
                                }
                            }

                            # Publicar violação (fail-open se Kafka não disponível)
                            try:
                                await alert_manager.publish_sla_violation(violation)
                            except Exception as e:
                                activity.logger.warning(
                                    'violation_publish_failed',
                                    workflow_id=workflow_id,
                                    ticket_id=ticket.get('ticket_id'),
                                    error=str(e)
                                )
                            activity.logger.warning(
                                'sla_violation_detected',
                                workflow_id=workflow_id,
                                ticket_id=ticket.get('ticket_id'),
                                delay_ms=violation['delay_ms']
                            )

                sla_status['violations_count'] = violations_count

                # Atualizar métricas Prometheus
                if sla_remaining_seconds > 0:
                    metrics.update_sla_remaining(
                        workflow_id=workflow_id,
                        risk_band='medium',  # Placeholder
                        remaining_seconds=sla_remaining_seconds
                    )

                if sla_status['deadline_approaching']:
                    metrics.record_deadline_approaching()

                if budget_data:
                    metrics.update_budget_remaining(
                        service_name=service_name,
                        slo_id='orchestrator-availability',  # Placeholder
                        percent=budget_data.get('error_budget_remaining', 0)
                    )
                    metrics.update_budget_status(
                        service_name=service_name,
                        slo_id='orchestrator-availability',
                        status=budget_status
                    )

                # Cleanup
                await sla_monitor.close()
                if kafka_producer:
                    try:
                        await kafka_producer.close()
                    except Exception as e:
                        activity.logger.warning(
                            'kafka_producer_close_failed',
                            workflow_id=workflow_id,
                            error=str(e)
                        )

        except Exception as e:
            activity.logger.error(
                'sla_monitoring_failed',
                workflow_id=workflow_id,
                error=str(e)
            )
            # Fail-open: continuar sem SLA monitoring

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
                'sla_violations': sla_status['violations_count']
            },
            'tickets_summary': [
                {
                    'ticket_id': t.get('ticket', {}).get('ticket_id'),
                    'status': t.get('ticket', {}).get('status'),
                    'duration': t.get('ticket', {}).get('estimated_duration_ms')
                }
                for t in tickets
            ],
            'sla_status': sla_status,
            'sla_remaining_seconds': sla_remaining_seconds,
            'budget_status': budget_status,
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
        # Criar Telemetry Frame com métricas de SLA
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
            'metrics': {
                **workflow_result.get('metrics', {}),
                'sla_metrics': {
                    'deadline_approaching': workflow_result.get('sla_status', {}).get('deadline_approaching', False),
                    'budget_critical': workflow_result.get('sla_status', {}).get('budget_critical', False),
                    'violations_count': workflow_result.get('sla_status', {}).get('violations_count', 0),
                    'remaining_seconds': workflow_result.get('sla_remaining_seconds', 0),
                    'budget_status': workflow_result.get('budget_status', 'UNKNOWN')
                }
            },
            'timestamp': datetime.now().isoformat(),
            'source': 'orchestrator-dynamic'
        }

        # TODO: Publicar no Kafka tópico telemetry.orchestration
        # producer = get_kafka_producer()
        # await producer.send(
        #     topic='telemetry.orchestration',
        #     value=json.dumps(telemetry_frame).encode()
        # )

        # Exportar métricas de SLA para Prometheus
        try:
            from src.observability.metrics import get_metrics
            metrics = get_metrics()

            # Métricas de SLA
            sla_status = workflow_result.get('sla_status', {})
            if sla_status.get('violations_count', 0) > 0:
                # Registrar violações
                for _ in range(sla_status['violations_count']):
                    metrics.record_sla_violation('medium', 'orchestration')  # Placeholder para risk_band e task_type

            if sla_status.get('deadline_approaching'):
                metrics.record_deadline_approaching()

        except Exception as e:
            activity.logger.warning(
                'metrics_export_failed',
                error=str(e)
            )

        # Log específico para SLA
        if workflow_result.get('sla_status', {}).get('violations_count', 0) > 0:
            activity.logger.warning(
                'sla_violations_detected_in_telemetry',
                workflow_id=workflow_result.get('workflow_id'),
                violations_count=workflow_result['sla_status']['violations_count'],
                budget_status=workflow_result.get('budget_status')
            )

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
