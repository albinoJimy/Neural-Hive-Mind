"""
Base infrastructure settings for Neural Hive-Mind services.

Este módulo fornece classes base para configurações de infraestrutura
partilhadas por todos os serviços da plataforma.
"""

from functools import lru_cache
from typing import List, Optional, Union, Dict, Any
from urllib.parse import urlparse

import json
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseSettings):
    """Configurações base para Kafka."""

    kafka_bootstrap_servers: str = Field(
        ...,
        description='Kafka bootstrap servers (host:port[,host:port...])'
    )
    kafka_security_protocol: str = Field(
        default='PLAINTEXT',
        description='Security protocol: PLAINTEXT, SASL_SSL, SASL_PLAINTEXT'
    )
    kafka_sasl_mechanism: Optional[str] = Field(
        default=None,
        description='SASL mechanism: PLAIN, SCRAM-SHA-256, SCRAM-SHA-512'
    )
    kafka_sasl_username: Optional[str] = Field(
        default=None,
        description='SASL username'
    )
    kafka_sasl_password: Optional[str] = Field(
        default=None,
        description='SASL password'
    )
    kafka_auto_offset_reset: str = Field(
        default='earliest',
        description='Auto offset reset: earliest, latest, none'
    )
    kafka_enable_auto_commit: bool = Field(
        default=False,
        description='Enable auto-commit offsets'
    )
    kafka_enable_idempotence: bool = Field(
        default=True,
        description='Enable idempotent producer'
    )

    @field_validator('kafka_bootstrap_servers')
    @classmethod
    def validate_kafka_bootstrap(cls, v: str) -> str:
        if not v or ':' not in v:
            raise ValueError('kafka_bootstrap_servers deve estar no formato host:port')
        return v


class MongoDBSettings(BaseSettings):
    """Configurações base para MongoDB."""

    mongodb_uri: str = Field(
        ...,
        description='MongoDB connection URI (mongodb://[user:pass@]host:port[/db])'
    )
    mongodb_database: str = Field(
        default='neural_hive',
        description='Nome do database MongoDB'
    )

    @field_validator('mongodb_uri')
    @classmethod
    def validate_mongodb_uri(cls, v: str) -> str:
        if not v or not v.startswith(('mongodb://', 'mongodb+srv://')):
            raise ValueError('mongodb_uri deve começar com mongodb:// ou mongodb+srv://')
        return v


class RedisSettings(BaseSettings):
    """Configurações base para Redis."""

    redis_cluster_nodes: str = Field(
        ...,
        description='Redis cluster nodes (host:port ou comma-separated)'
    )
    redis_password: Optional[str] = Field(
        default=None,
        description='Redis password (obrigatório em produção)'
    )
    redis_ssl_enabled: bool = Field(
        default=False,
        description='Habilitar SSL/TLS para Redis'
    )

    @field_validator('redis_cluster_nodes')
    @classmethod
    def validate_redis_nodes(cls, v: str) -> str:
        if not v or ':' not in v:
            raise ValueError('redis_cluster_nodes deve estar no formato host:port')
        return v


class OpenTelemetrySettings(BaseSettings):
    """Configurações base para OpenTelemetry."""

    otel_endpoint: str = Field(
        default='https://opentelemetry-collector.observability.svc.cluster.local:4317',
        description='Endpoint do OpenTelemetry Collector (OTLP)'
    )
    otel_tls_verify: bool = Field(
        default=True,
        description='Verificar certificado TLS do OTEL Collector'
    )
    otel_ca_bundle: Optional[str] = Field(
        default=None,
        description='Caminho para CA bundle do OTEL Collector'
    )
    otel_service_name: Optional[str] = Field(
        default=None,
        description='Nome do serviço para OTEL (sobrescreve service_name)'
    )

    @field_validator('otel_endpoint')
    @classmethod
    def validate_otel_endpoint(cls, v: str) -> str:
        if not v:
            raise ValueError('otel_endpoint não pode ser vazio')
        return v


