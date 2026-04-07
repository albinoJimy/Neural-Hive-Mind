"""
Infrastructure exceptions for Neural Hive-Mind.

Erros relacionados a conexões externas, bancos de dados, Kafka, etc.
"""

from typing import Dict, Any, Optional
from .base import NeuralHiveError, error_code


class InfrastructureErrorCode:
    """Códigos de erro de infraestrutura."""

    # Connection errors
    CONNECTION_FAILED = error_code("INFRA_001")
    CONNECTION_TIMEOUT = error_code("INFRA_002")
    CONNECTION_LOST = error_code("INFRA_003")

    # Database errors
    DATABASE_ERROR = error_code("INFRA_DB_001")
    QUERY_TIMEOUT = error_code("INFRA_DB_002")
    TRANSACTION_ERROR = error_code("INFRA_DB_003")

    # Messaging errors
    KAFKA_ERROR = error_code("INFRA_KAFKA_001")
    KAFKA_PRODUCER_ERROR = error_code("INFRA_KAFKA_002")
    KAFKA_CONSUMER_ERROR = error_code("INFRA_KAFKA_003")

    # Cache errors
    CACHE_ERROR = error_code("INFRA_CACHE_001")
    CACHE_MISS = error_code("INFRA_CACHE_002")

    # External service errors
    EXTERNAL_SERVICE_ERROR = error_code("INFRA_EXT_001")
    EXTERNAL_SERVICE_TIMEOUT = error_code("INFRA_EXT_002")


class ConnectionError(NeuralHiveError):
    """
    Exceção para falhas de conexão com serviços externos.

    Uso:
        raise ConnectionError(
            service="database",
            host="localhost",
            port=5432,
            reason="Connection refused"
        )
    """

    def __init__(
        self,
        message: str,
        service: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        reason: Optional[str] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        code = code or InfrastructureErrorCode.CONNECTION_FAILED

        # Construir details
        error_details = details or {}
        if service:
            error_details["service"] = service
        if host:
            error_details["host"] = host
        if port:
            error_details["port"] = port
        if reason:
            error_details["reason"] = reason

        super().__init__(message=message, code=code, details=error_details, http_status=503)

    @classmethod
    def service_unavailable(
        cls, service: str, host: str = None, port: int = None
    ) -> "ConnectionError":
        """Erro para serviço indisponível."""
        return cls(
            message=f"Service '{service}' is unavailable",
            service=service,
            host=host,
            port=port,
            code=InfrastructureErrorCode.CONNECTION_FAILED,
        )


class TimeoutError(NeuralHiveError):
    """
    Exceção para timeouts em operações externas.

    Uso:
        raise TimeoutError(
            operation="database_query",
            timeout_seconds=30,
            service="postgresql"
        )
    """

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        service: Optional[str] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        code = code or InfrastructureErrorCode.CONNECTION_TIMEOUT

        # Construir details
        error_details = details or {}
        if operation:
            error_details["operation"] = operation
        if timeout_seconds:
            error_details["timeout_seconds"] = timeout_seconds
        if service:
            error_details["service"] = service

        super().__init__(message=message, code=code, details=error_details, http_status=504)

    @classmethod
    def operation_timeout(
        cls, operation: str, timeout_seconds: float, service: str = None
    ) -> "TimeoutError":
        """Erro para operação que excedeu timeout."""
        return cls(
            message=f"Operation '{operation}' timed out after {timeout_seconds}s",
            operation=operation,
            timeout_seconds=timeout_seconds,
            service=service,
            code=InfrastructureErrorCode.CONNECTION_TIMEOUT,
        )


class DatabaseError(NeuralHiveError):
    """Exceção para erros de banco de dados."""

    def __init__(
        self,
        message: str,
        query: Optional[str] = None,
        database: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        code = InfrastructureErrorCode.DATABASE_ERROR

        # Construir details
        error_details = details or {}
        if query:
            # Truncar query muito longo
            error_details["query"] = query[:200] + "..." if len(query) > 200 else query
        if database:
            error_details["database"] = database

        super().__init__(message=message, code=code, details=error_details, http_status=500)

    @classmethod
    def query_failed(cls, query: str, reason: str, database: str = None) -> "DatabaseError":
        """Erro para query que falhou."""
        return cls(message=f"Database query failed: {reason}", query=query, database=database)


class KafkaError(NeuralHiveError):
    """Exceção para erros de Kafka."""

    def __init__(
        self,
        message: str,
        topic: Optional[str] = None,
        partition: Optional[int] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        code = code or InfrastructureErrorCode.KAFKA_ERROR

        # Construir details
        error_details = details or {}
        if topic:
            error_details["topic"] = topic
        if partition is not None:
            error_details["partition"] = partition

        super().__init__(message=message, code=code, details=error_details, http_status=500)

    @classmethod
    def producer_error(cls, topic: str, reason: str) -> "KafkaError":
        """Erro ao produzir mensagem para Kafka."""
        return cls(
            message=f"Failed to produce message to Kafka: {reason}",
            topic=topic,
            code=InfrastructureErrorCode.KAFKA_PRODUCER_ERROR,
        )

    @classmethod
    def consumer_error(cls, topic: str, reason: str) -> "KafkaError":
        """Erro ao consumir mensagem do Kafka."""
        return cls(
            message=f"Failed to consume message from Kafka: {reason}",
            topic=topic,
            code=InfrastructureErrorCode.KAFKA_CONSUMER_ERROR,
        )
