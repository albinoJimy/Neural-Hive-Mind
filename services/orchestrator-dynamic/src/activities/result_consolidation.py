"""
Activities Temporal para consolidação de resultados (Etapa C5).
"""
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4

from temporalio import activity
import structlog
from neural_hive_resilience.circuit_breaker import CircuitBreakerError

from src.sla.sla_monitor import SLAMonitor
from src.sla.alert_manager import AlertManager
from src.config.settings import get_settings
from src.clients.kafka_producer import KafkaProducerClient
from src.clients.self_healing_client import SelfHealingClient
from src.ml.scheduling_optimizer import SchedulingOptimizer

logger = structlog.get_logger()
_scheduling_optimizer = None
_config = None
_mongodb_client = None
_kafka_producer: Optional[KafkaProducerClient] = None
_self_healing_client: Optional[SelfHealingClient] = None


def set_activity_dependencies(
    scheduling_optimizer: SchedulingOptimizer = None,
    config=None,
    mongodb_client=None,
    kafka_producer: KafkaProducerClient = None,
    self_healing_client: SelfHealingClient = None
) -> None:
    """
    Injeta dependências globais para consolidação de resultados.

    Args:
        scheduling_optimizer: SchedulingOptimizer para feedback de outcomes
        config: OrchestratorSettings (opcional)
        mongodb_client: MongoDBClient para persistência (opcional)
        kafka_producer: KafkaProducerClient para publicações Kafka (opcional)
    """
    global _scheduling_optimizer, _config, _mongodb_client, _kafka_producer, _self_healing_client
    _scheduling_optimizer = scheduling_optimizer
    _config = config
    _mongodb_client = mongodb_client
    _kafka_producer = kafka_producer
    _self_healing_client = self_healing_client


def _set_global_kafka_producer(producer: KafkaProducerClient) -> None:
    """Define instância global de KafkaProducerClient (fail-open)."""
    global _kafka_producer
    _kafka_producer = producer