class GRPCSettings(BaseSettings):
    """Configurações base para clientes/servidores gRPC."""

    grpc_timeout_ms: int = Field(
        default=5000,
        description='Timeout padrão para chamadas gRPC (milissegundos)',
        gt=0
    )
    grpc_max_retries: int = Field(
        default=3,
        description='Número máximo de retries gRPC',
        ge=0
    )
    grpc_enable_retry: bool = Field(
        default=True,
        description='Habilitar retry policy gRPC'
    )
    grpc_max_message_length: int = Field(
        default=4 * 1024 * 1024,  # 4MB
        description='Tamanho máximo de mensagem gRPC (bytes)',
        gt=0
    )


class SPIFFESettings(BaseSettings):
    """Configurações base para SPIFFE/SPIRE mTLS."""

    spiffe_enabled: bool = Field(
        default=False,
        description='Habilitar autenticação via SPIFFE/SPIRE'
    )
    spiffe_enable_x509: bool = Field(
        default=False,
        description='Habilitar mTLS via SPIFFE X.509-SVID'
    )
    spiffe_socket_path: str = Field(
        default='unix:///run/spire/sockets/agent.sock',
        description='Caminho do socket da SPIRE Workload API'
    )
    spiffe_trust_domain: str = Field(
        default='neural-hive.local',
        description='Trust domain SPIFFE'
    )
    spiffe_jwt_audience: str = Field(
        default='neural-hive.local',
        description='Audience para validação de JWT-SVID'
    )
    spiffe_jwt_ttl_seconds: int = Field(
        default=3600,
        description='TTL do JWT-SVID em segundos',
        gt=0
    )


class VaultSettings(BaseSettings):
    """Configurações base para HashiCorp Vault."""

    vault_enabled: bool = Field(
        default=False,
        description='Habilitar integração com Vault'
    )
    vault_address: str = Field(
        default='https://vault.vault.svc.cluster.local:8200',
        description='Endereço do servidor Vault'
    )
    vault_tls_verify: bool = Field(
        default=True,
        description='Verificar certificado TLS do Vault'
    )
    vault_ca_bundle: Optional[str] = Field(
        default=None,
        description='Caminho para CA bundle do Vault'
    )
    vault_namespace: str = Field(
        default='',
        description='Namespace Vault (vazio para root)'
    )
    vault_auth_method: str = Field(
        default='kubernetes',
        description='Método de autenticação: kubernetes, token, github'
    )
    vault_kubernetes_role: str = Field(
        default='default',
        description='Role Kubernetes para autenticação Vault'
    )
    vault_mount_kv: str = Field(
        default='secret',
        description='Mount point do KV secrets engine'
    )
    vault_timeout_seconds: int = Field(
        default=5,
        description='Timeout para requisições Vault (segundos)',
        gt=0
    )
    vault_max_retries: int = Field(
        default=3,
        description='Número máximo de retries Vault',
        ge=0
    )
    vault_fail_open: bool = Field(
        default=False,
        description='Fail-open em erros do Vault (fallback para env vars)'
    )

    @field_validator('vault_fail_open')
    @classmethod
    def validate_vault_fail_open(cls, v: bool, info) -> bool:
        """Valida que fail_open só é True em desenvolvimento."""
        if not v:
            return v

        # Precisamos acessar environment de forma segura
        environment = getattr(info, 'data', {}).get('environment', 'development')

        allowed_environments = {'development', 'dev', 'local', 'test'}
        if environment.lower() not in allowed_environments:
            raise ValueError(
                f'vault_fail_open=True não é permitido em ambiente "{environment}". '
                f'Apenas {", ".join(sorted(allowed_environments))} permitem fail-open.'
            )
        return v


class ObservabilitySettings(BaseSettings):
    """Configurações base para observabilidade."""

    prometheus_port: int = Field(
        default=8080,
        description='Porta de métricas Prometheus',
        gt=0
    )
    jaeger_sampling_rate: float = Field(
        default=1.0,
        description='Taxa de sampling Jaeger/OTLP (0.0 a 1.0)',
        ge=0.0,
        le=1.0
    )
    enable_metrics: bool = Field(
        default=True,
        description='Habilitar métricas Prometheus'
    )
    enable_tracing: bool = Field(
        default=True,
        description='Habilitar tracing distribuído'
    )
    enable_logging: bool = Field(
        default=True,
        description='Habilitar logging estruturado'
    )


