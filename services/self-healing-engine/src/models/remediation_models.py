from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ExecutionMode(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL_APPROVAL = "MANUAL_APPROVAL"


class ActionType(str, Enum):
    """Tipos de ações suportadas em playbooks."""

    # Ações de execução de tickets
    REALLOCATE_TICKET = "reallocate_ticket"
    REALLOCATE_MULTIPLE_TICKETS = "reallocate_multiple_tickets"
    UPDATE_TICKET_STATUS = "update_ticket_status"
    GET_TICKET = "get_ticket"

    # Ações de workflow/orchestrator
    PAUSE_WORKFLOW = "pause_workflow"
    RESUME_WORKFLOW = "resume_workflow"
    TRIGGER_REPLANNING = "trigger_replanning"
    GET_WORKFLOW_STATUS = "get_workflow_status"

    # Ações de saúde
    CHECK_WORKER_HEALTH = "check_worker_health"
    CHECK_SERVICE_HEALTH = "check_service_health"

    # Ações de Kubernetes
    RESTART_POD = "restart_pod"
    DELETE_POD = "delete_pod"
    SCALE_DEPLOYMENT = "scale_deployment"
    PATCH_DEPLOYMENT = "patch_deployment"

    # Ações de Kafka
    CHECK_KAFKA_LAG = "check_kafka_lag"
    RESET_CONSUMER_OFFSET = "reset_consumer_offset"
    CLEANUP_POISON_MESSAGES = "cleanup_poison_messages"

    # Ações de database
    CHECK_DATABASE_CONNECTION = "check_database_connection"
    EXECUTE_QUERY = "execute_query"

    # Ações de políticas/configuração
    UPDATE_POLICY = "update_policy"
    APPLY_POLICY = "apply_policy"

    # Ações gerais
    WAIT = "wait"
    LOG = "log"
    NOTIFY = "notify"
    NOTIFY_AGENT = "notify_agent"


class PlaybookAction(BaseModel):
    """Modelo Pydantic para uma ação de playbook."""

    type: ActionType = Field(..., description="Tipo da ação a executar")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Parâmetros específicos da ação"
    )
    description: Optional[str] = Field(default=None, description="Descrição opcional da ação")
    continue_on_failure: bool = Field(
        default=False, description="Continuar execução mesmo se esta ação falhar"
    )
    timeout_seconds: Optional[int] = Field(
        default=None, ge=1, le=3600, description="Timeout específico para esta ação"
    )

    @field_validator("type")
    @classmethod
    def validate_action_type(cls, v: str) -> str:
        """Valida que o tipo de ação é suportado."""
        try:
            ActionType(v)
            return v
        except ValueError:
            valid_types = [t.value for t in ActionType]
            raise ValueError(
                f"Tipo de ação inválido: '{v}'. Tipos válidos: {', '.join(valid_types)}"
            )


class Playbook(BaseModel):
    """Modelo Pydantic para estrutura completa de um playbook."""

    playbook_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(
        default=None, max_length=500, description="Descrição do playbook"
    )
    timeout_seconds: int = Field(
        default=300, ge=1, le=3600, description="Timeout total do playbook (segundos)"
    )
    actions: list[PlaybookAction] = Field(
        ..., min_length=1, description="Lista de ações a executar"
    )
    enabled: bool = Field(default=True, description="Se o playbook está habilitado")
    execution_mode: ExecutionMode = Field(
        default=ExecutionMode.AUTOMATIC, description="Modo de execução padrão"
    )
    tags: list[str] = Field(default_factory=list, description="Tags para categorização")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")
    version: str = Field(default="1.0.0", description="Versão do playbook")
    created_at: Optional[datetime] = Field(
        default=None, description="Data de criação (automático se não fornecido)"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Data última atualização (automático se não fornecido)"
    )

    @field_validator("actions")
    @classmethod
    def validate_actions_not_empty(cls, v: list[PlaybookAction]) -> list[PlaybookAction]:
        """Valida que há pelo menos uma ação."""
        if not v:
            raise ValueError("Playbook deve conter pelo menos uma ação")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Valida formato das tags."""
        for tag in v:
            if not isinstance(tag, str) or len(tag) > 50:
                raise ValueError(f"Tag inválida: '{tag}'. Deve ser string com até 50 caracteres.")
        return v


class PlaybookValidationResult(BaseModel):
    """Resultado da validação de playbook."""

    valid: bool = Field(..., description="Se o playbook é válido")
    playbook_name: str = Field(..., description="Nome do playbook validado")
    errors: list[str] = Field(default_factory=list, description="Lista de erros de validação")
    warnings: list[str] = Field(
        default_factory=list, description="Lista de avisos (não bloqueia execução)"
    )
    action_count: int = Field(..., description="Número de ações no playbook")
    parsed_actions: list[str] = Field(default_factory=list, description="Tipos de ações parseadas")
    estimated_duration_seconds: Optional[int] = Field(
        default=None, description="Duração estimada baseada em timeouts"
    )


class RemediationRequest(BaseModel):
    remediation_id: Optional[str] = Field(
        default=None,
        description="Optional remediation ID (UUID). If not provided, it will be generated.",
    )
    incident_id: str = Field(..., description="ID do incidente que originou a remediação")
    playbook_name: str = Field(..., description="Nome do playbook a executar")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Parâmetros dinâmicos para execução"
    )
    execution_mode: ExecutionMode = Field(
        default=ExecutionMode.AUTOMATIC,
        description="Modo de execução (automático ou aguardando aprovação)",
    )


class RemediationResponse(BaseModel):
    remediation_id: str
    status: str
    started_at: Optional[str] = None
    message: Optional[str] = None


class RemediationStatusResponse(BaseModel):
    remediation_id: str
    status: str
    progress: float = 0.0
    actions_completed: int = 0
    total_actions: int = 0
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
