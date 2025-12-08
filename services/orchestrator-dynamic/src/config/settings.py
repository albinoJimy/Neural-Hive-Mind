"""
Configurações do serviço Orchestrator Dynamic usando Pydantic Settings.

NOTA: Este módulo usa Pydantic v2 com pydantic-settings.
- model_config substitui class Config (Pydantic v2)
- SettingsConfigDict para configuração de BaseSettings
"""
from typing import Optional
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    """Configurações do Orchestrator Dynamic."""

    # Configurações gerais
    service_name: str = Field(default='orchestrator-dynamic', description='Nome do serviço')
    service_version: str = Field(default='1.0.0', description='Versão do serviço')
    environment: str = Field(default='development', description='Ambiente de execução')
    log_level: str = Field(default='INFO', description='Nível de log')

    # Temporal
    temporal_enabled: bool = Field(
        default=True,
        description='Habilitar integração com Temporal (False = modo degradado sem workflows)'
    )
    temporal_host: str = Field(
        default='temporal-frontend.temporal.svc.cluster.local',
        description='Host do Temporal Server (pode incluir porta no formato host:port)'
    )
    temporal_port: int = Field(default=7233, description='Porta do Temporal Server (ignorada se host incluir porta)')
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
    kafka_sasl_mechanism: str = Field(default='SCRAM-SHA-512', description='Mecanismo SASL')
    kafka_sasl_username: Optional[str] = Field(default=None, description='Username SASL')
    kafka_sasl_password: Optional[str] = Field(default=None, description='Password SASL')
    kafka_ssl_ca_location: Optional[str] = Field(default=None, description='Caminho CA SSL')
    kafka_ssl_certificate_location: Optional[str] = Field(default=None, description='Caminho certificado SSL')
    kafka_ssl_key_location: Optional[str] = Field(default=None, description='Caminho chave SSL')

    # Kafka Producer (execution.tickets)
    kafka_tickets_topic: str = Field(default='execution.tickets', description='Tópico de tickets de execução')
    kafka_enable_idempotence: bool = Field(default=True, description='Habilitar idempotência')
    kafka_transactional_id: Optional[str] = Field(default=None, description='ID transacional')
    kafka_schema_registry_url: str = Field(
        default='http://schema-registry.neural-hive-kafka.svc.cluster.local:8081',
        description='URL do Schema Registry para serialização Avro'
    )
    schemas_base_path: str = Field(
        default='/app/schemas',
        description='Diretório base para schemas Avro'
    )

    # Self-Healing Engine
    self_healing_engine_url: str = Field(
        default='http://self-healing-engine:8080',
        description='Base URL do Self-Healing Engine'
    )
    self_healing_enabled: bool = Field(
        default=True,
        description='Flag para habilitar acionamento de autocura'
    )
    self_healing_timeout_seconds: int = Field(
        default=30,
        description='Timeout para chamadas HTTP ao Self-Healing Engine'
    )

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

    # Service Registry
    service_registry_host: str = Field(
        default='service-registry.neural-hive-execution.svc.cluster.local',
        description='Host do Service Registry'
    )
    service_registry_port: int = Field(default=50051, description='Porta gRPC do Service Registry')
    service_registry_timeout_seconds: int = Field(default=3, description='Timeout para chamadas gRPC')
    service_registry_max_results: int = Field(default=5, description='Máximo de workers retornados')
    service_registry_cache_ttl_seconds: int = Field(default=10, description='TTL do cache de descobertas')

    # Scheduler
    enable_intelligent_scheduler: bool = Field(default=True, description='Habilitar scheduler inteligente')
    scheduler_max_parallel_tickets: int = Field(default=100, description='Máximo de tickets paralelos')
    scheduler_priority_weights: dict = Field(
        default={'risk': 0.4, 'qos': 0.3, 'sla': 0.3},
        description='Pesos de priorização (risk, qos, sla)'
    )

    # SLA Tracking
    sla_default_timeout_ms: int = Field(default=3600000, description='Timeout padrão (1 hora)')
    sla_check_interval_seconds: int = Field(default=30, description='Intervalo de verificação de SLA')
    sla_alert_threshold_percent: float = Field(default=0.8, description='Threshold para alertas (80%)')

    # SLA Management System Integration
    sla_management_enabled: bool = Field(
        default=True,
        description='Habilitar integração com SLA Management System'
    )
    sla_management_host: str = Field(
        default='sla-management-system.neural-hive-orchestration.svc.cluster.local',
        description='Host do SLA Management System'
    )
    sla_management_port: int = Field(
        default=8000,
        description='Porta do SLA Management System'
    )
    sla_management_timeout_seconds: int = Field(
        default=5,
        description='Timeout para chamadas ao SLA Management System'
    )

    # Vault Integration
    vault_enabled: bool = Field(default=False, description='Habilitar integração com Vault')
    vault_address: str = Field(
        default='http://vault.vault.svc.cluster.local:8200',
        description='Endereço do servidor Vault'
    )
    vault_namespace: str = Field(default='', description='Namespace Vault')
    vault_auth_method: str = Field(default='kubernetes', description='Método de autenticação Vault')
    vault_kubernetes_role: str = Field(
        default='orchestrator-dynamic',
        description='Role Kubernetes para autenticação Vault'
    )
    vault_token_path: str = Field(
        default='/vault/secrets/token',
        description='Caminho para arquivo de token Vault (injetado pelo Agent)'
    )
    vault_mount_kv: str = Field(default='secret', description='Mount point do KV secrets')
    vault_mount_database: str = Field(default='database', description='Mount point do database secrets')
    vault_timeout_seconds: int = Field(default=5, description='Timeout para requisições Vault')
    vault_max_retries: int = Field(default=3, description='Número de tentativas de retry')
    vault_fail_open: bool = Field(
        default=True,
        description='Fail-open em erros do Vault (fallback para env vars)'
    )
    vault_token_renewal_threshold: float = Field(
        default=0.2,
        description='Threshold para renovação de token Vault (0.2 = renovar quando 80% do TTL foi consumido)'
    )
    vault_db_credentials_renewal_threshold: float = Field(
        default=0.2,
        description='Threshold para renovação de credenciais de DB (0.2 = renovar quando 80% do TTL foi consumido)'
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
    spiffe_enable_x509: bool = Field(
        default=False,
        description='Habilitar X.509-SVID para mTLS'
    )
    spiffe_environment: str = Field(
        default='development',
        description='Environment para política de fallback SPIFFE (development, staging, production)'
    )
    spiffe_fallback_allowed: bool = Field(
        default=False,
        description='Permitir fallback insecure quando SPIFFE indisponível (PERIGOSO - apenas desenvolvimento)'
    )
    sla_management_cache_ttl_seconds: int = Field(
        default=10,
        description='TTL do cache de budgets em Redis'
    )
    sla_budget_critical_threshold: float = Field(
        default=0.2,
        description='Threshold para alertas de budget crítico (20%)'
    )
    sla_deadline_warning_threshold: float = Field(
        default=0.8,
        description='Threshold para alertas de deadline (80%)'
    )

    # Optimizer Agents Integration (ML Predictive Scheduling)
    enable_optimizer_integration: bool = Field(
        default=False,
        description='Habilitar integração com Optimizer Agents para previsões ML remotas (Prophet/ARIMA + Q-learning RL). Dual-mode: remote + local fallback.'
    )
    optimizer_agents_endpoint: str = Field(
        default='optimizer-agents.neural-hive-estrategica.svc.cluster.local:50051',
        description='Endpoint gRPC do Optimizer Agents'
    )
    optimizer_grpc_timeout: int = Field(
        default=10,
        description='Timeout para chamadas gRPC ao Optimizer (segundos)'
    )
    optimizer_forecast_horizon_minutes: int = Field(
        default=60,
        description='Horizonte de previsão de carga em minutos'
    )

    # Local ML Load Prediction (Fallback Heurístico)
    ml_local_load_prediction_enabled: bool = Field(
        default=True,
        description='Habilitar preditor local de carga (fallback heurístico quando optimizer-agents indisponível)'
    )
    ml_local_load_cache_ttl_seconds: int = Field(
        default=30,
        description='TTL do cache Redis para predições locais de carga'
    )
    ml_local_load_window_minutes: int = Field(
        default=60,
        description='Janela de dados históricos para predição local (em minutos)'
    )
    ml_queue_prediction_weight: float = Field(
        default=0.2,
        description='Peso da predição de queue time no score composto de worker (0-1)'
    )
    ml_load_prediction_weight: float = Field(
        default=0.1,
        description='Peso da predição de carga no score composto de worker (0-1)'
    )
    ml_optimization_timeout_seconds: int = Field(
        default=2,
        description='Timeout para chamadas de otimização ML (local + remote)'
    )

    # ML Allocation Feedback Loop (para RL Training)
    ml_allocation_outcomes_enabled: bool = Field(
        default=True,
        description='Habilitar coleta de outcomes de alocação para feedback loop de RL'
    )
    ml_allocation_outcomes_topic: str = Field(
        default='ml.allocation_outcomes',
        description='Tópico Kafka para publicação de allocation outcomes (treinamento RL)'
    )
    sla_violations_topic: str = Field(
        default='sla.violations',
        description='Tópico Kafka para publicação de violações SLA formais'
    )
    sla_alerts_topic: str = Field(
        default='sla.alerts',
        description='Tópico Kafka para publicação de alertas proativos SLA'
    )
    sla_alert_deduplication_ttl_seconds: int = Field(
        default=300,
        description='TTL para deduplicação de alertas (5 minutos)'
    )
    sla_proactive_monitoring_enabled: bool = Field(
        default=False,
        description='Habilitar verificações proativas de SLA durante execução do workflow (C2/C4)'
    )
    sla_proactive_checkpoints: list = Field(
        default=['post_ticket_generation', 'post_ticket_publishing'],
        description='Checkpoints para verificações proativas de SLA'
    )

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

    # OPA Policy Engine
    opa_enabled: bool = Field(default=True, description='Habilitar validação de políticas OPA')
    opa_host: str = Field(
        default='opa.neural-hive-orchestration.svc.cluster.local',
        description='Host do OPA server'
    )
    opa_port: int = Field(default=8181, description='Porta do OPA server')
    opa_timeout_seconds: int = Field(default=2, description='Timeout para chamadas OPA')
    opa_retry_attempts: int = Field(default=3, description='Tentativas de retry')
    opa_cache_ttl_seconds: int = Field(default=30, description='TTL do cache de decisões')
    opa_fail_open: bool = Field(
        default=False,
        description='Fail-open em caso de erro OPA (False = fail-closed)'
    )

    # OPA Circuit Breaker
    opa_circuit_breaker_enabled: bool = Field(
        default=True,
        description='Habilitar circuit breaker para OPA (previne cascading failures)'
    )
    opa_circuit_breaker_failure_threshold: int = Field(
        default=5,
        description='Número de falhas consecutivas antes de abrir o circuito'
    )
    opa_circuit_breaker_reset_timeout: int = Field(
        default=60,
        description='Segundos antes de tentar fechar o circuito (half-open state)'
    )

    # OPA Policy Paths
    opa_policy_resource_limits: str = Field(
        default='neuralhive/orchestrator/resource_limits',
        description='Path da política de resource limits'
    )
    opa_policy_sla_enforcement: str = Field(
        default='neuralhive/orchestrator/sla_enforcement',
        description='Path da política de SLA enforcement'
    )
    opa_policy_feature_flags: str = Field(
        default='neuralhive/orchestrator/feature_flags',
        description='Path da política de feature flags'
    )

    # OPA Policy Parameters
    opa_max_concurrent_tickets: int = Field(
        default=100,
        description='Máximo de tickets concorrentes permitidos'
    )
    opa_allowed_capabilities: list = Field(
        default_factory=lambda: ['code_generation', 'deployment', 'testing', 'validation'],
        description='Capabilities permitidas'
    )
    opa_resource_limits: dict = Field(
        default_factory=lambda: {'max_cpu': '4000m', 'max_memory': '8Gi'},
        description='Limites de recursos'
    )

    # OPA Feature Flags
    opa_intelligent_scheduler_enabled: bool = Field(
        default=True,
        description='Habilitar intelligent scheduler'
    )
    opa_burst_capacity_enabled: bool = Field(
        default=True,
        description='Habilitar burst capacity'
    )
    opa_burst_threshold: float = Field(
        default=0.8,
        description='Threshold para burst capacity'
    )
    opa_predictive_allocation_enabled: bool = Field(
        default=False,
        description='Habilitar alocação preditiva'
    )
    opa_auto_scaling_enabled: bool = Field(
        default=False,
        description='Habilitar auto scaling'
    )
    opa_scheduler_namespaces: list = Field(
        default_factory=lambda: ['production', 'staging'],
        description='Namespaces para scheduler inteligente'
    )
    opa_premium_tenants: list = Field(
        default_factory=lambda: [],
        description='Tenants premium com prioridade'
    )

    # ML Predictions
    ml_predictions_enabled: bool = Field(
        default=True,
        description='Habilitar predições ML para tickets'
    )
    mlflow_tracking_uri: str = Field(
        default='http://mlflow.mlflow.svc.cluster.local:5000',
        description='MLflow tracking server URI'
    )
    mlflow_experiment_name: str = Field(
        default='orchestrator-predictive-models',
        description='Nome do experimento MLflow'
    )
    ml_training_window_days: int = Field(
        default=540,  # 18 meses, alinhado com Helm values.yaml
        description='Janela de dados de treino em dias (18 meses para capturar sazonalidade)'
    )
    ml_training_interval_hours: int = Field(
        default=24,
        description='Intervalo de retreinamento periódico em horas'
    )
    ml_min_training_samples: int = Field(
        default=100,
        description='Mínimo de amostras necessárias para treinamento'
    )
    ml_duration_error_threshold: float = Field(
        default=0.15,
        description='Erro máximo aceitável de predição de duração (15%)'
    )
    ml_anomaly_contamination: float = Field(
        default=0.05,
        description='Taxa esperada de anomalias (5%)'
    )
    ml_model_cache_ttl_seconds: int = Field(
        default=3600,
        description='TTL do cache de modelos (1 hora)'
    )
    ml_feature_cache_ttl_seconds: int = Field(
        default=3600,
        description='TTL do cache de estatísticas de features (1 hora)'
    )

    # Drift Detection
    ml_drift_detection_enabled: bool = Field(
        default=True,
        description='Habilitar detecção de drift de modelos'
    )
    ml_drift_check_window_days: int = Field(
        default=7,
        description='Janela de dados para drift detection em dias'
    )
    ml_drift_psi_threshold: float = Field(
        default=0.25,
        description='Threshold PSI para drift significativo'
    )
    ml_drift_mae_ratio_threshold: float = Field(
        default=1.5,
        description='Threshold de degradação de MAE (ratio atual/treino)'
    )
    ml_drift_ks_pvalue_threshold: float = Field(
        default=0.05,
        description='P-value threshold para K-S test (target drift)'
    )
    ml_drift_baseline_enabled: bool = Field(
        default=True,
        description='Salvar baseline de features durante treinamento'
    )

    # Training Job Configuration
    ml_training_job_timeout_seconds: int = Field(
        default=3600,
        description='Timeout para jobs de treinamento (1 hora)'
    )
    ml_training_job_memory_limit: str = Field(
        default='4Gi',
        description='Limite de memória para jobs de treinamento'
    )
    ml_training_job_cpu_limit: str = Field(
        default='2000m',
        description='Limite de CPU para jobs de treinamento'
    )
    ml_backfill_errors: bool = Field(
        default=False,
        description='Habilitar backfill de erros históricos durante treinamento'
    )
    ml_backfill_history_retention_days: int = Field(
        default=90,
        description='Retenção de histórico de backfill em dias'
    )

    # Prometheus Pushgateway (for CronJob metrics)
    prometheus_pushgateway_url: str = Field(
        default='http://prometheus-pushgateway.monitoring.svc.cluster.local:9091',
        description='URL do Prometheus Pushgateway'
    )

    # Pydantic v2: model_config substitui class Config
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',  # Ignorar variáveis de ambiente extras
    )


@lru_cache()
def get_settings() -> OrchestratorSettings:
    """
    Retorna instância singleton das configurações.
    Utiliza cache LRU para garantir que configurações sejam carregadas apenas uma vez.
    """
    return OrchestratorSettings()
