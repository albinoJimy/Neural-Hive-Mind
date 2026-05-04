"""
Context Builder para Unified Gateway.

Este serviço constrói o RequestContext completo a partir de:
1. JWT token (user_id, tenant_id, session_id) - extraído pelo JWTAuthMiddleware
2. Request input (text, files)
3. Request metadata (headers, client info)

Implementa R-G4: Context Builder para extrair tenant_id, session_id, user_id de JWT.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog
from fastapi import HTTPException, Request, status
from pydantic import ValidationError

from src.middleware.jwt_auth import AuthContext, get_auth_context
from src.models.context import (
    ActorContext,
    ActorType,
    RequestContext,
    RichContext,
    SecurityContext,
    SessionContext,
    SystemContext,
    TemporalContext,
    TenantContext,
)

logger = structlog.get_logger(__name__)


class ContextBuilderError(Exception):
    """Erro na construção do contexto."""

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class ContextBuilderConfig:
    """Configuração do Context Builder."""

    generate_request_id: bool = True
    generate_session_id: bool = True
    extract_client_ip: bool = True
    extract_user_agent: bool = True
    default_tenant_id: str | None = None
    session_ttl_hours: int = 24


class ContextBuilder:
    """
    Builder para construir RequestContext a partir da Request FastAPI.

    Fluxo:
    1. Extrai AuthContext do JWT (já processado pelo JWTAuthMiddleware)
    2. Extrai dados do body da request (input, files)
    3. Extrai metadados (client_ip, user_agent)
    4. Constrói RequestContext completo

    Implementa R-G4: Context Builder para extrair tenant_id, session_id, user_id.
    Implementa INV-7: JWT tokens validated must pass user_id, tenant_id downstream.
    """

    def __init__(self, config: ContextBuilderConfig | None = None):
        """
        Inicializa Context Builder.

        Args:
            config: Configuração do builder. Se None, usa padrão.
        """
        self.config = config or ContextBuilderConfig()

        logger.info(
            "context_builder_initialized",
            generate_request_id=self.config.generate_request_id,
            generate_session_id=self.config.generate_session_id,
            extract_client_ip=self.config.extract_client_ip,
        )

    async def build(
        self,
        request: Request,
        input_data: dict[str, Any] | None = None,
    ) -> RequestContext:
        """
        Constrói RequestContext a partir da Request.

        Args:
            request: Request FastAPI
            input_data: Dados de input da request (body parseado)

        Returns:
            RequestContext com todos os campos preenchidos

        Raises:
            ContextBuilderError: Se falhar ao construir contexto
        """
        try:
            # 1. Extrair AuthContext do JWT (INV-7)
            auth_context = await self._get_auth_context(request)

            # 2. Gerar request_id único
            request_id = self._generate_request_id()

            # 3. Extrair dados do input
            input_text, input_files = self._extract_input(input_data or {})

            # 4. Construir TenantContext (INV-7)
            tenant_context = self._build_tenant_context(auth_context)

            # 5. Construir SessionContext
            session_context = self._build_session_context(auth_context, request)

            # 6. Construir ActorContext
            actor_context = self._build_actor_context(auth_context)

            # 7. Extrair metadados
            metadata = self._extract_metadata(request)

            # 8. Construir RequestContext completo
            request_context = RequestContext(
                request_id=request_id,
                input_text=input_text,
                input_files=input_files,
                tenant=tenant_context,
                session=session_context,
                actor=actor_context,
                metadata=metadata,
            )

            logger.debug(
                "context_built",
                request_id=request_id,
                user_id=auth_context.user_id,
                tenant_id=auth_context.tenant_id,
                has_session=session_context is not None,
            )

            return request_context

        except ValidationError as e:
            raise ContextBuilderError(f"Invalid context data: {e}") from e
        except Exception as e:
            logger.exception("context_build_error")
            raise ContextBuilderError(f"Failed to build context: {e}") from e

    async def build_rich(
        self,
        request: Request,
        input_data: dict[str, Any] | None = None,
    ) -> RichContext:
        """
        Constrói RichContext completo com todas as dimensões.

        Inclui RequestContext + SystemContext + TemporalContext + SecurityContext.

        Args:
            request: Request FastAPI
            input_data: Dados de input da request (body parseado)

        Returns:
            RichContext com todas as dimensões
        """
        # Construir RequestContext base
        request_context = await self.build(request, input_data)

        # Obter AuthContext para SecurityContext
        auth_context = await self._get_auth_context(request)

        # Construir dimensões adicionais
        system_context = SystemContext()  # Defaults
        temporal_context = TemporalContext()  # Defaults
        security_context = self._build_security_context(auth_context)

        return RichContext(
            request=request_context,
            tenant=request_context.tenant,
            session=request_context.session,
            actor=request_context.actor,
            system=system_context,
            temporal=temporal_context,
            security=security_context,
        )

    async def _get_auth_context(self, request: Request) -> AuthContext:
        """
        Obtém AuthContext da request (processado pelo JWTAuthMiddleware).

        Implementa INV-7: Extrair user_id e tenant_id do JWT.
        """
        try:
            return await get_auth_context(request)
        except HTTPException:
            # Se não tem auth ou falhou, retorna AuthContext não autenticado
            return AuthContext(authenticated=False)

    def _generate_request_id(self) -> str:
        """Gera request_id único."""
        if self.config.generate_request_id:
            return f"req-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        return "unknown"

    def _extract_input(self, input_data: dict[str, Any]) -> tuple[str | None, list[str]]:
        """
        Extrai input_text e input_files dos dados da request.

        Args:
            input_data: Body da request parseado

        Returns:
            Tupla (input_text, input_files)
        """
        # Extrair input.text
        input_text = None
        if "input" in input_data:
            input_obj = input_data["input"]
            if isinstance(input_obj, dict):
                input_text = input_obj.get("text")
            elif isinstance(input_obj, str):
                input_text = input_obj

        # Extrair input.files
        input_files = []
        if "input" in input_data:
            input_obj = input_data["input"]
            if isinstance(input_obj, dict):
                files = input_obj.get("files", [])
                input_files = files if isinstance(files, list) else []

        return input_text, input_files

    def _build_tenant_context(self, auth_context: AuthContext) -> TenantContext | None:
        """
        Constrói TenantContext a partir do AuthContext.

        Implementa INV-7: Extrair tenant_id do JWT.

        Args:
            auth_context: Contexto de autenticação do JWT

        Returns:
            TenantContext ou None se não houver tenant_id
        """
        tenant_id = auth_context.tenant_id or self.config.default_tenant_id

        if not tenant_id:
            return None

        return TenantContext(tenant_id=tenant_id)

    def _build_session_context(
        self,
        auth_context: AuthContext,
        _request: Request,
    ) -> SessionContext | None:
        """
        Constrói SessionContext a partir do AuthContext.

        Implementa R-G4: Extrair session_id do JWT.

        Args:
            auth_context: Contexto de autenticação do JWT
            _request: Request FastAPI (mantido para compatibilidade futura)

        Returns:
            SessionContext ou None se não houver session_id
        """
        # Tentar obter session_id do AuthContext (do JWT)
        session_id = auth_context.session_id

        # Se não tem session_id no JWT e config permite gerar
        if not session_id and self.config.generate_session_id:
            session_id = f"session-{uuid4().hex[:16]}"

        if not session_id:
            return None

        return SessionContext(
            session_id=session_id,
            actor_id=auth_context.user_id,
        )

    def _build_actor_context(self, auth_context: AuthContext) -> ActorContext | None:
        """
        Constrói ActorContext a partir do AuthContext.

        Implementa INV-7: Extrair user_id do JWT.

        Args:
            auth_context: Contexto de autenticação do JWT

        Returns:
            ActorContext ou None se não houver user_id
        """
        user_id = auth_context.user_id

        if not user_id:
            return None

        # Determinar ActorType baseado no auth_method
        actor_type = ActorType.USER
        if auth_context.auth_method.value == "api_key":
            actor_type = ActorType.API_KEY
        elif auth_context.user_id.startswith("service-"):
            actor_type = ActorType.SERVICE

        return ActorContext(
            actor_id=user_id,
            actor_type=actor_type,
            permissions=auth_context.permissions or [],
        )

    def _extract_metadata(self, request: Request) -> dict[str, Any]:
        """
        Extrai metadados da request.

        Args:
            request: Request FastAPI

        Returns:
            Dict com metadados
        """
        metadata = {}

        # Client IP
        if self.config.extract_client_ip:
            metadata["client_ip"] = self._get_client_ip(request)

        # User Agent
        if self.config.extract_user_agent:
            metadata["user_agent"] = request.headers.get("user-agent")

        # Headers selecionados
        metadata["accept"] = request.headers.get("accept")
        metadata["accept_language"] = request.headers.get("accept-language")

        # Request info
        metadata["method"] = request.method
        metadata["path"] = request.url.path
        metadata["query_params"] = dict(request.query_params)

        return metadata

    def _get_client_ip(self, request: Request) -> str | None:
        """
        Obtém IP do cliente, considerando proxies.

        Tenta headers em ordem de prioridade:
        1. X-Forwarded-For (proxy/reverse proxy)
        2. X-Real-IP (nginx)
        3. CF-Connecting-IP (Cloudflare)
        4. Direct client address
        """
        # X-Forwarded-For pode ter múltiplos IPs: "client, proxy1, proxy2"
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # X-Real-IP (nginx)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Cloudflare
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            return cf_ip

        # Direct access (em dev/test)
        if hasattr(request, "client") and request.client:
            return request.client.host

        return None

    def _build_security_context(self, auth_context: AuthContext) -> SecurityContext:
        """
        Constrói SecurityContext a partir do AuthContext.

        Args:
            auth_context: Contexto de autenticação

        Returns:
            SecurityContext
        """
        return SecurityContext(
            authenticated=auth_context.authenticated,
            auth_method=auth_context.auth_method.value,
            permissions=auth_context.permissions or [],
            roles=auth_context.roles or [],
        )


# Instância singleton do Context Builder
_context_builder: ContextBuilder | None = None


def get_context_builder() -> ContextBuilder:
    """
    Retorna instância singleton do Context Builder.

    Returns:
        ContextBuilder
    """
    global _context_builder
    if _context_builder is None:
        _context_builder = ContextBuilder()
    return _context_builder


async def build_request_context(
    request: Request,
    input_data: dict[str, Any] | None = None,
) -> RequestContext:
    """
    Dependency do FastAPI para construir RequestContext.

    Uso:
        @app.post("/api/v1/nhm/request")
        async def handle_request(
            ctx: RequestContext = Depends(build_request_context)
        ):
            return {"request_id": ctx.request_id}

    Args:
        request: Request FastAPI (injetado automaticamente)
        input_data: Dados de input da request

    Returns:
        RequestContext construído

    Raises:
        HTTPException: Se falhar ao construir contexto
    """
    try:
        builder = get_context_builder()
        return await builder.build(request, input_data)
    except ContextBuilderError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e


async def build_rich_context(
    request: Request,
    input_data: dict[str, Any] | None = None,
) -> RichContext:
    """
    Dependency do FastAPI para construir RichContext completo.

    Uso:
        @app.post("/api/v1/nhm/request")
        async def handle_request(
            ctx: RichContext = Depends(build_rich_context)
        ):
            return {"request_id": ctx.request.request_id}

    Args:
        request: Request FastAPI (injetado automaticamente)
        input_data: Dados de input da request

    Returns:
        RichContext construído

    Raises:
        HTTPException: Se falhar ao construir contexto
    """
    try:
        builder = get_context_builder()
        return await builder.build_rich(request, input_data)
    except ContextBuilderError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e
