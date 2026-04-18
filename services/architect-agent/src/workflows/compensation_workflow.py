"""
Workflow de Compensação (Saga Pattern).

Implementa padrão Saga para compensação de operações em workflows
distribuídos, permitindo rollback de execuções parciais.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CompensationAction(str, Enum):
    """Ações de compensação."""

    ROLLBACK = "rollback"
    COMPENSATE = "compensate"
    CANCEL = "cancel"
    REVERT = "revert"
    UNDO = "undo"


@dataclass
class CompensationStep:
    """Passo de compensação para uma atividade."""

    step_id: str
    name: str
    original_activity: dict[str, Any]
    compensation_activity: dict[str, Any]
    order: int  # Ordem inversa para execução de compensação
    timeout_seconds: int = 300
    retry_policy: dict[str, Any] | None = None
    compensates_if: dict[str, Any] | None = None  # Condição para compensar
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "original_activity": self.original_activity,
            "compensation_activity": self.compensation_activity,
            "order": self.order,
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": self.retry_policy,
            "compensates_if": self.compensates_if,
            "description": self.description,
        }


@dataclass
class SagaState:
    """Estado de uma execução Saga."""

    saga_id: str
    workflow_id: str
    current_step: int = 0
    status: str = "running"  # running, compensating, completed, failed
    completed_steps: list[str] = field(default_factory=list)
    compensation_order: list[str] = field(default_factory=list)
    error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "saga_id": self.saga_id,
            "workflow_id": self.workflow_id,
            "current_step": self.current_step,
            "status": self.status,
            "completed_steps": self.completed_steps,
            "compensation_order": self.compensation_order,
            "error": self.error,
            "context": self.context,
        }


class CompensationWorkflow(BaseModel):
    """Workflow com compensação (Saga Pattern).

    Implementa padrão Saga onde cada passo tem uma ação de compensação
    correspondente. Em caso de falha, executa compensações em ordem reversa.

    Exemplo de uso:
        Provisionamento de infraestrutura cloud:
        1. Criar VPC
        2. Criar subnet
        3. Criar security group
        4. Launch instances

        Se passo 4 falhar, compensar: 3 -> 2 -> 1
    """

    model_config = {"extra": "forbid"}

    workflow_id: str = Field(..., description="ID único do workflow")
    name: str = Field(..., description="Nome do workflow")
    description: str = Field(default="", description="Descrição do propósito")
    steps: list[CompensationStep] = Field(..., description="Passos do workflow com compensação")
    auto_compensate: bool = Field(default=True, description="Compensar automaticamente em erro")
    compensation_timeout_seconds: int = Field(
        default=3600, description="Timeout total para compensação"
    )
    input_context: dict[str, Any] = Field(default_factory=dict, description="Contexto de entrada")

    def get_compensation_order(self) -> list[str]:
        """Retorna ordem de compensação (inverso da execução).

        Returns:
            Lista de step_ids em ordem de compensação
        """
        return [step.step_id for step in sorted(self.steps, key=lambda s: -s.order)]

    def get_compensation_steps(self, completed_step_ids: list[str]) -> list[CompensationStep]:
        """Retorna passos de compensação para os passos completados.

        Args:
            completed_step_ids: IDs dos passos que foram completados

        Returns:
            Lista de CompensationStep em ordem de execução de compensação
        """
        step_map = {s.step_id: s for s in self.steps}

        # Filtrar apenas passos completados
        completed_steps = [step_map[sid] for sid in completed_step_ids if sid in step_map]

        # Ordenar inversamente para compensação
        return sorted(completed_steps, key=lambda s: -s.order)

    def needs_compensation(self, step: CompensationStep, error_context: dict[str, Any]) -> bool:
        """Verifica se um passo precisa ser compensado.

        Args:
            step: CompensationStep a verificar
            error_context: Contexto do erro para avaliação

        Returns:
            True se compensação é necessária
        """
        if step.compensates_if is None:
            return True  # Compensar por padrão

        # Avaliar condição
        condition_field = step.compensates_if.get("field")
        condition_operator = step.compensates_if.get("operator")
        condition_value = step.compensates_if.get("value")

        if not all([condition_field, condition_operator]):
            return True

        actual_value = error_context.get(condition_field)

        match condition_operator:
            case "eq":
                return actual_value == condition_value
            case "ne":
                return actual_value != condition_value
            case "in":
                return actual_value in condition_value
            case "contains":
                return condition_value in str(actual_value)
            case _:
                return True

    def create_saga_state(self, saga_id: str | None = None) -> SagaState:
        """Cria estado inicial para execução Saga.

        Args:
            saga_id: ID único (gerado se None)

        Returns:
            SagaState inicializado
        """
        import uuid

        return SagaState(
            saga_id=saga_id or f"saga-{uuid.uuid4().hex[:8]}",
            workflow_id=self.workflow_id,
            current_step=0,
            status="running",
            compensation_order=self.get_compensation_order(),
            context=self.input_context.copy(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "auto_compensate": self.auto_compensate,
            "compensation_timeout_seconds": self.compensation_timeout_seconds,
            "input_context": self.input_context,
            "compensation_order": self.get_compensation_order(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompensationWorkflow":
        """Cria CompensationWorkflow a partir de dicionário."""
        steps = []
        for s_data in data.get("steps", []):
            steps.append(
                CompensationStep(
                    step_id=s_data["step_id"],
                    name=s_data["name"],
                    original_activity=s_data["original_activity"],
                    compensation_activity=s_data["compensation_activity"],
                    order=s_data["order"],
                    timeout_seconds=s_data.get("timeout_seconds", 300),
                    retry_policy=s_data.get("retry_policy"),
                    compensates_if=s_data.get("compensates_if"),
                    description=s_data.get("description", ""),
                )
            )

        return cls(
            workflow_id=data["workflow_id"],
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
            auto_compensate=data.get("auto_compensate", True),
            compensation_timeout_seconds=data.get("compensation_timeout_seconds", 3600),
            input_context=data.get("input_context", {}),
        )


# Exemplos de workflows de compensação predefinidos


def create_cloud_infrastructure_workflow() -> CompensationWorkflow:
    """Cria workflow Saga para provisionamento de infraestrutura cloud."""
    steps = [
        CompensationStep(
            step_id="create-vpc",
            name="create_vpc",
            original_activity={
                "type": "create_vpc",
                "cidr": "10.0.0.0/16",
            },
            compensation_activity={
                "type": "delete_vpc",
                "force": True,
            },
            order=1,
            description="Criar Virtual Private Cloud",
        ),
        CompensationStep(
            step_id="create-subnet",
            name="create_subnet",
            original_activity={
                "type": "create_subnet",
                "cidr": "10.0.1.0/24",
                "availability_zone": "us-east-1a",
            },
            compensation_activity={
                "type": "delete_subnet",
            },
            order=2,
            description="Criar subnet pública",
        ),
        CompensationStep(
            step_id="create-security-group",
            name="create_security_group",
            original_activity={
                "type": "create_security_group",
                "rules": [
                    {"protocol": "tcp", "port": 80, "source": "0.0.0.0/0"},
                    {"protocol": "tcp", "port": 443, "source": "0.0.0.0/0"},
                ],
            },
            compensation_activity={
                "type": "delete_security_group",
            },
            order=3,
            description="Criar security group com regras",
        ),
        CompensationStep(
            step_id="launch-instances",
            name="launch_instances",
            original_activity={
                "type": "launch_instances",
                "instance_type": "t3.medium",
                "ami": "ami-12345",
                "count": 3,
            },
            compensation_activity={
                "type": "terminate_instances",
                "force": True,
            },
            order=4,
            description="Lançar instâncias EC2",
        ),
    ]

    return CompensationWorkflow(
        workflow_id="wf-cloud-infra",
        name="cloud_infrastructure_provisioning",
        description="Provisionamento de infraestrutura cloud com compensação",
        steps=steps,
        auto_compensate=True,
    )


def create_database_migration_workflow() -> CompensationWorkflow:
    """Cria workflow Saga para migração de banco de dados."""
    steps = [
        CompensationStep(
            step_id="backup-source",
            name="backup_source_database",
            original_activity={
                "type": "backup_database",
                "database": "source_db",
            },
            compensation_activity={
                "type": "cleanup_backup",
            },
            order=1,
            description="Backup do banco de origem",
        ),
        CompensationStep(
            step_id="create-target-schema",
            name="create_target_schema",
            original_activity={
                "type": "create_schema",
                "database": "target_db",
            },
            compensation_activity={
                "type": "drop_schema",
                "database": "target_db",
            },
            order=2,
            description="Criar schema no banco destino",
        ),
        CompensationStep(
            step_id="migrate-data",
            name="migrate_data",
            original_activity={
                "type": "migrate_data",
                "batch_size": 1000,
            },
            compensation_activity={
                "type": "rollback_data",
            },
            order=3,
            description="Migrar dados em lotes",
        ),
        CompensationStep(
            step_id="update-app-config",
            name="update_application_config",
            original_activity={
                "type": "update_config",
                "database_url": "target_db",
            },
            compensation_activity={
                "type": "revert_config",
                "database_url": "source_db",
            },
            order=4,
            description="Atualizar configuração da aplicação",
        ),
    ]

    return CompensationWorkflow(
        workflow_id="wf-db-migration",
        name="database_migration",
        description="Migração de banco de dados com rollback",
        steps=steps,
        auto_compensate=True,
    )


def create_kubernetes_deployment_workflow() -> CompensationWorkflow:
    """Cria workflow Saga para deployment em Kubernetes."""
    steps = [
        CompensationStep(
            step_id="create-namespace",
            name="create_namespace",
            original_activity={
                "type": "kubectl_apply",
                "manifest": "namespace.yaml",
            },
            compensation_activity={
                "type": "kubectl_delete",
                "resource": "namespace",
            },
            order=1,
            description="Criar namespace",
        ),
        CompensationStep(
            step_id="create-configmaps",
            name="create_configmaps",
            original_activity={
                "type": "kubectl_apply",
                "manifest": "configmap.yaml",
            },
            compensation_activity={
                "type": "kubectl_delete",
                "resource": "configmap",
            },
            order=2,
            description="Criar ConfigMaps",
        ),
        CompensationStep(
            step_id="create-secrets",
            name="create_secrets",
            original_activity={
                "type": "kubectl_apply",
                "manifest": "secrets.yaml",
            },
            compensation_activity={
                "type": "kubectl_delete",
                "resource": "secret",
            },
            order=3,
            description="Criar Secrets",
        ),
        CompensationStep(
            step_id="deploy-app",
            name="deploy_application",
            original_activity={
                "type": "kubectl_apply",
                "manifest": "deployment.yaml",
            },
            compensation_activity={
                "type": "kubectl_rollback",
                "resource": "deployment",
            },
            order=4,
            description="Deploy da aplicação",
        ),
        CompensationStep(
            step_id="create-service",
            name="create_service",
            original_activity={
                "type": "kubectl_apply",
                "manifest": "service.yaml",
            },
            compensation_activity={
                "type": "kubectl_delete",
                "resource": "service",
            },
            order=5,
            description="Criar Service",
        ),
    ]

    return CompensationWorkflow(
        workflow_id="wf-k8s-deployment",
        name="kubernetes_deployment",
        description="Deploy em Kubernetes com rollback automático",
        steps=steps,
        auto_compensate=True,
    )
