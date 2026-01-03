"""
Configurações do Execution Ticket Service usando Pydantic Settings.
"""
from typing import Optional
from functools import lru_cache
from pydantic import Field, validator
from pydantic_settings import BaseSettings


class TicketServiceSettings(BaseSettings):
    """Configurações do Execution Ticket Service."""

    # Configurações gerais
    service_name: str = Field(default='execution-ticket-service', description='Nome do serviço')
    service_version: str = Field(default='1.0.0', description='Versão do serviço')
    environment: str = Field(default='development', description='Ambiente de execução')
    log_level: str = Field(default='INFO', description='Nível de log')

    # PostgreSQL (Primary Store)
    postgres_host: str = Field(..., description='Host do PostgreSQL')
    postgres_port: int = Field(default=5432, description='Porta do PostgreSQL')
    postgres_database: str = Field(default='neural_hive_tickets', description='Database PostgreSQL')
    postgres_user: str = Field(..., description='Usuário PostgreSQL')
    postgres_password: str = Field(..., description='Senha PostgreSQL')
    postgres_pool_size: int = Field(default=20, description='Tamanho do pool de conexões')
    postgres_max_overflow: int = Field(default=10, description='Overflow máximo do pool')
    postgres_ssl_mode: str = Field(default='require', description='Modo SSL PostgreSQL')

    # MongoDB (Audit Trail)
    mongodb_uri: str = Field(..., description='Connection string MongoDB')
    mongodb_database: str = Field(default='neural_hive_orchestration', description='Database MongoDB')
    mongodb_collection_tickets: str = Field(default='execution_tickets', description='Collection de tickets')
    mongodb_collection_audit: str = Field(default='ticket_audit_log', description='Collection de audit log')

    # Kafka Consumer
    kafka_bootstrap_servers: str = Field(..., description='Servidores Kafka')
    kafka_consumer_group_id: str = Field(default='execution-ticket-service', description='Group ID do consumer')
    kafka_tickets_topic: str = Field(default='execution.tickets', description='Tópico de tickets')
    kafka_auto_offset_reset: str = Field(default='earliest', description='Reset de offset')
    kafka_enable_auto_commit: bool = Field(default=False, description='Auto commit (manual para controle)')
    kafka_security_protocol: str = Field(default='PLAINTEXT', description='Protocolo de segurança Kafka')
    kafka_sasl_mechanism: str = Field(default='SCRAM-SHA-512', description='Mecanismo SASL')
    kafka_sasl_username: Optional[str] = Field(default=None, description='Username SASL')
    kafka_sasl_password: Optional[str] = Field(default=None, description='Password SASL')
    kafka_ssl_ca_location: Optional[str] = Field(default=None, description='Caminho CA SSL')
    kafka_ssl_certificate_location: Optional[str] = Field(default=None, description='Caminho certificado SSL')
    kafka_ssl_key_location: Optional[str] = Field(default=None, description='Caminho chave SSL')
    kafka_schema_registry_url: str = Field(
        default='http://schema-registry.neural-hive-kafka.svc.cluster.local:8081',
        description='URL do Schema Registry para deserialização Avro'
    )
    schemas_base_path: str = Field(
        default='/app/schemas',
        description='Diretório base dos schemas Avro'
    )

    # JWT Tokens
    jwt_secret_key: str = Field(..., description='Chave secreta JWT')
    jwt_algorithm: str = Field(default='HS256', description='Algoritmo JWT')
    jwt_token_expiration_seconds: int = Field(default=3600, description='Expiração do token (1 hora)')
    jwt_issuer: str = Field(default='neural-hive-mind', description='Issuer JWT')
    jwt_audience: str = Field(default='worker-agents', description='Audience JWT')

    # Webhooks
    webhook_enabled: bool = Field(default=True, description='Habilitar webhooks')
    webhook_timeout_seconds: int = Field(default=10, description='Timeout de webhooks')
    webhook_max_retries: int = Field(default=3, description='Máximo de retries')
    webhook_retry_backoff_seconds: int = Field(default=2, description='Backoff entre retries')
    webhook_batch_size: int = Field(default=10, description='Tamanho do batch de webhooks')
    webhook_worker_count: int = Field(default=5, description='Número de workers de webhooks')

    # gRPC Server
    grpc_port: int = Field(default=50052, description='Porta do servidor gRPC')
    grpc_max_workers: int = Field(default=10, description='Máximo de workers gRPC')
    grpc_max_concurrent_rpcs: int = Field(default=100, description='Máximo de RPCs concorrentes')

    # Observabilidade
    otel_exporter_endpoint: str = Field(
        default='http://otel-collector:4317',
        description='Endpoint do OpenTelemetry Collector'
    )
    prometheus_port: int = Field(default=9090, description='Porta de métricas Prometheus')
    jaeger_sampling_rate: float = Field(default=0.1, description='Taxa de sampling Jaeger')

    # Feature Flags
    enable_webhooks: bool = Field(default=True, description='Habilitar funcionalidade de webhooks')
    enable_jwt_tokens: bool = Field(default=True, description='Habilitar geração de tokens JWT')
    enable_audit_trail: bool = Field(default=True, description='Habilitar audit trail no MongoDB')
    enable_status_updates: bool = Field(default=True, description='Habilitar atualizações de status')

    # Connection retry configuration
    max_connection_retries: int = Field(default=5, description='Número máximo de tentativas de conexão')
    initial_retry_delay_seconds: float = Field(default=1.0, description='Delay inicial entre retries (exponential backoff)')

    @validator('environment')
    def validate_environment(cls, v):
        """Validar ambiente."""
        allowed = ['development', 'staging', 'production']
        if v not in allowed:
            raise ValueError(f'Environment must be one of {allowed}')
        return v

    @validator('jwt_secret_key')
    def validate_jwt_secret(cls, v, values):
        """Validar que JWT secret não seja padrão em produção."""
        if values.get('environment') == 'production' and v in ['changeme', 'default', 'secret']:
            raise ValueError('JWT secret key cannot be default value in production')
        return v

    @validator('webhook_timeout_seconds')
    def validate_webhook_timeout(cls, v):
        """Validar timeout de webhook."""
        if v > 30:
            raise ValueError('Webhook timeout cannot exceed 30 seconds')
        return v

    @validator('postgres_ssl_mode')
    def validate_ssl_in_production(cls, v, values):
        """Validar SSL habilitado em produção."""
        if values.get('environment') == 'production' and v == 'disable':
            raise ValueError('SSL must be enabled in production')
        return v

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False


@lru_cache()
def get_settings() -> TicketServiceSettings:
    """Retorna singleton de configurações."""
    return TicketServiceSettings()
