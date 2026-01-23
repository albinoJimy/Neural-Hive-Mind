"""Configuration settings for Scout Agents using Pydantic"""
from functools import lru_cache
from typing import List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseModel):
    """Service configuration"""
    service_name: str = Field(default="scout-agents", description="Service name")
    version: str = Field(default="1.0.7", description="Service version")
    environment: str = Field(default="dev", description="Environment (dev/staging/prod)")
    log_level: str = Field(default="INFO", description="Log level")


class KafkaConfig(BaseModel):
    """Kafka configuration"""
    bootstrap_servers: str = Field(default="localhost:9092", description="Kafka bootstrap servers")
    consumer_group_id: str = Field(default="scout-agents-dev", description="Consumer group ID")
    topics_signals: str = Field(default="exploration-signals", description="Signals topic")
    topics_opportunities: str = Field(default="exploration-opportunities", description="Opportunities topic")
    enable_sasl: bool = Field(default=False, description="Enable SASL authentication")
    sasl_mechanism: str = Field(default="PLAIN", description="SASL mechanism")
    sasl_username: str = Field(default="", description="SASL username")
    sasl_password: str = Field(default="", description="SASL password")
    enable_ssl: bool = Field(default=False, description="Enable SSL")


class ServiceRegistryConfig(BaseModel):
    """Service Registry configuration"""
    host: str = Field(default="service-registry", description="Service Registry host")
    port: int = Field(default=50051, description="Service Registry port")
    registration_interval: int = Field(default=300, description="Registration interval in seconds")
    heartbeat_interval: int = Field(default=30, description="Heartbeat interval in seconds")
    capabilities: Dict[str, Any] = Field(
        default_factory=lambda: {
            "agent_type": "scout",
            "exploration_domains": ["BUSINESS", "TECHNICAL"],
            "channel_types": ["CORE", "WEB", "API"],
            "max_signals_per_minute": 100
        },
        description="Agent capabilities"
    )

    @field_validator('port')
    @classmethod
    def validate_port(cls, v):
        if not 1024 <= v <= 65535:
            raise ValueError('Port must be between 1024 and 65535')
        return v


class MemoryLayerConfig(BaseModel):
    """Memory Layer API configuration"""
    api_url: str = Field(default="http://memory-layer-api:8000", description="Memory Layer API URL")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    retry_attempts: int = Field(default=3, description="Retry attempts on failure")


class PheromoneConfig(BaseModel):
    """Pheromone configuration"""
    enabled: bool = Field(default=True, description="Enable pheromone publishing")
    ttl: int = Field(default=3600, description="Pheromone TTL in seconds (1 hour)")
    decay_rate: float = Field(default=0.15, description="Decay rate per hour (15%)")
    # DEPRECATED: Chaves de feromônio agora são geradas via DomainMapper.to_pheromone_key()
    # Formato unificado: pheromone:{layer}:{domain}:{type}:{id?}
    # Esta configuração será removida em versão futura
    redis_key_prefix: str = Field(default="pheromone:exploration:", description="DEPRECATED - Redis key prefix")
    redis_url: str = Field(default="redis://neural-hive-cache.redis-cluster.svc.cluster.local:6379", description="Redis URL")

    @field_validator('decay_rate')
    @classmethod
    def validate_decay_rate(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError('Decay rate must be between 0.0 and 1.0')
        return v


class DetectionConfig(BaseModel):
    """Detection configuration"""
    curiosity_threshold: float = Field(default=0.6, description="Minimum curiosity score to publish")
    confidence_threshold: float = Field(default=0.7, description="Minimum confidence to publish")
    relevance_threshold: float = Field(default=0.5, description="Minimum relevance score")
    risk_threshold: float = Field(default=0.8, description="Maximum acceptable risk score")
    max_signals_per_minute: int = Field(default=100, description="Rate limit for signal publishing")

    @field_validator('curiosity_threshold', 'confidence_threshold', 'relevance_threshold', 'risk_threshold')
    @classmethod
    def validate_score(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError('Score thresholds must be between 0.0 and 1.0')
        return v


class ObservabilityConfig(BaseModel):
    """Observability configuration"""
    prometheus_port: int = Field(default=9090, description="Prometheus metrics port")
    http_port: int = Field(default=8000, description="HTTP server port")
    tracing_enabled: bool = Field(default=True, description="Enable OpenTelemetry tracing")
    jaeger_endpoint: str = Field(default="http://jaeger-collector:14268/api/traces", description="Jaeger endpoint")

    @field_validator('prometheus_port', 'http_port')
    @classmethod
    def validate_port(cls, v):
        if not 1024 <= v <= 65535:
            raise ValueError('Port must be between 1024 and 65535')
        return v


class Settings(BaseSettings):
    """Main settings class aggregating all configurations"""
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_nested_delimiter='__',
        case_sensitive=False
    )

    service: ServiceConfig = Field(default_factory=ServiceConfig)
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)
    service_registry: ServiceRegistryConfig = Field(default_factory=ServiceRegistryConfig)
    memory_layer: MemoryLayerConfig = Field(default_factory=MemoryLayerConfig)
    pheromone: PheromoneConfig = Field(default_factory=PheromoneConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
