"""
Workflow Paralelo para execução concorrente.

Implementa padrões fan-out/fan-in para execução paralela
de atividades independentes.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JoinStrategy(str, Enum):
    """Estratégias para join (fan-in) de resultados paralelos."""

    WAIT_ALL = "wait_all"  # Aguarda todas as tarefas completarem
    WAIT_FIRST = "wait_first"  # Primeira a completar vence
    WAIT_MAJORITY = "wait_majority"  # Maioria completa
    WAIT_N = "wait_n"  # N tarefas completarem
    ANY_SUCCESS = "any_success"  # Primeira sucesso


@dataclass
class ParallelTask:
    """Tarefa a ser executada em paralelo."""

    task_id: str
    name: str
    activity: dict[str, Any]
    dependencies: set[str] = field(default_factory=set)  # Task IDs que devem completar antes
    timeout_seconds: int = 300
    retry_policy: dict[str, Any] | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "activity": self.activity,
            "dependencies": list(self.dependencies),
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": self.retry_policy,
            "description": self.description,
        }


@dataclass
class JoinConfig:
    """Configuração de join (fan-in)."""

    strategy: JoinStrategy = JoinStrategy.WAIT_ALL
    n_value: int = 1  # Para WAIT_N
    timeout_seconds: int = 600  # Timeout global para join
    merge_strategy: str = "concat"  # concat, merge, custom

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "strategy": self.strategy.value,
            "n_value": self.n_value,
            "timeout_seconds": self.timeout_seconds,
            "merge_strategy": self.merge_strategy,
        }


class ParallelWorkflow(BaseModel):
    """Workflow com execução paralela.

    Implementa padrão fan-out/fan-in onde múltiplas tarefas
    independentes executam concorrentemente.

    Exemplo de uso:
        Deploy paralelo de microserviços independentes:
        - fan-out: iniciar deploy de user-api, product-api, order-api
        - fan-in: aguardar todos ou retornar primeiro sucesso
    """

    model_config = {"extra": "forbid"}

    workflow_id: str = Field(..., description="ID único do workflow")
    name: str = Field(..., description="Nome do workflow")
    description: str = Field(default="", description="Descrição do propósito")
    tasks: list[ParallelTask] = Field(..., description="Lista de tarefas paralelas")
    join_config: JoinConfig = Field(
        default_factory=JoinConfig, description="Configuração de join/fan-in"
    )
    input_context: dict[str, Any] = Field(default_factory=dict, description="Contexto de entrada")

    def get_execution_order(self) -> list[list[str]]:
        """Calcula ordem de execução considerando dependências.

        Returns:
            Lista de listas (batches) onde cada batch contém task_ids
            que podem ser executados em paralelo.
        """
        {t.task_id: t for t in self.tasks}
        completed: set[str] = set()
        batches: list[list[str]] = []

        while len(completed) < len(self.tasks):
            # Encontrar tarefas prontas (dependências satisfeitas)
            ready = []
            for task in self.tasks:
                if task.task_id in completed:
                    continue
                if task.dependencies.issubset(completed):
                    ready.append(task.task_id)

            if not ready:
                # Ciclo de dependência detectado
                remaining = [t.task_id for t in self.tasks if t.task_id not in completed]
                raise ValueError(f"Circular dependency detected among tasks: {remaining}")

            batches.append(ready)
            completed.update(ready)

        return batches

    def get_tasks_for_batch(self, batch_num: int) -> list[ParallelTask]:
        """Retorna tarefas para um batch específico."""
        batches = self.get_execution_order()
        if batch_num < 0 or batch_num >= len(batches):
            return []

        task_ids = batches[batch_num]
        task_map = {t.task_id: t for t in self.tasks}
        return [task_map[tid] for tid in task_ids]

    def can_join(self, completed_tasks: set[str]) -> bool:
        """Verifica se condições de join são atendidas.

        Args:
            completed_tasks: Conjunto de task_ids completados

        Returns:
            True se pode fazer join, False caso contrário
        """
        match self.join_config.strategy:
            case JoinStrategy.WAIT_ALL:
                return len(completed_tasks) >= len(self.tasks)
            case JoinStrategy.WAIT_FIRST:
                return len(completed_tasks) >= 1
            case JoinStrategy.WAIT_MAJORITY:
                return len(completed_tasks) > len(self.tasks) // 2
            case JoinStrategy.WAIT_N:
                return len(completed_tasks) >= self.join_config.n_value
            case JoinStrategy.ANY_SUCCESS:
                # Na prática requer rastreamento de sucesso/erro
                return len(completed_tasks) >= 1
            case _:
                return False

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
            "join_config": self.join_config.to_dict(),
            "input_context": self.input_context,
            "execution_order": self.get_execution_order(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParallelWorkflow":
        """Cria ParallelWorkflow a partir de dicionário."""
        tasks = []
        for t_data in data.get("tasks", []):
            tasks.append(
                ParallelTask(
                    task_id=t_data["task_id"],
                    name=t_data["name"],
                    activity=t_data["activity"],
                    dependencies=set(t_data.get("dependencies", [])),
                    timeout_seconds=t_data.get("timeout_seconds", 300),
                    retry_policy=t_data.get("retry_policy"),
                    description=t_data.get("description", ""),
                )
            )

        join_data = data.get("join_config", {})
        join_config = JoinConfig(
            strategy=JoinStrategy(join_data.get("strategy", "wait_all")),
            n_value=join_data.get("n_value", 1),
            timeout_seconds=join_data.get("timeout_seconds", 600),
            merge_strategy=join_data.get("merge_strategy", "concat"),
        )

        return cls(
            workflow_id=data["workflow_id"],
            name=data["name"],
            description=data.get("description", ""),
            tasks=tasks,
            join_config=join_config,
            input_context=data.get("input_context", {}),
        )


# Exemplos de workflows paralelos predefinidos


def create_parallel_deploy_workflow() -> ParallelWorkflow:
    """Cria workflow para deploy paralelo de microserviços."""
    tasks = [
        ParallelTask(
            task_id="deploy-user-api",
            name="deploy_user_api",
            activity={
                "type": "deploy",
                "service": "user-api",
                "image": "user-api:latest",
                "replicas": 3,
            },
            dependencies=set(),
            timeout_seconds=600,
            description="Deploy do serviço de usuários",
        ),
        ParallelTask(
            task_id="deploy-product-api",
            name="deploy_product_api",
            activity={
                "type": "deploy",
                "service": "product-api",
                "image": "product-api:latest",
                "replicas": 2,
            },
            dependencies=set(),
            timeout_seconds=600,
            description="Deploy do serviço de produtos",
        ),
        ParallelTask(
            task_id="deploy-order-api",
            name="deploy_order_api",
            activity={
                "type": "deploy",
                "service": "order-api",
                "image": "order-api:latest",
                "replicas": 3,
            },
            dependencies=set(),
            timeout_seconds=600,
            description="Deploy do serviço de pedidos",
        ),
        ParallelTask(
            task_id="run-smoke-tests",
            name="run_smoke_tests",
            activity={
                "type": "test",
                "test_suite": "smoke",
                "timeout": 300,
            },
            dependencies={"deploy-user-api", "deploy-product-api", "deploy-order-api"},
            timeout_seconds=400,
            description="Executar testes de smoke após todos os deploys",
        ),
    ]

    join_config = JoinConfig(
        strategy=JoinStrategy.WAIT_ALL,
        timeout_seconds=1800,
        merge_strategy="concat",
    )

    return ParallelWorkflow(
        workflow_id="wf-parallel-deploy",
        name="parallel_deployment",
        description="Deploy paralelo de microserviços independentes",
        tasks=tasks,
        join_config=join_config,
    )


def create_parallel_validation_workflow() -> ParallelWorkflow:
    """Cria workflow para validação paralela com múltiplas estratégias."""
    tasks = [
        ParallelTask(
            task_id="opa-validation",
            name="opa_policy_validation",
            activity={
                "type": "validate",
                "validator": "opa",
                "policy_path": "architecture/rules",
            },
            dependencies=set(),
            timeout_seconds=30,
            description="Validação via OPA",
        ),
        ParallelTask(
            task_id="scout-validation",
            name="scout_agent_validation",
            activity={
                "type": "validate",
                "validator": "scout",
                "check_security": True,
                "check_performance": True,
            },
            dependencies=set(),
            timeout_seconds=120,
            description="Validação via Scout Agents",
        ),
        ParallelTask(
            task_id="ml-validation",
            name="ml_model_validation",
            activity={
                "type": "validate",
                "validator": "ml",
                "model": "architectural_risk",
                "threshold": 0.7,
            },
            dependencies=set(),
            timeout_seconds=60,
            description="Validação via modelo ML de risco",
        ),
    ]

    join_config = JoinConfig(
        strategy=JoinStrategy.ANY_SUCCESS,
        timeout_seconds=300,
        merge_strategy="merge",
    )

    return ParallelWorkflow(
        workflow_id="wf-parallel-validation",
        name="parallel_validation",
        description="Validação paralela com múltiplas estratégias (any success)",
        tasks=tasks,
        join_config=join_config,
    )


def create_multi_region_replica_workflow() -> ParallelWorkflow:
    """Cria workflow para replicação multi-região em paralelo."""
    regions = ["us-east-1", "eu-west-1", "ap-southeast-1"]

    tasks = []
    for region in regions:
        tasks.append(
            ParallelTask(
                task_id=f"replicate-{region}",
                name=f"replicate_{region.replace('-', '_')}",
                activity={
                    "type": "replicate",
                    "region": region,
                    "service": "user-api",
                },
                dependencies=set(),
                timeout_seconds=900,
                description=f"Replicar para região {region}",
            )
        )

    # Task de DNS update depende de todas as replicações
    tasks.append(
        ParallelTask(
            task_id="update-dns",
            name="update_dns_records",
            activity={
                "type": "dns_update",
                "type": "geo_routing",
            },
            dependencies={f"replicate-{r}" for r in regions},
            timeout_seconds=300,
            description="Atualizar DNS para roteamento geo",
        )
    )

    join_config = JoinConfig(
        strategy=JoinStrategy.WAIT_ALL,
        timeout_seconds=3600,
        merge_strategy="concat",
    )

    return ParallelWorkflow(
        workflow_id="wf-multi-region-replica",
        name="multi_region_replication",
        description=f"Replicação paralela para {len(regions)} regiões",
        tasks=tasks,
        join_config=join_config,
    )
