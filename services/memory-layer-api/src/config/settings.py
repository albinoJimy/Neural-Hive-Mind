"""
Memory Layer API Settings
"""
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional


class Settings(BaseSettings):
    """Memory Layer API configuration"""

    # Application
    environment: str = Field(default='dev', description="Environment (dev, staging, production)")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default='INFO', description="Log level")
    service_name: str = Field(default='memory-layer-api', description="Service name")
    service_version: str = Field(default='1.0.0', description="Service version")

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
    neo4j_password: str = Field(..., description="Neo4j password")
    neo4j_database: str = Field(default='neo4j', description="Neo4j database name")
    neo4j_query_timeout: int = Field(default=50, description="Neo4j query timeout in ms")

    # ClickHouse (Histórico)
    clickhouse_host: str = Field(
        default='clickhouse-http.clickhouse-cluster.svc.cluster.local',
        description="ClickHouse host"
    )
    clickhouse_port: int = Field(default=8123, description="ClickHouse HTTP port")
    clickhouse_user: str = Field(default='default', description="ClickHouse username")
    clickhouse_password: str = Field(..., description="ClickHouse password")
    clickhouse_database: str = Field(default='neural_hive', description="ClickHouse database")
    clickhouse_retention_months: int = Field(
        default=18,
        description="ClickHouse retention period in months"
    )

    # Observabilidade
    otel_endpoint: str = Field(
        default='http://opentelemetry-collector.observability.svc.cluster.local:4317',
        description="OpenTelemetry collector endpoint"
    )
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

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
