import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# UTC timezone
UTC = timezone.utc


class DecisionType(str, Enum):
    """Tipo de decisão consolidada"""

    APPROVE = "approve"
    REJECT = "reject"
    REVIEW_REQUIRED = "review_required"
    CONDITIONAL = "conditional"


class ConsensusMethod(str, Enum):
    """Método de consenso utilizado"""

    BAYESIAN = "bayesian"
    VOTING = "voting"
    UNANIMOUS = "unanimous"
    FALLBACK = "fallback"


class SpecialistVote(BaseModel):
    """Voto individual de um especialista"""

    model_config = ConfigDict(use_enum_values=True)

    specialist_type: str = Field(..., description="Tipo do especialista")
    opinion_id: str = Field(..., description="ID do parecer")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Score de confiança")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Score de risco")
    recommendation: str = Field(..., description="Recomendação do especialista")
    weight: float = Field(..., ge=0.0, le=1.0, description="Peso aplicado no consenso")
    processing_time_ms: int = Field(..., description="Tempo de processamento em ms")

    # Campos hierárquicos (GAPS-03-04)
    seniority_level: str | None = Field(
        default=None,
        description="Nível de senioridade do especialista (trainee, junior, mid_level, senior, expert)",
    )
    seniority_multiplier: float | None = Field(
        default=None,
        ge=0.5,
        le=2.0,
        description="Multiplicador de peso baseado na senioridade (0.5 a 2.0)",
    )

    # Campo de método de decisão (GAPS-03 SPECIALIST-002)
    decision_method: str | None = Field(
        default=None,
        description="Método de decisão: ml, heuristic, hybrid",
    )


class ConsensusMetrics(BaseModel):
    """Métricas do processo de consenso"""

    model_config = ConfigDict(use_enum_values=True)

    divergence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Divergência entre especialistas"
    )
    convergence_time_ms: int = Field(..., description="Tempo para convergir em ms")
    unanimous: bool = Field(..., description="Se houve unanimidade")
    fallback_used: bool = Field(..., description="Se usou fallback determinístico")
    pheromone_strength: float = Field(
        ..., ge=0.0, le=1.0, description="Força do feromônio aplicado"
    )
    bayesian_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confiança Bayesiana agregada"
    )
    voting_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confiança do voting ensemble"
    )

    # Campos hierárquicos (GAPS-03-04)
    weighted_by_seniority: bool = Field(
        default=False, description="Indica se o consenso foi ponderado por senioridade"
    )
    seniority_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Distribuição de votos por nível de senioridade (ex: {senior: 2, expert: 1})",
    )
    consensus_method_hierarchical: bool = Field(
        default=False, description="Indica se o método de consenso hierárquico foi utilizado"
    )


