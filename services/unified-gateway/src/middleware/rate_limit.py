"""
Rate Limiting Middleware para Unified Gateway.

Implementa rate limiting por tenant usando Redis como backend.

Implementa INV-8: Rate limiting applied per-tenant before downstream
services, returns HTTP 429 with Retry-After.
"""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog
from fastapi import Request, Response, status
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class TenantTier(str, Enum):
    """Tiers de tenant para rate limiting."""

    TRIAL = "trial"
    DEFAULT = "default"
    ENTERPRISE = "enterprise"


@dataclass
class RateLimitConfig:
    """Configuração de rate limiting."""

    requests_per_minute: int
    requests_per_hour: int | None = None
    burst: int | None = None

    def __post_init__(self):
        if self.burst is None:
            self.burst = int(self.requests_per_minute * 1.5)


# Configurações por tier (INV-8)
RATE_LIMIT_TIERS = {
    TenantTier.TRIAL: RateLimitConfig(requests_per_minute=10),  # 10 req/min
    TenantTier.DEFAULT: RateLimitConfig(requests_per_minute=100),  # 100 req/min
    TenantTier.ENTERPRISE: RateLimitConfig(requests_per_minute=1000),  # 1000 req/min
}


@dataclass
class RateLimitResult:
    """Resultado da verificação de rate limit."""

    allowed: bool
    remaining: int
    reset_at: int  # Unix timestamp
    limit: int
    retry_after: int | None = None  # Segundos até retry


class RateLimitError(Exception):
    """Erro quando rate limit é excedido."""

    def __init__(self, result: RateLimitResult):
        self.result = result
        super().__init__(f"Rate limit exceeded: {result.retry_after}s until reset")


