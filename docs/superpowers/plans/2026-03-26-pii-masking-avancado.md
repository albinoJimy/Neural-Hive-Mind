# PII Masking Avançado - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sistema de mascaramento parcial de PII usando regex + spaCy NER, sem dependência do Presidio, integrado no gateway.

**Architecture:** Biblioteca compartilhada em `neural_hive_specialists/compliance/` com detecção via regex+spaCy e mascaramento parcial configurável. Integração no NLU Pipeline do gateway substituindo `_mask_pii()`.

**Tech Stack:** Python 3.12+, spaCy (pt_core_news_sm), regex, Pydantic

---

## Estrutura de Ficheiros

```
libraries/python/neural_hive_specialists/
├── compliance/
│   ├── __init__.py              # Exportar novos componentes
│   ├── pii_detector.py           # EXPANDE: adicionar PIIDetectorLite
│   ├── pii_masker.py             # NOVO: mascaramento parcial
│   └── pii_patterns.py           # NOVO: patterns regex por tipo
│
services/gateway-intencoes/
├── src/pipelines/
│   └── nlu_pipeline.py           # MODIFY: substituir _mask_pii()
│
tests/
├── libraries/python/neural_hive_specialists/tests/compliance/
│   ├── test_pii_masker.py       # NOVO
│   └── test_pii_patterns.py     # NOVO
```

---

## Task 1: Criar patterns PII

**Files:**
- Create: `libraries/python/neural_hive_specialists/compliance/pii_patterns.py`
- Test: `tests/libraries/python/neural_hive_specialists/tests/compliance/test_pii_patterns.py`

- [ ] **Step 1: Criar ficheiro com patterns**

