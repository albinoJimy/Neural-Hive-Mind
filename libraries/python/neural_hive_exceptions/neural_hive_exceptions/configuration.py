"""
Configuration exceptions for Neural Hive-Mind.

Erros relacionados a configuração de ambiente, variáveis de ambiente,
e inicialização de serviços.
"""

from typing import Any, Optional

from .base import NeuralHiveError, error_code


class ConfigErrorCode:
    """Códigos de erro de configuração."""

    # Missing configuration
    MISSING_REQUIRED_CONFIG = error_code("CONFIG_001")
    MISSING_ENV_VAR = error_code("CONFIG_002")

    # Invalid configuration
    INVALID_VALUE = error_code("CONFIG_003")
    INVALID_TYPE = error_code("CONFIG_004")

    # Configuration access errors
    CONFIG_ACCESS_ERROR = error_code("CONFIG_005")
    CONFIG_FILE_ERROR = error_code("CONFIG_006")


class ConfigurationError(NeuralHiveError):
    """
    Exceção para erros de configuração.

    Uso:
        raise ConfigurationError(
            config_key="DATABASE_URL",
            reason="Cannot be empty in production"
        )
    """

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        reason: Optional[str] = None,
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        code = code or ConfigErrorCode.MISSING_REQUIRED_CONFIG

        # Construir details
        error_details = details or {}
        if config_key:
            error_details["config_key"] = config_key
        if reason:
            error_details["reason"] = reason

        super().__init__(message=message, code=code, details=error_details, http_status=500)

    @classmethod
    def missing_required(cls, config_key: str) -> "ConfigurationError":
        """Erro para configuração obrigatória faltando."""
        return cls(
            message=f"Required configuration '{config_key}' is missing",
            config_key=config_key,
            code=ConfigErrorCode.MISSING_REQUIRED_CONFIG,
        )

    @classmethod
    def invalid_value(cls, config_key: str, value: Any, expected: str) -> "ConfigurationError":
        """Erro para valor de configuração inválido."""
        return cls(
            message=f"Configuration '{config_key}' has invalid value",
            config_key=config_key,
            reason=f"Expected: {expected}, got: {value}",
            code=ConfigErrorCode.INVALID_VALUE,
        )

    @classmethod
    def missing_env_var(cls, env_var: str) -> "ConfigurationError":
        """Erro para variável de ambiente faltando."""
        return cls(
            message=f"Required environment variable '{env_var}' is not set",
            config_key=env_var,
            code=ConfigErrorCode.MISSING_ENV_VAR,
        )
