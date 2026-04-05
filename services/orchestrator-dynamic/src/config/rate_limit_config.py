"""
Configuração de Rate Limiting por endpoint.

Este módulo define a configuração de rate limiting por endpoint, permitindo
limites diferentes dependendo do custo e criticidade de cada operação.
"""
from dataclasses import dataclass

from structlog import get_logger

logger = get_logger()


@dataclass
class RateLimitConfig:
    """
    Configuração de Token Bucket para um endpoint específico.

    Attributes:
        capacity: Capacidade base do token bucket (máximo de tokens)
        refill_rate: Taxa de refill (tokens por segundo)
        burst_multiplier: Multiplicador para capacidade de burst (padrão: 2.0)

    A capacidade efetiva do bucket é `capacity * burst_multiplier`, permitindo
    bursts temporários acima da capacidade base.
    """

    capacity: int
    refill_rate: float
    burst_multiplier: float = 2.0

    def get_effective_capacity(self) -> int:
        """
        Calcula a capacidade efetiva considerando o burst multiplier.

        Returns:
            Capacidade efetiva do bucket (int)
        """
        return int(self.capacity * self.burst_multiplier)


# Config por endpoint (method:path -> config)
# Limites são definidos baseados no custo e criticidade da operação:
# - Endpoints ML custosos (predict): limites mais baixos
# - Health checks: limites mais altos (operações baratas)
# - Workflows: limites moderados (operação principal)
ENDPOINT_RATE_LIMITS: dict[str, RateLimitConfig] = {
    "POST:/api/v1/workflows": RateLimitConfig(
        capacity=50,
        refill_rate=5,
        burst_multiplier=2.0,
    ),
    "POST:/api/v1/predict": RateLimitConfig(
        capacity=10,
        refill_rate=1,
        burst_multiplier=2.0,  # ML endpoint é custoso
    ),
    "GET:/api/v1/health": RateLimitConfig(
        capacity=1000,
        refill_rate=100,
        burst_multiplier=2.0,  # Health check é barato
    ),
}


def get_rate_limit_config(
    method: str,
    path: str,
    default_config: RateLimitConfig,
) -> RateLimitConfig:
    """
    Retorna a configuração de rate limiting para um endpoint específico.

    A busca é feita pela chave "{method}:{path}". Se o endpoint não estiver
    configurado em ENDPOINT_RATE_LIMITS, retorna a configuração padrão.

    Args:
        method: Método HTTP (GET, POST, PUT, DELETE, etc)
        path: Caminho do endpoint (deve começar com /)
        default_config: Configuração padrão caso endpoint não seja encontrado

    Returns:
        RateLimitConfig para o endpoint ou default_config se não encontrado

    Example:
        >>> default = RateLimitConfig(capacity=100, refill_rate=10)
        >>> config = get_rate_limit_config("POST", "/api/v1/workflows", default)
        >>> config.capacity
        50
        >>> config = get_rate_limit_config("GET", "/unknown", default)
        >>> config.capacity
        100
    """
    key = f"{method}:{path}"

    if key in ENDPOINT_RATE_LIMITS:
        logger.debug("using_endpoint_rate_limit_config", endpoint=key)
        return ENDPOINT_RATE_LIMITS[key]

    logger.debug("using_default_rate_limit_config", method=method, path=path)
    return default_config


__all__ = [
    "ENDPOINT_RATE_LIMITS",
    "RateLimitConfig",
    "get_rate_limit_config",
]
