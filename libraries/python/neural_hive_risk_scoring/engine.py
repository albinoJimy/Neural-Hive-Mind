"""
Risk Scoring Engine

Motor de avaliação de risco multi-domínio reutilizável.
Extraído e generalizado de services/semantic-translation-engine/src/services/risk_scorer.py.
"""

import structlog
from datetime import datetime
from typing import Dict, Any
from prometheus_client import Counter, Histogram

from .config import RiskBand, RiskScoringConfig
from neural_hive_domain import UnifiedDomain
from .models import RiskAssessment

logger = structlog.get_logger(__name__)


class RiskScoringMetrics:
    """Métricas Prometheus para risk scoring."""

    def __init__(self):
        try:
            self.risk_scores = Histogram(
                'neural_hive_risk_score',
                'Risk scores distribuídos',
                ['domain']
            )
        except ValueError:
            # Metrics já registradas (múltiplos workers ou reload)
            from prometheus_client import REGISTRY
            self.risk_scores = REGISTRY._names_to_collectors.get('neural_hive_risk_score')

        try:
            self.assessments_total = Counter(
                'neural_hive_risk_assessments_total',
                'Total de avaliações de risco',
                ['domain', 'risk_band']
            )
        except ValueError:
            # Metrics já registradas
            from prometheus_client import REGISTRY
            self.assessments_total = REGISTRY._names_to_collectors.get('neural_hive_risk_assessments_total')

    def observe_risk_score(self, score: float, domain: str):
        """Registra score de risco."""
        self.risk_scores.labels(domain=domain).observe(score)

    def increment_assessments(self, domain: str, risk_band: str):
        """Incrementa contador de avaliações."""
        self.assessments_total.labels(domain=domain, risk_band=risk_band).inc()


