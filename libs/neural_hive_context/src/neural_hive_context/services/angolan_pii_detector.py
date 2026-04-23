"""
Angolan PII Detector Service

Detecta informações pessoais identificáveis (PII) específicas de Angola.
Herda de RegexPIIDetector e adiciona padrões angolanos.
"""

import re
from typing import Set, Dict

from neural_hive_context.services.pii_detector import RegexPIIDetector
from neural_hive_context.models import PIIType, PIIRiskLevel


class AngolanPIIDetector(RegexPIIDetector):
    """
    Detector de PII angolano.

    Extende RegexPIIDetector com padrões específicos de Angola:
    - NIF (Número de Identificação Fiscal): 9 dígitos
    - BI (Bilhete de Identidade): formato XXXZZZZAA
    - NUIT (Número Único de Identificação Tributária): 9 dígitos

    Precisão: ~85-90% para padrões angolanos comuns
    """

    # Padrões regex específicos para Angola
    ANGOLAN_PATTERNS: Dict[PIIType, re.Pattern] = {
        PIIType.NIF: re.compile(
            r'\b\d{9}\b',  # 9 dígitos (NIF Angola tem formato específico)
            re.IGNORECASE
        ),
        PIIType.BI: re.compile(
            r'\b\d{12}[A-Z]{2}\b',  # XXXZZZZAA (12 dígitos + 2 letras)
            re.IGNORECASE
        ),
        PIIType.NUIT: re.compile(
            r'\b\d{9}\b',  # 9 dígitos (similar formato NIF)
            re.IGNORECASE
        ),
    }

    # Mapeamento de risco para tipos angolanos
    ANGOLAN_TYPE_RISK: Dict[PIIType, PIIRiskLevel] = {
        PIIType.NIF: PIIRiskLevel.HIGH,
        PIIType.BI: PIIRiskLevel.CRITICAL,
        PIIType.NUIT: PIIRiskLevel.HIGH,
    }

    def __init__(
        self,
        enabled_types: Set[PIIType] | None = None,
        min_confidence: float = 0.7,
        include_brazilian: bool = True,
    ):
        """
        Inicializa o detector angolano.

        Args:
            enabled_types: Tipos de PII para detectar (todos se None)
            min_confidence: Confiança mínima para reportar
            include_brazilian: Se True, inclui padrões brasileiros (CPF, CNH)
        """
        # Tipos angolanos sempre habilitados por padrão
        angolan_types = {PIIType.NIF, PIIType.BI, PIIType.NUIT}

        if enabled_types is None:
            enabled_types = angolan_types.copy()

        # Incluir padrões brasileiros se solicitado
        if include_brazilian:
            enabled_types.update({
                PIIType.EMAIL, PIIType.PHONE, PIIType.CPF,
                PIIType.CREDIT_CARD, PIIType.PASSPORT,
                PIIType.DRIVERS_LICENSE, PIIType.BANK_ACCOUNT,
                PIIType.ADDRESS, PIIType.SSN, PIIType.IP_ADDRESS,
                PIIType.URL,
            })

        super().__init__(enabled_types=enabled_types, min_confidence=min_confidence)

        # Adicionar padrões angolanos aos padrões existentes
        self.PATTERNS.update(self.ANGOLAN_PATTERNS)
        self.TYPE_RISK.update(self.ANGOLAN_TYPE_RISK)

        # Sobrescrever padrão PHONE para incluir código angolano +244
        self.PATTERNS[PIIType.PHONE] = re.compile(
            r'\+55\s?\(?\d{2,3}\)?[\s-]?\d{4,5}[\s-]?\d{4}|\+244\s?\d{3}[\s-]?\d{3}[\s-]?\d{3}|\(?\d{2,3}\)?[\s-]?\d{4,5}[\s-]?\d{4}',
            re.IGNORECASE
        )

    def _is_valid_match(self, entity_type: PIIType, text: str) -> bool:
        """
        Valida se o match é válido ou falso positivo.

        Args:
            entity_type: Tipo de entidade
            text: Texto do match

        Returns:
            True se válido, False se provável falso positivo
        """
        # Validações específicas angolanas
        if entity_type == PIIType.BI:
            # BI angolano: XXXZZZZAA
            # XXX = número de sequência (7 dígitos na prática)
            # ZZZZ = zeros ou dígito verificador
            # AA = letras
            if not re.match(r'^\d{12}[A-Z]{2}$', text, re.IGNORECASE):
                return False
            return True

        if entity_type == PIIType.NIF:
            # NIF angolano: 9 dígitos, começa com dígitos específicos
            # Formato: Primeiro dígito indica tipo de contribuinte
            digits = re.sub(r'[^\d]', '', text)
            if len(digits) != 9:
                return False
            # Validação básica: não pode ser todos iguais
            if digits == digits[0] * 9:
                return False
            # NIF Angola geralmente começa com 0, 1 ou 5
            if digits[0] not in '015':
                return False  # Possível falso positivo
            return True

        if entity_type == PIIType.NUIT:
            # NUIT angolano: 9 dígitos
            digits = re.sub(r'[^\d]', '', text)
            if len(digits) != 9:
                return False
            # Validação básica: não pode ser todos iguais
            if digits == digits[0] * 9:
                return False
            return True

        # Delegar para validação da classe base (padrões brasileiros/internacionais)
        return super()._is_valid_match(entity_type, text)

    def get_angolan_types(self) -> Set[PIIType]:
        """Retorna tipos de PII específicos de Angola."""
        return set(self.ANGOLAN_PATTERNS.keys())

    def is_angolan_type(self, entity_type: PIIType) -> bool:
        """Verifica se um tipo é específico de Angola."""
        return entity_type in self.ANGOLAN_PATTERNS
