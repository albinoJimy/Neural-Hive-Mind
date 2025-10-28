"""
Configuration Settings for Semantic Translation Engine

Manages all configuration using Pydantic Settings with environment variable support.
"""

from typing import List, Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Application configuration
    environment: str = Field(default='dev', description='Environment (dev, staging, production)')
    debug: bool = Field(default=False, description='Debug mode')
    log_level: str = Field(default='INFO', description='Logging level')
    service_name: str = Field(default='semantic-translation-engine', description='Service name')
    service_version: str = Field(default='1.0.0', description='Service version')

    # Kafka Consumer configuration
    kafka_bootstrap_servers: str = Field(..., description='Kafka bootstrap servers')
    kafka_consumer_group_id: str = Field(
        default='semantic-translation-engine',
        description='Kafka consumer group ID'
    )
    kafka_topics: List[str] = Field(
        default=[
            'intentions.business',
            'intentions.technical',
            'intentions.infrastructure',
            'intentions.security'
        ],
        description='Kafka topics to consume'
    )
    kafka_auto_offset_reset: str = Field(default='earliest', description='Auto offset reset')
    kafka_enable_auto_commit: bool = Field(default=False, description='Enable auto commit')
    kafka_session_timeout_ms: int = Field(default=30000, description='Session timeout (ms)')

    # Kafka Producer configuration
    kafka_plans_topic: str = Field(default='plans.ready', description='Plans output topic')
    kafka_enable_idempotence: bool = Field(default=True, description='Enable idempotence')
    kafka_transactional_id: Optional[str] = Field(None, description='Transactional ID')

    # Kafka Security
    kafka_security_protocol: str = Field(default='PLAINTEXT', description='Security protocol')
    kafka_sasl_mechanism: Optional[str] = Field(None, description='SASL mechanism')
    kafka_sasl_username: Optional[str] = Field(None, description='SASL username')
    kafka_sasl_password: Optional[str] = Field(None, description='SASL password')

    # Schema Registry
    schema_registry_url: Optional[str] = Field(None, description='Schema Registry URL')

    # Neo4j configuration
    neo4j_uri: str = Field(
        default='bolt://neo4j-bolt.neo4j-cluster.svc.cluster.local:7687',
        description='Neo4j URI'
    )
    neo4j_user: str = Field(default='neo4j', description='Neo4j user')
    neo4j_password: str = Field(..., description='Neo4j password')
    neo4j_database: str = Field(default='neo4j', description='Neo4j database')
    neo4j_max_connection_pool_size: int = Field(default=50, description='Max connection pool size')
    neo4j_connection_timeout: int = Field(default=30, description='Connection timeout (seconds)')
    neo4j_query_timeout: int = Field(default=50, description='Query timeout (ms)')

    # MongoDB configuration
    mongodb_uri: str = Field(
        default='mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017',
        description='MongoDB URI'
    )
    mongodb_database: str = Field(default='neural_hive', description='MongoDB database')
    mongodb_context_collection: str = Field(
        default='operational_context',
        description='Context collection'
    )
    mongodb_ledger_collection: str = Field(
        default='cognitive_ledger',
        description='Ledger collection'
    )
    mongodb_max_pool_size: int = Field(default=100, description='Max pool size')
    mongodb_timeout_ms: int = Field(default=5000, description='Timeout (ms)')

    # Redis configuration
    redis_cluster_nodes: str = Field(..., description='Redis cluster nodes')
    redis_cluster_enabled: bool = Field(default=True, description='Enable cluster mode')
    redis_password: Optional[str] = Field(None, description='Redis password')
    redis_ssl_enabled: bool = Field(default=False, description='Enable SSL')
    redis_default_ttl: int = Field(default=600, description='Default TTL (seconds)')
    redis_cache_enabled: bool = Field(default=True, description='Enable caching')

    # Observability configuration
    otel_endpoint: str = Field(
        default='http://opentelemetry-collector.observability.svc.cluster.local:4317',
        description='OpenTelemetry endpoint'
    )
    prometheus_port: int = Field(default=8080, description='Prometheus metrics port')
    jaeger_sampling_rate: float = Field(default=1.0, description='Jaeger sampling rate')

    # Risk Scoring configuration
    risk_weight_priority: float = Field(default=0.3, description='Priority weight')
    risk_weight_security: float = Field(default=0.4, description='Security weight')
    risk_weight_complexity: float = Field(default=0.3, description='Complexity weight')
    risk_threshold_high: float = Field(default=0.7, description='High risk threshold')
    risk_threshold_critical: float = Field(default=0.9, description='Critical risk threshold')

    # Feature Flags
    knowledge_graph_enabled: bool = Field(default=True, description='Enable Knowledge Graph')
    ledger_enabled: bool = Field(default=True, description='Enable Ledger')
    explainability_enabled: bool = Field(default=True, description='Enable Explainability')
    circuit_breaker_enabled: bool = Field(default=True, description='Enable Circuit Breaker')

    @validator('kafka_topics', pre=True)
    def parse_topics(cls, v):
        """Parse CSV string or JSON to list if needed"""
        if isinstance(v, str):
            # Try JSON first
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
            # Fallback to CSV
            return [s.strip() for s in v.split(',') if s.strip()]
        return v

    @validator('risk_weight_priority', 'risk_weight_security', 'risk_weight_complexity')
    def validate_weights(cls, v):
        """Validate risk weights are between 0 and 1"""
        if not 0 <= v <= 1:
            raise ValueError('Risk weights must be between 0 and 1')
        return v

    @validator('neo4j_query_timeout')
    def validate_neo4j_timeout(cls, v):
        """Validate Neo4j timeout meets SLO"""
        if v > 100:
            raise ValueError('Neo4j query timeout should be <= 100ms for SLO compliance')
        return v

    @validator('kafka_security_protocol')
    def validate_security_in_production(cls, v, values):
        """Validate security is enabled in production"""
        if values.get('environment') == 'production' and v == 'PLAINTEXT':
            raise ValueError('Production environment requires encrypted Kafka connection')
        return v

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings singleton instance"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
