"""
PII (Personally Identifiable Information) Models

Modelos para detecção e tratamento de informações pessoais sensíveis.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class PIIType(str, Enum):
    """Tipos de Informação Pessoal Identificável."""

    EMAIL = "email"
    PHONE = "phone"
    CPF = "cpf"  # Brasileiro
    CREDIT_CARD = "credit_card"
    PASSPORT = "passport"
    DRIVERS_LICENSE = "drivers_license"
    BANK_ACCOUNT = "bank_account"
    ADDRESS = "address"
    SSN = "ssn"  # US
    IP_ADDRESS = "ip_address"
    URL = "url"
    CUSTOMER_ID = "customer_id"
    USERNAME = "username"
    # PII Angolanos
    NIF = "nif"  # Número de Identificação Fiscal (Angola)
    BI = "bi"  # Bilhete de Identidade (Angola)
    NUIT = "nuit"  # Número Único de Identificação Tributária (Angola)


class PIIRiskLevel(str, Enum):
    """Níveis de risco para dados PII."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PIIEntity(BaseModel):
    """Entidade PII detectada no texto."""

    type: PIIType = Field(..., description="Tipo de PII detectado")
    value: str = Field(..., description="Valor original detectado")
    start_pos: int = Field(..., ge=0, description="Posição inicial no texto")
    end_pos: int = Field(..., ge=0, description="Posição final no texto")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confiança da detecção"
    )
    masked_value: Optional[str] = Field(None, description="Valor mascarado")


class PIIResult(BaseModel):
    """
    Resultado da detecção de PII em um texto.

    Contém todas as entidades detectadas, o texto mascarado
    e a avaliação de risco.
    """

    has_pii: bool = Field(..., description="Se algum PII foi detectado")
    entities: List[PIIEntity] = Field(
        default_factory=list,
        description="Lista de entidades PII detectadas"
    )
    masked_text: Optional[str] = Field(None, description="Texto com PII mascarado")
    requires_redaction: bool = Field(
        default=False,
        description="Se o texto requer anonimização antes do processamento"
    )
    risk_level: PIIRiskLevel = Field(
        default=PIIRiskLevel.NONE,
        description="Nível de risco baseado nos tipos detectados"
    )


class PIIDetectionConfig(BaseModel):
    """Configuração do detector de PII."""

    enabled: bool = Field(default=True, description="Se a detecção está habilitada")
    mask_by_default: bool = Field(
        default=False,
        description="Se deve mascarar automaticamente"
    )
    min_confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confiança mínima para considerar uma detecção válida"
    )
    enabled_types: List[PIIType] = Field(
        default_factory=lambda: list(PIIType),
        description="Tipos de PII habilitados para detecção"
    )
    strict_mode: bool = Field(
        default=False,
        description="Se True, aceita false positives; se False, mais conservador"
    )
