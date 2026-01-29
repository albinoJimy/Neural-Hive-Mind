"""
SemanticPipeline: Pipeline completo de avaliação semântica.

Orquestra SemanticAnalyzer, OntologyBasedEvaluator e FeatureExtractor
para fornecer avaliação 100% semântica sem string-match.
"""

from typing import Dict, List, Any, Optional
import structlog

from .semantic_analyzer import SemanticAnalyzer
from .ontology_evaluator import OntologyBasedEvaluator
from ..feature_extraction.feature_extractor import FeatureExtractor

logger = structlog.get_logger(__name__)


class SemanticPipeline:
    """Pipeline completo de avaliação semântica."""

    def __init__(self, config: Dict[str, Any], feature_extractor: FeatureExtractor):
        """
        Inicializa pipeline semântico.

        Args:
            config: Configuração do especialista
            feature_extractor: Extrator de features estruturadas
        """
        self.config = config
        self.feature_extractor = feature_extractor

        # Inicializar componentes
        self.semantic_analyzer = SemanticAnalyzer(config)
        self.ontology_evaluator = OntologyBasedEvaluator(config)

        # Pesos configuráveis para combinar análises
        self.semantic_weight = config.get("semantic_analysis_weight", 0.6)
        self.ontology_weight = config.get("ontology_analysis_weight", 0.4)

        logger.info(
            "SemanticPipeline initialized",
            semantic_weight=self.semantic_weight,
            ontology_weight=self.ontology_weight,
        )

    def evaluate_plan(
        self, cognitive_plan: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Avalia plano cognitivo usando pipeline semântico completo.

        Args:
            cognitive_plan: Plano cognitivo a avaliar
            context: Contexto adicional

        Returns:
            Dicionário com resultado da avaliação
        """
        try:
            logger.info(
                "Starting semantic evaluation", plan_id=cognitive_plan.get("plan_id")
            )

            # Extrair features estruturadas
            features_result = self.feature_extractor.extract_features(cognitive_plan)
            extracted_features = features_result

            tasks = cognitive_plan.get("tasks", [])

            # === Análise Semântica (baseada em embeddings) ===

            semantic_security = self.semantic_analyzer.analyze_security(tasks)
            semantic_architecture = self.semantic_analyzer.analyze_architecture(tasks)
            semantic_performance = self.semantic_analyzer.analyze_performance(tasks)
            semantic_quality = self.semantic_analyzer.analyze_code_quality(tasks)

            # === Análise Ontológica (baseada em conhecimento) ===

            ontology_security = self.ontology_evaluator.evaluate_security_level(
                cognitive_plan, extracted_features
            )

            ontology_architecture = (
                self.ontology_evaluator.evaluate_architecture_compliance(
                    cognitive_plan, extracted_features
                )
            )

            # Avaliar complexidade e risco via ontologia
            complexity_score = self.ontology_evaluator.evaluate_complexity(
                cognitive_plan, extracted_features
            )

            risk_patterns_score = self.ontology_evaluator.evaluate_risk_patterns(
                cognitive_plan, extracted_features
            )

            # === Combinar Scores Semânticos e Ontológicos ===

            security_score = (
                semantic_security * self.semantic_weight
                + ontology_security * self.ontology_weight
            )

            architecture_score = (
                semantic_architecture * self.semantic_weight
                + ontology_architecture * self.ontology_weight
            )

            # Performance e Quality usam apenas análise semântica
            performance_score = semantic_performance
            quality_score = semantic_quality

            # === Calcular Scores Finais ===

            # Confidence: média ponderada dos aspectos positivos
            confidence_score = (
                security_score * 0.3
                + architecture_score * 0.3
                + performance_score * 0.2
                + quality_score * 0.2
            )

            # Risk: combinar complexidade + risk_patterns + inverso dos scores
            base_risk = 1.0 - confidence_score
            risk_score = (
                base_risk * 0.4 + complexity_score * 0.3 + risk_patterns_score * 0.3
            )

            # === Determinar Recomendação ===

            domain = extracted_features.get("metadata_features", {}).get(
                "domain", "unknown"
            )

            recommendation = self.ontology_evaluator.get_domain_recommendations(
                domain, risk_score, confidence_score
            )

            # === Gerar Reasoning ===

            reasoning_summary = self._generate_reasoning(
                security_score,
                architecture_score,
                performance_score,
                quality_score,
                risk_score,
                confidence_score,
                recommendation,
            )

            # === Fatores de Raciocínio Estruturados ===

            reasoning_factors = [
                {
                    "factor_name": "semantic_security_analysis",
                    "weight": 0.3,
                    "score": security_score,
                    "description": f"Análise semântica de segurança (sem={semantic_security:.2f}, onto={ontology_security:.2f})",
                },
                {
                    "factor_name": "semantic_architecture_analysis",
                    "weight": 0.3,
                    "score": architecture_score,
                    "description": f"Análise semântica de arquitetura (sem={semantic_architecture:.2f}, onto={ontology_architecture:.2f})",
                },
                {
                    "factor_name": "semantic_performance_analysis",
                    "weight": 0.2,
                    "score": performance_score,
                    "description": f"Análise semântica de performance",
                },
                {
                    "factor_name": "semantic_quality_analysis",
                    "weight": 0.2,
                    "score": quality_score,
                    "description": f"Análise semântica de qualidade",
                },
                {
                    "factor_name": "complexity_evaluation",
                    "weight": 0.15,
                    "score": complexity_score,
                    "description": f"Complexidade baseada em ontologia",
                },
                {
                    "factor_name": "risk_patterns",
                    "weight": 0.15,
                    "score": risk_patterns_score,
                    "description": f"Padrões de risco identificados",
                },
            ]

            # === Sugestões de Mitigação ===

            mitigations = self._generate_mitigations(
                security_score, architecture_score, performance_score, quality_score
            )

            # === Resultado Final ===

            result = {
                "confidence_score": float(max(0.0, min(1.0, confidence_score))),
                "risk_score": float(max(0.0, min(1.0, risk_score))),
                "recommendation": recommendation,
                "reasoning_summary": reasoning_summary,
                "reasoning_factors": reasoning_factors,
                "mitigations": mitigations,
                "metadata": {
                    "evaluation_method": "semantic_pipeline",
                    "semantic_weight": self.semantic_weight,
                    "ontology_weight": self.ontology_weight,
                    "domain": domain,
                    "complexity_score": complexity_score,
                    "risk_patterns_score": risk_patterns_score,
                    "num_tasks": len(tasks),
                    "semantic_scores": {
                        "security": semantic_security,
                        "architecture": semantic_architecture,
                        "performance": semantic_performance,
                        "quality": semantic_quality,
                    },
                    "ontology_scores": {
                        "security": ontology_security,
                        "architecture": ontology_architecture,
                    },
                },
            }

            logger.info(
                "Semantic evaluation completed",
                plan_id=cognitive_plan.get("plan_id"),
                confidence=confidence_score,
                risk=risk_score,
                recommendation=recommendation,
            )

            return result

        except Exception as e:
            logger.error(
                "Semantic evaluation failed",
                plan_id=cognitive_plan.get("plan_id"),
                error=str(e),
                exc_info=True,
            )

            # Fallback para avaliação neutra
            return {
                "confidence_score": 0.5,
                "risk_score": 0.5,
                "recommendation": "review_required",
                "reasoning_summary": f"Avaliação semântica falhou: {str(e)}",
                "reasoning_factors": [],
                "mitigations": [],
                "metadata": {"evaluation_method": "fallback", "error": str(e)},
            }

    def _generate_reasoning(
        self,
        security_score: float,
        architecture_score: float,
        performance_score: float,
        quality_score: float,
        risk_score: float,
        confidence_score: float,
        recommendation: str,
    ) -> str:
        """Gera narrativa de raciocínio."""
        return (
            f"Avaliação semântica completa: "
            f"confiança={confidence_score:.2f}, risco={risk_score:.2f}. "
            f"Análises - segurança={security_score:.2f}, "
            f"arquitetura={architecture_score:.2f}, "
            f"performance={performance_score:.2f}, "
            f"qualidade={quality_score:.2f}. "
            f"Recomendação: {recommendation}."
        )

    def _generate_mitigations(
        self,
        security_score: float,
        architecture_score: float,
        performance_score: float,
        quality_score: float,
    ) -> List[Dict[str, Any]]:
        """Gera sugestões de mitigação."""
        mitigations = []

        if security_score < 0.6:
            mitigations.append(
                {
                    "mitigation_type": "security_improvement",
                    "description": "Reforçar práticas de segurança detectadas por análise semântica",
                    "priority": "high",
                    "estimated_effort": "2-3 dias",
                }
            )

        if architecture_score < 0.6:
            mitigations.append(
                {
                    "mitigation_type": "architecture_refactoring",
                    "description": "Melhorar padrões arquiteturais identificados semanticamente",
                    "priority": "medium",
                    "estimated_effort": "3-5 dias",
                }
            )

        if performance_score < 0.6:
            mitigations.append(
                {
                    "mitigation_type": "performance_optimization",
                    "description": "Otimizar aspectos de performance via análise semântica",
                    "priority": "medium",
                    "estimated_effort": "1-2 dias",
                }
            )

        if quality_score < 0.6:
            mitigations.append(
                {
                    "mitigation_type": "quality_enhancement",
                    "description": "Elevar qualidade de código conforme análise semântica",
                    "priority": "low",
                    "estimated_effort": "2-3 dias",
                }
            )

        return mitigations
