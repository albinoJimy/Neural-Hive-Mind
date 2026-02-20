"""
Rate Limiter usando Sliding Window Algorithm com Redis
Implementa rate limiting por usuario/tenant com suporte a burst capacity
"""

import asyncio
import time
from typing import Optional, Dict
from dataclasses import dataclass
import structlog
from prometheus_client import Counter, Histogram, Gauge

logger = structlog.get_logger(__name__)


@dataclass
class RateLimitResult:
    """Resultado da verificacao de rate limit"""

    allowed: bool
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp
    retry_after: Optional[int] = None  # Seconds to wait


class RateLimiter:
    """
    Implementa rate limiting usando Sliding Window Log com burst support

    Algoritmo:
    - Usa Redis sorted set para timestamps de requisicoes
    - Janela deslizante de 60 segundos (considera os ultimos 60s continuamente)
    - Suporta burst_size para permitir rajadas curtas acima do limite base
    - Suporta limites por user_id, tenant_id e globais
    - Fail-open se Redis indisponivel
    """

    WINDOW_SIZE_SECONDS = 60

    def __init__(
        self,
        redis_client,
        enabled: bool = True,
        default_limit: int = 1000,
        burst_size: int = 100,
        fail_open: bool = True,
    ):
        self.redis = redis_client
        self.enabled = enabled
        self.default_limit = default_limit
        self.burst_size = burst_size
        self.fail_open = fail_open

        # Configuracoes por tenant (pode ser carregado de config/database)
        self.tenant_limits: Dict[str, int] = {}
        self.user_limits: Dict[str, int] = {}

        # Metricas Prometheus - incluem user_id para visibilidade por usuario
        self.rate_limit_exceeded_counter = Counter(
            "gateway_rate_limit_exceeded_total",
            "Total de requisicoes bloqueadas por rate limiting",
            ["limit_type", "tenant_id", "user_id"],
        )

        self.rate_limit_check_duration = Histogram(
            "gateway_rate_limit_check_duration_seconds",
            "Duracao da verificacao de rate limit",
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        )

        self.rate_limit_current_usage = Gauge(
            "gateway_rate_limit_current_usage",
            "Uso atual do rate limit por usuario",
            ["tenant_id", "user_id"],
        )

        self.rate_limit_requests_total = Counter(
            "gateway_rate_limit_requests_total",
            "Total de requisicoes verificadas pelo rate limiter",
            ["tenant_id", "user_id", "allowed"],
        )

        logger.info(
            "rate_limiter_initialized",
            enabled=self.enabled,
            default_limit=self.default_limit,
            burst_size=self.burst_size,
            fail_open=self.fail_open,
        )

    async def check_rate_limit(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> RateLimitResult:
        """
        Verificar se requisicao esta dentro do rate limit usando sliding window

        Algoritmo Sliding Window Log:
        - Armazena timestamps de cada requisicao em um sorted set Redis
        - Remove timestamps fora da janela de 60 segundos
        - Conta requisicoes restantes na janela
        - Permite burst_size requisicoes adicionais para rajadas curtas

        Hierarquia de limites (do mais especifico ao mais geral):
        1. Limite por usuario especifico
        2. Limite por tenant
        3. Limite global padrao
        """
        if not self.enabled:
            return RateLimitResult(
                allowed=True,
                limit=self.default_limit,
                remaining=self.default_limit,
                reset_at=int(time.time()) + self.WINDOW_SIZE_SECONDS,
            )

        start_time = time.time()
        now = time.time()
        now_ms = int(now * 1000)  # Timestamp em milissegundos para maior precisao

        tenant_label = tenant_id or "unknown"
        user_label = user_id or "unknown"

        try:
            # Determinar limite aplicavel (base + burst)
            base_limit = self._get_applicable_limit(user_id, tenant_id)
            effective_limit = base_limit + self.burst_size

            # Chave Redis para sliding window (sorted set)
            key = f"gateway:rate_limit:sw:{user_id}"

            # Calcular janela de tempo
            window_start = now - self.WINDOW_SIZE_SECONDS
            window_start_ms = int(window_start * 1000)

            # Executar operacoes atomicas no Redis:
            # 1. Remover timestamps antigos (fora da janela)
            # 2. Adicionar timestamp atual
            # 3. Contar total na janela
            # 4. Definir TTL na chave
            count = await self._sliding_window_check(
                key=key,
                now_ms=now_ms,
                window_start_ms=window_start_ms,
                ttl=self.WINDOW_SIZE_SECONDS + 1,
            )

            # Calcular remaining e reset_at
            # reset_at e o tempo quando a janela comeca a "esquecer" requisicoes antigas
            reset_at = int(now) + self.WINDOW_SIZE_SECONDS
            remaining = max(0, effective_limit - count)

            # Verificar se permitido (count <= effective_limit pois ja adicionamos)
            allowed = count <= effective_limit

            # Registrar metricas
            duration = time.time() - start_time
            self.rate_limit_check_duration.observe(duration)

            # Atualizar gauge de uso atual com user_id
            self.rate_limit_current_usage.labels(
                tenant_id=tenant_label, user_id=user_label
            ).set(count)

            # Registrar requisicao total
            self.rate_limit_requests_total.labels(
                tenant_id=tenant_label, user_id=user_label, allowed=str(allowed).lower()
            ).inc()

            if not allowed:
                self.rate_limit_exceeded_counter.labels(
                    limit_type="user", tenant_id=tenant_label, user_id=user_label
                ).inc()

                # Calcular retry_after baseado na janela deslizante
                # Estimativa: tempo ate que requisicoes antigas expirem
                retry_after = max(1, self.WINDOW_SIZE_SECONDS - int(now - window_start))

                logger.warning(
                    "rate_limit_exceeded",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    count=count,
                    base_limit=base_limit,
                    burst_size=self.burst_size,
                    effective_limit=effective_limit,
                    retry_after=retry_after,
                )

                return RateLimitResult(
                    allowed=False,
                    limit=base_limit,  # Reporta limite base (sem burst) para o usuario
                    remaining=0,
                    reset_at=reset_at,
                    retry_after=retry_after,
                )

            logger.debug(
                "rate_limit_check_passed",
                user_id=user_id,
                tenant_id=tenant_id,
                count=count,
                base_limit=base_limit,
                burst_size=self.burst_size,
                effective_limit=effective_limit,
                remaining=remaining,
            )

            return RateLimitResult(
                allowed=True,
                limit=base_limit,  # Reporta limite base (sem burst) para o usuario
                remaining=max(
                    0, base_limit - count
                ),  # Remaining baseado no limite base
                reset_at=reset_at,
            )

        except Exception as e:
            duration = time.time() - start_time
            self.rate_limit_check_duration.observe(duration)

            # Fail-open: permitir requisicao se Redis falhar
            logger.error(
                "rate_limit_check_failed",
                error=str(e),
                user_id=user_id,
                fail_open=self.fail_open,
            )

            if self.fail_open:
                return RateLimitResult(
                    allowed=True,
                    limit=self.default_limit,
                    remaining=self.default_limit,
                    reset_at=int(time.time()) + self.WINDOW_SIZE_SECONDS,
                )
            else:
                # Fail-closed: bloquear se Redis falhar
                return RateLimitResult(
                    allowed=False,
                    limit=self.default_limit,
                    remaining=0,
                    reset_at=int(time.time()) + self.WINDOW_SIZE_SECONDS,
                    retry_after=self.WINDOW_SIZE_SECONDS,
                )

    async def _sliding_window_check(
        self, key: str, now_ms: int, window_start_ms: int, ttl: int
    ) -> int:
        """
        Executar verificacao de sliding window atomicamente no Redis

        Operacoes:
        1. ZREMRANGEBYSCORE - remove timestamps fora da janela
        2. ZADD - adiciona timestamp atual
        3. ZCARD - conta total na janela
        4. EXPIRE - define TTL na chave

        Retorna: contagem de requisicoes na janela (incluindo a atual)
        """
        try:
            # Usar pipeline para operacoes atomicas
            # Nota: A ordem importa - remover antigos, adicionar novo, contar
            operations = [
                {"method": "zremrangebyscore", "args": [key, 0, window_start_ms]},
                {"method": "zadd", "args": [key, {str(now_ms): now_ms}]},
                {"method": "zcard", "args": [key]},
                {"method": "expire", "args": [key, ttl]},
            ]

            results = await self.redis.pipeline_operations(operations)

            if results and len(results) >= 3:
                # Resultado do ZCARD e o terceiro item
                return int(results[2])

            return 1  # Fallback: assumir que esta e a primeira requisicao

        except Exception as e:
            logger.error("redis_sliding_window_failed", error=str(e), key=key)
            raise

    def _get_applicable_limit(self, user_id: str, tenant_id: Optional[str]) -> int:
        """Determinar limite aplicavel baseado em hierarquia"""

        # 1. Limite especifico do usuario
        if user_id in self.user_limits:
            return self.user_limits[user_id]

        # 2. Limite do tenant
        if tenant_id and tenant_id in self.tenant_limits:
            return self.tenant_limits[tenant_id]

        # 3. Limite global padrao
        return self.default_limit

    def set_user_limit(self, user_id: str, limit: int):
        """Configurar limite especifico para usuario"""
        self.user_limits[user_id] = limit
        logger.info("user_limit_set", user_id=user_id, limit=limit)

    def set_tenant_limit(self, tenant_id: str, limit: int):
        """Configurar limite especifico para tenant"""
        self.tenant_limits[tenant_id] = limit
        logger.info("tenant_limit_set", tenant_id=tenant_id, limit=limit)

    def remove_user_limit(self, user_id: str):
        """Remover limite especifico do usuario"""
        if user_id in self.user_limits:
            del self.user_limits[user_id]
            logger.info("user_limit_removed", user_id=user_id)

    def remove_tenant_limit(self, tenant_id: str):
        """Remover limite especifico do tenant"""
        if tenant_id in self.tenant_limits:
            del self.tenant_limits[tenant_id]
            logger.info("tenant_limit_removed", tenant_id=tenant_id)

    def get_current_limits(self) -> Dict:
        """Obter configuracao atual de limites"""
        return {
            "default_limit": self.default_limit,
            "burst_size": self.burst_size,
            "tenant_limits": self.tenant_limits.copy(),
            "user_limits": self.user_limits.copy(),
            "enabled": self.enabled,
            "fail_open": self.fail_open,
        }


# Singleton global para o rate limiter
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> Optional[RateLimiter]:
    """Obter instancia global do rate limiter"""
    return _rate_limiter


def set_rate_limiter(limiter: RateLimiter):
    """Definir instancia global do rate limiter"""
    global _rate_limiter
    _rate_limiter = limiter


def close_rate_limiter():
    """Fechar e limpar rate limiter global"""
    global _rate_limiter
    _rate_limiter = None
