"""
HierarchicalExplainer - Explicação de decisões com consenso hierárquico.

Calcula breakdown por nível de senioridade e força de consenso entre especialistas.

Explainability API v3 - Task 3
"""

from typing import Any, Dict, List, Optional

import structlog

# Importar modelos de senioridade locais (sincronizados com consensus-engine)
from src.models.seniority import SENIORITY_MULTIPLIERS, SeniorityLevel

logger = structlog.get_logger(__name__)


class HierarchicalExplainer:
    """
    Explainer para decisões tomadas via consenso hierárquico.

    Fornece análise detalhada de como a senioridade dos especialistas
    influenciou a decisão final, incluindo:
    - Breakdown por nível de senioridade
    - Força de consenso entre níveis
    - Contribuições individuais rankeadas
    """

    # Nível de senioridade padrão para decisões legadas (pré-GAPS-03)
    DEFAULT_SENIORITY_LEVEL = SeniorityLevel.MID_LEVEL

    def __init__(self):
        """Inicializa o explainer hierárquico."""
        self.logger = logger

    def explain(self, votes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Gera explicação completa hierárquica para uma decisão.

        Args:
            votes: Lista de votos dos especialistas com campos hierárquicos

        Returns:
            Dicionário com breakdown hierárquico e contribuições individuais
        """
        if not votes:
            self.logger.warning("No votes provided for hierarchical explanation")
            return {
                "hierarchical_breakdown": {
                    "by_level": {},
                    "dominant_level": None,
                    "consensus_strength": 0.0,
                },
                "individual_contributions": [],
            }

        # Normalizar votos (adicionar campos de senioridade se faltar)
        normalized_votes = self._normalize_votes(votes)

        # Calcular breakdown por nível
        by_level = self._calculate_by_level_breakdown(normalized_votes)

        # Calcular força de consenso
        consensus_strength = self._calculate_consensus_strength(by_level)

        # Determinar nível dominante
        dominant_level = self._determine_dominant_level(by_level)

        # Calcular contribuições individuais
        individual_contributions = self._calculate_individual_contributions(normalized_votes)

        return {
            "hierarchical_breakdown": {
                "by_level": by_level,
                "dominant_level": dominant_level,
                "consensus_strength": consensus_strength,
            },
            "individual_contributions": individual_contributions,
        }

    def _normalize_votes(self, votes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normaliza votos, adaptando formato specialist_votes para v3.

        Mapeia:
        - specialist_type -> seniority_level (via mapeamento)
        - specialist_type/opinion_id -> specialist_id
        - recommendation -> vote
        - confidence_score -> confidence

        Preserva campos já normalizados se presentes.

        Args:
            votes: Lista de votos brutos

        Returns:
            Lista de votos normalizados
        """
        # Mapeamento specialist_type -> seniority_level
        TYPE_TO_SENIORITY = {
            "business": "senior",
            "technical": "senior",
            "architecture": "expert",
            "behavior": "mid_level",
            "evolution": "mid_level",
        }

        normalized = []

        for vote in votes:
            normalized_vote = {}

            # Se o voto já tem specialist_id e seniority_level (pré-normalizado),
            # preservar esses valores
            if "specialist_id" in vote and "seniority_level" in vote:
                normalized_vote["specialist_id"] = vote["specialist_id"]
                normalized_vote["seniority_level"] = vote["seniority_level"]
                # Preservar specialist_type se existir
                if "specialist_type" in vote:
                    normalized_vote["specialist_type"] = vote["specialist_type"]
                else:
                    normalized_vote["specialist_type"] = "unknown"
            else:
                # Mapear identificador
                specialist_type = vote.get("specialist_type", "unknown")
                normalized_vote["specialist_id"] = vote.get("opinion_id", specialist_type)
                normalized_vote["specialist_type"] = specialist_type

                # Mapear seniority
                seniority_level = TYPE_TO_SENIORITY.get(specialist_type, "mid_level")
                normalized_vote["seniority_level"] = seniority_level

            # Mapear voto (verificar ambos os formatos)
            if "vote" in vote:
                normalized_vote["vote"] = vote["vote"]
            else:
                recommendation = vote.get("recommendation", "neutral")
                normalized_vote["vote"] = recommendation

            # Mapear confiança
            if "confidence" in vote:
                normalized_vote["confidence"] = vote["confidence"]
            else:
                normalized_vote["confidence"] = vote.get("confidence_score", 0.5)

            # Mapear peso
            if "seniority_multiplier" in vote:
                normalized_vote["seniority_multiplier"] = vote["seniority_multiplier"]
            elif "weight" in vote:
                normalized_vote["seniority_multiplier"] = vote["weight"]
            else:
                seniority_level = normalized_vote["seniority_level"]
                normalized_vote["seniority_multiplier"] = SENIORITY_MULTIPLIERS.get(
                    seniority_level, 1.0
                )

            # Adicionar decision_id se existir
            if "decision_id" in vote:
                normalized_vote["decision_id"] = vote["decision_id"]

            normalized.append(normalized_vote)

        return normalized

    def _calculate_by_level_breakdown(
        self, votes: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calcula breakdown estatístico por nível de senioridade.

        Args:
            votes: Lista de votos normalizados

        Returns:
            Dicionário com estatísticas por nível
        """
        by_level: Dict[str, Dict[str, Any]] = {}

        for vote in votes:
            level = vote["seniority_level"]

            if level not in by_level:
                by_level[level] = {
                    "count": 0,
                    "weight_multiplier": SENIORITY_MULTIPLIERS.get(level, 1.0),
                    "raw_votes": {"approve": 0, "reject": 0, "neutral": 0},
                    "weighted_contribution": 0.0,
                    "influence_direction": "neutral",
                    "specialists": [],
                }

            level_data = by_level[level]
            level_data["count"] += 1
            level_data["specialists"].append(vote["specialist_id"])

            # Contar voto bruto
            vote_type = vote.get("vote", "neutral")
            if vote_type in level_data["raw_votes"]:
                level_data["raw_votes"][vote_type] += 1

        # Calcular contribuição ponderada por nível
        for level, level_data in by_level.items():
            weighted_sum = 0.0
            multiplier = level_data["weight_multiplier"]

            for vote in votes:
                if vote["seniority_level"] == level:
                    vote_type = vote.get("vote", "neutral")
                    confidence = vote.get("confidence", 0.5)

                    # Calcular valor do voto: approve = +confidence, reject = -confidence
                    vote_value = 0.0
                    if vote_type == "approve":
                        vote_value = confidence
                    elif vote_type == "reject":
                        vote_value = -confidence

                    weighted_sum += vote_value * multiplier

            level_data["weighted_contribution"] = weighted_sum

            # Determinar direção de influência
            if weighted_sum > 0:
                level_data["influence_direction"] = "approve"
            elif weighted_sum < 0:
                level_data["influence_direction"] = "reject"
            else:
                level_data["influence_direction"] = "neutral"

        return by_level

    def _calculate_consensus_strength(self, by_level: Dict[str, Dict[str, Any]]) -> float:
        """
        Calcula a força do consenso entre níveis hierárquicos.

        Retornos:
        - 1.0: Todos os níveis concordam (unânime)
        - 0.5: Metade dos níveis concorda
        - 0.0: Nenhum nível ou completamente dividido

        Args:
            by_level: Breakdown por nível calculado anteriormente

        Returns:
            Float entre 0.0 e 1.0 representando força do consenso
        """
        if not by_level:
            return 0.0

        directions = []
        for level_data in by_level.values():
            direction = level_data.get("influence_direction", "neutral")
            if direction == "approve":
                directions.append(1)
            elif direction == "reject":
                directions.append(-1)
            else:
                directions.append(0)

        if not directions:
            return 0.0

        # Se todos concordam (mesma direção)
        if all(d == directions[0] for d in directions):
            return 1.0

        # Proporção de níveis na direção dominante
        # Contar occurrences de cada direção
        from collections import Counter

        direction_counts = Counter(directions)
        most_common_count = direction_counts.most_common(1)[0][1]

        return most_common_count / len(directions)

    def _determine_dominant_level(self, by_level: Dict[str, Dict[str, Any]]) -> Optional[str]:
        """
        Determina o nível hierárquico dominante na decisão.

        O nível dominante é aquele com maior contribuição ponderada absoluta.

        Args:
            by_level: Breakdown por nível calculado anteriormente

        Returns:
            String com o nível dominante ou None se vazio
        """
        if not by_level:
            return None

        dominant_level = None
        max_contribution = float("-inf")

        for level, level_data in by_level.items():
            contribution = abs(level_data["weighted_contribution"])
            if contribution > max_contribution:
                max_contribution = contribution
                dominant_level = level

        return dominant_level

    def _calculate_individual_contributions(
        self, votes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Calcula contribuição individual de cada especialista.

        Args:
            votes: Lista de votos normalizados

        Returns:
            Lista de contribuições ordenadas por rank (maior influência primeiro)
        """
        contributions = []

        for vote in votes:
            level = vote["seniority_level"]
            multiplier = vote["seniority_multiplier"]
            vote_type = vote.get("vote", "neutral")
            confidence = vote.get("confidence", 0.5)

            # Calcular score de contribuição
            vote_value = 0.0
            if vote_type == "approve":
                vote_value = confidence
            elif vote_type == "reject":
                vote_value = -confidence

            contribution_score = vote_value * multiplier

            contributions.append(
                {
                    "specialist_id": vote["specialist_id"],
                    "seniority_level": level,
                    "multiplier": multiplier,
                    "vote": vote_type,
                    "confidence": confidence,
                    "risk": vote.get("risk", 1.0 - confidence),
                    "weighted_vote": vote_type,  # Voto original (não muda com peso)
                    "contribution_score": contribution_score,
                    "rank": 0,  # Será preenchido após ordenação
                }
            )

        # Ordenar por contribution_score absoluto (maior influência primeiro)
        contributions.sort(key=lambda x: abs(x["contribution_score"]), reverse=True)

        # Atribuir ranks
        for i, contribution in enumerate(contributions, 1):
            contribution["rank"] = i

        return contributions

    async def explain_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gera explicação completa para uma decisão (async wrapper).

        Args:
            decision: Dicionário com decisão incluindo specialist_votes

        Returns:
            Dicionário com explicação hierárquica
        """
        votes = decision.get("specialist_votes", decision.get("votes", []))

        result = self.explain(votes)

        # Adicionar decision_id ao resultado
        result["decision_id"] = decision.get("decision_id", "unknown")

        # Adicionar campos esperados pelos testes
        if "hierarchical_breakdown" in result:
            result["hierarchical_weights"] = [
                level_data.get("weight_multiplier", 1.0)
                for level_data in result["hierarchical_breakdown"].get("by_level", {}).values()
            ]

            # Calcular seniority impact
            result["seniority_impact"] = self._calculate_seniority_impact(
                result["hierarchical_breakdown"]
            )

        return result

    def _calculate_seniority_impact(self, breakdown: Dict[str, Any]) -> float:
        """Calcula impacto total da senioridade na decisão."""
        by_level = breakdown.get("by_level", {})

        if not by_level:
            return 0.0

        # Somar contribuições ponderadas absolutas
        total_impact = sum(
            abs(level_data.get("weighted_contribution", 0.0)) for level_data in by_level.values()
        )

        return total_impact

    def calculate_seniority_weights(self, votes: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calcula pesos de senioridade para uma lista de votos.

        Args:
            votes: Lista de votos com campo seniority/seniority_level

        Returns:
            Dicionário mapeando nível para peso
        """
        weights = {}

        for vote in votes:
            # Tentar diferentes formatos de seniority
            seniority = vote.get("seniority_level", vote.get("seniority", "mid_level"))

            if seniority not in weights:
                weights[seniority] = SENIORITY_MULTIPLIERS.get(seniority, 1.0)

        return weights

    def _calculate_seniority_impact(self, breakdown: Dict[str, Any]) -> float:
        """Calcula impacto total da senioridade na decisão."""
        by_level = breakdown.get("by_level", {})

        if not by_level:
            return 0.0

        # Somar contribuições ponderadas absolutas
        total_impact = sum(
            abs(level_data.get("weighted_contribution", 0.0)) for level_data in by_level.values()
        )

        return total_impact

    def calculate_seniority_weights(self, votes: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calcula pesos de senioridade para uma lista de votos.

        Args:
            votes: Lista de votos com campo seniority/seniority_level

        Returns:
            Dicionário mapeando nível para peso
        """
        weights = {}

        for vote in votes:
            # Tentar diferentes formatos de seniority
            seniority = vote.get("seniority_level", vote.get("seniority", "mid_level"))

            if seniority not in weights:
                weights[seniority] = SENIORITY_MULTIPLIERS.get(seniority, 1.0)

        return weights
