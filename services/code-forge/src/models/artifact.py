from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    """Tipos de artefatos gerados"""
    CODE = 'CODE'
    IAC = 'IAC'
    TEST = 'TEST'
    POLICY = 'POLICY'
    DOCUMENTATION = 'DOCUMENTATION'
    CONTAINER = 'CONTAINER'
    CHART = 'CHART'
    FUNCTION = 'FUNCTION'


class GenerationMethod(str, Enum):
    """Métodos de geração de código"""
    TEMPLATE = 'TEMPLATE'
    HEURISTIC = 'HEURISTIC'
    LLM = 'LLM'
    HYBRID = 'HYBRID'


class ValidationType(str, Enum):
    """Tipos de validação"""
    SAST = 'SAST'
    DAST = 'DAST'
    UNIT_TEST = 'UNIT_TEST'
    INTEGRATION_TEST = 'INTEGRATION_TEST'
    LINT = 'LINT'
    SECURITY_SCAN = 'SECURITY_SCAN'
    COMPLIANCE_CHECK = 'COMPLIANCE_CHECK'


class ValidationStatus(str, Enum):
    """Status de validação"""
    PASSED = 'PASSED'
    FAILED = 'FAILED'
    WARNING = 'WARNING'
    SKIPPED = 'SKIPPED'


class ValidationResult(BaseModel):
    """Resultado de uma validação (SAST, DAST, teste, etc.)"""

    validation_type: ValidationType = Field(..., description='Tipo de validação')
    tool_name: str = Field(..., description='Nome da ferramenta')
    tool_version: str = Field(..., description='Versão da ferramenta')
    status: ValidationStatus = Field(..., description='Status da validação')
    score: Optional[float] = Field(None, description='Score de qualidade (0.0-1.0)', ge=0.0, le=1.0)
    issues_count: int = Field(..., description='Total de issues encontrados', ge=0)
    critical_issues: int = Field(..., description='Issues críticos', ge=0)
    high_issues: int = Field(..., description='Issues high', ge=0)
    medium_issues: int = Field(..., description='Issues medium', ge=0)
    low_issues: int = Field(..., description='Issues low', ge=0)
    report_uri: Optional[str] = Field(None, description='URI do relatório completo')
    executed_at: datetime = Field(..., description='Timestamp de execução')
    duration_ms: int = Field(..., description='Duração em milissegundos', ge=0)

    def has_critical_issues(self) -> bool:
        """Verifica se há issues críticos"""
        return self.critical_issues > 0

    def has_blocking_issues(self) -> bool:
        """Verifica se há issues que bloqueiam aprovação"""
        return self.critical_issues > 0 or self.high_issues > 5

    class Config:
        use_enum_values = True


class CodeForgeArtifact(BaseModel):
    """Artefato gerado pelo Code Forge"""

    artifact_id: str = Field(..., description='Identificador único (UUID)')
    ticket_id: str = Field(..., description='ID do Execution Ticket')
    plan_id: str = Field(..., description='ID do plano cognitivo')
    intent_id: str = Field(..., description='ID da intenção')
    decision_id: str = Field(..., description='ID da decisão')

    correlation_id: Optional[str] = Field(None, description='ID de correlação')
    trace_id: Optional[str] = Field(None, description='Trace ID OpenTelemetry')
    span_id: Optional[str] = Field(None, description='Span ID OpenTelemetry')

    artifact_type: ArtifactType = Field(..., description='Tipo de artefato')
    language: Optional[str] = Field(None, description='Linguagem/framework')
    template_id: Optional[str] = Field(None, description='Template usado')

    confidence_score: float = Field(..., description='Confiança na geração (0.0-1.0)', ge=0.0, le=1.0)
    generation_method: GenerationMethod = Field(..., description='Método de geração')

    content_uri: str = Field(..., description='URI do conteúdo (S3, OCI, Git)')
    content_hash: str = Field(..., description='SHA-256 do conteúdo')
    sbom_uri: Optional[str] = Field(None, description='URI do SBOM')
    signature: Optional[str] = Field(None, description='Assinatura Sigstore')

    validation_results: List[ValidationResult] = Field(default_factory=list, description='Resultados de validações')
    metadata: Dict[str, str] = Field(default_factory=dict, description='Metadados adicionais')

    created_at: datetime = Field(..., description='Timestamp de criação')
    schema_version: int = Field(default=1, description='Versão do schema')

    def has_critical_issues(self) -> bool:
        """Verifica se há issues críticos em qualquer validação"""
        return any(vr.has_critical_issues() for vr in self.validation_results)

    def calculate_overall_score(self) -> float:
        """Calcula score geral baseado em validações e confiança"""
        if not self.validation_results:
            return self.confidence_score

        validation_scores = [vr.score for vr in self.validation_results if vr.score is not None]
        if not validation_scores:
            return self.confidence_score

        avg_validation_score = sum(validation_scores) / len(validation_scores)
        return (self.confidence_score + avg_validation_score) / 2

    class Config:
        use_enum_values = True


