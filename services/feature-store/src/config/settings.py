"""
Configuração do Feature Store Service

Gerencia todas as configurações usando Pydantic Settings com suporte a variáveis de ambiente.
"""

from typing import Optional, List
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

from neural_hive_security.cors import CORSConfig


class Settings(BaseSettings):
    """Configurações do Feature Store Service"""

    # Configuração da aplicação
    environment: str = Field(default='dev', description='Ambiente (dev, staging, production)')
    debug: bool = Field(default=False, description='Modo debug')
    log_level: str = Field(default='INFO', description='Nível de log')
    service_name: str = Field(default='feature-store', description='Nome do serviço')
    service_version: str = Field(default='1.0.0', description='Versão do serviço')

    # CORS - Feature store é API interna
    is_public_api: bool = Field(default=False, description='API pública requer CORS')

    @property
    def cors_origins(self) -> List[str]:
        """CORS origins dinâmicas por ambiente."""
        return CORSConfig.get_origins_for_environment(
            self.environment,
            is_public_api=self.is_public_api
        )

    # MongoDB configuration
    mongodb_uri: str = Field(
        default='mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017',
        description='URI do MongoDB'
    )
    mongodb_database: str = Field(default='neural_hive', description='Database do MongoDB')
    mongodb_features_collection: str = Field(
        default='feature_store',
        description='Collection para features'
    )
    mongodb_max_pool_size: int = Field(default=100, description='Tamanho máximo do pool')
    mongodb_timeout_ms: int = Field(default=5000, description='Timeout (ms)')

    # Redis configuration
    redis_url: str = Field(
        default='redis://redis.redis.svc.cluster.local:6379/0',
        description='URL do Redis'
    )
    redis_cache_ttl_seconds: int = Field(
        default=3600,
        description='TTL padrão para cache em segundos (1h)'
    )
    redis_max_connections: int = Field(default=50, description='Máximo de conexões')
    redis_socket_timeout: int = Field(default=5, description='Socket timeout (segundos)')
    redis_socket_connect_timeout: int = Field(default=5, description='Socket connect timeout')

    # Feature computation configuration
    enable_async_computation: bool = Field(
        default=True,
        description='Habilitar computação assíncrona de features'
    )
    computation_timeout_seconds: int = Field(
        default=30,
        description='Timeout para computação de features'
    )
    max_parallel_computations: int = Field(
        default=10,
        description='Máximo de computações paralelas'
    )

    # Feature validation
    validate_feature_schema: bool = Field(
        default=True,
        description='Validar schema de features'
    )
    allow_null_features: bool = Field(
        default=True,
        description='Permitir features nulas'
    )

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

    # Rate Limiting
    rate_limit_requests_per_minute: int = Field(
        default=200,
        description='Limite de requests por minuto'
    )

    @model_validator(mode='after')
    def validate_cors_in_production(self) -> 'Settings':
        """
        Valida que serviços públicos não usam wildcard CORS em produção.
        """
        is_prod = self.environment.lower() in ('production', 'prod')

        if not is_prod:
            return self

        # Valida que não tem wildcard nas origens
        CORSConfig.validate_no_wildcard(self.cors_origins, self.environment)

        return self

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'Settings':
        """
        Valida que endpoints HTTP críticos usam HTTPS em produção/staging.
        """
        is_prod_staging = self.environment.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        # Endpoints críticos que devem usar HTTPS em produção
        http_endpoints = []
        if self.otel_endpoint.startswith('http://'):
            http_endpoints.append(('otel_endpoint', self.otel_endpoint))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.environment}: {endpoint_list}. "
                "Use HTTPS em produção/staging para garantir segurança de dados em trânsito."
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
    """Obtém instância singleton das configurações"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
