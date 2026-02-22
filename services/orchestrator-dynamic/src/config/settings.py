"""
Configurações do serviço Orchestrator Dynamic usando Pydantic Settings.

NOTA: Este módulo usa Pydantic v2 com pydantic-settings.
- model_config substitui class Config (Pydantic v2)
- SettingsConfigDict para configuração de BaseSettings
"""
from typing import Optional, List
from functools import lru_cache
from pydantic import Field, field_validator, model_validator
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
    temporal_namespace: str = Field(default='default', description='Namespace Temporal')
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
        default='https://schema-registry.kafka.svc.cluster.local:8081',
        description='URL do Schema Registry para serialização Avro'
    )
    schema_registry_tls_verify: bool = Field(default=True, description='Verificar certificado TLS do Schema Registry')
    schema_registry_ca_bundle: Optional[str] = Field(default=None, description='Caminho para CA bundle do Schema Registry')
    schemas_base_path: str = Field(
        default='/app/schemas',
        description='Diretório base para schemas Avro'
    )

    # Self-Healing Engine
    self_healing_engine_url: str = Field(
        default='https://self-healing-engine.neural-hive.svc.cluster.local:8443',
        description='Base URL do Self-Healing Engine'
    )
    self_healing_tls_verify: bool = Field(default=True, description='Verificar certificado TLS do Self-Healing Engine')
    self_healing_ca_bundle: Optional[str] = Field(default=None, description='Caminho para CA bundle do Self-Healing Engine')
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
    MONGODB_MAX_POOL_SIZE: int = Field(default=100, ge=10, le=500)
    MONGODB_MIN_POOL_SIZE: int = Field(default=10, ge=5, le=50)

    # Redis (cache opcional)
    redis_cluster_nodes: str = Field(..., description='Nodes do cluster Redis')
    redis_password: Optional[str] = Field(
        default=None,
        description='Senha Redis. ⚠️ Obrigatório em produção (validação automática).'
    )
    redis_ssl_enabled: bool = Field(default=False, description='Habilitar SSL para Redis')

    @field_validator('redis_password')
    @classmethod
    def validate_redis_password_in_production(cls, v: Optional[str], info) -> Optional[str]:
        """
        Validar que redis_password não está vazio em produção.

        Em produção, Redis deve sempre ter autenticação habilitada.
        """
        environment = info.data.get('environment', 'development')

        if environment in ['production', 'prod']:
            if v is None or v == '':
                raise ValueError(
                    'redis_password não pode ser vazio em ambiente production. '
                    'Configure REDIS_PASSWORD com uma senha segura ou use External Secrets Operator. '
                    'Consulte docs/SECRETS_MANAGEMENT_GUIDE.md para melhores práticas.'
                )

        return v

    # Service Registry
    service_registry_host: str = Field(
        default='service-registry.neural-hive.svc.cluster.local',
        description='Host do Service Registry'
    )
    service_registry_port: int = Field(default=50051, description='Porta gRPC do Service Registry')
    service_registry_timeout_seconds: int = Field(default=3, description='Timeout para chamadas gRPC')
    service_registry_max_results: int = Field(default=5, description='Máximo de workers retornados')
    service_registry_cache_ttl_seconds: int = Field(default=10, description='TTL do cache de descobertas')

    # Scheduler
    enable_intelligent_scheduler: bool = Field(default=True, description='Habilitar scheduler inteligente')
    enable_ml_enhanced_scheduling: bool = Field(
        default=False,
        description='Habilitar ML-enhanced scheduling com modelos treinados (requer modelos em Production)'
    )
    scheduler_max_parallel_tickets: int = Field(default=100, description='Máximo de tickets paralelos')
    scheduler_priority_weights: dict = Field(
        default={'risk': 0.4, 'qos': 0.3, 'sla': 0.3},
        description='Pesos de priorização (risk, qos, sla)'
    )
    scheduler_fallback_stub_enabled: bool = Field(
        default=False,
        description=(
            'Permitir fallback stub quando Intelligent Scheduler falha (apenas desenvolvimento). '
            '⚠️ ATENÇÃO: Em produção, falhas no scheduler devem propagar exceção para retry. '
            'Stub silencioso pode mascarar problemas sistêmicos e causar alocações inadequadas.'
        )
    )

    @field_validator('scheduler_fallback_stub_enabled')
    @classmethod
    def validate_scheduler_fallback_stub_requires_dev_environment(cls, v: bool, info) -> bool:
        """
        Validar que scheduler_fallback_stub_enabled só pode ser True em ambientes de desenvolvimento.

        Em produção, falhas no scheduler devem propagar exceção para garantir
        que problemas sistêmicos sejam tratados adequadamente e não mascarados
        por alocações stub inadequadas.
        """
        if v is not True:
            return v

        environment = info.data.get('environment', '')

        # Ambientes permitidos para fallback stub
        allowed_environments = ['development', 'dev', 'local', 'test']

        if environment.lower() not in allowed_environments:
            raise ValueError(
                f'scheduler_fallback_stub_enabled=True não é permitido em ambiente "{environment}". '
                f'Apenas ambientes {allowed_environments} permitem fallback stub. '
                'Em produção, falhas no scheduler devem propagar exceção para retry. '
                'Configure SCHEDULER_FALLBACK_STUB_ENABLED=false ou ENVIRONMENT=development.'
            )

        return v

    # Affinity/Anti-Affinity Configuration
    scheduler_enable_affinity: bool = Field(
        default=True,
        description='Habilitar affinity/anti-affinity para alocação de tickets'
    )
    scheduler_affinity_plan_weight: float = Field(
        default=0.6,
        description='Peso de plan affinity no score (data locality)'
    )
    scheduler_affinity_anti_weight: float = Field(
        default=0.3,
        description='Peso de anti-affinity para tickets críticos (fault tolerance)'
    )
    scheduler_affinity_intent_weight: float = Field(
        default=0.1,
        description='Peso de intent affinity no score (workflow co-location)'
    )
    scheduler_affinity_plan_threshold: int = Field(
        default=3,
        description='Número de tickets para affinity máxima (3+ = score 1.0)'
    )
    scheduler_affinity_cache_ttl_seconds: int = Field(
        default=14400,
        description='TTL do cache de alocações em Redis (4 horas, alinhado com SLA)'
    )
    scheduler_affinity_anti_affinity_risk_bands: List[str] = Field(
        default=['critical', 'high'],
        description='Risk bands que ativam anti-affinity'
    )
    scheduler_affinity_anti_affinity_priorities: List[str] = Field(
        default=['CRITICAL', 'HIGH'],
        description='Priorities que ativam anti-affinity'
    )

    # Preemption Configuration
    scheduler_enable_preemption: bool = Field(
        default=False,
        description='Habilitar preempção de tasks de baixa prioridade por tasks de alta prioridade'
    )
    scheduler_preemption_min_preemptor_priority: str = Field(
        default='HIGH',
        description='Prioridade mínima para preemptar (HIGH ou CRITICAL)'
    )
    scheduler_preemption_max_preemptable_priority: str = Field(
        default='LOW',
        description='Prioridade máxima que pode ser preemptada (LOW ou MEDIUM)'
    )
    scheduler_preemption_grace_period_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        description='Período de graça para cancelamento graceful (checkpointing)'
    )
    scheduler_preemption_max_concurrent: int = Field(
        default=5,
        ge=1,
        le=20,
        description='Limite de preempções simultâneas'
    )
    scheduler_preemption_worker_cooldown_seconds: int = Field(
        default=60,
        ge=10,
        le=600,
        description='Cooldown de worker após preempção (evitar thrashing)'
    )
    scheduler_preemption_retry_preempted_tasks: bool = Field(
        default=True,
        description='Reagendar tasks preemptadas automaticamente'
    )
    scheduler_preemption_retry_delay_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description='Delay antes de reagendar task preemptada (5 minutos default)'
    )

    @model_validator(mode='after')
    def validate_affinity_weights(self) -> 'OrchestratorSettings':
        """
        Valida que os pesos de affinity somam 1.0 e estão no intervalo [0, 1].

        Pesos:
        - scheduler_affinity_plan_weight: peso de data locality
        - scheduler_affinity_anti_weight: peso de anti-affinity para tolerância a falhas
        - scheduler_affinity_intent_weight: peso de workflow co-location

        A soma deve ser 1.0 (com tolerância de 0.001) para garantir que
        o score de affinity seja normalizado corretamente.
        """
        weights = [
            ('scheduler_affinity_plan_weight', self.scheduler_affinity_plan_weight),
            ('scheduler_affinity_anti_weight', self.scheduler_affinity_anti_weight),
            ('scheduler_affinity_intent_weight', self.scheduler_affinity_intent_weight),
        ]

        # Validar que cada peso está no intervalo [0, 1]
        for name, weight in weights:
            if weight < 0.0 or weight > 1.0:
                raise ValueError(
                    f'{name}={weight} está fora do intervalo permitido [0.0, 1.0]. '
                    'Cada peso de affinity deve estar entre 0 e 1.'
                )

        # Validar que a soma é 1.0 (com tolerância)
        total = sum(w for _, w in weights)
        tolerance = 0.001
        if abs(total - 1.0) > tolerance:
            raise ValueError(
                f'A soma dos pesos de affinity ({total:.4f}) difere de 1.0. '
                f'Valores atuais: plan_weight={self.scheduler_affinity_plan_weight}, '
                f'anti_weight={self.scheduler_affinity_anti_weight}, '
                f'intent_weight={self.scheduler_affinity_intent_weight}. '
                'Ajuste os valores para que a soma seja exatamente 1.0.'
            )

        return self

    # ML Predictions
    ml_predictions_enabled: bool = Field(
        default=True,
        description="Habilita predições ML centralizadas"
    )
    mlflow_tracking_uri: str = Field(
        default="https://mlflow.mlflow.svc.cluster.local:5000",
        description="URI do servidor MLflow"
    )
    mlflow_tls_verify: bool = Field(default=True, description='Verificar certificado TLS do MLflow')
    mlflow_ca_bundle: Optional[str] = Field(default=None, description='Caminho para CA bundle do MLflow')
    ml_scheduling_model_type: str = Field(
        default="xgboost",
        description="Tipo de modelo para SchedulingPredictor"
    )
    ml_anomaly_model_type: str = Field(
        default="isolation_forest",
        description="Tipo de modelo para AnomalyDetector"
    )
    ml_load_forecast_horizons: List[int] = Field(
        default=[60, 360, 1440],
        description="Horizontes de forecast em minutos"
    )
    ml_forecast_cache_ttl_seconds: int = Field(
        default=300,
        description="TTL do cache de forecasts"
    )
    ml_drift_detection_enabled: bool = Field(
        default=True,
        description="Habilita detecção de drift"
    )

    # SLA Tracking
    sla_default_timeout_ms: int = Field(default=3600000, description='Timeout padrão (1 hora)')
    sla_check_interval_seconds: int = Field(default=30, description='Intervalo de verificação de SLA')
    sla_alert_threshold_percent: float = Field(default=0.8, description='Threshold para alertas (80%)')

    # SLA Ticket Timeout Configuration
    sla_ticket_min_timeout_ms: int = Field(
        default=60000,
        description=(
            'Timeout mínimo para tickets em milissegundos (60 segundos). '
            'Aumentado de 30s para 60s para reduzir falsos positivos de SLA violation. '
            'Ref: Análise de logs mostrou remaining_seconds=-8.5 antes de workflow completar.'
        )
    )
    sla_ticket_timeout_buffer_multiplier: float = Field(
        default=3.0,
        description=(
            'Multiplicador de buffer para cálculo de timeout (3.0x estimated_duration). '
            'Aumentado de 1.5x para 3.0x para acomodar variabilidade de execução. '
            'Fórmula: timeout_ms = max(min_timeout_ms, estimated_duration_ms * multiplier)'
        )
    )

    # SLA Management System Integration
    sla_management_enabled: bool = Field(
        default=True,
        description='Habilitar integração com SLA Management System'
    )
    sla_management_host: str = Field(
        default='sla-management-system.neural-hive.svc.cluster.local',
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
        default='https://vault.vault.svc.cluster.local:8200',
        description='Endereço do servidor Vault'
    )
    vault_tls_verify: bool = Field(default=True, description='Verificar certificado TLS do Vault')
    vault_ca_bundle: Optional[str] = Field(default=None, description='Caminho para CA bundle do Vault')
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
        default=False,
        description=(
            'Fail-open em erros do Vault (fallback para env vars); propagado para VaultConfig.fail_open. '
            '⚠️ ATENÇÃO: Deve ser False por default para garantir zero-trust security. '
            'Validação automática permite True apenas em environment=development ou local.'
        )
    )

    @field_validator('vault_fail_open')
    @classmethod
    def validate_vault_fail_open_requires_dev_environment(cls, v: bool, info) -> bool:
        """
        Validar que vault_fail_open só pode ser True em ambientes de desenvolvimento.

        Em qualquer ambiente que não seja explicitamente development/local,
        fail_open=True é inseguro pois permite operação com credenciais
        estáticas em caso de falha do Vault, violando princípios zero-trust.

        Esta validação é fail-closed por design: se o environment não for
        explicitamente configurado como dev/local, fail_open=True é bloqueado.
        """
        if v is not True:
            return v

        environment = info.data.get('environment', '')

        # Ambientes permitidos para fail_open=True
        allowed_environments = ['development', 'dev', 'local', 'test']

        if environment.lower() not in allowed_environments:
            raise ValueError(
                f'vault_fail_open=True não é permitido em ambiente "{environment}". '
                f'Apenas ambientes {allowed_environments} permitem fail_open. '
                'Configure VAULT_FAIL_OPEN=false ou ENVIRONMENT=development. '
                'O serviço deve usar fail-closed em produção/staging para segurança zero-trust.'
            )

        return v

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
    spiffe_jwt_ttl_seconds: int = Field(
        default=3600,
        description='TTL desejado (segundos) para JWT-SVIDs solicitados ao SPIRE Workload API'
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

    # gRPC Server para Queen Agent
    enable_grpc_server: bool = Field(
        default=True,
        description='Habilitar servidor gRPC para comandos estratégicos da Queen Agent'
    )
    grpc_server_port: int = Field(
        default=50053,
        description='Porta do servidor gRPC para comandos estratégicos'
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
        default=True,
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
    CIRCUIT_BREAKER_ENABLED: bool = Field(default=True, description='Habilitar circuit breaker global MongoDB')
    CIRCUIT_BREAKER_FAIL_MAX: int = Field(default=5, description='Falhas consecutivas para abrir circuito')
    CIRCUIT_BREAKER_TIMEOUT: int = Field(default=60, description='Tempo em segundos com circuito aberto')
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(default=30, description='Tempo em segundos para half-open')

    # Kafka Circuit Breaker
    KAFKA_CIRCUIT_BREAKER_ENABLED: bool = Field(default=True, description='Habilitar circuit breaker para Kafka Producer')
    KAFKA_CIRCUIT_BREAKER_FAIL_MAX: int = Field(default=5, description='Falhas consecutivas para abrir circuito Kafka')
    KAFKA_CIRCUIT_BREAKER_TIMEOUT: int = Field(default=60, description='Tempo em segundos com circuito Kafka aberto')
    KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(default=30, description='Tempo de recuperação do circuito Kafka')

    # Temporal Circuit Breaker
    TEMPORAL_CIRCUIT_BREAKER_ENABLED: bool = Field(default=True, description='Habilitar circuit breaker para Temporal Client')
    TEMPORAL_CIRCUIT_BREAKER_FAIL_MAX: int = Field(default=5, description='Falhas consecutivas para abrir circuito Temporal')
    TEMPORAL_CIRCUIT_BREAKER_TIMEOUT: int = Field(default=60, description='Tempo em segundos com circuito Temporal aberto')
    TEMPORAL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(default=30, description='Tempo de recuperação do circuito Temporal')

    # Redis Circuit Breaker
    REDIS_CIRCUIT_BREAKER_ENABLED: bool = Field(default=True, description='Habilitar circuit breaker para Redis Client')
    REDIS_CIRCUIT_BREAKER_FAIL_MAX: int = Field(default=5, description='Falhas consecutivas para abrir circuito Redis')
    REDIS_CIRCUIT_BREAKER_TIMEOUT: int = Field(default=60, description='Tempo em segundos com circuito Redis aberto')
    REDIS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(default=60, description='Tempo de recuperação do circuito Redis (maior para cache)')

    # MongoDB Persistence Policies
    MONGODB_FAIL_OPEN_EXECUTION_TICKETS: bool = Field(
        default=False,
        description='Permitir fail-open para persistência de execution tickets (não recomendado para compliance)'
    )
    MONGODB_FAIL_OPEN_VALIDATION_AUDIT: bool = Field(
        default=True,
        description='Permitir fail-open para auditoria de validação'
    )
    MONGODB_FAIL_OPEN_WORKFLOW_RESULTS: bool = Field(
        default=True,
        description='Permitir fail-open para resultados de workflow'
    )

    # Compensacao Automatica (Saga Pattern)
    compensation_enabled: bool = Field(
        default=True,
        description='Habilitar compensacao automatica quando workflows falham'
    )
    compensation_max_retries: int = Field(
        default=3,
        description='Maximo de tentativas para compensacao'
    )
    compensation_timeout_seconds: int = Field(
        default=60,
        description='Timeout para cada operacao de compensacao'
    )
    compensation_fail_open: bool = Field(
        default=False,
        description='Se True, falha na compensacao nao bloqueia workflow'
    )

    # Observabilidade
    otel_enabled: bool = Field(
        default=False,
        description='Habilitar OpenTelemetry tracing (False por default, True em prod/staging via Helm)'
    )
    otel_exporter_endpoint: str = Field(
        default='https://opentelemetry-collector.observability.svc.cluster.local:4317',
        description='Endpoint do OpenTelemetry Collector'
    )
    otel_tls_verify: bool = Field(default=True, description='Verificar certificado TLS do OTEL Collector')
    otel_ca_bundle: Optional[str] = Field(default=None, description='Caminho para CA bundle do OTEL Collector')
    otel_sampling_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description='Taxa de amostragem de traces (0.0-1.0). Default 1.0 (100%), configurar via Helm por ambiente.'
    )
    prometheus_port: int = Field(default=9090, description='Porta para métricas Prometheus')

    # OPA Policy Engine
    opa_enabled: bool = Field(default=True, description='Habilitar validação de políticas OPA')
    opa_host: str = Field(
        default='opa.neural-hive.svc.cluster.local',
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
    opa_policy_security_constraints: str = Field(
        default='neuralhive/orchestrator/security_constraints',
        description='Path da política de security constraints'
    )

    # OPA Security Parameters
    opa_security_enabled: bool = Field(
        default=True,
        description='Habilitar validação de security constraints'
    )
    opa_allowed_tenants: list = Field(
        default_factory=lambda: [],
        description='Whitelist de tenants permitidos (vazio = todos permitidos)'
    )
    opa_rbac_roles: dict = Field(
        default_factory=lambda: {
            'admin@example.com': ['admin'],
            'developer@example.com': ['developer'],
            'viewer@example.com': ['viewer']
        },
        description='Mapeamento de usuários para roles RBAC'
    )
    opa_data_residency_regions: list = Field(
        default_factory=lambda: ['us-east-1', 'us-west-2', 'eu-west-1'],
        description='Regiões permitidas para data residency'
    )
    opa_tenant_rate_limits: dict = Field(
        default_factory=lambda: {},
        description='Rate limits por tenant (req/min)'
    )
    opa_global_rate_limit: int = Field(
        default=1000,
        description='Rate limit global (req/min)'
    )
    opa_default_tenant_rate_limit: int = Field(
        default=100,
        description='Rate limit padrão para tenants sem configuração específica (fallback quando tenant_rate_limits não definido; se ausente, usa global)'
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
        default='https://mlflow.mlflow.svc.cluster.local:5000',
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
        default='https://prometheus-pushgateway.monitoring.svc.cluster.local:9091',
        description='URL do Prometheus Pushgateway'
    )
    pushgateway_tls_verify: bool = Field(default=True, description='Verificar certificado TLS do Prometheus Pushgateway')
    pushgateway_ca_bundle: Optional[str] = Field(default=None, description='Caminho para CA bundle do Prometheus Pushgateway')

    # ClickHouse Integration
    clickhouse_host: str = Field(
        default='clickhouse.clickhouse.svc.cluster.local',
        description='Host do servidor ClickHouse'
    )
    clickhouse_port: int = Field(default=9000, description='Porta do ClickHouse (native protocol)')
    clickhouse_database: str = Field(default='neural_hive_analytics', description='Database ClickHouse')
    clickhouse_user: str = Field(default='orchestrator', description='Usuário ClickHouse')
    clickhouse_password: str = Field(default='', description='Senha ClickHouse')
    ml_use_clickhouse_for_features: bool = Field(
        default=True,
        description='Usar ClickHouse para computar features históricas (mais rápido que MongoDB)'
    )

    # Re-training Triggers
    ml_retraining_triggers_enabled: bool = Field(
        default=True,
        description='Habilitar triggers automáticos de re-treinamento'
    )
    ml_drift_trigger_threshold: float = Field(
        default=0.25,
        description='Threshold PSI para trigger de re-treinamento por drift'
    )
    ml_performance_trigger_threshold: float = Field(
        default=1.5,
        description='Threshold de degradação de MAE (ratio atual/treino) para trigger'
    )
    ml_data_volume_trigger_threshold: int = Field(
        default=10000,
        description='Volume de novos dados para trigger de re-treinamento'
    )

    # Model Validation
    ml_validation_enabled: bool = Field(default=True, description='Habilitar validação de modelos')
    ml_validation_mae_threshold: float = Field(
        default=0.15,
        description='Threshold MAE (15%) para validação de DurationPredictor'
    )
    ml_validation_precision_threshold: float = Field(
        default=0.75,
        description='Threshold precision para validação de AnomalyDetector'
    )
    ml_auto_rollback_enabled: bool = Field(
        default=True,
        description='Habilitar rollback automático quando modelo novo performa pior'
    )

    # Continuous Validation Configuration
    ml_continuous_validation_enabled: bool = Field(
        default=True,
        description='Habilitar validação contínua de modelos em produção'
    )
    ml_validation_check_interval_seconds: int = Field(
        default=300,
        description='Intervalo entre checks de validação contínua (5 minutos)'
    )
    ml_validation_use_mongodb: bool = Field(
        default=True,
        description='Usar MongoDB como fonte primária de predições (fallback para in-memory)'
    )
    ml_validation_mongodb_collection: str = Field(
        default='model_predictions',
        description='Collection MongoDB para predições e actuals'
    )
    ml_validation_windows: List[str] = Field(
        default=['1h', '24h', '7d'],
        description='Janelas temporais para métricas agregadas'
    )
    ml_validation_alert_cooldown_minutes: int = Field(
        default=30,
        description='Cooldown entre alertas do mesmo tipo (evitar spam)'
    )
    ml_validation_latency_enabled: bool = Field(
        default=True,
        description='Habilitar coleta de métricas de latência (p50, p95, p99)'
    )
    ml_validation_r2_enabled: bool = Field(
        default=True,
        description='Habilitar cálculo de R² (coeficiente de determinação)'
    )

    # Canary Deployment
    ml_canary_enabled: bool = Field(
        default=False,
        description='Habilitar canary deployment para modelos ML'
    )
    ml_canary_traffic_percentage: float = Field(
        default=0.1,
        description='Percentual de tráfego para canary (10%)'
    )
    ml_canary_duration_minutes: int = Field(
        default=60,
        description='Duração do período de canary em minutos'
    )

    # Shadow Mode Configuration
    ml_shadow_mode_enabled: bool = Field(
        default=False,
        description='Habilitar shadow mode para validação de modelos antes de canary'
    )
    ml_shadow_mode_duration_minutes: int = Field(
        default=10080,  # 7 dias
        description='Duração do período de shadow mode em minutos (default: 7 dias)'
    )
    ml_shadow_mode_min_predictions: int = Field(
        default=1000,
        description='Mínimo de predições shadow antes de considerar válido'
    )
    ml_shadow_mode_agreement_threshold: float = Field(
        default=0.90,
        description='Threshold de agreement rate para passar shadow mode (90%)'
    )
    ml_shadow_mode_sample_rate: float = Field(
        default=1.0,
        description='Taxa de amostragem para shadow predictions (1.0 = 100%)'
    )
    ml_shadow_mode_persist_comparisons: bool = Field(
        default=True,
        description='Persistir comparações no MongoDB para análise'
    )
    ml_shadow_mode_circuit_breaker_enabled: bool = Field(
        default=True,
        description='Habilitar circuit breaker para falhas do modelo shadow'
    )
    ml_shadow_model_version: Optional[str] = Field(
        default=None,
        description='Versão específica do modelo shadow a ser usada (se None, usa versão mais recente em staging)'
    )

    # ML Audit Logging Configuration
    ml_audit_enabled: bool = Field(
        default=True,
        description='Habilitar audit logging para ciclo de vida de modelos ML'
    )
    ml_audit_log_collection: str = Field(
        default='model_audit_log',
        description='Nome da collection MongoDB para audit logs de modelos'
    )
    ml_audit_retention_days: int = Field(
        default=365,
        description='Retenção de audit logs em dias (TTL index)'
    )

    # Gradual Rollout Configuration
    ml_gradual_rollout_enabled: bool = Field(
        default=True,
        description='Habilitar gradual rollout com checkpoints para modelos ML'
    )
    ml_rollout_stages: List[float] = Field(
        default=[0.25, 0.50, 0.75, 1.0],
        description='Estágios de rollout progressivo (fração de tráfego em cada estágio)'
    )
    ml_checkpoint_duration_minutes: int = Field(
        default=30,
        description='Duração de cada checkpoint de rollout em minutos'
    )
    ml_checkpoint_mae_threshold_pct: float = Field(
        default=20.0,
        description='Threshold de aumento de MAE (%) para rollback em checkpoint'
    )
    ml_checkpoint_error_rate_threshold: float = Field(
        default=0.001,
        description='Threshold de error rate (0.1%) para rollback em checkpoint'
    )

    # Pydantic v2: model_config substitui class Config
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',  # Ignorar variáveis de ambiente extras
    )

    def _is_kubernetes_internal_service(self, url: str) -> bool:
        """
        Verifica se a URL é um serviço interno do Kubernetes.

        Serviços internos (*.svc.cluster.local ou *.svc.*) são permitidos em HTTP
        mesmo em produção, pois a comunicação entre pods já é segura no cluster.
        """
        return '.svc.cluster.local' in url or '.svc.' in url

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'OrchestratorSettings':
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: Schema Registry, MLflow, OTEL, Vault, Prometheus Pushgateway.

        NOTA: Endpoints internos do Kubernetes (*.svc.cluster.local) são permitidos em HTTP
        pois a comunicação entre pods já é segura por padrão no cluster.
        """
        is_prod_staging = self.environment.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao (exceto serviços internos K8s)
        http_endpoints = []
        if self.kafka_schema_registry_url.startswith('http://'):
            if not self._is_kubernetes_internal_service(self.kafka_schema_registry_url):
                http_endpoints.append(('kafka_schema_registry_url', self.kafka_schema_registry_url))
        if self.mlflow_tracking_uri.startswith('http://'):
            if not self._is_kubernetes_internal_service(self.mlflow_tracking_uri):
                http_endpoints.append(('mlflow_tracking_uri', self.mlflow_tracking_uri))
        if self.otel_exporter_endpoint.startswith('http://'):
            if not self._is_kubernetes_internal_service(self.otel_exporter_endpoint):
                http_endpoints.append(('otel_exporter_endpoint', self.otel_exporter_endpoint))
        if self.vault_enabled and self.vault_address.startswith('http://'):
            if not self._is_kubernetes_internal_service(self.vault_address):
                http_endpoints.append(('vault_address', self.vault_address))
        if self.prometheus_pushgateway_url.startswith('http://'):
            if not self._is_kubernetes_internal_service(self.prometheus_pushgateway_url):
                http_endpoints.append(('prometheus_pushgateway_url', self.prometheus_pushgateway_url))
        if self.self_healing_engine_url.startswith('http://'):
            if not self._is_kubernetes_internal_service(self.self_healing_engine_url):
                http_endpoints.append(('self_healing_engine_url', self.self_healing_engine_url))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.environment}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito. "
                "Servicos internos do Kubernetes (*.svc.cluster.local) sao permitidos em HTTP."
            )

        # Validar que shadow mode está habilitado se canary está habilitado
        if self.ml_canary_enabled and not self.ml_shadow_mode_enabled:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "canary_enabled_without_shadow_mode: "
                "Recomenda-se habilitar shadow mode antes de canary para validação mais segura"
            )

        return self


@lru_cache()
def get_settings() -> OrchestratorSettings:
    """
    Retorna instância singleton das configurações.
    Utiliza cache LRU para garantir que configurações sejam carregadas apenas uma vez.
    """
    return OrchestratorSettings()
