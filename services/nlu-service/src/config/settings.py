"""Configurações do NLU Service."""

from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class NLUServiceSettings(BaseSettings):
    """Configurações do NLU Service."""

    # Service
    service_name: str = Field(default="nlu-service", description="Nome do serviço")
    service_version: str = Field(default="0.1.0", description="Versão do serviço")
    host: str = Field(default="0.0.0.0", description="Host para escutar")
    port: int = Field(default=8020, description="Porta HTTP/REST")
    grpc_port: int = Field(default=8021, description="Porta gRPC")

    # NLU Model
    nlu_language_model: str = Field(default="pt_core_news_sm", description="Modelo spaCy principal")
    nlu_model_cache_dir: Path = Field(
        default=Path("/app/models/spacy"), description="Diretório de cache dos modelos"
    )
    nlu_confidence_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Threshold de confiança base"
    )
    nlu_adaptive_threshold_enabled: bool = Field(
        default=True, description="Habilitar threshold adaptativo"
    )

    # Cache
    nlu_cache_enabled: bool = Field(default=True, description="Habilitar cache Redis")
    nlu_cache_ttl_seconds: int = Field(default=3600, description="TTL do cache em segundos")
    nlu_rules_config_path: str = Field(
        default="/app/config/nlu_rules.yaml", description="Path do arquivo de regras"
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="URL do Redis")
    redis_pool_size: int = Field(default=10, description="Tamanho do pool de conexões")
    redis_socket_timeout: float = Field(default=5.0, description="Timeout do socket Redis")

    # Observability
    otlp_endpoint: str = Field(
        default="http://localhost:4317", description="Endpoint OTLP para tracing"
    )
    otlp_insecure: bool = Field(default=True, description="Conexão insegura OTLP")
    enable_tracing: bool = Field(default=True, description="Habilitar tracing distribuído")
    enable_metrics: bool = Field(default=True, description="Habilitar métricas Prometheus")

    # Supported languages
    supported_languages: List[str] = Field(
        default=["pt", "en", "es"], description="Idiomas suportados"
    )

    # Processing limits
    max_text_length: int = Field(
        default=10000, ge=1, le=50000, description="Tamanho máximo do texto"
    )
    min_text_length: int = Field(default=3, ge=1, description="Tamanho mínimo do texto")
    processing_timeout_ms: int = Field(
        default=5000, ge=100, description="Timeout de processamento em ms"
    )

    # Cache warming
    enable_cache_warming: bool = Field(
        default=True, description="Habilitar cache warming na inicialização"
    )
    warmup_queries: List[str] = Field(
        default=[
            "status do sistema",
            "relatório de vendas",
            "deploy em produção",
        ],
        description="Queries para warmup",
    )

    @field_validator("nlu_model_cache_dir", mode="before")
    @classmethod
    def parse_model_cache_dir(cls, v):
        if isinstance(v, str):
            return Path(v)
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "NLU_"
        case_sensitive = False


# Global settings instance
_settings: NLUServiceSettings | None = None


def get_settings() -> NLUServiceSettings:
    """Retorna instância singleton de configurações."""
    global _settings
    if _settings is None:
        _settings = NLUServiceSettings()
    return _settings
