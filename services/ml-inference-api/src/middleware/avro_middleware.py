"""
Middleware para suporte a content-type Avro na API ML Inference.

Este middleware permite que a API aceite e retorne dados tanto em JSON
quanto em formato Avro binário, dependendo do Content-Type e Accept headers.

Uso:
    app.add_middleware(AvroContentTypeMiddleware)
"""
import json
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..schemas.avro_schemas import (
    AvroSchemaRegistry,
)

logger = structlog.get_logger()


# Content-Type headers
CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_AVRO = "application/avro"
CONTENT_TYPE_OCTET_STREAM = "application/octet-stream"

# Accept headers
ACCEPT_AVRO = "application/avro"
ACCEPT_JSON = "application/json"


class AvroContentTypeMiddleware(BaseHTTPMiddleware):
    """
    Middleware para suporte a content-type Avro.

    Funcionalidades:
    1. Detecta Content-Type da request
    2. Deserializa Avro se necessário
    3. Serializa response em Avro se Accept header solicitar
    4. Fallback para JSON em caso de erro
    """

    def __init__(
        self,
        app: ASGIApp,
        schema_registry: AvroSchemaRegistry | None = None,
        enable_fallback: bool = True,
    ):
        """
        Inicializa middleware.

        Args:
            app: Aplicação FastAPI
            schema_registry: Registry de schemas Avro (cria novo se None)
            enable_fallback: Habilita fallback para JSON em caso de erro
        """
        super().__init__(app)
        self.schema_registry = schema_registry or AvroSchemaRegistry()
        self.enable_fallback = enable_fallback
        logger.info(
            "avro_middleware_initialized",
            fallback_enabled=enable_fallback,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """
        Processa request com suporte Avro.

        Args:
            request: Request HTTP
            call_next: Próximo middleware/endpoint

        Returns:
            Response com content-type apropriado
        """
        # Detectar content-type
        content_type = request.headers.get("content-type", CONTENT_TYPE_JSON)
        accept_header = request.headers.get("accept", CONTENT_TYPE_JSON).lower()

        # Armazenar no state para uso nos endpoints
        request.state.is_avro_request = CONTENT_TYPE_AVRO in content_type or (
            "avro" in content_type.lower()
        )
        request.state.wants_avro_response = ACCEPT_AVRO in accept_header

        # Processar request
        response = await call_next(request)

        # Se o cliente quer Avro e temos um JSON response, converter
        if (
            request.state.wants_avro_response
            and response.headers.get("content-type", "").startswith("application/json")
        ):
            return await self._convert_to_avro(request, response)

        return response

    async def _convert_to_avro(
        self,
        request: Request,
        response: Response,
    ) -> Response:
        """
        Converte response JSON para Avro.

        Args:
            request: Request original
            response: Response JSON

        Returns:
            Response Avro ou JSON em caso de erro
        """
        if not self.enable_fallback:
            return response

        try:
            # Ler body JSON
            body_bytes = response.body
            body_json = json.loads(body_bytes.decode("utf-8"))

            # Determinar schema baseado no endpoint
            schema_name = self._get_schema_for_path(request.url.path)

            if schema_name:
                # Serializar para Avro
                avro_bytes = self.schema_registry.serialize(body_json, schema_name)

                return Response(
                    content=avro_bytes,
                    media_type=CONTENT_TYPE_AVRO,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

        except Exception as e:
            logger.warning(
                "avro_conversion_failed_using_json",
                error=str(e),
                path=request.url.path,
            )

        # Fallback para JSON original
        return response

    def _get_schema_for_path(self, path: str) -> str | None:
        """
        Determina qual schema usar baseado no path.

        Args:
            path: Caminho da request

        Returns:
            Nome do schema ou None
        """
        # Verifica batch primeiro (mais específico)
        if "/batch" in path or "batch" in path.lower():
            if "request" in path.lower():
                return "batch_request"
            else:
                return "batch_response"
        elif "/predict" in path:
            if "request" in path.lower():
                return "inference_request"
            else:
                return "inference_response"
        return None


async def parse_avro_body(
    request: Request,
    schema_name: str = "inference_request",
) -> dict:
    """
    Helper para parsear body Avro de request.

    Args:
        request: Request FastAPI
        schema_name: Nome do schema Avro

    Returns:
        Dicionário com dados parseados

    Raises:
        ValueError: Se falhar parse
    """
    content_type = request.headers.get("content-type", "")
    if "avro" not in content_type.lower():
        # Não é Avro, retorna JSON body
        return await request.json()

    body_bytes = await request.body()

    try:
        registry = AvroSchemaRegistry()
        parsed = registry.deserialize(body_bytes, schema_name)

        if parsed is None:
            raise ValueError("Failed to deserialize Avro body")

        return parsed

    except Exception as e:
        logger.error("avro_body_parse_failed", error=str(e), schema_name=schema_name)
        raise ValueError(f"Invalid Avro body: {str(e)}") from e


def avro_response(
    data: dict,
    schema_name: str = "inference_response",
    request: Request | None = None,
) -> Response:
    """
    Cria response Avro ou JSON baseado no Accept header.

    Args:
        data: Dados para serializar
        schema_name: Nome do schema Avro
        request: Request para verificar Accept header

    Returns:
        Response com content-type apropriado
    """
    wants_avro = False
    if request:
        accept_header = request.headers.get("accept", "").lower()
        wants_avro = ACCEPT_AVRO in accept_header

    if wants_avro:
        try:
            registry = AvroSchemaRegistry()
            avro_bytes = registry.serialize(data, schema_name)

            return Response(
                content=avro_bytes,
                media_type=CONTENT_TYPE_AVRO,
            )
        except Exception as e:
            logger.warning("avro_response_failed_using_json", error=str(e))

    # Fallback para JSON
    return JSONResponse(content=data)
