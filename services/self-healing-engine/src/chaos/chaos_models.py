"""
Modelos Pydantic para Chaos Engineering.

Define as estruturas de dados para experimentos de chaos,
injeção de falhas, validação e relatórios.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


class ChaosExperimentStatus(str, Enum):
    """Status do experimento de chaos."""
    PLANNED = "PLANNED"
    INJECTING = "INJECTING"
    VALIDATING = "VALIDATING"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"


class FaultType(str, Enum):
    """Tipos de falha suportados."""
    # Network faults
    NETWORK_LATENCY = "network_latency"
    NETWORK_PACKET_LOSS = "network_packet_loss"
    NETWORK_PARTITION = "network_partition"
    NETWORK_BANDWIDTH_LIMIT = "network_bandwidth_limit"

    # Pod faults
    POD_KILL = "pod_kill"
    CONTAINER_KILL = "container_kill"
    CONTAINER_PAUSE = "container_pause"
    POD_EVICT = "pod_evict"

    # Resource faults
    CPU_STRESS = "cpu_stress"
    MEMORY_STRESS = "memory_stress"
    DISK_FILL = "disk_fill"
    FD_EXHAUST = "fd_exhaust"

    # Application faults
    HTTP_ERROR = "http_error"
    HTTP_DELAY = "http_delay"
    CIRCUIT_BREAKER_TRIGGER = "circuit_breaker_trigger"


class RollbackStrategy(str, Enum):
    """Estratégia de rollback para experimentos."""
    AUTOMATIC = "automatic"  # Rollback automático em caso de falha
    MANUAL = "manual"  # Requer intervenção manual
    TIMEOUT = "timeout"  # Rollback após timeout
    NONE = "none"  # Sem rollback (falhas são permanentes até resolução manual)


class TargetSelector(BaseModel):
    """Seletor de alvos para injeção de falhas."""
    namespace: str = Field(default="default", description="Namespace Kubernetes")
    labels: Dict[str, str] = Field(default_factory=dict, description="Labels para seleção")
    pod_names: List[str] = Field(default_factory=list, description="Nomes específicos de pods")
    deployment_name: Optional[str] = Field(default=None, description="Nome do deployment")
    service_name: Optional[str] = Field(default=None, description="Nome do serviço")
    percentage: int = Field(default=100, ge=0, le=100, description="Percentual de pods afetados")


class FaultParameters(BaseModel):
    """Parâmetros de configuração de falha."""
    # Network parameters
    latency_ms: Optional[int] = Field(default=None, ge=0, description="Latência em ms")
    jitter_ms: Optional[int] = Field(default=None, ge=0, description="Variação de latência em ms")
    packet_loss_percent: Optional[float] = Field(default=None, ge=0, le=100, description="% de perda de pacotes")
    bandwidth_limit_kbps: Optional[int] = Field(default=None, ge=0, description="Limite de bandwidth em Kbps")
    correlation_percent: Optional[float] = Field(default=None, ge=0, le=100, description="Correlação de perda")

    # Resource parameters
    cpu_cores: Optional[int] = Field(default=None, ge=1, description="Núcleos de CPU para stress")
    cpu_load_percent: Optional[int] = Field(default=None, ge=0, le=100, description="% de carga de CPU")
    memory_bytes: Optional[int] = Field(default=None, ge=0, description="Bytes de memória para stress")
    disk_fill_bytes: Optional[int] = Field(default=None, ge=0, description="Bytes para preencher disco")
    disk_path: Optional[str] = Field(default=None, description="Path para disk fill")

    # Application parameters
    http_status_code: Optional[int] = Field(default=None, ge=100, le=599, description="Código HTTP para injetar")
    http_delay_ms: Optional[int] = Field(default=None, ge=0, description="Delay HTTP em ms")
    http_path_pattern: Optional[str] = Field(default=None, description="Padrão de path HTTP")

    # Container parameters
    container_name: Optional[str] = Field(default=None, description="Nome do container alvo")
    signal: Optional[str] = Field(default="SIGKILL", description="Sinal para container kill")


class ValidationCriteria(BaseModel):
    """Critérios de validação para experimentos."""
    max_recovery_time_seconds: int = Field(default=300, ge=0, description="Tempo máximo de recuperação")
    min_availability_percent: float = Field(default=99.0, ge=0, le=100, description="Disponibilidade mínima")
    max_error_rate_percent: float = Field(default=1.0, ge=0, le=100, description="Taxa máxima de erros")
    max_latency_p95_ms: Optional[int] = Field(default=None, ge=0, description="Latência P95 máxima em ms")
    max_latency_p99_ms: Optional[int] = Field(default=None, ge=0, description="Latência P99 máxima em ms")
    custom_metrics: Dict[str, Any] = Field(default_factory=dict, description="Métricas customizadas")
    required_playbook: Optional[str] = Field(default=None, description="Playbook que deve ser executado")


class FaultInjection(BaseModel):
    """Representa uma injeção de falha individual."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID da injeção")
    fault_type: FaultType = Field(..., description="Tipo de falha")
    target: TargetSelector = Field(default_factory=TargetSelector, description="Alvo da falha")
    parameters: FaultParameters = Field(default_factory=FaultParameters, description="Parâmetros da falha")
    duration_seconds: int = Field(default=60, ge=1, description="Duração da falha em segundos")
    start_time: Optional[datetime] = Field(default=None, description="Hora de início")
    end_time: Optional[datetime] = Field(default=None, description="Hora de término")
    status: str = Field(default="pending", description="Status da injeção")
    affected_pods: List[str] = Field(default_factory=list, description="Pods afetados")
    rollback_data: Dict[str, Any] = Field(default_factory=dict, description="Dados para rollback")