```python
"""
PII Patterns para detecção via regex.

Contém patterns compilados para detecção de PII global, europeu e brasileiro.
"""
import re
from enum import Enum
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


class PIICategory(str, Enum):
    """Categoria de PII"""
    GLOBAL = "global"
    EUROPEAN = "european"
    BRAZILIAN = "brazilian"
    NLP = "nlp"  # Detectado via spaCy NER


class PIIType(str, Enum):
    """Tipos de PII suportados"""
    # Global
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    IP_ADDRESS = "IP_ADDRESS"
    CREDIT_CARD = "CREDIT_CARD"
    UUID = "UUID"
    API_KEY = "API_KEY"

    # Europeu
    NIF = "NIF"  # Portugal
    IBAN = "IBAN"
    PASSPORT = "PASSPORT"
    SSN = "SSN"  # USA/UK
    POSTAL_CODE = "POSTAL_CODE"

    # Brasileiro
    CPF = "CPF"
    CNPJ = "CNPJ"
    RG = "RG"
    TITULO_ELEITOR = "TITULO_ELEITOR"
    BANK_ACCOUNT = "BANK_ACCOUNT"

    # NLP (spaCy)
    PERSON = "PERSON"
    ORG = "ORG"
    GPE = "GPE"  # Geopolitical Entity
    LOC = "LOC"  # Location
    DATE = "DATE"
    MONEY = "MONEY"


@dataclass
class PIIPattern:
    """Pattern de PII com regex e estratégia de mascaramento"""
    type: PIIType
    category: PIICategory
    regex: str
    flags: int = re.IGNORECASE
    mask_strategy: str = "partial"  # partial | full | hash
    show_first: int = 0
    show_last: int = 0
    preserve_format: bool = True


# Patterns compilados
PII_PATTERNS: List[PIIPattern] = [
    # === GLOBAL ===
    PIIPattern(
        type=PIIType.EMAIL,
        category=PIICategory.GLOBAL,
        regex=r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        mask_strategy="partial",
        show_first=1,
        show_last=0,  # j***@domain.com
    ),
    PIIPattern(
        type=PIIType.PHONE,
        category=PIICategory.GLOBAL,
        regex=r'(\+\d{1,3}[\s-]?)?(\d{2,3}[\s-]?)?(\d{4,5}[\s-]?)(\d{4})',
        mask_strategy="partial",
        show_first=6,
        show_last=4,  # +351 912 *** ***
    ),
    PIIPattern(
        type=PIIType.IP_ADDRESS,
        category=PIICategory.GLOBAL,
        regex=r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        mask_strategy="partial",
        show_first=4,
        show_last=2,  # 192.168.*.*
    ),
    PIIPattern(
        type=PIIType.IP_ADDRESS,
        category=PIICategory.GLOBAL,
        regex=r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b',
        mask_strategy="partial",
        show_first=4,
        show_last=4,  # 2001:db8::***:****
    ),
    PIIPattern(
        type=PIIType.CREDIT_CARD,
        category=PIICategory.GLOBAL,
        regex=r'\b(?:\d[ -]*?){13,19}\b',
        mask_strategy="partial",
        show_first=4,
        show_last=4,  # 4532 **** **** 1234
    ),
    PIIPattern(
        type=PIIType.UUID,
        category=PIICategory.GLOBAL,
        regex=r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b',
        mask_strategy="partial",
        show_first=8,
        show_last=4,  # 12345678-****-****-****-************
    ),
    PIIPattern(
        type=PIIType.API_KEY,
        category=PIICategory.GLOBAL,
        regex=r'\b[A-Za-z0-9]{20,}\b',  # Generic, será refinado no contexto
        mask_strategy="hash",
    ),

    # === EUROPEU ===
    PIIPattern(
        type=PIIType.NIF,
        category=PIICategory.EUROPEAN,
        regex=r'\b\d{9}\b',
        mask_strategy="partial",
        show_first=3,
        show_last=2,  # 123***45
    ),
    PIIPattern(
        type=PIIType.IBAN,
        category=PIICategory.EUROPEAN,
        regex=r'\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b',
        mask_strategy="partial",
        show_first=4,
        show_last=4,  # PT12********1234
    ),
    PIIPattern(
        type=PIIType.PASSPORT,
        category=PIICategory.EUROPEAN,
        regex=r'\b[A-Z]{1,2}[0-9]{6,9}\b',
        mask_strategy="partial",
        show_first=1,
        show_last=1,  # P1234567*
    ),
    PIIPattern(
        type=PIIType.SSN,
        category=PIICategory.EUROPEAN,
        regex=r'\b\d{3}-\d{2}-\d{4}\b',
        mask_strategy="partial",
        show_first=3,
        show_last=4,  # 123-**-****
    ),

    # === BRASILEIRO ===
    PIIPattern(
        type=PIIType.CPF,
        category=PIICategory.BRAZILIAN,
        regex=r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b',
        mask_strategy="partial",
        show_first=6,
        show_last=2,  # 123.456.***-**
    ),
    PIIPattern(
        type=PIIType.CNPJ,
        category=PIICategory.BRAZILIAN,
        regex=r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
        mask_strategy="partial",
        show_first=8,
        show_last=2,  # 12.345.678/***-**
    ),
    PIIPattern(
        type=PIIType.RG,
        category=PIICategory.BRAZILIAN,
        regex=r'\b\d{1,2}[A-Z]{0,}\d{3}[A-Z]{0,}\b',
        mask_strategy="partial",
        show_first=2,
        show_last=1,
    ),
    PIIPattern(
        type=PIIType.TITULO_ELEITOR,
        category=PIICategory.BRAZILIAN,
        regex=r'\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b',
        mask_strategy="partial",
        show_first=4,
        show_last=4,  # 1234 5678 **** ****
    ),
    PIIPattern(
        type=PIIType.BANK_ACCOUNT,
        category=PIICategory.BRAZILIAN,
        regex=r'\b\d{3,}-?\d{5,}-?\d{1}\b',
        mask_strategy="partial",
        show_first=3,
        show_last=1,  # 123-*****-*
    ),
]


class PIIPatternRegistry:
    """Registry para patterns compilados e lookup rápido."""

    def __init__(self):
        self._patterns_by_type: Dict[PIIType, re.Pattern] = {}
        self._patterns_by_category: Dict[PIICategory, List[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        """Compila patterns regex."""
        for pii_def in PII_PATTERNS:
            try:
                compiled = re.compile(pii_def.regex, pii_def.flags)
                self._patterns_by_type[pii_def.type] = compiled

                if pii_def.category not in self._patterns_by_category:
                    self._patterns_by_category[pii_def.category] = []
                self._patterns_by_category[pii_def.category].append(compiled)
            except re.error as e:
                # Log mas não falhar
                pass

    def get_pattern(self, pii_type: PIIType) -> Optional[re.Pattern]:
        """Obtém pattern compilado por tipo."""
        return self._patterns_by_type.get(pii_type)

    def get_patterns_by_category(self, category: PIICategory) -> List[Tuple[PIIType, re.Pattern]]:
        """Obtém patterns por categoria."""
        patterns = self._patterns_by_category.get(category, [])
        return [
            (ptype, pattern)
            for ptype, pattern in self._patterns_by_type.items()
            if pattern in patterns
        ]

    def get_all_types(self) -> List[PIIType]:
        """Retorna todos os tipos suportados."""
        return list(self._patterns_by_type.keys())


# Singleton
_registry = None

def get_pattern_registry() -> PIIPatternRegistry:
    """Retorna registry singleton."""
    global _registry
    if _registry is None:
        _registry = PIIPatternRegistry()
    return _registry
```

