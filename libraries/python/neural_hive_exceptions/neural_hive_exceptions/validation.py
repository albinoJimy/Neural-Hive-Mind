"""
Validation exceptions for Neural Hive-Mind.

Erros de validação de dados, schema e entrada de usuário.
"""

from typing import Dict, Any, Optional, List
from .base import NeuralHiveError, error_code


class ValidationErrorCode:
    """Códigos de erro de validação."""

    # General validation errors
    INVALID_INPUT = error_code("VALIDATION_001")
    MISSING_REQUIRED_FIELD = error_code("VALIDATION_002")
    INVALID_FORMAT = error_code("VALIDATION_003")
    OUT_OF_RANGE = error_code("VALIDATION_004")

    # Schema validation errors
    SCHEMA_MISMATCH = error_code("VALIDATION_SCHEMA_001")
    INVALID_TYPE = error_code("VALIDATION_SCHEMA_002")
    INVALID_ENUM_VALUE = error_code("VALIDATION_SCHEMA_003")

    # Business rule validation
    BUSINESS_RULE_VIOLATION = error_code("VALIDATION_BUSINESS_001")
    CONSTRAINT_VIOLATION = error_code("VALIDATION_CONSTRAINT_001")


class ValidationError(NeuralHiveError):
    """
    Exceção para erros de validação de dados.

    Uso:
        raise ValidationError(
            field="email",
            value="invalid-email",
            reason="Must be a valid email address"
        )
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        reason: Optional[str] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        code = code or ValidationErrorCode.INVALID_INPUT

        # Construir details automaticamente
        error_details = details or {}
        if field:
            error_details["field"] = field
        if value is not None:
            error_details["provided_value"] = str(value)
        if reason:
            error_details["reason"] = reason

        super().__init__(message=message, code=code, details=error_details, http_status=400)

    @classmethod
    def missing_field(cls, field: str) -> "ValidationError":
        """Erro para campo obrigatório faltando."""
        return cls(
            message=f"Required field '{field}' is missing",
            field=field,
            code=ValidationErrorCode.MISSING_REQUIRED_FIELD,
        )

    @classmethod
    def invalid_format(cls, field: str, value: Any, expected_format: str) -> "ValidationError":
        """Erro para formato inválido."""
        return cls(
            message=f"Field '{field}' has invalid format",
            field=field,
            value=value,
            reason=f"Expected format: {expected_format}",
            code=ValidationErrorCode.INVALID_FORMAT,
        )

    @classmethod
    def out_of_range(
        cls,
        field: str,
        value: float,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
    ) -> "ValidationError":
        """Erro para valor fora do range permitido."""
        parts = []
        if min_val is not None:
            parts.append(f"min={min_val}")
        if max_val is not None:
            parts.append(f"max={max_val}")

        return cls(
            message=f"Field '{field}' value {value} is out of range",
            field=field,
            value=value,
            reason=f"Must satisfy: {', '.join(parts)}",
            code=ValidationErrorCode.OUT_OF_RANGE,
        )


class SchemaValidationError(ValidationError):
    """Erro específico para validação de schema."""

    def __init__(
        self, message: str, schema_name: str, errors: Optional[List[Dict[str, Any]]] = None
    ):
        super().__init__(
            message=message,
            code=ValidationErrorCode.SCHEMA_MISMATCH,
            details={"schema": schema_name, "errors": errors or []},
        )
