"""
Configuração base para especialistas neurais usando Pydantic.
"""

import os
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Optional, Literal
import structlog

logger = structlog.get_logger()


class SpecialistConfig(BaseSettings):
    """Configuração base para especialistas neurais."""

    # Identificação
    specialist_type: str = Field(..., description="Tipo do especialista")
    specialist_version: str = Field(default="1.0.0", description="Versão do especialista")
    service_name: str = Field(..., description="Nome do serviço")

    # Ambiente
    environment: str = Field(default="production", env="ENVIRONMENT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # MLflow
    mlflow_tracking_uri: str = Field(..., env="MLFLOW_TRACKING_URI")
    mlflow_experiment_name: str = Field(..., env="MLFLOW_EXPERIMENT_NAME", description="Nome do experimento MLflow")
    mlflow_model_name: str = Field(..., env="MLFLOW_MODEL_NAME", description="Nome do modelo registrado")
    mlflow_model_stage: str = Field(default="Production", env="MLFLOW_MODEL_STAGE", description="Stage do modelo")

    # MongoDB (Ledger)
    mongodb_uri: str = Field(..., env="MONGODB_URI")
    mongodb_database: str = Field(default="neural_hive", env="MONGODB_DATABASE")
    mongodb_opinions_collection: str = Field(default="specialist_opinions")
    mongodb_ledger_collection: str = Field(default="cognitive_ledger", env="MONGODB_LEDGER_COLLECTION")
    mongodb_feature_store_collection: str = Field(default="plan_features", env="MONGODB_FEATURE_STORE_COLLECTION")

    # Redis (Cache)
    redis_cluster_nodes: str = Field(..., env="REDIS_CLUSTER_NODES")
    redis_password: Optional[str] = Field(None, env="REDIS_PASSWORD")
    redis_ssl_enabled: bool = Field(default=False, env="REDIS_SSL_ENABLED")
    redis_cache_ttl: int = Field(default=300, description="TTL do cache em segundos")

    # Opinion Cache Configuration
    opinion_cache_enabled: bool = Field(default=True, env="OPINION_CACHE_ENABLED", description="Feature flag para habilitar cache de opinions")
    opinion_cache_ttl_seconds: int = Field(default=3600, env="OPINION_CACHE_TTL_SECONDS", description="TTL específico para cache de opinions (1 hora)")
    opinion_cache_key_prefix: str = Field(default="opinion:", env="OPINION_CACHE_KEY_PREFIX", description="Prefixo para chaves Redis de opinions")
    opinion_cache_max_size_mb: int = Field(default=100, env="OPINION_CACHE_MAX_SIZE_MB", description="Tamanho máximo do cache em MB")

    # OpenTelemetry Tracing Configuration
    enable_tracing: bool = Field(default=True, env="ENABLE_TRACING", description="Feature flag para habilitar/desabilitar tracing")
    otel_insecure: bool = Field(default=True, env="OTEL_INSECURE", description="Usar conexão insegura (sem TLS)")
    trace_sampling_rate: float = Field(default=1.0, env="TRACE_SAMPLING_RATE", description="Taxa de amostragem de traces (0.0 a 1.0)")
    trace_batch_size: int = Field(default=512, env="TRACE_BATCH_SIZE", description="Tamanho do batch para exportação")
    trace_export_timeout_ms: int = Field(default=30000, env="TRACE_EXPORT_TIMEOUT_MS", description="Timeout de exportação em ms")

    # Span Configuration
    enable_detailed_spans: bool = Field(default=True, env="ENABLE_DETAILED_SPANS", description="Habilitar spans detalhados por etapa")
    span_include_plan_content: bool = Field(default=False, env="SPAN_INCLUDE_PLAN_CONTENT", description="Incluir conteúdo do plano em spans (pode ser grande)")
    span_include_model_predictions: bool = Field(default=True, env="SPAN_INCLUDE_MODEL_PREDICTIONS", description="Incluir predições do modelo em spans")

    # Batch Evaluation Configuration
    batch_max_concurrency: int = Field(default=10, env="BATCH_MAX_CONCURRENCY", description="Concorrência máxima para batch evaluation")
    batch_timeout_seconds: int = Field(default=30, env="BATCH_TIMEOUT_SECONDS", description="Timeout total para batch")
    batch_enable_partial_results: bool = Field(default=True, env="BATCH_ENABLE_PARTIAL_RESULTS", description="Retornar resultados parciais se algumas avaliações falharem")

    # Warmup Configuration
    warmup_enabled: bool = Field(default=True, env="WARMUP_ENABLED", description="Feature flag para habilitar warmup automático")
    warmup_on_startup: bool = Field(default=True, env="WARMUP_ON_STARTUP", description="Executar warmup automaticamente no startup")
    warmup_dummy_plan_path: Optional[str] = Field(default=None, env="WARMUP_DUMMY_PLAN_PATH", description="Caminho para plano dummy customizado")
    startup_skip_warmup_on_dependency_failure: bool = Field(
        default=True,
        env="STARTUP_SKIP_WARMUP_ON_DEPENDENCY_FAILURE",
        description="Skip warmup se dependências críticas falharem (acelera startup em modo degradado)"
    )
    startup_dependency_check_timeout_seconds: int = Field(
        default=10,
        env="STARTUP_DEPENDENCY_CHECK_TIMEOUT_SECONDS",
        description="Timeout para verificação de dependências no startup"
    )

    # Neo4j (Knowledge Graph)
    neo4j_uri: str = Field(..., env="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", env="NEO4J_USER")
    neo4j_password: str = Field(..., env="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", env="NEO4J_DATABASE")

    # gRPC Server
    grpc_port: int = Field(default=50051, env="GRPC_PORT")
    grpc_max_workers: int = Field(default=10, env="GRPC_MAX_WORKERS")
    grpc_max_message_length: int = Field(default=4 * 1024 * 1024, description="4MB")

    # JWT Authentication
    jwt_secret_key: Optional[str] = Field(None, env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_token_expiration_seconds: int = Field(default=3600, description="Tempo de expiração do token JWT")
    jwt_issuer: Optional[str] = Field(default="neural-hive", env="JWT_ISSUER")
    jwt_audience: Optional[str] = Field(default="specialists", env="JWT_AUDIENCE")
    enable_jwt_auth: bool = Field(default=True, env="ENABLE_JWT_AUTH", description="Feature flag para habilitar/desabilitar autenticação JWT")
    jwt_public_endpoints: List[str] = Field(
        default=["HealthCheck", "/grpc.health.v1.Health/Check", "/grpc.health.v1.Health/Watch"],
        description="Métodos gRPC que não requerem autenticação (paths completos ou nomes de método)"
    )

    # HTTP Server (Health/Metrics)
    http_port: int = Field(default=8000, env="HTTP_PORT")

    # Observabilidade
    otel_endpoint: str = Field(
        default="http://opentelemetry-collector.observability.svc.cluster.local:4317",
        env="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    prometheus_port: int = Field(default=8080, env="PROMETHEUS_PORT")

    # Capacidades
    supported_domains: List[str] = Field(default_factory=list)
    supported_plan_versions: List[str] = Field(default=["1.0.0"])

    # Thresholds
    min_confidence_score: float = Field(default=0.8, description="Score mínimo de confiança")
    high_risk_threshold: float = Field(default=0.7, description="Threshold de alto risco")

    # Timeouts
    evaluation_timeout_ms: int = Field(default=5000, description="Timeout de avaliação")
    model_inference_timeout_ms: int = Field(default=3000, description="Timeout de inferência")

    # Circuit Breaker
    circuit_breaker_failure_threshold: int = Field(default=5, description="Número de falhas antes de abrir o circuito")
    circuit_breaker_recovery_timeout: int = Field(default=60, description="Segundos antes de tentar recuperação")
    circuit_breaker_expected_exception: type = Field(default=Exception, description="Tipo de exceção a rastrear")
    enable_circuit_breaker: bool = Field(default=True, description="Feature flag para habilitar/desabilitar circuit breakers")
    ledger_buffer_size: int = Field(default=100, description="Tamanho do buffer em memória para fallback do ledger")
    mlflow_cache_ttl_seconds: int = Field(default=3600, description="TTL para modelos em cache")

    # Feature Flags
    enable_explainability: bool = Field(default=True)
    enable_caching: bool = Field(default=True)
    enable_model_monitoring: bool = Field(default=True)
    use_semantic_fallback: bool = Field(
        default=True,
        env="USE_SEMANTIC_FALLBACK",
        description="Feature flag para usar SemanticPipeline como fallback ao invés de heurísticas"
    )
    enable_ledger: bool = Field(
        default=True,
        env="ENABLE_LEDGER",
        description="Feature flag para habilitar/desabilitar ledger persistence"
    )
    ledger_required: bool = Field(
        default=False,
        env="LEDGER_REQUIRED",
        description="Se True, falha fatal se ledger indisponível; se False, continua em modo degradado"
    )
    model_required: bool = Field(
        default=True,
        env="MODEL_REQUIRED",
        description="Se True, exige modelo ML carregado para SERVING; se False, permite modo heurístico sem modelo"
    )
    ledger_init_retry_attempts: int = Field(
        default=5,
        env="LEDGER_INIT_RETRY_ATTEMPTS",
        description="Número de tentativas de inicialização do ledger"
    )
    ledger_init_retry_max_wait_seconds: int = Field(
        default=30,
        env="LEDGER_INIT_RETRY_MAX_WAIT_SECONDS",
        description="Tempo máximo de espera entre retries (exponential backoff)"
    )

    # Ledger Digital Signature Configuration
    enable_digital_signature: bool = Field(
        default=True,
        env="ENABLE_DIGITAL_SIGNATURE",
        description="Habilitar assinatura digital de opiniões do ledger"
    )
    ledger_private_key_path: Optional[str] = Field(
        default=None,
        env="LEDGER_PRIVATE_KEY_PATH",
        description="Caminho para chave privada RSA (PEM) para assinatura digital"
    )
    ledger_public_key_path: Optional[str] = Field(
        default=None,
        env="LEDGER_PUBLIC_KEY_PATH",
        description="Caminho para chave pública RSA (PEM) para verificação"
    )
    ledger_key_size: int = Field(
        default=2048,
        env="LEDGER_KEY_SIZE",
        description="Tamanho da chave RSA em bits (2048 ou 4096)"
    )

    # Ledger Schema and Validation
    enable_schema_validation: bool = Field(
        default=True,
        env="ENABLE_SCHEMA_VALIDATION",
        description="Validar schema OpinionDocumentV2 antes de persistir"
    )
    ledger_schema_version: str = Field(
        default="2.0.0",
        env="LEDGER_SCHEMA_VERSION",
        description="Versão do schema do ledger cognitivo"
    )

    # Ledger Query API Configuration
    query_cache_ttl_seconds: int = Field(
        default=300,
        env="QUERY_CACHE_TTL_SECONDS",
        description="TTL do cache de queries semânticas (5 minutos)"
    )
    enable_query_api: bool = Field(
        default=True,
        env="ENABLE_QUERY_API",
        description="Habilitar LedgerQueryAPI para consultas semânticas"
    )

    # Explainability - Method Preference
    explainability_method_preference: Literal['auto', 'shap', 'lime', 'heuristic'] = Field(
        default='auto',
        env="EXPLAINABILITY_METHOD_PREFERENCE",
        description="Preferência de método de explicabilidade (auto usa auto-detecção)"
    )

    # Explainability - SHAP Configuration
    shap_background_dataset_path: Optional[str] = Field(
        default=None,
        env="SHAP_BACKGROUND_DATASET_PATH",
        description="Caminho para dataset de background SHAP (Parquet)"
    )
    shap_timeout_seconds: float = Field(
        default=5.0,
        env="SHAP_TIMEOUT_SECONDS",
        description="Timeout para computação SHAP"
    )
    shap_max_background_samples: int = Field(
        default=100,
        env="SHAP_MAX_BACKGROUND_SAMPLES",
        description="Número máximo de amostras do background dataset"
    )

    # Explainability - LIME Configuration
    lime_num_samples: int = Field(
        default=1000,
        env="LIME_NUM_SAMPLES",
        description="Número de amostras para perturbação LIME"
    )
    lime_timeout_seconds: float = Field(
        default=5.0,
        env="LIME_TIMEOUT_SECONDS",
        description="Timeout para computação LIME"
    )

    # Explainability - Narrative Configuration
    narrative_top_features: int = Field(
        default=5,
        env="NARRATIVE_TOP_FEATURES",
        description="Número de features mais importantes para narrativa"
    )
    narrative_language: str = Field(
        default="pt-BR",
        env="NARRATIVE_LANGUAGE",
        description="Idioma das narrativas (pt-BR, en-US)"
    )

    # Explainability - Ledger V2 Configuration
    explainability_ledger_version: str = Field(
        default="2.0.0",
        env="EXPLAINABILITY_LEDGER_VERSION",
        description="Versão do schema do ledger de explicabilidade"
    )
    enable_explainability_ledger_v2: bool = Field(
        default=True,
        env="ENABLE_EXPLAINABILITY_LEDGER_V2",
        description="Feature flag para usar ExplainabilityLedgerV2"
    )
    enable_legacy_explainability_persistence: bool = Field(
        default=True,
        env="ENABLE_LEGACY_EXPLAINABILITY_PERSISTENCE",
        description="Feature flag para escrever no ledger antigo (explainability_ledger)"
    )

    # Feature Store
    ontology_path: Optional[str] = Field(
        default=None,
        env="ONTOLOGY_PATH",
        description="Caminho para diretório de ontologias"
    )
    embeddings_model: str = Field(
        default="paraphrase-multilingual-MiniLM-L12-v2",
        env="EMBEDDINGS_MODEL",
        description="Modelo sentence-transformers para embeddings"
    )
    embedding_cache_enabled: bool = Field(
        default=True,
        env="EMBEDDING_CACHE_ENABLED",
        description="Habilitar cache de embeddings em memória"
    )
    embedding_cache_size: int = Field(
        default=1000,
        env="EMBEDDING_CACHE_SIZE",
        description="Tamanho máximo do cache LRU de embeddings"
    )
    embedding_cache_ttl_seconds: Optional[int] = Field(
        default=None,
        env="EMBEDDING_CACHE_TTL_SECONDS",
        description="TTL do cache de embeddings (None = sem expiração)"
    )
    embedding_batch_size: int = Field(
        default=32,
        env="EMBEDDING_BATCH_SIZE",
        description="Batch size para geração de embeddings"
    )
    semantic_similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Threshold de similaridade semântica para detecção de padrões (0.0-1.0)"
    )
    enable_feature_extraction: bool = Field(
        default=True,
        env="ENABLE_FEATURE_EXTRACTION",
        description="Feature flag para habilitar extração de features estruturadas"
    )

    # Drift Monitoring
    enable_drift_monitoring: bool = Field(
        default=True,
        env="ENABLE_DRIFT_MONITORING",
        description="Feature flag para habilitar monitoramento de drift"
    )
    drift_detection_window_hours: int = Field(
        default=24,
        env="DRIFT_DETECTION_WINDOW_HOURS",
        description="Janela de tempo para detecção de drift"
    )
    drift_threshold_psi: float = Field(
        default=0.2,
        env="DRIFT_THRESHOLD_PSI",
        description="Threshold PSI para alertar drift"
    )
    drift_reference_dataset_path: Optional[str] = Field(
        default=None,
        env="DRIFT_REFERENCE_DATASET_PATH",
        description="Caminho para dataset de referência para drift"
    )

    # Model Registry
    mlflow_model_signature_version: str = Field(
        default="1.0.0",
        env="MLFLOW_MODEL_SIGNATURE_VERSION",
        description="Versão do schema de input do modelo"
    )
    mlflow_enable_input_logging: bool = Field(
        default=True,
        env="MLFLOW_ENABLE_INPUT_LOGGING",
        description="Habilitar logging de inputs/outputs do modelo"
    )

    # Compliance & Data Governance
    enable_compliance_layer: bool = Field(
        default=True,
        env="ENABLE_COMPLIANCE_LAYER",
        description="Feature flag para habilitar compliance layer (PII detection, encryption, audit)"
    )
    enable_pii_detection: bool = Field(
        default=True,
        env="ENABLE_PII_DETECTION",
        description="Feature flag para detecção de PII com Presidio"
    )
    pii_detection_languages: List[str] = Field(
        default=['pt', 'en'],
        env="PII_DETECTION_LANGUAGES",
        description="Idiomas suportados para detecção de PII"
    )
    pii_entities_to_detect: List[str] = Field(
        default=['PERSON', 'EMAIL_ADDRESS', 'PHONE_NUMBER', 'CREDIT_CARD', 'IBAN_CODE', 'IP_ADDRESS', 'LOCATION', 'DATE_TIME'],
        env="PII_ENTITIES_TO_DETECT",
        description="Entidades PII a detectar (PERSON, EMAIL_ADDRESS, PHONE_NUMBER, etc.)"
    )
    pii_anonymization_strategy: str = Field(
        default='replace',
        env="PII_ANONYMIZATION_STRATEGY",
        description="Estratégia de anonimização: replace, mask, redact, hash"
    )
    enable_field_encryption: bool = Field(
        default=True,
        env="ENABLE_FIELD_ENCRYPTION",
        description="Feature flag para criptografia de campos sensíveis"
    )
    encryption_key_path: Optional[str] = Field(
        default=None,
        env="ENCRYPTION_KEY_PATH",
        description="Caminho para chave Fernet (gera automaticamente se não fornecido)"
    )
    fields_to_encrypt: List[str] = Field(
        default=['trace_id', 'span_id', 'intent_id'],
        env="FIELDS_TO_ENCRYPT",
        description="Campos a criptografar em opinião (correlation_id removido para permitir buscas via hash)"
    )
    enable_correlation_hash: bool = Field(
        default=True,
        env="ENABLE_CORRELATION_HASH",
        description="Habilitar hash SHA-256 de correlation_id para buscas (substitui criptografia direta)"
    )
    encryption_algorithm: str = Field(
        default='fernet',
        env="ENCRYPTION_ALGORITHM",
        description="Algoritmo de criptografia (fernet)"
    )
    enable_audit_logging: bool = Field(
        default=True,
        env="ENABLE_AUDIT_LOGGING",
        description="Feature flag para audit logging"
    )
    audit_log_collection: str = Field(
        default='compliance_audit_log',
        env="AUDIT_LOG_COLLECTION",
        description="Collection MongoDB para audit logs"
    )
    audit_log_retention_days: int = Field(
        default=730,
        env="AUDIT_LOG_RETENTION_DAYS",
        description="Retenção de audit logs em dias (2 anos por padrão)"
    )
    audit_events_to_log: List[str] = Field(
        default=['config_change', 'data_access', 'retention_action', 'pii_detection', 'encryption_operation'],
        env="AUDIT_EVENTS_TO_LOG",
        description="Tipos de eventos a auditar"
    )
    enable_automated_retention: bool = Field(
        default=False,
        env="ENABLE_AUTOMATED_RETENTION",
        description="Feature flag para retenção automática (requer scheduler)"
    )
    retention_policy_schedule_cron: str = Field(
        default='0 2 * * *',
        env="RETENTION_POLICY_SCHEDULE_CRON",
        description="Expressão cron para execução de retention policies"
    )
    default_retention_days: int = Field(
        default=365,
        env="DEFAULT_RETENTION_DAYS",
        description="Retenção padrão de documentos em dias"
    )

    # Business Metrics Configuration
    enable_business_metrics: bool = Field(
        default=True,
        env="ENABLE_BUSINESS_METRICS",
        description="Habilitar coleta de business metrics"
    )
    business_metrics_window_hours: int = Field(
        default=24,
        env="BUSINESS_METRICS_WINDOW_HOURS",
        description="Janela de tempo para cálculo de métricas (horas)"
    )
    business_metrics_collection_interval_minutes: int = Field(
        default=60,
        env="BUSINESS_METRICS_COLLECTION_INTERVAL_MINUTES",
        description="Intervalo de coleta de business metrics (minutos)"
    )
    consensus_mongodb_uri: Optional[str] = Field(
        default=None,
        env="CONSENSUS_MONGODB_URI",
        description="URI do MongoDB do Consensus Engine (usar mesmo do ledger se None)"
    )
    consensus_mongodb_database: str = Field(
        default='neural_hive',
        env="CONSENSUS_MONGODB_DATABASE",
        description="Database do Consensus Engine"
    )
    consensus_collection_name: str = Field(
        default='consensus_decisions',
        env="CONSENSUS_COLLECTION_NAME",
        description="Collection de decisões de consenso"
    )
    execution_ticket_api_url: Optional[str] = Field(
        default=None,
        env="EXECUTION_TICKET_API_URL",
        description="URL da API do execution-ticket-service"
    )
    enable_business_value_tracking: bool = Field(
        default=False,
        env="ENABLE_BUSINESS_VALUE_TRACKING",
        description="Habilitar tracking de valor de negócio (requer execution-ticket-service)"
    )

    # Anomaly Detection Configuration
    enable_anomaly_detection: bool = Field(
        default=True,
        env="ENABLE_ANOMALY_DETECTION",
        description="Habilitar detecção de anomalias em métricas"
    )
    anomaly_contamination: float = Field(
        default=0.1,
        env="ANOMALY_CONTAMINATION",
        description="Contamination parameter do Isolation Forest (0.0-0.5)"
    )
    anomaly_n_estimators: int = Field(
        default=100,
        env="ANOMALY_N_ESTIMATORS",
        description="Número de árvores do Isolation Forest"
    )
    anomaly_model_path: str = Field(
        default='/data/models/anomaly_detector_{specialist_type}.pkl',
        env="ANOMALY_MODEL_PATH",
        description="Caminho para modelo treinado (usa {specialist_type} como placeholder)"
    )
    anomaly_training_window_days: int = Field(
        default=30,
        env="ANOMALY_TRAINING_WINDOW_DAYS",
        description="Janela de dados históricos para treinamento (dias)"
    )
    anomaly_retrain_interval_days: int = Field(
        default=7,
        env="ANOMALY_RETRAIN_INTERVAL_DAYS",
        description="Intervalo de re-treinamento do modelo (dias)"
    )
    anomaly_alert_threshold: float = Field(
        default=-0.3,
        env="ANOMALY_ALERT_THRESHOLD",
        description="Threshold de anomaly score para alertar (valores negativos)"
    )

    # ============================================================================
    # Ensemble Configuration
    # ============================================================================
    enable_ensemble: bool = Field(
        default=False,
        env="ENABLE_ENSEMBLE",
        description="Feature flag para habilitar ensemble de múltiplos modelos"
    )
    ensemble_models: List[str] = Field(
        default_factory=list,
        env="ENSEMBLE_MODELS",
        description="Lista de nomes de modelos MLflow para ensemble (ex: ['technical-rf-model', 'technical-gb-model'])"
    )
    ensemble_stages: List[str] = Field(
        default_factory=lambda: ['Production'],
        env="ENSEMBLE_STAGES",
        description="Stages correspondentes aos modelos de ensemble (deve ter mesmo tamanho que ensemble_models)"
    )
    ensemble_weights: Optional[List[float]] = Field(
        default=None,
        env="ENSEMBLE_WEIGHTS",
        description="Pesos fixos para ensemble (deve somar 1.0). Se None, usar pesos iguais [1/N, 1/N, ...]"
    )
    ensemble_weights_source: str = Field(
        default='config',
        env="ENSEMBLE_WEIGHTS_SOURCE",
        description="Fonte dos pesos do ensemble: 'config' (usar ensemble_weights), 'mlflow_artifact', 'learned' (meta-modelo)"
    )
    ensemble_meta_model_name: Optional[str] = Field(
        default=None,
        env="ENSEMBLE_META_MODEL_NAME",
        description="Nome do meta-modelo MLflow que aprende pesos de ensemble (usado quando weights_source='learned')"
    )
    ensemble_aggregation_method: str = Field(
        default='weighted_average',
        env="ENSEMBLE_AGGREGATION_METHOD",
        description="Método de agregação: 'weighted_average', 'voting', 'stacking'"
    )
    ensemble_approve_threshold: float = Field(
        default=0.8,
        env="ENSEMBLE_APPROVE_THRESHOLD",
        description="Threshold de confiança para aprovar (usado em weighted_average e stacking)"
    )
    ensemble_review_threshold: float = Field(
        default=0.6,
        env="ENSEMBLE_REVIEW_THRESHOLD",
        description="Threshold de confiança para review (abaixo deste valor = reject)"
    )

    # ============================================================================
    # A/B Testing Configuration
    # ============================================================================
    enable_ab_testing: bool = Field(
        default=False,
        env="ENABLE_AB_TESTING",
        description="Feature flag para habilitar A/B testing de modelos"
    )
    ab_test_model_a_name: str = Field(
        default='',
        env="AB_TEST_MODEL_A_NAME",
        description="Nome do modelo A (baseline) no MLflow. Se vazio, usar mlflow_model_name"
    )
    ab_test_model_a_stage: str = Field(
        default='Production',
        env="AB_TEST_MODEL_A_STAGE",
        description="Stage do modelo A no MLflow Model Registry"
    )
    ab_test_model_b_name: str = Field(
        default='',
        env="AB_TEST_MODEL_B_NAME",
        description="Nome do modelo B (challenger) no MLflow"
    )
    ab_test_model_b_stage: str = Field(
        default='Staging',
        env="AB_TEST_MODEL_B_STAGE",
        description="Stage do modelo B no MLflow Model Registry"
    )
    ab_test_traffic_split: float = Field(
        default=0.9,
        env="AB_TEST_TRAFFIC_SPLIT",
        description="Porcentagem de tráfego para modelo A (0.0 a 1.0). Modelo B recebe (1 - traffic_split)"
    )
    ab_test_hash_seed: str = Field(
        default='neural-hive-ab-test',
        env="AB_TEST_HASH_SEED",
        description="Seed para hash determinístico de seleção de variante"
    )
    ab_test_duration_days: int = Field(
        default=7,
        env="AB_TEST_DURATION_DAYS",
        description="Duração planejada do teste em dias"
    )
    ab_test_success_metric: str = Field(
        default='consensus_agreement',
        env="AB_TEST_SUCCESS_METRIC",
        description="Métrica de sucesso: 'consensus_agreement', 'precision', 'f1_score'"
    )
    ab_test_minimum_sample_size: int = Field(
        default=100,
        env="AB_TEST_MINIMUM_SAMPLE_SIZE",
        description="Tamanho mínimo de amostra por variante antes de concluir teste"
    )

    # ClickHouse Configuration (para histórico de métricas)
    clickhouse_uri: Optional[str] = Field(
        default=None,
        env="CLICKHOUSE_URI",
        description="URI do ClickHouse para histórico de métricas"
    )
    clickhouse_database: str = Field(
        default='neural_hive',
        env="CLICKHOUSE_DATABASE",
        description="Database do ClickHouse"
    )
    enable_metrics_history: bool = Field(
        default=False,
        env="ENABLE_METRICS_HISTORY",
        description="Persistir histórico de métricas no ClickHouse"
    )

    # ============================================================================
    # Feedback Collection Configuration
    # ============================================================================
    enable_feedback_collection: bool = Field(
        default=True,
        env="ENABLE_FEEDBACK_COLLECTION",
        description="Habilitar coleta de feedback humano"
    )
    feedback_mongodb_collection: str = Field(
        default='specialist_feedback',
        env="FEEDBACK_MONGODB_COLLECTION",
        description="Collection MongoDB para armazenar feedback"
    )
    feedback_api_enabled: bool = Field(
        default=True,
        env="FEEDBACK_API_ENABLED",
        description="Habilitar endpoint REST de feedback"
    )
    feedback_require_authentication: bool = Field(
        default=True,
        env="FEEDBACK_REQUIRE_AUTHENTICATION",
        description="Requerer JWT para submissão de feedback"
    )
    feedback_allowed_roles: List[str] = Field(
        default=['admin', 'specialist_reviewer', 'human_expert'],
        env="FEEDBACK_ALLOWED_ROLES",
        description="Roles permitidos para submeter feedback"
    )
    feedback_rating_min: float = Field(
        default=0.0,
        env="FEEDBACK_RATING_MIN",
        description="Rating mínimo permitido"
    )
    feedback_rating_max: float = Field(
        default=1.0,
        env="FEEDBACK_RATING_MAX",
        description="Rating máximo permitido"
    )

    # ============================================================================
    # Retraining Trigger Configuration
    # ============================================================================
    enable_retraining_trigger: bool = Field(
        default=True,
        env="ENABLE_RETRAINING_TRIGGER",
        description="Habilitar trigger automático de re-treinamento"
    )
    retraining_feedback_threshold: int = Field(
        default=100,
        env="RETRAINING_FEEDBACK_THRESHOLD",
        description="Threshold de feedbacks para disparar re-treinamento"
    )
    retraining_feedback_window_days: int = Field(
        default=7,
        env="RETRAINING_FEEDBACK_WINDOW_DAYS",
        description="Janela de tempo para contar feedbacks (dias)"
    )
    retraining_trigger_schedule_cron: str = Field(
        default='0 3 * * 0',
        env="RETRAINING_TRIGGER_SCHEDULE_CRON",
        description="Expressão cron para verificar threshold (semanalmente domingo 3h UTC)"
    )
    retraining_mlflow_project_uri: str = Field(
        default='./ml_pipelines/training',
        env="RETRAINING_MLFLOW_PROJECT_URI",
        description="URI do projeto MLflow para re-treinamento"
    )
    retraining_min_feedback_quality: float = Field(
        default=0.5,
        env="RETRAINING_MIN_FEEDBACK_QUALITY",
        description="Rating mínimo de feedback para incluir no dataset"
    )

    # ============================================================================
    # Training Pipeline Configuration
    # ============================================================================
    training_dataset_path: str = Field(
        default='/data/training/specialist_{specialist_type}_base.parquet',
        env="TRAINING_DATASET_PATH",
        description="Path para dataset de treinamento base"
    )
    training_validation_split: float = Field(
        default=0.2,
        env="TRAINING_VALIDATION_SPLIT",
        description="Split de validação"
    )
    training_test_split: float = Field(
        default=0.1,
        env="TRAINING_TEST_SPLIT",
        description="Split de teste"
    )
    training_random_seed: int = Field(
        default=42,
        env="TRAINING_RANDOM_SEED",
        description="Seed para reprodutibilidade"
    )
    training_model_types: List[str] = Field(
        default=['random_forest', 'gradient_boosting'],
        env="TRAINING_MODEL_TYPES",
        description="Tipos de modelo a treinar"
    )
    training_hyperparameter_tuning: bool = Field(
        default=False,
        env="TRAINING_HYPERPARAMETER_TUNING",
        description="Habilitar tuning de hiperparâmetros"
    )
    training_promotion_precision_threshold: float = Field(
        default=0.75,
        env="TRAINING_PROMOTION_PRECISION_THRESHOLD",
        description="Precision mínima para promoção"
    )
    training_promotion_recall_threshold: float = Field(
        default=0.70,
        env="TRAINING_PROMOTION_RECALL_THRESHOLD",
        description="Recall mínimo para promoção"
    )

    # =========================================================================
    # Multi-Tenancy Configuration
    # =========================================================================
    enable_multi_tenancy: bool = Field(
        default=False,
        env="ENABLE_MULTI_TENANCY",
        description="Habilitar suporte a multi-tenancy"
    )
    tenant_configs_path: Optional[str] = Field(
        default=None,
        env="TENANT_CONFIGS_PATH",
        description="Caminho para arquivo JSON/YAML com configurações por tenant"
    )
    default_tenant_id: str = Field(
        default='default',
        env="DEFAULT_TENANT_ID",
        description="Tenant padrão quando não especificado"
    )
    require_tenant_id: bool = Field(
        default=False,
        env="REQUIRE_TENANT_ID",
        description="Requerer tenant_id em todas as requisições"
    )
    max_tenants: int = Field(
        default=100,
        ge=1,
        le=1000,
        env="MAX_TENANTS",
        description="Número máximo de tenants suportados (limita cardinality de métricas)"
    )
    tenant_isolation_level: str = Field(
        default='logical',
        env="TENANT_ISOLATION_LEVEL",
        description="Nível de isolamento: 'logical' (mesma collection) ou 'physical' (collections separadas)"
    )

    # =========================================================================
    # Envoy Gateway Configuration
    # =========================================================================
    envoy_gateway_enabled: bool = Field(
        default=False,
        env="ENVOY_GATEWAY_ENABLED",
        description="Usar Envoy como API Gateway"
    )
    envoy_admin_port: int = Field(
        default=9901,
        env="ENVOY_ADMIN_PORT",
        description="Porta do admin interface do Envoy"
    )
    envoy_gateway_port: int = Field(
        default=50051,
        env="ENVOY_GATEWAY_PORT",
        description="Porta do gateway Envoy"
    )
    envoy_ratelimit_service_url: str = Field(
        default='ratelimit.observability.svc.cluster.local:8081',
        env="ENVOY_RATELIMIT_SERVICE_URL",
        description="URL do Envoy Rate Limit Service"
    )

    # Disaster Recovery Configuration
    enable_disaster_recovery: bool = Field(
        default=False,
        env="ENABLE_DISASTER_RECOVERY",
        description="Habilitar disaster recovery e backups automáticos"
    )
    backup_storage_provider: str = Field(
        default='s3',
        env="BACKUP_STORAGE_PROVIDER",
        description="Provider de storage para backups (s3, gcs, local)"
    )
    backup_s3_bucket: Optional[str] = Field(
        default=None,
        env="BACKUP_S3_BUCKET",
        description="Bucket S3 para backups (required se provider=s3)"
    )
    backup_s3_region: str = Field(
        default='us-west-2',
        env="BACKUP_S3_REGION",
        description="Região AWS S3"
    )
    backup_s3_prefix: str = Field(
        default='specialists/backups',
        env="BACKUP_S3_PREFIX",
        description="Prefixo de chave S3 para backups (deprecated, use backup_prefix)"
    )
    backup_prefix: str = Field(
        default='specialists/backups',
        env="BACKUP_PREFIX",
        description="Prefixo genérico para backups (S3/GCS/local)"
    )
    backup_gcs_bucket: Optional[str] = Field(
        default=None,
        env="BACKUP_GCS_BUCKET",
        description="Bucket GCS para backups (required se provider=gcs)"
    )
    backup_gcs_project: Optional[str] = Field(
        default=None,
        env="BACKUP_GCS_PROJECT",
        description="Projeto GCP (required se provider=gcs)"
    )
    backup_local_path: str = Field(
        default='/data/backups',
        env="BACKUP_LOCAL_PATH",
        description="Path local para backups (usado se provider=local)"
    )
    backup_retention_days: int = Field(
        default=90,
        env="BACKUP_RETENTION_DAYS",
        description="Dias de retenção de backups"
    )
    backup_compression_level: int = Field(
        default=6,
        env="BACKUP_COMPRESSION_LEVEL",
        description="Nível de compressão gzip (1-9)"
    )
    backup_include_cache: bool = Field(
        default=False,
        env="BACKUP_INCLUDE_CACHE",
        description="Incluir cache Redis no backup (cache é efêmero)"
    )
    backup_include_metrics: bool = Field(
        default=True,
        env="BACKUP_INCLUDE_METRICS",
        description="Incluir resumo de métricas no backup"
    )
    backup_include_feature_store: bool = Field(
        default=True,
        env="BACKUP_INCLUDE_FEATURE_STORE",
        description="Incluir feature store no backup"
    )
    backup_schedule_cron: str = Field(
        default='0 2 * * *',
        env="BACKUP_SCHEDULE_CRON",
        description="Schedule de backup automático (diariamente 2h UTC)"
    )
    backup_mode: str = Field(
        default='full',
        env="BACKUP_MODE",
        description="Modo de backup: 'full' (upload completo) ou 'incremental' (content-addressed storage com deduplicação)"
    )

    # Recovery Testing Configuration
    enable_recovery_testing: bool = Field(
        default=False,
        env="ENABLE_RECOVERY_TESTING",
        description="Habilitar testes de recovery automáticos"
    )
    recovery_test_schedule_cron: str = Field(
        default='0 4 * * 0',
        env="RECOVERY_TEST_SCHEDULE_CRON",
        description="Schedule de testes de recovery (semanalmente domingo 4h UTC)"
    )
    recovery_test_namespace: str = Field(
        default='dr-test',
        env="RECOVERY_TEST_NAMESPACE",
        description="Namespace para testes de recovery"
    )
    recovery_test_timeout_seconds: int = Field(
        default=600,
        env="RECOVERY_TEST_TIMEOUT_SECONDS",
        description="Timeout de teste de recovery em segundos"
    )

    # AWS/GCP Credentials (opcional, usar IAM roles quando possível)
    aws_access_key_id: Optional[str] = Field(
        default=None,
        env="AWS_ACCESS_KEY_ID",
        description="AWS access key (usar IAM role se possível)"
    )
    aws_secret_access_key: Optional[str] = Field(
        default=None,
        env="AWS_SECRET_ACCESS_KEY",
        description="AWS secret key (usar IAM role se possível)"
    )
    gcp_credentials_path: Optional[str] = Field(
        default=None,
        env="GCP_CREDENTIALS_PATH",
        description="Path para service account JSON do GCP"
    )

    @field_validator('embedding_cache_size')
    @classmethod
    def validate_cache_size(cls, v):
        """Valida limites razoáveis para cache de embeddings."""
        if v < 10:
            raise ValueError("embedding_cache_size deve ser >= 10")
        if v > 100000:
            logger.warning(
                "embedding_cache_size muito alto - pode consumir muita memória",
                embedding_cache_size=v
            )
        return v

    @field_validator('semantic_similarity_threshold')
    @classmethod
    def validate_semantic_threshold(cls, v):
        """Valida range do threshold de similaridade semântica."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("semantic_similarity_threshold deve estar entre 0.0 e 1.0")
        return v

    @field_validator('opinion_cache_ttl_seconds')
    @classmethod
    def validate_opinion_cache_ttl(cls, v):
        """Valida que TTL de opinion cache é positivo."""
        if v <= 0:
            raise ValueError('opinion_cache_ttl_seconds deve ser maior que 0')
        return v

    @field_validator('batch_max_concurrency')
    @classmethod
    def validate_batch_concurrency(cls, v):
        """Valida que concorrência de batch está em range válido."""
        if not 1 <= v <= 100:
            raise ValueError('batch_max_concurrency deve estar entre 1 e 100')
        return v

    @field_validator('shap_background_dataset_path')
    @classmethod
    def validate_shap_background_path(cls, v):
        """Valida que background dataset existe se configurado."""
        if v and not os.path.exists(v):
            logger.warning(
                "SHAP background dataset not found",
                path=v
            )
        return v

    @field_validator('jwt_secret_key')
    @classmethod
    def validate_jwt_secret(cls, v, info):
        """
        Valida que jwt_secret_key está presente quando enable_jwt_auth=True.

        Nota: Para ambientes de desenvolvimento/teste (ENVIRONMENT=local ou test),
        o JWT pode ser desabilitado via ENABLE_JWT_AUTH=false. Para produção,
        jwt_secret_key é obrigatório se JWT estiver habilitado.
        """
        enable_jwt = info.data.get('enable_jwt_auth', True)
        environment = info.data.get('environment', 'production')

        # Se JWT estiver habilitado, secret é obrigatório
        if enable_jwt and not v:
            # Em produção, secret é sempre obrigatório
            if environment == 'production':
                raise ValueError(
                    'jwt_secret_key é obrigatório em ambiente production quando enable_jwt_auth=True. '
                    'Configure JWT_SECRET_KEY ou desabilite via ENABLE_JWT_AUTH=false'
                )
            # Em outros ambientes, apenas alertar via log (será validado em runtime)
            else:
                # Retornar None e deixar o interceptor validar em runtime
                pass

        # Se secret for fornecido, validar tamanho
        if v and len(v) < 32:
            raise ValueError('jwt_secret_key deve ter no mínimo 32 caracteres')

        return v

    @field_validator('ledger_private_key_path')
    @classmethod
    def validate_ledger_private_key_path(cls, v, info):
        """
        Valida que ledger_private_key_path existe quando enable_digital_signature=True.

        Chaves podem ser geradas com: python scripts/generate_rsa_keys.py
        Em desenvolvimento, assinatura pode ser desabilitada via ENABLE_DIGITAL_SIGNATURE=false
        """
        enable_signature = info.data.get('enable_digital_signature', True)

        if enable_signature and v and not os.path.exists(v):
            logger.warning(
                "Ledger private key file not found",
                path=v,
                hint="Generate keys with: python scripts/generate_rsa_keys.py"
            )

        return v

    @field_validator('ledger_schema_version')
    @classmethod
    def validate_ledger_schema_version(cls, v):
        """Valida formato semver do ledger_schema_version."""
        import re
        semver_pattern = r'^\d+\.\d+\.\d+$'
        if not re.match(semver_pattern, v):
            raise ValueError(
                f"ledger_schema_version deve estar em formato semver (ex: '2.0.0'), recebido: {v}"
            )
        return v

    @field_validator('encryption_key_path')
    @classmethod
    def validate_encryption_key_path(cls, v, info):
        """
        Valida que encryption_key_path existe quando enable_field_encryption=True.
        """
        enable_encryption = info.data.get('enable_field_encryption', True)

        if enable_encryption and v and not os.path.exists(v):
            logger.warning(
                "Encryption key file not found - encryption may fail",
                path=v,
                hint="Chave será gerada automaticamente se não fornecida"
            )

        return v

    @field_validator('pii_entities_to_detect')
    @classmethod
    def validate_pii_entities(cls, v):
        """
        Valida que pii_entities_to_detect contém apenas entidades conhecidas do Presidio.
        """
        known_entities = {
            'PERSON', 'EMAIL_ADDRESS', 'PHONE_NUMBER', 'CREDIT_CARD',
            'IBAN_CODE', 'IP_ADDRESS', 'LOCATION', 'DATE_TIME',
            'US_SSN', 'US_DRIVER_LICENSE', 'US_PASSPORT', 'UK_NHS',
            'SG_NRIC_FIN', 'AU_ABN', 'AU_ACN', 'AU_TFN', 'AU_MEDICARE',
            'CRYPTO', 'URL', 'US_BANK_NUMBER', 'NRP', 'MEDICAL_LICENSE'
        }

        for entity in v:
            if entity not in known_entities:
                logger.warning(
                    "Entidade PII desconhecida - pode não ser detectada corretamente",
                    entity=entity,
                    known_entities=sorted(known_entities)
                )

        return v

    @field_validator('feedback_rating_min', 'feedback_rating_max')
    @classmethod
    def validate_feedback_rating_range(cls, v):
        """Valida que ratings estão no range 0.0-1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('feedback_rating_min e feedback_rating_max devem estar entre 0.0 e 1.0')
        return v

    @field_validator('retraining_feedback_threshold')
    @classmethod
    def validate_retraining_threshold(cls, v):
        """Valida que threshold de re-treinamento é positivo."""
        if v <= 0:
            raise ValueError('retraining_feedback_threshold deve ser maior que 0')
        return v

    @field_validator('retraining_trigger_schedule_cron')
    @classmethod
    def validate_retraining_cron(cls, v, info):
        """Valida formato cron quando enable_retraining_trigger=True."""
        enable_retraining = info.data.get('enable_retraining_trigger', False)

        if enable_retraining and v:
            import re
            # Validar formato cron básico (5 campos)
            cron_pattern = r'^(\*|([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])|\*\/([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])) (\*|([0-9]|1[0-9]|2[0-3])|\*\/([0-9]|1[0-9]|2[0-3])) (\*|([1-9]|1[0-9]|2[0-9]|3[0-1])|\*\/([1-9]|1[0-9]|2[0-9]|3[0-1])) (\*|([1-9]|1[0-2])|\*\/([1-9]|1[0-2])) (\*|([0-6])|\*\/([0-6]))$'
            if not re.match(cron_pattern, v):
                raise ValueError(
                    f"retraining_trigger_schedule_cron deve estar em formato cron válido (5 campos), recebido: {v}"
                )

        return v

    @field_validator('training_validation_split', 'training_test_split')
    @classmethod
    def validate_training_splits(cls, v):
        """Valida que splits de treinamento estão no range 0.0-1.0."""
        if not 0.0 < v < 1.0:
            raise ValueError('training_validation_split e training_test_split devem estar entre 0.0 e 1.0')
        return v

    @field_validator('retention_policy_schedule_cron')
    @classmethod
    def validate_retention_cron(cls, v, info):
        """
        Valida formato cron quando enable_automated_retention=True.
        """
        enable_retention = info.data.get('enable_automated_retention', False)

        if enable_retention and v:
            import re
            # Validar formato cron básico (5 campos)
            cron_pattern = r'^(\*|([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])|\*\/([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])) (\*|([0-9]|1[0-9]|2[0-3])|\*\/([0-9]|1[0-9]|2[0-3])) (\*|([1-9]|1[0-9]|2[0-9]|3[0-1])|\*\/([1-9]|1[0-9]|2[0-9]|3[0-1])) (\*|([1-9]|1[0-2])|\*\/([1-9]|1[0-2])) (\*|([0-6])|\*\/([0-6]))$'
            if not re.match(cron_pattern, v):
                raise ValueError(
                    f"retention_policy_schedule_cron deve estar em formato cron válido (5 campos), recebido: {v}"
                )

        return v

    @field_validator('anomaly_contamination')
    @classmethod
    def validate_anomaly_contamination(cls, v):
        """Valida que contamination está entre 0.0 e 0.5."""
        if not 0.0 < v <= 0.5:
            raise ValueError('anomaly_contamination deve estar entre 0.0 e 0.5')
        return v

    @field_validator('business_metrics_window_hours')
    @classmethod
    def validate_business_metrics_window(cls, v):
        """Valida que janela de métricas é positiva."""
        if v <= 0:
            raise ValueError('business_metrics_window_hours deve ser maior que 0')
        return v

    @field_validator('anomaly_alert_threshold')
    @classmethod
    def validate_anomaly_threshold(cls, v):
        """Valida que threshold de anomalia é negativo."""
        if v >= 0:
            raise ValueError('anomaly_alert_threshold deve ser negativo (scores de anomalia são negativos)')
        return v

    @field_validator('trace_sampling_rate')
    @classmethod
    def validate_trace_sampling_rate(cls, v):
        """Valida que taxa de amostragem está entre 0.0 e 1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('trace_sampling_rate deve estar entre 0.0 e 1.0')
        return v

    @field_validator('otel_endpoint')
    @classmethod
    def validate_otel_endpoint(cls, v):
        """Valida formato de URL do endpoint OpenTelemetry."""
        if not v:
            return v
        if not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('otel_endpoint deve começar com http:// ou https://')
        return v

    @field_validator('ensemble_weights')
    @classmethod
    def validate_ensemble_weights(cls, v):
        """Valida que pesos de ensemble somam 1.0."""
        if v is None:
            return v
        if not v:
            raise ValueError('ensemble_weights não pode ser lista vazia')
        total = sum(v)
        if not (0.99 <= total <= 1.01):  # Tolerância para erros de ponto flutuante
            raise ValueError(f'ensemble_weights deve somar 1.0, mas soma {total:.4f}')
        return v

    @field_validator('ensemble_models')
    @classmethod
    def validate_ensemble_models(cls, v, info):
        """Valida que ensemble_models tem tamanho compatível com ensemble_stages."""
        if not v:
            return v
        stages = info.data.get('ensemble_stages', [])
        # Permitir broadcasting: se ensemble_stages tem length 1, aplicar a todos os modelos
        if stages and len(stages) != 1 and len(v) != len(stages):
            raise ValueError(
                f'ensemble_models ({len(v)} itens) deve ter mesmo tamanho que '
                f'ensemble_stages ({len(stages)} itens), ou ensemble_stages deve ter 1 item '
                f'(que será usado para todos os modelos)'
            )
        return v

    @field_validator('ab_test_traffic_split')
    @classmethod
    def validate_ab_test_traffic_split(cls, v):
        """Valida que traffic split está entre 0.0 e 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError('ab_test_traffic_split deve estar entre 0.0 e 1.0')
        return v

    @field_validator('enable_ab_testing')
    @classmethod
    def validate_mutually_exclusive_features(cls, v, info):
        """Valida que ensemble e A/B testing não estão habilitados simultaneamente."""
        enable_ensemble = info.data.get('enable_ensemble', False)
        if v and enable_ensemble:
            raise ValueError(
                'enable_ensemble e enable_ab_testing não podem estar ambos habilitados simultaneamente. '
                'Escolha um dos dois modos de operação.'
            )
        return v

    @field_validator('tenant_configs_path')
    @classmethod
    def validate_tenant_configs_path(cls, v, info):
        """Valida que tenant_configs_path existe quando enable_multi_tenancy=True."""
        enable_multi_tenancy = info.data.get('enable_multi_tenancy', False)

        if enable_multi_tenancy and not v:
            raise ValueError(
                'tenant_configs_path é obrigatório quando enable_multi_tenancy=True. '
                'Configure TENANT_CONFIGS_PATH com caminho para arquivo JSON/YAML de configs.'
            )

        if v and not os.path.exists(v):
            logger.warning(
                "Arquivo de tenant configs não encontrado",
                path=v,
                hint="Será carregado em runtime - verifique que path está correto"
            )

        return v

    @field_validator('max_tenants')
    @classmethod
    def validate_max_tenants(cls, v):
        """Valida que max_tenants está em range válido."""
        if not 1 <= v <= 1000:
            raise ValueError('max_tenants deve estar entre 1 e 1000')
        return v

    @field_validator('tenant_isolation_level')
    @classmethod
    def validate_tenant_isolation_level(cls, v):
        """Valida que tenant_isolation_level é um valor válido."""
        valid_levels = ['logical', 'physical']
        if v not in valid_levels:
            raise ValueError(
                f"tenant_isolation_level deve ser um de {valid_levels}, recebido: {v}"
            )
        return v

    @field_validator('backup_storage_provider')
    @classmethod
    def validate_backup_storage_provider(cls, v):
        """Valida que provider de storage é válido."""
        valid_providers = ['s3', 'gcs', 'local']
        if v not in valid_providers:
            raise ValueError(
                f"backup_storage_provider deve ser um de {valid_providers}, recebido: {v}"
            )
        return v

    @field_validator('backup_s3_bucket')
    @classmethod
    def validate_backup_s3_bucket(cls, v, info):
        """Valida que S3 bucket está presente quando provider=s3."""
        provider = info.data.get('backup_storage_provider', 's3')
        enable_dr = info.data.get('enable_disaster_recovery', False)

        if enable_dr and provider == 's3' and not v:
            raise ValueError(
                'backup_s3_bucket é obrigatório quando backup_storage_provider=s3 e enable_disaster_recovery=true. '
                'Configure BACKUP_S3_BUCKET'
            )
        return v

    @field_validator('backup_gcs_bucket', 'backup_gcs_project')
    @classmethod
    def validate_backup_gcs_config(cls, v, info):
        """Valida que GCS bucket e project estão presentes quando provider=gcs."""
        provider = info.data.get('backup_storage_provider', 's3')
        enable_dr = info.data.get('enable_disaster_recovery', False)

        if enable_dr and provider == 'gcs' and not v:
            field_name = info.field_name
            raise ValueError(
                f'{field_name} é obrigatório quando backup_storage_provider=gcs e enable_disaster_recovery=true. '
                f'Configure {field_name.upper()}'
            )
        return v

    @field_validator('backup_retention_days')
    @classmethod
    def validate_backup_retention_days(cls, v):
        """Valida que retenção de backups é positiva."""
        if v <= 0:
            raise ValueError('backup_retention_days deve ser maior que 0')
        return v

    @field_validator('backup_compression_level')
    @classmethod
    def validate_backup_compression_level(cls, v):
        """Valida que nível de compressão está no range 1-9."""
        if not 1 <= v <= 9:
            raise ValueError('backup_compression_level deve estar entre 1 e 9')
        return v

    @field_validator('recovery_test_timeout_seconds')
    @classmethod
    def validate_recovery_test_timeout(cls, v):
        """Valida que timeout de teste é positivo."""
        if v <= 0:
            raise ValueError('recovery_test_timeout_seconds deve ser maior que 0')
        return v

    @field_validator('backup_prefix')
    @classmethod
    def validate_backup_prefix(cls, v, info):
        """Mapeia backup_s3_prefix para backup_prefix para retrocompatibilidade."""
        backup_s3_prefix = info.data.get('backup_s3_prefix')
        # Se backup_prefix não foi setado mas backup_s3_prefix foi (e é diferente do default), usar backup_s3_prefix
        if v == 'specialists/backups' and backup_s3_prefix and backup_s3_prefix != 'specialists/backups':
            logger.warning(
                "BACKUP_S3_PREFIX está deprecated, use BACKUP_PREFIX",
                backup_s3_prefix=backup_s3_prefix
            )
            return backup_s3_prefix
        return v

    @field_validator('backup_mode')
    @classmethod
    def validate_backup_mode(cls, v):
        """Valida que backup_mode é um valor válido."""
        valid_modes = ['full', 'incremental']
        if v not in valid_modes:
            raise ValueError(
                f"backup_mode deve ser um de {valid_modes}, recebido: {v}"
            )
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def to_dict(self) -> dict:
        """Converte configuração para dicionário."""
        return self.dict()
