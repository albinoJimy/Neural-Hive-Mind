"""
Modelo Pydantic para Execution Feedback (contrato canónico do loop OBSERVE→LEARN).

Spec: docs/specs/2026-06-22-fundacao-loop-learn — Fase 0 (Fundação).
Corresponde ao schema Avro schemas/execution-feedback/execution-feedback.avsc.

Contrato capability-agnostic: EXECUTE/GENERATE/MIGRATE traduzem o seu resultado
para este formato. A Fundação manda no formato — nenhuma capacidade o dita.

NOTA: Pydantic v2 (ConfigDict). Timestamps em epoch millis (int), consistente
com o schema ExecutionTicket e com ticket_generation.
"""

from pydantic import BaseModel, ConfigDict, Field


class ExecutionFeedback(BaseModel):
    """Feedback canónico de uma unidade de execução, consumido pelo loop LEARN."""

    # Identidade / auditoria
    feedback_id: str = Field(
        ..., description="Identificador do feedback ({ticket_id}:{millis})"
    )
    feedback_persisted_at: int = Field(..., description="Epoch millis da persistência")

    # Ganchos transversais (Fundação → Roteamento → Capacidades)
    capability: str = Field(
        ..., description="Capacidade emissora: EXECUTE|GENERATE|MIGRATE"
    )
    journey_id: str | None = Field(
        default=None, description="Gancho de Roteamento (journey router); opcional hoje"
    )

    # Correlação
    ticket_id: str | None = Field(
        default=None, description="Chave de update em execution_tickets"
    )
    plan_id: str = Field(..., description="Plano cognitivo de origem")
    trace_id: str | None = Field(
        default=None, description="Correlação OBSERVE (OpenTelemetry)"
    )

    # Sinal de aprendizagem
    status: str = Field(..., description="Estado final do ticket")
    actual_duration_ms: int | None = Field(
        default=None, description="Duração real (label do regressor)"
    )
    started_at: int | None = Field(default=None, description="Início (epoch millis)")
    completed_at: int | None = Field(default=None, description="Fim (epoch millis)")

    # Guarda de qualidade de dados (anti-verde-falso)
    simulated: bool = Field(
        default=False, description="Execução simulada/degradada (excluída do treino)"
    )

    model_config = ConfigDict(extra="forbid")
