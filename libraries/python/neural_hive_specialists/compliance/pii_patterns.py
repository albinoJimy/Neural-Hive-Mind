"""
PII Patterns para detecção via regex.

Contém patterns compilados para detecção de PII global, europeu e brasileiro.
"""
import re
import structlog
from enum import Enum
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

logger = structlog.get_logger(__name__)


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
        # Nota: re.IGNORECASE já lida com case, portanto [a-z] é suficiente
        regex=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}\b",
        mask_strategy="partial",
        show_first=1,
        show_last=0,  # j***@domain.com
    ),
    PIIPattern(
        type=PIIType.PHONE,
        category=PIICategory.GLOBAL,
        regex=r"(\+\d{1,3}[\s-]?)?(\d{2,3}[\s-]?)?(\d{4,5}[\s-]?)(\d{4})",
        mask_strategy="partial",
        show_first=6,
        show_last=4,  # +351 912 *** ***
    ),
    PIIPattern(
        type=PIIType.IP_ADDRESS,
        category=PIICategory.GLOBAL,
        regex=r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        mask_strategy="partial",
        show_first=4,
        show_last=2,  # 192.168.*.*
    ),
    # Nota: IPv6 pattern não suporta notação comprimida (::), mas aceitável para implementação inicial
    PIIPattern(
        type=PIIType.IP_ADDRESS,
        category=PIICategory.GLOBAL,
        regex=r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
        mask_strategy="partial",
        show_first=4,
        show_last=4,  # 2001:db8::***:****
    ),
    PIIPattern(
        type=PIIType.CREDIT_CARD,
        category=PIICategory.GLOBAL,
        regex=r"\b(?:\d[ -]*?){13,19}\b",
        mask_strategy="partial",
        show_first=4,
        show_last=4,  # 4532 **** **** 1234
    ),
    PIIPattern(
        type=PIIType.UUID,
        category=PIICategory.GLOBAL,
        regex=r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        mask_strategy="partial",
        show_first=8,
        show_last=4,  # 12345678-****-****-****-************
    ),
    # API_KEY: Pattern genérico, deve ser usado com contexto adicional (prefixos como "sk_", "apiKey", etc.)
    PIIPattern(
        type=PIIType.API_KEY,
        category=PIICategory.GLOBAL,
        regex=r"\b[A-Za-z0-9]{20,}\b",
        mask_strategy="hash",
    ),
    # === EUROPEU ===
    # NIF (Portugal): 9 dígitos. Nota: Pattern genérico pode gerar falsos positivos,
    # deve ser usado em contexto com validação adicional (dígito de controle)
    PIIPattern(
        type=PIIType.NIF,
        category=PIICategory.EUROPEAN,
        regex=r"\b\d{9}\b",
        mask_strategy="partial",
        show_first=3,
        show_last=2,  # 123***45
    ),
    PIIPattern(
        type=PIIType.IBAN,
        category=PIICategory.EUROPEAN,
        regex=r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b",
        mask_strategy="partial",
        show_first=4,
        show_last=4,  # PT12********1234
    ),
    PIIPattern(
        type=PIIType.PASSPORT,
        category=PIICategory.EUROPEAN,
        regex=r"\b[A-Z]{1,2}[0-9]{6,9}\b",
        mask_strategy="partial",
        show_first=1,
        show_last=1,  # P1234567*
    ),
    PIIPattern(
        type=PIIType.SSN,
        category=PIICategory.EUROPEAN,
        regex=r"\b\d{3}-\d{2}-\d{4}\b",
        mask_strategy="partial",
        show_first=3,
        show_last=4,  # 123-**-****
    ),
    # === BRASILEIRO ===
    PIIPattern(
        type=PIIType.CPF,
        category=PIICategory.BRAZILIAN,
        regex=r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
        mask_strategy="partial",
        show_first=6,
        show_last=2,  # 123.456.***-**
    ),
    PIIPattern(
        type=PIIType.CNPJ,
        category=PIICategory.BRAZILIAN,
        regex=r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
        mask_strategy="partial",
        show_first=8,
        show_last=2,  # 12.345.678/***-**
    ),
    # RG: Pattern genérico devido à variação entre estados. Formato típico: XX###XXX ou X###XXX#
    PIIPattern(
        type=PIIType.RG,
        category=PIICategory.BRAZILIAN,
        regex=r"\b\d{1,2}[A-Z]{0,2}\d{3}[A-Z0-9]{0,2}\b",
        mask_strategy="partial",
        show_first=2,
        show_last=1,
    ),
    PIIPattern(
        type=PIIType.TITULO_ELEITOR,
        category=PIICategory.BRAZILIAN,
        regex=r"\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b",
        mask_strategy="partial",
        show_first=4,
        show_last=4,  # 1234 5678 **** ****
    ),
    PIIPattern(
        type=PIIType.BANK_ACCOUNT,
        category=PIICategory.BRAZILIAN,
        regex=r"\b\d{3,}-?\d{5,}-?\d{1}\b",
        mask_strategy="partial",
        show_first=3,
        show_last=1,  # 123-*****-*
    ),
]


class PIIPatternRegistry:
    """Registry para patterns compilados e lookup rápido."""

    def __init__(self):
        self._patterns_by_type: Dict[PIIType, List[Tuple[PIIPattern, re.Pattern]]] = {}
        self._patterns_by_category: Dict[PIICategory, List[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        """Compila patterns regex."""
        for pii_def in PII_PATTERNS:
            try:
                compiled = re.compile(pii_def.regex, pii_def.flags)

                if pii_def.type not in self._patterns_by_type:
                    self._patterns_by_type[pii_def.type] = []
                self._patterns_by_type[pii_def.type].append((pii_def, compiled))

                if pii_def.category not in self._patterns_by_category:
                    self._patterns_by_category[pii_def.category] = []
                self._patterns_by_category[pii_def.category].append(compiled)
            except re.error as e:
                logger.warning(
                    "failed_to_compile_pii_pattern",
                    pattern=pii_def.regex,
                    pii_type=str(pii_def.type),
                    error=str(e),
                )

    def get_pattern(self, pii_type: PIIType) -> Optional[re.Pattern]:
        """Obtém primeiro pattern compilado por tipo (para compatibilidade)."""
        patterns = self._patterns_by_type.get(pii_type)
        return patterns[0][1] if patterns else None

    def get_patterns(self, pii_type: PIIType) -> List[Tuple[PIIPattern, re.Pattern]]:
        """Obtém todos os patterns compilados por tipo."""
        return self._patterns_by_type.get(pii_type, [])

    def get_patterns_by_category(self, category: PIICategory) -> List[Tuple[PIIType, re.Pattern]]:
        """Obtém patterns por categoria."""
        result = []
        for pii_def in PII_PATTERNS:
            if pii_def.category == category:
                compiled = self.get_pattern(pii_def.type)
                if compiled:
                    result.append((pii_def.type, compiled))
        return result

    def get_all_types(self) -> List[PIIType]:
        """Retorna todos os tipos suportados."""
        return list(self._patterns_by_type.keys())


# Singleton - inicializado no carregamento do módulo (mais simples, thread-safe)
_registry = PIIPatternRegistry()


def get_pattern_registry() -> PIIPatternRegistry:
    """Retorna registry singleton."""
    return _registry
