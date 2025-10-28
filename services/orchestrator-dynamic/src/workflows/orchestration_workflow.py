"""
Workflow Temporal principal para orquestração de execução (Fluxo C).
Implementa as etapas C1-C6 conforme documento-06.
"""
from datetime import timedelta
from typing import Any, Dict

from temporalio import workflow

# Import activities (serão definidos posteriormente)
with workflow.unsafe.imports_passed_through():
    from src.activities.plan_validation import (
        validate_cognitive_plan,
        audit_validation,
        optimize_dag
    )
    from src.activities.ticket_generation import (
        generate_execution_tickets,
        allocate_resources,
        publish_ticket_to_kafka
    )
    from src.activities.result_consolidation import (
        consolidate_results,
        trigger_self_healing,
        publish_telemetry,
        buffer_telemetry
    )


@workflow.defn
class OrchestrationWorkflow:
    """
    Workflow de orquestração que converte Cognitive Plans em Execution Tickets.

    Implementa o Fluxo C (Orquestração de Execução Adaptativa) conforme
    documento-06-fluxos-processos-neural-hive-mind.md Seção 6.
    """

    def __init__(self):
        self._status = 'initializing'
        self._tickets_generated = []
        self._workflow_result = {}

    @workflow.run
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executa o workflow de orquestração.

        Args:
            input_data: Dicionário contendo:
                - consolidated_decision: Decisão consolidada do Consensus Engine
                - cognitive_plan: Plano cognitivo a ser executado

        Returns:
            Dicionário com resultado da orquestração (tickets, status, métricas)
        """
        consolidated_decision = input_data['consolidated_decision']
        cognitive_plan = input_data['cognitive_plan']

        workflow_id = workflow.info().workflow_id
        plan_id = cognitive_plan.get('plan_id')
        intent_id = cognitive_plan.get('intent_id')

        workflow.logger.info(
            f'Iniciando workflow de orquestração',
            workflow_id=workflow_id,
            plan_id=plan_id,
            intent_id=intent_id
        )

        try:
            # === C1: Validar Plano Cognitivo ===
            self._status = 'validating_plan'
            workflow.logger.info('C1: Validando plano cognitivo')

            validation_result = await workflow.execute_activity(
                validate_cognitive_plan,
                args=[plan_id, cognitive_plan],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=workflow.RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=timedelta(milliseconds=500),
                    non_retryable_error_types=['InvalidSchemaError']
                )
            )

            if not validation_result['valid']:
                workflow.logger.error(
                    'Plano cognitivo inválido',
                    errors=validation_result['errors']
                )
                raise workflow.ApplicationError(
                    f'Plano cognitivo inválido: {validation_result["errors"]}',
                    non_retryable=True
                )

            # Auditar validação
            await workflow.execute_activity(
                audit_validation,
                args=[plan_id, validation_result],
                start_to_close_timeout=timedelta(seconds=3),
                retry_policy=workflow.RetryPolicy(maximum_attempts=3)
            )

            workflow.logger.info('Plano cognitivo validado com sucesso')

            # === C2: Quebrar Plano em Tickets ===
            self._status = 'generating_tickets'
            workflow.logger.info('C2: Gerando execution tickets')

            tickets = await workflow.execute_activity(
                generate_execution_tickets,
                args=[cognitive_plan, consolidated_decision],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=workflow.RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=timedelta(seconds=1)
                )
            )

            self._tickets_generated = tickets
            workflow.logger.info(f'Gerados {len(tickets)} execution tickets')

            # === C3: Alocar Recursos ===
            self._status = 'allocating_resources'
            workflow.logger.info('C3: Alocando recursos')

            allocated_tickets = []
            for ticket in tickets:
                allocated_ticket = await workflow.execute_activity(
                    allocate_resources,
                    args=[ticket],
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=workflow.RetryPolicy(
                        maximum_attempts=3,
                        initial_interval=timedelta(seconds=2)
                    )
                )
                allocated_tickets.append(allocated_ticket)

            workflow.logger.info('Recursos alocados para todos os tickets')

            # === C4: Executar Tarefas (publicar tickets) ===
            self._status = 'publishing_tickets'
            workflow.logger.info('C4: Publicando tickets no Kafka')

            published_tickets = []
            for ticket in allocated_tickets:
                publish_result = await workflow.execute_activity(
                    publish_ticket_to_kafka,
                    args=[ticket],
                    start_to_close_timeout=timedelta(seconds=15),
                    retry_policy=workflow.RetryPolicy(
                        maximum_attempts=5,
                        initial_interval=timedelta(seconds=1),
                        backoff_coefficient=2.0
                    )
                )
                published_tickets.append(publish_result)

            workflow.logger.info(f'Publicados {len(published_tickets)} tickets no Kafka')

            # === C5: Consolidar Resultado ===
            self._status = 'consolidating_results'
            workflow.logger.info('C5: Consolidando resultados')

            workflow_result = await workflow.execute_activity(
                consolidate_results,
                args=[published_tickets, workflow_id],
                start_to_close_timeout=timedelta(seconds=20),
                retry_policy=workflow.RetryPolicy(maximum_attempts=2)
            )

            self._workflow_result = workflow_result

            # Se resultado inconsistente, acionar autocura
            if not workflow_result.get('consistent', True):
                workflow.logger.warning('Resultado inconsistente detectado, acionando autocura')
                await workflow.execute_activity(
                    trigger_self_healing,
                    args=[workflow_id, workflow_result.get('errors', [])],
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=3)
                )

            # === C6: Publicar Telemetria ===
            self._status = 'publishing_telemetry'
            workflow.logger.info('C6: Publicando telemetria')

            try:
                await workflow.execute_activity(
                    publish_telemetry,
                    args=[workflow_result],
                    start_to_close_timeout=timedelta(seconds=15),
                    retry_policy=workflow.RetryPolicy(
                        maximum_attempts=5,
                        initial_interval=timedelta(seconds=1),
                        backoff_coefficient=2.0
                    )
                )
            except Exception as e:
                workflow.logger.warning(f'Falha ao publicar telemetria, usando buffer: {e}')
                await workflow.execute_activity(
                    buffer_telemetry,
                    args=[workflow_result],
                    start_to_close_timeout=timedelta(seconds=5),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=3)
                )

            # Workflow concluído com sucesso
            self._status = 'completed'
            workflow.logger.info('Workflow de orquestração concluído com sucesso')

            return {
                'workflow_id': workflow_id,
                'plan_id': plan_id,
                'intent_id': intent_id,
                'status': 'success',
                'tickets_generated': len(tickets),
                'result': workflow_result
            }

        except Exception as e:
            self._status = 'failed'
            workflow.logger.error(f'Erro no workflow de orquestração: {e}', exc_info=True)
            raise

    @workflow.signal
    async def ticket_completed(self, ticket_id: str, result: Dict[str, Any]):
        """
        Signal para notificar conclusão de um ticket.

        Args:
            ticket_id: ID do ticket concluído
            result: Resultado da execução do ticket
        """
        workflow.logger.info(f'Ticket {ticket_id} concluído', result=result)

    @workflow.signal
    async def cancel_workflow(self):
        """Signal para cancelar workflow manualmente."""
        workflow.logger.info('Recebida solicitação de cancelamento do workflow')
        self._status = 'cancelled'

    @workflow.query
    def get_status(self) -> Dict[str, Any]:
        """
        Query para consultar status atual do workflow.

        Returns:
            Dicionário com status e informações do workflow
        """
        return {
            'status': self._status,
            'tickets_generated': len(self._tickets_generated),
            'workflow_result': self._workflow_result
        }

    @workflow.query
    def get_tickets(self) -> list:
        """
        Query para listar tickets gerados.

        Returns:
            Lista de tickets gerados
        """
        return self._tickets_generated