class ConsolidatedDecision(BaseModel):
    """Decisão consolidada do mecanismo de consenso

    NOTA IMPORTANTE sobre Enums:
    Este modelo NÃO usa `use_enum_values=True` para os campos `final_decision` e
    `consensus_method`. Isso garante que esses campos sempre mantenham seus tipos
    enum originais (DecisionType e ConsensusMethod), permitindo acesso seguro a
    `.value` em todo o código.

    Os validadores `coerce_final_decision` e `coerce_consensus_method` garantem
    que strings sejam automaticamente convertidas para os enums correspondentes
    durante a instanciação ou deserialização.

    NOTA sobre correlation_id:
    O ConsensusOrchestrator garante que novas decisões sempre tenham correlation_id
    não-None, gerando UUID fallback quando ausente no plano cognitivo. O tipo
    Optional[str] é mantido para compatibilidade com deserialização de dados legados.

    DECISÃO DE ARQUITETURA (Issue #1 - correlation_id):
    O contrato do Consensus Engine agora garante que correlation_id nunca será None
    ou vazio em decisões publicadas no Kafka. Quando o plano cognitivo não fornece
    correlation_id, um UUID v4 é gerado automaticamente para garantir rastreabilidade
    distribuída end-to-end. Esta decisão foi tomada para evitar falhas de validação
    no Orchestrator Dynamic (FlowCContext) e manter a integridade do tracing.
    """

    decision_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="ID único da decisão"
    )
    plan_id: str = Field(..., description="ID do plano avaliado")
    intent_id: str = Field(..., description="ID da intenção original")
    correlation_id: str | None = Field(
        default=None,
        description="ID de correlação para rastreamento distribuído. "
        "ConsensusOrchestrator garante valor não-None em novas decisões. "
        "None apenas em deserialização de dados legados.",
    )
    trace_id: str | None = Field(default=None, description="Trace ID OpenTelemetry")
    span_id: str | None = Field(default=None, description="Span ID OpenTelemetry")

    # Decisão final - SEM use_enum_values para manter tipo enum
    final_decision: DecisionType = Field(..., description="Decisão consolidada")
    consensus_method: ConsensusMethod = Field(..., description="Método de consenso usado")

    @field_validator("final_decision", mode="before")
    @classmethod
    def coerce_final_decision(cls, v):
        """Garante que final_decision seja sempre um DecisionType enum.

        Aceita tanto strings quanto enums na entrada, sempre retornando o enum.
        Isso resolve o problema de deserialização onde Pydantic pode receber
        uma string do MongoDB/Kafka mas o código espera acessar .value.
        """
        if isinstance(v, str):
            try:
                return DecisionType(v)
            except ValueError:
                # Tenta lookup por nome (ex: 'APPROVE' -> DecisionType.APPROVE)
                return DecisionType[v.upper()]
        return v

    @field_validator("consensus_method", mode="before")
    @classmethod
    def coerce_consensus_method(cls, v):
        """Garante que consensus_method seja sempre um ConsensusMethod enum."""
        if isinstance(v, str):
            try:
                return ConsensusMethod(v)
            except ValueError:
                return ConsensusMethod[v.upper()]
        return v

    # Scores agregados
    aggregated_confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança agregada")
    aggregated_risk: float = Field(..., ge=0.0, le=1.0, description="Risco agregado")

    # Votos dos especialistas
    specialist_votes: list[SpecialistVote] = Field(..., description="Votos individuais")

    # Métricas de consenso
    consensus_metrics: ConsensusMetrics = Field(..., description="Métricas do consenso")

    # Explicabilidade
    explainability_token: str = Field(..., description="Token para explicação consolidada")
    reasoning_summary: str = Field(..., description="Resumo da decisão")

    # Compliance e guardrails
    compliance_checks: dict[str, bool] = Field(
        default_factory=dict, description="Verificações de compliance"
    )
    guardrails_triggered: list[str] = Field(
        default_factory=list, description="Guardrails acionados"
    )
    requires_human_review: bool = Field(default=False, description="Requer revisão humana")

    # Plano cognitivo original (para downstream consumers como Orchestrator)
    cognitive_plan: dict[str, Any] | None = Field(
        default=None, description="Plano cognitivo original que gerou esta decisão"
    )

    # Metadados
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Data de criação")
    valid_until: datetime | None = Field(default=None, description="Validade da decisão")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")

    # Auditoria
    hash: str | None = Field(default=None, description="Hash SHA-256 para integridade")
    schema_version: int = Field(default=1, description="Versão do schema")

    def calculate_hash(self) -> str:
        """Calcula hash SHA-256 para auditoria"""
        data = {
            "decision_id": self.decision_id,
            "plan_id": self.plan_id,
            "final_decision": self.final_decision.value,
            "aggregated_confidence": self.aggregated_confidence,
            "aggregated_risk": self.aggregated_risk,
            "specialist_votes": [v.model_dump(mode="json") for v in self.specialist_votes],
            "created_at": self.created_at.isoformat(),
        }

        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def to_avro_dict(self) -> dict[str, Any]:
        """Converter para formato Avro compatível"""
        # Converter metadata para map<string> (todos valores como string)
        metadata_str = {k: str(v) for k, v in self.metadata.items()}

        return {
            "decision_id": self.decision_id,
            "plan_id": self.plan_id,
            "intent_id": self.intent_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "final_decision": self.final_decision.value,
            "consensus_method": self.consensus_method.value,
            "aggregated_confidence": self.aggregated_confidence,
            "aggregated_risk": self.aggregated_risk,
            "specialist_votes": [
                {
                    "specialist_type": v.specialist_type,
                    "opinion_id": v.opinion_id,
                    "confidence_score": v.confidence_score,
                    "risk_score": v.risk_score,
                    "recommendation": v.recommendation,
                    "weight": v.weight,
                    "processing_time_ms": v.processing_time_ms,
                    "seniority_level": v.seniority_level,
                    "seniority_multiplier": v.seniority_multiplier,
                    "decision_method": v.decision_method,
                }
                for v in self.specialist_votes
            ],
            "consensus_metrics": {
                "divergence_score": self.consensus_metrics.divergence_score,
                "convergence_time_ms": self.consensus_metrics.convergence_time_ms,
                "unanimous": self.consensus_metrics.unanimous,
                "fallback_used": self.consensus_metrics.fallback_used,
                "pheromone_strength": self.consensus_metrics.pheromone_strength,
                "bayesian_confidence": self.consensus_metrics.bayesian_confidence,
                "voting_confidence": self.consensus_metrics.voting_confidence,
                "weighted_by_seniority": self.consensus_metrics.weighted_by_seniority,
                "seniority_distribution": self.consensus_metrics.seniority_distribution,
                "consensus_method_hierarchical": self.consensus_metrics.consensus_method_hierarchical,
            },
            "explainability_token": self.explainability_token,
            "reasoning_summary": self.reasoning_summary,
            "compliance_checks": self.compliance_checks,
            "guardrails_triggered": self.guardrails_triggered,
            "cognitive_plan": json.dumps(self.cognitive_plan, default=str)
            if self.cognitive_plan is not None
            else None,
            "requires_human_review": self.requires_human_review,
            "created_at": int(self.created_at.timestamp() * 1000),
            "valid_until": int(self.valid_until.timestamp() * 1000) if self.valid_until else None,
            "metadata": metadata_str,
            "hash": self.hash,
            "schema_version": self.schema_version,
        }

    model_config = ConfigDict(
        # NÃO usar use_enum_values=True - queremos manter enums como objetos
        # para permitir acesso a .value em todo o código
        validate_assignment=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )
