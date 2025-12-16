from pydantic import Field, field_validator, model_validator
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
    grpc_timeout_ms: int = Field(
        default=5000,
        description='Timeout gRPC em milliseconds (env: GRPC_TIMEOUT_MS). '
                    'Default 5000ms para execuções locais/teste sem Kubernetes. '
                    'Em Kubernetes/produção, configurar 120000ms via variável de ambiente '
                    'GRPC_TIMEOUT_MS (injetada pelo Helm) para acomodar tempo de processamento '
                    'dos specialists (49-66s para ML inference).',
        gt=0
    )
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
    #
    # NOTA: Thresholds ajustados baseado em análise de produção (2025-12)
    # Valores anteriores (0.8 confidence, 0.05 divergence) eram muito restritivos,
    # causando 78% de rejeições mesmo com modelos saudáveis.
    #
    # Novos valores base refletem:
    # - Confiança típica de modelos ML em produção: 70-75%
    # - Divergência natural entre 5 specialists heterogêneos: 15-20%
    # - Margem para degradação parcial sem falsos positivos
    min_confidence_score: float = Field(
        default=0.65,  # Reduzido de 0.8 para 0.65 (65%)
        description='Score mínimo de confiança obrigatório. '
                    'Ajustado para 65% baseado em análise de produção. '
                    'Thresholds adaptativos podem relaxar até 50% quando modelos degradados.',
        ge=0.0,
        le=1.0
    )
    max_divergence_threshold: float = Field(
        default=0.25,  # Aumentado de 0.05 para 0.25 (25%)
        description='Divergência máxima permitida entre specialists. '
                    'Ajustado para 25% para acomodar variação natural entre 5 specialists. '
                    'Thresholds adaptativos podem relaxar até 35% quando modelos degradados.',
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

    # Configuração de Resiliência do Consumer
    # Estes parâmetros controlam o comportamento do consumer sob condições de erro,
    # incluindo backoff exponencial, circuit breaker e Dead Letter Queue.
    consumer_max_consecutive_errors: int = Field(
        default=10,
        description='Máximo de erros consecutivos antes do circuit breaker abrir. '
                    'Quando atingido, consumer para para evitar falhas em cascata.',
        gt=0
    )
    consumer_base_backoff_seconds: float = Field(
        default=1.0,
        description='Duração base para backoff exponencial (segundos). '
                    'Backoff = base * 2^erros_consecutivos, limitado ao máximo.',
        gt=0.0
    )
    consumer_max_backoff_seconds: float = Field(
        default=60.0,
        description='Limite máximo de backoff (segundos). '
                    'Previne esperas indefinidamente longas durante falhas sustentadas.',
        gt=0.0
    )
    consumer_poll_timeout_seconds: float = Field(
        default=1.0,
        description='Timeout do poll do consumer Kafka (segundos). '
                    'Controla tradeoff entre responsividade e frequência de polling.',
        gt=0.0
    )
    # NOTA: DLQ ainda não está implementado no consumer. Estas configurações são
    # reservadas para implementação futura. Não habilite consumer_enable_dlq em produção.
    consumer_enable_dlq: bool = Field(
        default=False,
        description='[NÃO IMPLEMENTADO] Habilitar Dead Letter Queue para mensagens que falham. '
                    'Reservado para implementação futura - não habilite em produção.'
    )
    kafka_dlq_topic: str = Field(
        default='plans.ready.dlq',
        description='[NÃO IMPLEMENTADO] Tópico Kafka para mensagens Dead Letter Queue.'
    )
    consumer_max_retries_before_dlq: int = Field(
        default=3,
        description='[NÃO IMPLEMENTADO] Máximo de retries antes de enviar mensagem para DLQ.',
        ge=0
    )

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

    @model_validator(mode='after')
    def validate_backoff_config(self) -> 'Settings':
        '''Valida consistência entre parâmetros de backoff do consumer.'''
        if self.consumer_max_backoff_seconds < self.consumer_base_backoff_seconds:
            raise ValueError(
                f'consumer_max_backoff_seconds ({self.consumer_max_backoff_seconds}) deve ser '
                f'>= consumer_base_backoff_seconds ({self.consumer_base_backoff_seconds})'
            )
        return self


# Singleton
_settings = None


def get_settings() -> Settings:
    '''Retorna instância singleton das configurações'''
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
