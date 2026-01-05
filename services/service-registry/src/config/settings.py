from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Configurações do Registry Backend (Redis)
    # Nota: Mantemos nomes ETCD_* para compatibilidade com configs existentes
    # mas agora usa Redis como backend
    ETCD_ENDPOINTS: List[str] = Field(
        default=["redis:6379"],
        description="Endpoints do Redis para registry (formato host:port)"
    )
    ETCD_PREFIX: str = Field(
        default="neural-hive:agents",
        description="Prefixo das chaves no Redis"
    )
    ETCD_TIMEOUT_SECONDS: int = Field(
        default=5,
        description="Timeout para operações no Redis"
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
    REDIS_PASSWORD: Optional[str] = Field(
        default=None,
        description="Senha do Redis. Obrigatorio em producao (validacao automatica)."
    )

    @field_validator('REDIS_PASSWORD')
    @classmethod
    def validate_redis_password_in_production(cls, v: Optional[str], info) -> Optional[str]:
        """
        Validar que REDIS_PASSWORD nao esta vazio em producao.

        Em producao, Redis deve sempre ter autenticacao habilitada para prevenir
        acesso nao autorizado ao registry de agentes.
        """
        environment = info.data.get('ENVIRONMENT', 'development')

        if environment in ['production', 'prod']:
            if not v or v == '':
                raise ValueError(
                    'REDIS_PASSWORD nao pode ser vazio em ambiente production. '
                    'Configure REDIS_PASSWORD com uma senha segura ou use External Secrets Operator. '
                    'Consulte docs/SECRETS_MANAGEMENT_GUIDE.md para melhores praticas.'
                )

        return v

    # Configurações de observabilidade
    OTEL_EXPORTER_ENDPOINT: str = Field(
        default="http://otel-collector:4317",
        description="Endpoint do coletor OpenTelemetry"
    )

    # Vault Integration
    VAULT_ENABLED: bool = Field(default=False, description="Habilitar integração com Vault")
    VAULT_ADDRESS: str = Field(
        default="http://vault.vault.svc.cluster.local:8200",
        description="Endereço do servidor Vault"
    )
    VAULT_KUBERNETES_ROLE: str = Field(
        default="service-registry",
        description="Role Kubernetes para autenticação Vault"
    )
    VAULT_TOKEN_PATH: str = Field(
        default="/vault/secrets/token",
        description="Caminho para arquivo de token Vault"
    )
    VAULT_MOUNT_KV: str = Field(default="secret", description="Mount point do KV secrets")

    # SPIFFE Integration
    SPIFFE_ENABLED: bool = Field(default=False, description="Habilitar integração com SPIFFE")
    SPIFFE_SOCKET_PATH: str = Field(
        default="unix:///run/spire/sockets/agent.sock",
        description="Caminho do socket da SPIRE Workload API"
    )
    SPIFFE_TRUST_DOMAIN: str = Field(
        default="neural-hive.local",
        description="Trust domain SPIFFE"
    )
    SPIFFE_JWT_AUDIENCE: str = Field(
        default="service-registry.neural-hive.local",
        description="Audience para validação de JWT-SVID"
    )
    SPIFFE_VERIFY_PEER: bool = Field(
        default=True,
        description="Verificar peer SPIFFE IDs em chamadas gRPC"
    )
    SPIFFE_ENABLE_X509: bool = Field(
        default=True,
        description="Habilitar X.509-SVID para mTLS no servidor"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra='ignore'
    )


@lru_cache()
def get_settings() -> Settings:
    """Retorna configurações cacheadas"""
    return Settings()
