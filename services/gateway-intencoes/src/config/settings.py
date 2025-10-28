from typing import List, Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Configurações da aplicação Gateway de Intenções"""
    
    # Aplicação
    environment: str = Field(default="dev")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    
    # Kafka
    kafka_bootstrap_servers: str = Field(default="neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092")
    schema_registry_url: str = Field(default="http://schema-registry.neural-hive-kafka.svc.cluster.local:8081")

    # Kafka Security
    kafka_security_protocol: str = Field(default="PLAINTEXT")  # PLAINTEXT, SASL_SSL, SSL
    kafka_sasl_mechanism: str = Field(default="SCRAM-SHA-512")  # PLAIN, SCRAM-SHA-256, SCRAM-SHA-512
    kafka_sasl_username: Optional[str] = Field(default=None)
    kafka_sasl_password: Optional[str] = Field(default=None)
    kafka_ssl_ca_location: Optional[str] = Field(default=None)
    kafka_ssl_certificate_location: Optional[str] = Field(default=None)
    kafka_ssl_key_location: Optional[str] = Field(default=None)

    # Kafka Performance
    kafka_batch_size: int = Field(default=16384)  # bytes
    kafka_linger_ms: int = Field(default=10)  # milliseconds
    kafka_compression_type: str = Field(default="snappy")  # none, gzip, snappy, lz4, zstd
    
    # ASR Pipeline
    asr_model_name: str = Field(default="base")
    asr_device: str = Field(default="cpu")
    asr_timeout_seconds: int = Field(default=60)
    asr_max_concurrent_jobs: int = Field(default=5)
    
    # NLU Pipeline
    nlu_language_model: str = Field(default="pt_core_news_sm")
    nlu_confidence_threshold: float = Field(default=0.75)
    nlu_cache_enabled: bool = Field(default=True)
    nlu_cache_ttl_seconds: int = Field(default=3600)
    
    # Redis Cache
    redis_cluster_nodes: str = Field(default="neural-hive-cache.redis-cluster.svc.cluster.local:6379")
    redis_password: Optional[str] = Field(default=None)
    redis_ca_cert_path: Optional[str] = Field(default=None)
    redis_default_ttl: int = Field(default=600)  # 10 minutos
    redis_max_connections: int = Field(default=100)
    redis_pool_size: int = Field(default=10)
    redis_timeout: int = Field(default=5000)  # ms

    # Redis Security
    redis_ssl_enabled: bool = Field(default=False)
    redis_ssl_cert_reqs: str = Field(default="required")  # none, optional, required
    redis_ssl_ca_certs: Optional[str] = Field(default=None)
    redis_ssl_certfile: Optional[str] = Field(default=None)
    redis_ssl_keyfile: Optional[str] = Field(default=None)

    # Redis Performance
    redis_connection_pool_max_connections: int = Field(default=50)
    redis_retry_on_timeout: bool = Field(default=True)

    # OAuth2/Keycloak
    keycloak_url: str = Field(default="https://keycloak.neural-hive.local")
    keycloak_realm: str = Field(default="neural-hive")
    keycloak_client_id: str = Field(default="gateway-intencoes")
    keycloak_client_secret: Optional[str] = Field(default=None)
    jwks_uri: str = Field(default="https://keycloak.neural-hive.local/auth/realms/neural-hive/protocol/openid-connect/certs")
    token_validation_enabled: bool = Field(default=True)

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_requests_per_minute: int = Field(default=1000)
    rate_limit_burst_size: int = Field(default=100)

    # Security Features
    mtls_validation_enabled: bool = Field(default=False)
    api_key_auth_enabled: bool = Field(default=False)
    request_signature_validation_enabled: bool = Field(default=False)

    # Segurança (mantido para compatibilidade)
    jwt_secret_key: str = Field(default="your-secret-key")
    jwt_algorithm: str = Field(default="HS256")
    
    # CORS e hosts
    allowed_origins: List[str] = Field(default=["*"])
    allowed_hosts: List[str] = Field(default=["*"])
    
    # Observabilidade - OpenTelemetry Collector OTLP endpoint
    otel_endpoint: str = Field(default="http://opentelemetry-collector.observability.svc.cluster.local:4317")
    prometheus_port: int = Field(default=8080)
    jaeger_sampling_rate: float = Field(default=0.1)
    
    # Limites
    max_audio_size_mb: int = Field(default=10)
    max_text_length: int = Field(default=10000)

    # Feature Flags
    batch_processing_enabled: bool = Field(default=True)
    circuit_breaker_enabled: bool = Field(default=True)
    distributed_cache_enabled: bool = Field(default=True)
    
    @validator('kafka_security_protocol')
    def validate_kafka_security_protocol(cls, v):
        allowed = ['PLAINTEXT', 'SASL_SSL', 'SSL', 'SASL_PLAINTEXT']
        if v not in allowed:
            raise ValueError(f'kafka_security_protocol must be one of {allowed}')
        return v

    @validator('kafka_sasl_mechanism')
    def validate_kafka_sasl_mechanism(cls, v):
        allowed = ['PLAIN', 'SCRAM-SHA-256', 'SCRAM-SHA-512', 'GSSAPI']
        if v not in allowed:
            raise ValueError(f'kafka_sasl_mechanism must be one of {allowed}')
        return v

    @validator('redis_ssl_cert_reqs')
    def validate_redis_ssl_cert_reqs(cls, v):
        allowed = ['none', 'optional', 'required']
        if v not in allowed:
            raise ValueError(f'redis_ssl_cert_reqs must be one of {allowed}')
        return v

    @validator('environment')
    def validate_environment_security(cls, v, values):
        if v == 'prod':
            # Em produção, alguns recursos de segurança são obrigatórios
            if not values.get('token_validation_enabled', True):
                raise ValueError('token_validation_enabled must be True in production')
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False

_settings: Optional[Settings] = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings