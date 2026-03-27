"""
Active Learning Strategy - Calcula valor informacional de cada caso.

Define quais casos são mais valiosos para coletar feedback manual,
baseado em incerteza do modelo, representação no dataset e novidade.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
import structlog

from pydantic import BaseModel, Field

logger = structlog.get_logger()

# Pesos padrão para cálculo de valor informacional
DEFAULT_CONFIDENCE_WEIGHT = 0.5
DEFAULT_REPRESENTATION_WEIGHT = 0.3
DEFAULT_NOVELTY_WEIGHT = 0.2

# Threshold padrão para coleta de feedback
DEFAULT_THRESHOLD = 0.6


@dataclass
class InformationValue:
    """Valor informacional de um caso."""

    value: float  # 0.0-1.0
    confidence: float  # Confiança da predição
    representation: float  # Representação no dataset (0-1)
    domain_novelty: float  # Novidade do domínio (0-1)
    reason: str = ""  # Descrição do porquê é valioso

    def __post_init__(self):
        """Gera razão automaticamente se não fornecida."""
        if not self.reason:
            self.reason = self._generate_reason()

    def _generate_reason(self) -> str:
        """Gera descrição baseada nos componentes."""
        parts = []

        if self.confidence < 0.4:
            parts.append("alta incerteza")
        elif self.confidence > 0.8:
            parts.append("baixa incerteza")

        if self.representation < 0.2:
            parts.append("baixa representação")
        elif self.representation > 0.8:
            parts.append("alta representação")

        if self.domain_novelty > 0.7:
            parts.append("domínio novo")

        if parts:
            return f'{", ".join(parts)} (valor: {self.value:.2f})'
        return f"Valor informacional: {self.value:.2f}"

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "value": self.value,
            "confidence": self.confidence,
            "representation": self.representation,
            "domain_novelty": self.domain_novelty,
            "reason": self.reason,
        }


class ActiveLearningStrategy:
    """
    Estratégia de Active Learning para priorizar coleta de feedback.

    Calcula "valor informacional" baseado em:
    - Incerteza da predição (quanto menor, maior valor)
    - Representação no dataset (quanto menor, maior valor)
    - Novidade do domínio (quanto maior, maior valor)
    """

    def __init__(
        self,
        confidence_weight: float = DEFAULT_CONFIDENCE_WEIGHT,
        representation_weight: float = DEFAULT_REPRESENTATION_WEIGHT,
        novelty_weight: float = DEFAULT_NOVELTY_WEIGHT,
        threshold: float = DEFAULT_THRESHOLD,
    ):
        """
        Inicializa a estratégia.

        Args:
            confidence_weight: Peso da incerteza no cálculo (padrão: 0.5)
            representation_weight: Peso da representação (padrão: 0.3)
            novelty_weight: Peso da novidade (padrão: 0.2)
            threshold: Threshold mínimo para coleta (padrão: 0.6)
        """
        # Validar pesos somam 1.0
        total_weight = confidence_weight + representation_weight + novelty_weight
        if abs(total_weight - 1.0) > 0.01:
            logger.warning("Weights do not sum to 1.0, normalizing", total=total_weight)
            # Normalizar
            self.confidence_weight = confidence_weight / total_weight
            self.representation_weight = representation_weight / total_weight
            self.novelty_weight = novelty_weight / total_weight
        else:
            self.confidence_weight = confidence_weight
            self.representation_weight = representation_weight
            self.novelty_weight = novelty_weight

        self.threshold = threshold

        logger.info(
            "ActiveLearningStrategy initialized",
            confidence_weight=self.confidence_weight,
            representation_weight=self.representation_weight,
            novelty_weight=self.novelty_weight,
            threshold=threshold,
        )

    def calculate_information_value(self, case: Dict[str, Any]) -> float:
        """
        Calcula valor informacional de um caso.

        Args:
            case: Dicionário com:
                - confidence: Confiança da predição (0-1)
                - representation: Representação no dataset (0-1)
                - domain_novelty: Novidade do domínio (0-1)

        Returns:
            Valor informacional (0.0-1.0)
        """
        confidence = case.get("confidence", 0.5)
        representation = case.get("representation", 0.5)
        novelty = case.get("domain_novelty", 0.5)

        # Incerteza = 1 - confiança (quanto menor a confiança, maior a incerteza)
        uncertainty = 1.0 - confidence

        # Valor ponderado
        value = (
            uncertainty * self.confidence_weight
            + (1.0 - representation) * self.representation_weight
            + novelty * self.novelty_weight
        )

        return round(min(1.0, max(0.0, value)), 3)

    def calculate_from_prediction(
        self, prediction: Dict[str, Any], dataset_stats: Dict[str, Any]
    ) -> float:
        """
        Calcula valor informacional a partir de predição ML.

        Args:
            prediction: Dicionário com predição (decision, confidence, nlp_features)
            dataset_stats: Estatísticas do dataset (distribuição de classes/domínios)

        Returns:
            Valor informacional (0.0-1.0)
        """
        # Extrair confiança
        confidence = prediction.get("confidence", 0.5)

        # Extrair representação da classe
        decision = prediction.get("decision", "approve")
        class_dist = dataset_stats.get("class_distribution", {})
        class_representation = class_dist.get(decision, 0.5)

        # Extrair novidade do domínio
        nlp_features = prediction.get("nlp_features", {}) or {}
        domain = nlp_features.get("primary_domain", "unknown")
        domain_dist = dataset_stats.get("domain_distribution", {})

        if domain in domain_dist:
            domain_representation = domain_dist[domain]
            domain_novelty = 1.0 - domain_representation
        else:
            # Domínio desconhecido = máxima novidade
            domain_novelty = 1.0

        # Calcular valor
        return self.calculate_information_value(
            {
                "confidence": confidence,
                "representation": class_representation,
                "domain_novelty": domain_novelty,
            }
        )

    def should_collect_feedback(
        self, case: Dict[str, Any], threshold: Optional[float] = None
    ) -> bool:
        """
        Decide se deve coletar feedback para este caso.

        Args:
            case: Dicionário com dados do caso (pode ser prediction dict ou dict com campos)
            threshold: Threshold opcional (usa padrão se não fornecido)

        Returns:
            True se valor informacional >= threshold
        """
        # Tentar calcular a partir de prediction format
        if "decision" in case or "confidence" in case:
            # Verificar se tem dataset_stats (se não, usar método simples)
            # Para simplificar, extrair valores do case
            confidence = case.get("confidence", 0.5)
            representation = case.get("representation", 0.5)
            novelty = case.get("domain_novelty", 0.5)

            value = self.calculate_information_value(
                {
                    "confidence": confidence,
                    "representation": representation,
                    "domain_novelty": novelty,
                }
            )
        else:
            # Case já tem os campos necessários
            value = self.calculate_information_value(case)

        threshold = threshold if threshold is not None else self.threshold

        return value >= threshold

    def rank_cases(
        self,
        cases: list[Dict[str, Any]],
        dataset_stats: Dict[str, Any],
        limit: int = None,
    ) -> list[tuple[int, float]]:
        """
        Rankeia casos por valor informacional.

        Args:
            cases: Lista de casos (predictions)
            dataset_stats: Estatísticas do dataset
            limit: Máximo de casos a retornar

        Returns:
            Lista de tuplas (index, value) ordenada por valor (decrescente)
        """
        scored_cases = []

        for idx, case in enumerate(cases):
            value = self.calculate_from_prediction(case, dataset_stats)
            scored_cases.append((idx, value))

        # Ordenar por valor (decrescente)
        scored_cases.sort(key=lambda x: x[1], reverse=True)

        if limit:
            scored_cases = scored_cases[:limit]

        return scored_cases

    def get_top_cases(
        self,
        predictions: list[Dict[str, Any]],
        dataset_stats: Dict[str, Any],
        n: int = 10,
    ) -> list[Dict[str, Any]]:
        """
        Retorna top N casos por valor informacional.

        Args:
            predictions: Lista de predições
            dataset_stats: Estatísticas do dataset
            n: Número de casos a retornar

        Returns:
            Lista dos top N casos com valores incluídos
        """
        ranked = self.rank_cases(predictions, dataset_stats, limit=n)

        result = []
        for idx, score in ranked:
            case = predictions[idx].copy()
            case["_information_value"] = score
            case["_information_rank"] = len(result) + 1
            result.append(case)

        return result