- [ ] **Step 2: Criar testes dos patterns**

```python
"""Testes de PII patterns."""
import pytest
from neural_hive_specialists.compliance.pii_patterns import (
    PIIType, PIICategory, get_pattern_registry
)


class TestPIIPatterns:
    """Testa registry de patterns."""

    def test_registry_initialization(self):
        registry = get_pattern_registry()
        assert registry is not None

    def test_email_pattern(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.EMAIL)
        assert pattern is not None
        assert pattern.search("user@example.com")

    def test_cpf_pattern(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.CPF)
        assert pattern.search("123.456.789-00")

    def test_ip_address_pattern(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.IP_ADDRESS)
        assert pattern.search("192.168.1.1")

    def test_get_all_types(self):
        registry = get_pattern_registry()
        types = registry.get_all_types()
        assert PIIType.EMAIL in types
        assert PIIType.CPF in types
```

- [ ] **Step 3: Commit**

```bash
git add libraries/python/neural_hive_specialists/compliance/pii_patterns.py
git add tests/libraries/python/neural_hive_specialists/tests/compliance/test_pii_patterns.py
git commit -m "feat(compliance): add PII patterns registry with regex for Global/EU/BR types"
```

---

## Task 2: Criar PIIMasker

**Files:**
- Create: `libraries/python/neural_hive_specialists/compliance/pii_masker.py`
- Test: `tests/libraries/python/neural_hive_specialists/tests/compliance/test_pii_masker.py`

- [ ] **Step 1: Criar ficheiro PIIMasker**

```python
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
    FULL = "full"        # Substitui por tag
    HASH = "hash"        # Substitui por hash
    REDACT = "retract"   # Remove completamente


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
        except ImportError:
            self._nlp = None

    def mask(
        self,
        text: str,
        types_to_mask: Optional[List[PIIType]] = None,
        strategy: Optional[MaskStrategy] = None
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
            return MaskResult(text="", entities=[], metadata={"count": 0})

        entities = self._detect_entities(text, types_to_mask)

        # Ordenar por start (reverso para não quebrar índices)
        entities_sorted = sorted(entities, key=lambda e: e.start, reverse=True)

        masked_text = text
        stats = {"total": 0, "by_type": {}}

        for entity in entities_sorted:
            # Aplicar mascaramento
            masked_value = self._apply_mask(entity, strategy or self.strategy)
            entity.masked_value = masked_value

            # Substituir no texto
            masked_text = (
                masked_text[:entity.start] + masked_value + masked_text[entity.end:]
            )

            # Estatísticas
            stats["total"] += 1
            stats["by_type"][entity.type.value] = stats["by_type"].get(entity.type.value, 0) + 1

        return MaskResult(text=masked_text, entities=entities_sorted, metadata=stats)

    def _detect_entities(
        self,
        text: str,
        types_to_mask: Optional[List[PIIType]]
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

                entities.append(PIIEntity(
                    type=pii_type,
                    category=category,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                ))

        # Detecção via spaCy NER
        if self._nlp:
            entities.extend(self._detect_with_spacy(text, types_to_mask))

        return entities

    def _detect_with_spacy(
        self,
        text: str,
        types_to_mask: Optional[List[PIIType]]
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

            # Filtrar se tipos_to_mask especificado
            if types_to_mask and pii_type not in types_to_mask:
                continue

            entities.append(PIIEntity(
                type=pii_type,
                category=PIICategory.NLP,
                value=ent.text,
                start=ent.start_char,
                end=ent.end_char,
            ))

        return entities

    def _apply_mask(self, entity: PIIEntity, strategy: MaskStrategy) -> str:
        """Aplica mascaramento a uma entidade."""
        value = entity.value
        length = len(value)

        # Obter configuração específica do tipo
        type_config = self.type_strategies.get(entity.type, {})
        entity_strategy = MaskStrategy(type_config.get("strategy", strategy.value))

        if entity_strategy == MaskStrategy.FULL:
            return f"[{entity.type.value}]"

        elif entity_strategy == MaskStrategy.HASH:
            hash_val = hashlib.sha256(value.encode()).hexdigest()[:8]
            return f"{hash_val}..."

        elif entity_strategy == MaskStrategy.RETRACT:
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
                return self._mask_preserving_format(
                    value, show_first, show_last
                )
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


def create_masker(**kwargs) -> PIIMasker:
    """Factory para criar PIIMasker."""
    return PIIMasker(**kwargs)
```

