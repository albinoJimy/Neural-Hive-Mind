"""
Risk Explainability

Explicabilidade de decisões de risco com SHAP-like values e feature importance.
"""

import structlog
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field
from collections import OrderedDict

from .config import RiskBand, RiskScoringConfig
from .models import RiskAssessment
from neural_hive_domain import UnifiedDomain


logger = structlog.get_logger(__name__)


@dataclass
class FactorContribution:
    """Contribuição de um fator para o score final."""

    name: str
    value: float
    weight: float
    contribution: float  # Contribuição absoluta para o score
    contribution_percentage: float  # Percentual do total
    direction: str  # 'increases_risk', 'decreases_risk', 'neutral'
    description: str

    def to_dict(self) -> Dict:
        """Converte para dicionário."""
        return {
            "name": self.name,
            "value": self.value,
            "weight": self.weight,
            "contribution": self.contribution,
            "contribution_percentage": self.contribution_percentage,
            "direction": self.direction,
            "description": self.description,
        }


@dataclass
class RiskExplanation:
    """Explicação completa de uma avaliação de risco."""

    entity_id: str
    domain: UnifiedDomain
    final_score: float
    final_band: RiskBand
    factors: List[FactorContribution]
    base_score: float  # Score base sem fatores
    total_adjustment: float  # Ajuste total dos fatores
    reasoning: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Converte para dicionário."""
        return {
            "entity_id": self.entity_id,
            "domain": self.domain.value,
            "final_score": self.final_score,
            "final_band": self.final_band.value,
            "base_score": self.base_score,
            "total_adjustment": self.total_adjustment,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat(),
            "factors": [f.to_dict() for f in self.factors],
            "metadata": self.metadata,
        }


@dataclass
class WhatIfScenario:
    """Resultado de análise what-if."""

    scenario_name: str
    modified_factors: Dict[str, float]
    original_score: float
    new_score: float
    score_delta: float
    band_change: Optional[Tuple[RiskBand, RiskBand]]
    impact: str  # 'significant', 'moderate', 'minimal'

    def to_dict(self) -> Dict:
        """Converte para dicionário."""
        return {
            "scenario_name": self.scenario_name,
            "modified_factors": self.modified_factors,
            "original_score": self.original_score,
            "new_score": self.new_score,
            "score_delta": self.score_delta,
            "band_change": [b.value for b in self.band_change] if self.band_change else None,
            "impact": self.impact,
        }


class RiskExplainability:
    """Gerencia explicabilidade de avaliações de risco."""

    def __init__(self, config: RiskScoringConfig):
        """Inicializa serviço de explicabilidade.

        Args:
            config: Configuração do risk scoring
        """
        self.config = config

    def explain_assessment(
        self, assessment: RiskAssessment, entity_id: str, base_score: float = 0.5
    ) -> RiskExplanation:
        """Gera explicação detalhada para avaliação.

        Args:
            assessment: Avaliação de risco
            entity_id: ID da entidade
            base_score: Score base (ponto de partida)

        Returns:
            RiskExplanation com detalhes da decisão
        """
        # Calcular contribuições dos fatores
        factors = self._calculate_factor_contributions(
            assessment.factors, assessment.domain, base_score
        )

        # Calcular ajuste total
        total_adjustment = sum(f.contribution for f in factors)

        # Gerar reasoning
        reasoning = self._generate_detailed_reasoning(
            assessment.score, assessment.band, factors, total_adjustment
        )

        explanation = RiskExplanation(
            entity_id=entity_id,
            domain=assessment.domain,
            final_score=assessment.score,
            final_band=assessment.band,
            factors=factors,
            base_score=base_score,
            total_adjustment=total_adjustment,
            reasoning=reasoning,
        )

        logger.debug(
            "risk_explanation_generated",
            entity_id=entity_id,
            domain=assessment.domain.value,
            score=assessment.score,
        )

        return explanation

    def _calculate_factor_contributions(
        self, factors: Dict[str, float], domain: UnifiedDomain, base_score: float
    ) -> List[FactorContribution]:
        """Calcula contribuição de cada fator.

        Args:
            factors: Dict de fator -> score
            domain: Domínio dos fatores
            base_score: Score base

        Returns:
            Lista de FactorContribution ordenada por importância
        """
        weights = self.config.get_weights(domain)
        contributions = []

        for factor_name, factor_value in factors.items():
            weight = weights.get(factor_name, 0.25)

            # Contribuição = weight * (value - 0.5)
            # Valores > 0.5 aumentam risco, < 0.5 diminuem
            contribution = weight * (factor_value - 0.5)

            # Direção
            if contribution > 0.01:
                direction = "increases_risk"
            elif contribution < -0.01:
                direction = "decreases_risk"
            else:
                direction = "neutral"

            # Descrição
            description = self._get_factor_description(factor_name, factor_value, domain)

            contributions.append(
                FactorContribution(
                    name=factor_name,
                    value=factor_value,
                    weight=weight,
                    contribution=contribution,
                    contribution_percentage=0.0,  # Calculado depois
                    direction=direction,
                    description=description,
                )
            )

        # Calcular percentuais (baseado no valor absoluto total)
        total_abs = sum(abs(c.contribution) for c in contributions)
        if total_abs > 0:
            for c in contributions:
                c.contribution_percentage = (abs(c.contribution) / total_abs) * 100

        # Ordenar por contribuição absoluta
        contributions.sort(key=lambda x: abs(x.contribution), reverse=True)

        return contributions

    def _get_factor_description(
        self, factor_name: str, factor_value: float, domain: UnifiedDomain
    ) -> str:
        """Gera descrição legível do fator."""
        descriptions = {
            # Business factors
            "priority": f"Prioridade {'alta' if factor_value > 0.6 else 'baixa'}",
            "cost": f"Custo estimado {'elevado' if factor_value > 0.6 else 'moderado'}",
            "kpi_alignment": f"Alinhamento com KPIs {'baixo' if factor_value > 0.6 else 'alto'}",
            "complexity": f"Complexidade {'alta' if factor_value > 0.6 else 'baixa'}",
            # Technical factors
            "code_quality": f"Qualidade de código {'baixa' if factor_value > 0.6 else 'boa'}",
            "performance": f"Risco de performance {'alto' if factor_value > 0.6 else 'baixo'}",
            "scalability": f"Escalabilidade {'limitada' if factor_value > 0.6 else 'boa'}",
            "dependencies": f"Dependências {'críticas' if factor_value > 0.6 else 'estáveis'}",
            # Security factors
            "security_level": f"Nível de segurança {'baixo' if factor_value > 0.6 else 'adequado'}",
            "pii_exposure": f"Exposição a PII {'alta' if factor_value > 0.6 else 'baixa'}",
            "authentication": f"Autenticação {'fraca' if factor_value > 0.6 else 'forte'}",
            "encryption": f"Criptografia {'insuficiente' if factor_value > 0.6 else 'adequada'}",
            # Operational factors
            "availability": f"Disponibilidade {'arriscada' if factor_value > 0.6 else 'confiável'}",
            "reliability": f"Confiabilidade {'baixa' if factor_value > 0.6 else 'alta'}",
            "maintainability": f"Manutenibilidade {'difícil' if factor_value > 0.6 else 'fácil'}",
            "observability": f"Observabilidade {'insuficiente' if factor_value > 0.6 else 'boa'}",
            # Compliance factors
            "regulatory": f"Risco regulatório {'alto' if factor_value > 0.6 else 'baixo'}",
            "audit_trail": f"Trilha de auditoria {'incompleta' if factor_value > 0.6 else 'completa'}",
            "data_retention": f"Retenção de dados {'problemática' if factor_value > 0.6 else 'adequada'}",
            "policy_adherence": f"Aderência a políticas {'baixa' if factor_value > 0.6 else 'boa'}",
        }

        return descriptions.get(factor_name, f"Fator {factor_name} = {factor_value:.2f}")

    def _generate_detailed_reasoning(
        self,
        final_score: float,
        final_band: RiskBand,
        factors: List[FactorContribution],
        total_adjustment: float,
    ) -> str:
        """Gera justificativa detalhada."""
        # Top 3 fatores
        top_factors = factors[:3]

        factor_descriptions = []
        for f in top_factors:
            direction_symbol = (
                "↑"
                if f.direction == "increases_risk"
                else ("↓" if f.direction == "decreases_risk" else "→")
            )
            factor_descriptions.append(
                f"{f.name} ({direction_symbol} {abs(f.contribution):.2f}, {f.contribution_percentage:.1f}%)"
            )

        reasoning = (
            f"Score final: {final_score:.2f} ({final_band.value}). "
            f"Ajuste total: {total_adjustment:+.2f}. "
            f"Principais fatores: {', '.join(factor_descriptions)}."
        )

        return reasoning

    def what_if_analysis(
        self,
        assessment: RiskAssessment,
        entity_id: str,
        scenarios: Dict[str, Dict[str, float]],
        base_score: float = 0.5,
    ) -> List[WhatIfScenario]:
        """Realiza análise what-if de cenários.

        Args:
            assessment: Avaliação original
            entity_id: ID da entidade
            scenarios: Dict de nome_do_cenario -> {fator: novo_valor}
            base_score: Score base

        Returns:
            Lista de WhatIfScenario
        """
        results = []

        # Recalcular score original para comparação
        original_score = assessment.score
        original_band = assessment.band

        for scenario_name, modified_factors in scenarios.items():
            # Criar fatores modificados
            new_factors = assessment.factors.copy()
            new_factors.update(modified_factors)

            # Recalcular score
            weights = self.config.get_weights(assessment.domain)

            weighted_sum = 0.0
            total_weight = 0.0

            for factor_name, factor_value in new_factors.items():
                weight = weights.get(factor_name, 0.25)
                weighted_sum += factor_value * weight
                total_weight += weight

            new_score = weighted_sum / total_weight if total_weight > 0 else base_score

            # Nova band
            thresholds = self.config.get_thresholds(assessment.domain)
            if new_score >= thresholds["critical"]:
                new_band = RiskBand.CRITICAL
            elif new_score >= thresholds["high"]:
                new_band = RiskBand.HIGH
            elif new_score >= thresholds["medium"]:
                new_band = RiskBand.MEDIUM
            else:
                new_band = RiskBand.LOW

            # Delta
            score_delta = new_score - original_score

            # Impacto
            if abs(score_delta) >= 0.2:
                impact = "significant"
            elif abs(score_delta) >= 0.1:
                impact = "moderate"
            else:
                impact = "minimal"

            # Mudança de band
            band_change = None
            if new_band != original_band:
                band_change = (original_band, new_band)

            results.append(
                WhatIfScenario(
                    scenario_name=scenario_name,
                    modified_factors=modified_factors,
                    original_score=original_score,
                    new_score=new_score,
                    score_delta=score_delta,
                    band_change=band_change,
                    impact=impact,
                )
            )

        logger.debug(
            "what_if_analysis_completed", entity_id=entity_id, scenarios_count=len(scenarios)
        )

        return results

    def compare_assessments(
        self, assessment1: RiskAssessment, assessment2: RiskAssessment, entity_id: str
    ) -> Dict:
        """Compara duas avaliações da mesma entidade.

        Args:
            assessment1: Primeira avaliação
            assessment2: Segunda avaliação
            entity_id: ID da entidade

        Returns:
            Dict com comparação detalhada
        """
        # Diferença de score
        score_delta = assessment2.score - assessment1.score

        # Comparar fatores
        factor_changes = []
        for factor_name in set(assessment1.factors.keys()) | set(assessment2.factors.keys()):
            value1 = assessment1.factors.get(factor_name, 0.5)
            value2 = assessment2.factors.get(factor_name, 0.5)
            delta = value2 - value1

            if abs(delta) > 0.01:  # Mudança significativa
                factor_changes.append(
                    {
                        "factor": factor_name,
                        "from": value1,
                        "to": value2,
                        "delta": delta,
                        "direction": "increased"
                        if delta > 0
                        else ("decreased" if delta < 0 else "unchanged"),
                    }
                )

        # Ordenar por magnitude da mudança
        factor_changes.sort(key=lambda x: abs(x["delta"]), reverse=True)

        # Mudança de band
        band_changed = assessment1.band != assessment2.band

        return {
            "entity_id": entity_id,
            "domain1": assessment1.domain.value,
            "domain2": assessment2.domain.value,
            "score1": assessment1.score,
            "score2": assessment2.score,
            "score_delta": score_delta,
            "band1": assessment1.band.value,
            "band2": assessment2.band.value,
            "band_changed": band_changed,
            "factor_changes": factor_changes,
            "timestamp1": assessment1.assessed_at.isoformat() if assessment1.assessed_at else None,
            "timestamp2": assessment2.assessed_at.isoformat() if assessment2.assessed_at else None,
        }

    def get_feature_importance(self, domain: UnifiedDomain) -> List[Tuple[str, float]]:
        """Retorna importância de features por domínio.

        Args:
            domain: Domínio de análise

        Returns:
            Lista de (feature, weight) ordenada por peso
        """
        weights = self.config.get_weights(domain)
        sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        return sorted_weights

    def generate_recommendations(self, explanation: RiskExplanation) -> List[str]:
        """Gera recomendações baseado na explicação.

        Args:
            explanation: Explicação da avaliação

        Returns:
            Lista de recomendações
        """
        recommendations = []

        # Analisar fatores que mais aumentam risco
        risk_increasing = [f for f in explanation.factors if f.direction == "increases_risk"]

        for factor in risk_increasing[:3]:  # Top 3
            if factor.contribution > 0.1:
                recommendation = self._get_recommendation_for_factor(
                    factor.name, factor.value, explanation.domain
                )
                if recommendation:
                    recommendations.append(recommendation)

        # Recomendação baseada na band
        if explanation.final_band == RiskBand.CRITICAL:
            recommendations.append(
                "Risco crítico detectado. Revisão urgente recomendada antes da execução."
            )
        elif explanation.final_band == RiskBand.HIGH:
            recommendations.append(
                "Risco alto identificado. Considere mitigação antes de prosseguir."
            )

        return recommendations

    def _get_recommendation_for_factor(
        self, factor_name: str, factor_value: float, domain: UnifiedDomain
    ) -> Optional[str]:
        """Retorna recomendação específica para um fator."""
        recommendations = {
            "priority": "Reavalie a prioridade desta ação. Consere adiar ou escalar.",
            "cost": "Revise estimativas de custo. Considere abordagem mais econômica.",
            "complexity": "Simplifique a abordagem para reduzir complexidade.",
            "code_quality": "Realize refactoring e code review antes de prosseguir.",
            "performance": "Adicione testes de carga e otimizações de performance.",
            "scalability": "Revise arquitetura para garantir escalabilidade.",
            "dependencies": "Audite dependências e considere alternatives mais estáveis.",
            "security_level": "Revise controles de segurança e adicione camadas de proteção.",
            "pii_exposure": "Minimize exposição a dados sensíveis. Revista políticas de privacidade.",
            "authentication": "Fortaleça mecanismos de autenticação (MFA, etc.).",
            "encryption": "Implemente criptografia em repouso e em trânsito.",
            "availability": "Adicione redundância e failover para garantir disponibilidade.",
            "observability": "Melhore logs, métricas e tracing para melhor observabilidade.",
            "regulatory": "Assegure conformidade com regulamentações aplicáveis.",
            "audit_trail": "Implemente trilha de auditoria completa.",
        }

        return recommendations.get(factor_name)

    def create_summary_report(self, explanation: RiskExplanation) -> str:
        """Cria relatório resumido em formato legível.

        Args:
            explanation: Explicação da avaliação

        Returns:
            String com relatório formatado
        """
        lines = [
            f"=== RELATÓRIO DE AVALIAÇÃO DE RISCO ===",
            f"",
            f"Entidade: {explanation.entity_id}",
            f"Domínio: {explanation.domain.value}",
            f"Score Final: {explanation.final_score:.2f} / 1.00",
            f"Classificação: {explanation.final_band.value.upper()}",
            f"",
            f"--- Fatores de Risco ---",
        ]

        for factor in explanation.factors:
            direction_symbol = (
                "↑"
                if factor.direction == "increases_risk"
                else ("↓" if factor.direction == "decreases_risk" else "→")
            )
            lines.append(
                f"  {direction_symbol} {factor.name}: {factor.value:.2f} "
                f"(peso={factor.weight:.2f}, contribuição={factor.contribution:+.2f})"
            )

        lines.append("")
        lines.append("--- Recomendações ---")

        recommendations = self.generate_recommendations(explanation)
        if recommendations:
            for rec in recommendations:
                lines.append(f"  • {rec}")
        else:
            lines.append("  Nenhuma recomendação específica.")

        lines.append("")
        lines.append(f"--- Justificativa ---")
        lines.append(explanation.reasoning)

        return "\n".join(lines)
