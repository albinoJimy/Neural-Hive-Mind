"""
Configuração para OPA Client.

Modelo de configuração centralizado.
"""
from typing import Any

from pydantic import BaseModel, Field


class OPAConfig(BaseModel):
    """Configuração do cliente OPA."""

    opa_url: str = Field(default="http://localhost:8181", description="URL base do OPA")
    opa_host: str | None = Field(default=None, description="Host OPA (para compatibilidade)")
    opa_port: int | None = Field(default=None, description="Porta OPA (para compatibilidade)")
    opa_timeout_seconds: int = Field(default=5, description="Timeout em segundos")
    opa_cache_ttl_seconds: int = Field(default=300, description="TTL do cache em segundos")
    opa_circuit_breaker_enabled: bool = Field(default=True, description="Habilitar circuit breaker")
    opa_circuit_breaker_failure_threshold: int = Field(
        default=5, description="Limite de falhas para abrir circuit breaker"
    )
    opa_circuit_breaker_reset_timeout_seconds: int = Field(
        default=60, description="Timeout de reset do circuit breaker"
    )
    opa_max_concurrent_evaluations: int = Field(
        default=20, description="Máximo de avaliações concorrentes"
    )
    opa_cache_max_size: int = Field(default=1000, description="Tamanho máximo do cache LRU")
    opa_retry_attempts: int = Field(default=3, description="Número de tentativas de retry")
    opa_retry_initial_delay: float = Field(default=0.1, description="Delay inicial para retry (s)")
    opa_retry_max_delay: float = Field(default=2.0, description="Delay máximo para retry (s)")
    opa_connection_pool_size: int = Field(default=100, description="Tamanho do pool de conexões")
    opa_enable_metrics: bool = Field(default=True, description="Habilitar métricas Prometheus")

    def model_post_init(self, __context: Any) -> None:
        """Post-init para derivar host/port da URL se necessário."""
        if self.opa_host is None or self.opa_port is None:
            # Extrair host e port da URL se não fornecidos
            parsed_url = self.opa_url.strip("http://").strip("https://")
            if ":" in parsed_url:
                host, port = parsed_url.split(":", 1)
                self.opa_host = host
                try:
                    self.opa_port = int(port)
                except ValueError:
                    self.opa_port = 8181
            else:
                self.opa_host = parsed_url
                self.opa_port = 8181