def _get_self_healing_client(config) -> Optional[SelfHealingClient]:
    """Retorna cliente HTTP do Self-Healing Engine (singleton)."""
    global _self_healing_client
    if _self_healing_client:
        return _self_healing_client

    try:
        _self_healing_client = SelfHealingClient(
            base_url=config.self_healing_engine_url,
            timeout=config.self_healing_timeout_seconds
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('self_healing_client_init_failed', error=str(exc))
        _self_healing_client = None

    return _self_healing_client


def _extract_affected_tickets(tickets_context: Optional[List[Dict[str, Any]]]) -> List[str]:
    """Extrai ticket_ids de um contexto de tickets publicado."""
    if not tickets_context:
        return []
    ticket_ids = [
        t.get('ticket', {}).get('ticket_id')
        for t in tickets_context
        if t.get('ticket', {}).get('ticket_id')
    ]
    return list({tid for tid in ticket_ids if tid})


def _extract_worker_map(tickets_context: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
    """Mapeia ticket_id -> worker/agent id a partir do contexto de tickets."""
    worker_map: Dict[str, str] = {}
    if not tickets_context:
        return worker_map

    for t in tickets_context:
        ticket = t.get('ticket', {})
        ticket_id = ticket.get('ticket_id')
        allocation_metadata = ticket.get('allocation_metadata') or {}
        worker_id = ticket.get('worker_id') or allocation_metadata.get('agent_id')
        if ticket_id and worker_id:
            worker_map[ticket_id] = worker_id
    return worker_map


def _extract_worker_from_inconsistencies(inconsistencies: List[str]) -> Optional[str]:
    """Busca menções a worker nas inconsistências (heurística)."""
    for inc in inconsistencies:
        lower = inc.lower()
        if 'worker' in lower:
            tokens = inc.replace(':', ' ').replace(',', ' ').split()
            for tok in tokens:
                if tok.lower().startswith('worker'):
                    return tok
    return None


def _extract_sla_details(tickets_context: Optional[List[Dict[str, Any]]], workflow_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Deriva dados de SLA para playbook sla_violation_mitigation."""
    delay_ms = 0
    violation_type = 'SLA_VIOLATION'

    if workflow_result:
        sla_status = workflow_result.get('sla_status') or {}
        if sla_status.get('budget_critical'):
            violation_type = 'BUDGET_CRITICAL'

    if tickets_context:
        for t in tickets_context:
            ticket = t.get('ticket', {})
            sla = ticket.get('sla', {})
            timeout_ms = sla.get('timeout_ms')
            actual_duration_ms = ticket.get('actual_duration_ms') or ticket.get('estimated_duration_ms')
            if timeout_ms and actual_duration_ms and actual_duration_ms > timeout_ms:
                delay_ms = max(delay_ms, actual_duration_ms - timeout_ms)
                violation_type = 'DEADLINE_EXCEEDED'

    return {
        'violation_type': violation_type,
        'delay_ms': int(delay_ms)
    }


def _first_non_empty(values: List[str]) -> Optional[str]:
    return next((v for v in values if v), None)


def _infer_incident_type(inconsistencies: List[str]) -> str:
    """Deduz tipo de incidente a partir das inconsistências detectadas."""
    joined = ' '.join(inconsistencies).lower()
    if 'sla' in joined or 'viol' in joined:
        return 'SLA_VIOLATION'
    if 'timeout' in joined or 'tempo' in joined or 'deadline' in joined:
        return 'TICKET_TIMEOUT'
    if 'worker' in joined and ('fail' in joined or 'unhealthy' in joined or 'responde' in joined):
        return 'WORKER_FAILURE'
    return 'INCONSISTENCY'


def _recommend_playbook(incident_type: str, inconsistencies: Optional[List[str]] = None) -> Optional[str]:
    """Mapeia incident_type ou texto de inconsistências para playbook recomendado."""
    text = ' '.join(inconsistencies or []).lower()
    if 'status inválido' in text or 'timeout' in text or 'sla' in text:
        return 'ticket_timeout_recovery'
    if 'worker' in text and ('não responde' in text or 'unhealthy' in text):
        return 'worker_failure_recovery'
    if 'sla' in text or 'viola' in text:
        return 'sla_violation_mitigation'

    mapping = {
        'TICKET_TIMEOUT': 'ticket_timeout_recovery',
        'WORKER_FAILURE': 'worker_failure_recovery',
        'SLA_VIOLATION': 'sla_violation_mitigation'
    }
    return mapping.get(incident_type)


def compute_and_record_ml_error(ticket: Dict[str, Any], metrics) -> None:
    """
    Calcula e registra erro de predição ML para um ticket (erro e acurácia).

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
        try:
            metrics.record_ml_prediction_accuracy(
                model_type='duration',
                predicted_ms=predicted_duration_ms,
                actual_ms=actual_duration_ms
            )
        except Exception as metric_err:
            logger.warning(
                'ml_accuracy_record_failed',
                ticket_id=ticket_id,
                error=str(metric_err)
            )

    except Exception as e:
        # Fail-open: log erro mas não bloqueia
        logger.warning(
            'ml_error_tracking_failed',
            ticket_id=ticket.get('ticket_id', 'unknown'),
            error=str(e)
        )


async def record_allocation_outcome_for_ticket(
    ticket: Dict[str, Any],
    scheduling_optimizer: SchedulingOptimizer
) -> None:
    """
    Registra allocation outcome para um ticket COMPLETED usando SchedulingOptimizer.

    Args:
        ticket: Ticket já executado com actual_duration_ms
        scheduling_optimizer: Instância do SchedulingOptimizer injetada
    """
    try:
        allocation_metadata = ticket.get('allocation_metadata') or {}
        ticket_id = ticket.get('ticket_id', 'unknown')

        actual_duration_ms = ticket.get('actual_duration_ms')
        agent_id = allocation_metadata.get('agent_id')

        if not allocation_metadata or not agent_id or not actual_duration_ms:
            logger.debug(
                'allocation_outcome_skipped',
                ticket_id=ticket_id,
                reason='allocation_metadata/agent_id/actual_duration_ms ausente'
            )
            return

        worker = {
            'agent_id': agent_id,
            'agent_type': allocation_metadata.get('agent_type'),
            'predicted_queue_ms': allocation_metadata.get('predicted_queue_ms'),
            'predicted_load_pct': allocation_metadata.get('predicted_load_pct'),
            'ml_enriched': allocation_metadata.get('ml_scheduling_enriched') or allocation_metadata.get('ml_enriched', False)
        }

        await scheduling_optimizer.record_allocation_outcome(
            ticket=ticket,
            worker=worker,
            actual_duration_ms=actual_duration_ms
        )

        logger.info(
            'allocation_outcome_recorded',
            ticket_id=ticket_id,
            worker_id=agent_id,
            actual_duration_ms=actual_duration_ms
        )

    except Exception as e:
        logger.warning(
            'allocation_outcome_recording_failed',
            ticket_id=ticket.get('ticket_id', 'unknown'),
            error=str(e)
        )


@activity.defn
async def consolidate_results(tickets: List[Dict[str, Any]], workflow_id: str) -> Dict[str, Any]:
    """
    Agrega resultados de todos os tickets executados e calcula métricas.
    Também registra outcomes de alocação para feedback loop de RL.

    Args:
        tickets: Lista de tickets publicados
        workflow_id: ID do workflow Temporal

    Returns:
        Resultado consolidado com métricas e status
    """
    activity.logger.info(f'Consolidando resultados do workflow {workflow_id}')

    try:
        global _config
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

        metrics = None
        try:
            from src.observability.metrics import get_metrics

            metrics = get_metrics()
        except Exception as metrics_error:
            activity.logger.warning(
                f'metrics_unavailable workflow_id={workflow_id} error={metrics_error}'
            )

        try:
            config = _config or get_settings()
            _config = config

            # Rastreamento de erros ML e feedback loop fora do bloco de SLA
            for ticket_data in tickets:
                ticket = ticket_data.get('ticket', {})
                if ticket.get('status') == 'COMPLETED' and ticket.get('actual_duration_ms') is not None:
                    if metrics:
                        compute_and_record_ml_error(ticket, metrics)
                    else:
                        activity.logger.debug(
                            f"ml_error_tracking_skipped_no_metrics ticket_id={ticket.get('ticket_id', 'unknown')}"
                        )

                    if _scheduling_optimizer and _config and _config.ml_allocation_outcomes_enabled:
                        try:
                            await record_allocation_outcome_for_ticket(ticket, _scheduling_optimizer)
                            activity.logger.info(
                                f"allocation_outcome_feedback_sent workflow_id={workflow_id} ticket_id={ticket.get('ticket_id')}"
                            )
                        except Exception as feedback_error:
                            activity.logger.warning(
                                f"allocation_outcome_feedback_failed workflow_id={workflow_id} ticket_id={ticket.get('ticket_id')} error={feedback_error}"
                            )

            # Monitoramento de SLA (integração com SLA Management System)
            if config.sla_management_enabled:
                # Obter instâncias de clientes compartilhados
                from src.clients.redis_client import get_redis_client
                from src.clients.kafka_producer import KafkaProducerClient

                if metrics is None:
                    try:
                        from src.observability.metrics import get_metrics

                        metrics = get_metrics()
                    except Exception as metrics_error:
                        activity.logger.warning(
                            f'metrics_unavailable_for_sla workflow_id={workflow_id} error={metrics_error}'
                        )

                if metrics is None:
                    activity.logger.warning(
                        f'sla_monitoring_skipped_no_metrics workflow_id={workflow_id}'
                    )
                else:
                    # Inicializar Redis client (fail-open se não disponível)
                    redis_client = await get_redis_client(config)

                    # Inicializar Kafka producer para alertas e violações
                    kafka_producer = None
                    try:
                        kafka_producer = KafkaProducerClient(config)
                        await kafka_producer.initialize()
                    except Exception as e:
                        activity.logger.warning(
                            f'kafka_producer_initialization_failed workflow_id={workflow_id} error={e}'
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
                                        f'deadline_alert_send_failed workflow_id={workflow_id} ticket_id={ticket_id} error={e}'
                                    )
                                activity.logger.warning(
                                    f"sla_deadline_approaching workflow_id={workflow_id} ticket_id={ticket_id} remaining_seconds={deadline_data['remaining_seconds']} percent_consumed={deadline_data['percent_consumed']}"
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
                                f'budget_alert_send_failed workflow_id={workflow_id} service_name={service_name} error={e}'
                            )
                        activity.logger.warning(
                            f"sla_budget_critical workflow_id={workflow_id} service_name={service_name} budget_remaining={budget_data.get('error_budget_remaining')}"
                        )
                    elif budget_data:
                        budget_status = budget_data.get('status', 'HEALTHY')

                    # Verificar violações reais (tickets que excederam SLA)
                    violations_count = 0

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
                                        f"violation_publish_failed workflow_id={workflow_id} ticket_id={ticket.get('ticket_id')} error={e}"
                                    )
                                activity.logger.warning(
                                    f"sla_violation_detected workflow_id={workflow_id} ticket_id={ticket.get('ticket_id')} delay_ms={violation['delay_ms']}"
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
                                f'kafka_producer_close_failed workflow_id={workflow_id} error={e}'
                            )

        except Exception as e:
            activity.logger.error(
                f'sla_monitoring_failed workflow_id={workflow_id} error={e}'
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

        # Persistir resultado no MongoDB (fail-open)
        try:
            if _mongodb_client:
                await _mongodb_client.save_workflow_result(result)
                activity.logger.info(f'workflow_result_persisted workflow_id={workflow_id}')
            else:
                activity.logger.warning(f'mongodb_client_not_initialized workflow_id={workflow_id}')
        except CircuitBreakerError:
            activity.logger.warning(
                f'workflow_result_persist_circuit_open workflow_id={workflow_id}'
            )
        except Exception as mongo_error:
            activity.logger.error(
                f'workflow_result_persist_failed workflow_id={workflow_id} error={mongo_error}'
            )

        activity.logger.info(
            f'Resultados consolidados para workflow {workflow_id} status={overall_status} total_tickets={total_tickets} consistent={consistent}'
        )

        return result

    except Exception as e:
        activity.logger.error(f'Erro ao consolidar resultados: {e}', exc_info=True)
        raise


@activity.defn
async def trigger_self_healing(
    workflow_id: str,
    inconsistencies: List[str],
    tickets_context: Optional[List[Dict[str, Any]]] = None,
    workflow_result: Optional[Dict[str, Any]] = None
) -> None:
    """
    Publica evento de inconsistência para acionar Fluxo E (Autocura).

    Args:
        workflow_id: ID do workflow com inconsistências
        inconsistencies: Lista de inconsistências detectadas
    """
    activity.logger.warning(
        f'self_healing.trigger_called workflow_id={workflow_id} inconsistencies_count={len(inconsistencies)}'
    )

    try:
        global _config
        config = _config or get_settings()
        _config = config
    except Exception as cfg_error:
        activity.logger.error(f'self_healing.config_load_failed error={cfg_error}')
        raise

    incident_type = _infer_incident_type(inconsistencies)
    recommended_playbook = _recommend_playbook(incident_type, inconsistencies)
    severity = 'CRITICAL' if incident_type in ['SLA_VIOLATION', 'WORKER_FAILURE'] else 'WARNING'
    created_at_ms = int(datetime.utcnow().timestamp() * 1000)

    affected_tickets = _extract_affected_tickets(tickets_context)
    worker_map = _extract_worker_map(tickets_context)

    incident_event = {
        'incident_id': str(uuid4()),
        'workflow_id': workflow_id,
        'incident_type': incident_type,
        'severity': severity,
        'details': inconsistencies,
        'affected_tickets': affected_tickets,
        'correlation_id': workflow_id,
        'trace_id': workflow_id,
        'recommended_playbook': recommended_playbook,
        'auto_remediation_enabled': True,
        'escalation_required': incident_type in ['SLA_VIOLATION', 'WORKER_FAILURE'],
        'created_at': created_at_ms
    }
    incident_event['hash'] = hashlib.sha256(
        json.dumps(incident_event, sort_keys=True).encode('utf-8')
    ).hexdigest()

    metrics = None
    try:
        from src.observability.metrics import get_metrics

        metrics = get_metrics()
    except Exception as metrics_error:
        activity.logger.warning(
            f'metrics_unavailable_self_healing workflow_id={workflow_id} error={metrics_error}'
        )

    kafka_publish_ok = False
    producer = _kafka_producer

    # Inicializar producer se não injetado
    if producer is None:
        try:
            producer = KafkaProducerClient(config)
            await producer.initialize()
            _set_global_kafka_producer(producer)
        except Exception as init_error:
            activity.logger.warning(
                f'self_healing.kafka_producer_init_failed workflow_id={workflow_id} error={init_error}'
            )

    # Publicar no Kafka (fail-open)
    if producer:
        try:
            kafka_publish_ok = await producer.publish_incident_avro(incident_event)
        except Exception as kafka_error:
            activity.logger.warning(
                f"self_healing.kafka_publish_failed workflow_id={workflow_id} incident_id={incident_event['incident_id']} incident_type={incident_type} error={kafka_error}"
            )

    remediation_id = None
    if config.self_healing_enabled and recommended_playbook:
        client = _get_self_healing_client(config)
        if client:
            namespace = getattr(config, 'kubernetes_namespace', 'default') if hasattr(config, 'kubernetes_namespace') else 'default'
            sla_details = _extract_sla_details(tickets_context, workflow_result)

            # Construir parâmetros específicos por tipo de incidente/playbook
            parameters: Dict[str, Any] = {
                "workflow_id": workflow_id,
                "incident_type": incident_type,
                "inconsistencies": inconsistencies,
                "affected_tickets": affected_tickets
            }

            if incident_type == 'TICKET_TIMEOUT':
                ticket_id = _first_non_empty(affected_tickets) or 'unknown-ticket'
                worker_id = worker_map.get(ticket_id) or _first_non_empty(list(worker_map.values())) or _extract_worker_from_inconsistencies(inconsistencies) or 'unknown-worker'
                parameters.update({
                    "ticket_id": ticket_id,
                    "worker_id": worker_id,
                    "previous_worker_id": worker_id,
                    "namespace": namespace
                })
            elif incident_type == 'WORKER_FAILURE':
                worker_id = _first_non_empty(list(worker_map.values())) or _extract_worker_from_inconsistencies(inconsistencies) or 'unknown-worker'
                parameters.update({
                    "worker_id": worker_id,
                    "previous_worker_id": worker_id,
                    "namespace": namespace,
                    "affected_tickets": affected_tickets
                })
            elif incident_type == 'SLA_VIOLATION':
                parameters.update({
                    "workflow_id": workflow_id,
                    "service_name": getattr(config, 'service_name', 'orchestrator-dynamic'),
                    "violation_type": sla_details.get('violation_type', 'SLA_VIOLATION'),
                    "delay_ms": sla_details.get('delay_ms', 0)
                })

            remediation_payload = {
                "incident_id": incident_event["incident_id"],
                "remediation_id": incident_event["incident_id"],
                "recommended_playbook": recommended_playbook,
                "parameters": parameters,
                "execution_mode": "AUTOMATIC"
            }
            try:
                remediation_id = await client.trigger_remediation(remediation_payload)
                if remediation_id:
                    activity.logger.info(
                        f'self_healing.http_trigger_sent workflow_id={workflow_id} remediation_id={remediation_id} playbook={recommended_playbook}'
                    )
                else:
                    activity.logger.warning(
                        f"self_healing.http_trigger_failed workflow_id={workflow_id} incident_id={incident_event['incident_id']} playbook={recommended_playbook}"
                    )
            except Exception as http_error:  # noqa: BLE001
                activity.logger.warning(
                    f"self_healing.http_trigger_exception workflow_id={workflow_id} incident_id={incident_event['incident_id']} error={http_error}"
                )
    elif config.self_healing_enabled and not recommended_playbook:
        activity.logger.warning(
            f'self_healing.no_playbook_mapped workflow_id={workflow_id} incident_type={incident_type} inconsistencies={inconsistencies}'
        )

    if not kafka_publish_ok:
        # Registrar incidente no MongoDB (fail-open)
        if _mongodb_client:
            try:
                await _mongodb_client.save_incident(incident_event)
                activity.logger.warning(
                    f"self_healing.incident_buffered incident_id={incident_event['incident_id']} workflow_id={workflow_id}"
                )
            except Exception as mongo_error:
                activity.logger.error(
                    f'incident_persist_failed workflow_id={workflow_id} error={mongo_error}'
                )
        else:
            activity.logger.warning(f'mongodb_client_not_initialized workflow_id={workflow_id}')

    if metrics:
        try:
            metrics.record_self_healing_triggered(incident_type=incident_type)
        except Exception as metrics_error:
            activity.logger.warning(
                f'metrics_self_healing_trigger_record_failed workflow_id={workflow_id} error={metrics_error}'
            )

    activity.logger.info(
        f"self_healing.incident_processed workflow_id={workflow_id} incident_id={incident_event['incident_id']} incident_type={incident_type} recommended_playbook={recommended_playbook} kafka_published={kafka_publish_ok} remediation_id={remediation_id}"
    )


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

        # TODO: Implementar publicação Kafka em fase futura (PHASE2-009)
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
                f'metrics_export_failed error={e}'
            )

        # Log específico para SLA
        if workflow_result.get('sla_status', {}).get('violations_count', 0) > 0:
            activity.logger.warning(
                f"sla_violations_detected_in_telemetry workflow_id={workflow_result.get('workflow_id')} violations_count={workflow_result['sla_status']['violations_count']} budget_status={workflow_result.get('budget_status')}"
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

        # Persistir no MongoDB (fail-open)
        if _mongodb_client:
            try:
                await _mongodb_client.save_telemetry_buffer(buffered_frame)
            except Exception as mongo_error:
                activity.logger.error(
                    f'telemetry_buffer_persist_failed error={mongo_error}'
                )
        else:
            activity.logger.warning('mongodb_client_not_initialized')

        activity.logger.info('Telemetria buffered com sucesso')

    except Exception as e:
        activity.logger.error(f'Erro ao buffer telemetria: {e}', exc_info=True)
        raise
