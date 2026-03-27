"""
Dataset Balance Analyzer - Analisa balanceamento do dataset de feedback.

Identifica classes, confianças e domínios sub-representados para
priorizar coleta de feedback via Active Learning.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from collections import Counter, defaultdict
import structlog

from pydantic import BaseModel, Field

logger = structlog.get_logger()


@dataclass
class PriorityRecommendation:
    """Recomendação de prioridade para coleta de feedback."""

    type: str  # 'class', 'confidence', 'domain'
    value: str  # 'reject', 'low', 'security', etc.
    gap: float  # Gap de representação em pontos percentuais
    reason: str = ""  # Descrição do porquê é prioritário

    def __post_init__(self):
        """Gera razão automaticamente se não fornecida."""
        if not self.reason:
            self.reason = f"{self.value} está sub-representado em {self.gap:.1f}pp"

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "type": self.type,
            "value": self.value,
            "gap": self.gap,
            "reason": self.reason,
        }


class BalanceMetrics(BaseModel):
    """Métricas de balanceamento do dataset."""

    total_feedbacks: int = Field(default=0, description="Total de feedbacks no dataset")
    balance: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Distribuição por classe (approve/reject/review_required)",
    )
    confidence_distribution: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Distribuição por faixa de confiança (low/medium/high)",
    )
    domain_distribution: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Distribuição por domínio NLP"
    )
    semantic_features_count: int = Field(
        default=0, description="Contagem de feedbacks com features semânticas"
    )
    semantic_features_percentage: float = Field(
        default=0.0, description="Porcentagem de feedbacks com features semânticas"
    )
    priority_recommendations: List[Dict[str, Any]] = Field(
        default_factory=list, description="Lista de recomendações de prioridade"
    )
    last_updated: str = Field(
        default="", description="Timestamp da última atualização (ISO format)"
    )


class DatasetBalanceAnalyzer:
    """
    Analisa balanceamento do dataset de feedback.

    Responsável por:
    - Calcular distribuição por classe, confiança e domínio
    - Identificar classes/feature sub-representadas
    - Gerar recomendações de prioridade para coleta
    """

    # Classes alvo para balanceamento (33% cada em cenário ideal)
    TARGET_CLASSES = ["approve", "reject", "review_required"]
    TARGET_BALANCE = 1.0 / 3.0  # ~33.3%

    # Faixas de confiança
    CONFIDENCE_RANGES = {"low": (0.0, 0.3), "medium": (0.3, 0.7), "high": (0.7, 1.0)}

    # Prefixos de features semânticas
    SEMANTIC_PREFIXES = ["semantic_"]

    def __init__(self, collection, target_balance: float = None):
        """
        Inicializa o analyzer.

        Args:
            collection: Coleção MongoDB de specialist_feedback
            target_balance: Balanceamento alvo (padrão: 1/3 para cada classe)
        """
        self.collection = collection
        self.target_balance = target_balance or self.TARGET_BALANCE

        logger.info(
            "DatasetBalanceAnalyzer initialized", target_balance=self.target_balance
        )

    def calculate_balance_metrics(self) -> BalanceMetrics:
        """
        Calcula métricas completas de balanceamento.

        Returns:
            BalanceMetrics com distribuição por classe, confiança e domínio
        """
        total = self._count_total()

        if total == 0:
            return BalanceMetrics(total_feedbacks=0)

        # Calcular distribuições
        class_dist = self._calculate_class_distribution(total)
        confidence_dist = self._calculate_confidence_distribution(total)
        domain_dist = self._calculate_domain_distribution(total)
        semantic_count, semantic_pct = self._calculate_semantic_features_stats(total)

        # Gerar recomendações
        recommendations = self._generate_priority_recommendations(
            class_dist, confidence_dist, domain_dist, total
        )

        metrics = BalanceMetrics(
            total_feedbacks=total,
            balance=class_dist,
            confidence_distribution=confidence_dist,
            domain_distribution=domain_dist,
            semantic_features_count=semantic_count,
            semantic_features_percentage=semantic_pct,
            priority_recommendations=[r.to_dict() for r in recommendations],
        )

        logger.info(
            "Balance metrics calculated",
            total=total,
            semantic_pct=semantic_pct,
            recommendations_count=len(recommendations),
        )

        return metrics

    def get_priority_recommendations(
        self, limit: int = 10
    ) -> List[PriorityRecommendation]:
        """
        Retorna lista de recomendações priorizadas.

        Args:
            limit: Máximo de recomendações a retornar

        Returns:
            Lista de PriorityRecommendation ordenada por gap (decrescente)
        """
        metrics = self.calculate_balance_metrics()

        # Converter dicts de volta para PriorityRecommendation
        recommendations = [
            PriorityRecommendation(**r) for r in metrics.priority_recommendations
        ]

        # Ordenar por gap e limitar
        recommendations.sort(key=lambda r: r.gap, reverse=True)

        return recommendations[:limit]

    def _count_total(self) -> int:
        """Conta total de feedbacks na coleção."""
        try:
            return self.collection.count_documents({})
        except Exception as e:
            logger.error("Failed to count total feedbacks", error=str(e))
            return 0

    def _calculate_class_distribution(self, total: int) -> Dict[str, Dict[str, Any]]:
        """Calcula distribuição por classe (approve/reject/review_required)."""
        distribution = {}

        try:
            # Pipeline de agregação para contar por classe
            pipeline = [
                {"$group": {"_id": "$human_recommendation", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]

            results = list(self.collection.aggregate(pipeline))

            for result in results:
                rec = result["_id"]
                if rec is None:
                    continue

                count = result["count"]
                percentage = (count / total * 100) if total > 0 else 0
                gap = max(0, (self.TARGET_BALANCE * 100) - percentage)

                distribution[rec] = {
                    "count": count,
                    "percentage": round(percentage, 1),
                    "gap": round(gap, 1),
                }

        except Exception as e:
            logger.error("Failed to calculate class distribution", error=str(e))

        return distribution

    def _calculate_confidence_distribution(
        self, total: int
    ) -> Dict[str, Dict[str, Any]]:
        """Calcula distribuição por faixa de confiança."""
        distribution = {
            key: {"count": 0, "percentage": 0.0} for key in self.CONFIDENCE_RANGES
        }

        try:
            # Buscar todos os documents com opinion_confidence
            pipeline = [
                {"$match": {"opinion_confidence": {"$type": "number", "$ne": None}}},
                {"$project": {"opinion_confidence": 1}},
            ]

            results = list(self.collection.aggregate(pipeline))

            # Categorizar por faixa
            for doc in results:
                conf = doc["opinion_confidence"]
                for range_name, (low, high) in self.CONFIDENCE_RANGES.items():
                    if low <= conf < high:
                        distribution[range_name]["count"] += 1
                        break

            # Calcular porcentagens
            for range_name in distribution:
                count = distribution[range_name]["count"]
                pct = (count / total * 100) if total > 0 else 0
                distribution[range_name]["percentage"] = round(pct, 1)

        except Exception as e:
            logger.error("Failed to calculate confidence distribution", error=str(e))

        return distribution

    def _calculate_domain_distribution(self, total: int) -> Dict[str, Dict[str, Any]]:
        """Calcula distribuição por domínio NLP."""
        distribution = {}

        try:
            # Buscar todos com nlp_features.primary_domain
            pipeline = [
                {
                    "$match": {
                        "nlp_features.primary_domain": {"$type": "string", "$ne": None}
                    }
                },
                {"$project": {"domain": "$nlp_features.primary_domain"}},
            ]

            results = list(self.collection.aggregate(pipeline))

            # Contar por domínio
            domain_counts = Counter(doc.get("domain", "unknown") for doc in results)

            for domain, count in domain_counts.items():
                pct = (count / total * 100) if total > 0 else 0
                distribution[domain] = {"count": count, "percentage": round(pct, 1)}

        except Exception as e:
            logger.error("Failed to calculate domain distribution", error=str(e))

        return distribution

    def _calculate_semantic_features_stats(self, total: int) -> tuple[int, float]:
        """Calcula estatísticas de features semânticas."""
        try:
            # Contar feedbacks com reasoning_factors semânticos
            pipeline = [
                {
                    "$match": {
                        "reasoning_factors": {"$type": "array", "$not": {"$size": 0}}
                    }
                },
                {"$project": {"reasoning_factors": 1}},
            ]

            results = list(self.collection.aggregate(pipeline))

            semantic_count = 0
            for doc in results:
                factors = doc.get("reasoning_factors", [])
                if factors:
                    # Verificar se pelo menos um fator tem prefixo semantic_
                    for factor in factors:
                        name = factor.get("factor_name", "")
                        if any(
                            name.startswith(prefix) for prefix in self.SEMANTIC_PREFIXES
                        ):
                            semantic_count += 1
                            break

            percentage = (semantic_count / total * 100) if total > 0 else 0

            return semantic_count, round(percentage, 1)

        except Exception as e:
            logger.error("Failed to calculate semantic features stats", error=str(e))
            return 0, 0.0

    def _generate_priority_recommendations(
        self,
        class_dist: Dict[str, Dict[str, Any]],
        confidence_dist: Dict[str, Dict[str, Any]],
        domain_dist: Dict[str, Dict[str, Any]],
        total: int,
    ) -> List[PriorityRecommendation]:
        """Gera recomendações de prioridade baseado em gaps."""
        recommendations = []

        # Classes sub-representadas
        for cls, stats in class_dist.items():
            gap = stats.get("gap", 0)
            if gap > 10.0:  # Mais de 10pp de gap
                recommendations.append(
                    PriorityRecommendation(
                        type="class",
                        value=cls,
                        gap=gap,
                        reason=f"{cls} está {gap:.1f}pp abaixo do alvo de 33%",
                    )
                )

        # Confianças sub-representadas
        target_conf_pct = 100.0 / 3.0  # ~33% para cada faixa
        for conf_range, stats in confidence_dist.items():
            pct = stats.get("percentage", 0)
            gap = max(0, target_conf_pct - pct)
            if gap > 10.0:
                recommendations.append(
                    PriorityRecommendation(
                        type="confidence",
                        value=conf_range,
                        gap=gap,
                        reason=f"Confiança {conf_range} está {gap:.1f}pp abaixo do alvo",
                    )
                )

        # Domínios sub-representados (menos de 10% ou menos de 10 samples)
        min_domain_pct = 10.0
        min_domain_samples = 10
        for domain, stats in domain_dist.items():
            count = stats.get("count", 0)
            pct = stats.get("percentage", 0)

            if count < min_domain_samples or pct < min_domain_pct:
                gap = min_domain_pct - pct
                recommendations.append(
                    PriorityRecommendation(
                        type="domain",
                        value=domain,
                        gap=gap,
                        reason=f"Domínio {domain} tem apenas {count} samples ({pct:.1f}%)",
                    )
                )

        # Ordenar por gap e retornar top 10
        recommendations.sort(key=lambda r: r.gap, reverse=True)

        return recommendations[:10]