class BaseInfrastructureSettings(BaseSettings):
    """
    Configurações base para todos os serviços Neural Hive-Mind.

    Esta classe consolida configurações comuns que antes estavam
    duplicadas em cada serviço. Para usar, herde desta classe e
    adicione as configurações específicas do seu serviço.

    Exemplo:
        from neural_hive_infrastructure import BaseInfrastructureSettings

        class MyServiceSettings(BaseInfrastructureSettings):
            # Configurações específicas do serviço
            my_custom_feature_enabled: bool = True

        settings = MyServiceSettings()
    """

    # ===== Configurações da Aplicação =====
    environment: str = Field(
        default='development',
        description='Ambiente de execução: development, staging, production'
    )
    debug: bool = Field(
        default=False,
        description='Modo debug (verbose logging, reload)'
    )
    log_level: str = Field(
        default='INFO',
        description='Nível de log: DEBUG, INFO, WARNING, ERROR, CRITICAL'
    )
    service_name: str = Field(
        default='nhm-service',
        description='Nome do serviço'
    )
    service_version: str = Field(
        default='1.0.0',
        description='Versão do serviço (semver)'
    )

    # ===== Configurações de Rede =====
    grpc_port: int = Field(
        default=50051,
        description='Porta do servidor gRPC',
        gt=0
    )
    http_port: int = Field(
        default=8000,
        description='Porta do servidor HTTP/REST',
        gt=0
    )

    # ===== Configurações Kafka =====
    kafka_bootstrap_servers: str = Field(
        ...,
        description='Kafka bootstrap servers (host:port[,host:port...])'
    )
    kafka_security_protocol: str = Field(
        default='PLAINTEXT',
        description='Security protocol: PLAINTEXT, SASL_SSL, SASL_PLAINTEXT'
    )
    kafka_sasl_mechanism: Optional[str] = Field(
        default=None,
        description='SASL mechanism: PLAIN, SCRAM-SHA-256, SCRAM-SHA-512'
    )
    kafka_sasl_username: Optional[str] = Field(
        default=None,
        description='SASL username'
    )
    kafka_sasl_password: Optional[str] = Field(
        default=None,
        description='SASL password'
    )
    kafka_auto_offset_reset: str = Field(
        default='earliest',
        description='Auto offset reset: earliest, latest, none'
    )
    kafka_enable_auto_commit: bool = Field(
        default=False,
        description='Enable auto-commit offsets'
    )
    kafka_enable_idempotence: bool = Field(
        default=True,
        description='Enable idempotent producer'
    )

    # ===== Configurações MongoDB =====
    mongodb_uri: str = Field(
        ...,
        description='MongoDB connection URI (mongodb://[user:pass@]host:port[/db])'
    )
    mongodb_database: str = Field(
        default='neural_hive',
        description='Nome do database MongoDB'
    )

    # ===== Configurações Redis =====
    redis_cluster_nodes: str = Field(
        ...,
        description='Redis cluster nodes (host:port ou comma-separated)'
    )
    redis_password: Optional[str] = Field(
        default=None,
        description='Redis password (obrigatório em produção)'
    )
    redis_ssl_enabled: bool = Field(
        default=False,
        description='Habilitar SSL/TLS para Redis'
    )

    # ===== Configurações OpenTelemetry =====
    otel_endpoint: str = Field(
        default='https://opentelemetry-collector.observability.svc.cluster.local:4317',
        description='Endpoint do OpenTelemetry Collector (OTLP)'
    )
    otel_tls_verify: bool = Field(
        default=True,
        description='Verificar certificado TLS do OTEL Collector'
    )
    otel_ca_bundle: Optional[str] = Field(
        default=None,
        description='Caminho para CA bundle do OTEL Collector'
    )
    otel_service_name: Optional[str] = Field(
        default=None,
        description='Nome do serviço para OTEL (sobrescreve service_name)'
    )

    # ===== Configurações gRPC =====
    grpc_timeout_ms: int = Field(
        default=5000,
        description='Timeout padrão para chamadas gRPC (milissegundos)',
        gt=0
    )
    grpc_max_retries: int = Field(
        default=3,
        description='Número máximo de retries gRPC',
        ge=0
    )
    grpc_enable_retry: bool = Field(
        default=True,
        description='Habilitar retry policy gRPC'
    )

    # ===== Configurações Observabilidade =====
    prometheus_port: int = Field(
        default=8080,
        description='Porta de métricas Prometheus',
        gt=0
    )
    jaeger_sampling_rate: float = Field(
        default=1.0,
        description='Taxa de sampling Jaeger/OTLP (0.0 a 1.0)',
        ge=0.0,
        le=1.0
    )
    enable_metrics: bool = Field(
        default=True,
        description='Habilitar métricas Prometheus'
    )
    enable_tracing: bool = Field(
        default=True,
        description='Habilitar tracing distribuído'
    )

    # ===== Configurações SPIFFE/SPIRE =====
    spiffe_enabled: bool = Field(
        default=False,
        description='Habilitar autenticação via SPIFFE/SPIRE'
    )
    spiffe_enable_x509: bool = Field(
        default=False,
        description='Habilitar mTLS via SPIFFE X.509-SVID'
    )
    spiffe_socket_path: str = Field(
        default='unix:///run/spire/sockets/agent.sock',
        description='Caminho do socket da SPIRE Workload API'
    )
    spiffe_trust_domain: str = Field(
        default='neural-hive.local',
        description='Trust domain SPIFFE'
    )
    spiffe_jwt_audience: str = Field(
        default='neural-hive.local',
        description='Audience para validação de JWT-SVID'
    )

    # ===== Configurações Vault =====
    vault_enabled: bool = Field(
        default=False,
        description='Habilitar integração com Vault'
    )
    vault_address: str = Field(
        default='https://vault.vault.svc.cluster.local:8200',
        description='Endereço do servidor Vault'
    )
    vault_tls_verify: bool = Field(
        default=True,
        description='Verificar certificado TLS do Vault'
    )
    vault_namespace: str = Field(
        default='',
        description='Namespace Vault (vazio para root)'
    )
    vault_auth_method: str = Field(
        default='kubernetes',
        description='Método de autenticação: kubernetes, token, github'
    )
    vault_kubernetes_role: str = Field(
        default='default',
        description='Role Kubernetes para autenticação Vault'
    )
    vault_fail_open: bool = Field(
        default=False,
        description='Fail-open em erros do Vault (fallback para env vars)'
    )

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    # ===== Validators =====

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(
                f'log_level inválido: {v}. '
                f'Níveis válidos: {", ".join(sorted(valid_levels))}'
            )
        return v_upper

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid_envs = {'development', 'dev', 'staging', 'production', 'prod', 'test'}
        v_lower = v.lower()
        if v_lower not in valid_envs:
            raise ValueError(
                f'environment inválido: {v}. '
                f'Válidos: {", ".join(sorted(valid_envs))}'
            )
        return v_lower

    @field_validator('kafka_bootstrap_servers')
    @classmethod
    def validate_kafka_bootstrap(cls, v: str) -> str:
        if not v or ':' not in v:
            raise ValueError('kafka_bootstrap_servers deve estar no formato host:port')
        return v

    @field_validator('mongodb_uri')
    @classmethod
    def validate_mongodb_uri(cls, v: str) -> str:
        if not v or not v.startswith(('mongodb://', 'mongodb+srv://')):
            raise ValueError('mongodb_uri deve começar com mongodb:// ou mongodb+srv://')
        return v

    @field_validator('redis_cluster_nodes')
    @classmethod
    def validate_redis_nodes(cls, v: str) -> str:
        if not v or ':' not in v:
            raise ValueError('redis_cluster_nodes deve estar no formato host:port')
        return v

    @field_validator('vault_fail_open')
    @classmethod
    def validate_vault_fail_open(cls, v: bool, info) -> bool:
        """Valida que fail_open só é True em desenvolvimento."""
        if not v:
            return v

        environment = info.data.get('environment', 'development')

        allowed_environments = {'development', 'dev', 'local', 'test'}
        if environment.lower() not in allowed_environments:
            raise ValueError(
                f'vault_fail_open=True não é permitido em ambiente "{environment}". '
                f'Apenas {", ".join(sorted(allowed_environments))} permitem fail-open.'
            )
        return v

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'BaseInfrastructureSettings':
        """
        Valida que endpoints HTTP críticos usam HTTPS em produção/staging.

        Endpoints internos do cluster Kubernetes (.svc.cluster.local)
        são permitidos usar HTTP.
        """
        is_prod_staging = self.environment.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        def is_internal_cluster_endpoint(url: str) -> bool:
            internal_suffixes = (
                '.svc.cluster.local',
                '.svc.cluster',
                '.svc',
            )
            parsed = urlparse(url)
            hostname = parsed.hostname or ''
            return any(hostname.endswith(suffix) for suffix in internal_suffixes)

        # Verificar endpoints que devem usar HTTPS
        insecure_endpoints = []

        # OTEL endpoint
        otel_endpoint = str(self.otel_endpoint)
        if otel_endpoint.startswith('http://') and not is_internal_cluster_endpoint(otel_endpoint):
            insecure_endpoints.append(('otel_endpoint', otel_endpoint))

        # Vault address
        if self.vault_enabled:
            vault_address = str(self.vault_address)
            if vault_address.startswith('http://') and not is_internal_cluster_endpoint(vault_address):
                insecure_endpoints.append(('vault_address', vault_address))

        if insecure_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in insecure_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros em {self.environment}: {endpoint_list}. "
                "Use HTTPS em produção/staging. Endpoints internos (.svc.cluster.local) são permitidos."
            )

        return self

    @model_validator(mode='after')
    def validate_redis_password_in_production(self) -> 'BaseInfrastructureSettings':
        """Valida que redis_password está configurado em produção."""
        is_prod = self.environment.lower() in ('production', 'prod')
        if not is_prod:
            return self

        if not self.redis_password or self.redis_password == '':
            raise ValueError(
                'redis_password é obrigatório em ambiente production. '
                'Configure REDIS_PASSWORD com uma senha segura.'
            )

        return self

    def get_kafka_config(self) -> Dict[str, Any]:
        """Retorna configurações de Kafka como dict para uso com aiokafka."""
        config = {
            'bootstrap_servers': self.kafka_bootstrap_servers,
            'security_protocol': self.kafka_security_protocol,
            'auto_offset_reset': self.kafka_auto_offset_reset,
            'enable_auto_commit': self.kafka_enable_auto_commit,
        }

        if self.kafka_sasl_mechanism:
            config['sasl_mechanism'] = self.kafka_sasl_mechanism
            config['sasl_plain_username'] = self.kafka_sasl_username
            config['sasl_plain_password'] = self.kafka_sasl_password

        return config

    def get_mongodb_config(self) -> Dict[str, Any]:
        """Retorna configurações de MongoDB como dict."""
        return {
            'uri': self.mongodb_uri,
            'database': self.mongodb_database,
        }

    def get_redis_config(self) -> Dict[str, Any]:
        """Retorna configurações de Redis como dict."""
        return {
            'nodes': self.redis_cluster_nodes,
            'password': self.redis_password,
            'ssl': self.redis_ssl_enabled,
        }


# Singleton cache
_settings_cache: Dict[str, BaseInfrastructureSettings] = {}


def get_settings(
    settings_class: type = BaseInfrastructureSettings,
    force_reload: bool = False
) -> BaseInfrastructureSettings:
    """
    Retorna instância singleton das configurações.

    Args:
        settings_class: Classe de settings a instanciar
        force_reload: Força recarregamento do cache

    Returns:
        Instância das configurações

    Example:
        from neural_hive_infrastructure import get_settings, BaseInfrastructureSettings

        class MySettings(BaseInfrastructureSettings):
            my_custom_field: str = 'default'

        settings = get_settings(MySettings)
    """
    cache_key = settings_class.__name__

    if force_reload or cache_key not in _settings_cache:
        _settings_cache[cache_key] = settings_class()

    return _settings_cache[cache_key]
