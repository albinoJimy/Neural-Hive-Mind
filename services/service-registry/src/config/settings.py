from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator, model_validator
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
        default="https://opentelemetry-collector.observability.svc.cluster.local:4317",
        description="Endpoint do coletor OpenTelemetry"
    )
    OTEL_TLS_VERIFY: bool = Field(default=True, description="Verificar certificado TLS do OTEL Collector")
    OTEL_CA_BUNDLE: Optional[str] = Field(default=None, description="Caminho para CA bundle do OTEL Collector")

    # Vault Integration
    VAULT_ENABLED: bool = Field(default=False, description="Habilitar integração com Vault")
    VAULT_ADDRESS: str = Field(
        default="https://vault.vault.svc.cluster.local:8200",
        description="Endereço do servidor Vault"
    )
    VAULT_TLS_VERIFY: bool = Field(default=True, description="Verificar certificado TLS do Vault")
    VAULT_CA_BUNDLE: Optional[str] = Field(default=None, description="Caminho para CA bundle do Vault")
    VAULT_NAMESPACE: str = Field(default="", description="Namespace Vault (vazio para root)")
    VAULT_AUTH_METHOD: str = Field(default="kubernetes", description="Método de autenticação Vault")
    VAULT_KUBERNETES_ROLE: str = Field(
        default="service-registry",
        description="Role Kubernetes para autenticação Vault"
    )
    VAULT_TOKEN_PATH: str = Field(
        default="/vault/secrets/token",
        description="Caminho para arquivo de token Vault"
    )
    VAULT_MOUNT_KV: str = Field(default="secret", description="Mount point do KV secrets")
    VAULT_TIMEOUT_SECONDS: int = Field(default=5, description="Timeout para requisições Vault")
    VAULT_MAX_RETRIES: int = Field(default=3, description="Número de tentativas de retry")
    VAULT_FAIL_OPEN: bool = Field(
        default=False,
        description=(
            "Fail-open em erros do Vault (fallback para env vars). "
            "ATENCAO: Deve ser False em producao para zero-trust security."
        )
    )

    @field_validator('VAULT_FAIL_OPEN')
    @classmethod
    def validate_vault_fail_open_requires_dev_environment(cls, v: bool, info) -> bool:
        """
        Validar que VAULT_FAIL_OPEN só pode ser True em ambientes de desenvolvimento.
        """
        if v is not True:
            return v

        environment = info.data.get('ENVIRONMENT', '')

        # Ambientes permitidos para fail_open=True
        allowed_environments = ['development', 'dev', 'local', 'test']

        if environment.lower() not in allowed_environments:
            raise ValueError(
                f'VAULT_FAIL_OPEN=True não é permitido em ambiente "{environment}". '
                f'Apenas ambientes {allowed_environments} permitem fail_open. '
                'Configure VAULT_FAIL_OPEN=false ou ENVIRONMENT=development.'
            )

        return v

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

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'Settings':
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: OTEL Collector, Vault.
        """
        is_prod_staging = self.ENVIRONMENT.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []
        if self.OTEL_EXPORTER_ENDPOINT.startswith('http://'):
            http_endpoints.append(('OTEL_EXPORTER_ENDPOINT', self.OTEL_EXPORTER_ENDPOINT))
        if self.VAULT_ENABLED and self.VAULT_ADDRESS.startswith('http://'):
            http_endpoints.append(('VAULT_ADDRESS', self.VAULT_ADDRESS))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.ENVIRONMENT}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito."
            )

        return self


@lru_cache()
def get_settings() -> Settings:
    """Retorna configurações cacheadas"""
    return Settings()
