from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from uuid import uuid4


class ConflictDomain(str, Enum):
    """Domínios de conflito"""
    BUSINESS_VS_TECHNICAL = "BUSINESS_VS_TECHNICAL"
    SECURITY_VS_PERFORMANCE = "SECURITY_VS_PERFORMANCE"
    COST_VS_QUALITY = "COST_VS_QUALITY"
    SPEED_VS_RELIABILITY = "SPEED_VS_RELIABILITY"


class Conflict(BaseModel):
    """Representa um conflito entre domínios"""

    conflict_id: str = Field(default_factory=lambda: str(uuid4()), description="ID único do conflito")
    conflict_domain: ConflictDomain = Field(..., description="Domínio do conflito")

    entities: List[Dict[str, Any]] = Field(default_factory=list, description="Entidades em conflito")
    severity: float = Field(0.0, ge=0.0, le=1.0, description="Severidade do conflito")

    detected_at: datetime = Field(default_factory=datetime.now, description="Quando foi detectado")
    context: Dict[str, Any] = Field(default_factory=dict, description="Contexto adicional")

    def calculate_severity(self) -> float:
        """Calcular severidade baseado em divergência de scores"""
        if len(self.entities) < 2:
            return 0.0

        # Extrair scores das entidades
        scores = []
        for entity in self.entities:
            if 'confidence_score' in entity:
                scores.append(entity['confidence_score'])
            elif 'aggregated_confidence' in entity:
                scores.append(entity['aggregated_confidence'])

        if len(scores) < 2:
            return 0.0

        # Calcular divergência (desvio padrão normalizado)
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5

        # Normalizar severidade (0-1)
        severity = min(std_dev * 2, 1.0)

        self.severity = severity
        return severity

    def suggest_resolution(self) -> str:
        """Sugerir estratégia de resolução"""
        if self.conflict_domain == ConflictDomain.SECURITY_VS_PERFORMANCE:
            return "PRIORITIZE_SECURITY" if self.severity > 0.7 else "COMPROMISE"

        elif self.conflict_domain == ConflictDomain.BUSINESS_VS_TECHNICAL:
            return "PRIORITIZE_BUSINESS" if self.severity < 0.5 else "COMPROMISE"

        elif self.conflict_domain == ConflictDomain.COST_VS_QUALITY:
            return "COMPROMISE"

        elif self.conflict_domain == ConflictDomain.SPEED_VS_RELIABILITY:
            return "PRIORITIZE_RELIABILITY" if self.severity > 0.6 else "COMPROMISE"

        return "ESCALATE_HUMAN"


class ConflictResolution(BaseModel):
    """Resolução de um conflito"""

    conflict_id: str = Field(..., description="ID do conflito")
    resolution_strategy: str = Field(..., description="Estratégia de resolução")

    chosen_entity: Optional[str] = Field(None, description="Entidade escolhida")
    rationale: str = Field(..., description="Justificativa da resolução")

    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança na resolução")
    resolved_at: datetime = Field(default_factory=datetime.now, description="Quando foi resolvido")
