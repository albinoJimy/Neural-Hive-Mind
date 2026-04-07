# Optimizer MCP Server Configuration

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

from neural_hive_security.cors import CORSConfig


class OptimizerMCPServerSettings(BaseSettings):
    """Configurações do Optimizer MCP Server."""

    service_name: str = "optimizer-mcp-server"
    service_version: str = "1.0.0"
    log_level: str = "INFO"

    # Configurações de análise
    max_files_per_scan: int = 100
    max_function_length: int = 100  # linhas
    complexity_threshold: int = 10  # McCabe

    # Configurações de performance
    default_duration: str = "1h"  # janela de análise

    # Ambiente
    environment: str = "development"
    is_public_api: bool = True

    class Config:
        env_prefix = "OPTIMIZER_MCP_"
        env_file = ".env"

    @property
    def CORS_ORIGINS(self) -> List[str]:
        """CORS origins dinâmicas por ambiente."""
        return CORSConfig.get_origins_for_environment(
            self.environment, is_public_api=self.is_public_api
        )


_settings_instance: OptimizerMCPServerSettings | None = None


def get_settings() -> OptimizerMCPServerSettings:
    """Retorna instância singleton de settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = OptimizerMCPServerSettings()
    return _settings_instance
