"""
ML Model Deployment Pipeline

Este módulo fornece funcionalidades para promoção de modelos ML entre ambientes
(staging → production) com validação, backup e rollback automático.
"""

from .promote_model import (
    ModelBackupError,
    ModelPromotionError,
    ModelValidationError,
    backup_current_model,
    promote_model,
    rollback_model,
    update_model_version,
    validate_model,
)

__all__ = [
    "validate_model",
    "backup_current_model",
    "promote_model",
    "rollback_model",
    "update_model_version",
    "ModelPromotionError",
    "ModelValidationError",
    "ModelBackupError",
]
