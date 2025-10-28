from typing import List, Dict, Optional
from uuid import uuid4
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings
import os


class WorkerAgentSettings(BaseSettings):
    '''Configurações do Worker Agent usando Pydantic Settings'''

    # Identificação
    service_name: str = 'worker-agents'
    service_version: str = '1.0.0'
    agent_id: str = Field(default_factory=lambda: str(uuid4()))
    namespace: str = 'neural-hive-execution'
    cluster: str = 'local'
    environment: str = 'production'

    # Capabilities
    supported_task_types: List[str] = Field(
        default_factory=lambda: ['BUILD', 'DEPLOY', 'TEST', 'VALIDATE', 'EXECUTE']
    )
    max_concurrent_tasks: int = 5
    task_timeout_multiplier: float = 1.5

    # Kafka
    kafka_bootstrap_servers: str = 'localhost:9092'
    kafka_tickets_topic: str = 'execution.tickets'
    kafka_results_topic: str = 'execution.results'
    kafka_consumer_group_id: str = 'worker-agents'
    kafka_auto_offset_reset: str = 'earliest'
    kafka_enable_auto_commit: bool = False

    # Service Registry
    service_registry_host: str = 'localhost'
    service_registry_port: int = 50051
    heartbeat_interval_seconds: int = 30
    registration_retry_max_attempts: int = 5

    # Execution Ticket Service
    execution_ticket_service_url: str = 'http://localhost:8080'
    ticket_api_timeout_seconds: int = 10

    # Temporal (opcional)
    temporal_host: str = 'temporal-frontend.temporal.svc.cluster.local'
    temporal_port: int = 7233
    temporal_namespace: str = 'neural-hive-mind'
    temporal_task_queue: str = 'worker-tasks'
    enable_temporal_activities: bool = False

    # Retry & Resilience
    max_retries_per_ticket: int = 3
    retry_backoff_base_seconds: int = 2
    retry_backoff_max_seconds: int = 60
    dependency_check_interval_seconds: int = 5
    dependency_check_max_attempts: int = 60

    # Observabilidade
    otel_exporter_endpoint: str = 'http://localhost:4317'
    prometheus_port: int = 9090
    http_port: int = 8080
    log_level: str = 'INFO'

    # Istio/mTLS
    enable_mtls: bool = True
    mtls_cert_path: str = '/etc/certs/tls.crt'
    mtls_key_path: str = '/etc/certs/tls.key'

    def get_metadata(self) -> Dict[str, str]:
        '''Retorna metadata para registro no Service Registry'''
        return {
            'namespace': self.namespace,
            'cluster': self.cluster,
            'version': self.service_version,
            'pod_name': os.getenv('POD_NAME', 'unknown'),
            'node_name': os.getenv('NODE_NAME', 'unknown'),
            'environment': self.environment
        }

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False


@lru_cache()
def get_settings() -> WorkerAgentSettings:
    '''Retorna instância singleton de settings'''
    return WorkerAgentSettings()
