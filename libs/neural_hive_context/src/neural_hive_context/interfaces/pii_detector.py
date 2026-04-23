"""
PII Detector Interface

Interface abstrata para detecção de informações pessoais sensíveis.
"""

from abc import ABC, abstractmethod
from neural_hive_context.models.pii import PIIResult


class IPIIDetector(ABC):
    """
    Interface para detecção de PII (Personally Identifiable Information).

    Implementações devem detectar diversos tipos de dados sensíveis
    como emails, CPF, cartões de crédito, etc.
    """

    @abstractmethod
    def detect(self, text: str) -> PIIResult:
        """
        Detecta informações pessoais no texto fornecido.

        Args:
            text: Texto para analisar

        Returns:
            PIIResult contendo:
            - has_pii: Bool indicando se PII foi encontrado
            - entities: Lista de PIIEntity detectadas
            - masked_text: Texto com PII mascarado (se aplicável)
            - risk_level: Nível de risco (none, low, medium, high, critical)
            - requires_redaction: Se o texto requer anonimização

        Raises:
            ValueError: Se o texto estiver inválido
        """
        pass
