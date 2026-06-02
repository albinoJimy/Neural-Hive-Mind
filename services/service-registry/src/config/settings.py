import json
from functools import lru_cache
from typing import Optional, Union

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações do Service Registry"""

    # Informações do serviço
    SERVICE_NAME: str = Field(default="service-registry", description="Nome do serviço")
    SERVICE_VERSION: str = Field(default="1.3.0", description="Versão do serviço")
    ENVIRONMENT: str = Field(default="development", description="Ambiente de execução")
    LOG_LEVEL: str = Field(default="INFO", description="Nível de log")

    # Configurações de rede
    GRPC_PORT: int = Field(default=50051, description="Porta do servidor gRPC")
    METRICS_PORT: int = Field(default=9090, description="Porta de métricas Prometheus")

    # Configurações do Registry Backend (Redis)
    # Nota: Fase de migração etcd→Redis - suporta ambos os nomes por compatibilidade
    # Prioridade: REGISTRY_REDIS_* > ETCD_* (deprecated)

    # Nomes legados (deprecated, removidos em v1.6.0)
    # Mantidos aqui para Pydantic ler do environment, mas uso interno via propriedades
    ETCD_ENDPOINTS: Optional[list[str]] = Field(
        default=None,
        description="[DEPRECATED - use REGISTRY_REDIS_ENDPOINTS] Endpoints do Redis",
    )
    ETCD_PREFIX: Optional[str] = Field(
        default=None,
        description="[DEPRECATED - use REGISTRY_REDIS_PREFIX] Prefixo das chaves no Redis",
    )
    ETCD_TIMEOUT_SECONDS: Optional[int] = Field(
        default=None,
        description="[DEPRECATED - use REGISTRY_REDIS_TIMEOUT_SECONDS] Timeout Redis",
    )

    # Novos nomes (padrão para v1.4.0+)
    # Nota: Podem ser omitidos em favor de ETCD_* durante Fase 1 (v1.3.0)
    REGISTRY_REDIS_ENDPOINTS: Optional[list[str]] = Field(
        default=None,
        description="Endpoints do Redis para registry (formato host:port)",
    )
    REGISTRY_REDIS_PREFIX: Optional[str] = Field(
        default=None,
        description="Prefixo das chaves no Redis",
    )
    REGISTRY_REDIS_TIMEOUT_SECONDS: Optional[int] = Field(
        default=None,
        description="Timeout para operações no Redis",
    )
    REGISTRY_REDIS_CLUSTER_MODE: bool = Field(
        default=False,
        description="Usar Redis Cluster mode (requer redis.asyncio.cluster.RedisCluster)",
    )

    # Configurações de health checks
    HEALTH_CHECK_INTERVAL_SECONDS: int = Field(
        default=60, description="Intervalo entre verificações de saúde"
    )
    HEARTBEAT_TIMEOUT_SECONDS: int = Field(
        default=120, description="Timeout para considerar agente inativo"
    )

    # Configurações do Redis (para feromônios)
    REDIS_CLUSTER_NODES: list[str] = Field(
        default=["redis:6379"], description="Nós do cluster Redis"
    )
    REDIS_PASSWORD: Optional[str] = Field(
        default=None, description="Senha do Redis. Obrigatorio em producao (validacao automatica)."
    )

    @field_validator(
        "REGISTRY_REDIS_ENDPOINTS", "ETCD_ENDPOINTS", "REDIS_CLUSTER_NODES", mode="before"
    )
    @classmethod
    def parse_list_from_json_string(cls, v: Union[str, list[str], None]) -> Union[list[str], None]:
        """
        Parseia listas que vem como JSON string de variaveis de ambiente.

        Helm passa listas como JSON: '["redis:6379"]'
        Pydantic precisa converter para lista Python: ["redis:6379"]
        """
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            # Se parece com JSON array, faz parse
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            # Se nao e JSON, assume string unica
            return [v] if v else []
        return v if v else []

    @field_validator("REDIS_PASSWORD")
    @classmethod
    def validate_redis_password_in_production(cls, v: Optional[str], info) -> Optional[str]:
        """
        Validar que REDIS_PASSWORD nao esta vazio em producao.

        Em producao, Redis deve sempre ter autenticacao habilitada para prevenir
        acesso nao autorizado ao registry de agentes.
        """
        environment = info.data.get("ENVIRONMENT", "development")

        if environment in ["production", "prod"]:
            if not v or v == "":
                raise ValueError(
                    "REDIS_PASSWORD nao pode ser vazio em ambiente production. "
                    "Configure REDIS_PASSWORD com uma senha segura ou use External Secrets Operator. "
                    "Consulte docs/SECRETS_MANAGEMENT_GUIDE.md para melhores praticas."
                )

        return v

    # Configurações de observabilidade
    OTEL_EXPORTER_ENDPOINT: str = Field(
        default="https://opentelemetry-collector.observability.svc.cluster.local:4317",
        description="Endpoint do coletor OpenTelemetry",
    )
    OTEL_TLS_VERIFY: bool = Field(
        default=True, description="Verificar certificado TLS do OTEL Collector"
    )
    OTEL_CA_BUNDLE: Optional[str] = Field(
        default=None, description="Caminho para CA bundle do OTEL Collector"
    )

    # Vault Integration
    VAULT_ENABLED: bool = Field(default=False, description="Habilitar integração com Vault")
    VAULT_ADDRESS: str = Field(
        default="https://vault.vault.svc.cluster.local:8200",
        description="Endereço do servidor Vault",
    )
    VAULT_TLS_VERIFY: bool = Field(default=True, description="Verificar certificado TLS do Vault")
    VAULT_CA_BUNDLE: Optional[str] = Field(
        default=None, description="Caminho para CA bundle do Vault"
    )
    VAULT_NAMESPACE: str = Field(default="", description="Namespace Vault (vazio para root)")
    VAULT_AUTH_METHOD: str = Field(default="kubernetes", description="Método de autenticação Vault")
    VAULT_KUBERNETES_ROLE: str = Field(
        default="service-registry", description="Role Kubernetes para autenticação Vault"
    )
    VAULT_TOKEN_PATH: str = Field(
        default="/vault/secrets/token", description="Caminho para arquivo de token Vault"
    )
    VAULT_MOUNT_KV: str = Field(default="secret", description="Mount point do KV secrets")
    VAULT_TIMEOUT_SECONDS: int = Field(default=5, description="Timeout para requisições Vault")
    VAULT_MAX_RETRIES: int = Field(default=3, description="Número de tentativas de retry")
    VAULT_FAIL_OPEN: bool = Field(
        default=False,
        description=(
            "Fail-open em erros do Vault (fallback para env vars). "
            "ATENCAO: Deve ser False em producao para zero-trust security."
        ),
    )

    @field_validator("VAULT_FAIL_OPEN")
    @classmethod
    def validate_vault_fail_open_requires_dev_environment(cls, v: bool, info) -> bool:
        """
        Validar que VAULT_FAIL_OPEN só pode ser True em ambientes de desenvolvimento.
        """
        if v is not True:
            return v

        environment = info.data.get("ENVIRONMENT", "")

        # Ambientes permitidos para fail_open=True
        allowed_environments = ["development", "dev", "local", "test"]

        if environment.lower() not in allowed_environments:
            raise ValueError(
                f'VAULT_FAIL_OPEN=True não é permitido em ambiente "{environment}". '
                f"Apenas ambientes {allowed_environments} permitem fail_open. "
                "Configure VAULT_FAIL_OPEN=false ou ENVIRONMENT=development."
            )

        return v

    # SPIFFE Integration
    SPIFFE_ENABLED: bool = Field(default=False, description="Habilitar integração com SPIFFE")
    SPIFFE_SOCKET_PATH: str = Field(
        default="unix:///run/spire/sockets/agent.sock",
        description="Caminho do socket da SPIRE Workload API",
    )
    SPIFFE_TRUST_DOMAIN: str = Field(default="neural-hive.local", description="Trust domain SPIFFE")
    SPIFFE_JWT_AUDIENCE: str = Field(
        default="service-registry.neural-hive.local",
        description="Audience para validação de JWT-SVID",
    )
    SPIFFE_VERIFY_PEER: bool = Field(
        default=True, description="Verificar peer SPIFFE IDs em chamadas gRPC"
    )
    SPIFFE_ENABLE_X509: bool = Field(
        default=True, description="Habilitar X.509-SVID para mTLS no servidor"
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    @model_validator(mode="after")
    def validate_https_in_production(self) -> "Settings":
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: OTEL Collector, Vault.

        Excecao: Endpoints internos do cluster Kubernetes (.svc.cluster.local)
        sao permitidos usar HTTP em producao, pois o trafego ja esta protegido
        pela rede interna do cluster e/ou service mesh (Istio mTLS).
        """
        is_prod_staging = self.ENVIRONMENT.lower() in ("production", "staging", "prod")
        if not is_prod_staging:
            return self

        def is_internal_cluster_endpoint(url: str) -> bool:
            """Verifica se URL e um endpoint interno do cluster Kubernetes."""
            internal_suffixes = (
                ".svc.cluster.local",
                ".svc.cluster",
                ".svc",
            )
            from urllib.parse import urlparse

            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            return any(hostname.endswith(suffix) for suffix in internal_suffixes)

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []
        if self.OTEL_EXPORTER_ENDPOINT.startswith("http://"):
            if not is_internal_cluster_endpoint(self.OTEL_EXPORTER_ENDPOINT):
                http_endpoints.append(("OTEL_EXPORTER_ENDPOINT", self.OTEL_EXPORTER_ENDPOINT))
        if self.VAULT_ENABLED and self.VAULT_ADDRESS.startswith("http://"):
            if not is_internal_cluster_endpoint(self.VAULT_ADDRESS):
                http_endpoints.append(("VAULT_ADDRESS", self.VAULT_ADDRESS))

        if http_endpoints:
            endpoint_list = ", ".join(f"{name}={url}" for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.ENVIRONMENT}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito. "
                "Endpoints internos do cluster (.svc.cluster.local) sao permitidos usar HTTP."
            )

        return self

    @model_validator(mode="after")
    def migrate_etcd_to_redis_config(self) -> "Settings":
        """
        Migra configs ETCD_* (deprecated) para REGISTRY_REDIS_*.

        Estratégia de 3 fases:
        - Fase 1 (v1.3.0): Aceita ambos, usa REGISTRY_REDIS_* se disponível
        - Fase 2 (v1.4.0): Atualiza Helm charts para usar novos nomes
        - Fase 3 (v1.6.0): Remove suporte a ETCD_*

        Emite aviso se ETCD_* está sendo usado como fallback.
        """
        import warnings

        # Migrar ENDPOINTS
        if not hasattr(self, "_resolved_redis_endpoints"):
            if self.REGISTRY_REDIS_ENDPOINTS is not None:
                # Novo nome definido explicitamente (ou via env)
                self._resolved_redis_endpoints = self.REGISTRY_REDIS_ENDPOINTS
            elif self.ETCD_ENDPOINTS is not None:
                # Apenas nome legado definido
                warnings.warn(
                    "ETCD_ENDPOINTS is deprecated and will be removed in v1.6.0. "
                    "Use REGISTRY_REDIS_ENDPOINTS instead. "
                    "See docs/service-registry/MIGRATION_ETCD_TO_REDIS.md",
                    DeprecationWarning,
                    stacklevel=2,
                )
                self._resolved_redis_endpoints = self.ETCD_ENDPOINTS
            else:
                # Nenhum definido, usar default
                self._resolved_redis_endpoints = ["redis:6379"]

        # Migrar PREFIX
        if not hasattr(self, "_resolved_redis_prefix"):
            if self.REGISTRY_REDIS_PREFIX is not None:
                self._resolved_redis_prefix = self.REGISTRY_REDIS_PREFIX
            elif self.ETCD_PREFIX is not None:
                warnings.warn(
                    "ETCD_PREFIX is deprecated. Use REGISTRY_REDIS_PREFIX instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                self._resolved_redis_prefix = self.ETCD_PREFIX
            else:
                self._resolved_redis_prefix = "neural-hive:agents"

        # Migrar TIMEOUT
        if not hasattr(self, "_resolved_redis_timeout"):
            if self.REGISTRY_REDIS_TIMEOUT_SECONDS is not None:
                self._resolved_redis_timeout = self.REGISTRY_REDIS_TIMEOUT_SECONDS
            elif self.ETCD_TIMEOUT_SECONDS is not None:
                warnings.warn(
                    "ETCD_TIMEOUT_SECONDS is deprecated. Use REGISTRY_REDIS_TIMEOUT_SECONDS instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                self._resolved_redis_timeout = self.ETCD_TIMEOUT_SECONDS
            else:
                self._resolved_redis_timeout = 5

        return self

    # Propriedades para acessar valores migrados (abstração para código)
    @property
    def registry_redis_endpoints(self) -> list[str]:
        """Endpoints do Redis para registry (mesclado de ETCD_ENDPOINTS para compatibilidade)"""
        if not hasattr(self, "_resolved_redis_endpoints"):
            # Força migração se propriedade acessada antes do validator
            self.migrate_etcd_to_redis_config()
        return getattr(self, "_resolved_redis_endpoints", ["redis:6379"])

    @property
    def registry_redis_prefix(self) -> str:
        """Prefixo das chaves no Redis (mesclado de ETCD_PREFIX para compatibilidade)"""
        if not hasattr(self, "_resolved_redis_prefix"):
            self.migrate_etcd_to_redis_config()
        return getattr(self, "_resolved_redis_prefix", "neural-hive:agents")

    @property
    def registry_redis_timeout(self) -> int:
        """Timeout para operações no Redis (mesclado de ETCD_TIMEOUT_SECONDS para compatibilidade)"""
        if not hasattr(self, "_resolved_redis_timeout"):
            self.migrate_etcd_to_redis_config()
        return getattr(self, "_resolved_redis_timeout", 5)

    @property
    def registry_redis_prefix(self) -> str:
        """Prefixo das chaves no Redis (mesclado de ETCD_PREFIX para compatibilidade)"""
        return getattr(self, "_resolved_redis_prefix", "neural-hive:agents")

    @property
    def registry_redis_timeout(self) -> int:
        """Timeout para operações no Redis (mesclado de ETCD_TIMEOUT_SECONDS para compatibilidade)"""
        return getattr(self, "_resolved_redis_timeout", 5)

    @property
    def registry_redis_cluster_mode(self) -> bool:
        """Indica se o Redis registry deve usar modo Cluster"""
        return self.REGISTRY_REDIS_CLUSTER_MODE


@lru_cache
def get_settings() -> Settings:
    """Retorna configurações cacheadas"""
    return Settings()
