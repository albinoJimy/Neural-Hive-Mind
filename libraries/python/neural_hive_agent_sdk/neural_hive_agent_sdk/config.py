from pydantic import Field
from pydantic_settings import BaseSettings


class AgentConfig(BaseSettings):
    """Configurações para integração do agente com Service Registry"""

    # Endpoint do Service Registry
    REGISTRY_GRPC_ENDPOINT: str = Field(
        default="service-registry:50051",
        description="Endpoint gRPC do Service Registry (host:port)"
    )

    # Informações do agente
    AGENT_NAMESPACE: str = Field(
        default="default",
        description="Namespace Kubernetes do agente"
    )

    AGENT_CLUSTER: str = Field(
        default="local",
        description="Nome do cluster"
    )

    AGENT_VERSION: str = Field(
        default="1.0.0",
        description="Versão do agente"
    )

    # Configurações de heartbeat
    HEARTBEAT_INTERVAL_SECONDS: int = Field(
        default=30,
        description="Intervalo entre heartbeats em segundos"
    )

    # Configurações de gRPC
    GRPC_TIMEOUT_SECONDS: int = Field(
        default=5,
        description="Timeout para operações gRPC"
    )

    GRPC_MAX_RETRIES: int = Field(
        default=3,
        description="Número máximo de retries para operações gRPC"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "AGENT_"
        case_sensitive = True
