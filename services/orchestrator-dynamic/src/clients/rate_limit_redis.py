"""Backend Redis distribuído para Token Bucket Rate Limiting.

Implementa operações atômicas via Lua script para evitar race conditions
em ambientes distribuídos com múltiplas instâncias do Orchestrator Dynamic.

Chave Redis: rate_limit:{tenant_id}:{user_id}:{endpoint}
TTL: 1 hora para chaves não utilizadas (economia de memória)
Fail-open: Retorna permissivo se Redis estiver indisponível
"""

from __future__ import annotations

import time

import redis.asyncio as redis
import structlog
from prometheus_client import Counter

from src.clients.redis_client import get_redis_client

logger = structlog.get_logger(__name__)


# =============================================================================
# Lua Script para Operação Atômica
# =============================================================================

REFILL_AND_ACQUIRE_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local tokens = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

-- Obter estado atual
local current = redis.call('HMGET', key, 'tokens', 'last_refill')
local current_tokens = tonumber(current[1]) or capacity
local last_refill = tonumber(current[2]) or now

-- Calcular refill
local elapsed = now - last_refill
local refill_amount = math.floor(elapsed * refill_rate)
current_tokens = math.min(capacity, current_tokens + refill_amount)

-- Verificar se pode consumir
local can_acquire = current_tokens >= tokens
if can_acquire then
    current_tokens = current_tokens - tokens
end

-- Salvar estado
redis.call('HMSET', key, 'tokens', current_tokens, 'last_refill', now)
redis.call('EXPIRE', key, 3600)

