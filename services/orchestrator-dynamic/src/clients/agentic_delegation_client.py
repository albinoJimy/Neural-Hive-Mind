"""
AgenticDelegationClient - Facade para delegação de tarefas a agentes especializados.

Provê uma interface unificada para delegar tarefas a diferentes agentes:
- Requirements Engineering (porta 8010)
- Architect Agent (porta 8011)
- Documentation Generation (porta 8012)
- Test Generation (porta 8013)
- Outros agentes conforme necessário
"""

import uuid
from datetime import UTC, datetime

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import OrchestratorSettings
from src.models.agentic_delegation import (
    AgentCapabilities,
    AgentType,
    DelegatedTask,
    DelegationMetrics,
    DelegationRequest,
    DelegationResponse,
    TaskStatus,
)

logger = structlog.get_logger(__name__)

# Mapa de portas dos agentes especializados
AGENT_PORTS: dict[AgentType, int] = {
    AgentType.REQUIREMENTS_ENGINEERING: 8010,
    AgentType.ARCHITECT_AGENT: 8011,
    AgentType.DOCUMENTATION_GENERATION: 8012,
    AgentType.TEST_GENERATION: 8013,
    AgentType.CODE_GENERATION: 8014,
    AgentType.DEPLOYMENT_AGENT: 8015,
    AgentType.OPTIMIZER_AGENTS: 8003,
    AgentType.ANALYST_AGENTS: 8006,
    AgentType.SCOUT_AGENTS: 8007,
    AgentType.GUARD_AGENTS: 8008,
}


