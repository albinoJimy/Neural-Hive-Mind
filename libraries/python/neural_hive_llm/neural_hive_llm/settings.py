"""Configurações para clientes LLM via Pydantic Settings.

Implementa carregamento de configurações de variáveis de ambiente
com validação usando Pydantic Settings.
"""

import os
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import LLMProvider


class LLMSettings(BaseSettings):
    """Configurações para clientes LLM.

    Carrega configurações de variáveis de ambiente com prefixo LLM_.

    Attributes:
        provider: Provedor LLM (openai, anthropic, local)
        api_key: Chave de API para provedores externos
        model: Nome do modelo a ser usado
        endpoint_url: URL customizada para provedor local
        timeout: Timeout de requisição em segundos
        max_retries: Número máximo de tentativas de retry
        base_delay: Delay base para exponential backoff
        max_delay: Delay máximo para exponential backoff
        enable_circuit_breaker: Habilitar circuit breaker
        circuit_breaker_threshold: Falhas consecutivas para abrir circuito
        circuit_breaker_timeout: Timeout de recuperação do circuit breaker
        enable_tracing: Habilitar OpenTelemetry tracing
        enable_metrics: Habilitar métricas Prometheus
        service_name: Nome do serviço para observabilidade
    """

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Configurações básicas
    provider: LLMProvider = Field(
        default=LLMProvider.LOCAL,
        description="Provedor LLM",
    )

    api_key: Optional[str] = Field(
        default=None,
        description="Chave de API para provedores externos",
    )

    model: str = Field(
        default="gpt-4",
        description="Nome do modelo LLM",
    )

    endpoint_url: Optional[str] = Field(
        default=None,
        description="URL customizada para provedor local",
    )

    # Configurações de timeout e retry
    timeout: float = Field(
        default=60.0,
        ge=1.0,
        le=600.0,
        description="Timeout de requisição em segundos",
    )

    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Número máximo de tentativas de retry",
    )

    base_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Delay base para exponential backoff",
    )

    max_delay: float = Field(
        default=60.0,
        ge=1.0,
        le=300.0,
        description="Delay máximo para exponential backoff",
    )

    # Configurações de circuit breaker
    enable_circuit_breaker: bool = Field(
        default=True,
        description="Habilitar circuit breaker",
    )

    circuit_breaker_threshold: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Falhas consecutivas para abrir circuito",
    )

    circuit_breaker_timeout: float = Field(
        default=60.0,
        ge=10.0,
        le=600.0,
        description="Timeout de recuperação do circuit breaker",
    )

    # Configurações de observabilidade
    enable_tracing: bool = Field(
        default=True,
        description="Habilitar OpenTelemetry tracing",
    )

    enable_metrics: bool = Field(
        default=True,
        description="Habilitar métricas Prometheus",
    )

    service_name: str = Field(
        default="neural_hive_llm",
        description="Nome do serviço para observabilidade",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: Optional[str], info) -> Optional[str]:
        """Valida que api_key está presente para provedores externos.

        Args:
            v: Valor da api_key
            info: Informações do campo sendo validado

        Returns:
            Valor validado da api_key

        Raises:
            ValueError: Se api_key ausente para provedor que requer
        """
        provider = info.data.get("provider")
        if provider != LLMProvider.LOCAL and not v:
            raise ValueError(
                f"api_key é obrigatório para provider '{provider.value}'"
            )
        return v

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, v: Optional[str], info) -> Optional[str]:
        """Valida endpoint_url para provedor local.

        Args:
            v: Valor do endpoint_url
            info: Informações do campo sendo validado

        Returns:
            Valor validado do endpoint_url
        """
        provider = info.data.get("provider")
        if provider == LLMProvider.LOCAL and not v:
            # Usar padrão para Ollama
            return "http://localhost:11434/api"
        return v

    def get_model_pricing_key(self) -> str:
        """Retorna chave para lookup de precificação.

        Returns:
            Chave do modelo para tabela de preços
        """
        model_mapping = {
            # OpenAI
            "gpt-4": "gpt-4",
            "gpt-4-turbo": "gpt-4-turbo",
            "gpt-4o": "gpt-4o",
            "gpt-4o-mini": "gpt-4o-mini",
            "gpt-3.5-turbo": "gpt-3.5-turbo",
            # Anthropic
            "claude-3-opus": "claude-3-opus-20240229",
            "claude-3-sonnet": "claude-3-sonnet-20240229",
            "claude-3-haiku": "claude-3-haiku-20240307",
        }
        return model_mapping.get(self.model, self.model)

    def get_user_agent(self) -> str:
        """Retorna User-Agent para requisições HTTP.

        Returns:
            String User-Agent
        """
        return f"{self.service_name}/1.0"


# Instância global (singleton)
_settings_instance: Optional[LLMSettings] = None


def get_llm_settings(**overrides) -> LLMSettings:
    """Retorna instância de configurações LLM.

    Usa padrão singleton - primeiras chamadas criam a instância,
    chamadas subsequentes retornam a mesma instância.

    Args:
        **overrides: Overrides de configuração

    Returns:
        Instância de LLMSettings

    Example:
        ```python
        # Usar variáveis de ambiente
        settings = get_llm_settings()

        # Com overrides
        settings = get_llm_settings(provider=LLMProvider.OPENAI, model="gpt-4o")
        ```
    """
    global _settings_instance

    if _settings_instance is None:
        try:
            _settings_instance = LLMSettings()
        except Exception as e:
            # Se validação falhar, tentar sem api_key (para testes)
            import os

            if "LLM_API_KEY" in os.environ:
                raise
            # Fallback para configuração local sem validação
            _settings_instance = LLMSettings(
                provider=LLMProvider.LOCAL,
                api_key=None,
            )

    # Aplicar overrides se fornecidos
    if overrides:
        # Criar nova instância com overrides
        return LLMSettings(**{**_settings_instance.model_dump(), **overrides})

    return _settings_instance


def reset_llm_settings():
    """Reseta instância global de configurações (útil para testes)."""
    global _settings_instance
    _settings_instance = None


__all__ = [
    "LLMSettings",
    "get_llm_settings",
    "reset_llm_settings",
]
