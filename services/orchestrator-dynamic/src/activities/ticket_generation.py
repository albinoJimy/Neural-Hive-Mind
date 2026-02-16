"""
Activities Temporal para geração de Execution Tickets (Etapa C2).
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List

from temporalio import activity
import structlog
from neural_hive_resilience.circuit_breaker import CircuitBreakerError
from pymongo.errors import PyMongoError

from src.scheduler import IntelligentScheduler

logger = structlog.get_logger()

# Global clients (serão injetados pelo worker)
_kafka_producer = None
_mongodb_client = None
_registry_client = None
_intelligent_scheduler = None
_policy_validator = None
_config = None
_ml_predictor = None
_scheduling_optimizer = None


def set_activity_dependencies(kafka_producer, mongodb_client, registry_client=None, intelligent_scheduler=None, policy_validator=None, config=None, ml_predictor=None, scheduling_optimizer=None):
    """
    Injeta dependências globais nas activities.

    Args:
        kafka_producer: Cliente Kafka Producer
        mongodb_client: Cliente MongoDB
        registry_client: Cliente do Service Registry (opcional)
        intelligent_scheduler: Scheduler inteligente (opcional)
        policy_validator: PolicyValidator para validação OPA (opcional)
        config: OrchestratorSettings (opcional)
        ml_predictor: MLPredictor para predições ML (opcional)
        scheduling_optimizer: SchedulingOptimizer para enriquecer metadata (opcional)
    """
    global _kafka_producer, _mongodb_client, _registry_client, _intelligent_scheduler, _policy_validator, _config, _ml_predictor, _scheduling_optimizer
    _kafka_producer = kafka_producer
    _mongodb_client = mongodb_client
    _registry_client = registry_client
    _intelligent_scheduler = intelligent_scheduler
    _policy_validator = policy_validator
    _config = config
    _ml_predictor = ml_predictor
    _scheduling_optimizer = scheduling_optimizer


@activity.defn
async def generate_execution_tickets(
    cognitive_plan: Dict[str, Any],
    consolidated_decision: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Gera Execution Tickets a partir de um Cognitive Plan.

    Args:
        cognitive_plan: Plano cognitivo com tasks e execution_order
        consolidated_decision: Decisão consolidada que aprovou o plano

    Returns:
        Lista de tickets ordenada topologicamente
    """
    logger.info(f'Gerando execution tickets para plano {cognitive_plan["plan_id"]}')

    try:
        tasks = cognitive_plan.get('tasks', [])
        plan_id = cognitive_plan['plan_id']
        intent_id = cognitive_plan['intent_id']
        decision_id = consolidated_decision['decision_id']
        risk_band = cognitive_plan.get('risk_band', 'medium')

        # Mapeamento de task_id para ticket_id
        task_to_ticket_map = {}
        tickets = []

        # Gerar um ticket para cada task
        for task in tasks:
            ticket_id = str(uuid.uuid4())
            task_id = task['task_id']
            task_to_ticket_map[task_id] = ticket_id

            # ============================================================================
            # SLA Timeout Calculation
            # ============================================================================
            # Fórmula: timeout_ms = max(min_timeout_ms, estimated_duration_ms * buffer_multiplier)
            #
            # Configuração via environment variables:
            #   - SLA_TICKET_MIN_TIMEOUT_MS (default: 60000ms = 60s)
            #   - SLA_TICKET_TIMEOUT_BUFFER_MULTIPLIER (default: 3.0)
            #
            # Histórico de mudanças:
            #   - v1.0.0: min=30s, buffer=1.5x (resultou em 100% falsos positivos)
            #   - v1.0.9: min=60s, buffer=3.0x (baseado em análise de logs de produção)
            #
            # Rationale dos valores atuais:
            #   - 60s mínimo: Acomoda overhead de inicialização de workers e rede
            #   - 3.0x buffer: Margem para variabilidade de carga e recursos
            # ============================================================================
            estimated_duration_ms = task.get('estimated_duration_ms', 60000)

            # Usar valores configuráveis de timeout (via environment variables)
            # - min_timeout_ms: Timeout mínimo absoluto (default 60s)
            # - buffer_multiplier: Multiplicador de buffer (default 3.0x)
            # Rationale: Valores aumentados baseados em análise de logs de produção
            # que mostraram 100% de falsos positivos com valores anteriores (30s/1.5x)
            min_timeout_ms = _config.sla_ticket_min_timeout_ms if _config else 60000
            buffer_multiplier = _config.sla_ticket_timeout_buffer_multiplier if _config else 3.0
            timeout_ms = max(min_timeout_ms, int(estimated_duration_ms * buffer_multiplier))
            deadline = int((datetime.now().timestamp() + timeout_ms / 1000) * 1000)

            # Log detalhado do cálculo de timeout para auditoria e debugging
            logger.info(
                'sla_timeout_calculated',
                ticket_id=ticket_id,
                task_id=task_id,
                estimated_duration_ms=estimated_duration_ms,
                min_timeout_ms=min_timeout_ms,
                buffer_multiplier=buffer_multiplier,
                calculated_timeout_before_max=int(estimated_duration_ms * buffer_multiplier),
                final_timeout_ms=timeout_ms,
                timeout_seconds=timeout_ms / 1000,
                risk_band=risk_band,
                config_source='injected' if _config else 'defaults'
            )

            # Validação: garantir que timeout nunca seja menor que o mínimo configurado
            if timeout_ms < min_timeout_ms:
                logger.error(
                    'sla_timeout_below_minimum',
                    ticket_id=ticket_id,
                    timeout_ms=timeout_ms,
                    min_timeout_ms=min_timeout_ms,
                    estimated_duration_ms=estimated_duration_ms
                )
                raise RuntimeError(
                    f'Timeout calculado ({timeout_ms}ms) está abaixo do mínimo configurado ({min_timeout_ms}ms). '
                    f'Isso indica um bug na fórmula de cálculo.'
                )

            # Mapear max_retries baseado em risk_band
            retry_map = {'critical': 5, 'high': 3, 'medium': 2, 'low': 1}
            max_retries = retry_map.get(risk_band, 2)

            # Definir QoS baseado em risk_band
            if risk_band in ['critical', 'high']:
                delivery_mode = 'EXACTLY_ONCE'
                consistency = 'STRONG'
            else:
                delivery_mode = 'AT_LEAST_ONCE'
                consistency = 'EVENTUAL'

            ticket = {
                'ticket_id': ticket_id,
                'plan_id': plan_id,
                'intent_id': intent_id,
                'decision_id': decision_id,
                'correlation_id': consolidated_decision.get('correlation_id'),
                'trace_id': consolidated_decision.get('trace_id'),
                'span_id': consolidated_decision.get('span_id'),
                'task_id': task_id,
                'task_type': task.get('task_type', 'EXECUTE'),
                'description': task.get('description', ''),
                'dependencies': [],  # Será preenchido após mapeamento
                'status': 'PENDING',
                'priority': cognitive_plan.get('priority', 'NORMAL'),
                'risk_band': risk_band,
                'sla': {
                    'deadline': deadline,
                    'timeout_ms': timeout_ms,
                    'max_retries': max_retries
                },
                'qos': {
                    'delivery_mode': delivery_mode,
                    'consistency': consistency,
                    'durability': 'PERSISTENT'
                },
                'parameters': task.get('parameters', {}),
                'required_capabilities': task.get('required_capabilities', []),
                'security_level': cognitive_plan.get('security_level', 'INTERNAL'),
                'created_at': int(datetime.now().timestamp() * 1000),
                'started_at': None,
                'completed_at': None,
                'estimated_duration_ms': estimated_duration_ms,
                'actual_duration_ms': None,
                'retry_count': 0,
                'error_message': None,
                'compensation_ticket_id': None,
                'metadata': {
                    'workflow_id': activity.info().workflow_id,
                    'generated_by': 'orchestrator-dynamic'
                },
                'schema_version': 1
            }

            tickets.append(ticket)

        # Mapear dependencies de task_ids para ticket_ids
        for i, task in enumerate(tasks):
            task_dependencies = task.get('dependencies', [])
            ticket_dependencies = [task_to_ticket_map[dep] for dep in task_dependencies if dep in task_to_ticket_map]
            tickets[i]['dependencies'] = ticket_dependencies

        # Ordenar tickets topologicamente usando execution_order
        execution_order = cognitive_plan.get('execution_order', [task['task_id'] for task in tasks])
        ordered_tickets = []
        for task_id in execution_order:
            if task_id in task_to_ticket_map:
                ticket_id = task_to_ticket_map[task_id]
                ticket = next((t for t in tickets if t['ticket_id'] == ticket_id), None)
                if ticket:
                    ordered_tickets.append(ticket)

        logger.info(
            f'Gerados {len(ordered_tickets)} execution tickets',
            plan_id=plan_id,
            risk_band=risk_band
        )

        return ordered_tickets

    except Exception as e:
        logger.error(f'Erro ao gerar execution tickets: {e}', exc_info=True)
        raise


