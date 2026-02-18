from typing import List, Dict, Optional
from uuid import uuid4
from functools import lru_cache
from pydantic import Field, model_validator
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
        default_factory=lambda: ['BUILD', 'DEPLOY', 'TEST', 'VALIDATE', 'EXECUTE', 'COMPENSATE', 'QUERY']
    )
    # Service Registry capabilities (must match STE required_capabilities)
    # Includes: read, write, compute, analyze, transform, test, security, scan, compliance
    capabilities: List[str] = Field(
        default_factory=lambda: [
            'python', 'terraform', 'kubernetes',  # Original capabilities
            'read', 'write', 'compute',            # STE DAG capabilities
            'analyze', 'transform', 'test', 'code', # Additional capabilities (code added for STE compatibility)
            'security', 'scan', 'compliance'        # Security capabilities
        ]
    )
    max_concurrent_tasks: int = 5
    task_timeout_multiplier: float = 1.5

    # Backpressure Control
    max_concurrent_tickets: int = Field(
        default=10,
        description='Número máximo de tickets em processamento simultâneo (backpressure)'
    )
    consumer_pause_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description='Threshold para pausar consumer (% de max_concurrent_tickets)'
    )
    consumer_resume_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description='Threshold para resumir consumer (% de max_concurrent_tickets)'
    )

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
        default='https://schema-registry.kafka.svc.cluster.local:8081',
        description='URL do Schema Registry'
    )

    # Dead Letter Queue (DLQ)
    kafka_dlq_topic: str = Field(
        default='execution.tickets.dlq',
        description='Topico Kafka para Dead Letter Queue'
    )
    kafka_dlq_enabled: bool = Field(
        default=True,
        description='Habilitar consumo do DLQ'
    )
    kafka_max_retries_before_dlq: int = Field(
        default=3,
        description='Numero maximo de retries antes de enviar para DLQ'
    )
    schema_registry_tls_verify: bool = Field(default=True, description='Verificar certificado TLS do Schema Registry')
    schema_registry_ca_bundle: Optional[str] = Field(default=None, description='Caminho para CA bundle do Schema Registry')
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
    argocd_notifications_webhook: Optional[str] = None

    # GitOps / Flux CD
    flux_enabled: bool = False
    flux_namespace: str = 'flux-system'
    flux_kubeconfig_path: Optional[str] = None
    flux_timeout_seconds: int = 600

    # OPA Validation
    opa_url: str = 'http://opa.neural-hive-governance:8181'
    opa_enabled: bool = True
    opa_token: Optional[str] = None
    opa_timeout_seconds: int = 30
    opa_verify_ssl: bool = True
    opa_retry_attempts: int = 3
    opa_retry_backoff_base_seconds: int = 2
    opa_retry_backoff_max_seconds: int = 60
    opa_poll_interval_seconds: int = 5
    opa_poll_timeout_seconds: int = 300

    # SAST / Security
    trivy_enabled: bool = True
    trivy_timeout_seconds: int = 300

    # Test Execution
    test_execution_timeout_seconds: int = 600
    test_retry_attempts: int = 3
    allowed_test_commands: List[str] = Field(
        default_factory=lambda: ['pytest', 'npm test', 'go test', 'mvn test']
    )

    # GitHub Actions
    github_actions_enabled: bool = False
    github_api_url: str = 'https://api.github.com'
    github_token: Optional[str] = None
    github_actions_timeout_seconds: int = 900

    # GitLab CI
    gitlab_ci_enabled: bool = False
    gitlab_url: str = 'https://gitlab.com'
    gitlab_token: Optional[str] = None
    gitlab_timeout_seconds: int = 900
    gitlab_tls_verify: bool = True

    # Jenkins
    jenkins_enabled: bool = False
    jenkins_url: Optional[str] = None
    jenkins_user: Optional[str] = None
    jenkins_token: Optional[str] = None
    jenkins_timeout_seconds: int = 600
    jenkins_tls_verify: bool = True

    # Test report parsing
    junit_xml_enabled: bool = True
    coverage_report_enabled: bool = True

    # Validation providers
    sonarqube_enabled: bool = False
    sonarqube_url: Optional[str] = None
    sonarqube_token: Optional[str] = None
    sonarqube_timeout_seconds: int = 600
    snyk_enabled: bool = False
    snyk_token: Optional[str] = None
    checkov_enabled: bool = False
    checkov_timeout_seconds: int = 300

    # Temporal (opcional)
    temporal_host: str = 'temporal-frontend.temporal.svc.cluster.local'
    temporal_port: int = 7233
    temporal_namespace: str = 'default'
    temporal_task_queue: str = 'worker-tasks'
    enable_temporal_activities: bool = False

    # Retry & Resilience
    max_retries_per_ticket: int = 3
    retry_backoff_base_seconds: int = 2
    retry_backoff_max_seconds: int = 60
    code_forge_retry_attempts: int = 3
    dependency_check_interval_seconds: int = 5
    dependency_check_max_attempts: int = 60

    # Observabilidade
    otel_exporter_endpoint: str = 'https://opentelemetry-collector.observability.svc.cluster.local:4317'
    otel_tls_verify: bool = Field(default=True, description='Verificar certificado TLS do OTEL Collector')
    otel_ca_bundle: Optional[str] = Field(default=None, description='Caminho para CA bundle do OTEL Collector')
    prometheus_port: int = 9090
    http_port: int = 8080
    grpc_port: int = 0  # Worker-agents usa apenas HTTP, não gRPC
    log_level: str = 'INFO'

    # Istio/mTLS
    enable_mtls: bool = True
    mtls_cert_path: str = '/etc/certs/tls.crt'
    mtls_key_path: str = '/etc/certs/tls.key'

    # Vault Integration
    # As flags vault_enabled e spiffe_enabled são independentes; SPIFFE pode ser habilitado sem Vault para autenticação mTLS/JWT.
    vault_enabled: bool = Field(default=False, description='Habilitar integração com Vault')
    vault_address: str = Field(
        default='https://vault.vault.svc.cluster.local:8200',
        description='Endereço do servidor Vault'
    )
    vault_tls_verify: bool = Field(default=True, description='Verificar certificado TLS do Vault')
    vault_ca_bundle: Optional[str] = Field(default=None, description='Caminho para CA bundle do Vault')
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
    spiffe_jwt_ttl_seconds: int = Field(
        default=3600,
        description='TTL desejado (segundos) para JWT-SVIDs solicitados ao SPIRE Workload API'
    )
    spiffe_enable_x509: bool = Field(
        default=True,
        description='Habilitar X.509-SVID para mTLS'
    )
    spiffe_fallback_allowed: bool = Field(
        default=False,
        description='Permitir fallback insecure quando SPIFFE indisponível (apenas para desenvolvimento)'
    )

    # Scheduler Preemption (configuração do orchestrator compartilhada)
    scheduler_enable_preemption: bool = Field(
        default=False,
        description='Habilitar aceitação de chamadas de preempção do orchestrator via mTLS'
    )

    # Docker Runtime
    docker_enabled: bool = Field(default=False, description='Habilitar Docker Runtime')
    docker_base_url: str = Field(default='unix:///var/run/docker.sock', description='URL do Docker daemon')
    docker_timeout_seconds: int = Field(default=600, description='Timeout padrão para execuções Docker')
    docker_verify_ssl: bool = Field(default=True, description='Verificar SSL para conexões TCP')
    docker_default_cpu_limit: float = Field(default=1.0, description='Limite de CPU padrão em cores')
    docker_default_memory_limit: str = Field(default='512m', description='Limite de memória padrão')
    docker_network_mode: str = Field(default='bridge', description='Modo de rede padrão')
    docker_cleanup_containers: bool = Field(default=True, description='Remover containers após execução')

    # Kubernetes Jobs Runtime
    k8s_jobs_enabled: bool = Field(default=False, description='Habilitar K8s Jobs Runtime')
    k8s_jobs_namespace: str = Field(default='neural-hive-execution', description='Namespace para Jobs')
    k8s_jobs_kubeconfig_path: Optional[str] = Field(default=None, description='Caminho para kubeconfig')
    k8s_jobs_timeout_seconds: int = Field(default=600, description='Timeout padrão para Jobs')
    k8s_jobs_default_cpu_request: str = Field(default='100m', description='CPU request padrão')
    k8s_jobs_default_cpu_limit: str = Field(default='1000m', description='CPU limit padrão')
    k8s_jobs_default_memory_request: str = Field(default='128Mi', description='Memory request padrão')
    k8s_jobs_default_memory_limit: str = Field(default='512Mi', description='Memory limit padrão')
    k8s_jobs_service_account: str = Field(default='worker-agent-executor', description='ServiceAccount padrão')
    k8s_jobs_backoff_limit: int = Field(default=0, description='Número de retries do Job')
    k8s_jobs_cleanup: bool = Field(default=True, description='Deletar Jobs após execução')
    k8s_jobs_poll_interval_seconds: int = Field(default=5, description='Intervalo de polling do Job')

    # AWS Lambda Runtime
    lambda_enabled: bool = Field(default=False, description='Habilitar Lambda Runtime')
    lambda_region: str = Field(default='us-east-1', description='Região AWS')
    lambda_access_key: Optional[str] = Field(default=None, description='AWS Access Key')
    lambda_secret_key: Optional[str] = Field(default=None, description='AWS Secret Key')
    lambda_function_name: str = Field(default='neural-hive-executor', description='Nome da função Lambda')
    lambda_timeout_seconds: int = Field(default=900, description='Timeout máximo (max 900s)')

    # Local Runtime
    local_runtime_enabled: bool = Field(default=True, description='Habilitar Local Runtime (fallback)')
    local_runtime_timeout_seconds: int = Field(default=300, description='Timeout padrão')
    local_runtime_enable_sandbox: bool = Field(default=True, description='Habilitar validação de comandos')
    local_runtime_allowed_commands: List[str] = Field(
        default_factory=lambda: ['python', 'python3', 'node', 'bash', 'sh', 'terraform', 'kubectl', 'helm']
    )
    local_runtime_working_dir: str = Field(default='/tmp/neural-hive-execution', description='Diretório de trabalho')

    # Runtime Selection Strategy
    default_runtime: str = Field(default='local', description='Runtime padrão (k8s, docker, lambda, local)')
    runtime_fallback_chain: List[str] = Field(
        default_factory=lambda: ['k8s', 'docker', 'local', 'simulation'],
        description='Cadeia de fallback entre runtimes'
    )

    # Redis (para deduplicação de tickets)
    redis_url: Optional[str] = Field(default=None, description='URL completa do Redis (se fornecida, ignora host/port)')
    redis_host: str = Field(default='neural-hive-cache.redis-cluster.svc.cluster.local', description='Host do Redis')
    redis_port: int = Field(default=6379, description='Porta do Redis')
    redis_password: Optional[str] = Field(default=None, description='Senha do Redis')
    redis_ssl_enabled: bool = Field(default=False, description='Habilitar SSL para conexão Redis')
    redis_enabled: bool = Field(default=True, description='Habilitar deduplicação via Redis (fail-open se indisponível)')

    # MongoDB (para persistência de DLQ)
    mongodb_uri: str = Field(
        default='mongodb://mongodb.neural-hive-data.svc.cluster.local:27017',
        description='URI de conexão MongoDB'
    )
    mongodb_database: str = Field(default='neural_hive_workers', description='Nome do database MongoDB')
    mongodb_dlq_collection: str = Field(default='execution_tickets_dlq', description='Coleção para DLQ')
    mongodb_enabled: bool = Field(default=True, description='Habilitar MongoDB para persistência DLQ')
    mongodb_max_pool_size: int = Field(default=10, description='Tamanho máximo do pool de conexões')
    mongodb_server_selection_timeout_ms: int = Field(default=5000, description='Timeout seleção de servidor')

    # DLQ Alerting
    dlq_alert_kafka_topic: str = Field(
        default='sre.alerts',
        description='Tópico Kafka para alertas de DLQ'
    )
    dlq_alert_enabled: bool = Field(default=True, description='Habilitar alertas para mensagens DLQ')

    # DLQ Retry
    dlq_publish_max_retries: int = Field(default=3, description='Número máximo de retries para publicar no DLQ')
    dlq_publish_retry_backoff_base_seconds: float = Field(default=1.0, description='Base do backoff exponencial (segundos)')
    dlq_publish_retry_backoff_max_seconds: float = Field(default=30.0, description='Máximo do backoff exponencial (segundos)')

    # Neo4j (para queries de grafo - opcional)
    neo4j_enabled: bool = Field(default=False, description='Habilitar Neo4j para queries')
    neo4j_uri: str = Field(default='bolt://neo4j.neural-hive-data.svc.cluster.local:7687', description='URI de conexão Neo4j')
    neo4j_user: str = Field(default='neo4j', description='Usuário Neo4j')
    neo4j_password: Optional[str] = Field(default=None, description='Senha Neo4j')
    neo4j_database: str = Field(default='neo4j', description='Nome do banco Neo4j')
    neo4j_max_pool_size: int = Field(default=50, description='Tamanho máximo do pool de conexões Neo4j')
    neo4j_connection_timeout: int = Field(default=30, description='Timeout de conexão Neo4j (segundos)')
    neo4j_encrypted: bool = Field(default=False, description='Usar conexão criptografada Neo4j')

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

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'WorkerAgentSettings':
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: Schema Registry, OTEL, Vault.
        Excecao: URLs internas do cluster (.svc.cluster.local) sao permitidas com HTTP
        pois o trafego permanece dentro do cluster Kubernetes.
        """
        is_prod_staging = self.environment.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        def is_internal_cluster_url(url: str) -> bool:
            """Verifica se e URL interna do cluster Kubernetes."""
            return '.svc.cluster.local' in url or url.startswith('http://localhost')

        # Endpoints criticos que devem usar HTTPS em producao (exceto URLs internas)
        http_endpoints = []
        if self.kafka_schema_registry_url.startswith('http://') and not is_internal_cluster_url(self.kafka_schema_registry_url):
            http_endpoints.append(('kafka_schema_registry_url', self.kafka_schema_registry_url))
        if self.otel_exporter_endpoint.startswith('http://') and not is_internal_cluster_url(self.otel_exporter_endpoint):
            http_endpoints.append(('otel_exporter_endpoint', self.otel_exporter_endpoint))
        if self.vault_enabled and self.vault_address.startswith('http://') and not is_internal_cluster_url(self.vault_address):
            http_endpoints.append(('vault_address', self.vault_address))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.environment}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito."
            )

        return self

    @model_validator(mode='after')
    def validate_gitops_config(self) -> 'WorkerAgentSettings':
        """
        Valida configuração GitOps (ArgoCD e Flux).
        Garante que campos obrigatórios estão presentes quando habilitados.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Validar ArgoCD
        if self.argocd_enabled:
            if not self.argocd_url:
                raise ValueError(
                    "argocd_url obrigatório quando argocd_enabled=True"
                )
            if not self.argocd_token:
                raise ValueError(
                    "argocd_token obrigatório quando argocd_enabled=True"
                )
            # Validar formato de URL
            if not (self.argocd_url.startswith('http://') or self.argocd_url.startswith('https://')):
                raise ValueError(
                    f"argocd_url deve começar com http:// ou https://. Valor atual: '{self.argocd_url}'"
                )

        # Validar Flux
        if self.flux_enabled:
            if not self.flux_kubeconfig_path:
                raise ValueError(
                    "flux_kubeconfig_path obrigatório quando flux_enabled=True"
                )

        # Warning se ambos estão desabilitados (deploy executor usará fallback)
        if not self.argocd_enabled and not self.flux_enabled:
            logger.warning(
                "GitOps desabilitado: argocd_enabled=False e flux_enabled=False. "
                "Deploy executor usará fallback local."
            )

        return self

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False


@lru_cache()
def get_settings() -> WorkerAgentSettings:
    '''Retorna instância singleton de settings'''
    return WorkerAgentSettings()
