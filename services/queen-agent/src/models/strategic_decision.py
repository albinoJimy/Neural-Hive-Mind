import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from uuid import uuid4


class DecisionType(str, Enum):
    """Tipos de decisões estratégicas"""
    PRIORITIZATION = "PRIORITIZATION"
    CONFLICT_RESOLUTION = "CONFLICT_RESOLUTION"
    REPLANNING = "REPLANNING"
    EXCEPTION_APPROVAL = "EXCEPTION_APPROVAL"
    QOS_ADJUSTMENT = "QOS_ADJUSTMENT"
    RESOURCE_REALLOCATION = "RESOURCE_REALLOCATION"


class TriggeredBy(BaseModel):
    """Informações sobre o que acionou a decisão"""
    event_type: str = Field(..., description="Tipo de evento que acionou a decisão")
    source_id: str = Field(..., description="ID da fonte que acionou")
    timestamp: int = Field(..., description="Timestamp do evento")


class DecisionContext(BaseModel):
    """Contexto estratégico no momento da decisão"""
    active_plans: List[str] = Field(default_factory=list, description="IDs dos planos ativos")
    critical_incidents: List[str] = Field(default_factory=list, description="IDs de incidentes críticos")
    sla_violations: List[str] = Field(default_factory=list, description="IDs de violações de SLA")
    resource_saturation: float = Field(0.0, description="Percentual de saturação de recursos")


class DecisionAnalysis(BaseModel):
    """Análise realizada para a decisão"""
    neo4j_query_results: Dict[str, Any] = Field(default_factory=dict, description="Resultados de queries Neo4j")
    pheromone_signals: Dict[str, float] = Field(default_factory=dict, description="Sinais de feromônios")
    metrics_snapshot: Dict[str, float] = Field(default_factory=dict, description="Snapshot de métricas")
    conflict_domains: List[str] = Field(default_factory=list, description="Domínios em conflito")


class DecisionAction(BaseModel):
    """Decisão tomada e ação recomendada"""
    action: str = Field(..., description="Ação a ser tomada")
    target_entities: List[str] = Field(default_factory=list, description="IDs das entidades alvo")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parâmetros da ação")
    rationale: str = Field(..., description="Justificativa da decisão")


class RiskAssessment(BaseModel):
    """Avaliação de risco da decisão"""
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Score de risco")
    risk_factors: List[str] = Field(default_factory=list, description="Fatores de risco")
    mitigations: List[str] = Field(default_factory=list, description="Mitigações recomendadas")


class ActionTaken(BaseModel):
    """Ação executada"""
    action_type: str = Field(..., description="Tipo de ação")
    target_service: str = Field(..., description="Serviço alvo")
    status: str = Field(..., description="Status da execução")
    timestamp: int = Field(..., description="Timestamp da execução")


class StrategicDecision(BaseModel):
    """Decisão estratégica do Queen Agent"""

    decision_id: str = Field(default_factory=lambda: str(uuid4()), description="ID único da decisão")
    decision_type: DecisionType = Field(..., description="Tipo de decisão")
    correlation_id: str = Field(default_factory=lambda: str(uuid4()), description="ID de correlação")
    trace_id: str = Field(default_factory=str, description="Trace ID OpenTelemetry")
    span_id: str = Field(default_factory=str, description="Span ID OpenTelemetry")

    triggered_by: TriggeredBy = Field(..., description="O que acionou a decisão")
    context: DecisionContext = Field(default_factory=DecisionContext, description="Contexto estratégico")
    analysis: DecisionAnalysis = Field(default_factory=DecisionAnalysis, description="Análise realizada")
    decision: DecisionAction = Field(..., description="Decisão tomada")

    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confiança na decisão")
    risk_assessment: RiskAssessment = Field(..., description="Avaliação de risco")

    guardrails_validated: List[str] = Field(default_factory=list, description="Guardrails validados")
    actions_taken: List[ActionTaken] = Field(default_factory=list, description="Ações executadas")

    explainability_token: str = Field(default_factory=lambda: str(uuid4()), description="Token de explicabilidade")
    reasoning_summary: str = Field(..., description="Resumo da lógica de decisão")

    created_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000), description="Timestamp de criação")
    expires_at: int = Field(..., description="Timestamp de expiração")

    hash: str = Field(default_factory=str, description="Hash SHA-256 para integridade")
    schema_version: int = Field(default=1, description="Versão do schema")

    def to_avro_dict(self) -> Dict[str, Any]:
        """Serializar para dict compatível com Avro"""
        data = self.model_dump()

        # Converter enums para strings
        data['decision_type'] = self.decision_type.value

        # Converter nested objects
        data['triggered_by'] = self.triggered_by.model_dump()
        data['context'] = self.context.model_dump()
        data['analysis'] = {
            'neo4j_query_results': {k: json.dumps(v) for k, v in self.analysis.neo4j_query_results.items()},
            'pheromone_signals': self.analysis.pheromone_signals,
            'metrics_snapshot': self.analysis.metrics_snapshot,
            'conflict_domains': self.analysis.conflict_domains
        }
        data['decision'] = {
            'action': self.decision.action,
            'target_entities': self.decision.target_entities,
            'parameters': {k: json.dumps(v) for k, v in self.decision.parameters.items()},
            'rationale': self.decision.rationale
        }
        data['risk_assessment'] = self.risk_assessment.model_dump()
        data['actions_taken'] = [action.model_dump() for action in self.actions_taken]

        return data

    @classmethod
    def from_avro_dict(cls, data: Dict[str, Any]) -> 'StrategicDecision':
        """Deserializar de dict Avro"""
        # Converter análise
        if 'analysis' in data:
            data['analysis'] = {
                'neo4j_query_results': {k: json.loads(v) for k, v in data['analysis']['neo4j_query_results'].items()},
                'pheromone_signals': data['analysis']['pheromone_signals'],
                'metrics_snapshot': data['analysis']['metrics_snapshot'],
                'conflict_domains': data['analysis']['conflict_domains']
            }

        # Converter parâmetros da decisão
        if 'decision' in data and 'parameters' in data['decision']:
            data['decision']['parameters'] = {k: json.loads(v) for k, v in data['decision']['parameters'].items()}

        return cls(**data)

    def calculate_hash(self) -> str:
        """Gerar hash SHA-256 para integridade"""
        # Criar representação canônica
        canonical = {
            'decision_id': self.decision_id,
            'decision_type': self.decision_type.value,
            'triggered_by': self.triggered_by.model_dump(),
            'decision': self.decision.model_dump(),
            'created_at': self.created_at
        }

        canonical_str = json.dumps(canonical, sort_keys=True)
        return hashlib.sha256(canonical_str.encode()).hexdigest()

    def is_expired(self) -> bool:
        """Verificar se decisão expirou"""
        current_ts = int(datetime.now().timestamp() * 1000)
        return current_ts > self.expires_at

    def validate_guardrails(self) -> bool:
        """Validar contra lista de guardrails"""
        # TODO: Implementar validação via OPA policies
        return len(self.guardrails_validated) > 0
