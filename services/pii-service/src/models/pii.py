"""Models PII para o serviço."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PIIType(str, Enum):
    """Tipos de PII suportados (INV-2: 7 tipos requeridos)."""

    # Tipos requeridos por INV-2
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    CPF = "CPF"
    CNPJ = "CNPJ"
    CREDIT_CARD = "CREDIT_CARD"
    SSN = "SSN"
    ADDRESS = "ADDRESS"

    # Tipos adicionais suportados (23 tipos totais para R-P3)
    IP_ADDRESS = "IP_ADDRESS"
    UUID = "UUID"
    API_KEY = "API_KEY"
    NIF = "NIF"
    IBAN = "IBAN"
    PASSPORT = "PASSPORT"
    POSTAL_CODE = "POSTAL_CODE"
    RG = "RG"
    TITULO_ELEITOR = "TITULO_ELEITOR"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    PERSON = "PERSON"
    ORG = "ORG"
    DATE = "DATE"
    PII_UNKNOWN = "PII_UNKNOWN"


class MaskStrategy(str, Enum):
    """Estratégias de mascaramento (INV-2: 3 estratégias requeridas)."""

    # Estratégias requeridas por INV-2
    MASK_FULL = "MASK_FULL"  # Substituir por tag
    MASK_PARTIAL = "MASK_PARTIAL"  # Mascaramento parcial
    MASK_REDACT = "MASK_REDACT"  # Remover completamente

    # Estratégia adicional
    MASK_HASH = "MASK_HASH"  # Substituir por hash


class PIIFound(BaseModel):
    """PII detectado com posição (INV-2: positions requeridos)."""

    type: PIIType = Field(..., description="Tipo de PII detectado")
    value: str = Field(..., description="Valor original detectado")
    start: int = Field(..., description="Posição inicial no texto (INV-2)")
    end: int = Field(..., description="Posição final no texto (INV-2)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confiança da detecção")
    masked_value: str | None = Field(None, description="Valor mascarado")


class MaskResult(BaseModel):
    """Resultado de mascaramento."""

    type: PIIType = Field(..., description="Tipo de PII mascarado")
    original_value: str = Field(..., description="Valor original")
    masked_value: str = Field(..., description="Valor mascarado")
    start: int = Field(..., description="Posição inicial no texto")
    end: int = Field(..., description="Posição final no texto")
    strategy_used: MaskStrategy = Field(..., description="Estratégia utilizada")
    mask_id: str | None = Field(None, description="ID para unmask reversível (INV-14)")


@dataclass
class EncryptedPII:
    """PII criptografado para unmask reversível (INV-14)."""

    mask_id: str  # Token criptografado
    original_value: str  # Valor original (não persistido em logs)
    pii_type: PIIType
    created_at: datetime
    expires_at: datetime
    requestor_id: str
    attempt_count: int = 0


class PIIServiceError(Exception):
    """Exceção base para erros do PII Service."""

    def __init__(self, message: str, code: str = "PII_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class PIIUnmaskError(PIIServiceError):
    """Erro ao fazer unmask de PII."""

    def __init__(self, message: str):
        super().__init__(message, code="UNMASK_ERROR")


class PIIAuthError(PIIServiceError):
    """Erro de autenticação para operação PII."""

    def __init__(self, message: str = "Authentication required for PII operations"):
        super().__init__(message, code="AUTH_ERROR")