class RiskScoringEngine:
    """Motor de avaliação de risco multi-domínio."""

    def __init__(self, config: RiskScoringConfig):
        self.config = config
        self.domain_weights = self._load_domain_weights()
        self.metrics = RiskScoringMetrics()

    def _load_domain_weights(self) -> Dict[str, Dict[str, float]]:
        """Carrega pesos de domínios da configuração."""
        return {
            UnifiedDomain.BUSINESS.value: self.config.business_weights,
            UnifiedDomain.TECHNICAL.value: self.config.technical_weights,
            UnifiedDomain.SECURITY.value: self.config.security_weights,
            UnifiedDomain.OPERATIONAL.value: self.config.operational_weights,
            UnifiedDomain.COMPLIANCE.value: self.config.compliance_weights,
        }

    def score(self, entity: Dict[str, Any], domain: UnifiedDomain) -> RiskAssessment:
        """Calcula score de risco para entidade.

        Args:
            entity: Entidade a avaliar (plan, decision, execution)
            domain: Domínio de avaliação

        Returns:
            RiskAssessment com score, band, factors
        """
        # Calcular fatores individuais por domínio
        factors = self._calculate_factors(entity, domain)

        # Calcular score ponderado
        risk_score = self._calculate_weighted_score(factors, domain)

        # Classificar em risk band
        risk_band = self._classify_risk_band(risk_score, domain)

        # Gerar justificativa
        reasoning = self._generate_reasoning(factors, risk_score, risk_band)

        # Métricas
        self.metrics.observe_risk_score(risk_score, domain.value)
        self.metrics.increment_assessments(domain.value, risk_band.value)

        logger.info(
            "risk_assessment_completed",
            domain=domain.value,
            risk_score=risk_score,
            risk_band=risk_band.value,
            entity_id=entity.get('id', 'unknown')
        )

        return RiskAssessment(
            score=risk_score,
            band=risk_band,
            factors=factors,
            reasoning=reasoning,
            domain=domain,
            assessed_at=datetime.utcnow()
        )

    def _calculate_factors(self, entity: Dict, domain: UnifiedDomain) -> Dict[str, float]:
        """Calcula fatores de risco por domínio."""
        if domain == UnifiedDomain.BUSINESS:
            return self._calculate_business_factors(entity)
        elif domain == UnifiedDomain.TECHNICAL:
            return self._calculate_technical_factors(entity)
        elif domain == UnifiedDomain.SECURITY:
            return self._calculate_security_factors(entity)
        elif domain == UnifiedDomain.OPERATIONAL:
            return self._calculate_operational_factors(entity)
        elif domain == UnifiedDomain.COMPLIANCE:
            return self._calculate_compliance_factors(entity)
        else:
            return {}

    def _calculate_business_factors(self, entity: Dict) -> Dict[str, float]:
        """Fatores de risco de negócio."""
        return {
            'priority': self._map_priority_to_risk(entity.get('priority', 'normal')),
            'cost': self._calculate_cost_risk(entity),
            'kpi_alignment': self._calculate_kpi_risk(entity),
            'complexity': self._calculate_complexity_risk(entity)
        }

    def _calculate_technical_factors(self, entity: Dict) -> Dict[str, float]:
        """Fatores de risco técnico."""
        return {
            'code_quality': self._calculate_code_quality_risk(entity),
            'performance': self._calculate_performance_risk(entity),
            'scalability': self._calculate_scalability_risk(entity),
            'dependencies': self._calculate_dependency_risk(entity)
        }

    def _calculate_security_factors(self, entity: Dict) -> Dict[str, float]:
        """Fatores de risco de segurança."""
        return {
            'security_level': self._map_security_level_to_risk(entity.get('security_level', 'internal')),
            'pii_exposure': self._calculate_pii_risk(entity),
            'authentication': self._calculate_auth_risk(entity),
            'encryption': self._calculate_encryption_risk(entity)
        }

    def _calculate_operational_factors(self, entity: Dict) -> Dict[str, float]:
        """Fatores de risco operacional."""
        return {
            'availability': self._calculate_availability_risk(entity),
            'reliability': self._calculate_reliability_risk(entity),
            'maintainability': self._calculate_maintainability_risk(entity),
            'observability': self._calculate_observability_risk(entity)
        }

    def _calculate_compliance_factors(self, entity: Dict) -> Dict[str, float]:
        """Fatores de risco de compliance."""
        return {
            'regulatory': self._calculate_regulatory_risk(entity),
            'audit_trail': self._calculate_audit_risk(entity),
            'data_retention': self._calculate_retention_risk(entity),
            'policy_adherence': self._calculate_policy_risk(entity)
        }

    def _calculate_weighted_score(self, factors: Dict[str, float], domain: UnifiedDomain) -> float:
        """Calcula score ponderado."""
        weights = self.domain_weights.get(domain.value, {})

        total_weight = 0.0
        weighted_sum = 0.0

        for factor_name, factor_score in factors.items():
            weight = weights.get(factor_name, 1.0 / len(factors))
            weighted_sum += factor_score * weight
            total_weight += weight

        # Normalizar
        risk_score = weighted_sum / total_weight if total_weight > 0 else 0.5
        return max(0.0, min(1.0, risk_score))

    def _classify_risk_band(self, risk_score: float, domain: UnifiedDomain) -> RiskBand:
        """Classifica score em risk band."""
        thresholds = self.config.get_thresholds(domain)

        if risk_score >= thresholds['critical']:
            return RiskBand.CRITICAL
        elif risk_score >= thresholds['high']:
            return RiskBand.HIGH
        elif risk_score >= thresholds['medium']:
            return RiskBand.MEDIUM
        else:
            return RiskBand.LOW

    def _generate_reasoning(self, factors: Dict[str, float], risk_score: float, risk_band: RiskBand) -> str:
        """Gera justificativa da avaliação."""
        top_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)[:3]
        factor_desc = ", ".join([f"{name} ({score:.2f})" for name, score in top_factors])
        return f"Risk score {risk_score:.2f} ({risk_band.value}). Fatores principais: {factor_desc}"

    # Heurísticas específicas (simplificadas - expandir conforme necessário)

    def _map_priority_to_risk(self, priority: str) -> float:
        mapping = {'low': 0.2, 'normal': 0.4, 'high': 0.7, 'critical': 0.9}
        return mapping.get(priority, 0.5)

    def _map_security_level_to_risk(self, level: str) -> float:
        mapping = {'public': 0.9, 'internal': 0.5, 'confidential': 0.3, 'restricted': 0.1}
        return mapping.get(level, 0.5)

    def _calculate_cost_risk(self, entity: Dict) -> float:
        cost = entity.get('estimated_cost', 0)
        if cost > 100000:
            return 0.9
        elif cost > 50000:
            return 0.7
        elif cost > 10000:
            return 0.4
        else:
            return 0.2

    def _calculate_kpi_risk(self, entity: Dict) -> float:
        # Placeholder: avaliar alinhamento com KPIs
        return 0.3

    def _calculate_complexity_risk(self, entity: Dict) -> float:
        complexity = entity.get('complexity', 'medium')
        mapping = {'low': 0.2, 'medium': 0.5, 'high': 0.8, 'very_high': 0.95}
        return mapping.get(complexity, 0.5)

    def _calculate_code_quality_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_performance_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_scalability_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_dependency_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_pii_risk(self, entity: Dict) -> float:
        has_pii = entity.get('handles_pii', False)
        return 0.8 if has_pii else 0.2

    def _calculate_auth_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_encryption_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_availability_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_reliability_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_maintainability_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_observability_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_regulatory_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_audit_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_retention_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3

    def _calculate_policy_risk(self, entity: Dict) -> float:
        # Placeholder
        return 0.3
