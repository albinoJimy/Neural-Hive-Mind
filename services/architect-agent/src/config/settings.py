"""Configuration settings for Architect Agent using Pydantic"""

from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from neural_hive_security.cors import CORSConfig


class ServiceConfig(BaseModel):
    """Service configuration"""

    service_name: str = Field(default="architect-agent", description="Service name")
    version: str = Field(default="1.0.0", description="Service version")
    environment: str = Field(
        default="development", description="Environment (development/staging/production)"
    )
    is_public_api: bool = Field(default=True, description="API pública requer CORS")
    log_level: str = Field(default="INFO", description="Log level")
    http_port: int = Field(default=8011, description="HTTP server port")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        if v not in ("development", "staging", "production"):
            raise ValueError("environment must be development, staging, or production")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        if v.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ValueError("log_level must be DEBUG, INFO, WARNING, or ERROR")
        return v.upper()

    @field_validator("http_port")
    @classmethod
    def validate_port(cls, v):
        if not 1024 <= v <= 65535:
            raise ValueError("Port must be between 1024 and 65535")
        return v


class KafkaConfig(BaseModel):
    """Kafka configuration"""

    bootstrap_servers: str = Field(default="localhost:9092", description="Kafka bootstrap servers")
    cognitive_plans_topic: str = Field(
        default="cognitive.plans.created", description="Cognitive plans topic"
    )
    consumer_group: str = Field(default="architect-agent", description="Consumer group ID")
    auto_offset_reset: str = Field(default="earliest", description="Auto offset reset policy")


class MongoDBConfig(BaseModel):
    """MongoDB configuration"""

    url: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URL")
    database: str = Field(default="architect_agent", description="Database name")
    collection_architecture: str = Field(
        default="architecture_plans", description="Architecture plans collection"
    )
    collection_validation: str = Field(
        default="validation_reports", description="Validation reports collection"
    )
    collection_evolution: str = Field(
        default="evolution_history", description="Evolution history collection"
    )


class ScoutAgentsConfig(BaseModel):
    """Scout Agents configuration"""

    url: str = Field(default="http://localhost:8020", description="Scout Agents URL")
    timeout_seconds: int = Field(default=30, description="Request timeout in seconds")

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v):
        if v <= 0:
            raise ValueError("timeout must be positive")
        return v


class OPAConfig(BaseModel):
    """Open Policy Agent configuration"""

    url: str = Field(default="http://localhost:8181", description="OPA server URL")
    policy_path: str = Field(
        default="architecture/rules", description="OPA policy path (without /v1/data/ prefix)"
    )
    timeout_seconds: int = Field(default=10, description="Request timeout in seconds")

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v):
        if v <= 0:
            raise ValueError("timeout must be positive")
        return v


class LLMConfig(BaseModel):
    """LLM configuration (optional)"""

    provider: str = Field(default="", description="LLM provider (openai/anthropic)")
    api_key: Optional[str] = Field(
        default=None, description="LLM API key (OBRIGATÓRIO se provider definido)"
    )
    model: str = Field(default="gpt-4", description="LLM model name")
    timeout_seconds: int = Field(default=60, description="Request timeout in seconds")
    max_tokens: int = Field(default=2000, description="Maximum tokens for generation")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v):
        if v and v not in ("openai", "anthropic"):
            raise ValueError("provider must be openai, anthropic, or empty")
        return v

    @field_validator("timeout_seconds", "max_tokens")
    @classmethod
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError("value must be positive")
        return v


class ObservabilityConfig(BaseModel):
    """Observability configuration"""

    otel_endpoint: str = Field(
        default="http://otel-collector:4317", description="OpenTelemetry endpoint"
    )
    prometheus_port: int = Field(default=9098, description="Prometheus metrics port")

    @field_validator("prometheus_port")
    @classmethod
    def validate_port(cls, v):
        if not 1024 <= v <= 65535:
            raise ValueError("Port must be between 1024 and 65535")
        return v


class Settings(BaseSettings):
    """Main settings class aggregating all configurations"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_nested_delimiter="__", case_sensitive=False
    )

    service: ServiceConfig = Field(default_factory=ServiceConfig)
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)
    mongodb: MongoDBConfig = Field(default_factory=MongoDBConfig)
    scout_agents: ScoutAgentsConfig = Field(default_factory=ScoutAgentsConfig)
    opa: OPAConfig = Field(default_factory=OPAConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @property
    def CORS_ORIGINS(self) -> List[str]:
        """
        CORS origins dinâmicas por ambiente usando neural_hive_security.
        """
        return CORSConfig.get_origins_for_environment(
            self.service.environment, is_public_api=self.service.is_public_api
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
