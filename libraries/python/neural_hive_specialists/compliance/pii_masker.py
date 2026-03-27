"""
PII Masker - Mascaramento parcial de informações sensíveis.

Aplica mascaramento parcial baseado em regras por tipo de PII.
"""
import re
import hashlib
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from .pii_patterns import PIIType, PIICategory, get_pattern_registry, PII_PATTERNS


class MaskStrategy(str, Enum):
    """Estratégia de mascaramento."""

    PARTIAL = "partial"  # Mostra primeiro/último caracteres
    FULL = "full"  # Substitui por tag
    HASH = "hash"  # Substitui por hash
    REDACT = "redact"  # Remove completamente


@dataclass
class PIIEntity:
    """Entidade PII detectada."""

    type: PIIType
    category: PIICategory
    value: str
    start: int
    end: int
    confidence: float = 1.0
    masked_value: Optional[str] = None


@dataclass
class MaskResult:
    """Resultado de mascaramento."""

    text: str
    entities: List[PIIEntity]
    metadata: Dict[str, int]


class PIIMasker:
    """
    Aplica mascaramento parcial a PII em texto.

    Suporta:
    - Mascaramento parcial (preserva formato)
    - Múltiplos tipos de PII
    - Configuração por tipo
    - Estatísticas de mascaramento
    """

    def __init__(
        self,
        strategy: MaskStrategy = MaskStrategy.PARTIAL,
        mask_char: str = "*",
        min_chars_to_preserve: int = 1,
        enable_spacy: bool = True,
    ):
        """
        Inicializa masker.

        Args:
            strategy: Estratégia de mascaramento padrão
            mask_char: Carácter para mascaramento
            min_chars_to_preserve: Mínimo de caracteres a preservar
            enable_spacy: Usar spaCy NER para detecção NLP
        """
        self.strategy = strategy
        self.mask_char = mask_char
        self.min_chars_to_preserve = min_chars_to_preserve
        self.enable_spacy = enable_spacy

        # Carregar patterns
        self.pattern_registry = get_pattern_registry()

        # Mapear estratégias por tipo (override)
        self.type_strategies: Dict[PIIType, dict] = {}
        for pii_def in PII_PATTERNS:
            self.type_strategies[pii_def.type] = {
                "strategy": pii_def.mask_strategy,
                "show_first": pii_def.show_first,
                "show_last": pii_def.show_last,
                "preserve_format": pii_def.preserve_format,
            }

        # Carregar spaCy se habilitado
        self._nlp = None
        if enable_spacy:
            self._load_spacy()

    def _load_spacy(self):
        """Carrega modelo spaCy para NER."""
        try:
            import spacy

            try:
                self._nlp = spacy.load("pt_core_news_sm")
            except OSError:
                # Fallback para inglês
                self._nlp = spacy.load("en_core_web_sm")
        except Exception:
            # Captura ImportError, ValueError (numpy compat), e outros erros
            self._nlp = None

    def mask(
        self,
        text: str,
        types_to_mask: Optional[List[PIIType]] = None,
        strategy: Optional[MaskStrategy] = None,
    ) -> MaskResult:
        """
        Mascara PII em texto.

        Args:
            text: Texto para mascarar
            types_to_mask: Tipos específicos para mascarar (todos se None)
            strategy: Override de estratégia

        Returns:
            MaskResult com texto mascarado e entidades detectadas
        """
        if not text:
            return MaskResult(
                text="", entities=[], metadata={"total": 0, "by_type": {}}
            )

        entities = self._detect_entities(text, types_to_mask)

        # Ordenar por start (reverso para não quebrar índices)
        entities_sorted = sorted(entities, key=lambda e: e.start, reverse=True)

        # Remove overlapping entities (keep longer matches)
        filtered_entities = []
        for entity in entities_sorted:
            if not any(
                e.start < entity.end and e.end > entity.start for e in filtered_entities
            ):
                filtered_entities.append(entity)
        entities_sorted = filtered_entities

        masked_text = text
        stats = {"total": 0, "by_type": {}}

        for entity in entities_sorted:
            # Aplicar mascaramento
            masked_value = self._apply_mask(entity, strategy or self.strategy)
            entity.masked_value = masked_value

            # Substituir no texto
            masked_text = (
                masked_text[: entity.start] + masked_value + masked_text[entity.end :]
            )

            # Estatísticas
            stats["total"] += 1
            stats["by_type"][entity.type.value] = (
                stats["by_type"].get(entity.type.value, 0) + 1
            )

        return MaskResult(text=masked_text, entities=entities_sorted, metadata=stats)

    def _detect_entities(
        self, text: str, types_to_mask: Optional[List[PIIType]]
    ) -> List[PIIEntity]:
        """Detecta entidades PII via regex e spaCy."""
        entities = []

        # Detecção via regex
        all_types = types_to_mask or self.pattern_registry.get_all_types()

        for pii_type in all_types:
            pattern = self.pattern_registry.get_pattern(pii_type)
            if pattern is None:
                continue

            for match in pattern.finditer(text):
                # Encontrar definição para obter categoria
                category = self._get_category_for_type(pii_type)

                entities.append(
                    PIIEntity(
                        type=pii_type,
                        category=category,
                        value=match.group(),
                        start=match.start(),
                        end=match.end(),
                    )
                )

        # Detecção via spaCy NER
        if self._nlp:
            entities.extend(self._detect_with_spacy(text, types_to_mask))

        return entities

    def _detect_with_spacy(
        self, text: str, types_to_mask: Optional[List[PIIType]]
    ) -> List[PIIEntity]:
        """Detecta entidades usando spaCy NER."""
        if not self._nlp:
            return []

        entities = []
        doc = self._nlp(text)

        # Mapear spaCy labels para PIIType
        spacy_mapping = {
            "PERSON": PIIType.PERSON,
            "ORG": PIIType.ORG,
            "GPE": PIIType.GPE,
            "LOC": PIIType.LOC,
            "DATE": PIIType.DATE,
            "MONEY": PIIType.MONEY,
        }

        for ent in doc.ents:
            pii_type = spacy_mapping.get(ent.label_)
            if pii_type is None:
                continue

            # Filtrar se types_to_mask especificado
            if types_to_mask and pii_type not in types_to_mask:
                continue

            entities.append(
                PIIEntity(
                    type=pii_type,
                    category=PIICategory.NLP,
                    value=ent.text,
                    start=ent.start_char,
                    end=ent.end_char,
                )
            )

        return entities

    def _apply_mask(self, entity: PIIEntity, strategy: MaskStrategy) -> str:
        """Aplica mascaramento a uma entidade."""
        value = entity.value
        length = len(value)

        # Obter configuração específica do tipo
        type_config = self.type_strategies.get(entity.type, {})
        # Se strategy explicitamente passada, usar ela; senão usar do tipo
        if strategy == MaskStrategy.PARTIAL:
            entity_strategy = MaskStrategy(
                type_config.get("strategy", MaskStrategy.PARTIAL.value)
            )
        else:
            entity_strategy = strategy

        if entity_strategy == MaskStrategy.FULL:
            return f"[{entity.type.value}]"

        elif entity_strategy == MaskStrategy.HASH:
            hash_val = hashlib.sha256(value.encode()).hexdigest()[:8]
            return f"{hash_val}..."

        elif entity_strategy == MaskStrategy.REDACT:
            return ""

        else:  # PARTIAL
            show_first = type_config.get("show_first", self.min_chars_to_preserve)
            show_last = type_config.get("show_last", 0)
            preserve_format = type_config.get("preserve_format", True)

            # Para valores curtos, garantir mínimo
            if length <= show_first + show_last:
                show_first = max(1, length // 2)
                show_last = length - show_first

            if preserve_format:
                # Preservar caracteres especiais
                return self._mask_preserving_format(value, show_first, show_last)
            else:
                # Mascaramento simples
                first = value[:show_first]
                last = value[-show_last:] if show_last > 0 else ""
                middle = self.mask_char * (length - show_first - show_last)
                return first + middle + last

    def _mask_preserving_format(
        self, value: str, show_first: int, show_last: int
    ) -> str:
        """Mascara preservando caracteres especiais."""
        # Preservar formato: manter não-alfanuméricos
        result = []
        visible_count = 0

        for char in value:
            if char.isalnum() and visible_count < show_first:
                result.append(char)
                visible_count += 1
            elif char.isalnum() and visible_count >= len(value) - show_last:
                result.append(char)
                visible_count += 1
            elif char.isalnum():
                result.append(self.mask_char)
            else:
                result.append(char)  # Preservar separadores

        return "".join(result)

    def _get_category_for_type(self, pii_type: PIIType) -> PIICategory:
        """Obtém categoria para tipo de PII."""
        for pii_def in PII_PATTERNS:
            if pii_def.type == pii_type:
                return pii_def.category
        return PIICategory.GLOBAL


def create_masker(
    strategy: MaskStrategy = MaskStrategy.PARTIAL,
    mask_char: str = "*",
    min_chars_to_preserve: int = 1,
    enable_spacy: bool = True,
) -> PIIMasker:
    """
    Factory para criar PIIMasker com configurações padrão.

    Args:
        strategy: Estratégia de mascaramento padrão
        mask_char: Carácter para mascaramento
        min_chars_to_preserve: Mínimo de caracteres a preservar
        enable_spacy: Usar spaCy NER para detecção NLP

    Returns:
        Instância configurada de PIIMasker
    """
    return PIIMasker(
        strategy=strategy,
        mask_char=mask_char,
        min_chars_to_preserve=min_chars_to_preserve,
        enable_spacy=enable_spacy,
    )
