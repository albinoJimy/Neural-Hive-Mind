"""
Configuracao do Approval Service

Gerencia todas as configuracoes usando Pydantic Settings com suporte a variaveis de ambiente.
"""

from typing import Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuracoes do Approval Service"""

    # Configuracao da aplicacao
    environment: str = Field(default='dev', description='Ambiente (dev, staging, production)')
    debug: bool = Field(default=False, description='Modo debug')
    log_level: str = Field(default='INFO', description='Nivel de log')
    service_name: str = Field(default='approval-service', description='Nome do servico')
    service_version: str = Field(default='1.0.0', description='Versao do servico')

    # Kafka Consumer configuration
    kafka_bootstrap_servers: str = Field(..., description='Servidores Kafka bootstrap')
    kafka_consumer_group_id: str = Field(
        default='approval-service',
        description='ID do grupo de consumer Kafka'
    )
    kafka_approval_requests_topic: str = Field(
        default='cognitive-plans-approval-requests',
        description='Topico para requests de aprovacao'
    )
    kafka_approval_responses_topic: str = Field(
        default='cognitive-plans-approval-responses',
        description='Topico para responses de aprovacao'
    )
    kafka_auto_offset_reset: str = Field(default='earliest', description='Auto offset reset')
    kafka_enable_auto_commit: bool = Field(default=False, description='Enable auto commit')
    kafka_session_timeout_ms: int = Field(default=30000, description='Session timeout (ms)')
    kafka_max_poll_interval_ms: int = Field(default=300000, description='Max poll interval (ms)')

    # Kafka Producer configuration
    kafka_enable_idempotence: bool = Field(default=True, description='Habilitar idempotencia')
    kafka_transactional_id: Optional[str] = Field(None, description='ID transacional')

    # Kafka Security
    kafka_security_protocol: str = Field(default='PLAINTEXT', description='Protocolo de seguranca')
    kafka_sasl_mechanism: Optional[str] = Field(None, description='Mecanismo SASL')
    kafka_sasl_username: Optional[str] = Field(None, description='Usuario SASL')
    kafka_sasl_password: Optional[str] = Field(None, description='Senha SASL')

    # Schema Registry
    schema_registry_url: Optional[str] = Field(None, description='URL do Schema Registry')

    # MongoDB configuration
    mongodb_uri: str = Field(
        default='mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017',
        description='URI do MongoDB'
    )
    mongodb_database: str = Field(default='neural_hive', description='Database do MongoDB')
    mongodb_collection: str = Field(
        default='plan_approvals',
        description='Collection para aprovacoes'
    )
    mongodb_max_pool_size: int = Field(default=100, description='Tamanho maximo do pool')
    mongodb_timeout_ms: int = Field(default=5000, description='Timeout (ms)')

    # Feedback Collection Configuration (para ML continuous learning)
    enable_feedback_collection: bool = Field(
        default=True,
        description='Habilitar coleta de feedback para ML'
    )
    feedback_mongodb_collection: str = Field(
        default='specialist_feedback',
        description='Collection MongoDB para feedback'
    )
    mongodb_opinions_collection: str = Field(
        default='specialist_opinions',
        description='Collection do ledger cognitivo'
    )
    feedback_rating_min: float = Field(default=0.0, description='Rating minimo')
    feedback_rating_max: float = Field(default=1.0, description='Rating maximo')
    feedback_on_approval_failure_mode: str = Field(
        default='log_and_continue',
        description='Comportamento em falha de feedback: log_and_continue ou raise_error'
    )

    # Keycloak configuration
    keycloak_url: str = Field(
        default='http://keycloak.keycloak.svc.cluster.local:8080',
        description='URL do Keycloak'
    )
    keycloak_realm: str = Field(default='neural-hive', description='Realm do Keycloak')
    keycloak_client_id: str = Field(default='approval-service', description='Client ID')
    admin_role_name: str = Field(default='neural-hive-admin', description='Nome da role admin')
    require_auth: bool = Field(default=True, description='Require JWT authentication')

    # Observability configuration
    otel_endpoint: str = Field(
        default='https://opentelemetry-collector.observability.svc.cluster.local:4317',
        description='Endpoint do OpenTelemetry'
    )
    otel_tls_verify: bool = Field(
        default=True,
        description='Verificar certificado TLS do OTEL Collector'
    )
    prometheus_port: int = Field(default=8000, description='Porta do Prometheus metrics')
    jaeger_sampling_rate: float = Field(default=1.0, description='Taxa de amostragem Jaeger')

    # Rate Limiting
    rate_limit_requests_per_minute: int = Field(
        default=100,
        description='Limite de requests por minuto por usuario'
    )

    @field_validator('kafka_security_protocol')
    @classmethod
    def validate_security_in_production(cls, v, info):
        """Valida que seguranca esta habilitada em producao"""
        values = info.data
        if values.get('environment') == 'production' and v == 'PLAINTEXT':
            raise ValueError('Ambiente de producao requer conexao Kafka encriptada')
        return v

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'Settings':
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        """
        is_prod_staging = self.environment.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []
        if self.otel_endpoint.startswith('http://'):
            http_endpoints.append(('otel_endpoint', self.otel_endpoint))
        if self.keycloak_url.startswith('http://'):
            http_endpoints.append(('keycloak_url', self.keycloak_url))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.environment}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito."
            )

        return self

    model_config = {
        'env_file': '.env',
        'env_file_encoding': 'utf-8',
        'case_sensitive': False
    }


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Obtem instancia singleton das configuracoes"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
