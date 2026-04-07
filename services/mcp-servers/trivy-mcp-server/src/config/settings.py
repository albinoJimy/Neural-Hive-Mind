"""Configurações do Trivy MCP Server."""

from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

from neural_hive_security.cors import CORSConfig


class Settings(BaseSettings):
    """Configurações do servidor via environment variables."""

    # Informações do serviço
    service_name: str = "trivy-mcp-server"
    service_version: str = "1.0.0"

    # Servidor HTTP
    http_host: str = "0.0.0.0"
    http_port: int = 3000

    # Trivy CLI
    trivy_path: str = "trivy"
    trivy_timeout: int = 300
    trivy_cache_dir: str = "/tmp/trivy-cache"

    # Observability
    otel_endpoint: str = "http://otel-collector:4317"
    log_level: str = "INFO"
    metrics_port: int = 9091

    # Ambiente
    environment: str = "development"
    is_public_api: bool = True

    class Config:
        env_prefix = ""
        case_sensitive = False

    @property
    def CORS_ORIGINS(self) -> List[str]:
        """CORS origins dinâmicas por ambiente."""
        return CORSConfig.get_origins_for_environment(
            self.environment, is_public_api=self.is_public_api
        )


@lru_cache()
def get_settings() -> Settings:
    """Retorna instância singleton das configurações."""
    return Settings()
