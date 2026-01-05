import structlog
import asyncio
from typing import Dict, Any
from datetime import datetime

from neural_hive_observability import get_tracer

logger = structlog.get_logger()


class TaskExecutionError(Exception):
    pass


class ExecutionEngine:
    '''Orquestrador principal de execução de tarefas'''

    def __init__(self, config, ticket_client, result_producer, dependency_coordinator, executor_registry, metrics=None):
        self.config = config
        self.ticket_client = ticket_client
        self.result_producer = result_producer
        self.dependency_coordinator = dependency_coordinator
        self.executor_registry = executor_registry
        self.metrics = metrics
        self.logger = logger.bind(service='execution_engine')

        # Rastrear tarefas em execução
        self.active_tasks: Dict[str, asyncio.Task] = {}

        # Limitar concorrência
        self.task_semaphore = asyncio.Semaphore(config.max_concurrent_tasks)

    async def process_ticket(self, ticket: Dict[str, Any]):
        '''Processar ticket de execução'''
        ticket_id = ticket.get('ticket_id')

        # Validar se já está em execução
        if ticket_id in self.active_tasks:
            self.logger.warning('ticket_already_processing', ticket_id=ticket_id)
            return

        # Criar task assíncrona
        task = asyncio.create_task(self._execute_ticket(ticket))
        self.active_tasks[ticket_id] = task

        self.logger.info(
            'ticket_processing_started',
            ticket_id=ticket_id,
            task_type=ticket.get('task_type'),
            active_tasks_count=len(self.active_tasks)
        )

        if self.metrics:
            if hasattr(self.metrics, 'tickets_processing_total'):
                self.metrics.tickets_processing_total.labels(task_type=ticket.get('task_type')).inc()
            if hasattr(self.metrics, 'active_tasks'):
                self.metrics.active_tasks.set(len(self.active_tasks))

    async def _execute_ticket(self, ticket: Dict[str, Any]):
        '''Executar ticket com coordenação de dependências e retry logic'''
        ticket_id = ticket.get('ticket_id')
        task_type = ticket.get('task_type')
        start_time = datetime.now()

        tracer = get_tracer()
        with tracer.start_as_current_span("ticket_execution") as span:
            span.set_attribute("neural.hive.ticket_id", ticket_id)
            span.set_attribute("neural.hive.task_type", task_type)
            span.set_attribute("neural.hive.plan_id", ticket.get('plan_id', ''))
            span.set_attribute("neural.hive.intent_id", ticket.get('intent_id', ''))

            try:
                # Adquirir semaphore (limitar concorrência)
                async with self.task_semaphore:

                    self.logger.info(
                        'ticket_execution_started',
                        ticket_id=ticket_id,
                        task_type=task_type,
                        plan_id=ticket.get('plan_id'),
                        intent_id=ticket.get('intent_id')
                    )

                    # Atualizar status para RUNNING
                    await self.ticket_client.update_ticket_status(ticket_id, 'RUNNING')

                    # Verificar dependências
                    try:
                        await self.dependency_coordinator.wait_for_dependencies(ticket)
                    except Exception as dep_error:
                        self.logger.error(
                            'dependency_check_failed',
                            ticket_id=ticket_id,
                            error=str(dep_error)
                        )
                        span.set_attribute("error", True)
                        span.set_attribute("error.type", "dependency")
                        # Marcar como FAILED
                        await self.ticket_client.update_ticket_status(
                            ticket_id,
                            'FAILED',
                            error_message=f'Dependency check failed: {str(dep_error)}'
                        )
                        # Publicar resultado
                        await self.result_producer.publish_result(
                            ticket_id,
                            'FAILED',
                            {'success': False},
                            error_message=str(dep_error)
                        )
                        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                        if self.metrics:
                            if hasattr(self.metrics, 'tickets_failed_total'):
                                self.metrics.tickets_failed_total.labels(task_type=task_type, error_type='dependency').inc()
                            if hasattr(self.metrics, 'task_duration_seconds'):
                                self.metrics.task_duration_seconds.labels(task_type=task_type).observe(duration_ms / 1000)
                        return

                    # Executar tarefa com retry
                    try:
                        result = await self._execute_task_with_retry(ticket)

                        # Sucesso
                        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

                        await self.ticket_client.update_ticket_status(
                            ticket_id,
                            'COMPLETED',
                            actual_duration_ms=duration_ms
                        )

                        await self.result_producer.publish_result(
                            ticket_id,
                            'COMPLETED',
                            result,
                            actual_duration_ms=duration_ms
                        )

                        self.logger.info(
                            'ticket_execution_completed',
                            ticket_id=ticket_id,
                            task_type=task_type,
                            duration_ms=duration_ms
                        )

                        if self.metrics:
                            if hasattr(self.metrics, 'tickets_completed_total'):
                                self.metrics.tickets_completed_total.labels(task_type=task_type).inc()
                            if hasattr(self.metrics, 'task_duration_seconds'):
                                self.metrics.task_duration_seconds.labels(task_type=task_type).observe(duration_ms / 1000)

                    except TaskExecutionError as exec_error:
                        # Falha após todas as tentativas
                        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                        span.set_attribute("error", True)
                        span.set_attribute("error.type", "execution_error")

                        await self.ticket_client.update_ticket_status(
                            ticket_id,
                            'FAILED',
                            error_message=str(exec_error),
                            actual_duration_ms=duration_ms
                        )

                        await self.result_producer.publish_result(
                            ticket_id,
                            'FAILED',
                            {'success': False},
                            error_message=str(exec_error),
                            actual_duration_ms=duration_ms
                        )

                        self.logger.error(
                            'ticket_execution_failed',
                            ticket_id=ticket_id,
                            task_type=task_type,
                            error=str(exec_error),
                            duration_ms=duration_ms
                        )

                        if self.metrics:
                            if hasattr(self.metrics, 'tickets_failed_total'):
                                self.metrics.tickets_failed_total.labels(task_type=task_type, error_type='execution_error').inc()
                            if hasattr(self.metrics, 'task_duration_seconds'):
                                self.metrics.task_duration_seconds.labels(task_type=task_type).observe(duration_ms / 1000)

            except asyncio.TimeoutError:
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                span.set_attribute('error', True)
                span.set_attribute('error.type', 'timeout')
                self.logger.error('ticket_execution_timeout', ticket_id=ticket_id)
                await self.ticket_client.update_ticket_status(
                    ticket_id,
                    'FAILED',
                    error_message='Execution timeout',
                    actual_duration_ms=duration_ms
                )
                try:
                    await self.result_producer.publish_result(
                        ticket_id,
                        'FAILED',
                        {'success': False},
                        error_message='Execution timeout',
                        actual_duration_ms=duration_ms
                    )
                except Exception as pub_exc:
                    self.logger.error('result_publish_failed_timeout', ticket_id=ticket_id, error=str(pub_exc))
                if self.metrics:
                    if hasattr(self.metrics, 'tickets_failed_total'):
                        self.metrics.tickets_failed_total.labels(task_type=task_type, error_type='timeout').inc()
                    if hasattr(self.metrics, 'task_duration_seconds'):
                        self.metrics.task_duration_seconds.labels(task_type=task_type).observe(duration_ms / 1000)

            except Exception as e:
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                span.set_attribute('error', True)
                span.set_attribute('error.type', 'exception')
                self.logger.error(
                    'ticket_execution_error',
                    ticket_id=ticket_id,
                    error=str(e),
                    exc_info=True
                )
                await self.ticket_client.update_ticket_status(
                    ticket_id,
                    'FAILED',
                    error_message=str(e),
                    actual_duration_ms=duration_ms
                )
                try:
                    await self.result_producer.publish_result(
                        ticket_id,
                        'FAILED',
                        {'success': False},
                        error_message=str(e),
                        actual_duration_ms=duration_ms
                    )
                except Exception as pub_exc:
                    self.logger.error('result_publish_failed_error', ticket_id=ticket_id, error=str(pub_exc))
                if self.metrics:
                    if hasattr(self.metrics, 'tickets_failed_total'):
                        self.metrics.tickets_failed_total.labels(task_type=task_type, error_type='exception').inc()
                    if hasattr(self.metrics, 'task_duration_seconds'):
                        self.metrics.task_duration_seconds.labels(task_type=task_type).observe(duration_ms / 1000)

            finally:
                # Remover de active_tasks
                if ticket_id in self.active_tasks:
                    del self.active_tasks[ticket_id]
                if self.metrics and hasattr(self.metrics, 'active_tasks'):
                    self.metrics.active_tasks.set(len(self.active_tasks))

    async def _execute_task_with_retry(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        '''Executar tarefa com retry logic'''
        task_type = ticket.get('task_type')
        ticket_id = ticket.get('ticket_id')
        sla = ticket.get('sla', {})
        max_retries = sla.get('max_retries', self.config.max_retries_per_ticket)
        timeout_ms = sla.get('timeout_ms', 60000)

        # Calcular timeout
        timeout_seconds = (timeout_ms * self.config.task_timeout_multiplier) / 1000

        # Obter executor
        executor = self.executor_registry.get_executor(task_type)

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                self.logger.debug(
                    'task_execution_attempt',
                    ticket_id=ticket_id,
                    task_type=task_type,
                    attempt=attempt + 1,
                    max_retries=max_retries
                )

                # Executar com timeout
                result = await asyncio.wait_for(
                    executor.execute(ticket),
                    timeout=timeout_seconds
                )

                return result

            except asyncio.TimeoutError as e:
                last_error = f'Timeout after {timeout_seconds}s'
                self.logger.warning(
                    'task_execution_timeout',
                    ticket_id=ticket_id,
                    task_type=task_type,
                    attempt=attempt + 1,
                    timeout_seconds=timeout_seconds
                )
                if self.metrics and hasattr(self.metrics, 'task_retries_total'):
                    self.metrics.task_retries_total.labels(task_type=task_type, attempt=str(attempt + 1)).inc()

            except Exception as e:
                last_error = str(e)
                self.logger.warning(
                    'task_execution_failed_retry',
                    ticket_id=ticket_id,
                    task_type=task_type,
                    attempt=attempt + 1,
                    error=str(e)
                )
                if self.metrics and hasattr(self.metrics, 'task_retries_total'):
                    self.metrics.task_retries_total.labels(task_type=task_type, attempt=str(attempt + 1)).inc()

            # Backoff exponencial
            if attempt < max_retries:
                backoff = min(
                    self.config.retry_backoff_base_seconds * (2 ** attempt),
                    self.config.retry_backoff_max_seconds
                )
                await asyncio.sleep(backoff)

        # Todas as tentativas falharam
        raise TaskExecutionError(f'Task execution failed after {max_retries + 1} attempts: {last_error}')

    async def shutdown(self, timeout_seconds: int = 30):
        '''Shutdown graceful do execution engine'''
        if not self.active_tasks:
            self.logger.info('no_active_tasks_to_shutdown')
            return

        self.logger.info(
            'shutting_down_execution_engine',
            active_tasks_count=len(self.active_tasks),
            timeout_seconds=timeout_seconds
        )

        # Aguardar conclusão de tarefas ativas
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.active_tasks.values(), return_exceptions=True),
                timeout=timeout_seconds
            )
            self.logger.info('all_active_tasks_completed')

        except asyncio.TimeoutError:
            # Cancelar tarefas que não concluíram
            cancelled_count = 0
            for ticket_id, task in self.active_tasks.items():
                if not task.done():
                    task.cancel()
                    cancelled_count += 1
                    self.logger.warning('task_cancelled', ticket_id=ticket_id)

            if self.metrics and cancelled_count > 0:
                for _ in range(cancelled_count):
                    self.metrics.tasks_cancelled_total.inc()
            self.logger.warning(
                'shutdown_timeout_tasks_cancelled',
                cancelled_count=cancelled_count
            )
