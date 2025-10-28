"""
Configurações do serviço Orchestrator Dynamic usando Pydantic Settings.
"""
from typing import Optional
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class OrchestratorSettings(BaseSettings):
    """Configurações do Orchestrator Dynamic."""

    # Configurações gerais
    service_name: str = Field(default='orchestrator-dynamic', description='Nome do serviço')
    service_version: str = Field(default='1.0.0', description='Versão do serviço')
    environment: str = Field(default='development', description='Ambiente de execução')
    log_level: str = Field(default='INFO', description='Nível de log')

    # Temporal
    temporal_host: str = Field(..., description='Host do Temporal Server')
    temporal_port: int = Field(default=7233, description='Porta do Temporal Server')
    temporal_namespace: str = Field(default='neural-hive-mind', description='Namespace Temporal')
    temporal_task_queue: str = Field(default='orchestration-tasks', description='Fila de tarefas Temporal')
    temporal_workflow_id_prefix: str = Field(default='orch-', description='Prefixo para workflow IDs')
    temporal_tls_enabled: bool = Field(default=False, description='Habilitar TLS para Temporal')

    # Kafka Consumer (plans.consensus)
    kafka_bootstrap_servers: str = Field(..., description='Servidores Kafka')
    kafka_consumer_group_id: str = Field(default='orchestrator-dynamic', description='Group ID do consumer')
    kafka_consensus_topic: str = Field(default='plans.consensus', description='Tópico de decisões consolidadas')
    kafka_auto_offset_reset: str = Field(default='earliest', description='Reset de offset')
    kafka_enable_auto_commit: bool = Field(default=False, description='Auto commit (manual para controle)')
    kafka_security_protocol: str = Field(default='PLAINTEXT', description='Protocolo de segurança Kafka')
    kafka_sasl_username: Optional[str] = Field(default=None, description='Username SASL')
    kafka_sasl_password: Optional[str] = Field(default=None, description='Password SASL')

    # Kafka Producer (execution.tickets)
    kafka_tickets_topic: str = Field(default='execution.tickets', description='Tópico de tickets de execução')
    kafka_enable_idempotence: bool = Field(default=True, description='Habilitar idempotência')
    kafka_transactional_id: Optional[str] = Field(default=None, description='ID transacional')

    # PostgreSQL (Temporal state store)
    postgres_host: str = Field(..., description='Host PostgreSQL')
    postgres_port: int = Field(default=5432, description='Porta PostgreSQL')
    postgres_database: str = Field(default='temporal', description='Database Temporal')
    postgres_user: str = Field(..., description='Usuário PostgreSQL')
    postgres_password: str = Field(..., description='Senha PostgreSQL')
    postgres_ssl_mode: str = Field(default='require', description='Modo SSL')

    # MongoDB (auditoria)
    mongodb_uri: str = Field(..., description='Connection string MongoDB')
    mongodb_database: str = Field(default='neural_hive_orchestration', description='Database MongoDB')
    mongodb_collection_tickets: str = Field(default='execution_tickets', description='Collection de tickets')
    mongodb_collection_workflows: str = Field(default='workflows', description='Collection de workflows')

    # Redis (cache opcional)
    redis_cluster_nodes: str = Field(..., description='Nodes do cluster Redis')
    redis_password: Optional[str] = Field(default=None, description='Senha Redis')
    redis_ssl_enabled: bool = Field(default=False, description='Habilitar SSL para Redis')

    # Scheduler
    enable_intelligent_scheduler: bool = Field(default=True, description='Habilitar scheduler inteligente')
    scheduler_max_parallel_tickets: int = Field(default=100, description='Máximo de tickets paralelos')
    scheduler_priority_weights: dict = Field(
        default={'critical': 1.0, 'high': 0.7, 'normal': 0.5, 'low': 0.3},
        description='Pesos de priorização por risk_band'
    )

    # SLA Tracking
    sla_default_timeout_ms: int = Field(default=3600000, description='Timeout padrão (1 hora)')
    sla_check_interval_seconds: int = Field(default=30, description='Intervalo de verificação de SLA')
    sla_alert_threshold_percent: float = Field(default=0.8, description='Threshold para alertas (80%)')

    # Retry Policies
    retry_max_attempts: int = Field(default=3, description='Máximo de tentativas')
    retry_initial_interval_ms: int = Field(default=1000, description='Intervalo inicial de retry')
    retry_backoff_coefficient: float = Field(default=2.0, description='Coeficiente de backoff exponencial')
    retry_max_interval_ms: int = Field(default=60000, description='Intervalo máximo de retry')

    # Observabilidade
    otel_exporter_endpoint: str = Field(
        default='http://otel-collector:4317',
        description='Endpoint do OpenTelemetry Collector'
    )
    prometheus_port: int = Field(default=9090, description='Porta para métricas Prometheus')

    class Config:
        """Configuração do Pydantic Settings."""
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False


@lru_cache()
def get_settings() -> OrchestratorSettings:
    """
    Retorna instância singleton das configurações.
    Utiliza cache LRU para garantir que configurações sejam carregadas apenas uma vez.
    """
    return OrchestratorSettings()
