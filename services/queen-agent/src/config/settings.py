from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações do Queen Agent via variáveis de ambiente"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True
    )

    # Service Metadata
    SERVICE_NAME: str = 'queen-agent'
    SERVICE_VERSION: str = '1.0.0'
    ENVIRONMENT: str = 'production'
    LOG_LEVEL: str = 'INFO'

    # FastAPI
    FASTAPI_HOST: str = '0.0.0.0'
    FASTAPI_PORT: int = 8000
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ['*'])

    # gRPC
    GRPC_PORT: int = 50053
    GRPC_MAX_WORKERS: int = 10

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str
    KAFKA_CONSUMER_GROUP: str = 'queen-agent-group'
    KAFKA_TOPICS_CONSENSUS: str = 'plans.consensus'
    KAFKA_TOPICS_TELEMETRY: str = 'telemetry.aggregated'
    KAFKA_TOPICS_INCIDENTS: str = 'incidents.critical'
    KAFKA_TOPICS_STRATEGIC: str = 'strategic.decisions'
    KAFKA_AUTO_OFFSET_RESET: str = 'earliest'

    # MongoDB
    MONGODB_URI: str
    MONGODB_DATABASE: str = 'neural_hive'
    MONGODB_COLLECTION_LEDGER: str = 'strategic_decisions_ledger'
    MONGODB_COLLECTION_EXCEPTIONS: str = 'exception_approvals'
    MONGODB_MAX_POOL_SIZE: int = 100
    MONGODB_MIN_POOL_SIZE: int = 10

    # Redis
    REDIS_CLUSTER_NODES: str
    REDIS_PASSWORD: str = ''
    REDIS_SSL_ENABLED: bool = True
    # DEPRECATED: Chaves de feromônio agora são geradas via DomainMapper.to_pheromone_key()
    # Formato unificado: pheromone:{layer}:{domain}:{type}:{id?}
    # Esta configuração será removida em versão futura
    REDIS_PHEROMONE_PREFIX: str = 'pheromone:strategic:'
    REDIS_CACHE_TTL_SECONDS: int = 300

    # Neo4j
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    NEO4J_DATABASE: str = 'neo4j'
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = 50

    # Prometheus
    PROMETHEUS_URL: str = 'http://prometheus-server:9090'
    PROMETHEUS_QUERY_TIMEOUT_SECONDS: int = 30

    # Orchestrator Integration (Strategic Commands gRPC)
    ORCHESTRATOR_GRPC_HOST: str = 'orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local'
    ORCHESTRATOR_GRPC_PORT: int = 50053
    ORCHESTRATOR_GRPC_TIMEOUT: int = 10

    # SPIFFE/SPIRE mTLS
    SPIFFE_ENABLED: bool = False
    SPIFFE_SOCKET_PATH: str = 'unix:///run/spire/sockets/agent.sock'
    SPIFFE_TRUST_DOMAIN: str = 'neural-hive.local'
    SPIFFE_ENABLE_X509: bool = False

    # Service Registry Integration
    SERVICE_REGISTRY_GRPC_HOST: str = 'service-registry'
    SERVICE_REGISTRY_GRPC_PORT: int = 50051

    # Decision Engine
    DECISION_CONFIDENCE_THRESHOLD: float = 0.7
    CONFLICT_RESOLUTION_TIMEOUT_SECONDS: int = 60
    REPLANNING_COOLDOWN_SECONDS: int = 300
    MAX_CONCURRENT_DECISIONS: int = 5

    # Observability
    OTEL_EXPORTER_ENDPOINT: str = 'http://jaeger-collector:4317'
    METRICS_PORT: int = 9090
    CIRCUIT_BREAKER_ENABLED: bool = True
    CIRCUIT_BREAKER_FAIL_MAX: int = 5
    CIRCUIT_BREAKER_TIMEOUT: int = 60
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30

    # OPA Policy Engine
    OPA_ENABLED: bool = True
    OPA_URL: str = 'http://opa.neural-hive-governance:8181'
    OPA_TIMEOUT_SECONDS: int = 5
    OPA_FAIL_OPEN: bool = False  # Fail closed em produção

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'Settings':
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: Prometheus, OTEL, OPA.
        """
        is_prod_staging = self.ENVIRONMENT.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []
        if self.PROMETHEUS_URL.startswith('http://'):
            http_endpoints.append(('PROMETHEUS_URL', self.PROMETHEUS_URL))
        if self.OTEL_EXPORTER_ENDPOINT.startswith('http://'):
            http_endpoints.append(('OTEL_EXPORTER_ENDPOINT', self.OTEL_EXPORTER_ENDPOINT))
        if self.OPA_URL.startswith('http://'):
            http_endpoints.append(('OPA_URL', self.OPA_URL))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.ENVIRONMENT}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito."
            )

        return self


@lru_cache()
def get_settings() -> Settings:
    """Retorna singleton de configurações"""
    return Settings()
