"""
Load Balancer para coordenação de Worker Agents

Implementa distribuição de tarefas usando múltiplas estratégias:
- Round Robin
- Least Loaded
- Weighted (baseado em capacidade)
- Consistent Hashing
"""
import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

UTC = timezone.utc  # type: ignore
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

import structlog

if TYPE_CHECKING:
    from src.clients import RedisClient, ServiceRegistryClient
    from src.config import Settings


logger = structlog.get_logger()


class BalancingStrategy(Enum):
    """Estratégias de balanceamento"""

    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    WEIGHTED = "weighted"
    CONSISTENT_HASH = "consistent_hash"


@dataclass
class WorkerMetrics:
    """Métricas de um worker"""

    worker_id: str
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_processing_time_ms: float = 0.0
    last_heartbeat: datetime | None = None
    capacity: float = 1.0  # Capacidade relativa (1.0 = baseline)
    is_healthy: bool = True


@dataclass
class TaskAssignment:
    """Resultado da atribuição de tarefa"""

    worker_id: str
    strategy: BalancingStrategy
    assigned_at: datetime = field(default_factory=datetime.utcnow)


class LoadBalancer:
    """
    Balanceador de carga para distribuir tarefas entre workers.

    Usa Redis para armazenar estado distribuído e cache local para performance.
    """

    # Chaves Redis
    WORKERS_KEY = "queen_agent:load_balancer:workers"
    METRICS_KEY = "queen_agent:load_balancer:metrics"
    ASSIGNMENTS_KEY = "queen_agent:load_balancer:assignments"

    def __init__(
        self,
        redis_client: "RedisClient",
        service_registry_client: Optional["ServiceRegistryClient"] = None,
        settings: Optional["Settings"] = None,
    ):
        self.redis_client = redis_client
        self.service_registry_client = service_registry_client
        self.settings = settings

        # Configurações com defaults
        self.strategy = BalancingStrategy(
            getattr(settings, "LOAD_BALANCER_STRATEGY", "round_robin")
        )
        self.heartbeat_timeout_seconds = getattr(settings, "WORKER_HEARTBEAT_TIMEOUT_SECONDS", 30)
        self.metrics_ttl_seconds = getattr(settings, "METRICS_TTL_SECONDS", 300)

        # Estado local
        self._round_robin_index = 0
        self._local_cache: dict[str, WorkerMetrics] = {}
        self._cache_lock = asyncio.Lock()
        self._round_robin_lock = asyncio.Lock()

        # Background tasks
        self.is_running = False
        self._sync_task: asyncio.Task | None = None

        logger.info(
            "load_balancer_initialized",
            strategy=self.strategy.value,
            heartbeat_timeout=self.heartbeat_timeout_seconds,
        )

    async def start(self) -> None:
        """Iniciar balanceador e sync em background"""
        if self.is_running:
            logger.warning("load_balancer_already_running")
            return

        self.is_running = True
        self._sync_task = asyncio.create_task(self._sync_loop())

        logger.info("load_balancer_started")

    async def stop(self) -> None:
        """Parar balanceador"""
        self.is_running = False
        if self._sync_task:
            self._sync_task.cancel()
        logger.info("load_balancer_stopped")

    async def register_worker(
        self,
        worker_id: str,
        capacity: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Registrar um worker no balanceador.

        Args:
            worker_id: ID único do worker
            capacity: Capacidade relativa do worker
            metadata: Metadados adicionais

        Returns:
            True se registrado com sucesso
        """
        try:
            async with self._cache_lock:
                # Criar métricas iniciais
                metrics = WorkerMetrics(
                    worker_id=worker_id,
                    capacity=capacity,
                    last_heartbeat=datetime.now(UTC),
                    is_healthy=True,
                )
                self._local_cache[worker_id] = metrics

            # Persistir no Redis
            worker_data = {
                "worker_id": worker_id,
                "capacity": str(capacity),
                "registered_at": datetime.now(UTC).isoformat(),
                "metadata": str(metadata or {}),
            }
            await self.redis_client.client.hset(self.WORKERS_KEY, worker_id, str(worker_data))
            await self.redis_client.client.expire(self.WORKERS_KEY, self.metrics_ttl_seconds)

            logger.info(
                "worker_registered",
                worker_id=worker_id,
                capacity=capacity,
            )
            return True

        except Exception as e:
            logger.exception("register_worker_failed", error=str(e), worker_id=worker_id)
            return False

    async def unregister_worker(self, worker_id: str) -> bool:
        """
        Remover worker do balanceador.

        Args:
            worker_id: ID do worker a remover

        Returns:
            True se removido com sucesso
        """
        try:
            async with self._cache_lock:
                if worker_id in self._local_cache:
                    del self._local_cache[worker_id]

            await self.redis_client.client.hdel(self.WORKERS_KEY, worker_id)
            await self.redis_client.client.hdel(self.METRICS_KEY, worker_id)

            logger.info("worker_unregistered", worker_id=worker_id)
            return True

        except Exception as e:
            logger.exception("unregister_worker_failed", error=str(e), worker_id=worker_id)
            return False

    async def update_worker_metrics(
        self,
        worker_id: str,
        active_tasks: int | None = None,
        completed_tasks: int | None = None,
        failed_tasks: int | None = None,
        avg_processing_time_ms: float | None = None,
    ) -> bool:
        """
        Atualizar métricas de um worker.

        Args:
            worker_id: ID do worker
            active_tasks: Número de tarefas ativas
            completed_tasks: Número de tarefas completadas
            failed_tasks: Número de tarefas falhadas
            avg_processing_time_ms: Tempo médio de processamento

        Returns:
            True se atualizado com sucesso
        """
        try:
            async with self._cache_lock:
                if worker_id not in self._local_cache:
                    # Worker não registrado, criar entry
                    await self.register_worker(worker_id)

                metrics = self._local_cache[worker_id]

                if active_tasks is not None:
                    metrics.active_tasks = active_tasks
                if completed_tasks is not None:
                    metrics.completed_tasks = completed_tasks
                if failed_tasks is not None:
                    metrics.failed_tasks = failed_tasks
                if avg_processing_time_ms is not None:
                    metrics.avg_processing_time_ms = avg_processing_time_ms

                metrics.last_heartbeat = datetime.now(UTC)
                metrics.is_healthy = True

            # Persistir no Redis
            metrics_data = {
                "worker_id": worker_id,
                "active_tasks": str(metrics.active_tasks),
                "completed_tasks": str(metrics.completed_tasks),
                "failed_tasks": str(metrics.failed_tasks),
                "avg_processing_time_ms": str(metrics.avg_processing_time_ms),
                "last_heartbeat": metrics.last_heartbeat.isoformat(),
                "capacity": str(metrics.capacity),
            }
            await self.redis_client.client.hset(self.METRICS_KEY, worker_id, str(metrics_data))
            await self.redis_client.client.expire(self.METRICS_KEY, self.metrics_ttl_seconds)

            logger.debug("worker_metrics_updated", worker_id=worker_id)
            return True

        except Exception as e:
            logger.exception("update_worker_metrics_failed", error=str(e), worker_id=worker_id)
            return False

    async def assign_task(
        self,
        task_id: str,
        task_data: dict[str, Any] | None = None,
        strategy: BalancingStrategy | None = None,
    ) -> TaskAssignment | None:
        """
        Atribuir tarefa a um worker usando estratégia configurada.

        Args:
            task_id: ID da tarefa
            task_data: Dados da tarefa (para consistent hashing)
            strategy: Estratégia a usar (override da padrão)

        Returns:
            TaskAssignment se atribuído, None se nenhum worker disponível
        """
        try:
            strategy = strategy or self.strategy
            workers = await self._get_healthy_workers()

            if not workers:
                logger.warning("no_healthy_workers_available", task_id=task_id)
                return None

            # Selecionar worker baseado na estratégia
            if strategy == BalancingStrategy.ROUND_ROBIN:
                worker_id = await self._select_round_robin(workers)
            elif strategy == BalancingStrategy.LEAST_LOADED:
                worker_id = await self._select_least_loaded(workers)
            elif strategy == BalancingStrategy.WEIGHTED:
                worker_id = await self._select_weighted(workers)
            elif strategy == BalancingStrategy.CONSISTENT_HASH:
                worker_id = await self._select_consistent_hash(workers, task_id, task_data)
            else:
                worker_id = workers[0]

            if not worker_id:
                return None

            # Incrementar tarefas ativas
            await self.update_worker_metrics(
                worker_id, active_tasks=self._local_cache[worker_id].active_tasks + 1
            )

            # Registrar atribuição
            assignment = TaskAssignment(
                worker_id=worker_id,
                strategy=strategy,
            )

            await self._record_assignment(task_id, assignment)

            logger.info(
                "task_assigned",
                task_id=task_id,
                worker_id=worker_id,
                strategy=strategy.value,
            )

            return assignment

        except Exception as e:
            logger.exception("assign_task_failed", error=str(e), task_id=task_id)
            return None

    async def complete_task(
        self,
        worker_id: str,
        task_id: str,
        success: bool = True,
        processing_time_ms: float | None = None,
    ) -> bool:
        """
        Marcar tarefa como completa e atualizar métricas.

        Args:
            worker_id: ID do worker
            task_id: ID da tarefa
            success: Se a tarefa foi bem-sucedida
            processing_time_ms: Tempo de processamento

        Returns:
            True se atualizado com sucesso
        """
        try:
            async with self._cache_lock:
                if worker_id not in self._local_cache:
                    logger.warning("worker_not_found_in_cache", worker_id=worker_id)
                    return False

                metrics = self._local_cache[worker_id]

                # Decrementar tarefas ativas
                metrics.active_tasks = max(0, metrics.active_tasks - 1)

                # Incrementar contador
                if success:
                    metrics.completed_tasks += 1
                else:
                    metrics.failed_tasks += 1

                # Atualizar tempo médio
                if processing_time_ms is not None:
                    current_avg = metrics.avg_processing_time_ms
                    completed = metrics.completed_tasks + metrics.failed_tasks
                    metrics.avg_processing_time_ms = (
                        current_avg * (completed - 1) + processing_time_ms
                    ) / completed

            logger.debug(
                "task_completed",
                worker_id=worker_id,
                task_id=task_id,
                success=success,
            )
            return True

        except Exception as e:
            logger.exception("complete_task_failed", error=str(e), worker_id=worker_id)
            return False

    async def _get_healthy_workers(self) -> list[str]:
        """Obter lista de workers saudáveis"""
        async with self._cache_lock:
            now = datetime.now(UTC)
            healthy_workers = []

            for worker_id, metrics in self._local_cache.items():
                # Verificar timeout de heartbeat
                if metrics.last_heartbeat:
                    elapsed = (now - metrics.last_heartbeat).total_seconds()
                    if elapsed > self.heartbeat_timeout_seconds:
                        metrics.is_healthy = False
                        logger.warning(
                            "worker_heartbeat_timeout",
                            worker_id=worker_id,
                            elapsed_seconds=elapsed,
                        )
                        continue

                if metrics.is_healthy:
                    healthy_workers.append(worker_id)

            return healthy_workers

    async def _select_round_robin(self, workers: list[str]) -> str | None:
        """Selecionar worker usando round robin"""
        if not workers:
            return None

        async with self._round_robin_lock:
            worker_id = workers[self._round_robin_index % len(workers)]
            self._round_robin_index += 1
            return worker_id

    async def _select_least_loaded(self, workers: list[str]) -> str | None:
        """Selecionar worker com menos carga"""
        if not workers:
            return None

        async with self._cache_lock:
            # Ordenar por tarefas ativas (menos primeiro)
            sorted_workers = sorted(
                workers,
                key=lambda w: (self._local_cache.get(w, WorkerMetrics(worker_id=w)).active_tasks),
            )
            return sorted_workers[0] if sorted_workers else None

    async def _select_weighted(self, workers: list[str]) -> str | None:
        """Selecionar worker ponderado por capacidade"""
        if not workers:
            return None

        async with self._cache_lock:
            # Calcular peso ajustado por carga
            weights = []
            for worker_id in workers:
                metrics = self._local_cache.get(worker_id, WorkerMetrics(worker_id=worker_id))
                # Peso = capacidade / (tarefas_ativas + 1)
                weight = metrics.capacity / (metrics.active_tasks + 1)
                weights.append(weight)

            # Selecionar baseado em peso
            total_weight = sum(weights)
            if total_weight == 0:
                return workers[0]

            import random

            rand = random.uniform(0, total_weight)
            cumulative = 0

            for worker_id, weight in zip(workers, weights, strict=False):
                cumulative += weight
                if rand <= cumulative:
                    return worker_id

            return workers[0]

    async def _select_consistent_hash(
        self,
        workers: list[str],
        task_id: str,
        task_data: dict[str, Any] | None = None,
    ) -> str | None:
        """Selecionar worker usando consistent hashing"""
        if not workers:
            return None

        # Usar task_id como chave de hash
        key = f"{task_id}:{task_data or {}!s}"

        # Calcular hash
        hash_value = int(hashlib.sha256(key.encode()).hexdigest(), 16)

        # Selecionar worker
        worker_index = hash_value % len(workers)
        return workers[worker_index]

    async def _record_assignment(self, task_id: str, assignment: TaskAssignment) -> None:
        """Registrar atribuição no Redis"""
        try:
            assignment_data = {
                "task_id": task_id,
                "worker_id": assignment.worker_id,
                "strategy": assignment.strategy.value,
                "assigned_at": assignment.assigned_at.isoformat(),
            }
            await self.redis_client.client.hset(self.ASSIGNMENTS_KEY, task_id, str(assignment_data))
            await self.redis_client.client.expire(self.ASSIGNMENTS_KEY, self.metrics_ttl_seconds)
        except Exception as e:
            logger.exception("record_assignment_failed", error=str(e), task_id=task_id)

    async def _sync_loop(self) -> None:
        """Loop de sincronização com Redis"""
        while self.is_running:
            try:
                await asyncio.sleep(5)
                # Sync poderia ser expandido para buscar dados do Redis
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("sync_loop_error", error=str(e))

    async def get_workers_status(self) -> dict[str, dict[str, Any]]:
        """
        Obter status de todos os workers.

        Returns:
            Dicionário com status de cada worker
        """
        async with self._cache_lock:
            status = {}
            for worker_id, metrics in self._local_cache.items():
                status[worker_id] = {
                    "active_tasks": metrics.active_tasks,
                    "completed_tasks": metrics.completed_tasks,
                    "failed_tasks": metrics.failed_tasks,
                    "avg_processing_time_ms": metrics.avg_processing_time_ms,
                    "capacity": metrics.capacity,
                    "is_healthy": metrics.is_healthy,
                    "last_heartbeat": metrics.last_heartbeat.isoformat()
                    if metrics.last_heartbeat
                    else None,
                }
            return status

    async def get_statistics(self) -> dict[str, Any]:
        """
        Obter estatísticas do balanceador.

        Returns:
            Dicionário com estatísticas
        """
        async with self._cache_lock:
            total_workers = len(self._local_cache)
            healthy_workers = sum(1 for m in self._local_cache.values() if m.is_healthy)
            total_active = sum(m.active_tasks for m in self._local_cache.values())
            total_completed = sum(m.completed_tasks for m in self._local_cache.values())
            total_failed = sum(m.failed_tasks for m in self._local_cache.values())

            return {
                "total_workers": total_workers,
                "healthy_workers": healthy_workers,
                "unhealthy_workers": total_workers - healthy_workers,
                "total_active_tasks": total_active,
                "total_completed_tasks": total_completed,
                "total_failed_tasks": total_failed,
                "strategy": self.strategy.value,
            }