@activity.defn
async def allocate_resources(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aloca recursos para um ticket usando Intelligent Scheduler.
    Enriquece allocation_metadata com dados de predições ML para feedback loop.

    Args:
        ticket: Execution ticket

    Returns:
        Ticket atualizado com allocation_metadata
    """
    ticket_id = ticket.get('ticket_id', 'unknown')
    logger.info(f'Alocando recursos para ticket {ticket_id}')

    try:
        # Validar políticas OPA antes de alocar recursos
        feature_flags = {}
        if _policy_validator and _config and _config.opa_enabled:
            try:
                policy_result = await _policy_validator.validate_execution_ticket(ticket)

                if not policy_result.valid:
                    # Rejeitar alocação se políticas forem violadas
                    violation_msgs = [f'{v.policy_name}/{v.rule}: {v.message}' for v in policy_result.violations]
                    logger.error(
                        f'Ticket {ticket_id} rejeitado por políticas OPA',
                        violations=violation_msgs
                    )
                    raise RuntimeError(f'Ticket rejeitado por políticas: {violation_msgs}')

                # Logar warnings mas não bloquear
                if policy_result.warnings:
                    warning_msgs = [f'{w.policy_name}/{w.rule}: {w.message}' for w in policy_result.warnings]
                    logger.warning(
                        f'Ticket {ticket_id} tem warnings de políticas',
                        warnings=warning_msgs
                    )

                # Obter feature flags das decisões de políticas
                feature_flags = policy_result.policy_decisions.get('feature_flags', {})

                # Adicionar policy_decisions ao ticket metadata
                if 'metadata' not in ticket:
                    ticket['metadata'] = {}
                ticket['metadata']['policy_decisions'] = policy_result.policy_decisions
                ticket['metadata']['policy_validated_at'] = policy_result.evaluated_at.isoformat()

                logger.info(
                    f'Ticket {ticket_id} validado por políticas OPA',
                    feature_flags=feature_flags
                )

            except RuntimeError:
                # Re-raise policy violations
                raise
            except Exception as e:
                # Erro na validação OPA
                logger.error(f'Erro ao validar políticas OPA: {e}', exc_info=True)
                if not _config.opa_fail_open:
                    raise RuntimeError(f'Falha na validação de políticas: {str(e)}')

        # ML Predictions: enriquece ticket com predições antes do scheduler
        predicted_duration_ms = None
        if _ml_predictor:
            try:
                ticket = await _ml_predictor.predict_and_enrich(ticket)
                # Extrair predicted_duration_ms para usar em allocation_metadata
                predictions = ticket.get('predictions', {})
                predicted_duration_ms = predictions.get('duration_ms')
                logger.info(
                    f'ML predictions adicionadas ao ticket {ticket_id}',
                    predictions=ticket.get('predictions')
                )
            except Exception as e:
                logger.warning(
                    f'ML prediction falhou para ticket {ticket_id}, continuando sem predições: {e}'
                )

        # Decidir se usar IntelligentScheduler baseado em feature flags
        use_intelligent_scheduler = feature_flags.get('enable_intelligent_scheduler', True) if _policy_validator else True

        # Tentar usar Intelligent Scheduler se disponível e habilitado
        if _intelligent_scheduler and use_intelligent_scheduler:
            logger.info(
                f'Usando Intelligent Scheduler para ticket {ticket_id}',
                scheduler_enabled=True
            )

            try:
                # Delegar alocação para o scheduler
                ticket = await _intelligent_scheduler.schedule_ticket(ticket)

                # Adicionar predicted_duration_ms ao allocation_metadata para tracking de erro ML
                # Usado para ML error tracking e feedback loop
                if predicted_duration_ms is not None and 'allocation_metadata' in ticket:
                    ticket['allocation_metadata']['predicted_duration_ms'] = predicted_duration_ms

                allocation_metadata = ticket.get('allocation_metadata') or {}
                if 'predicted_queue_ms' in allocation_metadata:
                    ticket['allocation_metadata']['predicted_queue_ms'] = allocation_metadata.get('predicted_queue_ms')
                if 'predicted_load_pct' in allocation_metadata:
                    ticket['allocation_metadata']['predicted_load_pct'] = allocation_metadata.get('predicted_load_pct')
                if 'ml_enriched' in allocation_metadata or 'ml_scheduling_enriched' in allocation_metadata:
                    ticket['allocation_metadata']['ml_enriched'] = allocation_metadata.get('ml_enriched', allocation_metadata.get('ml_scheduling_enriched', False))

                # Validação OPA da alocação de recursos (C3)
                if _policy_validator and _config and _config.opa_enabled:
                    allocation_metadata = ticket.get('allocation_metadata') or {}
                    agent_info = {
                        'agent_id': allocation_metadata.get('agent_id'),
                        'agent_type': allocation_metadata.get('agent_type'),
                        'capacity': allocation_metadata.get('capacity') or allocation_metadata.get('resources', {})
                    }

                    try:
                        # Ausência de allocation_metadata.agent_id é tratada como erro fatal (sem fallback)
                        if agent_info['agent_id'] is None:
                            raise RuntimeError('allocation_metadata.agent_id ausente para validação de recursos')

                        policy_result = await _policy_validator.validate_resource_allocation(ticket, agent_info)

                        if not policy_result.valid:
                            violation_msgs = [f'{v.policy_name}/{v.rule}: {v.message}' for v in policy_result.violations]
                            logger.error(
                                f'Alocação rejeitada por políticas OPA para ticket {ticket_id}',
                                violations=violation_msgs,
                                agent_id=agent_info.get('agent_id')
                            )
                            raise RuntimeError(f'Alocação rejeitada por políticas: {violation_msgs}')

                        if policy_result.warnings:
                            warning_msgs = [f'{w.policy_name}/{w.rule}: {w.message}' for w in policy_result.warnings]
                            logger.warning(
                                f'Alocação com warnings de políticas OPA para ticket {ticket_id}',
                                warnings=warning_msgs,
                                agent_id=agent_info.get('agent_id')
                            )

                        if 'metadata' not in ticket:
                            ticket['metadata'] = {}

                        existing_decisions = ticket['metadata'].get('policy_decisions', {})
                        if isinstance(existing_decisions, dict):
                            existing_decisions.update(policy_result.policy_decisions)
                            ticket['metadata']['policy_decisions'] = existing_decisions
                        else:
                            ticket['metadata']['policy_decisions'] = policy_result.policy_decisions
                        ticket['metadata']['policy_validated_at'] = policy_result.evaluated_at.isoformat()

                        logger.info(
                            f'Validação OPA de alocação concluída para ticket {ticket_id}',
                            agent_id=agent_info.get('agent_id'),
                            agent_type=agent_info.get('agent_type')
                        )
                    except RuntimeError:
                        raise
                    except Exception as e:
                        logger.warning(
                            f'Erro ao validar alocação via OPA para ticket {ticket_id}: {e}',
                            agent_id=agent_info.get('agent_id')
                        )
                        if not _config.opa_fail_open:
                            raise RuntimeError(f'Falha na validação de alocação: {str(e)}')

                logger.info(
                    f'Recursos alocados via Intelligent Scheduler para ticket {ticket_id}',
                    allocation_method=ticket.get('allocation_metadata', {}).get('allocation_method'),
                    priority_score=ticket.get('allocation_metadata', {}).get('priority_score'),
                    agent_id=ticket.get('allocation_metadata', {}).get('agent_id')
                )

                return ticket

            except Exception as e:
                logger.warning(
                    f'Falha no Intelligent Scheduler, usando fallback: {e}',
                    ticket_id=ticket_id
                )
                # Fallback para alocação stub

        # Fallback: alocação stub (scheduler não disponível ou falhou)
        logger.info(
            f'Usando alocação stub para ticket {ticket_id}',
            reason='scheduler_unavailable_or_failed'
        )

        # Calcular priority score simples
        risk_band = ticket.get('risk_band', 'normal')
        priority_weights = {'critical': 1.0, 'high': 0.7, 'normal': 0.5, 'low': 0.3}
        priority_score = priority_weights.get(risk_band, 0.5)

        # Adicionar metadata de alocação stub
        allocation_metadata = {
            'allocated_at': int(datetime.now().timestamp() * 1000),
            'agent_id': 'worker-agent-pool',
            'agent_type': 'worker-agent',
            'priority_score': priority_score,
            'agent_score': 0.5,
            'composite_score': 0.5,
            'allocation_method': 'fallback_stub',
            'workers_evaluated': 0
        }

        ticket['allocation_metadata'] = allocation_metadata

        # Adicionar predicted_duration_ms ao allocation_metadata para tracking de erro ML
        # Usado para ML error tracking e feedback loop
        if predicted_duration_ms is not None:
            ticket['allocation_metadata']['predicted_duration_ms'] = predicted_duration_ms
        ticket['allocation_metadata']['predicted_queue_ms'] = 2000.0
        ticket['allocation_metadata']['predicted_load_pct'] = 0.5
        ticket['allocation_metadata']['ml_enriched'] = False

        logger.info(
            f'Recursos alocados (stub) para ticket {ticket_id}',
            priority_score=priority_score
        )

        return ticket

    except Exception as e:
        logger.error(
            f'Erro ao alocar recursos para ticket {ticket_id}: {e}',
            exc_info=True
        )
        raise


@activity.defn
async def publish_ticket_to_kafka(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """
    Publica Execution Ticket no tópico Kafka execution.tickets.

    Tickets rejeitados pelo scheduler (status='rejected') não são publicados
    e são registrados como falha de alocação.

    Args:
        ticket: Execution ticket a ser publicado

    Returns:
        Resultado da publicação: {'published': bool, 'ticket_id': str, 'kafka_offset': int, 'ticket': dict}
        Para tickets rejeitados: {'published': False, 'ticket_id': str, 'rejected': True, 'rejection_reason': str}

    Raises:
        RuntimeError: Se dependências não foram injetadas ou persistência falhar (fail-closed)
    """
    ticket_id = ticket['ticket_id']

    # === Validar dependências injetadas no início ===
    if _config is None:
        raise RuntimeError(
            'Config não foi injetado nas activities. '
            'Verifique se set_activity_dependencies() foi chamado no worker.'
        )

    logger.info(
        'publishing_ticket_to_kafka',
        ticket_id=ticket_id,
        plan_id=ticket.get('plan_id'),
        fail_open_enabled=_config.MONGODB_FAIL_OPEN_EXECUTION_TICKETS
    )

    try:
        # === Gate: Verificar se ticket foi rejeitado pelo scheduler ===
        if ticket.get('status') == 'rejected' or ticket.get('allocation_metadata') is None:
            rejection_metadata = ticket.get('rejection_metadata', {})
            rejection_reason = rejection_metadata.get('rejection_reason', 'unknown')
            rejection_message = rejection_metadata.get('rejection_message', 'Ticket rejeitado sem motivo especificado')

            logger.error(
                'ticket_rejected_not_published',
                ticket_id=ticket_id,
                rejection_reason=rejection_reason,
                rejection_message=rejection_message,
                plan_id=ticket.get('plan_id')
            )

            # Persistir ticket rejeitado no MongoDB para auditoria
            if _mongodb_client is not None:
                try:
                    ticket['status'] = 'rejected'
                    await _mongodb_client.save_execution_ticket(ticket)
                    logger.info(
                        f'Ticket rejeitado {ticket_id} persistido no MongoDB para auditoria',
                        plan_id=ticket.get('plan_id')
                    )
                except Exception as db_error:
                    logger.warning(
                        f'Erro ao persistir ticket rejeitado no MongoDB: {db_error}',
                        ticket_id=ticket_id
                    )

            return {
                'published': False,
                'ticket_id': ticket_id,
                'rejected': True,
                'rejection_reason': rejection_reason,
                'rejection_message': rejection_message,
                'ticket': ticket
            }

        # Verificar se dependências foram injetadas
        if _kafka_producer is None:
            raise RuntimeError('Kafka producer não foi injetado nas activities')
        if _mongodb_client is None:
            raise RuntimeError('MongoDB client não foi injetado nas activities')

        # ML Error Tracking: se ticket está sendo atualizado para COMPLETED, rastrear erro
        if ticket.get('status') == 'COMPLETED' and ticket.get('actual_duration_ms') is not None:
            try:
                from src.observability.metrics import get_metrics
                from src.activities.result_consolidation import compute_and_record_ml_error
                metrics = get_metrics()
                compute_and_record_ml_error(ticket, metrics)
            except Exception as e:
                # Fail-open: não bloqueia publicação
                logger.warning(
                    'ml_error_tracking_failed_in_publish',
                    ticket_id=ticket_id,
                    error=str(e)
                )

        # IMPORTANTE: O ticket deve ser publicado com status 'PENDING'.
        # O Worker Agent é responsável por mudar o status para 'RUNNING' quando iniciar o processamento.
        # Ref: services/worker-agents/src/engine/execution_engine.py linha 85

        # Publicar ticket no Kafka usando o producer real
        kafka_result = await _kafka_producer.publish_ticket(ticket)

        logger.info(
            f'Ticket {ticket_id} publicado no Kafka. Será processado pelo Execution Ticket Service',
            plan_id=ticket['plan_id'],
            topic=kafka_result['topic'],
            partition=kafka_result['partition'],
            offset=kafka_result['offset'],
            webhook_url=ticket.get('metadata', {}).get('webhook_url')
        )

        # Persistir ticket no MongoDB para auditoria
        try:
            await _mongodb_client.save_execution_ticket(ticket)
            logger.info(
                'ticket_persisted_successfully',
                ticket_id=ticket_id,
                plan_id=ticket['plan_id']
            )
        except CircuitBreakerError:
            # Circuit breaker aberto - problema sistêmico, sempre propagar
            logger.error(
                'execution_ticket_persist_circuit_open',
                ticket_id=ticket_id,
                plan_id=ticket.get('plan_id'),
                circuit_state='open'
            )
            # Circuit breaker indica problema sistêmico - propagar para retry
            raise RuntimeError(
                f'Circuit breaker aberto para persistência do ticket {ticket_id}. '
                'Problema sistêmico detectado no MongoDB.'
            )

        except PyMongoError as db_error:
            # Erro de MongoDB - verificar política de fail-open
            logger.error(
                'execution_ticket_persist_failed',
                ticket_id=ticket_id,
                plan_id=ticket.get('plan_id'),
                error=str(db_error),
                error_type=type(db_error).__name__,
                fail_open_enabled=_config.MONGODB_FAIL_OPEN_EXECUTION_TICKETS
            )

            # Verificar política de fail-open configurável
            if _config.MONGODB_FAIL_OPEN_EXECUTION_TICKETS:
                logger.warning(
                    'execution_ticket_persist_fail_open_activated',
                    ticket_id=ticket_id,
                    plan_id=ticket.get('plan_id')
                )
                # Registrar métrica de fail-open
                try:
                    from src.observability.metrics import get_metrics
                    metrics = get_metrics()
                    metrics.record_mongodb_persistence_fail_open('execution_tickets')
                except Exception:
                    pass  # Não falhar por causa de métricas
                # Continuar sem persistência
            else:
                # Fail-closed: propagar erro para retry do Temporal
                # Auditoria é crítica para compliance
                raise RuntimeError(
                    f'Falha crítica na persistência do ticket {ticket_id}: {str(db_error)}'
                )

        except Exception as e:
            # Erro inesperado - logar e verificar política
            logger.error(
                'execution_ticket_persist_unexpected_error',
                ticket_id=ticket_id,
                plan_id=ticket.get('plan_id'),
                error=str(e),
                error_type=type(e).__name__,
                fail_open_enabled=_config.MONGODB_FAIL_OPEN_EXECUTION_TICKETS,
                exc_info=True
            )

            if _config.MONGODB_FAIL_OPEN_EXECUTION_TICKETS:
                logger.warning(
                    'execution_ticket_persist_fail_open_activated',
                    ticket_id=ticket_id,
                    plan_id=ticket.get('plan_id'),
                    error_type='unexpected'
                )
                # Registrar métrica de fail-open
                try:
                    from src.observability.metrics import get_metrics
                    metrics = get_metrics()
                    metrics.record_mongodb_persistence_fail_open('execution_tickets')
                except Exception:
                    pass  # Não falhar por causa de métricas
            else:
                raise RuntimeError(
                    f'Erro inesperado na persistência do ticket {ticket_id}: {str(e)}'
                )

        # Construir resultado com informações do Kafka
        result = {
            'published': True,
            'ticket_id': ticket_id,
            'topic': kafka_result['topic'],
            'partition': kafka_result['partition'],
            'kafka_offset': kafka_result['offset'],
            'timestamp': kafka_result['timestamp'],
            'ticket': ticket
        }

        return result

    except RuntimeError as e:
        # Erro de configuração - não retry
        logger.error(
            f'Erro de configuração ao publicar ticket {ticket_id}: {e}',
            exc_info=True
        )
        raise

    except Exception as e:
        # Erro na publicação - permite retry pelo Temporal
        logger.error(
            f'Erro ao publicar ticket {ticket_id} (plan_id={ticket.get("plan_id")}): {e}'
        )
        raise