- [ ] **Step 2: Criar testes do masker**

```python
"""Testes de PII Masker."""
import pytest
from neural_hive_specialists.compliance.pii_masker import (
    PIIMasker, MaskStrategy, MaskResult, PIIType, create_masker
)


class TestPIIMasker:
    """Testa mascaramento de PII."""

    def test_mask_email_partial(self):
        masker = create_masker(strategy=MaskStrategy.PARTIAL)
        result = masker.mask("Contact: john@example.com")
        assert "john@example.com" not in result.text
        assert "j***" in result.text or "jo***" in result.text

    def test_mask_cpf_partial(self):
        masker = create_masker()
        result = masker.mask("CPF: 123.456.789-00")
        assert "123.456.***-**" == result.text
        assert result.metadata["total"] == 1

    def test_mask_phone_preserves_format(self):
        masker = create_masker()
        result = masker.mask("+351 912 345 678")
        assert "+351" in result.text
        assert "***" in result.text

    def test_full_masking_strategy(self):
        masker = create_masker(strategy=MaskStrategy.FULL)
        result = masker.mask("Email: test@example.com")
        assert "[EMAIL]" in result.text

    def test_multiple_entities(self):
        masker = create_masker()
        result = masker.mask("João Silva - CPF: 123.456.789-00")
        assert result.metadata["total"] >= 1
```

- [ ] **Step 3: Commit**

```bash
git add libraries/python/neural_hive_specialists/compliance/pii_masker.py
git add tests/libraries/python/neural_hive_specialists/tests/compliance/test_pii_masker.py
git commit -m "feat(compliance): add PIIMasker with partial masking and spacy NER integration"
```

---

## Task 3: Expandir PIIDetector com versão Lite

**Files:**
- Modify: `libraries/python/neural_hive_specialists/compliance/pii_detector.py`
- Modify: `libraries/python/neural_hive_specialists/compliance/__init__.py`

- [ ] **Step 1: Adicionar PIIDetectorLite no pii_detector.py**

No final do ficheiro `pii_detector.py`, adicionar:

```python
# === VERSÃO LITE (sem Presidio) ===

class PIIDetectorLite:
    """
    Versão leve de detecção de PII sem dependência do Presidio.

    Usa regex + spaCy para detecção e integra com PIIMasker para
    mascaramento. Ideal para serviços onde o Presidio é muito pesado.
    """

    def __init__(self, config=None):
        """
        Inicializa detector lite.

        Args:
            config: Config (opcional, usa defaults se não fornecido)
        """
        from .pii_masker import PIIMasker, MaskStrategy
        from .pii_patterns import get_pattern_registry, PIIType

        self.masker = PIIMasker(
            strategy=MaskStrategy.PARTIAL,
            enable_spacy=True,
        )
        self.pattern_registry = get_pattern_registry()
        self.enabled = True

        logger = structlog.get_logger(__name__)
        logger.info("PIIDetectorLite initialized", strategy="partial")

    def detect_pii(self, text: str, language: str = "pt") -> List[Dict]:
        """
        Detecta PII em texto.

        Retorna lista de dicionários compatível com formato Presidio para
        fácil migração.
        """
        if not self.enabled or not text:
            return []

        result = self.masker.mask(text)

        # Converter para formato compatível
        detected = []
        for entity in result.entities:
            detected.append({
                "entity_type": entity.type.value,
                "start": entity.start,
                "end": entity.end,
                "score": entity.confidence,
                "value": entity.value,
            })

        return detected

    def anonymize_text(self, text: str, language: str = "pt") -> Tuple[str, List]:
        """
        Anonimiza texto (interface compatível com PIIDetector).
        """
        result = self.masker.mask(text)

        metadata = [
            {
                "entity_type": e.type.value,
                "start": e.start,
                "end": e.end,
                "score": e.confidence,
            }
            for e in result.entities
        ]

        return result.text, metadata

    def is_enabled(self) -> bool:
        """Verifica se detector está habilitado."""
        return self.enabled
```

- [ ] **Step 2: Atualizar exports no __init__.py**

```python
"""
Compliance layer para PII detection, encryption e auditing.
"""

from .pii_detector import PIIDetector, PIIDetectorLite
from .pii_masker import PIIMasker, MaskStrategy, create_masker
from .pii_patterns import PIIType, PIICategory, get_pattern_registry

__all__ = [
    "PIIDetector",
    "PIIDetectorLite",
    "PIIMasker",
    "MaskStrategy",
    "create_masker",
    "PIIType",
    "PIICategory",
    "get_pattern_registry",
]
```

