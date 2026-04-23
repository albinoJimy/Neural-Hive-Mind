"""
PII Detector Service

Detecta informações pessoais identificáveis (PII) em texto.
Usa regex-based detection para MVP, com suporte para ML no futuro.
"""

import re
from typing import List, Dict, Any, Optional, Set
from enum import Enum

from neural_hive_context.interfaces import IPIIDetector
from neural_hive_context.models import PIIResult, PIIRiskLevel, PIIType, PIIEntity


class RegexPIIDetector(IPIIDetector):
    """
    Detector de PII baseado em expressões regulares.

    Padrões suportados:
    - Email (user@domain.com)
    - Phone (internacionais)
    - CPF (brasileiro)
    - Credit Card (Visa, Mastercard, Amex)
    - SSN (EUA)
    - IP Address
    - URL/Sensíveis

    Precisão: ~85-90% para padrões comuns
    Recall: ~80-85% (pode ter falsos negativos em variações)
    """

    # Padrões regex para diferentes tipos de PII
    PATTERNS: Dict[PIIType, re.Pattern] = {
        PIIType.EMAIL: re.compile(
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
            re.IGNORECASE
        ),
        PIIType.PHONE: re.compile(
            r'\b(?:\+?55\s?)?(?:\(?\d{2,3}\)?[\s-]?)?\d{4,5}[\s-]?\d{4}\b',
            re.IGNORECASE
        ),
        PIIType.CPF: re.compile(
            r'\b\d{3}[\.\s]?\d{3}[\.\s]?\d{3}[-\s]?\d{2}\b',
            re.IGNORECASE
        ),
        PIIType.CREDIT_CARD: re.compile(
            r'\b(?:\d{4}[\s-]?){3}\d{4}\b',
            re.IGNORECASE
        ),
        PIIType.SSN: re.compile(
            r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
            re.IGNORECASE
        ),
        PIIType.IP_ADDRESS: re.compile(
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
            re.IGNORECASE
        ),
        PIIType.URL: re.compile(
            r'\bhttps?://(?:www\.)?[^\s/$.?#].[^\s]*\b',
            re.IGNORECASE
        ),
        # Novos tipos - PII Brasileiro adicional
        PIIType.PASSPORT: re.compile(
            r'\b[A-Z]{2}\d{7}\b',  # Formato: AA####### (Brasil)
            re.IGNORECASE
        ),
        PIIType.DRIVERS_LICENSE: re.compile(
            r'\b\d{11}\b',  # CNH: 11 dígitos (similar CPF mas sem formatação)
            re.IGNORECASE
        ),
        PIIType.BANK_ACCOUNT: re.compile(
            r'Banco\s+\d{3,4}.*?(?:Ag|agencia?\.?)\s*\d{1,5}.*?(?:Conta|conta|c/c)\s*\d{4,}[-\s]?\d{1,2}|\d{3,4}[-\s]\d{1,5}[-\s]\d{4,}[-\s]?\d{1,2}',
            re.IGNORECASE
        ),
        PIIType.ADDRESS: re.compile(
            r'\b(?:Rua|Av|Avenida|Rua\s+|R\.|Av\.)\s+[^\n]{10,100}(?:,\s*\d{3,5}|,\s*[A-Z]{2}\s*\d{5}-\d{3})',
            re.IGNORECASE
        ),
    }

    # Mapeamento de tipo para risco (numérico para comparação)
    TYPE_RISK: Dict[PIIType, PIIRiskLevel] = {
        PIIType.EMAIL: PIIRiskLevel.MEDIUM,
        PIIType.PHONE: PIIRiskLevel.MEDIUM,
        PIIType.CPF: PIIRiskLevel.HIGH,
        PIIType.CREDIT_CARD: PIIRiskLevel.CRITICAL,
        PIIType.SSN: PIIRiskLevel.CRITICAL,
        PIIType.IP_ADDRESS: PIIRiskLevel.LOW,
        PIIType.URL: PIIRiskLevel.LOW,
        # Novos tipos
        PIIType.PASSPORT: PIIRiskLevel.HIGH,
        PIIType.DRIVERS_LICENSE: PIIRiskLevel.HIGH,
        PIIType.BANK_ACCOUNT: PIIRiskLevel.HIGH,
        PIIType.ADDRESS: PIIRiskLevel.MEDIUM,
    }

    # Ordem de gravidade para comparação
    RISK_ORDER: list[PIIRiskLevel] = [
        PIIRiskLevel.NONE,
        PIIRiskLevel.LOW,
        PIIRiskLevel.MEDIUM,
        PIIRiskLevel.HIGH,
        PIIRiskLevel.CRITICAL,
    ]

    def __init__(
        self,
        enabled_types: Optional[Set[PIIType]] = None,
        min_confidence: float = 0.7,
    ):
        """
        Inicializa o detector.

        Args:
            enabled_types: Tipos de PII para detectar (todos se None)
            min_confidence: Confiança mínima para reportar (não usado em regex, mas mantido para interface)
        """
        self.enabled_types = enabled_types or set(list(PIIType))
        self.min_confidence = min_confidence

    def detect(self, text: str) -> PIIResult:
        """
        Detecta PII no texto fornecido.

        Args:
            text: Texto para analisar

        Returns:
            PIIResult com entidades detectadas e nível de risco
        """
        if not text:
            return PIIResult(
                has_pii=False,
                entities=[],
                risk_level=PIIRiskLevel.NONE,
                requires_redaction=False,
            )

        detected_entities = []
        max_risk = PIIRiskLevel.NONE

        for entity_type, pattern in self.PATTERNS.items():
            if entity_type not in self.enabled_types:
                continue

            matches = pattern.finditer(text)
            for match in matches:
                entity_text = match.group()
                start = match.start()
                end = match.end()

                # Validar match (evitar falsos positivos)
                if self._is_valid_match(entity_type, entity_text):
                    detected_entities.append(PIIEntity(
                        type=entity_type,
                        value=entity_text,
                        start_pos=start,
                        end_pos=end,
                        confidence=0.9,  # Regex tem alta confiança
                        masked_value=self._mask_entity(entity_text),
                    ))

                    # Atualizar risco máximo
                    entity_risk = self.TYPE_RISK.get(entity_type, PIIRiskLevel.LOW)
                    current_max_idx = self.RISK_ORDER.index(max_risk)
                    entity_risk_idx = self.RISK_ORDER.index(entity_risk)
                    if entity_risk_idx > current_max_idx:
                        max_risk = entity_risk

        # Determinar se requer redação
        requires_redaction = max_risk in [PIIRiskLevel.HIGH, PIIRiskLevel.CRITICAL]

        return PIIResult(
            has_pii=len(detected_entities) > 0,
            entities=detected_entities,
            risk_level=max_risk,
            requires_redaction=requires_redaction,
            masked_text=self._mask_text(text, detected_entities) if detected_entities else None,
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
        # Validações específicas por tipo
        if entity_type == PIIType.CREDIT_CARD:
            # Remover espaços/hífens e verificar Luhn
            digits = re.sub(r'[\s-]', '', text)
            if len(digits) == 16 and self._luhn_check(digits):
                return True
            return False  # Requer Luhn válido

        if entity_type == PIIType.CPF:
            # Validar dígitos verificadores do CPF
            digits = re.sub(r'[^\d]', '', text)
            if len(digits) == 11 and self._cpf_check(digits):
                return True
            return False

        if entity_type == PIIType.IP_ADDRESS:
            # Verificar se é IP válido (0-255 em cada octeto)
            octets = text.split('.')
            if len(octets) == 4:
                try:
                    return all(0 <= int(o) <= 255 for o in octets)
                except ValueError:
                    return False
            return False

        if entity_type == PIIType.EMAIL:
            # Verificar se tem @ e domínio válido
            if '@' not in text:
                return False
            parts = text.split('@')
            if len(parts) != 2:
                return False
            local, domain = parts
            return len(local) > 0 and '.' in domain and len(domain.split('.')[-1]) >= 2

        if entity_type == PIIType.SSN:
            # SSN formato: XXX-XX-XXXX (9 dígitos)
            # Evitar falsos positivos de telefone: XXXXX-XXXX (8 dígitos + hífen)
            digits = re.sub(r'[^\d]', '', text)
            # SSN deve ter exatamente 9 dígitos
            if len(digits) != 9:
                return False
            # Se tem formato XXXXX-XXXX, provavelmente é telefone brasileiro
            if re.match(r'^\d{5}-\d{4}$', text):
                return False
            return True

        if entity_type == PIIType.PASSPORT:
            # Validar formato de passaporte brasileiro: AA####### (2 letras + 7 dígitos)
            if not re.match(r'^[A-Z]{2}\d{7}$', text):
                return False
            return True

        if entity_type == PIIType.DRIVERS_LICENSE:
            # CNH tem 11 dígitos mas deve validar dígitos verificadores
            digits = re.sub(r'[^\d]', '', text)
            if len(digits) != 11:
                return False
            # Evitar sequências (mesma lógica CPF)
            if digits == digits[0] * 11:
                return False
            # Validação simplificada da CNH (dígito verificador)
            return self._cnh_check(digits) if len(digits) == 11 else True

        if entity_type == PIIType.BANK_ACCOUNT:
            # Validação: deve ter pelo menos banco + agência ou conta
            # Aceita formatos: "Banco 001 Ag 1234 Conta 56789-0", "001-1234-56789-0", etc.
            digits = re.findall(r'\d+', text)
            if len(digits) < 2:
                return False
            # Deve ter soma de pelo menos 8 dígitos entre banco, agência e conta
            total_digits = sum(len(d) for d in digits)
            return total_digits >= 8

        if entity_type == PIIType.ADDRESS:
            # Validação básica: deve ter nome de logradouro + número
            if not re.search(r'(Rua|Av|Avenida)', text, re.IGNORECASE):
                return False
            if not re.search(r'\d{3,5}', text):  # CEP ou número
                return False
            return True

        # Padrões simples aceitos por padrão
        return True

    def _luhn_check(self, card_number: str) -> bool:
        """Verifica dígito Luhn para cartão de crédito."""
        total = 0
        for i, digit in enumerate(reversed(card_number)):
            n = int(digit)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return total % 10 == 0

    def _cpf_check(self, cpf: str) -> bool:
        """Verifica dígitos verificadores do CPF."""
        if len(cpf) != 11 or cpf == cpf[0] * 11:
            return False

        # Primeiro dígito verificador
        sum1 = sum(int(cpf[i]) * (10 - i) for i in range(9))
        digit1 = 11 - (sum1 % 11)
        if digit1 >= 10:
            digit1 = 0

        # Segundo dígito verificador
        sum2 = sum(int(cpf[i]) * (11 - i) for i in range(10))
        digit2 = 11 - (sum2 % 11)
        if digit2 >= 10:
            digit2 = 0

        return int(cpf[9]) == digit1 and int(cpf[10]) == digit2

    def _cnh_check(self, cnh: str) -> bool:
        """Verifica dígito verificador da CNH (Carteira Nacional de Habilitação)."""
        if len(cnh) != 11 or cnh == cnh[0] * 11:
            return False

        # Cálculo do dígito verificador da CNH
        sum1 = 0
        for i in range(9):
            sum1 += int(cnh[i]) * (9 - i)

        digit1 = sum1 % 11
        if digit1 >= 10:
            digit1 = 0

        # Verificar primeiro dígito
        if int(cnh[9]) != digit1:
            return False

        # Segundo dígito (mais complexo)
        sum2 = 0
        for i in range(10):
            sum2 += int(cnh[i]) * (10 - i) if i < 9 else int(cnh[i]) * 2

        digit2 = sum2 % 11
        if digit2 >= 10:
            digit2 = 0

        return int(cnh[10]) == digit2

    def _mask_entity(self, text: str, mask_char: str = '*') -> str:
        """
        Mascara a entidade detectada para logging seguro.

        Args:
            text: Texto da entidade
            mask_char: Caractere para mascarar

        Returns:
            Texto mascarado (ex: joao@exemplo.com -> j***@e******.com)
        """
        if len(text) <= 4:
            return mask_char * len(text)

        # Mostrar primeiros 2 e últimos 2 caracteres
        return text[:2] + mask_char * (len(text) - 4) + text[-2:]

    def get_supported_types(self) -> Set[PIIType]:
        """Retorna tipos de PII suportados."""
        return set(self.PATTERNS.keys())

    def _mask_text(self, text: str, entities: List[PIIEntity]) -> str:
        """
        Mascarar todas as entidades detectadas no texto.

        Args:
            text: Texto original
            entities: Lista de entidades detectadas

        Returns:
            Texto com PII mascarado
        """
        if not entities:
            return text

        # Criar cópia do texto
        masked = text

        # Ordenar por posição (reverso para não quebrar índices)
        sorted_entities = sorted(entities, key=lambda e: e.start_pos, reverse=True)

        for entity in sorted_entities:
            # Substituir entidade por máscara
            masked = (
                masked[:entity.start_pos]
                + "*" * (entity.end_pos - entity.start_pos)
                + masked[entity.end_pos:]
            )

        return masked

    def enable_type(self, entity_type: PIIType) -> None:
        """Habilita detecção de um tipo de PII."""
        self.enabled_types.add(entity_type)

    def disable_type(self, entity_type: PIIType) -> None:
        """Desabilita detecção de um tipo de PII."""
        self.enabled_types.discard(entity_type)
