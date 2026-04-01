"""
ExplanationQualityScorer - Métricas de qualidade de explicações.

Calcula métricas de qualidade para explicações geradas pelo sistema:
- Completude: quantos campos obrigatórios estão presentes
- Clareza: quão clara e compreensível é a explicação
- Especificidade: quão específica e detalhada é a explicação

GAPS-04 Task 4
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class ExplanationQualityScorer:
    """
    Calculadora de métricas de qualidade para explicações.

    Avalia a qualidade das explicações geradas em diferentes dimensões
    e produz um score agregado.
    """

    # Pesos padrão para score agregado
    DEFAULT_WEIGHTS = {
        "completeness": 0.4,  # Completude é mais importante
        "clarity": 0.35,
        "specificity": 0.25,
    }

    # Campos obrigatórios para completude máxima
    REQUIRED_FIELDS = {
        "consensus_process": ["method", "num_specialists"],
        "specialist_opinions": ["specialist_type", "confidence"],
        "final_decision": ["decision"],
    }

    # Padrões para detecção de clareza
    VAGUE_PATTERNS = [
        r"\b(ok|tudo bem|sim|não|talvez|possivelmente)\b\.?\s*$",
        r"^\s*[a-zA-Z]{1,3}\.?\s*$",  # Respostas muito curtas
    ]

    # Padrões para detecção de especificidade (números, métricas)
    SPECIFICITY_PATTERNS = [
        r"\b\d+\.?\d*%?\b",  # Números e porcentagens
        r"\b\d+ms\b",  # Tempo em ms
        r"\b\d+s\b",  # Tempo em segundos
        r"\b\d+(?:,\d{3})*\b",  # Números grandes com vírgula
    ]

    def __init__(self, mongodb_client=None):
        """
        Inicializa o scorer.

        Args:
            mongodb_client: Cliente MongoDB opcional para persistência
        """
        self.mongodb = mongodb_client

    def score_completeness(self, explanation: Dict[str, Any]) -> float:
        """
        Calcula score de completude da explicação.

        Completude mede quantos campos obrigatórios estão presentes.

        Args:
            explanation: Dicionário com dados da explicação

        Returns:
            Score entre 0.0 e 1.0
        """
        if not explanation:
            return 0.0

        total_required = 0
        present_fields = 0

        # Verificar campos em cada seção
        for section, fields in self.REQUIRED_FIELDS.items():
            if section not in explanation:
                continue

            section_data = explanation[section]

            # Se section_data é uma lista
            if isinstance(section_data, list):
                if len(section_data) == 0:
                    continue

                # Verificar campos em cada item da lista
                for item in section_data[:3]:  # Limitar a 3 itens para eficiência
                    for field in fields:
                        total_required += 1
                        if field in item and item[field] is not None:
                            present_fields += 1

            # Se section_data é um dicionário
            elif isinstance(section_data, dict):
                for field in fields:
                    total_required += 1
                    if field in section_data and section_data[field] is not None:
                        present_fields += 1

        if total_required == 0:
            return 0.0

        return present_fields / total_required

    def score_clarity(self, explanation: Dict[str, Any]) -> float:
        """
        Calcula score de clareza da explicação.

        Clareza mede quão compreensível é a explicação,
        penalizando respostas vagas ou muito curtas.

        Args:
            explanation: Dicionário com dados da explicação

        Returns:
            Score entre 0.0 e 1.0
        """
        if not explanation:
            return 0.0

        # Coletar todos os textos de reasoning
        texts = self._collect_reasoning_texts(explanation)

        if not texts:
            return 0.0

        total_score = 0.0

        for text in texts:
            text = text.strip()

            # Penalizar textos muito curtos
            if len(text) < 10:
                total_score += 0.1
                continue

            # Verificar se é vago
            is_vague = False
            for pattern in self.VAGUE_PATTERNS:
                if re.match(pattern, text, re.IGNORECASE):
                    is_vague = True
                    break

            if is_vague:
                total_score += 0.2
            else:
                # Texto com tamanho razoável
                if 10 <= len(text) <= 200:
                    total_score += 0.9
                elif len(text) > 200:
                    # Texto muito longo pode reduzir clareza
                    total_score += 0.7
                else:
                    total_score += 0.5

        # Normalizar para [0, 1]
        if texts:
            return min(1.0, total_score / len(texts))
        return 0.0

    def score_specificity(self, explanation: Dict[str, Any]) -> float:
        """
        Calcula score de especificidade da explicação.

        Especificidade mede o nível de detalhe e presença de
        métricas/números concretos.

        Args:
            explanation: Dicionário com dados da explicação

        Returns:
            Score entre 0.0 e 1.0
        """
        if not explanation:
            return 0.0

        # Coletar todos os textos de reasoning
        texts = self._collect_reasoning_texts(explanation)

        if not texts:
            return 0.0

        total_specificity = 0.0
        total_texts = len(texts)

        for text in texts:
            text_score = 0.0

            # Contar ocorrências de padrões de especificidade
            pattern_count = 0
            for pattern in self.SPECIFICITY_PATTERNS:
                matches = re.findall(pattern, text, re.IGNORECASE)
                pattern_count += len(matches)

            # Calcular score baseado em padrões encontrados
            if pattern_count >= 3:
                text_score = 1.0
            elif pattern_count >= 2:
                text_score = 0.8
            elif pattern_count >= 1:
                text_score = 0.6
            else:
                # Sem números/métricas, verificar comprimento
                if len(text) > 100:
                    text_score = 0.3
                elif len(text) > 50:
                    text_score = 0.2
                else:
                    text_score = 0.1

            total_specificity += text_score

        return min(1.0, total_specificity / total_texts) if total_texts > 0 else 0.0

    def _collect_reasoning_texts(self, explanation: Dict[str, Any]) -> list:
        """Coleta todos os textos de reasoning da explicação."""
        texts = []

        # Adicionar reasoning_summary se existir
        if "reasoning_summary" in explanation:
            texts.append(explanation["reasoning_summary"])

        # Adicionar reasoning de specialist_opinions
        if "specialist_opinions" in explanation:
            for opinion in explanation["specialist_opinions"]:
                if "reasoning" in opinion:
                    texts.append(str(opinion["reasoning"]))
                elif "reasoning_summary" in opinion:
                    texts.append(str(opinion["reasoning_summary"]))

        # Adicionar rationale de final_decision
        if "final_decision" in explanation:
            decision = explanation["final_decision"]
            if isinstance(decision, dict) and "rationale" in decision:
                texts.append(str(decision["rationale"]))

        return texts

    def calculate_overall_score(
        self, scores: Dict[str, float], weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calcula score agregado a partir dos scores individuais.

        Args:
            scores: Dicionário com scores por dimensão
            weights: Pesos customizados (opcional)

        Returns:
            Score agregado entre 0.0 e 1.0
        """
        weights = weights or self.DEFAULT_WEIGHTS

        total_weight = 0.0
        weighted_sum = 0.0

        for dimension, score in scores.items():
            if dimension in weights:
                weight = weights[dimension]
                weighted_sum += score * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        return min(1.0, weighted_sum / total_weight)

    def score_explanation(
        self, explanation: Dict[str, Any], weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        Calcula todas as métricas de qualidade para uma explicação.

        Args:
            explanation: Dicionário com dados da explicação
            weights: Pesos customizados para score agregado

        Returns:
            Dicionário com todos os scores e overall
        """
        scores = {
            "completeness": self.score_completeness(explanation),
            "clarity": self.score_clarity(explanation),
            "specificity": self.score_specificity(explanation),
        }

        scores["overall"] = self.calculate_overall_score(scores, weights)

        return scores

    def save_scores(self, explanation_id: str, scores: Dict[str, float]) -> bool:
        """
        Salva scores no MongoDB.

        Args:
            explanation_id: ID da explicação
            scores: Dicionário com scores a salvar

        Returns:
            True se salvou com sucesso, False caso contrário
        """
        if not self.mongodb:
            logger.warning("MongoDB client not configured, skipping save")
            return False

        try:
            collection = self.mongodb.db["explanation_quality"]

            document = {
                "explanation_id": explanation_id,
                "completeness": scores.get("completeness", 0.0),
                "clarity": scores.get("clarity", 0.0),
                "specificity": scores.get("specificity", 0.0),
                "overall": scores.get("overall", 0.0),
                "timestamp": datetime.now(timezone.utc),
            }

            collection.update_one(
                {"explanation_id": explanation_id}, {"$set": document}, upsert=True
            )

            logger.info(
                "Quality scores saved",
                explanation_id=explanation_id,
                overall_score=scores.get("overall"),
            )
            return True

        except Exception as e:
            logger.error("Error saving quality scores", explanation_id=explanation_id, error=str(e))
            return False

    async def get_overall_score(self, explanation: Dict[str, Any]) -> float:
        """
        Calcula score geral de uma explicação (async wrapper).

        Args:
            explanation: Dicionário com dados da explicação

        Returns:
            Score geral entre 0.0 e 1.0
        """
        scores = self.score_explanation(explanation)
        return scores.get("overall", 0.0)

    def batch_score_explanations(
        self, explanations: list, weights: Optional[Dict[str, float]] = None
    ) -> list:
        """
        Calcula scores para múltiplas explicações.

        Args:
            explanations: Lista de dicionários de explicação
            weights: Pesos customizados (opcional)

        Returns:
            Lista de resultados com scores
        """
        results = []

        for i, explanation in enumerate(explanations):
            exp_id = (
                explanation.get("explainability_token")
                or explanation.get("decision_id")
                or f"exp-{i}"
            )

            scores = self.score_explanation(explanation, weights)
            scores["explanation_id"] = exp_id

            # Salvar no MongoDB
            self.save_scores(exp_id, scores)

            results.append(scores)

        return results