class AgenticDelegationClient:
    """
    Facade para delegação de tarefas a agentes especializados.

    Funcionalidades:
    - Delegar tarefas para agentes específicos
    - Consultar status de tarefas delegadas
    - Cancelar tarefas
    - Obter métricas de delegação
    - Health check de agentes
    """

    def __init__(self, config: OrchestratorSettings):
        """Inicializa o cliente.

        Args:
            config: Configurações do orchestrator
        """
        self.config = config
        self.logger = logger.bind(component="agentic_delegation_client")
        self._client: httpx.AsyncClient | None = None
        self._tasks: dict[str, DelegatedTask] = {}  # Cache local de tarefas
        self._agent_capabilities: dict[AgentType, AgentCapabilities] = {}

    async def initialize(self):
        """Inicializa o cliente HTTP."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        self.logger.info("agentic_delegation_client_initialized")

    async def close(self):
        """Fecha o cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self.logger.info("agentic_delegation_client_closed")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=0.5, max=2))
    async def delegate(
        self,
        request: DelegationRequest,
    ) -> DelegationResponse:
        """
        Delega uma tarefa para um agente especializado.

        Args:
            request: Request de delegação

        Returns:
            DelegationResponse com task_id e status
        """
        task_id = f"DT-{uuid.uuid4().hex[:10].upper()}"

        # Criar tarefa delegada
        task = DelegatedTask(
            id=task_id,
            agent_type=request.agent_type,
            task_type=request.task_type,
            payload=request.payload,
            priority=request.priority,
            timeout_seconds=request.timeout_seconds,
            cognitive_plan_id=request.cognitive_plan_id,
            workflow_id=request.workflow_id,
            correlation_id=request.correlation_id,
            metadata=request.metadata,
        )

        # Obter endpoint do agente
        agent_endpoint = self._get_agent_endpoint(request.agent_type)

        self.logger.info(
            "delegating_task",
            task_id=task_id,
            agent_type=request.agent_type.value,
            task_type=request.task_type,
            endpoint=agent_endpoint,
        )

        try:
            # Delegar via HTTP POST
            if self._client is None:
                raise RuntimeError("Client not initialized")

            response = await self._client.post(
                f"{agent_endpoint}/delegate",
                json=request.payload,
                headers={"X-Task-ID": task_id, "X-Correlation-ID": request.correlation_id or ""},
            )

            if response.status_code == 200:
                task.status = TaskStatus.ASSIGNED
                task.assigned_at = datetime.now(UTC)
            else:
                task.status = TaskStatus.FAILED
                task.error = f"HTTP {response.status_code}: {response.text}"

            # Guardar tarefa no cache
            self._tasks[task_id] = task

            # Estimar duração baseada no tipo de agente
            capabilities = self._agent_capabilities.get(request.agent_type)
            estimated_duration = capabilities.avg_duration_seconds if capabilities else 60

            return DelegationResponse(
                task_id=task_id,
                status=task.status,
                agent_type=request.agent_type,
                estimated_duration_seconds=estimated_duration,
            )

        except httpx.HTTPError as e:
            self.logger.exception("delegation_http_error", task_id=task_id, error=str(e))
            task.status = TaskStatus.FAILED
            task.error = str(e)
            self._tasks[task_id] = task
            raise

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=0.5, max=1))
    async def get_task_status(self, task_id: str) -> DelegatedTask | None:
        """
        Consulta status de uma tarefa delegada.

        Args:
            task_id: ID da tarefa

        Returns:
            DelegatedTask ou None se não encontrado
        """
        # Primeiro verificar cache local
        if task_id in self._tasks:
            task = self._tasks[task_id]

            # Se ainda não completada, consultar o agente
            if task.status in [TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS]:
                agent_endpoint = self._get_agent_endpoint(task.agent_type)
                try:
                    if self._client is None:
                        return task

                    response = await self._client.get(
                        f"{agent_endpoint}/tasks/{task_id}",
                    )

                    if response.status_code == 200:
                        data = response.json()
                        # Atualizar status
                        task.status = TaskStatus(data.get("status", task.status.value))
                        if task.status == TaskStatus.COMPLETED:
                            task.completed_at = datetime.now(UTC)
                            task.result = data.get("result")
                        elif task.status == TaskStatus.FAILED:
                            task.error = data.get("error")
                            task.completed_at = datetime.now(UTC)
                        task.updated_at = datetime.now(UTC)

                except httpx.HTTPError as e:
                    self.logger.warning("task_status_check_failed", task_id=task_id, error=str(e))

            return task

        return None

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancela uma tarefa delegada.

        Args:
            task_id: ID da tarefa

        Returns:
            True se cancelada com sucesso
        """
        task = await self.get_task_status(task_id)
        if not task:
            return False

        # Só pode cancelar se ainda estiver pending ou assigned
        if task.status not in [TaskStatus.PENDING, TaskStatus.ASSIGNED]:
            return False

        agent_endpoint = self._get_agent_endpoint(task.agent_type)
        try:
            if self._client is None:
                return False

            response = await self._client.post(f"{agent_endpoint}/tasks/{task_id}/cancel")

            if response.status_code == 200:
                task.status = TaskStatus.CANCELLED
                task.updated_at = datetime.now(UTC)
                return True

        except httpx.HTTPError as e:
            self.logger.warning("task_cancel_failed", task_id=task_id, error=str(e))

        return False

    async def get_metrics(self) -> DelegationMetrics:
        """
        Obtém métricas de delegação.

        Returns:
            DelegationMetrics com estatísticas
        """
        total = len(self._tasks)
        pending = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)
        in_progress = sum(1 for t in self._tasks.values() if t.status == TaskStatus.IN_PROGRESS)
        completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)

        # Calcular duração média das tarefas completadas
        completed_tasks = [t for t in self._tasks.values() if t.completed_at and t.started_at]
        if completed_tasks:
            durations = [(t.completed_at - t.started_at).total_seconds() for t in completed_tasks]
            avg_duration = sum(durations) / len(durations)
        else:
            avg_duration = 0.0

        success_rate = completed / total if total > 0 else 1.0

        # Agrupar por tipo de agente
        by_agent_type: dict[str, dict[str, int]] = {}
        for task in self._tasks.values():
            agent = task.agent_type.value
            if agent not in by_agent_type:
                by_agent_type[agent] = {"total": 0, "completed": 0, "failed": 0}
            by_agent_type[agent]["total"] += 1
            if task.status == TaskStatus.COMPLETED:
                by_agent_type[agent]["completed"] += 1
            elif task.status == TaskStatus.FAILED:
                by_agent_type[agent]["failed"] += 1

        return DelegationMetrics(
            total_tasks=total,
            pending_tasks=pending,
            in_progress_tasks=in_progress,
            completed_tasks=completed,
            failed_tasks=failed,
            avg_duration_seconds=avg_duration,
            success_rate=success_rate,
            by_agent_type=by_agent_type,
        )

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=0.5, max=1))
    async def check_agent_health(self, agent_type: AgentType) -> bool:
        """
        Verifica saúde de um agente.

        Args:
            agent_type: Tipo de agente

        Returns:
            True se agente está saudável
        """
        agent_endpoint = self._get_agent_endpoint(agent_type)
        try:
            if self._client is None:
                return False

            response = await self._client.get(f"{agent_endpoint}/health")
            is_healthy = response.status_code == 200

            # Atualizar capabilities
            if agent_type not in self._agent_capabilities:
                self._agent_capabilities[agent_type] = AgentCapabilities(
                    agent_type=agent_type,
                    endpoint=agent_endpoint,
                )
            self._agent_capabilities[agent_type].is_healthy = is_healthy

            return is_healthy

        except httpx.HTTPError:
            self.logger.warning("agent_health_check_failed", agent_type=agent_type.value)
            return False

    async def get_agent_capabilities(self, agent_type: AgentType) -> AgentCapabilities | None:
        """
        Obtém capacidades de um agente.

        Args:
            agent_type: Tipo de agente

        Returns:
            AgentCapabilities ou None
        """
        if agent_type in self._agent_capabilities:
            return self._agent_capabilities[agent_type]

        # Descobrir capabilities via health check
        is_healthy = await self.check_agent_health(agent_type)
        if is_healthy:
            return self._agent_capabilities.get(agent_type)

        return None

    def _get_agent_endpoint(self, agent_type: AgentType) -> str:
        """
        Obtém endpoint de um agente.

        Args:
            agent_type: Tipo de agente

        Returns:
            URL completa do endpoint
        """
        port = AGENT_PORTS.get(agent_type, 8000)
        host = self.config.agents_host if hasattr(self.config, "agents_host") else "localhost"
        return f"http://{host}:{port}/api/v1"
