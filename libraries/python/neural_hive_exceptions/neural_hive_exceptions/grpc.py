"""
gRPC exceptions and error handling for Neural Hive-Mind.

Conversão entre exceções internas e status gRPC, com adaptadores
para HTTP REST APIs.
"""

from typing import Dict, Any, Optional
import grpc

from .base import NeuralHiveError, ErrorContext


class GRPCErrorCode:
    """Códigos de erro gRPC mapeados para Neural Hive."""

    # Generic gRPC status codes
    OK = grpc.StatusCode.OK
    CANCELLED = grpc.StatusCode.CANCELLED
    UNKNOWN = grpc.StatusCode.UNKNOWN
    INVALID_ARGUMENT = grpc.StatusCode.INVALID_ARGUMENT
    DEADLINE_EXCEEDED = grpc.StatusCode.DEADLINE_EXCEEDED
    NOT_FOUND = grpc.StatusCode.NOT_FOUND
    ALREADY_EXISTS = grpc.StatusCode.ALREADY_EXISTS
    PERMISSION_DENIED = grpc.StatusCode.PERMISSION_DENIED
    UNAUTHENTICATED = grpc.StatusCode.UNAUTHENTICATED
    RESOURCE_EXHAUSTED = grpc.StatusCode.RESOURCE_EXHAUSTED
    FAILED_PRECONDITION = grpc.StatusCode.FAILED_PRECONDITION
    ABORTED = grpc.StatusCode.ABORTED
    OUT_OF_RANGE = grpc.StatusCode.OUT_OF_RANGE
    UNIMPLEMENTED = grpc.StatusCode.UNIMPLEMENTED
    INTERNAL = grpc.StatusCode.INTERNAL
    UNAVAILABLE = grpc.StatusCode.UNAVAILABLE
    DATA_LOSS = grpc.StatusCode.DATA_LOSS


class GRPCError(NeuralHiveError):
    """
    Exceção para erros em chamadas gRPC.

    Uso:
        raise GRPCError(
            status_code=grpc.StatusCode.NOT_FOUND,
            detail="Resource not found",
            details={"resource_type": "Plan", "resource_id": "123"}
        )
    """

    def __init__(
        self,
        message: str,
        status_code: grpc.StatusCode = grpc.StatusCode.INTERNAL,
        details: Optional[Dict[str, Any]] = None,
        context: Optional[ErrorContext] = None,
    ):
        # Mapear status code gRPC para HTTP
        http_status_map = {
            grpc.StatusCode.INVALID_ARGUMENT: 400,
            grpc.StatusCode.NOT_FOUND: 404,
            grpc.StatusCode.ALREADY_EXISTS: 409,
            grpc.StatusCode.PERMISSION_DENIED: 403,
            grpc.StatusCode.UNAUTHENTICATED: 401,
            grpc.StatusCode.RESOURCE_EXHAUSTED: 429,
            grpc.StatusCode.FAILED_PRECONDITION: 412,
            grpc.StatusCode.OUT_OF_RANGE: 400,
            grpc.StatusCode.UNIMPLEMENTED: 501,
            grpc.StatusCode.UNAVAILABLE: 503,
        }

        # Construir details
        error_details = details or {}
        error_details["grpc_status"] = status_code.name
        error_details["grpc_code"] = status_code.value

        if context:
            error_details["context"] = context.to_dict()

        # Converter status code para código NHM
        code = f"NHM_GRPC_{status_code.name}"

        super().__init__(
            message=message,
            code=code,
            details=error_details,
            http_status=http_status_map.get(status_code, 500),
        )

        self.grpc_status_code = status_code


def grpc_error_to_status(
    error: Exception, context: Optional[ErrorContext] = None
) -> grpc.StatusCode:
    """
    Converte exceção Python em status gRPC apropriado.

    Args:
        error: Exceção a converter
        context: Contexto adicional para logging

    Returns:
        StatusCode gRPC correspondente
    """
    if isinstance(error, grpc.StatusCode):
        return error

    if isinstance(error, NeuralHiveError):
        # Mapear HTTP status para gRPC
        http_to_grpc = {
            400: grpc.StatusCode.INVALID_ARGUMENT,
            401: grpc.StatusCode.UNAUTHENTICATED,
            403: grpc.StatusCode.PERMISSION_DENIED,
            404: grpc.StatusCode.NOT_FOUND,
            409: grpc.StatusCode.ALREADY_EXISTS,
            412: grpc.StatusCode.FAILED_PRECONDITION,
            429: grpc.StatusCode.RESOURCE_EXHAUSTED,
            500: grpc.StatusCode.INTERNAL,
            501: grpc.StatusCode.UNIMPLEMENTED,
            503: grpc.StatusCode.UNAVAILABLE,
        }
        return http_to_grpc.get(error.http_status, grpc.StatusCode.INTERNAL)

    # Para exceções genéricas, tentar inferir pelo tipo
    if isinstance(error, ValueError):
        return grpc.StatusCode.INVALID_ARGUMENT
    if isinstance(error, KeyError):
        return grpc.StatusCode.NOT_FOUND
    if isinstance(error, PermissionError):
        return grpc.StatusCode.PERMISSION_DENIED

    return grpc.StatusCode.UNKNOWN


def create_grpc_error(error: Exception, context: Optional[ErrorContext] = None) -> GRPCError:
    """
    Cria GRPCError a partir de qualquer exceção.

    Args:
        error: Exceção original
        context: Contexto adicional

    Returns:
        GRPCError com status apropriado
    """
    status_code = grpc_error_to_status(error, context)

    return GRPCError(
        message=str(error),
        status_code=status_code,
        details={"original_type": type(error).__name__},
        context=context,
    )


# Adaptador HTTP para exceções gRPC
class HTTPStatusFromGRPC:
    """
    Mapeia status gRPC para códigos HTTP em exceções.

    Uso em FastAPI:
        @app.exception_handler(GRPCError)
        async def grpc_exception_handler(request, exc):
            return JSONResponse(
                status_code=exc.http_status,
                content=exc.to_dict()
            )
    """

    @staticmethod
    def get_http_status(grpc_status: grpc.StatusCode) -> int:
        """Retorna código HTTP para status gRPC."""
        status_map = {
            grpc.StatusCode.OK: 200,
            grpc.StatusCode.CANCELLED: 499,
            grpc.StatusCode.UNKNOWN: 500,
            grpc.StatusCode.INVALID_ARGUMENT: 400,
            grpc.StatusCode.DEADLINE_EXCEEDED: 504,
            grpc.StatusCode.NOT_FOUND: 404,
            grpc.StatusCode.ALREADY_EXISTS: 409,
            grpc.StatusCode.PERMISSION_DENIED: 403,
            grpc.StatusCode.UNAUTHENTICATED: 401,
            grpc.StatusCode.RESOURCE_EXHAUSTED: 429,
            grpc.StatusCode.FAILED_PRECONDITION: 412,
            grpc.StatusCode.ABORTED: 409,
            grpc.StatusCode.OUT_OF_RANGE: 400,
            grpc.StatusCode.UNIMPLEMENTED: 501,
            grpc.StatusCode.INTERNAL: 500,
            grpc.StatusCode.UNAVAILABLE: 503,
            grpc.StatusCode.DATA_LOSS: 500,
        }
        return status_map.get(grpc_status, 500)
