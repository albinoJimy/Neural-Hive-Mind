import structlog
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from neural_hive_observability import get_tracer

logger = structlog.get_logger()


class TaskExecutionError(Exception):
    pass


class ExecutionEngine:
    '''Orquestrador principal de execução de tarefas'''

    # TTL para deduplicação de tickets (7 dias - alinhado com retention Kafka)
    DEDUPLICATION_TTL_SECONDS = 604800
    # TTL para chave de processing (10 minutos - tempo máximo esperado de processamento)
    PROCESSING_TTL_SECONDS = 600

    def __init__(self, config, ticket_client, result_producer, dependency_coordinator, executor_registry, redis_client=None, metrics=None):
        self.config = config
        self.ticket_client = ticket_client
        self.result_producer = result_producer
        self.dependency_coordinator = dependency_coordinator
        self.executor_registry = executor_registry
        self.redis_client = redis_client
        self.metrics = metrics
        self.logger = logger.bind(service='execution_engine')

        # Rastrear tarefas em execução
        self.active_tasks: Dict[str, asyncio.Task] = {}

        # Limitar concorrência
        self.task_semaphore = asyncio.Semaphore(config.max_concurrent_tasks)

    async def _is_duplicate_ticket(self, ticket_id: str) -> bool:
        """
        Verificar se ticket já foi processado usando Redis (two-phase scheme).

        Implementa deduplicação em duas fases:
        1. Verifica se já existe chave 'processed' (processamento concluído anteriormente)
        2. Verifica se já existe chave 'processing' (processamento em andamento)
        3. Se nenhuma existe, marca como 'processing' com TTL curto

        Args:
            ticket_id: ID do execution ticket

        Returns:
            True se duplicata (já processado ou em processamento), False caso contrário
        """
        if not self.redis_client:
            self.logger.warning('redis_client_not_available_skipping_deduplication')
            return False

        try:
            processed_key = f"ticket:processed:{ticket_id}"
            processing_key = f"ticket:processing:{ticket_id}"

            # Fase 1: Verificar se já foi processado com sucesso
            if await self.redis_client.exists(processed_key):
                self.logger.info(
                    'duplicate_ticket_detected',
                    ticket_id=ticket_id,
                    message='Ticket já foi processado com sucesso, ignorando'
                )
                if self.metrics and hasattr(self.metrics, 'duplicates_detected_total'):
                    self.metrics.duplicates_detected_total.labels(component='execution_engine').inc()
                return True

            # Fase 2: Tentar marcar como em processamento (SETNX)
            is_new = await self.redis_client.set(
                processing_key,
                "1",
                ex=self.PROCESSING_TTL_SECONDS,
                nx=True
            )

            if not is_new:
                self.logger.info(
                    'ticket_already_processing',
                    ticket_id=ticket_id,
                    message='Ticket já está em processamento por outro worker, ignorando'
                )
                if self.metrics and hasattr(self.metrics, 'duplicates_detected_total'):
                    self.metrics.duplicates_detected_total.labels(component='execution_engine').inc()
                return True

            self.logger.debug('ticket_marked_as_processing', ticket_id=ticket_id)
            return False

        except Exception as e:
            self.logger.error(
                'deduplication_check_failed',
                ticket_id=ticket_id,
                error=str(e),
                message='Continuando processamento sem deduplicação'
            )
            # Fail-open: continuar processamento em caso de erro no Redis
            return False

    async def _mark_ticket_processed(self, ticket_id: str) -> None:
        """
        Marca ticket como processado com sucesso e remove chave de processing.

        Args:
            ticket_id: ID do execution ticket
        """
        if not self.redis_client or not ticket_id:
            return

        try:
            processed_key = f"ticket:processed:{ticket_id}"
            processing_key = f"ticket:processing:{ticket_id}"

            # Marcar como processado com TTL longo
            await self.redis_client.set(
                processed_key,
                "1",
                ex=self.DEDUPLICATION_TTL_SECONDS
            )

            # Remover chave de processing
            await self.redis_client.delete(processing_key)

            self.logger.debug('ticket_marked_as_processed', ticket_id=ticket_id)

        except Exception as e:
            self.logger.error(
                'mark_ticket_processed_failed',
                ticket_id=ticket_id,
                error=str(e)
            )

    async def _clear_ticket_processing(self, ticket_id: str) -> None:
        """
        Limpa chave de processing para permitir reprocessamento após falha.

        Args:
            ticket_id: ID do execution ticket
        """
        if not self.redis_client or not ticket_id:
            return

        try:
            processing_key = f"ticket:processing:{ticket_id}"
            await self.redis_client.delete(processing_key)
            self.logger.debug('ticket_processing_cleared', ticket_id=ticket_id)

        except Exception as e:
            self.logger.error(
                'clear_ticket_processing_failed',
                ticket_id=ticket_id,
                error=str(e)
            )

    async def process_ticket(self, ticket: Dict[str, Any]):
        '''Processar ticket de execução'''
        ticket_id = ticket.get('ticket_id')

        # Validar que ticket_id está presente e não é vazio
        if not ticket_id:
            self.logger.error(
                'ticket_id_missing_or_empty',
                ticket=ticket,
                message='Ticket inválido: ticket_id ausente ou vazio. Ignorando processamento.'
            )
            if self.metrics and hasattr(self.metrics, 'tickets_failed_total'):
                task_type = ticket.get('task_type', 'unknown')
                self.metrics.tickets_failed_total.labels(task_type=task_type, error_type='invalid_ticket_id').inc()
            return

        # Verificar duplicata via Redis (idempotência)
        if await self._is_duplicate_ticket(ticket_id):
            self.logger.info('duplicate_ticket_skipped', ticket_id=ticket_id)
            if self.metrics and hasattr(self.metrics, 'duplicates_detected_total'):
                self.metrics.duplicates_detected_total.labels(component='execution_engine').inc()
            return

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

                        # Limpar chave de processing para permitir retry (two-phase scheme)
                        await self._clear_ticket_processing(ticket_id)

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

                        # Marcar ticket como processado com sucesso (two-phase scheme)
                        await self._mark_ticket_processed(ticket_id)

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

                        # Limpar chave de processing para permitir retry (two-phase scheme)
                        await self._clear_ticket_processing(ticket_id)

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

            except asyncio.CancelledError:
                # Task was cancelled (preemption or graceful shutdown)
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                span.set_attribute('error', True)
                span.set_attribute('error.type', 'cancelled')
                self.logger.info(
                    'ticket_execution_cancelled',
                    ticket_id=ticket_id,
                    duration_ms=duration_ms
                )
                # Note: Status update and result publish are handled by cancel_active_task
                # Just clean up and re-raise to signal cancellation
                raise

            except asyncio.TimeoutError:
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                span.set_attribute('error', True)
                span.set_attribute('error.type', 'timeout')
                self.logger.error('ticket_execution_timeout', ticket_id=ticket_id)

                # Limpar chave de processing para permitir retry (two-phase scheme)
                await self._clear_ticket_processing(ticket_id)

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

                # Limpar chave de processing para permitir retry (two-phase scheme)
                await self._clear_ticket_processing(ticket_id)

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

    async def cancel_active_task(
        self,
        ticket_id: str,
        reason: str = 'preemption',
        preempted_by: Optional[str] = None,
        grace_period_seconds: int = 30
    ) -> Dict[str, Any]:
        """
        Cancel an active task with optional checkpointing.

        Called by the HTTP endpoint when the Orchestrator requests preemption.

        Args:
            ticket_id: ID of the ticket to cancel
            reason: Reason for cancellation (preemption, timeout, user_request)
            preempted_by: ID of the ticket that is preempting this one
            grace_period_seconds: Time to wait for graceful cancellation

        Returns:
            Dict with cancellation result
        """
        if ticket_id not in self.active_tasks:
            self.logger.warning(
                'cancel_task_not_active',
                ticket_id=ticket_id
            )
            return {
                'success': False,
                'message': f'Task {ticket_id} is not active'
            }

        task = self.active_tasks[ticket_id]
        checkpoint_saved = False
        checkpoint_key = None

        self.logger.info(
            'cancelling_active_task',
            ticket_id=ticket_id,
            reason=reason,
            preempted_by=preempted_by,
            grace_period_seconds=grace_period_seconds
        )

        try:
            # Save checkpoint before cancellation if Redis is available
            if self.redis_client:
                checkpoint_result = await self._save_checkpoint(
                    ticket_id,
                    reason=reason,
                    preempted_by=preempted_by
                )
                checkpoint_saved = checkpoint_result.get('success', False)
                checkpoint_key = checkpoint_result.get('checkpoint_key')

            # Cancel the task
            task.cancel()

            # Wait for graceful cancellation with timeout
            try:
                await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=grace_period_seconds
                )
            except asyncio.CancelledError:
                pass  # Expected
            except asyncio.TimeoutError:
                self.logger.warning(
                    'graceful_cancellation_timeout',
                    ticket_id=ticket_id,
                    grace_period_seconds=grace_period_seconds
                )

            # Update ticket status to PREEMPTED
            status = 'PREEMPTED' if reason == 'preemption' else 'CANCELLED'
            try:
                await self.ticket_client.update_ticket_status(
                    ticket_id,
                    status,
                    error_message=f'Task {reason}: preempted by {preempted_by}' if preempted_by else f'Task {reason}'
                )
            except Exception as status_error:
                self.logger.error(
                    'update_status_failed',
                    ticket_id=ticket_id,
                    error=str(status_error)
                )

            # Publish result
            try:
                await self.result_producer.publish_result(
                    ticket_id,
                    status,
                    {
                        'success': False,
                        'reason': reason,
                        'preempted_by': preempted_by,
                        'checkpoint_key': checkpoint_key
                    },
                    error_message=f'Task {reason}'
                )
            except Exception as pub_error:
                self.logger.error(
                    'publish_result_failed',
                    ticket_id=ticket_id,
                    error=str(pub_error)
                )

            # Clear processing key to allow retry
            await self._clear_ticket_processing(ticket_id)

            # Record metrics
            if self.metrics:
                if hasattr(self.metrics, 'tasks_cancelled_total'):
                    self.metrics.tasks_cancelled_total.labels(reason=reason).inc()
                if hasattr(self.metrics, 'tasks_preempted_total') and reason == 'preemption':
                    self.metrics.tasks_preempted_total.inc()
                if hasattr(self.metrics, 'checkpoint_saves_total') and checkpoint_saved:
                    self.metrics.checkpoint_saves_total.labels(success='true').inc()

            self.logger.info(
                'task_cancelled_successfully',
                ticket_id=ticket_id,
                reason=reason,
                checkpoint_saved=checkpoint_saved,
                checkpoint_key=checkpoint_key
            )

            return {
                'success': True,
                'ticket_id': ticket_id,
                'reason': reason,
                'checkpoint_saved': checkpoint_saved,
                'checkpoint_key': checkpoint_key,
                'message': f'Task {ticket_id} cancelled successfully'
            }

        except Exception as e:
            self.logger.error(
                'cancel_task_failed',
                ticket_id=ticket_id,
                error=str(e)
            )
            return {
                'success': False,
                'ticket_id': ticket_id,
                'message': f'Failed to cancel task: {str(e)}'
            }

    async def _save_checkpoint(
        self,
        ticket_id: str,
        reason: str = 'preemption',
        preempted_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save task checkpoint to Redis for later retry.

        Args:
            ticket_id: ID of the ticket being checkpointed
            reason: Reason for checkpoint
            preempted_by: ID of preempting ticket

        Returns:
            Dict with checkpoint result
        """
        if not self.redis_client:
            return {'success': False, 'message': 'Redis not available'}

        checkpoint_key = f"checkpoint:{ticket_id}"

        try:
            import json as json_lib
            checkpoint_data = {
                'ticket_id': ticket_id,
                'reason': reason,
                'preempted_by': preempted_by,
                'timestamp': datetime.now().isoformat(),
                'worker_id': getattr(self.config, 'agent_id', 'unknown')
            }

            # Store checkpoint with 24h TTL
            await self.redis_client.set(
                checkpoint_key,
                json_lib.dumps(checkpoint_data),
                ex=86400  # 24 hours
            )

            self.logger.info(
                'checkpoint_saved',
                ticket_id=ticket_id,
                checkpoint_key=checkpoint_key
            )

            return {
                'success': True,
                'checkpoint_key': checkpoint_key
            }

        except Exception as e:
            self.logger.error(
                'checkpoint_save_failed',
                ticket_id=ticket_id,
                error=str(e)
            )
            if self.metrics and hasattr(self.metrics, 'checkpoint_saves_total'):
                self.metrics.checkpoint_saves_total.labels(success='false').inc()
            return {
                'success': False,
                'message': str(e)
            }
