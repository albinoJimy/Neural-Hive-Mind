"""
Activities Temporal para geração de Execution Tickets (Etapa C2).
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List

from temporalio import activity
import structlog

logger = structlog.get_logger()

# Global clients (serão injetados pelo worker)
_kafka_producer = None
_mongodb_client = None
_registry_client = None


def set_activity_dependencies(kafka_producer, mongodb_client, registry_client=None):
    """
    Injeta dependências globais nas activities.

    Args:
        kafka_producer: Cliente Kafka Producer
        mongodb_client: Cliente MongoDB
        registry_client: Cliente do Service Registry (opcional)
    """
    global _kafka_producer, _mongodb_client, _registry_client
    _kafka_producer = kafka_producer
    _mongodb_client = mongodb_client
    _registry_client = registry_client


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
    activity.logger.info(f'Gerando execution tickets para plano {cognitive_plan["plan_id"]}')

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

            # Calcular SLA
            estimated_duration_ms = task.get('estimated_duration_ms', 60000)
            timeout_ms = int(estimated_duration_ms * 1.5)  # Buffer 50%
            deadline = int((datetime.now().timestamp() + timeout_ms / 1000) * 1000)

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

        activity.logger.info(
            f'Gerados {len(ordered_tickets)} execution tickets',
            plan_id=plan_id,
            risk_band=risk_band
        )

        return ordered_tickets

    except Exception as e:
        activity.logger.error(f'Erro ao gerar execution tickets: {e}', exc_info=True)
        raise


@activity.defn
async def allocate_resources(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aloca recursos para um ticket integrando com Service Registry.

    Args:
        ticket: Execution ticket

    Returns:
        Ticket atualizado com allocation_metadata
    """
    activity.logger.info(f'Alocando recursos para ticket {ticket["ticket_id"]}')

    try:
        allocated = False
        allocated_agent_id = None
        allocated_agent_type = None
        allocation_score = 0.0

        # Extrair informações do ticket
        required_capabilities = ticket.get('required_capabilities', [])
        security_level = ticket.get('security_level', 'INTERNAL')
        risk_band = ticket.get('risk_band', 'medium')
        namespace = ticket.get('metadata', {}).get('namespace', 'default')

        # Se registry_client está disponível, usar discovery
        if _registry_client and required_capabilities:
            try:
                # Criar filtros baseados no ticket
                filters = {
                    'namespace': namespace,
                    'status': 'HEALTHY'
                }

                activity.logger.info(
                    f'Descobrindo agentes para ticket {ticket["ticket_id"]}',
                    capabilities=required_capabilities,
                    filters=filters
                )

                # Chamar Service Registry para descobrir agentes
                # TODO: Implementar chamada gRPC real quando proto estiver pronto
                # response = await _registry_client.DiscoverAgents(
                #     capabilities=required_capabilities,
                #     filters=filters,
                #     max_results=5
                # )

                # Mock para desenvolvimento
                # if response and response.agents:
                #     best_agent = response.agents[0]
                #     allocated = True
                #     allocated_agent_id = best_agent.agent_id
                #     allocated_agent_type = best_agent.agent_type
                #     allocation_score = 0.95  # Calcular baseado em scores

                activity.logger.info(
                    f'Agentes descobertos para ticket {ticket["ticket_id"]}',
                    allocated=allocated,
                    agent_id=allocated_agent_id
                )

            except Exception as e:
                activity.logger.warning(
                    f'Falha ao descobrir agentes via Service Registry: {e}',
                    ticket_id=ticket["ticket_id"]
                )
                # Fallback para alocação stub

        # Fallback: alocação stub (se registry não disponível ou falhou)
        if not allocated:
            activity.logger.info(
                f'Usando alocação stub para ticket {ticket["ticket_id"]}',
                reason='registry_unavailable_or_no_match'
            )
            allocated = True  # Stub sempre aloca

        # Calcular priority score
        priority_weights = {'critical': 1.0, 'high': 0.7, 'normal': 0.5, 'low': 0.3}
        priority_score = priority_weights.get(risk_band, 0.5)

        # Combinar com allocation_score se disponível
        if allocation_score > 0:
            priority_score = (priority_score * 0.5) + (allocation_score * 0.5)

        # Adicionar metadata de alocação
        allocation_metadata = {
            'allocated': allocated,
            'priority_score': priority_score,
            'allocated_at': int(datetime.now().timestamp() * 1000)
        }

        if allocated_agent_id:
            allocation_metadata['allocated_agent_id'] = allocated_agent_id
            allocation_metadata['allocated_agent_type'] = allocated_agent_type
            allocation_metadata['allocation_score'] = allocation_score

            # Adicionar webhook_url se agente registrado no Service Registry
            # TODO: Consultar Service Registry para obter webhook_url do agente
            # if _registry_client:
            #     try:
            #         agent_info = await _registry_client.GetAgent(agent_id=allocated_agent_id)
            #         if agent_info and agent_info.webhook_url:
            #             ticket['metadata']['webhook_url'] = agent_info.webhook_url
            #     except Exception as e:
            #         activity.logger.warning(f'Failed to get webhook URL for agent {allocated_agent_id}: {e}')

        ticket['metadata']['allocation_metadata'] = allocation_metadata

        activity.logger.info(
            f'Recursos alocados para ticket {ticket["ticket_id"]}',
            allocated=allocated,
            priority_score=priority_score,
            agent_id=allocated_agent_id,
            webhook_url=ticket['metadata'].get('webhook_url')
        )

        return ticket

    except Exception as e:
        activity.logger.error(f'Erro ao alocar recursos para ticket {ticket["ticket_id"]}: {e}', exc_info=True)
        raise


@activity.defn
async def publish_ticket_to_kafka(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """
    Publica Execution Ticket no tópico Kafka execution.tickets.

    Args:
        ticket: Execution ticket a ser publicado

    Returns:
        Resultado da publicação: {'published': bool, 'ticket_id': str, 'kafka_offset': int, 'ticket': dict}
    """
    ticket_id = ticket['ticket_id']
    activity.logger.info(f'Publicando ticket {ticket_id} no Kafka')

    try:
        # Verificar se dependências foram injetadas
        if _kafka_producer is None:
            raise RuntimeError('Kafka producer não foi injetado nas activities')
        if _mongodb_client is None:
            raise RuntimeError('MongoDB client não foi injetado nas activities')

        # Atualizar status do ticket para RUNNING
        ticket['status'] = 'RUNNING'

        # Publicar ticket no Kafka usando o producer real
        kafka_result = await _kafka_producer.publish_ticket(ticket)

        activity.logger.info(
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
            activity.logger.info(
                f'Ticket {ticket_id} persistido no MongoDB',
                plan_id=ticket['plan_id']
            )
        except Exception as db_error:
            # Log do erro mas não falha a publicação do ticket
            # O ticket já foi publicado no Kafka com sucesso
            activity.logger.error(
                f'Erro ao persistir ticket no MongoDB: {db_error}',
                ticket_id=ticket_id,
                exc_info=True
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
        activity.logger.error(
            f'Erro de configuração ao publicar ticket {ticket_id}: {e}',
            exc_info=True
        )
        raise

    except Exception as e:
        # Erro na publicação - permite retry pelo Temporal
        activity.logger.error(
            f'Erro ao publicar ticket {ticket_id}: {e}',
            plan_id=ticket.get('plan_id'),
            exc_info=True
        )
        raise
