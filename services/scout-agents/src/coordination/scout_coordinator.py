"""
ScoutCoordinator - Coordena múltiplos scouts para exploração paralela.

Responsável por:
- Distribuir tarefas entre scouts
- Gerenciar estado compartilhado
- Evitar trabalho duplicado
- Sincronizar progresso
"""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
import structlog

logger = structlog.get_logger()


class Task:
    """Representa uma tarefa de exploração."""

    def __init__(
        self,
        task_id: str,
        target: str,  # filepath ou directory
        task_type: str,  # 'scan_file', 'analyze_directory', 'detect_patterns'
        priority: float = 0.5,
        metadata: Optional[Dict] = None
    ):
        self.task_id = task_id
        self.target = target
        self.task_type = task_type
        self.priority = priority  # 0.0 a 1.0
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.assigned_to: Optional[str] = None
        self.status = 'pending'  # pending, assigned, completed, failed
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.result: Optional[Dict] = None

    def to_dict(self) -> Dict:
        """Converte para dicionário."""
        return {
            'task_id': self.task_id,
            'target': self.target,
            'task_type': self.task_type,
            'priority': self.priority,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'assigned_to': self.assigned_to,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result': self.result
        }


class ScoutCoordinator:
    """Coordena múltiplos scouts para exploração paralela."""

    def __init__(
        self,
        coordinator_id: str,
        max_concurrent_tasks: int = 10,
        task_timeout: int = 300
    ):
        """
        Inicializa ScoutCoordinator.

        Args:
            coordinator_id: Identificador do coordenador
            max_concurrent_tasks: Máximo de tarefas simultâneas
            task_timeout: Timeout para tarefas (segundos)
        """
        self.coordinator_id = coordinator_id
        self.max_concurrent_tasks = max_concurrent_tasks
        self.task_timeout = task_timeout

        # Estado
        self._tasks: Dict[str, Task] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._active_tasks: Set[str] = set()
        self._scouts: Dict[str, Dict] = {}  # scout_id -> {status, last_heartbeat}

        # Filas por prioridade
        self._high_priority_queue: asyncio.Queue = asyncio.Queue()
        self._normal_priority_queue: asyncio.Queue = asyncio.Queue()

        # Estatísticas
        self.stats = {
            'tasks_created': 0,
            'tasks_assigned': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'tasks_timeout': 0
        }

    async def register_scout(self, scout_id: str, capabilities: List[str]) -> bool:
        """
        Registra um scout no coordendor.

        Args:
            scout_id: Identificador do scout
            capabilities: Lista de capacidades do scout

        Returns:
            True se registrado com sucesso
        """
        self._scouts[scout_id] = {
            'status': 'idle',
            'capabilities': capabilities,
            'last_heartbeat': datetime.now(),
            'tasks_completed': 0
        }

        logger.info(
            "scout_registered",
            scout_id=scout_id,
            capabilities=capabilities
        )

        return True

    async def unregister_scout(self, scout_id: str):
        """
        Remove um scout do coordenador.

        Args:
            scout_id: Identificador do scout
        """
        if scout_id in self._scouts:
            # Reatribuir tarefas ativas
            for task_id, task in self._tasks.items():
                if task.assigned_to == scout_id and task.status == 'assigned':
                    task.assigned_to = None
                    task.status = 'pending'
                    await self._enqueue_task(task)

            del self._scouts[scout_id]

            logger.info("scout_unregistered", scout_id=scout_id)

    async def create_task(
        self,
        target: str,
        task_type: str,
        priority: float = 0.5,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Cria uma nova tarefa de exploração.

        Args:
            target: Alvo da tarefa
            task_type: Tipo de tarefa
            priority: Prioridade (0-1)
            metadata: Metadados adicionais

        Returns:
            ID da tarefa criada
        """
        task_id = f"task_{datetime.now().timestamp()}_{len(self._tasks)}"

        task = Task(
            task_id=task_id,
            target=target,
            task_type=task_type,
            priority=priority,
            metadata=metadata
        )

        self._tasks[task_id] = task
        self.stats['tasks_created'] += 1

        await self._enqueue_task(task)

        logger.info(
            "task_created",
            task_id=task_id,
            target=target,
            task_type=task_type,
            priority=priority
        )

        return task_id

    async def _enqueue_task(self, task: Task):
        """Adiciona tarefa à fila apropriada."""
        if task.priority > 0.7:
            await self._high_priority_queue.put(task)
        else:
            await self._normal_priority_queue.put(task)

    async def get_next_task(self, scout_id: str, capabilities: List[str]) -> Optional[Dict]:
        """
        Retorna próxima tarefa para um scout.

        Args:
            scout_id: Identificador do scout
            capabilities: Capacidades do scout

        Returns:
            Dict da tarefa ou None
        """
        # Atualizar heartbeat
        if scout_id in self._scouts:
            self._scouts[scout_id]['last_heartbeat'] = datetime.now()

        # Verificar limite de tarefas simultâneas
        if len(self._active_tasks) >= self.max_concurrent_tasks:
            return None

        # Tentar obter tarefa de alta prioridade primeiro
        task = None
        try:
            task = await asyncio.wait_for(
                self._high_priority_queue.get(),
                timeout=0.1
            )
        except asyncio.TimeoutError:
            try:
                task = await asyncio.wait_for(
                    self._normal_priority_queue.get(),
                    timeout=0.1
                )
            except asyncio.TimeoutError:
                return None

        if task and task.task_id not in self._active_tasks:
            # Verificar se scout tem capacidade necessária
            required_capability = task.metadata.get('required_capability')
            if required_capability and required_capability not in capabilities:
                # Re-enfileir tarefa
                await self._enqueue_task(task)
                return None

            # Atribuir tarefa
            task.assigned_to = scout_id
            task.status = 'assigned'
            task.started_at = datetime.now()
            self._active_tasks.add(task.task_id)
            self.stats['tasks_assigned'] += 1

            logger.info(
                "task_assigned",
                task_id=task.task_id,
                scout_id=scout_id
            )

            return task.to_dict()

        return None

    async def complete_task(
        self,
        task_id: str,
        result: Dict,
        success: bool = True
    ):
        """
        Marca tarefa como completada.

        Args:
            task_id: ID da tarefa
            result: Resultado da tarefa
            success: Se foi completada com sucesso
        """
        if task_id not in self._tasks:
            logger.warning("task_not_found", task_id=task_id)
            return

        task = self._tasks[task_id]
        task.status = 'completed' if success else 'failed'
        task.completed_at = datetime.now()
        task.result = result

        # Remover de tarefas ativas
        self._active_tasks.discard(task_id)

        # Atualizar estatísticas do scout
        if task.assigned_to and task.assigned_to in self._scouts:
            if success:
                self._scouts[task.assigned_to]['tasks_completed'] += 1
            self._scouts[task.assigned_to]['status'] = 'idle'

        if success:
            self.stats['tasks_completed'] += 1
        else:
            self.stats['tasks_failed'] += 1

        logger.info(
            "task_completed",
            task_id=task_id,
            success=success
        )

    async def timeout_stale_tasks(self):
        """Marca tarefas expiradas como failed."""
        now = datetime.now()
        timeout = timedelta(seconds=self.task_timeout)

        stale_tasks = [
            task_id for task_id, task in self._tasks.items()
            if task.status == 'assigned'
            and task.started_at
            and now - task.started_at > timeout
        ]

        for task_id in stale_tasks:
            await self.complete_task(
                task_id,
                {'error': 'timeout'},
                success=False
            )
            self.stats['tasks_timeout'] += 1

            logger.warning("task_timeout", task_id=task_id)

    async def get_task_status(self, task_id: str) -> Optional[Dict]:
        """
        Retorna status de uma tarefa.

        Args:
            task_id: ID da tarefa

        Returns:
            Dict com status ou None
        """
        if task_id in self._tasks:
            return self._tasks[task_id].to_dict()
        return None

    async def get_coordinator_status(self) -> Dict:
        """
        Retorna status do coordenador.

        Returns:
            Dict com estatísticas e estado
        """
        # Contar tarefas por status
        tasks_by_status = {}
        for task in self._tasks.values():
            status = task.status
            tasks_by_status[status] = tasks_by_status.get(status, 0) + 1

        # Contar scouts por status
        scouts_by_status = {}
        for scout in self._scouts.values():
            status = scout['status']
            scouts_by_status[status] = scouts_by_status.get(status, 0) + 1

        return {
            'coordinator_id': self.coordinator_id,
            'stats': self.stats,
            'tasks_by_status': tasks_by_status,
            'scouts_by_status': scouts_by_status,
            'active_tasks': len(self._active_tasks),
            'queue_size': (
                self._high_priority_queue.qsize() +
                self._normal_priority_queue.qsize()
            ),
            'timestamp': datetime.now().isoformat()
        }

    async def broadcast_event(self, event_type: str, payload: Dict):
        """
        Broadcast evento para todos os scouts registrados.

        Args:
            event_type: Tipo do evento
            payload: Payload do evento
        """
        for scout_id in self._scouts.keys():
            logger.info(
                "event_broadcast",
                scout_id=scout_id,
                event_type=event_type
            )

    async def redistribute_tasks(self):
        """
        Redistribui tarefas de scouts desconectados.
        """
        # Encontrar tarefas atribuídas a scouts inativos
        inactive_scouts = [
            scout_id for scout_id, scout in self._scouts.items()
            if datetime.now() - scout.get('last_heartbeat', datetime.now()) > timedelta(minutes=5)
        ]

        for task_id, task in self._tasks.items():
            if task.assigned_to in inactive_scouts and task.status == 'assigned':
                # Reatribuir tarefa
                task.assigned_to = None
                task.status = 'pending'
                await self._enqueue_task(task)

                logger.info(
                    "task_redistributed",
                    task_id=task_id,
                    from_scout=task.assigned_to
                )

    def reset(self):
        """Reset todo o estado do coordenador."""
        self._tasks.clear()
        self._active_tasks.clear()
        self._scouts.clear()

        while not self._high_priority_queue.empty():
            self._high_priority_queue.get_nowait()

        while not self._normal_priority_queue.empty():
            self._normal_priority_queue.get_nowait()

        logger.info("coordinator_reset", coordinator_id=self.coordinator_id)
