"""Modelos de classificação de intenção."""

import logging
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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
    """Resultado do processamento NLU (compatível com NLU Service)."""

    text: str
    domain: str  # DOMAIN_UNKNOWN, BUSINESS, TECHNICAL, INFRASTRUCTURE, SECURITY
    confidence: float
    entities: dict[str, str]  # EntityType -> value
    keywords: list[str]

    model_config = {"extra": "allow"}


class IntentClassifier:
    """
    Classificador de intenção integrado com NLU Service.

    Combina:
    1. Classificação de domínio do NLU Service (gRPC)
    2. Heurísticas de palavras-chave (fallback)
    3. Mapeamento domínio → flow type

    Mapeamento domínio → flow:
    - BUSINESS → A-F (Cognitive Pipeline - dashboard, relatórios, dados)
    - TECHNICAL → G (Code Generation - gerar código, criar app)
    - INFRASTRUCTURE → H (Migration - migrar, atualizar legado)
    - SECURITY → A-F (Cognitive Pipeline com contexto de segurança)
    - DOMAIN_UNKNOWN → A-F (default)
    """

    # Mapeamento UnifiedDomain → FlowType
    DOMAIN_TO_FLOW = {
        "BUSINESS": FlowType.AF,
        "TECHNICAL": FlowType.G,
        "INFRASTRUCTURE": FlowType.H,
        "SECURITY": FlowType.AF,
        "DOMAIN_UNKNOWN": FlowType.AF,
    }

    # Refinamento por palavras-chave (overrides quando NLU tem baixa confiança)
    FLOW_AF_KEYWORDS = ["consultar", "buscar", "analisar", "listar", "mostrar", "dashboard", "relatório", "dados"]
    FLOW_G_KEYWORDS = ["gerar", "criar", "build", "desenvolver", "código", "implementar", "app", "sistema"]
    FLOW_H_KEYWORDS = ["migrar", "migration", "legado", "legacy", "atualizar", "modernizar"]

    def __init__(self, nlu_client=None):
        """
        Inicializa o classificador.

        Args:
            nlu_client: Cliente NLU Service (opcional, para injeção de dependência)
        """
        self._nlu_client = nlu_client

    async def classify(
        self,
        text: str,
        language: str = "pt",
        context: dict[str, str] | None = None,
    ) -> ClassificationDecision:
        """
        Classifica a intenção baseado no texto usando NLU Service.

        Args:
            text: Texto para classificar
            language: Idioma do texto
            context: Contexto adicional (tenant_id, user_id, etc)

        Returns:
            ClassificationDecision com flow_type, confidence e reasoning
        """
        if self._nlu_client is None:
            logger.warning("NLU client not available, using keyword-only classification")
            return self._classify_by_keywords(text)

        try:
            # Obter resultado do NLU Service
            nlu_result = await self._nlu_client.parse(
                text=text,
                language=language,
                context=context,
                enable_cache=True,
            )

            # Mapear domínio para flow type
            flow_type = self._domain_to_flow(nlu_result.domain, text)

            # Se confiança do NLU é baixa, refinar com keywords
            if nlu_result.confidence < 0.6:
                keyword_decision = self._classify_by_keywords(text)
                if keyword_decision.confidence > nlu_result.confidence:
                    return keyword_decision

            # Calcular confiança final (combinar NLU + keywords)
            final_confidence = self._combine_confidence(nlu_result.confidence, text)

            reasoning_parts = [
                f"domínio NLU: {nlu_result.domain}",
                f"confiança NLU: {nlu_result.confidence:.2f}",
            ]
            if nlu_result.keywords:
                reasoning_parts.append(f"keywords: {', '.join(nlu_result.keywords[:3])}")

            return ClassificationDecision(
                flow_type=flow_type,
                confidence=final_confidence,
                reasoning=" | ".join(reasoning_parts),
                alternative=self._get_alternative(flow_type),
            )

        except Exception as e:
            logger.error(f"Error in NLU classification: {e}, falling back to keywords")
            return self._classify_by_keywords(text)

    def _domain_to_flow(self, domain: str, text: str) -> FlowType:
        """
        Mapeia domínio NLU para flow type.

        Args:
            domain: Domínio do NLU Service
            text: Texto original (para refinamento)

        Returns:
            FlowType correspondente
        """
        flow = self.DOMAIN_TO_FLOW.get(domain, FlowType.AF)

        # Refinamento: DOMAIN_UNKNOWN com keywords claras
        if domain == "DOMAIN_UNKNOWN":
            text_lower = text.lower()
            if any(kw in text_lower for kw in self.FLOW_G_KEYWORDS):
                return FlowType.G
            if any(kw in text_lower for kw in self.FLOW_H_KEYWORDS):
                return FlowType.H

        return flow

    def _combine_confidence(self, nlu_confidence: float, text: str) -> float:
        """
        Combina confiança do NLU com análise de keywords.

        Args:
            nlu_confidence: Confiança do NLU Service
            text: Texto original

        Returns:
            Confiança combinada (0.0-1.0)
        """
        text_lower = text.lower()

        # Boost de confiança se keywords confirmam o flow
        has_af_keywords = any(kw in text_lower for kw in self.FLOW_AF_KEYWORDS)
        has_g_keywords = any(kw in text_lower for kw in self.FLOW_G_KEYWORDS)
        has_h_keywords = any(kw in text_lower for kw in self.FLOW_H_KEYWORDS)

        keyword_boost = 0.1 if (has_af_keywords or has_g_keywords or has_h_keywords) else 0.0

        return min(nlu_confidence + keyword_boost, 1.0)

    def _classify_by_keywords(self, text: str) -> ClassificationDecision:
        """
        Classificação baseada apenas em keywords (fallback).

        Args:
            text: Texto para classificar

        Returns:
            ClassificationDecision com base em keywords
        """
        text_lower = text.lower()

        # Contar keywords por flow
        af_count = sum(1 for kw in self.FLOW_AF_KEYWORDS if kw in text_lower)
        g_count = sum(1 for kw in self.FLOW_G_KEYWORDS if kw in text_lower)
        h_count = sum(1 for kw in self.FLOW_H_KEYWORDS if kw in text_lower)

        counts = {FlowType.AF: af_count, FlowType.G: g_count, FlowType.H: h_count}
        max_count = max(counts.values())

        if max_count == 0:
            return ClassificationDecision(
                flow_type=FlowType.AF,
                confidence=0.4,
                reasoning="Sem keywords identificadas, default para A-F",
                alternative=FlowType.G,
            )

        winner = max(counts, key=counts.get)
        confidence = min(max_count / 3.0, 0.8)  # Max 0.8 para keyword-only

        return ClassificationDecision(
            flow_type=winner,
            confidence=confidence,
            reasoning=f"Classificação por keywords: {max_count} ocorrências",
            alternative=self._get_alternative(winner),
        )

    def _get_alternative(self, flow_type: FlowType) -> FlowType | None:
        """Retorna flow type alternativo."""
        alternatives = {FlowType.AF: FlowType.G, FlowType.G: FlowType.AF, FlowType.H: FlowType.AF}
        return alternatives.get(flow_type)
