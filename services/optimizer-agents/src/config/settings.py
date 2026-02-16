from functools import lru_cache
from typing import List, Optional
import warnings

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Optimizer Agents."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    environment: str = Field(default="dev", description="Environment (dev, staging, prod)")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    service_name: str = Field(default="optimizer-agents", description="Service name")
    service_version: str = Field(default="1.0.0", description="Service version")

    # Kafka
    kafka_bootstrap_servers: str = Field(default="kafka.kafka.svc.cluster.local:9092")
    kafka_consumer_group_id: str = Field(default="optimizer-agents")
    kafka_insights_topic: str = Field(default="insights.generated")
    kafka_telemetry_topic: str = Field(default="telemetry.aggregated")
    kafka_optimization_topic: str = Field(default="optimization.applied")
    kafka_experiments_topic: str = Field(default="experiments.results")
    kafka_experiment_requests_topic: str = Field(default="experiments.requests", description="Kafka topic for experiment requests")

    # gRPC Server
    grpc_port: int = Field(default=50051, description="gRPC server port")

    # gRPC Clients
    consensus_engine_endpoint: str = Field(default="consensus-engine.consensus-engine.svc.cluster.local:50051")
    orchestrator_endpoint: str = Field(default="orchestrator-dynamic.orchestrator-dynamic.svc.cluster.local:50051")
    analyst_agents_endpoint: str = Field(default="analyst-agents.analyst-agents.svc.cluster.local:50051")
    queen_agent_endpoint: str = Field(default="queen-agent.queen-agent.svc.cluster.local:50051")
    service_registry_endpoint: str = Field(default="service-registry.service-registry.svc.cluster.local:50051")
    grpc_timeout: int = Field(default=5, description="gRPC timeout in seconds")
    grpc_max_retries: int = Field(default=3, description="Max retries for gRPC calls")

    # MongoDB
    mongodb_uri: str = Field(default="mongodb://mongodb.mongodb.svc.cluster.local:27017")
    mongodb_database: str = Field(default="neural_hive")
    mongodb_optimization_collection: str = Field(default="optimization_ledger")
    mongodb_experiments_collection: str = Field(default="experiments_ledger")
    mongodb_insights_collection: str = Field(default="insights", description="MongoDB collection for insights")
    mongodb_max_pool_size: int = Field(default=100, description="Maximum MongoDB connections in pool")
    mongodb_min_pool_size: int = Field(default=10, description="Minimum MongoDB connections in pool")

    # Redis
    redis_cluster_nodes: str = Field(default="redis-cluster.redis.svc.cluster.local:6379")
    redis_password: str = Field(default="")
    redis_ssl_enabled: bool = Field(default=False)
    redis_cache_ttl: int = Field(default=300, description="Cache TTL in seconds")

    # MLflow
    mlflow_tracking_uri: str = Field(default="https://mlflow.mlflow.svc.cluster.local:5000")
    mlflow_tls_verify: bool = Field(default=True, description="Verificar certificado TLS do MLflow")
    mlflow_ca_bundle: Optional[str] = Field(default=None, description="Caminho para CA bundle do MLflow")
    mlflow_experiment_name: str = Field(default="optimizer-agents")

    # Argo Workflows
    argo_server_endpoint: str = Field(default="argo-server.argo.svc.cluster.local:2746")
    argo_namespace: str = Field(default="argo")
    argo_workflows_namespace: str = Field(default="argo")

    # Observability
    otel_endpoint: str = Field(default="https://opentelemetry-collector.observability.svc.cluster.local:4317")
    otel_tls_verify: bool = Field(default=True, description="Verificar certificado TLS do OTEL Collector")
    otel_ca_bundle: Optional[str] = Field(default=None, description="Caminho para CA bundle do OTEL Collector")
    prometheus_port: int = Field(default=8080)
    jaeger_sampling_rate: float = Field(default=1.0)

    # Optimization Config
    min_improvement_threshold: float = Field(default=0.05, description="Minimum improvement to apply optimization")
    max_weight_adjustment: float = Field(default=0.2, description="Max weight adjustment per iteration")
    max_slo_adjustment_percentage: float = Field(default=0.1, description="Max SLO adjustment percentage")
    experiment_timeout_seconds: int = Field(default=3600, description="Experiment timeout in seconds")
    enable_auto_approval: bool = Field(default=False, description="Enable auto-approval")
    require_queen_approval: bool = Field(default=True, description="Require Queen approval")
    rollback_on_degradation: bool = Field(default=True, description="Auto rollback on degradation")
    degradation_threshold: float = Field(default=0.05, description="Degradation threshold for rollback")
    learning_rate: float = Field(default=0.01, description="RL learning rate")
    exploration_rate: float = Field(default=0.1, description="Epsilon for epsilon-greedy")
    discount_factor: float = Field(default=0.95, description="RL discount factor")

    # Feature Flags
    enable_rl: bool = Field(default=True, description="Enable reinforcement learning")
    enable_bandits: bool = Field(default=True, description="Enable contextual bandits")
    enable_causal_analysis: bool = Field(default=True, description="Enable causal analysis")
    enable_experiments: bool = Field(default=True, description="Enable experiments")

    # ML Predictive Scheduling
    clickhouse_host: str = Field(default="clickhouse.clickhouse.svc.cluster.local", description="ClickHouse host")
    clickhouse_port: int = Field(default=9000, description="ClickHouse port")
    clickhouse_user: str = Field(default="default", description="ClickHouse user")
    clickhouse_password: str = Field(default="", description="ClickHouse password")
    clickhouse_database: str = Field(default="neural_hive", description="ClickHouse database")

    ml_load_forecast_horizons: List[int] = Field(default=[60, 360, 1440], description="Forecast horizons in minutes (1h, 6h, 24h)")
    ml_prophet_seasonality_mode: str = Field(default="additive", description="Prophet seasonality mode (additive/multiplicative)")
    ml_prophet_changepoint_prior_scale: float = Field(default=0.05, description="Prophet changepoint prior scale")

    ml_scheduling_epsilon: float = Field(default=0.1, description="Epsilon for scheduling RL exploration")
    ml_scheduling_learning_rate: float = Field(default=0.01, description="Learning rate for scheduling Q-learning")
    ml_scheduling_discount_factor: float = Field(default=0.95, description="Discount factor for scheduling RL")

    ml_training_interval_hours: int = Field(default=24, description="Interval for periodic model retraining (hours)")
    ml_training_window_days: int = Field(default=540, description="Training data window (18 months)")
    ml_min_training_samples: int = Field(default=1000, description="Minimum samples required for training")

    ml_model_cache_ttl_seconds: int = Field(default=3600, description="Model cache TTL (1 hour)")
    ml_forecast_cache_ttl_seconds: int = Field(default=300, description="Forecast cache TTL (5 minutes)")

    enable_load_prediction: bool = Field(default=True, description="Enable load prediction features")
    enable_scheduling_optimization: bool = Field(default=True, description="Enable scheduling optimization")

    # Configurações para Consensus Optimization (extensões gRPC)
    weight_cache_ttl_seconds: int = Field(default=300, description="TTL do cache de pesos no Redis")
    min_weight_value: float = Field(default=0.05, description="Valor mínimo permitido para peso de especialista")
    max_weight_value: float = Field(default=0.50, description="Valor máximo permitido para peso de especialista")

    # Configurações para Orchestrator Optimization (extensões gRPC)
    min_error_budget_percentage: float = Field(default=0.20, description="Mínimo error budget para aplicar SLO")
    slo_cache_ttl_seconds: int = Field(default=300, description="TTL do cache de SLOs no Redis")
    gradual_rollout_enabled: bool = Field(default=True, description="Habilitar rollout gradual de SLOs")
    min_slo_latency_ms: int = Field(default=100, description="Latência mínima permitida para SLO")
    min_slo_availability: float = Field(default=0.95, description="Disponibilidade mínima permitida para SLO")
    max_slo_error_rate: float = Field(default=0.10, description="Error rate máximo permitido para SLO")

    # Configuração RL para extensões
    rl_learning_rate: float = Field(default=0.1, description="Taxa de aprendizado do Q-learning para extensões")
    rl_discount_factor: float = Field(default=0.9, description="Fator de desconto do Q-learning para extensões")
    rl_exploration_rate: float = Field(default=0.1, description="Taxa de exploração (epsilon) para extensões")

    # SPIFFE/SPIRE Configuration (mTLS)
    spiffe_enabled: bool = Field(default=False, description="Habilitar integração SPIFFE/SPIRE")
    spiffe_enable_x509: bool = Field(default=False, description="Habilitar X.509-SVID para mTLS")
    spiffe_socket_path: str = Field(default="unix:///run/spire/sockets/agent.sock", description="SPIRE Workload API socket")
    spiffe_trust_domain: str = Field(default="neural-hive.local", description="SPIFFE trust domain")
    spiffe_jwt_audience: str = Field(default="neural-hive.local", description="JWT-SVID audience")
    spiffe_jwt_ttl_seconds: int = Field(default=3600, description="TTL do JWT-SVID em segundos")

    # A/B Testing Configuration
    ab_test_default_alpha: float = Field(default=0.05, description="Nivel de significancia padrao para testes A/B")
    ab_test_default_power: float = Field(default=0.80, description="Power estatistico padrao")
    ab_test_min_sample_size: int = Field(default=100, description="Tamanho minimo de amostra por grupo")
    ab_test_max_sample_size: int = Field(default=1000000, description="Tamanho maximo de amostra por grupo")
    ab_test_early_stopping_enabled: bool = Field(default=True, description="Habilitar parada antecipada por default")
    ab_test_sequential_testing_enabled: bool = Field(default=True, description="Habilitar sequential testing (SPRT)")
    ab_test_bayesian_analysis_enabled: bool = Field(default=True, description="Habilitar analise Bayesiana por default")
    ab_test_guardrail_check_interval_seconds: int = Field(default=30, description="Intervalo de verificacao de guardrails")
    ab_test_default_traffic_split: float = Field(default=0.5, description="Split de trafego padrao (50/50)")
    ab_test_max_duration_days: int = Field(default=30, description="Duracao maxima de experimentos em dias")
    ab_test_metrics_retention_days: int = Field(default=14, description="Dias de retencao de metricas no Redis")

    @field_validator("min_improvement_threshold", "max_weight_adjustment", "max_slo_adjustment_percentage")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Value must be positive")
        return v

    @field_validator("learning_rate", "exploration_rate", "discount_factor")
    @classmethod
    def validate_rate(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("Value must be between 0 and 1")
        return v

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'Settings':
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: MLflow, OTEL, Schema Registry, Prometheus.
        Endpoints internos do cluster (.svc.cluster.local) sao permitidos via HTTP.
        """
        is_prod_staging = self.environment.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []

        # Verifica MLflow - permite HTTP para servicos internos do cluster
        if self.mlflow_tracking_uri.startswith('http://'):
            # Permite HTTP para servicos internos do cluster
            if '.svc.cluster.local' not in self.mlflow_tracking_uri:
                http_endpoints.append(('mlflow_tracking_uri', self.mlflow_tracking_uri))

        # Verifica OTEL - permite HTTP para servicos internos do cluster
        if self.otel_endpoint.startswith('http://'):
            if '.svc.cluster.local' not in self.otel_endpoint:
                http_endpoints.append(('otel_endpoint', self.otel_endpoint))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.environment}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito. "
                "Endpoints internos do cluster (.svc.cluster.local) sao permitidos via HTTP."
            )

        return self


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