return {can_acquire and 1 or 0, current_tokens}
"""


# =============================================================================
# Métricas Prometheus
# =============================================================================

rate_limit_redis_errors_total = Counter(
    "rate_limit_redis_errors_total",
    "Total de erros Redis no rate limiting",
    ["service", "operation"],
)


# =============================================================================
# Funções Auxiliares
# =============================================================================


def generate_rate_limit_key(
    tenant_id: str,
    user_id: str,
    endpoint: str | None = None,
) -> str:
    """Gera chave Redis para rate limit.

    Args:
        tenant_id: ID do tenant
        user_id: ID do usuário
        endpoint: Path do endpoint (opcional, usa "global" se None)

    Returns:
        Chave Redis no formato: rate_limit:{tenant_id}:{user_id}:{endpoint}
    """

    # Sanitizar caracteres especiais para usar como chave Redis
    def sanitize(s: str) -> str:
        """Remove ou substitui caracteres problemáticos."""
        # Lista de caracteres a substituir
        replacements = {
            ":": "_",
            "/": "_",
            "?": "_",
            "&": "_",
            "@": "_",  # Adicionado para email
            "=": "_",
            ".": "_",  # Adicionado para dominios
        }
        for old, new in replacements.items():
            s = s.replace(old, new)
        return s

    safe_tenant = sanitize(tenant_id)
    safe_user = sanitize(user_id)
    safe_endpoint = sanitize(endpoint) if endpoint else "global"

    return f"rate_limit:{safe_tenant}:{safe_user}:{safe_endpoint}"


# =============================================================================
# Backend Redis
# =============================================================================


class RedisTokenBucketBackend:
    """Backend Redis distribuído para Token Bucket Rate Limiting.

    Implementa operações atômicas via Lua script para garantir consistência
    em ambientes com múltiplas instâncias do Orchestrator Dynamic.

    Comportamento fail-open: Se Redis estiver indisponível, retorna True
    (permitir requisição) para não degradar disponibilidade do serviço.

    Attributes:
        redis_client: Cliente Redis assíncrono
        service_name: Nome do serviço para métricas
        key_prefix: Prefixo para chaves Redis (default: "rate_limit")
        default_ttl: TTL em segundos para chaves (default: 3600)
    """

    def __init__(
        self,
        redis_client: redis.Redis | None,
        service_name: str = "orchestrator-dynamic",
        key_prefix: str = "rate_limit",
        default_ttl: int = 3600,
    ):
        """Inicializa backend Redis.

        Args:
            redis_client: Cliente Redis assíncrono (opcional)
            service_name: Nome do serviço para métricas
            key_prefix: Prefixo para chaves Redis
            default_ttl: TTL padrão em segundos
        """
        self.redis_client = redis_client
        self.service_name = service_name
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.logger = structlog.get_logger(__name__, service_name=service_name)

    async def _ensure_redis_client(self) -> redis.Redis | None:
        """Garante que cliente Redis está inicializado.

        Returns:
            Cliente Redis ou None se não disponível
        """
        if self.redis_client is None:
            self.redis_client = await get_redis_client()
        return self.redis_client

    async def acquire(
        self,
        tenant_id: str,
        user_id: str,
        endpoint: str | None,
        capacity: int,
        refill_rate: float,
        tokens: int = 1,
    ) -> bool:
        """Tenta adquirir tokens do bucket distribuído.

        Usa Lua script para operação atômica (check-and-set).

        Args:
            tenant_id: ID do tenant
            user_id: ID do usuário
            endpoint: Path do endpoint (opcional)
            capacity: Capacidade máxima do bucket
            refill_rate: Taxa de reabastecimento (tokens/segundo)
            tokens: Número de tokens a adquirir

        Returns:
            True se tokens foram adquiridos, False caso contrário
        """
        redis_client = await self._ensure_redis_client()

        if redis_client is None:
            # Fail-open: Redis indisponível, permitir requisição
            self.logger.warning(
                "rate_limit_redis_unavailable",
                tenant_id=tenant_id,
                user_id=user_id,
                endpoint=endpoint,
            )
            rate_limit_redis_errors_total.labels(
                service=self.service_name,
                operation="acquire",
            ).inc()
            return True

        key = generate_rate_limit_key(tenant_id, user_id, endpoint)
        now = time.monotonic()

        try:
            # Executar Lua script atomicamente
            result = await redis_client.eval(
                REFILL_AND_ACQUIRE_LUA,
                1,  # num_keys
                key,  # KEYS[1]
                capacity,  # ARGV[1]
                refill_rate,  # ARGV[2]
                tokens,  # ARGV[3]
                now,  # ARGV[4]
            )

            # Resultado é [allowed (0/1), tokens_restantes]
            allowed = bool(result[0])
            tokens_remaining = int(result[1])

            self.logger.debug(
                "rate_limit_acquire_result",
                key=key,
                allowed=allowed,
                tokens_remaining=tokens_remaining,
                tokens_requested=tokens,
            )

            return allowed

        except redis.ConnectionError as e:
            self.logger.warning(
                "rate_limit_redis_connection_error",
                key=key,
                error=str(e),
            )
            rate_limit_redis_errors_total.labels(
                service=self.service_name,
                operation="acquire",
            ).inc()
            # Fail-open: permitir requisição
            return True

        except Exception as e:
            self.logger.error(
                "rate_limit_redis_unexpected_error",
                key=key,
                error=str(e),
                error_type=type(e).__name__,
            )
            rate_limit_redis_errors_total.labels(
                service=self.service_name,
                operation="acquire",
            ).inc()
            # Fail-open: permitir requisição
            return True

    async def get_tokens(
        self,
        tenant_id: str,
        user_id: str,
        endpoint: str | None = None,
    ) -> int | None:
        """Consulta tokens disponíveis no bucket.

        Args:
            tenant_id: ID do tenant
            user_id: ID do usuário
            endpoint: Path do endpoint (opcional)

        Returns:
            Tokens disponíveis ou None se chave não existe/erro
        """
        redis_client = await self._ensure_redis_client()

        if redis_client is None:
            return None

        key = generate_rate_limit_key(tenant_id, user_id, endpoint)

        try:
            tokens_str = await redis_client.hget(key, "tokens")
            if tokens_str is None:
                return None
            return int(tokens_str)

        except (redis.ConnectionError, ValueError) as e:
            self.logger.warning(
                "rate_limit_get_tokens_error",
                key=key,
                error=str(e),
            )
            return None

    async def reset(
        self,
        tenant_id: str,
        user_id: str,
        endpoint: str | None = None,
        capacity: int = 100,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Reseta bucket para capacidade máxima.

        Args:
            tenant_id: ID do tenant
            user_id: ID do usuário
            endpoint: Path do endpoint (opcional)
            capacity: Nova capacidade (default: 100)
            ttl_seconds: TTL personalizado (usa default_ttl se None)

        Returns:
            True se reset bem-sucedido, False caso contrário
        """
        redis_client = await self._ensure_redis_client()

        if redis_client is None:
            return False

        key = generate_rate_limit_key(tenant_id, user_id, endpoint)
        now = time.monotonic()
        ttl = ttl_seconds or self.default_ttl

        try:
            await redis_client.hset(
                key,
                mapping={
                    "tokens": capacity,
                    "last_refill": now,
                },
            )
            await redis_client.expire(key, ttl)

            self.logger.debug(
                "rate_limit_reset",
                key=key,
                capacity=capacity,
                ttl=ttl,
            )

            return True

        except redis.ConnectionError as e:
            self.logger.warning(
                "rate_limit_reset_error",
                key=key,
                error=str(e),
            )
            return False

    async def delete(
        self,
        tenant_id: str,
        user_id: str,
        endpoint: str | None = None,
    ) -> bool:
        """Remove chave de rate limit.

        Args:
            tenant_id: ID do tenant
            user_id: ID do usuário
            endpoint: Path do endpoint (opcional)

        Returns:
            True se deletado com sucesso, False caso contrário
        """
        redis_client = await self._ensure_redis_client()

        if redis_client is None:
            return False

        key = generate_rate_limit_key(tenant_id, user_id, endpoint)

        try:
            result = await redis_client.delete(key)

            self.logger.debug(
                "rate_limit_delete",
                key=key,
                deleted=result,
            )

            return result > 0

        except redis.ConnectionError as e:
            self.logger.warning(
                "rate_limit_delete_error",
                key=key,
                error=str(e),
            )
            return False

    async def health_check(self) -> bool:
        """Verifica saúde da conexão Redis.

        Returns:
            True se Redis está respondendo, False caso contrário
        """
        redis_client = await self._ensure_redis_client()

        if redis_client is None:
            return False

        try:
            await redis_client.ping()
            return True

        except redis.ConnectionError:
            return False
