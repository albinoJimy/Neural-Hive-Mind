"""
Configurações do SLA Management System usando Pydantic Settings.
"""

from functools import lru_cache
from typing import List, Dict, Any
from pydantic import Field
from pydantic_settings import BaseSettings


class PrometheusSettings(BaseSettings):
    """Configurações do Prometheus."""
    url: str = Field(
        default="http://prometheus-server.monitoring.svc.cluster.local:9090",
        description="URL do Prometheus"
    )
    timeout_seconds: int = Field(default=30, description="Timeout para queries")
    max_retries: int = Field(default=3, description="Retries em caso de falha")


class PostgreSQLSettings(BaseSettings):
    """Configurações do PostgreSQL."""
    host: str = Field(default="postgres-sla.neural-hive-data.svc.cluster.local")
    port: int = Field(default=5432)
    database: str = Field(default="sla_management")
    user: str = Field(default="sla_user")
    password: str = Field(default="", description="Senha do PostgreSQL")
    pool_min_size: int = Field(default=2)
    pool_max_size: int = Field(default=10)
    connection_timeout: int = Field(default=10)


class RedisSettings(BaseSettings):
    """Configurações do Redis."""
    cluster_nodes: List[str] = Field(
        default=["redis-cluster.redis-cluster.svc.cluster.local:6379"]
    )
    password: str = Field(default="")
    ssl: bool = Field(default=False)
    decode_responses: bool = Field(default=True)
    cache_ttl_seconds: int = Field(default=60, description="TTL para budgets")


class KafkaSettings(BaseSettings):
    """Configurações do Kafka."""
    bootstrap_servers: List[str] = Field(
        default=["kafka-bootstrap.kafka.svc.cluster.local:9092"]
    )
    budget_topic: str = Field(default="sla.budgets")
    freeze_topic: str = Field(default="sla.freeze.events")
    violations_topic: str = Field(default="sla.violations")
    producer_config: Dict[str, Any] = Field(
        default={
            "compression_type": "gzip",
            "acks": "all",
            "retries": 3,
            "max_in_flight_requests_per_connection": 5
        }
    )


class AlertmanagerSettings(BaseSettings):
    """Configurações do Alertmanager."""
    url: str = Field(
        default="http://alertmanager.monitoring.svc.cluster.local:9093"
    )
    webhook_path: str = Field(default="/webhooks/alertmanager")
    api_timeout_seconds: int = Field(default=10)


class CalculatorSettings(BaseSettings):
    """Configurações do calculador de budgets."""
    calculation_interval_seconds: int = Field(
        default=30,
        description="Intervalo de cálculo de budgets"
    )
    error_budget_window_days: int = Field(
        default=30,
        description="Janela de cálculo"
    )
    burn_rate_fast_threshold: float = Field(
        default=14.4,
        description="Threshold para fast burn"
    )
    burn_rate_slow_threshold: float = Field(
        default=6,
        description="Threshold para slow burn"
    )


class PolicySettings(BaseSettings):
    """Configurações de políticas de freeze."""
    freeze_threshold_percent: float = Field(
        default=20,
        description="% de budget para acionar freeze"
    )
    auto_unfreeze_enabled: bool = Field(
        default=True,
        description="Auto-descongelar quando budget recupera"
    )
    unfreeze_threshold_percent: float = Field(
        default=50,
        description="% para descongelar"
    )


class Settings(BaseSettings):
    """Configurações principais do SLA Management System."""

    service_name: str = Field(default="sla-management-system")
    version: str = Field(default="1.0.0")
    environment: str = Field(default="production")
    log_level: str = Field(default="INFO")
    debug: bool = Field(default=False)

    # Sub-settings
    prometheus: PrometheusSettings = Field(default_factory=PrometheusSettings)
    postgresql: PostgreSQLSettings = Field(default_factory=PostgreSQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    alertmanager: AlertmanagerSettings = Field(default_factory=AlertmanagerSettings)
    calculator: CalculatorSettings = Field(default_factory=CalculatorSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)

    model_config = {
        "env_file": ".env",
        "env_nested_delimiter": "__",
        "case_sensitive": False
    }


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton das configurações."""
    return Settings()
