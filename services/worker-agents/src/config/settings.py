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
    kafka_security_protocol: str = 'PLAINTEXT'
    kafka_sasl_mechanism: str = Field(default='SCRAM-SHA-512')
    kafka_sasl_username: Optional[str] = None
    kafka_sasl_password: Optional[str] = None
    kafka_ssl_ca_location: Optional[str] = None
    kafka_ssl_certificate_location: Optional[str] = None
    kafka_ssl_key_location: Optional[str] = None
    kafka_schema_registry_url: str = Field(
        default='http://schema-registry.neural-hive-kafka.svc.cluster.local:8081',
        description='URL do Schema Registry'
    )
    schemas_base_path: str = Field(
        default='/app/schemas',
        description='Diretório base para schemas Avro'
    )

    # Service Registry
    service_registry_host: str = 'localhost'
    service_registry_port: int = 50051
    heartbeat_interval_seconds: int = 30
    registration_retry_max_attempts: int = 5

    # Execution Ticket Service
    execution_ticket_service_url: str = 'http://localhost:8080'
    ticket_api_timeout_seconds: int = 10

    # Code Forge
    code_forge_url: str = 'http://code-forge.neural-hive-execution:8000'
    code_forge_timeout_seconds: int = 14400  # 4 hours
    code_forge_enabled: bool = True

    # GitOps / ArgoCD
    argocd_url: Optional[str] = None
    argocd_token: Optional[str] = None
    argocd_enabled: bool = False

    # OPA Validation
    opa_url: str = 'http://opa.neural-hive-governance:8181'
    opa_enabled: bool = True

    # SAST / Security
    trivy_enabled: bool = True
    trivy_timeout_seconds: int = 300

    # Test Execution
    test_execution_timeout_seconds: int = 600
    allowed_test_commands: List[str] = Field(
        default_factory=lambda: ['pytest', 'npm test', 'go test', 'mvn test']
    )

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

    # Vault Integration
    vault_enabled: bool = Field(default=False, description='Habilitar integração com Vault')
    vault_address: str = Field(
        default='http://vault.vault.svc.cluster.local:8200',
        description='Endereço do servidor Vault'
    )
    vault_kubernetes_role: str = Field(
        default='worker-agents',
        description='Role Kubernetes para autenticação Vault'
    )
    vault_token_path: str = Field(
        default='/vault/secrets/token',
        description='Caminho para arquivo de token Vault'
    )
    vault_mount_kv: str = Field(default='secret', description='Mount point do KV secrets')
    vault_fail_open: bool = Field(
        default=True,
        description='Fail-open em erros do Vault'
    )

    # SPIFFE/SPIRE Integration
    spiffe_enabled: bool = Field(default=False, description='Habilitar integração com SPIFFE')
    spiffe_socket_path: str = Field(
        default='unix:///run/spire/sockets/agent.sock',
        description='Caminho do socket da SPIRE Workload API'
    )
    spiffe_trust_domain: str = Field(
        default='neural-hive.local',
        description='Trust domain SPIFFE'
    )
    spiffe_jwt_audience: str = Field(
        default='vault.neural-hive.local',
        description='Audience para JWT-SVID'
    )

    def get_metadata(self) -> Dict[str, str]:
        '''Retorna metadata para registro no Service Registry'''
        metadata = {
            'namespace': self.namespace,
            'cluster': self.cluster,
            'version': self.service_version,
            'pod_name': os.getenv('POD_NAME', 'unknown'),
            'node_name': os.getenv('NODE_NAME', 'unknown'),
            'environment': self.environment
        }

        # Add SPIFFE ID if available
        if self.spiffe_enabled:
            spiffe_id = os.getenv('SPIFFE_ID', '')
            if spiffe_id:
                metadata['spiffe_id'] = spiffe_id

        return metadata

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False


@lru_cache()
def get_settings() -> WorkerAgentSettings:
    '''Retorna instância singleton de settings'''
    return WorkerAgentSettings()
