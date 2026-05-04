"""Modelos de classificação de intenção."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class FlowType(str, Enum):
    """Tipos de fluxo suportados."""

    AF = "A-F"  # Cognitive Pipeline
    G = "G"  # Code Generation
    H = "H"  # Migration


class ClassificationDecision(BaseModel):
    """Resultado da classificação de intenção."""

    flow_type: FlowType
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    alternative: FlowType | None = None

    model_config = {"extra": "allow"}


class NLUResult(BaseModel):
    """Resultado do processamento NLU."""

    text: str
    domain: str
    confidence: float
    entities: dict[str, str]
    keywords: list[str]

    model_config = {"extra": "allow"}


class IntentClassifier:
    """
    Classificador de intenção com múltiplos sinais.

    Regras de classificação (ordem de precedência):
    1. Palavras-chave explícitas (peso variável)
    2. Entidades detectadas (peso 3.0)
    3. Complexidade inferida (peso 2.0)
    4. Default para A-F (peso 1.0)
    """

    # Palavras-chave por fluxo com pesos
    # Palavras de alta prioridade têm peso maior
    FLOW_AF_KEYWORDS_PRIORITY = {
        "dashboard": 5.0,
        "relatório": 4.0,
        "dados": 3.0,
        "visualizar": 4.0,
    }
    FLOW_AF_KEYWORDS = ["consultar", "buscar", "analisar", "listar", "mostrar"]

    FLOW_G_KEYWORDS_PRIORITY = {
        "sistema": 5.0,
        "software": 5.0,
        "app": 4.0,
        "aplicação": 4.0,
    }
    FLOW_G_KEYWORDS = ["gerar", "criar", "build", "desenvolver", "código", "implementar", "desenvolvimento"]

    FLOW_H_KEYWORDS_PRIORITY = {
        "legado": 5.0,
        "legacy": 5.0,
        "migrar": 5.0,
        "migration": 5.0,
    }
    FLOW_H_KEYWORDS = ["antigo", "atualizar", "modernizar", "sistema antigo"]

    def classify(self, nlu_result: NLUResult) -> ClassificationDecision:
        """
        Classifica a intenção baseado no resultado NLU.

        Args:
            nlu_result: Resultado do processamento NLU

        Returns:
            ClassificationDecision com flow_type e confiança
        """
        # 1. Verificar palavras-chave (peso 4.0)
        keyword_score = self._score_keywords(nlu_result.text, nlu_result.keywords)
        if keyword_score["confidence"] > 0.8:
            return self._decision(
                keyword_score["flow"],
                0.9,
                f"Palavras-chave indicam {keyword_score['flow'].value}: {keyword_score['matched']}",
            )

        # 2. Verificar entidades (peso 3.0)
        entity_score = self._score_entities(nlu_result.entities)
        if entity_score["confidence"] > 0.8:
            return self._decision(
                entity_score["flow"],
                0.85,
                f"Entidade '{entity_score['matched']}' indica {entity_score['flow'].value}",
            )

        # 3. Combinação keyword + entity
        combined = self._combine_scores(keyword_score, entity_score)
        if combined["confidence"] > 0.7:
            return self._decision(
                combined["flow"],
                combined["confidence"],
                f"Combinação de indicadores: {combined['reasoning']}",
            )

        # 4. Default para A-F
        return ClassificationDecision(
            flow_type=FlowType.AF,
            confidence=0.5,
            reasoning="Sem indicadores claros, defaultando para Cognitive Pipeline",
            alternative=None,
        )

    def _score_keywords(self, text: str, keywords: list[str]) -> dict:
        """Pontua palavras-chave encontradas."""
        text_lower = text.lower()

        # Contar palavras-chave de cada fluxo no texto
        af_count = sum(1 for kw in self.FLOW_AF_KEYWORDS if kw in text_lower)
        g_count = sum(1 for kw in self.FLOW_G_KEYWORDS if kw in text_lower)
        h_count = sum(1 for kw in self.FLOW_H_KEYWORDS if kw in text_lower)

        scores = {
            FlowType.AF: af_count * 4.0,
            FlowType.G: g_count * 4.0,
            FlowType.H: h_count * 4.0,
        }

        max_score = max(scores.values())
        if max_score == 0:
            return {"flow": FlowType.AF, "confidence": 0, "matched": []}

        winner = max(scores, key=scores.get)

        # Coletar palavras-chave encontradas para reasoning
        matches = []
        if winner == FlowType.AF:
            matches = [kw for kw in self.FLOW_AF_KEYWORDS if kw in text_lower]
        elif winner == FlowType.G:
            matches = [kw for kw in self.FLOW_G_KEYWORDS if kw in text_lower]
        else:
            matches = [kw for kw in self.FLOW_H_KEYWORDS if kw in text_lower]

        return {
            "flow": winner,
            "confidence": min(max_score / 8.0, 1.0),  # Normalizar
            "matched": matches,
        }

    def _score_entities(self, entities: dict[str, str]) -> dict:
        """Pontua entidades encontradas."""
        if not entities:
            return {"flow": FlowType.AF, "confidence": 0, "matched": None}

        # Entidades que indicam fluxo G
        if "software_type" in entities or "app_type" in entities:
            return {
                "flow": FlowType.G,
                "confidence": 0.9,
                "matched": list(entities.keys())[0],
            }

        # Entidades que indicam fluxo H
        if "legacy_system" in entities or "database_schema" in entities:
            return {
                "flow": FlowType.H,
                "confidence": 0.95,
                "matched": list(entities.keys())[0],
            }

        return {"flow": FlowType.AF, "confidence": 0, "matched": None}

    def _combine_scores(self, keyword_score: dict, entity_score: dict) -> dict:
        """Combina scores de keyword e entity."""
        # Pontuação ponderada
        weights = {"keyword": 4.0, "entity": 3.0}

        scores = {
            FlowType.AF: (
                keyword_score.get("confidence", 0) * weights["keyword"]
                if keyword_score.get("flow") == FlowType.AF
                else 0
            )
            + (
                entity_score.get("confidence", 0) * weights["entity"]
                if entity_score.get("flow") == FlowType.AF
                else 0
            ),
            FlowType.G: (
                keyword_score.get("confidence", 0) * weights["keyword"]
                if keyword_score.get("flow") == FlowType.G
                else 0
            )
            + (
                entity_score.get("confidence", 0) * weights["entity"]
                if entity_score.get("flow") == FlowType.G
                else 0
            ),
            FlowType.H: (
                keyword_score.get("confidence", 0) * weights["keyword"]
                if keyword_score.get("flow") == FlowType.H
                else 0
            )
            + (
                entity_score.get("confidence", 0) * weights["entity"]
                if entity_score.get("flow") == FlowType.H
                else 0
            ),
        }

        max_score = max(scores.values())
        if max_score == 0:
            return {"flow": FlowType.AF, "confidence": 0, "reasoning": "sem indicadores"}

        winner = max(scores, key=scores.get)
        confidence = min(max_score / 7.0, 1.0)

        reasoning_parts = []
        if keyword_score.get("flow") == winner:
            reasoning_parts.append(f"palavras-chave: {keyword_score.get('matched', [])}")
        if entity_score.get("flow") == winner:
            reasoning_parts.append(f"entidade: {entity_score.get('matched', '')}")

        return {
            "flow": winner,
            "confidence": confidence,
            "reasoning": ", ".join(reasoning_parts),
        }

    def _decision(
        self, flow_type: FlowType, confidence: float, reasoning: str
    ) -> ClassificationDecision:
        """Cria uma decisão de classificação."""
        # Determinar alternativa
        alternatives = {FlowType.AF: FlowType.G, FlowType.G: FlowType.AF, FlowType.H: FlowType.AF}
        alternative = alternatives.get(flow_type)

        return ClassificationDecision(
            flow_type=flow_type, confidence=confidence, reasoning=reasoning, alternative=alternative
        )
