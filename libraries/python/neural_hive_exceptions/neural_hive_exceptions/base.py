"""
Base exception class for Neural Hive-Mind.
"""

from dataclasses import dataclass
from typing import Any, Optional


class NeuralHiveError(Exception):
    """
    Base exception para Neural Hive Mind.

    Todas as exceções da plataforma devem herdar desta classe para
    garantir consistência em tratamento de erros e logging estruturado.

    Attributes:
        message: Mensagem de erro legível para humanos
        code: Código de erro único (ex: NHM_VALIDATION_001)
        details: Dicionário com contexto adicional do erro
        http_status: Código HTTP sugerido (para APIs REST)
    """

    def __init__(
        self,
        message: str,
        code: str = "NHM_UNKNOWN_ERROR",
        details: Optional[dict[str, Any]] = None,
        http_status: int = 500,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        self.http_status = http_status
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """
        Converte exceção para dicionário serializável.

        Returns:
            Dicionário com campos da exceção
        """
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
            "http_status": self.http_status,
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code}, message={self.message})"


def error_code(code: str) -> str:
    """
    Gera código de erro padronizado com prefixo NHM_.

    Args:
        code: Código sem prefixo (ex: "VALIDATION_001")

    Returns:
        Código completo com prefixo (ex: "NHM_VALIDATION_001")
    """
    if not code.startswith("NHM_"):
        return f"NHM_{code}"
    return code


@dataclass
class ErrorContext:
    """
    Contexto adicional para logging estruturado de erros.

    Attributes:
        service: Nome do serviço que gerou o erro
        component: Componente específico (ex: "database", "kafka")
        operation: Operação que falhou (ex: "connect", "query")
        trace_id: ID do trace distribuído para correlação
        timestamp: Timestamp do erro
    """

    service: str
    component: str
    operation: str
    trace_id: Optional[str] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "service": self.service,
            "component": self.component,
            "operation": self.operation,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
        }