class StageStatus(str, Enum):
    """Status de um stage do pipeline"""
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    SKIPPED = 'SKIPPED'


class PipelineStage(BaseModel):
    """Representa um stage do pipeline"""

    stage_name: str = Field(..., description='Nome do stage')
    status: StageStatus = Field(..., description='Status do stage')
    started_at: Optional[datetime] = Field(None, description='Timestamp de início')
    completed_at: Optional[datetime] = Field(None, description='Timestamp de conclusão')
    duration_ms: int = Field(..., description='Duração em milissegundos', ge=0)
    error_message: Optional[str] = Field(None, description='Mensagem de erro se falhou')

    class Config:
        use_enum_values = True


class PipelineStatus(str, Enum):
    """Status de um pipeline Code Forge"""
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    PARTIAL = 'PARTIAL'
    REQUIRES_REVIEW = 'REQUIRES_REVIEW'


class PipelineResult(BaseModel):
    """Resultado completo de um pipeline Code Forge"""

    pipeline_id: str = Field(..., description='Identificador único do pipeline (UUID)')
    ticket_id: str = Field(..., description='ID do Execution Ticket')
    plan_id: str = Field(..., description='ID do plano cognitivo')
    intent_id: str = Field(..., description='ID da intenção')
    decision_id: str = Field(..., description='ID da decisão')

    correlation_id: Optional[str] = Field(None, description='ID de correlação')
    trace_id: Optional[str] = Field(None, description='Trace ID OpenTelemetry')
    span_id: Optional[str] = Field(None, description='Span ID OpenTelemetry')

    status: PipelineStatus = Field(..., description='Status do pipeline')
    artifacts: List[CodeForgeArtifact] = Field(default_factory=list, description='Artefatos gerados')
    pipeline_stages: List[PipelineStage] = Field(default_factory=list, description='Status dos stages')

    total_duration_ms: int = Field(..., description='Duração total em milissegundos', ge=0)
    approval_required: bool = Field(..., description='Requer aprovação manual')
    approval_reason: Optional[str] = Field(None, description='Motivo da aprovação manual')

    error_message: Optional[str] = Field(None, description='Mensagem de erro se falhou')
    git_mr_url: Optional[str] = Field(None, description='URL do Merge Request')

    created_at: datetime = Field(..., description='Timestamp de criação')
    completed_at: Optional[datetime] = Field(None, description='Timestamp de conclusão')
    metadata: Dict[str, str] = Field(default_factory=dict, description='Metadados adicionais')

    schema_version: int = Field(default=1, description='Versão do schema')

    def requires_manual_review(self) -> bool:
        """Verifica se requer revisão manual"""
        return self.approval_required or self.status == PipelineStatus.REQUIRES_REVIEW

    def calculate_overall_score(self) -> float:
        """Calcula score geral do pipeline"""
        if not self.artifacts:
            return 0.0

        artifact_scores = [a.calculate_overall_score() for a in self.artifacts]
        return sum(artifact_scores) / len(artifact_scores)

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
