"""
Módulo de Compliance e Governança de Dados.

Este módulo implementa funcionalidades de conformidade com LGPD/GDPR:
- Detecção e anonimização de PII (Presidio)
- Criptografia de campos sensíveis (Fernet)
- Audit logging de operações
- Políticas de retenção de dados
"""

from .compliance_layer import ComplianceLayer
from .field_encryptor import FieldEncryptor
from .audit_logger import AuditLogger
from .pii_detector import PIIDetector
from .pii_masker import PIIMasker, MaskStrategy, create_masker
from .pii_patterns import PIIType, PIICategory, get_pattern_registry

__all__ = [
    "ComplianceLayer",
    "FieldEncryptor",
    "AuditLogger",
    "PIIDetector",
    "PIIMasker",
    "MaskStrategy",
    "create_masker",
    "PIIType",
    "PIICategory",
    "get_pattern_registry",
]
