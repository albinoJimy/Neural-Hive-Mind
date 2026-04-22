"""Processador de Texto para NLU.

Autor: Neural Hive Mind
Criado: 2026-04-20 (REFACTOR-A-001)
"""

import logging
import re
from typing import Any, Optional

from models.intent_envelope import Entity

logger = logging.getLogger(__name__)

# Importar compliance (PII masking)
try:
    from neural_hive_specialists.compliance import (
        MaskStrategy,
        PIIDetectorLite,
        PIIMasker,
        PIIType,
    )

    PII_MASKING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PII masking module not available: {e}. Using simple fallback.")
    PII_MASKING_AVAILABLE = False
    PIIType = None  # type: ignore


class TextProcessor:
    """Processador de texto para NLU."""

    def __init__(
        self,
        enable_pii_masking: bool = True,
        pii_mask_strategy: str = "redact",
        enable_entity_extraction: bool = True,
    ):
        """Inicializa processador de texto.

        Args:
            enable_pii_masking: Habilita masking de PII
            pii_mask_strategy: Estratégia de masking ('redact', 'hash', 'tokenize')
            enable_entity_extraction: Habilita extração de entidades
        """
        self.enable_pii_masking = enable_pii_masking and PII_MASKING_AVAILABLE
        self.pii_mask_strategy = pii_mask_strategy
        self.enable_entity_extraction = enable_entity_extraction

        # Inicializar componentes PII se disponível
        if self.enable_pii_masking:
            self.pii_detector = PIIDetectorLite()
            # Converter string para enum MaskStrategy
            try:
                strategy = (
                    MaskStrategy[pii_mask_strategy.upper()]
                    if isinstance(pii_mask_strategy, str)
                    else pii_mask_strategy
                )
            except (KeyError, AttributeError):
                strategy = MaskStrategy.REDACT
            self.pii_masker = PIIMasker(strategy=strategy)
        else:
            self.pii_detector = None
            self.pii_masker = None

    def normalize(self, text: str) -> str:
        """Normaliza texto para processamento.

        Args:
            text: Texto original

        Returns:
            Texto normalizado
        """
        if not text:
            return ""

        # 1. Converter para minúsculas (mas preservar para detecção PII)
        normalized = text.strip()

        # 2. Remover espaços extras
        normalized = re.sub(r"\s+", " ", normalized)

        # 3. Remover caracteres especiais excessivos
        normalized = re.sub(r"[^\w\s\.,!?;:@\-áéíóúàâêôãõç]", "", normalized)

        # 4. Normalizar quotes
        normalized = normalized.replace('"', '"').replace('"', '"').replace("'", "'")

        return normalized.strip()

    def mask_pii(
        self, text: str, entities: Optional[list[Entity]] = None
    ) -> tuple[str, list[Entity]]:
        """Detecta e mascara informações PII.

        Args:
            text: Texto original
            entities: Lista de entidades já extraídas

        Returns:
            Tupla (texto mascarado, entidades PII detectadas)
        """
        if not self.enable_pii_masking:
            return text, []

        pii_entities = []

        try:
            # Detectar PII
            detections = self.pii_detector.detect(text)

            if detections:
                # Criar entidades PII
                for detection in detections:
                    entity = Entity(
                        type=detection.type.value,
                        text=detection.matched_text,
                        start=detection.start,
                        end=detection.end,
                        confidence=detection.confidence,
                    )
                    pii_entities.append(entity)

                # Mascarar texto
                masked_text = self.pii_masker.mask(text, detections)
                return masked_text, pii_entities

        except Exception as e:
            logger.warning(f"PII masking error: {e}. Returning original text.")

        return text, pii_entities

    def extract_entities(self, doc: Any, masked: bool = False) -> list[Entity]:
        """Extrai entidades do documento spaCy.

        Args:
            doc: Documento spaCy processado
            masked: Se texto foi mascarado (afeta confiança)

        Returns:
            Lista de entidades extraídas
        """
        if not self.enable_entity_extraction:
            return []

        entities = []

        try:
            # Entidades nomeadas do spaCy
            for ent in doc.ents:
                entity_type = self._map_entity_type(ent.label_)
                entities.append(
                    Entity(
                        type=entity_type,
                        text=ent.text,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=0.8 if not masked else 0.6,
                    )
                )

            # Números e datas
            for token in doc:
                if token.like_num:
                    entities.append(
                        Entity(
                            type="NUMBER",
                            text=token.text,
                            confidence=0.9,
                        )
                    )
                elif token.like_date:
                    entities.append(
                        Entity(
                            type="DATE",
                            text=token.text,
                            confidence=0.85,
                        )
                    )
                elif token.like_email:
                    entities.append(
                        Entity(
                            type="EMAIL",
                            text=token.text,
                            confidence=0.95,
                        )
                    )
                elif token.like_url:
                    entities.append(
                        Entity(
                            type="URL",
                            text=token.text,
                            confidence=0.95,
                        )
                    )

        except Exception as e:
            logger.warning(f"Entity extraction error: {e}")

        return entities

    def _map_entity_type(self, spacy_label: str) -> str:
        """Mapeia labels spaCy para tipos de entidade NLU.

        Args:
            spacy_label: Label do spaCy

        Returns:
            Tipo de entidade NLU
        """
        mapping = {
            "PERSON": "PERSON",
            "ORG": "ORGANIZATION",
            "GPE": "LOCATION",
            "LOC": "LOCATION",
            "PRODUCT": "PRODUCT",
            "EVENT": "EVENT",
            "DATE": "DATE",
            "TIME": "TIME",
            "PERCENT": "PERCENTAGE",
            "MONEY": "MONEY",
            "QUANTITY": "QUANTITY",
            "CARDINAL": "NUMBER",
            "ORDINAL": "ORDINAL",
        }
        return mapping.get(spacy_label, spacy_label)

    def extract_keywords(self, text: str, top_n: int = 10) -> list[str]:
        """Extrai palavras-chave do texto usando TF simples.

        Args:
            text: Texto processado
            top_n: Número de palavras-chave

        Returns:
            Lista de palavras-chave
        """
        if not text:
            return []

        # Tokenizar e filtrar stop words simples
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())

        # Contar frequência
        from collections import Counter

        stop_words = {
            "que",
            "para",
            "como",
            "onde",
            "qual",
            "este",
            "esta",
            "isto",
            "the",
            "a",
            "an",
            "of",
            "to",
            "in",
            "is",
            "it",
            "that",
            "que",
            "para",
            "con",
            "como",
            "donde",
            "este",
            "esta",
        }

        filtered = [w for w in words if w not in stop_words and len(w) > 2]
        counter = Counter(filtered)

        return [word for word, _ in counter.most_common(top_n)]

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcula similaridade entre dois textos.

        Args:
            text1: Primeiro texto
            text2: Segundo texto

        Returns:
            Score de similaridade (0-1)
        """
        if not text1 or not text2:
            return 0.0

        # Similaridade simples por overlap de palavras
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union) if union else 0.0

    def truncate(self, text: str, max_length: int = 500) -> str:
        """Trunca texto preservando palavras completas.

        Args:
            text: Texto original
            max_length: Comprimento máximo

        Returns:
            Texto truncado
        """
        if len(text) <= max_length:
            return text

        truncated = text[:max_length]
        # Encontrar último espaço completo
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.8:  # Se não reduzir muito
            truncated = truncated[:last_space]

        return truncated.strip() + "..."

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do processador.

        Returns:
            Estatísticas atuais
        """
        return {
            "pii_masking_enabled": self.enable_pii_masking,
            "pii_mask_strategy": self.pii_mask_strategy,
            "entity_extraction_enabled": self.enable_entity_extraction,
            "pii_available": PII_MASKING_AVAILABLE,
        }
