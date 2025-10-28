from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    '''Configurações do Consensus Engine'''

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )

    # Aplicação
    environment: str = Field(default='dev', description='Ambiente de execução')
    debug: bool = Field(default=False, description='Modo debug')
    log_level: str = Field(default='INFO', description='Nível de log')
    service_name: str = Field(default='consensus-engine', description='Nome do serviço')
    service_version: str = Field(default='1.0.0', description='Versão do serviço')

    # Kafka Consumer (plans.ready)
    kafka_bootstrap_servers: str = Field(..., description='Kafka bootstrap servers')
    kafka_consumer_group_id: str = Field(default='consensus-engine', description='Consumer group ID')
    kafka_plans_topic: str = Field(default='plans.ready', description='Tópico de planos cognitivos')
    kafka_auto_offset_reset: str = Field(default='earliest', description='Auto offset reset')
    kafka_enable_auto_commit: bool = Field(default=False, description='Auto commit offsets')
    kafka_security_protocol: str = Field(default='PLAINTEXT', description='Security protocol')
    kafka_sasl_mechanism: Optional[str] = Field(default=None, description='SASL mechanism')
    kafka_sasl_username: Optional[str] = Field(default=None, description='SASL username')
    kafka_sasl_password: Optional[str] = Field(default=None, description='SASL password')

    # Kafka Producer (plans.consensus)
    kafka_consensus_topic: str = Field(default='plans.consensus', description='Tópico de decisões consolidadas')
    kafka_enable_idempotence: bool = Field(default=True, description='Enable idempotence')
    kafka_transactional_id: Optional[str] = Field(default=None, description='Transactional ID')

    # gRPC Clients (Especialistas)
    specialist_business_endpoint: str = Field(
        default='specialist-business.specialist-business.svc.cluster.local:50051',
        description='Endpoint do Business Specialist'
    )
    specialist_technical_endpoint: str = Field(
        default='specialist-technical.specialist-technical.svc.cluster.local:50051',
        description='Endpoint do Technical Specialist'
    )
    specialist_behavior_endpoint: str = Field(
        default='specialist-behavior.specialist-behavior.svc.cluster.local:50051',
        description='Endpoint do Behavior Specialist'
    )
    specialist_evolution_endpoint: str = Field(
        default='specialist-evolution.specialist-evolution.svc.cluster.local:50051',
        description='Endpoint do Evolution Specialist'
    )
    specialist_architecture_endpoint: str = Field(
        default='specialist-architecture.specialist-architecture.svc.cluster.local:50051',
        description='Endpoint do Architecture Specialist'
    )
    grpc_timeout_ms: int = Field(default=5000, description='Timeout gRPC em milliseconds', gt=0)
    grpc_max_retries: int = Field(default=3, description='Máximo de retries gRPC', ge=0)

    # MongoDB (Ledger)
    mongodb_uri: str = Field(..., description='URI do MongoDB')
    mongodb_database: str = Field(default='neural_hive', description='Database MongoDB')
    mongodb_consensus_collection: str = Field(
        default='consensus_decisions',
        description='Collection de decisões consolidadas'
    )
    mongodb_pheromones_collection: str = Field(
        default='pheromone_signals',
        description='Collection de feromônios'
    )

    # Redis (Feromônios)
    redis_cluster_nodes: str = Field(..., description='Redis cluster nodes')
    redis_password: Optional[str] = Field(default=None, description='Redis password')
    redis_ssl_enabled: bool = Field(default=False, description='Redis SSL enabled')
    pheromone_ttl: int = Field(default=3600, description='TTL de feromônios em segundos', gt=0)
    pheromone_decay_rate: float = Field(
        default=0.1,
        description='Taxa de decay de feromônios por hora',
        ge=0.0,
        le=1.0
    )

    # Observabilidade
    otel_endpoint: str = Field(
        default='http://opentelemetry-collector.observability.svc.cluster.local:4317',
        description='Endpoint do OpenTelemetry Collector'
    )
    prometheus_port: int = Field(default=8080, description='Porta de métricas Prometheus', gt=0)
    jaeger_sampling_rate: float = Field(default=1.0, description='Taxa de sampling Jaeger', ge=0.0, le=1.0)

    # Consensus Configuration
    min_confidence_score: float = Field(
        default=0.8,
        description='Score mínimo de confiança obrigatório',
        ge=0.0,
        le=1.0
    )
    max_divergence_threshold: float = Field(
        default=0.05,
        description='Divergência máxima permitida (5%)',
        ge=0.0,
        le=1.0
    )
    high_risk_threshold: float = Field(
        default=0.7,
        description='Threshold de alto risco',
        ge=0.0,
        le=1.0
    )
    critical_risk_threshold: float = Field(
        default=0.9,
        description='Threshold de risco crítico',
        ge=0.0,
        le=1.0
    )
    bayesian_prior_weight: float = Field(
        default=0.1,
        description='Peso do prior Bayesiano',
        ge=0.0,
        le=1.0
    )
    voting_weight_decay: float = Field(
        default=0.95,
        description='Decay de pesos históricos',
        ge=0.0,
        le=1.0
    )
    require_unanimous_for_critical: bool = Field(
        default=True,
        description='Requer unanimidade para planos críticos'
    )
    fallback_to_deterministic: bool = Field(
        default=True,
        description='Usar fallback determinístico quando necessário'
    )

    # Feature Flags
    enable_bayesian_averaging: bool = Field(default=True, description='Habilitar Bayesian Averaging')
    enable_pheromones: bool = Field(default=True, description='Habilitar feromônios digitais')
    enable_fallback: bool = Field(default=True, description='Habilitar fallback determinístico')
    enable_parallel_invocation: bool = Field(default=True, description='Habilitar invocação paralela')

    @field_validator('grpc_timeout_ms', 'grpc_max_retries', 'pheromone_ttl', 'prometheus_port')
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('Valor deve ser positivo')
        return v

    @field_validator('kafka_bootstrap_servers', 'mongodb_uri', 'redis_cluster_nodes')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        if not v or v.strip() == '':
            raise ValueError('Valor não pode ser vazio')
        return v

    @field_validator('specialist_business_endpoint', 'specialist_technical_endpoint',
                     'specialist_behavior_endpoint', 'specialist_evolution_endpoint',
                     'specialist_architecture_endpoint')
    @classmethod
    def validate_endpoint_format(cls, v: str) -> str:
        if not v or ':' not in v:
            raise ValueError('Endpoint deve estar no formato host:port')
        return v


# Singleton
_settings = None


def get_settings() -> Settings:
    '''Retorna instância singleton das configurações'''
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
