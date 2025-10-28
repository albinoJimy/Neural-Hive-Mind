from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações do Service Registry"""

    # Informações do serviço
    SERVICE_NAME: str = Field(default="service-registry", description="Nome do serviço")
    SERVICE_VERSION: str = Field(default="1.0.0", description="Versão do serviço")
    ENVIRONMENT: str = Field(default="development", description="Ambiente de execução")
    LOG_LEVEL: str = Field(default="INFO", description="Nível de log")

    # Configurações de rede
    GRPC_PORT: int = Field(default=50051, description="Porta do servidor gRPC")
    METRICS_PORT: int = Field(default=9090, description="Porta de métricas Prometheus")

    # Configurações do etcd
    ETCD_ENDPOINTS: List[str] = Field(
        default=["http://etcd:2379"],
        description="Endpoints do cluster etcd"
    )
    ETCD_PREFIX: str = Field(
        default="/neural-hive/agents",
        description="Prefixo das chaves no etcd"
    )
    ETCD_TIMEOUT_SECONDS: int = Field(
        default=5,
        description="Timeout para operações no etcd"
    )

    # Configurações de health checks
    HEALTH_CHECK_INTERVAL_SECONDS: int = Field(
        default=60,
        description="Intervalo entre verificações de saúde"
    )
    HEARTBEAT_TIMEOUT_SECONDS: int = Field(
        default=120,
        description="Timeout para considerar agente inativo"
    )

    # Configurações do Redis (para feromônios)
    REDIS_CLUSTER_NODES: List[str] = Field(
        default=["redis:6379"],
        description="Nós do cluster Redis"
    )
    REDIS_PASSWORD: str = Field(default="", description="Senha do Redis")

    # Configurações de observabilidade
    OTEL_EXPORTER_ENDPOINT: str = Field(
        default="http://otel-collector:4317",
        description="Endpoint do coletor OpenTelemetry"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Retorna configurações cacheadas"""
    return Settings()
