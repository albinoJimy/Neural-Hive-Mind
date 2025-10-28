"""
Risk Scoring Configuration

Configuração Pydantic para motor de risk scoring multi-domínio.
"""

from pydantic import BaseModel, Field
from typing import Dict
from enum import Enum


class RiskDomain(str, Enum):
    """Domínios de avaliação de risco."""
    BUSINESS = 'business'
    TECHNICAL = 'technical'
    SECURITY = 'security'
    OPERATIONAL = 'operational'
    COMPLIANCE = 'compliance'


class RiskBand(str, Enum):
    """Classificação de risco."""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class RiskScoringConfig(BaseModel):
    """Configuração do motor de risk scoring."""

    # Thresholds por domínio
    business_thresholds: Dict[str, float] = Field(
        default={'medium': 0.4, 'high': 0.7, 'critical': 0.9}
    )
    technical_thresholds: Dict[str, float] = Field(
        default={'medium': 0.4, 'high': 0.7, 'critical': 0.9}
    )
    security_thresholds: Dict[str, float] = Field(
        default={'medium': 0.3, 'high': 0.6, 'critical': 0.8}  # Mais rigoroso
    )
    operational_thresholds: Dict[str, float] = Field(
        default={'medium': 0.4, 'high': 0.7, 'critical': 0.9}
    )
    compliance_thresholds: Dict[str, float] = Field(
        default={'medium': 0.3, 'high': 0.6, 'critical': 0.8}  # Mais rigoroso
    )

    # Pesos por domínio e fator
    business_weights: Dict[str, float] = Field(
        default={'priority': 0.3, 'cost': 0.3, 'kpi_alignment': 0.2, 'complexity': 0.2}
    )
    technical_weights: Dict[str, float] = Field(
        default={'code_quality': 0.25, 'performance': 0.25, 'scalability': 0.25, 'dependencies': 0.25}
    )
    security_weights: Dict[str, float] = Field(
        default={'security_level': 0.4, 'pii_exposure': 0.3, 'authentication': 0.2, 'encryption': 0.1}
    )
    operational_weights: Dict[str, float] = Field(
        default={'availability': 0.3, 'reliability': 0.3, 'maintainability': 0.2, 'observability': 0.2}
    )
    compliance_weights: Dict[str, float] = Field(
        default={'regulatory': 0.4, 'audit_trail': 0.3, 'data_retention': 0.2, 'policy_adherence': 0.1}
    )

    def get_thresholds(self, domain: RiskDomain) -> Dict[str, float]:
        """Retorna thresholds para domínio."""
        mapping = {
            RiskDomain.BUSINESS: self.business_thresholds,
            RiskDomain.TECHNICAL: self.technical_thresholds,
            RiskDomain.SECURITY: self.security_thresholds,
            RiskDomain.OPERATIONAL: self.operational_thresholds,
            RiskDomain.COMPLIANCE: self.compliance_thresholds
        }
        return mapping.get(domain, self.business_thresholds)

    def get_weights(self, domain: RiskDomain) -> Dict[str, float]:
        """Retorna pesos para domínio."""
        mapping = {
            RiskDomain.BUSINESS: self.business_weights,
            RiskDomain.TECHNICAL: self.technical_weights,
            RiskDomain.SECURITY: self.security_weights,
            RiskDomain.OPERATIONAL: self.operational_weights,
            RiskDomain.COMPLIANCE: self.compliance_weights
        }
        return mapping.get(domain, self.business_weights)
