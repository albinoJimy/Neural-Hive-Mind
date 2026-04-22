import threading
from typing import Optional

from pydantic import Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings

from neural_hive_security.cors import CORSConfig


class Settings(BaseSettings):
    """Configurações da aplicação Gateway de Intenções"""

    # Aplicação
    environment: str = Field(default="dev")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # CORS - Gateway é API pública
    is_public_api: bool = Field(default=True, description="API pública requer CORS")

    # Override de CORS (opcional, para casos especiais)
    cors_origins_override: list[str] | None = Field(
        default=None,
        description="Override manual de CORS origins (None = usar configuração automática)",
    )

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092"
    )
    schema_registry_url: str = Field(
        default="https://schema-registry.neural-hive-kafka.svc.cluster.local:8081"
    )

    # Schema Registry TLS
    schema_registry_tls_enabled: bool = Field(
        default=True, description="Habilitar TLS para conexão com Schema Registry"
    )
    schema_registry_tls_verify: bool = Field(
        default=True, description="Verificar certificado TLS do Schema Registry"
    )
    schema_registry_ssl_ca_location: str | None = Field(
        default="/etc/ssl/certs/schema-registry-ca.crt",
        description="Caminho para CA do Schema Registry",
    )
    schema_registry_ca_bundle: str | None = Field(
        default=None, description="Caminho para CA bundle do Schema Registry (legado)"
    )

    # Kafka Security
    kafka_security_protocol: str = Field(default="PLAINTEXT")  # PLAINTEXT, SASL_SSL, SSL
    kafka_sasl_mechanism: str = Field(
        default="SCRAM-SHA-512"
    )  # PLAIN, SCRAM-SHA-256, SCRAM-SHA-512
    kafka_sasl_username: str | None = Field(default=None)
    kafka_sasl_password: str | None = Field(default=None)
    kafka_ssl_ca_location: str | None = Field(default=None)
    kafka_ssl_certificate_location: str | None = Field(default=None)
    kafka_ssl_key_location: str | None = Field(default=None)

    # Kafka Performance
    kafka_batch_size: int = Field(default=16384)  # bytes
    kafka_linger_ms: int = Field(default=10)  # milliseconds
    kafka_compression_type: str = Field(default="snappy")  # none, gzip, snappy, lz4, zstd
    kafka_acks: str = Field(
        default="all"
    )  # 0, 1, all (use 'all' for exactly-once, '1' for lower latency)
    kafka_enable_idempotence: bool = Field(default=True)  # Habilitar idempotência para exactly-once
    kafka_max_in_flight: int = Field(default=5)  # Máximo de requisições em voo por conexão

    # Fast Producer Control (exactly-once vs latency)
    kafka_enable_fast_producer: bool = Field(
        default=False,
        description="Habilitar producer não-transacional para menor latência (desabilitado por padrão para exactly-once). "
        "Só habilitar se latência é mais prioritária que exactly-once semantics.",
    )
    kafka_fast_producer_topics: str = Field(
        default="",
        description="Allowlist de tópicos (separados por vírgula) permitidos para fast producer. "
        "Vazio = nenhum tópico permitido. Usar apenas para tópicos não-críticos.",
    )

    # ASR Pipeline
    # Modelos disponíveis: tiny (39MB), base (142MB), small (466MB), medium (1.5GB), large (2.9GB)
    asr_model_name: str = Field(default="tiny")
    asr_device: str = Field(default="cpu")
    asr_timeout_seconds: int = Field(default=60)
    asr_max_concurrent_jobs: int = Field(default=5)
    asr_lazy_loading: bool = Field(
        default=True, description="Habilitar lazy loading do modelo Whisper"
    )
    asr_model_cache_dir: str = Field(
        default="/app/models/whisper",
        description="Diretório de cache de modelos montado via volume persistente",
    )

    # NLU Pipeline
    nlu_language_model: str = Field(default="pt_core_news_sm")
    nlu_model_cache_dir: str = Field(
        default="/app/models/spacy",
        description="Diretório de cache de modelos spaCy montado via volume persistente",
    )
    nlu_confidence_threshold: float = Field(default=0.5)
    nlu_confidence_threshold_strict: float = Field(default=0.75)
    nlu_adaptive_threshold_enabled: bool = Field(default=True)
    nlu_rules_config_path: str = Field(default="/app/config/nlu_rules.yaml")
    nlu_cache_enabled: bool = Field(default=True)
    nlu_cache_ttl_seconds: int = Field(default=3600)

    # NLU Routing Thresholds
    nlu_routing_threshold_high: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Threshold mínimo para processamento normal (confidence >= threshold)",
    )
    nlu_routing_threshold_low: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Threshold mínimo para processamento com baixa confiança (threshold_low <= confidence < threshold_high)",
    )
    nlu_routing_use_adaptive_for_decisions: bool = Field(
        default=False,
        description="Se True, usa adaptive threshold calculado pelo NLU para decisões de roteamento; se False, usa thresholds fixos",
    )

    # FEAT-A-005: Threshold Service - Externalização de configurações NLU
    nlu_threshold_auto_reload: bool = Field(
        default=False,
        description="Habilita recarga automática de configuração de thresholds",
    )
    nlu_threshold_reload_interval: int = Field(
        default=300,
        description="Intervalo de recarga de thresholds em segundos (padrão: 5 minutos)",
    )
    nlu_threshold_cache_ttl: int = Field(
        default=300,
        description="TTL do cache de thresholds em segundos (0 = sem expiração, padrão: 5 minutos)",
    )
    nlu_threshold_config_path: str | None = Field(
        default=None,
        description="Caminho para arquivo YAML de configuração de thresholds (opcional)",
    )

    # Redis Cache
    redis_cluster_nodes: str = Field(
        default="neural-hive-cache.redis-cluster.svc.cluster.local:6379"
    )
    redis_mode: str = Field(
        default="cluster",
        description="Modo de conexão Redis: 'cluster' para Redis Cluster (segue redirecionamentos MOVED/ASK), 'standalone' para Redis single-node",
    )
    redis_password: str | None = Field(default=None)
    redis_ca_cert_path: str | None = Field(default=None)
    redis_default_ttl: int = Field(default=600)  # 10 minutos
    redis_max_connections: int = Field(default=100)
    redis_pool_size: int = Field(default=10)
    redis_timeout: int = Field(default=5000)  # ms

    # Redis Security
    redis_ssl_enabled: bool = Field(default=False)
    redis_ssl_cert_reqs: str = Field(default="required")  # none, optional, required
    redis_ssl_ca_certs: str | None = Field(default=None)
    redis_ssl_certfile: str | None = Field(default=None)
    redis_ssl_keyfile: str | None = Field(default=None)

    # Redis Performance
    redis_connection_pool_max_connections: int = Field(default=50)
    redis_retry_on_timeout: bool = Field(default=True)

    # OAuth2/Keycloak
    keycloak_url: str = Field(default="https://keycloak.neural-hive.local")
    keycloak_realm: str = Field(default="neural-hive")
    keycloak_client_id: str = Field(default="gateway-intencoes")
    keycloak_client_secret: str | None = Field(default=None)
    jwks_uri: str = Field(
        default="https://keycloak.neural-hive.local/auth/realms/neural-hive/protocol/openid-connect/certs"
    )
    token_validation_enabled: bool = Field(default=True)

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_requests_per_minute: int = Field(default=1000)
    rate_limit_burst_size: int = Field(default=100)
    rate_limit_fail_open: bool = Field(
        default=True,
        description="Permitir requisicoes se Redis falhar (fail-open) ou bloquear (fail-closed)",
    )
    rate_limit_tenant_overrides: str = Field(
        default="{}",
        description="Rate limits especificos por tenant_id em formato JSON",
    )
    rate_limit_user_overrides: str = Field(
        default="{}", description="Rate limits especificos por user_id em formato JSON"
    )

    # Security Features
    mtls_validation_enabled: bool = Field(default=False)
    api_key_auth_enabled: bool = Field(default=False)
    request_signature_validation_enabled: bool = Field(default=False)
    allow_insecure_http_endpoints: bool = Field(
        default=False,
        description="Permitir endpoints HTTP em staging (para comunicação interna do cluster)",
    )

    # PII Masking
    enable_pii_masking: bool = Field(
        default=True,
        description="Habilitar mascaramento de informações sensíveis (PII) no texto de entrada",
    )
    pii_masking_strategy: str = Field(
        default="partial",
        description="Estratégia de mascaramento: partial (preserva formato), redact (remove completamente)",
    )
    pii_masking_preserve_format: bool = Field(
        default=True,
        description="Preservar formato original ao mascarar (ex: ***-***-*** para CPF)",
    )
    pii_masking_spacy_model: str = Field(
        default="pt_core_news_sm",
        description="Modelo spaCy para detecção de entidades (pt_core_news_sm ou pt_core_news_lg)",
    )

    # Segurança (OBRIGATÓRIO em production)
    # Nota: jwt_secret_key agora é opcional pois pode vir do Vault
    # Em produção, use Vault ou defina JWT_SECRET environment variable
    jwt_secret_key: str | None = Field(
        default=None,
        description="JWT secret key (Opcional - usa Vault se disponível, senão este valor)",
    )
    jwt_algorithm: str = Field(default="HS256")

    # Vault integration
    vault_enabled: bool = Field(
        default=False, description="Habilitar integração com HashiCorp Vault para secrets"
    )
    vault_addr: str | None = Field(default=None, description="Endereço do servidor Vault")
    vault_token: str | None = Field(
        default=None,
        description="Token para autenticação no Vault (opcional, usa Kubernetes auth se não fornecido)",
    )
    vault_role: str = Field(
        default="neural-hive-gateway", description="Role para autenticação Kubernetes no Vault"
    )
    vault_mount_point: str = Field(default="neural-hive", description="Mount point KV v2 no Vault")

    # Private attributes for Vault client and cached secrets
    _vault_client: Optional["VaultClient"] = PrivateAttr(default=None)
    _jwt_secret_cached: str | None = PrivateAttr(default=None)
    _secret_key_cached: str | None = PrivateAttr(default=None)
    _vault_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    # CORS e hosts (usa biblioteca neural_hive_security)
    allowed_hosts: list[str] = Field(
        default=[], description="Allowed hosts for TrustedHostMiddleware (configurado via property)"
    )

    @property
    def allowed_hosts_property(self) -> list[str]:
        """
        Retorna hosts permitidos por ambiente.

        Prioriza configuração explícita, senão usa defaults seguros por ambiente.
        Nunca retorna wildcard em produção.
        """
        # Se configurado explicitamente, retorna configuração
        if self.allowed_hosts:
            return self.allowed_hosts

        # Defaults por ambiente (sem wildcard em produção)
        if self.environment == "production":
            return ["api.neural-hive.com", "gateway.neural-hive.com", "neural-hive.com"]
        if self.environment == "staging":
            return ["api.staging.neural-hive.com", "gateway.staging.neural-hive.com"]
        # development
        return ["localhost", "127.0.0.1", "neural-hive.local", "*.neural-hive.local"]

    @property
    def allowed_origins(self) -> list[str]:
        """
        CORS origins dinâmicas por ambiente.

        Usa neural_hive_security.CORSConfig para configurar origens
        seguras por ambiente, com opção de override manual.
        """
        # Se override foi fornecido, usa ele
        if self.cors_origins_override is not None:
            return self.cors_origins_override

        # Caso contrário, usa configuração automática
        return CORSConfig.get_origins_for_environment(
            self.environment, is_public_api=self.is_public_api
        )

    # Observabilidade - OpenTelemetry Collector OTLP endpoint
    otel_enabled: bool = Field(
        default=True,
        description="Habilitar OpenTelemetry para tracing distribuído (True em prod/staging, False em dev via Helm)",
    )
    otel_endpoint: str = Field(
        default="https://opentelemetry-collector.observability.svc.cluster.local:4317"
    )
    otel_tls_verify: bool = Field(
        default=True, description="Verificar certificado TLS do OTEL Collector"
    )
    otel_ca_bundle: str | None = Field(
        default=None, description="Caminho para CA bundle do OTEL Collector"
    )
    prometheus_port: int = Field(default=8080)
    jaeger_sampling_rate: float = Field(default=0.1)

    # Limites
    max_audio_size_mb: int = Field(default=10)
    max_text_length: int = Field(default=10000)

    # Feature Flags
    batch_processing_enabled: bool = Field(default=True)
    circuit_breaker_enabled: bool = Field(default=True)
    distributed_cache_enabled: bool = Field(default=True)

    @field_validator("kafka_security_protocol")
    @classmethod
    def validate_kafka_security_protocol(cls, v: str) -> str:
        allowed = ["PLAINTEXT", "SASL_SSL", "SSL", "SASL_PLAINTEXT"]
        if v not in allowed:
            raise ValueError(f"kafka_security_protocol must be one of {allowed}")
        return v

    @field_validator("kafka_sasl_mechanism")
    @classmethod
    def validate_kafka_sasl_mechanism(cls, v: str) -> str:
        allowed = ["PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512", "GSSAPI"]
        if v not in allowed:
            raise ValueError(f"kafka_sasl_mechanism must be one of {allowed}")
        return v

    @field_validator("redis_ssl_cert_reqs")
    @classmethod
    def validate_redis_ssl_cert_reqs(cls, v: str) -> str:
        allowed = ["none", "optional", "required"]
        if v not in allowed:
            raise ValueError(f"redis_ssl_cert_reqs must be one of {allowed}")
        return v

    @model_validator(mode="before")
    @classmethod
    def validate_environment_security(cls, data: dict) -> dict:
        environment = data.get("environment")
        if environment == "prod":
            # Em produção, alguns recursos de segurança são obrigatórios
            if not data.get("token_validation_enabled", True):
                raise ValueError("token_validation_enabled must be True in production")
        return data

    @model_validator(mode="before")
    @classmethod
    def validate_allowed_hosts(cls, data: dict) -> dict:
        """Bloqueia wildcard ou lista vazia de allowed_hosts em produção."""
        allowed_hosts = data.get("allowed_hosts", [])
        env = data.get("environment", "development")
        env_lower = env.lower() if env else "development"

        if env_lower in ("production", "prod"):
            if "*" in allowed_hosts or not allowed_hosts:
                raise ValueError(
                    "allowed_hosts nao pode ser wildcard ou vazio em producao. "
                    "Configure hosts explicitos ou use a propriedade allowed_hosts_property."
                )
        return data

    @field_validator("pii_masking_strategy")
    @classmethod
    def validate_pii_masking_strategy(cls, v: str) -> str:
        allowed = ["partial", "redact", "full"]
        if v not in allowed:
            raise ValueError(f"pii_masking_strategy must be one of {allowed}")
        return v

    @model_validator(mode="before")
    @classmethod
    def validate_routing_thresholds(cls, data: dict) -> dict:
        low_threshold = data.get("nlu_routing_threshold_low")
        high_threshold = data.get("nlu_routing_threshold_high", 0.5)
        if low_threshold is not None and low_threshold >= high_threshold:
            raise ValueError(
                f"nlu_routing_threshold_low ({low_threshold}) must be < nlu_routing_threshold_high ({high_threshold})"
            )
        return data

    @field_validator("cors_origins_override", mode="before")
    @classmethod
    def parse_cors_origins_override(cls, v):
        """Parse CORS_ORIGINS from comma-separated string to list."""
        if v is None:
            return None
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @model_validator(mode="after")
    def validate_cors_in_production(self) -> "Settings":
        """
        Valida que não usa wildcard CORS em produção.
        """
        # Se override foi fornecido, valida ele
        origins = self.allowed_origins

        is_prod = self.environment.lower() in ("production", "prod", "staging", "stage")

        if not is_prod:
            return self

        # Valida que não tem wildcard nas origens
        CORSConfig.validate_no_wildcard(origins, self.environment)

        return self

    @model_validator(mode="after")
    def validate_https_in_production(self) -> "Settings":
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: Schema Registry, OTEL Collector.
        Pode ser desabilitado com allow_insecure_http_endpoints=True para staging.
        """
        # Permitir HTTP se flag está habilitada (staging com comunicação interna)
        if self.allow_insecure_http_endpoints:
            return self

        is_prod_staging = self.environment.lower() in ("production", "staging", "prod")
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []
        if self.schema_registry_url.startswith("http://"):
            http_endpoints.append(("schema_registry_url", self.schema_registry_url))
        if self.otel_enabled and self.otel_endpoint.startswith("http://"):
            http_endpoints.append(("otel_endpoint", self.otel_endpoint))

        if http_endpoints:
            endpoint_list = ", ".join(f"{name}={url}" for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.environment}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito. "
                "Ou defina ALLOW_INSECURE_HTTP_ENDPOINTS=true para comunicacao interna do cluster."
            )

        return self

    def _ensure_vault_client(self):
        """Inicializa o Vault client se necessário e se Vault estiver habilitado."""
        if not self.vault_enabled:
            return None

        # Thread-safe initialization with double-checked locking
        if self._vault_client is None:
            with self._vault_lock:
                # Double-check after acquiring lock
                if self._vault_client is None:
                    try:
                        # Import correto usando path relativo ao src
                        # Configurar environment para VaultClient
                        import os

                        from src.clients.vault_client import VaultClient

                        if self.vault_addr:
                            os.environ["VAULT_ADDR"] = self.vault_addr
                        if self.vault_token:
                            os.environ["VAULT_TOKEN"] = self.vault_token
                        if self.vault_role:
                            os.environ["VAULT_ROLE"] = self.vault_role

                        self._vault_client = VaultClient()
                    except Exception as e:
                        # Vault não disponível, usar fallback
                        from structlog import get_logger

                        logger = get_logger()
                        logger.warning(
                            "vault_init_failed", error=str(e), fallback="using_env_or_config"
                        )
                        self._vault_client = False  # Marcador para não tentar novamente

        return self._vault_client if self._vault_client is not False else None

    @property
    def JWT_SECRET(self) -> str:
        """
        Retorna JWT secret da seguinte ordem de prioridade:
        1. Vault (se habilitado e disponível)
        2. jwt_secret_key (config)
        3. JWT_SECRET environment variable

        Raises:
            ValueError: Se nenhum secret estiver disponível
        """
        # Thread-safe cache access
        if self._jwt_secret_cached:
            return self._jwt_secret_cached

        # Tentar obter do Vault primeiro (com lock para thread-safety)
        vault_client = self._ensure_vault_client()
        if vault_client and self._jwt_secret_cached is None:
            with self._vault_lock:
                # Double-check after acquiring lock
                if self._jwt_secret_cached is None:
                    try:
                        self._jwt_secret_cached = vault_client.get_jwt_secret()
                    except Exception:
                        pass  # Vault falhou, tentar outros métodos

        # Usar cached secret do Vault
        if self._jwt_secret_cached:
            return self._jwt_secret_cached

        # Fallback para config
        if self.jwt_secret_key:
            return self.jwt_secret_key

        # Fallback para environment variable
        import os

        env_secret = os.getenv("JWT_SECRET")
        if env_secret:
            return env_secret

        raise ValueError(
            "JWT_SECRET não encontrado. Configure via Vault, jwt_secret_key, ou JWT_SECRET environment variable."
        )

    @property
    def SECRET_KEY(self) -> str:
        """
        Retorna SECRET_KEY (para compatibilidade, usa JWT_SECRET).

        Em produção, recomenda-se usar Vault para secrets.
        """
        return self.JWT_SECRET

    class Config:
        env_file = ".env"
        case_sensitive = False


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
