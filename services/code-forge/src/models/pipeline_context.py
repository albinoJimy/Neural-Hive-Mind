from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field

from .execution_ticket import ExecutionTicket
from .artifact import CodeForgeArtifact, ValidationResult, PipelineStage, PipelineResult, PipelineStatus, StageStatus
from .template import Template


class PipelineContext(BaseModel):
    """Contexto de execução de um pipeline Code Forge"""

    pipeline_id: str = Field(..., description='UUID do pipeline')
    ticket: ExecutionTicket = Field(..., description='Ticket de entrada')

    trace_id: str = Field(..., description='Trace ID OpenTelemetry')
    span_id: str = Field(..., description='Span ID OpenTelemetry')

    selected_template: Optional[Template] = Field(None, description='Template selecionado')
    generated_artifacts: List[CodeForgeArtifact] = Field(default_factory=list, description='Artefatos gerados')
    validation_results: List[ValidationResult] = Field(default_factory=list, description='Resultados de validações')
    pipeline_stages: List[PipelineStage] = Field(default_factory=list, description='Status dos stages')

    metadata: Dict[str, Any] = Field(default_factory=dict, description='Metadados adicionais')

    started_at: datetime = Field(default_factory=datetime.now, description='Timestamp de início')
    completed_at: Optional[datetime] = Field(None, description='Timestamp de conclusão')

    error: Optional[Exception] = Field(None, description='Erro se falhou')

    def add_artifact(self, artifact: CodeForgeArtifact):
        """Adiciona um artefato gerado"""
        self.generated_artifacts.append(artifact)

    def add_validation(self, validation: ValidationResult):
        """Adiciona um resultado de validação"""
        self.validation_results.append(validation)

    def add_stage(self, stage: PipelineStage):
        """Adiciona um stage"""
        self.pipeline_stages.append(stage)

    def mark_stage_completed(self, stage_name: str, duration_ms: int):
        """Marca um stage como completado"""
        for stage in self.pipeline_stages:
            if stage.stage_name == stage_name:
                stage.status = StageStatus.COMPLETED
                stage.completed_at = datetime.now()
                stage.duration_ms = duration_ms
                break

    def mark_stage_failed(self, stage_name: str, error_message: str, duration_ms: int):
        """Marca um stage como falho"""
        for stage in self.pipeline_stages:
            if stage.stage_name == stage_name:
                stage.status = StageStatus.FAILED
                stage.completed_at = datetime.now()
                stage.duration_ms = duration_ms
                stage.error_message = error_message
                break

    def calculate_duration(self) -> int:
        """Calcula duração total do pipeline em milissegundos"""
        if self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        else:
            delta = datetime.now() - self.started_at
            return int(delta.total_seconds() * 1000)

    def calculate_quality_score(self) -> float:
        """Calcula score de qualidade geral do pipeline"""
        if not self.generated_artifacts:
            return 0.0

        artifact_scores = [a.calculate_overall_score() for a in self.generated_artifacts]
        return sum(artifact_scores) / len(artifact_scores)

    def has_critical_issues(self) -> bool:
        """Verifica se há issues críticos"""
        return any(vr.has_critical_issues() for vr in self.validation_results)

    def should_require_manual_review(self, auto_approval_threshold: float, min_quality_score: float) -> tuple[bool, Optional[str]]:
        """Determina se requer aprovação manual"""
        quality_score = self.calculate_quality_score()

        # Rejeição automática
        if quality_score < min_quality_score:
            return True, f'Score de qualidade muito baixo: {quality_score:.2f}'

        # Issues críticos bloqueiam
        if self.has_critical_issues():
            return True, 'Issues críticos encontrados em validações'

        # Aprovação automática
        if quality_score >= auto_approval_threshold:
            return False, None

        # Faixa intermediária requer revisão
        return True, f'Score de qualidade requer revisão: {quality_score:.2f}'

    def to_pipeline_result(self, auto_approval_threshold: float, min_quality_score: float) -> PipelineResult:
        """Converte contexto para PipelineResult"""
        requires_review, review_reason = self.should_require_manual_review(
            auto_approval_threshold, min_quality_score
        )

        # Determina status do pipeline
        if self.error:
            status = PipelineStatus.FAILED
        elif requires_review:
            status = PipelineStatus.REQUIRES_REVIEW
        elif all(s.status == StageStatus.COMPLETED for s in self.pipeline_stages):
            status = PipelineStatus.COMPLETED
        else:
            status = PipelineStatus.PARTIAL

        return PipelineResult(
            pipeline_id=self.pipeline_id,
            ticket_id=self.ticket.ticket_id,
            plan_id=self.ticket.plan_id,
            intent_id=self.ticket.intent_id,
            decision_id=self.ticket.decision_id,
            correlation_id=self.ticket.correlation_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
            status=status,
            artifacts=self.generated_artifacts,
            pipeline_stages=self.pipeline_stages,
            total_duration_ms=self.calculate_duration(),
            approval_required=requires_review,
            approval_reason=review_reason,
            error_message=str(self.error) if self.error else None,
            git_mr_url=self.metadata.get('git_mr_url'),
            created_at=self.started_at,
            completed_at=self.completed_at,
            metadata={k: str(v) for k, v in self.metadata.items()},
            schema_version=1
        )

    class Config:
        arbitrary_types_allowed = True