class ChaosExperiment(BaseModel):
    """Experimento de Chaos Engineering."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID do experimento")
    name: str = Field(..., min_length=1, max_length=200, description="Nome do experimento")
    description: Optional[str] = Field(default=None, description="Descrição do experimento")
    environment: str = Field(default="staging", description="Ambiente de execução")
    fault_injections: List[FaultInjection] = Field(default_factory=list, description="Injeções de falha")
    validation_criteria: ValidationCriteria = Field(
        default_factory=ValidationCriteria,
        description="Critérios de validação"
    )
    rollback_strategy: RollbackStrategy = Field(
        default=RollbackStrategy.AUTOMATIC,
        description="Estratégia de rollback"
    )
    timeout_seconds: int = Field(default=600, ge=60, le=3600, description="Timeout total em segundos")
    blast_radius_limit: int = Field(default=5, ge=1, le=50, description="Limite de pods afetados")
    status: ChaosExperimentStatus = Field(default=ChaosExperimentStatus.PLANNED, description="Status atual")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Data de criação")
    started_at: Optional[datetime] = Field(default=None, description="Data de início")
    completed_at: Optional[datetime] = Field(default=None, description="Data de conclusão")
    approved_by: Optional[str] = Field(default=None, description="Aprovador do experimento")
    executed_by: Optional[str] = Field(default=None, description="Executor do experimento")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")


class ValidationResult(BaseModel):
    """Resultado de validação de playbook."""
    playbook_name: str = Field(..., description="Nome do playbook validado")
    success: bool = Field(..., description="Se a validação foi bem-sucedida")
    recovery_time_seconds: Optional[float] = Field(default=None, description="Tempo de recuperação em segundos")
    availability_percent: Optional[float] = Field(default=None, description="Disponibilidade durante teste")
    error_rate_percent: Optional[float] = Field(default=None, description="Taxa de erros durante teste")
    latency_p95_ms: Optional[float] = Field(default=None, description="Latência P95 em ms")
    latency_p99_ms: Optional[float] = Field(default=None, description="Latência P99 em ms")
    criteria_met: Dict[str, bool] = Field(default_factory=dict, description="Critérios atendidos")
    observations: List[str] = Field(default_factory=list, description="Observações do validador")
    metrics_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Snapshot de métricas")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp da validação")


class ExperimentReport(BaseModel):
    """Relatório completo de experimento de chaos."""
    experiment_id: str = Field(..., description="ID do experimento")
    experiment_name: str = Field(..., description="Nome do experimento")
    environment: str = Field(..., description="Ambiente de execução")
    start_time: datetime = Field(..., description="Hora de início")
    end_time: datetime = Field(..., description="Hora de término")
    duration_seconds: float = Field(..., description="Duração total em segundos")
    status: ChaosExperimentStatus = Field(..., description="Status final")
    fault_injections: List[FaultInjection] = Field(default_factory=list, description="Injeções executadas")
    validations: List[ValidationResult] = Field(default_factory=list, description="Resultados de validação")
    blast_radius: int = Field(default=0, description="Número de pods afetados")
    playbooks_triggered: List[str] = Field(default_factory=list, description="Playbooks acionados")
    outcome: str = Field(..., description="Resultado final (success/failure)")
    failure_reason: Optional[str] = Field(default=None, description="Razão de falha se aplicável")
    recommendations: List[str] = Field(default_factory=list, description="Recomendações baseadas no teste")
    metrics_summary: Dict[str, Any] = Field(default_factory=dict, description="Resumo de métricas")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Data de geração do relatório")


class ChaosExperimentRequest(BaseModel):
    """Request para criar um experimento de chaos."""
    name: str = Field(..., min_length=1, max_length=200, description="Nome do experimento")
    description: Optional[str] = Field(default=None, description="Descrição")
    environment: str = Field(default="staging", description="Ambiente")
    fault_injections: List[FaultInjection] = Field(..., min_length=1, description="Injeções de falha")
    validation_criteria: Optional[ValidationCriteria] = Field(default=None, description="Critérios de validação")
    rollback_strategy: RollbackStrategy = Field(default=RollbackStrategy.AUTOMATIC, description="Estratégia rollback")
    timeout_seconds: int = Field(default=600, ge=60, le=3600, description="Timeout em segundos")
    blast_radius_limit: int = Field(default=5, ge=1, le=50, description="Limite de blast radius")
    approved_by: Optional[str] = Field(default=None, description="Aprovador")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados")


class ChaosExperimentResponse(BaseModel):
    """Response de experimento de chaos."""
    experiment_id: str = Field(..., description="ID do experimento")
    status: ChaosExperimentStatus = Field(..., description="Status atual")
    message: str = Field(..., description="Mensagem de status")
    started_at: Optional[datetime] = Field(default=None, description="Data de início")
    estimated_duration_seconds: Optional[int] = Field(default=None, description="Duração estimada")


class ScenarioConfig(BaseModel):
    """Configuração de cenário pré-definido."""
    name: str = Field(..., description="Nome do cenário")
    description: str = Field(..., description="Descrição do cenário")
    target_service: str = Field(..., description="Serviço alvo")
    target_namespace: str = Field(default="default", description="Namespace alvo")
    playbook_to_validate: Optional[str] = Field(default=None, description="Playbook para validar")
    custom_parameters: Dict[str, Any] = Field(default_factory=dict, description="Parâmetros customizados")
