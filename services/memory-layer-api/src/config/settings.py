"""
Memory Layer API Settings
"""
from pydantic_settings import BaseSettings
from pydantic import Field, validator, model_validator
from typing import Optional


class Settings(BaseSettings):
    """Memory Layer API configuration"""

    # Application
    environment: str = Field(default='dev', description="Environment (dev, staging, production)")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default='INFO', description="Log level")
    service_name: str = Field(default='memory-layer-api', description="Service name")
    service_version: str = Field(default='1.0.0', description="Service version")
    allow_insecure_http_endpoints: bool = Field(
        default=False,
        description="Allow insecure HTTP endpoints in production (for internal cluster communication)"
    )

    # Redis (Curto Prazo)
    redis_cluster_nodes: str = Field(
        default='neural-hive-cache.redis-cluster.svc.cluster.local:6379',
        description="Redis cluster nodes (comma-separated)"
    )
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_ssl_enabled: bool = Field(default=False, description="Enable SSL for Redis")
    redis_default_ttl: int = Field(default=300, description="Default TTL in seconds (5 minutes)")
    redis_max_ttl: int = Field(default=900, description="Max TTL in seconds (15 minutes)")

    # MongoDB (Operacional)
    mongodb_uri: str = Field(
        default='mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017',
        description="MongoDB connection URI"
    )
    mongodb_database: str = Field(default='neural_hive', description="MongoDB database name")
    mongodb_context_collection: str = Field(
        default='operational_context',
        description="Collection for operational context"
    )
    mongodb_lineage_collection: str = Field(
        default='data_lineage',
        description="Collection for data lineage"
    )
    mongodb_quality_collection: str = Field(
        default='data_quality_metrics',
        description="Collection for quality metrics"
    )
    mongodb_retention_days: int = Field(default=30, description="MongoDB retention period in days")

    # Neo4j (Semântico)
    neo4j_uri: str = Field(
        default='bolt://neo4j-bolt.neo4j-cluster.svc.cluster.local:7687',
        description="Neo4j connection URI"
    )
    neo4j_user: str = Field(default='neo4j', description="Neo4j username")
    neo4j_password: str = Field(default="", description="Neo4j password")
    neo4j_database: str = Field(default='neo4j', description="Neo4j database name")
    neo4j_query_timeout: int = Field(default=50, description="Neo4j query timeout in ms")

    # ClickHouse (Histórico)
    clickhouse_host: str = Field(
        default='clickhouse-http.clickhouse-cluster.svc.cluster.local',
        description="ClickHouse host"
    )
    clickhouse_port: int = Field(default=8123, description="ClickHouse HTTP port")
    clickhouse_user: str = Field(default='default', description="ClickHouse username")
    clickhouse_password: str = Field(default="", description="ClickHouse password")
    clickhouse_database: str = Field(default='neural_hive', description="ClickHouse database")
    clickhouse_retention_months: int = Field(
        default=18,
        description="ClickHouse retention period in months"
    )

    # Kafka (Real-time Sync)
    kafka_bootstrap_servers: str = Field(
        default='kafka-cluster-kafka-bootstrap.kafka.svc.cluster.local:9092',
        description="Kafka bootstrap servers"
    )
    kafka_sync_topic: str = Field(
        default='memory.sync.events',
        description="Topic para eventos de sincronização de memória"
    )
    kafka_dlq_topic: str = Field(
        default='memory.sync.events.dlq',
        description="Topic de Dead Letter Queue para eventos com falha"
    )
    kafka_schema_registry_url: str = Field(
        default='https://schema-registry.kafka.svc.cluster.local:8081',
        description="URL do Schema Registry"
    )
    schema_registry_tls_verify: bool = Field(default=True, description="Verificar certificado TLS do Schema Registry")
    schema_registry_ca_bundle: Optional[str] = Field(default=None, description="Caminho para CA bundle do Schema Registry")
    kafka_security_protocol: str = Field(
        default='PLAINTEXT',
        description="Protocolo de segurança Kafka"
    )
    kafka_sasl_username: Optional[str] = Field(default=None, description="Username SASL Kafka")
    kafka_sasl_password: Optional[str] = Field(default=None, description="Password SASL Kafka")
    kafka_consumer_group: str = Field(
        default='memory-sync-consumer',
        description="Consumer group para sincronização"
    )
    enable_realtime_sync: bool = Field(
        default=True,
        description="Habilitar sincronização em tempo real via Kafka"
    )

    # Observabilidade
    otel_endpoint: str = Field(
        default='https://opentelemetry-collector.observability.svc.cluster.local:4317',
        description="OpenTelemetry collector endpoint"
    )
    otel_tls_verify: bool = Field(default=True, description="Verificar certificado TLS do OTEL Collector")
    otel_ca_bundle: Optional[str] = Field(default=None, description="Caminho para CA bundle do OTEL Collector")
    prometheus_port: int = Field(default=8080, description="Prometheus metrics port")
    jaeger_sampling_rate: float = Field(default=1.0, description="Jaeger sampling rate")

    # Roteamento de Queries
    hot_data_threshold_seconds: int = Field(
        default=300,
        description="Threshold for hot data (Redis) in seconds"
    )
    warm_data_threshold_days: int = Field(
        default=30,
        description="Threshold for warm data (MongoDB) in days"
    )
    cold_data_threshold_months: int = Field(
        default=18,
        description="Threshold for cold data (ClickHouse) in months"
    )

    # Data Quality
    quality_check_enabled: bool = Field(default=True, description="Enable quality checks")
    completeness_threshold: float = Field(
        default=0.95,
        description="Minimum completeness score (0-1)"
    )
    accuracy_threshold: float = Field(
        default=0.95,
        description="Minimum accuracy score (0-1)"
    )
    freshness_threshold_hours: int = Field(
        default=24,
        description="Maximum freshness age in hours"
    )

    # Feature Flags
    enable_cache: bool = Field(default=True, description="Enable caching")
    enable_lineage_tracking: bool = Field(default=True, description="Enable lineage tracking")
    enable_quality_monitoring: bool = Field(default=True, description="Enable quality monitoring")
    enable_auto_routing: bool = Field(default=True, description="Enable automatic query routing")

    @validator('completeness_threshold', 'accuracy_threshold')
    def validate_score_range(cls, v):
        """Validate score thresholds are between 0 and 1"""
        if not 0.0 <= v <= 1.0:
            raise ValueError('Score thresholds must be between 0.0 and 1.0')
        return v

    @validator('redis_default_ttl', 'redis_max_ttl', 'mongodb_retention_days',
               'clickhouse_retention_months', 'freshness_threshold_hours')
    def validate_positive(cls, v):
        """Validate retention periods are positive"""
        if v <= 0:
            raise ValueError('Retention periods must be positive')
        return v

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'Settings':
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: Schema Registry, OTEL Collector.
        Pode ser desabilitado com allow_insecure_http_endpoints=True para staging.
        """
        # Permitir HTTP se flag está habilitada (staging com comunicação interna)
        if self.allow_insecure_http_endpoints:
            return self

        is_prod_staging = self.environment.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []
        if self.kafka_schema_registry_url.startswith('http://'):
            http_endpoints.append(('kafka_schema_registry_url', self.kafka_schema_registry_url))
        if self.otel_endpoint.startswith('http://'):
            http_endpoints.append(('otel_endpoint', self.otel_endpoint))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.environment}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito."
            )

        return self

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
