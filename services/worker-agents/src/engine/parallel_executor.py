"""
Parallel Executor para execução avançada de múltiplos tickets em paralelo.

Este módulo fornece funcionalidades para:
- Execução paralela de tickets independentes
- Batch processing de tickets do mesmo tipo
- Coordenação de dependências complexas
- Priority-based execution
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from neural_hive_observability import get_tracer

logger = structlog.get_logger()


class TaskPriority(Enum):
    """Prioridades de execução de tarefas."""

    CRITICAL = 1  # SLA crítico, compensation
    HIGH = 2  # User-facing, timeout curto
    MEDIUM = 3  # Batch jobs, processamento normal
    LOW = 4  # Background, cleanup


@dataclass
class ParallelExecutionConfig:
    """Configuração para execução paralela."""

    max_parallel_tasks: int = 10
    max_parallel_by_type: dict[str, int] = field(default_factory=dict)
    enable_batching: bool = True
    batch_size: int = 5
    batch_timeout_seconds: float = 1.0
    enable_priority_queue: bool = True


@dataclass
class TicketWrapper:
    """Wrapper para ticket com metadata de execução."""

    ticket: dict[str, Any]
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: set[str] = field(default_factory=set)
    submitted_at: float = field(default_factory=time.monotonic)
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def ticket_id(self) -> str:
        return self.ticket.get("ticket_id", "")

    @property
    def task_type(self) -> str:
        return self.ticket.get("task_type", "")


class ParallelExecutor:
    """
    Executor paralelo avançado para Worker Agents.

    Implementa:
    - Execução paralela de tickets independentes
    - Fila de prioridade
    - Batch processing por task_type
    - Coordenação de dependências
    - Timeout e cancelamento granular
    """

    def __init__(self, config: ParallelExecutionConfig, execution_engine, metrics=None):
        self.config = config
        self.execution_engine = execution_engine
        self.metrics = metrics
        self.logger = logger.bind(service="parallel_executor")

        # Filas por prioridade
        self.queues: dict[TaskPriority, asyncio.Queue] = {
            priority: asyncio.Queue() for priority in TaskPriority
        }

        # Workers por task_type
        self.active_by_type: dict[str, int] = {}
        self.active_tasks: dict[str, asyncio.Task] = {}

        # Semaphores para limitar paralelismo
        self.global_semaphore = asyncio.Semaphore(config.max_parallel_tasks)
        self.type_semaphores: dict[str, asyncio.Semaphore] = {}

        # Processor tasks
        self._processor_tasks: list[asyncio.Task] = []
        self._running = False

        # Batch accumulators
        self._batch_accumulators: dict[str, list[TicketWrapper]] = {}

        self.logger.info(
            "parallel_executor_initialized",
            max_parallel=config.max_parallel_tasks,
            enable_batching=config.enable_batching,
            enable_priority=config.enable_priority_queue,
        )

    def get_type_semaphore(self, task_type: str) -> asyncio.Semaphore:
        """Obtém ou cria semaphore para um task_type."""
        if task_type not in self.type_semaphores:
            max_parallel = self.config.max_parallel_by_type.get(
                task_type, self.config.max_parallel_tasks
            )
            self.type_semaphores[task_type] = asyncio.Semaphore(max_parallel)
        return self.type_semaphores[task_type]

    async def submit_ticket(
        self,
        ticket: dict[str, Any],
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: set[str] | None = None,
    ) -> str:
        """
        Submete um ticket para execução paralela.

        Args:
            ticket: Execution ticket
            priority: Prioridade de execução
            dependencies: IDs de tickets dependentes

        Returns:
            correlation_id para tracking
        """
        wrapper = TicketWrapper(
            ticket=ticket, priority=priority, dependencies=dependencies or set()
        )

        if self.config.enable_priority_queue:
            await self.queues[priority].put(wrapper)
        else:
            await self.queues[TaskPriority.MEDIUM].put(wrapper)

        self.logger.info(
            "ticket_submitted",
            ticket_id=wrapper.ticket_id,
            task_type=wrapper.task_type,
            priority=priority.name,
            correlation_id=wrapper.correlation_id,
        )

        if self.metrics and hasattr(self.metrics, "parallel_tickets_submitted_total"):
            self.metrics.parallel_tickets_submitted_total.labels(
                task_type=wrapper.task_type, priority=priority.name
            ).inc()

        return wrapper.correlation_id

    async def submit_batch(
        self, tickets: list[dict[str, Any]], priority: TaskPriority = TaskPriority.MEDIUM
    ) -> list[str]:
        """
        Submete múltiplos tickets para execução em lote.

        Args:
            tickets: Lista de execution tickets
            priority: Prioridade comum para todos

        Returns:
            Lista de correlation_ids
        """
        correlation_ids = []

        if self.config.enable_batching:
            # Agrupar por task_type para batch processing
            by_type: dict[str, list[dict[str, Any]]] = {}
            for ticket in tickets:
                task_type = ticket.get("task_type", "UNKNOWN")
                if task_type not in by_type:
                    by_type[task_type] = []
                by_type[task_type].append(ticket)

            # Processar cada tipo em batch
            for task_type, type_tickets in by_type.items():
                for ticket in type_tickets:
                    wrapper = TicketWrapper(ticket=ticket, priority=priority)
                    await self.queues[priority].put(wrapper)
                    correlation_ids.append(wrapper.correlation_id)
        else:
            # Submeter individualmente
            for ticket in tickets:
                cid = await self.submit_ticket(ticket, priority)
                correlation_ids.append(cid)

        self.logger.info(
            "batch_submitted",
            total_tickets=len(tickets),
            correlation_ids_count=len(correlation_ids),
        )

        return correlation_ids

    async def start(self, num_workers: int = 4):
        """Inicia os processor workers."""
        if self._running:
            return

        self._running = True

        for i in range(num_workers):
            task = asyncio.create_task(self._processor_worker(i))
            self._processor_tasks.append(task)

        self.logger.info("parallel_executor_started", num_workers=num_workers)

    async def stop(self, timeout_seconds: float = 30.0):
        """Para o executor paralelo."""
        if not self._running:
            return

        self._running = False

        # Cancelar processor tasks
        for task in self._processor_tasks:
            task.cancel()

        # Aguardar finalização com timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._processor_tasks, return_exceptions=True),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            self.logger.warning("processor_shutdown_timeout")

        self._processor_tasks.clear()
        self.logger.info("parallel_executor_stopped")

    async def _processor_worker(self, worker_id: int):
        """
        Worker que processa tickets das filas de prioridade.

        Processa filas em ordem de prioridade, sempre verificando
        se há tickets de prioridade mais alta antes de processar
        tickets de prioridade mais baixa.
        """
        self.logger.info("processor_worker_started", worker_id=worker_id)

        while self._running:
            # Tentar obter ticket da fila de maior prioridade primeiro
            wrapper = None
            for priority in TaskPriority:
                if not self._running:
                    break

                try:
                    queue = self.queues[priority]
                    wrapper = await asyncio.wait_for(queue.get(), timeout=0.1)
                    break  # Got a ticket, exit priority loop
                except TimeoutError:
                    continue

            if wrapper is None:
                continue

            # Processar ticket
            await self._process_ticket(wrapper, worker_id)

        self.logger.info("processor_worker_stopped", worker_id=worker_id)

    async def _process_ticket(self, wrapper: TicketWrapper, worker_id: int):
        """Processa um ticket individual."""
        ticket_id = wrapper.ticket_id
        task_type = wrapper.task_type

        start_time = time.monotonic()

        # Adquirir semaphores
        async with self.global_semaphore:
            type_semaphore = self.get_type_semaphore(task_type)
            async with type_semaphore:
                # Atualizar contadores
                if task_type not in self.active_by_type:
                    self.active_by_type[task_type] = 0
                self.active_by_type[task_type] += 1
                self.active_tasks[ticket_id] = asyncio.current_task()

                try:
                    # Tracing
                    tracer = get_tracer()
                    with tracer.start_as_current_span("parallel_ticket_execution") as span:
                        if span:
                            span.set_attribute("neural.hive.ticket_id", ticket_id)
                            span.set_attribute("neural.hive.task_type", task_type)
                            span.set_attribute("neural.hive.worker_id", worker_id)
                            span.set_attribute("neural.hive.priority", wrapper.priority.name)

                        # Executar via engine
                        await self.execution_engine.process_ticket(wrapper.ticket)

                    duration = time.monotonic() - start_time

                    self.logger.info(
                        "parallel_ticket_completed",
                        ticket_id=ticket_id,
                        task_type=task_type,
                        worker_id=worker_id,
                        duration_seconds=duration,
                    )

                    if self.metrics:
                        if hasattr(self.metrics, "parallel_ticket_duration_seconds"):
                            self.metrics.parallel_ticket_duration_seconds.labels(
                                task_type=task_type
                            ).observe(duration)

                except Exception as e:
                    duration = time.monotonic() - start_time
                    self.logger.exception(
                        "parallel_ticket_failed",
                        ticket_id=ticket_id,
                        task_type=task_type,
                        error=str(e),
                        duration_seconds=duration,
                    )

                    if self.metrics:
                        if hasattr(self.metrics, "parallel_tickets_failed_total"):
                            self.metrics.parallel_tickets_failed_total.labels(
                                task_type=task_type, error_type=type(e).__name__
                            ).inc()

                finally:
                    # Limpar contadores
                    if task_type in self.active_by_type:
                        self.active_by_type[task_type] -= 1
                    if ticket_id in self.active_tasks:
                        del self.active_tasks[ticket_id]

    async def execute_parallel_independent(
        self, tickets: list[dict[str, Any]], timeout_seconds: float | None = None
    ) -> list[dict[str, Any]]:
        """
        Executa múltiplos tickets independentes em paralelo.

        Args:
            tickets: Lista de tickets sem dependências entre si
            timeout_seconds: Timeout global para todas as execuções

        Returns:
            Lista de resultados na mesma ordem dos tickets
        """
        if not tickets:
            return []

        self.logger.info("parallel_independent_execution_start", num_tickets=len(tickets))

        start_time = time.monotonic()

        async def execute_single(ticket: dict[str, Any]) -> dict[str, Any]:
            ticket_id = ticket.get("ticket_id", "unknown")
            try:
                await self.execution_engine.process_ticket(ticket)
                return {"ticket_id": ticket_id, "success": True}
            except Exception as e:
                return {"ticket_id": ticket_id, "success": False, "error": str(e)}

        # Executar em paralelo
        tasks = [execute_single(ticket) for ticket in tickets]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=timeout_seconds
            )
        except TimeoutError:
            results = []
            for ticket in tickets:
                results.append(
                    {
                        "ticket_id": ticket.get("ticket_id", "unknown"),
                        "success": False,
                        "error": "Timeout",
                    }
                )

        duration = time.monotonic() - start_time

        successful = sum(1 for r in results if r.get("success"))
        self.logger.info(
            "parallel_independent_execution_completed",
            total=len(tickets),
            successful=successful,
            failed=len(tickets) - successful,
            duration_seconds=duration,
        )

        if self.metrics and hasattr(self.metrics, "parallel_batch_duration_seconds"):
            self.metrics.parallel_batch_duration_seconds.observe(duration)

        return results

    async def execute_with_dependencies(
        self, tickets: list[dict[str, Any]], dependency_graph: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        """
        Executa tickets com dependências em paralelo quando possível.

        Args:
            tickets: Lista de tickets
            dependency_graph: Mapa de ticket_id -> lista de dependências

        Returns:
            Lista de resultados
        """
        if not tickets:
            return []

        self.logger.info("parallel_execution_with_deps_start", num_tickets=len(tickets))

        # Criar mapa de tickets
        tickets_map = {t.get("ticket_id"): t for t in tickets}

        # Estado de execução
        completed: set[str] = set()
        failed: set[str] = set()
        results: list[dict[str, Any]] = []

        # Executar enquanto houver tickets pendentes
        while len(completed) + len(failed) < len(tickets):
            # Encontrar tickets prontos (dependências satisfeitas)
            ready_tickets = []

            for ticket_id, ticket in tickets_map.items():
                if ticket_id in completed or ticket_id in failed:
                    continue

                dependencies = dependency_graph.get(ticket_id, [])
                if all(dep in completed for dep in dependencies):
                    ready_tickets.append(ticket)

            if not ready_tickets:
                # Verificar se há tickets com dependências falhas
                remaining = [
                    tid for tid in tickets_map if tid not in completed and tid not in failed
                ]
                # Marcar tickets com dependências falhas como falhados
                for ticket_id in remaining:
                    dependencies = dependency_graph.get(ticket_id, [])
                    if any(dep in failed for dep in dependencies):
                        failed.add(ticket_id)
                        results.append(
                            {
                                "ticket_id": ticket_id,
                                "success": False,
                                "error": f"Dependency failed: {[d for d in dependencies if d in failed]}",
                            }
                        )
                # Se ainda não há tickets prontos, é um ciclo
                ready_tickets = [
                    tickets_map[tid]
                    for tid in tickets_map
                    if tid not in completed and tid not in failed
                ]
                if not ready_tickets:
                    break

            # Executar tickets prontos em paralelo
            batch_results = await self.execute_parallel_independent(
                ready_tickets, timeout_seconds=300.0
            )

            # Atualizar estado
            for result in batch_results:
                ticket_id = result.get("ticket_id")
                if result.get("success"):
                    completed.add(ticket_id)
                else:
                    failed.add(ticket_id)
                results.append(result)

        successful = len(completed)
        self.logger.info(
            "parallel_execution_with_deps_completed",
            total=len(tickets),
            successful=successful,
            failed=len(failed),
        )

        return results

    def get_status(self) -> dict[str, Any]:
        """Retorna status atual do executor paralelo."""
        return {
            "running": self._running,
            "active_tasks": len(self.active_tasks),
            "active_by_type": dict(self.active_by_type),
            "queue_sizes": {
                priority.name: queue.qsize() for priority, queue in self.queues.items()
            },
            "processor_tasks": len(self._processor_tasks),
            "max_parallel": self.config.max_parallel_tasks,
            "enable_batching": self.config.enable_batching,
            "enable_priority": self.config.enable_priority_queue,
        }


async def execute_parallel_tickets(
    tickets: list[dict[str, Any]],
    execution_engine,
    max_parallel: int = 10,
    timeout_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """
    Função de conveniência para execução paralela de tickets.

    Args:
        tickets: Lista de tickets para executar
        execution_engine: Instância de ExecutionEngine
        max_parallel: Número máximo de execuções paralelas
        timeout_seconds: Timeout global opcional

    Returns:
        Lista de resultados de execução
    """
    config = ParallelExecutionConfig(max_parallel_tasks=max_parallel)
    executor = ParallelExecutor(config, execution_engine)

    return await executor.execute_parallel_independent(tickets, timeout_seconds=timeout_seconds)
