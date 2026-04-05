"""
Configurações do ML Inference API usando Pydantic Settings.
"""
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from neural_hive_security.cors import CORSConfig


class MLInferenceSettings(BaseSettings):
    """Configurações do ML Inference API."""

    # Configurações gerais
    service_name: str = Field(default="ml-inference-api", description="Nome do serviço")
    service_version: str = Field(default="1.0.0", description="Versão do serviço")
    environment: str = Field(default="development", description="Ambiente de execução")
    log_level: str = Field(default="INFO", description="Nível de log")
    is_public_api: bool = Field(default=True, description="API pública requer CORS")

    # API
    api_host: str = Field(default="0.0.0.0", description="Host da API")
    api_port: int = Field(default=8010, description="Porta da API")

    # MLflow / Model Registry
    mlflow_tracking_uri: str = Field(
        default="http://mlflow:5000", description="URI do MLflow Tracking Server"
    )
    mlflow_model_name: str = Field(
        default="nhm_approval_model", description="Nome do modelo no MLflow"
    )
    local_model_path: str = Field(
        default="/app/ml_models", description="Caminho local para modelos"
    )

    # Batch Inference
    batch_default_size: int = Field(
        default=10, description="Tamanho padrão do batch"
    )
    batch_max_size: int = Field(
        default=100, description="Tamanho máximo do batch"
    )
    batch_timeout_seconds: float = Field(
        default=5.0, description="Timeout para acumular batch (segundos)"
    )

    # Rate Limiting
    enable_rate_limiting: bool = Field(
        default=True, description="Habilitar rate limiting"
    )
    rate_limit_requests_per_minute: int = Field(
        default=60, description="Limite de requests por minuto"
    )

    # GPU (opcional)
    enable_gpu: bool = Field(default=False, description="Habilitar inferência em GPU")
    gpu_memory_fraction: float = Field(
        default=0.8, description="Fração de memória GPU a usar"
    )
    gpu_device_id: int = Field(default=0, description="ID do dispositivo GPU")

    # Circuit Breaker
    circuit_breaker_threshold: int = Field(
        default=5, description="Número de falhas para abrir circuit breaker"
    )
    circuit_breaker_timeout_seconds: int = Field(
        default=60, description="Tempo para manter circuit breaker aberto (segundos)"
    )
    circuit_breaker_recovery_timeout_seconds: int = Field(
        default=30, description="Tempo para tentar recuperação (segundos)"
    )

    # Observabilidade
    otel_exporter_endpoint: str = Field(
        default="http://otel-collector:4317",
        description="Endpoint do OpenTelemetry Collector",
    )
    prometheus_port: int = Field(
        default=9091, description="Porta de métricas Prometheus"
    )
    jaeger_sampling_rate: float = Field(
        default=0.1, description="Taxa de sampling Jaeger"
    )

    # CORS (para overrides)
    cors_origins: Optional[str] = Field(
        default=None, description="Origens CORS (override via string)"
    )

    # Autenticação
    enable_auth: bool = Field(
        default=False, description="Habilitar autenticação JWT"
    )
    jwt_secret_key: str = Field(
        default="change-me-in-production", description="Chave secreta JWT"
    )
    jwt_algorithm: str = Field(default="HS256", description="Algoritmo JWT")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validar ambiente."""
        allowed = ["development", "staging", "production", "test"]
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v

    @field_validator("api_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validar porta."""
        if not 1024 <= v <= 65535:
            raise ValueError("Port must be between 1024 and 65535")
        return v

    @field_validator("batch_default_size", "batch_max_size")
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        """Validar tamanho do batch."""
        if v <= 0:
            raise ValueError("Batch size must be positive")
        return v

    @field_validator("gpu_memory_fraction")
    @classmethod
    def validate_gpu_fraction(cls, v: float) -> float:
        """Validar fração de GPU."""
        if not 0.0 < v <= 1.0:
            raise ValueError("GPU memory fraction must be between 0 and 1")
        return v

    @field_validator("circuit_breaker_threshold")
    @classmethod
    def validate_circuit_breaker_threshold(cls, v: int) -> int:
        """Validar threshold do circuit breaker."""
        if v <= 0:
            raise ValueError("Circuit breaker threshold must be positive")
        return v

    @model_validator(mode="after")
    def validate_batch_sizes(self) -> "MLInferenceSettings":
        """Validar que batch_default_size <= batch_max_size."""
        if self.batch_default_size > self.batch_max_size:
            raise ValueError(
                "batch_default_size must be <= batch_max_size"
            )
        return self

    @model_validator(mode="after")
    def validate_jwt_secret_in_production(self) -> "MLInferenceSettings":
        """Validar que JWT secret não seja padrão em produção."""
        if (
            self.environment == "production"
            and self.enable_auth
            and self.jwt_secret_key in ["changeme", "default", "secret", "change-me-in-production"]
        ):
            raise ValueError(
                "JWT secret key cannot be default value in production"
            )
        return self

    @property
    def CORS_ORIGINS(self) -> List[str]:
        """
        CORS origins dinâmicas por ambiente usando neural_hive_security.
        """
        if self.cors_origins:
            import json
            try:
                return json.loads(self.cors_origins)
            except json.JSONDecodeError:
                pass
        return CORSConfig.get_origins_for_environment(
            self.environment, is_public_api=self.is_public_api
        )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )


@lru_cache()
def get_settings() -> MLInferenceSettings:
    """Retorna singleton de configurações."""
    return MLInferenceSettings()