- [ ] **Step 3: Commit**

```bash
git add libraries/python/neural_hive_specialists/compliance/pii_detector.py
git add libraries/python/neural_hive_specialists/compliance/__init__.py
git commit -m "feat(compliance): add PIIDetectorLite without Presidio dependency"
```

---

## Task 4: Integrar no NLU Pipeline do Gateway

**Files:**
- Modify: `services/gateway-intencoes/src/pipelines/nlu_pipeline.py`

- [ ] **Step 1: Atualizar imports no topo do ficheiro**

Adicionar após os imports existentes:

```python
from neural_hive_specialists.compliance import (
    PIIDetectorLite,
    PIIMasker,
    MaskStrategy,
    PIIType,
)
```

- [ ] **Step 2: Substituir método _mask_pii**

Localizar o método `_mask_pii` (linha ~1056) e substituir completamente:

```python
def _mask_pii(self, text: str) -> str:
    """
    Mascarar informações pessoais com sistema avançado.

    Usa PIIDetectorLite com regex + spaCy NER para detecção e
    PIIMasker para mascaramento parcial configurável.
    """
    try:
        # Usar detector lite (sem Presidio)
        detector = PIIDetectorLite()

        if not detector.is_enabled():
            # Fallback para método simples se detector desabilitado
            return self._mask_pii_simple(text)

        # Aplicar mascaramento
        masked_text, _ = detector.anonymize_text(text)

        return masked_text

    except Exception as e:
        # Fallback em caso de erro
        self.logger.warning("PII masking failed, using simple fallback", error=str(e))
        return self._mask_pii_simple(text)


def _mask_pii_simple(self, text: str) -> str:
    """Método simples de fallback (mantém compatibilidade)."""
    import re

    # Email
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]", text
    )
    # CPF
    text = re.sub(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", "[CPF]", text)
    # Telefone
    text = re.sub(r"\b\d{2}\s?\d{4,5}-?\d{4}\b", "[PHONE]", text)
    return text
```

- [ ] **Step 3: Testar no gateway**

```bash
cd /home/jimy/NHM/Neural-Hive-Mind/services/gateway-intencoes
python3 -m pytest tests/unit/test_nlu_pipeline.py::TestNLUPipeline::test_pii_masking -v
```

- [ ] **Step 4: Commit**

```bash
git add services/gateway-intencoes/src/pipelines/nlu_pipeline.py
git commit -m "feat(gateway): integrate advanced PII masking with PIIDetectorLite"
```

---

## Task 5: Actualizar feature-map.md

**Files:**
- Modify: `docs/feature-map.md`

- [ ] **Step 1: Actualizar Gateway para 100%**

Localizar linha do Gateway e actualizar:

```markdown
### Gateway de Intenções (100%)
- [x] NLU Pipeline
- [x] ASR Pipeline (voz)
- [x] Roteamento adaptativo
- [x] Cache Redis
- [x] Observabilidade
- [x] Segurança OAuth2/Keycloak
- [x] PII masking avançado - PIIDetectorLite com regex+spaCyNER, mascaramento parcial configurável
```

- [ ] **Step 2: Adicionar aos concluídos recentemente**

```markdown
- ✅ **PII Masking Avançado** (2026-03-26) - PIIDetectorLite + PIIMasker com regex+spaCy, mascaramento parcial, 15+ tipos de PII
```

- [ ] **Step 3: Commit**

```bash
git add docs/feature-map.md
git commit -m "docs: update feature-map with advanced PII masking completion"
```

---

## Task 6: Adicionar configuração ao settings

**Files:**
- Modify: `services/gateway-intencoes/src/config/settings.py`

- [ ] **Step 1: Adicionar configurações PII**

Adicionar à classe Settings:

```python
# PII Masking
enable_pii_masking: bool = Field(default=True)
pii_masking_strategy: str = Field(default="partial")
pii_masking_preserve_format: bool = Field(default=True)
pii_masking_spacy_model: str = Field(default="pt_core_news_sm")
```

- [ ] **Step 2: Commit**

```bash
git add services/gateway-intencoes/src/config/settings.py
git commit -m "feat(gateway): add PII masking configuration to settings"
```

---

## Resumo

**Total de tarefas:** 6
**Ficheiros a criar:** 4
**Ficheiros a modificar:** 3
**Testes a criar:** 3

**Ordem de execução:** Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6
