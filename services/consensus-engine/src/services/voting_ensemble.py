from collections import Counter
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class VotingEnsemble:
    """Voting ensemble com pesos dinâmicos para agregação de recomendações"""

    def __init__(self, config):
        self.config = config

    def aggregate_recommendations(
        self, opinions: list[dict[str, Any]], weights: dict[str, float]
    ) -> tuple[str, dict[str, float]]:
        """Agrega recomendações usando voting ponderado

        Args:
            opinions: Lista de pareceres
            weights: Pesos dinâmicos por especialista

        Returns:
            Tuple (recomendação vencedora, distribuição de votos)
        """
        # Coletar votos ponderados
        vote_weights = {}

        for opinion in opinions:
            specialist_type = opinion["specialist_type"]
            recommendation = opinion["opinion"]["recommendation"]
            weight = weights.get(specialist_type, 0.2)

            if recommendation not in vote_weights:
                vote_weights[recommendation] = 0.0

            vote_weights[recommendation] += weight

        # Normalizar distribuição
        total_weight = sum(vote_weights.values())
        vote_distribution = {rec: weight / total_weight for rec, weight in vote_weights.items()}

        # Selecionar vencedor (maior peso)
        winner = max(vote_weights.items(), key=lambda x: x[1])[0]

        logger.info(
            "Voting ensemble result",
            winner=winner,
            distribution=vote_distribution,
            num_opinions=len(opinions),
        )

        return winner, vote_distribution

    def check_unanimity(self, opinions: list[dict[str, Any]]) -> bool:
        """Verifica se há unanimidade nas recomendações"""
        recommendations = [op["opinion"]["recommendation"] for op in opinions]
        return len(set(recommendations)) == 1

    def check_majority(
        self, opinions: list[dict[str, Any]], threshold: float = 0.6
    ) -> tuple[bool, Optional[str]]:
        """Verifica se há maioria (>threshold) para alguma recomendação

        Args:
            opinions: Lista de pareceres
            threshold: Threshold de maioria (padrão 60%)

        Returns:
            Tuple (tem maioria, recomendação majoritária)
        """
        recommendations = [op["opinion"]["recommendation"] for op in opinions]
        counter = Counter(recommendations)

        for recommendation, count in counter.items():
            ratio = count / len(recommendations)
            if ratio >= threshold:
                return True, recommendation

        return False, None