class RateLimiter:
    """
    Rate Limiter usando Redis com algoritmo de janela deslizante.

    Implementa INV-8: rate limiting por tenant com Redis backend.
    """

    def __init__(self, redis_url: str | None = None):
        """
        Inicializa rate limiter.

        Args:
            redis_url: URL do Redis (se None, usa settings)
        """
        self.redis_url = redis_url or settings.RATE_LIMIT_REDIS_URL
        self._redis: Redis | None = None

    async def get_redis(self) -> Redis:
        """Retorna conexão Redis (lazy)."""
        if self._redis is None:
            self._redis = Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def check_rate_limit(
        self,
        tenant_id: str,
        tier: TenantTier = TenantTier.DEFAULT,
        user_id: str | None = None,
        endpoint: str | None = None,
    ) -> RateLimitResult:
        """
        Verifica se request está dentro do rate limit.

        Implementa INV-8: retorna HTTP 429 com Retry-After se excedido.

        Args:
            tenant_id: ID do tenant
            tier: Tier do tenant
            user_id: ID do usuário (opcional, para rate limiting por usuário)
            endpoint: Endpoint específico (opcional, para rate limiting por endpoint)

        Returns:
            RateLimitResult com resultado da verificação
        """
        config = RATE_LIMIT_TIERS[tier]
        now = int(time.time())
        minute_window = now // 60
        minute_key = self._make_key(
            tenant_id, user_id, endpoint, "rate_limit", minute_window
        )

        redis = await self.get_redis()

        try:
            # Pipeline Redis para operações atômicas
            pipe = redis.pipeline()

            # Obter contador atual
            pipe.get(minute_key)
            # Obter TTL para reset time
            pipe.ttl(minute_key)

            results = await pipe.execute()

            current_count = int(results[0]) if results[0] else 0
            ttl = int(results[1]) if results[1] else 60

            # Verificar se excedeu limite
            if current_count >= config.requests_per_minute:
                # Rate limit excedido
                reset_at = now + ttl
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=reset_at,
                    limit=config.requests_per_minute,
                    retry_after=ttl,
                )

            # Incrementar contador
            pipe.incr(minute_key)
            # Configurar expiry (60 segundos)
            pipe.expire(minute_key, 60)

            await pipe.execute()

            # Retornar resultado permitido
            remaining = config.requests_per_minute - current_count - 1
            reset_at = now + (60 if ttl == 60 else ttl)

            return RateLimitResult(
                allowed=True,
                remaining=max(0, remaining),
                reset_at=reset_at,
                limit=config.requests_per_minute,
                retry_after=None,
            )

        except Exception as e:
            logger.error(
                "rate_limit_check_failed",
                tenant_id=tenant_id,
                error=str(e),
            )
            # Em caso de erro, permitir request (fail open)
            return RateLimitResult(
                allowed=True,
                remaining=config.requests_per_minute,
                reset_at=now + 60,
                limit=config.requests_per_minute,
                retry_after=None,
            )

    def _make_key(self, *parts: str) -> str:
        """Cria chave Redis."""
        return ":".join(f"unified_gateway:rate_limit:{p}" for p in parts if p)

    async def close(self):
        """Fecha conexão Redis."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware de rate limiting para Unified Gateway.

    Implementa INV-8: Rate limiting por tenant antes de serviços downstream.

    Paths excluídos do rate limiting podem ser configurados via exclude_paths.
    """

    def __init__(
        self,
        app,
        rate_limiter: RateLimiter | None = None,
        exclude_paths: list[str] | None = None,
        enabled: bool = True,
    ):
        """
        Inicializa middleware de rate limiting.

        Args:
            app: Aplicação FastAPI
            rate_limiter: Instância de RateLimiter
            exclude_paths: Paths para excluir do rate limiting
            enabled: Se False, rate limiting é desabilitado
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter()
        self.exclude_paths = exclude_paths or [
            "/health",
            "/health/ready",
            "/health/live",
            "/metrics",
        ]
        self.enabled = enabled

        logger.info(
            "rate_limit_middleware_initialized",
            enabled=enabled,
            exclude_paths=exclude_paths,
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Processa requisição com rate limiting.

        Implementa INV-8: retorna HTTP 429 com Retry-After se excedido.
        """
        path = request.url.path

        # Pular rate limiting para paths excluídos
        if not self.enabled or self._should_skip(path):
            return await call_next(request)

        # Extrair tenant_id do contexto de autenticação
        tenant_id = None
        user_id = None
        tier = TenantTier.DEFAULT

        if hasattr(request.state, "auth_context"):
            auth_ctx = request.state.auth_context
            tenant_id = auth_ctx.tenant_id or "anonymous"
            user_id = auth_ctx.user_id
            # Determinar tier baseado em roles ou claims
            if auth_ctx.roles and "enterprise" in auth_ctx.roles:
                tier = TenantTier.ENTERPRISE
            elif auth_ctx.roles and "trial" in auth_ctx.roles:
                tier = TenantTier.TRIAL
        else:
            tenant_id = "anonymous"

        # Verificar rate limit
        result = await self.rate_limiter.check_rate_limit(
            tenant_id=tenant_id,
            tier=tier,
            user_id=user_id,
            endpoint=path,
        )

        # Guardar resultado no state para uso posterior
        request.state.rate_limit_result = result

        # Se não permitido, retornar 429 com Retry-After (INV-8)
        if not result.allowed:
            logger.info(
                "rate_limit_exceeded",
                tenant_id=tenant_id,
                user_id=user_id,
                path=path,
                retry_after=result.retry_after,
            )
            return self._create_rate_limit_response(result)

        # Processar requisição
        response = await call_next(request)

        # Adicionar headers de rate limit à resposta (INV-8)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_at)

        return response

    def _should_skip(self, path: str) -> bool:
        """Verifica se path deve ser excluído do rate limiting."""
        return any(path.startswith(exclude_path) for exclude_path in self.exclude_paths)

    def _create_rate_limit_response(self, result: RateLimitResult) -> Response:
        """
        Cria resposta HTTP 429 com header Retry-After.

        Implementa INV-8: retorna HTTP 429 com Retry-After.
        """
        return Response(
            content=f'{{"error": "rate_limit_exceeded", "message": "Rate limit exceeded. Try again in {result.retry_after}s", "retry_after": {result.retry_after}}}',
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={
                "Retry-After": str(result.retry_after),  # INV-8
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(result.reset_at),
                "Content-Type": "application/json",
            },
            media_type="application/json",
        )


# Singleton para reutilização
_rate_limiter_singleton: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Retorna instância singleton de RateLimiter."""
    global _rate_limiter_singleton
    if _rate_limiter_singleton is None:
        _rate_limiter_singleton = RateLimiter()
    return _rate_limiter_singleton
