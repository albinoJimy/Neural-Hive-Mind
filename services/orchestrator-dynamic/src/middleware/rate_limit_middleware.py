"""
Rate Limit Middleware para FastAPI usando Token Bucket algorithm.

Integra-se com neural_hive_resilience.TokenBucketRateLimiter para
controle de requisições por tenant, usuário e endpoint.
"""
import time

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from dataclasses import dataclass

from neural_hive_resilience import (
    RateLimiterFactory,
    RateLimitResult,
)

from src.config.rate_limit_config import get_rate_limit_config, RateLimitConfig

logger = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware de Rate Limiting usando Token Bucket algorithm.

    Extrai contexto dos headers (X-Tenant-ID, X-User-ID) e da request (method, path)
    para construir chave hierárquica: rate_limit:{tenant_id}:{user_id}:{endpoint}

    Adiciona headers RateLimit-* nas respostas e retorna HTTP 429 quando excedido.
    """

    # Valores padrão para headers ausentes
    DEFAULT_TENANT_ID = "anonymous"
    DEFAULT_USER_ID = "anonymous"

    def __init__(
        self,
        app,
        redis_client,  # pylint: disable=unused-argument
        settings,
    ):
        """
        Inicializa o middleware de Rate Limiting (1.3).

        Args:
            app: Instância do FastAPI
            redis_client: Cliente Redis (para uso futuro com backend distribuído)
            settings: Configurações do Orchestrator
        """
        super().__init__(app)
        self.settings = settings
        self.enable_rate_limiting = getattr(settings, "enable_rate_limiting", True)
        self.redis_client = redis_client
        self.service_name = getattr(settings, "service_name", "orchestrator-dynamic")

        # Configurações de rate limit
        self.default_capacity = getattr(settings, "rate_limit_default_capacity", 100)
        self.default_refill_rate = getattr(
            settings, "rate_limit_default_refill_rate", 10.0
        )
        self.burst_multiplier = getattr(settings, "rate_limit_burst_multiplier", 2.0)
        self.redis_key_prefix = getattr(
            settings, "rate_limit_redis_key_prefix", "rate_limit"
        )
        self.tier_limits = getattr(settings, "rate_limit_tier_limits", {})

        # Factory para criar rate limiters
        self.limiter_factory = RateLimiterFactory(service_name=self.service_name)

        # Cache de limiters por chave (in-memory para Task 1, Redis para Task 2)
        self._limiters_cache: dict[str, object] = {}

        logger.info(
            "rate_limit_middleware_initialized",
            enabled=self.enable_rate_limiting,
            default_capacity=self.default_capacity,
            default_refill_rate=self.default_refill_rate,
            burst_multiplier=self.burst_multiplier,
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Processa request e aplica rate limiting (1.4).

        Args:
            request: Request HTTP
            call_next: Próximo middleware/handler na chain

        Returns:
            Response com headers RateLimit-* ou 429 se excedido
        """
        # Se rate limiting desabilitado, bypass
        if not self.enable_rate_limiting:
            return await call_next(request)

        # Extrair contexto da request
        tenant_id = self._extract_tenant_id(request)
        user_id = self._extract_user_id(request)
        endpoint = self._extract_endpoint(request)

        # Construir chave de rate limit
        rate_limit_key = self._build_rate_limit_key(
            tenant_id=tenant_id,
            user_id=user_id,
            endpoint=endpoint,
        )

        # Verificar rate limit
        rate_limit_result = await self._check_rate_limit(
            key=rate_limit_key,
            tenant_id=tenant_id,
            method=request.method,
            path=request.url.path,
        )

        # Se permitido, adicionar headers e continuar
        if rate_limit_result.allowed:
            response = await call_next(request)
            self._add_rate_limit_headers(
                response=response,
                result=rate_limit_result,
                capacity=self.default_capacity,
            )
            return response

        # Se negado, retornar 429 com Retry-After (1.6)
        return self._create_rate_limit_exceeded_response(
            result=rate_limit_result,
            tenant_id=tenant_id,
        )

    def _extract_tenant_id(self, request: Request) -> str:
        """
        Extrai tenant_id do header X-Tenant-ID.

        Args:
            request: Request HTTP

        Returns:
            Tenant ID ou DEFAULT_TENANT_ID se ausente
        """
        return request.headers.get("X-Tenant-ID", self.DEFAULT_TENANT_ID)

    def _extract_user_id(self, request: Request) -> str:
        """
        Extrai user_id do header X-User-ID.

        Args:
            request: Request HTTP

        Returns:
            User ID ou DEFAULT_USER_ID se ausente
        """
        return request.headers.get("X-User-ID", self.DEFAULT_USER_ID)

    def _extract_endpoint(self, request: Request) -> str:
        """
        Extrai endpoint no formato {method}:{path}.

        Args:
            request: Request HTTP

        Returns:
            Endpoint string (ex: "POST:/api/v1/workflows")
        """
        return f"{request.method}:{request.url.path}"

    def _build_rate_limit_key(
        self,
        tenant_id: str,
        user_id: str,
        endpoint: str,
    ) -> str:
        """
        Constrói chave Redis para rate limiting.

        Formato: {prefix}:{tenant_id}:{user_id}:{endpoint}

        Args:
            tenant_id: ID do tenant
            user_id: ID do usuário
            endpoint: Endpoint (method:path)

        Returns:
            Chave de rate limit
        """
        return f"{self.redis_key_prefix}:{tenant_id}:{user_id}:{endpoint}"

    def _get_tier_config(self, tenant_id: str) -> dict | None:
        """
        Obtém configuração de tier para um tenant específico.

        Verifica se o tenant_id tem um tier específico configurado em
        rate_limit_tier_limits e retorna a configuração correspondente.

        Args:
            tenant_id: ID do tenant (ex: "tenant-premium-123")

        Returns:
            Dict com capacity e refill_rate do tier, ou None se não encontrado
        """
        if not self.tier_limits:
            return None

        # Tentar mapear tenant_id para tier baseado em prefixo
        # Ex: "tenant-premium-123" -> "premium"
        for tier_name, tier_config in self.tier_limits.items():
            # Verificar se tenant_id começa com prefixo do tier
            tier_prefix = f"{tier_name.lower()}-"
            if tenant_id.lower().startswith(tier_prefix):
                return tier_config

        # Verificar se há configuração exata para este tenant_id
        if tenant_id in self.tier_limits:
            return self.tier_limits[tenant_id]

        return None

    def _get_or_create_limiter(self, key: str, method: str, path: str, tenant_id: str):
        """
        Obtém ou cria limiter para chave específica.

        Usa cache in-memory. Prioriza configurações na seguinte ordem:
        1. Configuração específica do endpoint (se existir)
        2. Configuração de tier do tenant (se existir)
        3. Configuração padrão do sistema

        Args:
            key: Chave de rate limit
            method: Método HTTP (ex: "POST")
            path: Caminho do endpoint (ex: "/api/v1/workflows")
            tenant_id: ID do tenant para verificar tier limits

        Returns:
            TokenBucketRateLimiter instance
        """
        if key not in self._limiters_cache:
            # Criar config padrão
            default_config = RateLimitConfig(
                capacity=self.default_capacity,
                refill_rate=self.default_refill_rate,
                burst_multiplier=self.burst_multiplier,
            )

            # Obter config do endpoint (se existir)
            endpoint_config = get_rate_limit_config(
                method=method,
                path=path,
                default_config=default_config,
            )

            # Verificar se tenant tem tier específico com limites diferentes
            tier_config = self._get_tier_config(tenant_id)
            if tier_config:
                # Tier config sobrescreve capacity e refill_rate
                # Mas mantém burst_multiplier do endpoint
                capacity = tier_config.get("capacity", endpoint_config.capacity)
                refill_rate = tier_config.get("refill_rate", endpoint_config.refill_rate)
            else:
                capacity = endpoint_config.capacity
                refill_rate = endpoint_config.refill_rate

            # Usar burst_multiplier do endpoint (ou padrão se não especificado)
            burst_multiplier = endpoint_config.burst_multiplier

            # Calcular capacidade efetiva com burst
            effective_capacity = int(capacity * burst_multiplier)

            self._limiters_cache[key] = self.limiter_factory.token_bucket(
                capacity=effective_capacity,
                refill_rate=refill_rate,
                name=key,
            )

            logger.debug(
                "rate_limiter_created",
                key=key,
                tenant_id=tenant_id,
                endpoint=f"{method}:{path}",
                capacity=capacity,
                effective_capacity=effective_capacity,
                refill_rate=refill_rate,
                burst_multiplier=burst_multiplier,
                tier_config=bool(tier_config),
            )

        return self._limiters_cache[key]

    async def _check_rate_limit(
        self,
        key: str,
        tenant_id: str,
        method: str,
        path: str,
    ) -> RateLimitResult:
        """
        Verifica se requisição deve ser permitida.

        Args:
            key: Chave de rate limit
            tenant_id: ID do tenant para verificar tier limits
            method: Método HTTP
            path: Caminho do endpoint

        Returns:
            RateLimitResult com status da verificação
        """
        limiter = self._get_or_create_limiter(key, method, path, tenant_id)

        try:
            result = await limiter.acquire(tokens=1, block=False)

            logger.debug(
                "rate_limit_check_passed",
                key=key,
                tenant_id=tenant_id,
                tokens_remaining=result.tokens_remaining,
            )

        except Exception as e:
            # RateLimitExceededError ou outro erro
            retry_after = getattr(e, "retry_after", 60.0)

            logger.warning(
                "rate_limit_exceeded",
                key=key,
                tenant_id=tenant_id,
                error=str(e),
                retry_after=retry_after,
            )

            return RateLimitResult(
                allowed=False,
                tokens_remaining=0,
                retry_after=retry_after,
                reset_time=time.time() + retry_after,
            )
        else:
            return result

    def _add_rate_limit_headers(
        self,
        response: Response,
        result: RateLimitResult,
        capacity: int,
    ) -> None:
        """
        Adiciona headers RateLimit-* na resposta (1.5).

        Args:
            response: Response HTTP
            result: Resultado do rate limit check
            capacity: Capacidade configurada
        """
        response.headers["RateLimit-Limit"] = f"{capacity};w=60"
        response.headers["RateLimit-Remaining"] = str(result.tokens_remaining)
        response.headers["RateLimit-Reset"] = str(int(result.reset_time))

    def _create_rate_limit_exceeded_response(
        self,
        result: RateLimitResult,
        tenant_id: str,
    ) -> JSONResponse:
        """
        Cria resposta HTTP 429 com Retry-After (1.6).

        Args:
            result: Resultado do rate limit check
            tenant_id: ID do tenant

        Returns:
            JSONResponse com status 429
        """
        # Arredondar para cima e garantir mínimo de 1 segundo
        retry_after_seconds = max(
            1, int(result.retry_after) + (1 if result.retry_after % 1 > 0 else 0)
        )

        headers = {
            "RateLimit-Limit": f"{self.default_capacity};w=60",
            "RateLimit-Remaining": "0",
            "RateLimit-Reset": str(int(result.reset_time)),
            "Retry-After": str(retry_after_seconds),
            "Content-Type": "application/json",
        }

        logger.warning(
            "rate_limit_denied",
            tenant_id=tenant_id,
            retry_after=retry_after_seconds,
        )

        return JSONResponse(
            status_code=429,
            headers=headers,
            content={
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded. Retry after {retry_after_seconds} seconds.",
                "tenant_id": tenant_id,
                "limit": self.default_capacity,
                "window": 60,
                "retry_after": retry_after_seconds,
            },
        )
