"""
Configuração para neural_hive_llm.

Define LLMSettings usando Pydantic Settings para configuração via ambiente.
"""

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from neural_hive_llm.models import LLMProvider


class LLMSettings(BaseSettings):
    """Configurações para clientes LLM via variáveis de ambiente.

    Variáveis de ambiente (prefixo LLM_):
        LLM_PROVIDER: Provider a usar (openai, anthropic, local)
        LLM_API_KEY: API key para providers remotos
        LLM_BASE_URL: URL base (para local provider)
        LLM_MODEL: Modelo a usar
        LLM_MAX_RETRIES: Máximo de tentativas de retry
        LLM_TIMEOUT_SECONDS: Timeout para requisições
        LLM_TEMPERATURE: Temperatura padrão
        LLM_MAX_TOKENS: Máximo de tokens padrão
    """

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Provider e autenticação
    provider: LLMProvider = Field(
        default=LLMProvider.LOCAL,
        description="Provider LLM a ser utilizado",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key para providers remotos (openai, anthropic)",
    )
    base_url: Optional[str] = Field(
        default="http://localhost:11434",
        description="URL base para provider local (Ollama)",
    )

    # Configurações de modelo
    model: str = Field(
        default="llama2",
        description="Modelo a ser utilizado (provider-specific)",
    )

    # Configurações de retry/resilience
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Número máximo de tentativas de retry",
    )
    retry_base_delay: float = Field(
        default=1.0,
        ge=0.1,
        description="Delay base para retry (exponential backoff)",
    )
    retry_max_delay: float = Field(
        default=60.0,
        ge=1.0,
        description="Delay máximo para retry",
    )
    timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=600.0,
        description="Timeout para requisições em segundos",
    )

    # Configurações de geração padrão
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperatura padrão para geração",
    )
    max_tokens: Optional[int] = Field(
        default=2048,
        ge=1,
        description="Máximo padrão de tokens a gerar",
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
        default="neural-hive-llm",
        description="Nome do serviço para métricas/tracing",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_for_remote_provider(cls, v: Optional[str], info) -> Optional[str]:
        """Valida que api_key está presente para providers remotos."""
        provider = info.data.get("provider")
        if provider in (LLMProvider.OPENAI, LLMProvider.ANTHROPIC):
            if not v:
                raise ValueError(f"api_key é obrigatório para provider {provider.value}")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url_for_local_provider(cls, v: Optional[str], info) -> Optional[str]:
        """Valida que base_url está presente para provider local."""
        provider = info.data.get("provider")
        if provider == LLMProvider.LOCAL and not v:
            return "http://localhost:11434"  # Default para Ollama
        return v


# Singleton para settings globais
_global_settings: Optional[LLMSettings] = None


def get_llm_settings(**kwargs) -> LLMSettings:
    """
    Retorna configurações LLM (singleton com override).

    Args:
        **kwargs: Override settings específicas

    Returns:
        LLMSettings: Configurações validadas

    Example:
        >>> settings = get_llm_settings(provider=LLMProvider.OPENAI)
        >>> settings = get_llm_settings()  # Usa variáveis de ambiente
    """
    global _global_settings

    if _global_settings is None:
        _global_settings = LLMSettings()

    if kwargs:
        # Criar cópia com overrides
        return _global_settings.model_copy(update=kwargs)

    return _global_settings


def reset_llm_settings() -> None:
    """Reseta o singleton de settings (útil para testes)."""
    global _global_settings
    _global_settings = None
