"""
Métricas customizadas Prometheus para especialistas neurais.
"""

from prometheus_client import Counter, Histogram, Gauge
from typing import Dict, Any
import structlog

from .config import SpecialistConfig

logger = structlog.get_logger()


class SpecialistMetrics:
    """Métricas customizadas para especialistas neurais."""

    def __init__(self, config: SpecialistConfig, specialist_type: str):
        self.specialist_type = specialist_type
        self.config = config

        # Contadores de avaliações
        self._total_evaluations = 0
        self._success_evaluations = 0
        self._error_evaluations = 0

        # Somas para cálculo de médias
        self._total_processing_time = 0.0
        self._total_confidence_score = 0.0

        logger.info(
            "Metrics initialized",
            specialist_type=specialist_type
        )

        self._initialize_metrics()

    def _initialize_metrics(self):
        """Inicializa métricas Prometheus."""

        # Avaliações processadas
        self.evaluations_total = Counter(
            'neural_hive_specialist_evaluations_total',
            'Total de avaliações processadas',
            ['specialist_type', 'status']
        )

        # Duração de avaliação
        self.evaluation_duration_seconds = Histogram(
            'neural_hive_specialist_evaluation_duration_seconds',
            'Duração da avaliação em segundos',
            ['specialist_type'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )

        # Distribuição de confiança
        self.confidence_score_histogram = Histogram(
            'neural_hive_specialist_confidence_score',
            'Distribuição de scores de confiança',
            ['specialist_type'],
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        )

        # Distribuição de risco
        self.risk_score_histogram = Histogram(
            'neural_hive_specialist_risk_score',
            'Distribuição de scores de risco',
            ['specialist_type'],
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        )

        # Recomendações por tipo
        self.recommendations_total = Counter(
            'neural_hive_specialist_recommendations_total',
            'Total de recomendações por tipo',
            ['specialist_type', 'recommendation']
        )

        # Precisão do especialista (gauge atualizada periodicamente)
        self.accuracy_score = Gauge(
            'neural_hive_specialist_accuracy_score',
            'Score de precisão do especialista',
            ['specialist_type']
        )

        # Divergência média (vs decisão final do consenso)
        self.divergence_score = Gauge(
            'neural_hive_specialist_divergence_score',
            'Divergência média vs decisão final',
            ['specialist_type']
        )

        # Modelo carregado
        self.model_info = Gauge(
            'neural_hive_specialist_model_info',
            'Informações do modelo carregado',
            ['specialist_type', 'model_version', 'model_type']
        )

        # Circuit Breaker State Gauge
        self.circuit_breaker_state = Gauge(
            'neural_hive_circuit_breaker_state',
            'Estado atual do circuit breaker (0=closed, 1=open, 2=half-open)',
            ['specialist_type', 'client_name']
        )

        # Circuit Breaker Transitions Counter
        self.circuit_breaker_transitions_total = Counter(
            'neural_hive_circuit_breaker_transitions_total',
            'Total de transições de estado do circuit breaker',
            ['specialist_type', 'client_name', 'from_state', 'to_state']
        )

        # Circuit Breaker Failures Counter
        self.circuit_breaker_failures_total = Counter(
            'neural_hive_circuit_breaker_failures_total',
            'Total de falhas que contribuem para abertura do circuito',
            ['specialist_type', 'client_name', 'exception_type']
        )

        # Circuit Breaker Success After Half-Open Counter
        self.circuit_breaker_success_after_halfopen_total = Counter(
            'neural_hive_circuit_breaker_success_after_halfopen_total',
            'Total de chamadas bem-sucedidas no estado half-open',
            ['specialist_type', 'client_name']
        )

        # Fallback Invocations Counter
        self.fallback_invocations_total = Counter(
            'neural_hive_fallback_invocations_total',
            'Total de invocações de estratégia de fallback',
            ['specialist_type', 'client_name', 'fallback_type']
        )

        # Authentication Metrics
        self.auth_requests_total = Counter(
            'neural_hive_specialist_auth_requests_total',
            'Total de requisições de autenticação por método e status',
            ['specialist_type', 'method', 'status']  # status: bypassed, success, failed
        )

        self.auth_attempts_total = Counter(
            'neural_hive_auth_attempts_total',
            'Total de tentativas de autenticação',
            ['specialist_type', 'status']  # status: success, failure
        )

        self.auth_failures_total = Counter(
            'neural_hive_auth_failures_total',
            'Total de falhas de autenticação por tipo',
            ['specialist_type', 'failure_type']  # failure_type: missing_token, invalid_token, expired_token, invalid_format, insufficient_permissions
        )

        self.auth_success_by_service = Counter(
            'neural_hive_auth_success_by_service_total',
            'Total de autenticações bem-sucedidas por tipo de serviço',
            ['specialist_type', 'service_type']  # service_type: consensus-engine, admin, monitoring
        )

        self.auth_token_validation_duration_seconds = Histogram(
            'neural_hive_auth_token_validation_duration_seconds',
            'Duração da validação de token JWT',
            ['specialist_type'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
        )

        # Métricas de modelo ML
        self.model_inference_duration = Histogram(
            f'{self.specialist_type}_model_inference_duration_seconds',
            'Tempo de inferência do modelo ML',
            ['specialist_type', 'model_version']
        )

        self.model_inference_total = Counter(
            f'{self.specialist_type}_model_inference_total',
            'Total de inferências de modelo',
            ['specialist_type', 'status']  # status: success, timeout, error
        )

        self.model_fallback_total = Counter(
            f'{self.specialist_type}_model_fallback_total',
            'Total de fallbacks para heurísticas',
            ['specialist_type', 'reason']  # reason: timeout, error, unavailable
        )

        # Métricas de feature extraction
        self.feature_extraction_duration = Histogram(
            f'{self.specialist_type}_feature_extraction_duration_seconds',
            'Tempo de extração de features',
            ['specialist_type']
        )

        self.feature_vector_size = Gauge(
            f'{self.specialist_type}_feature_vector_size',
            'Tamanho do vetor de features',
            ['specialist_type']
        )

        # Explainability metrics
        self.explainability_computation_time = Histogram(
            'specialist_explainability_computation_seconds',
            'Tempo de computação de explicabilidade',
            ['specialist_type', 'method'],  # method: shap, lime, heuristic
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        )

        self.explainability_method_usage = Counter(
            'specialist_explainability_method_total',
            'Contagem de uso de métodos de explicabilidade',
            ['specialist_type', 'method']
        )

        self.explainability_errors = Counter(
            'specialist_explainability_errors_total',
            'Erros em computação de explicabilidade',
            ['specialist_type', 'method', 'error_type']
        )

        self.explainability_feature_count = Histogram(
            'specialist_explainability_feature_count',
            'Número de features com importância calculada',
            ['specialist_type', 'method'],
            buckets=[5, 10, 20, 50, 100]
        )

        self.explainability_ledger_v2_persistence = Counter(
            'specialist_explainability_ledger_v2_persistence_total',
            'Persistências no ExplainabilityLedgerV2',
            ['specialist_type', 'status']  # status: success, error
        )

        self.narrative_generation_time = Histogram(
            'specialist_narrative_generation_seconds',
            'Tempo de geração de narrativas',
            ['specialist_type', 'language'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0]
        )

        # Cache Metrics
        self.cache_hits_total = Counter(
            'neural_hive_specialist_cache_hits_total',
            'Total de cache hits',
            ['specialist_type']
        )

        self.cache_misses_total = Counter(
            'neural_hive_specialist_cache_misses_total',
            'Total de cache misses',
            ['specialist_type']
        )

        self.cache_hit_ratio = Gauge(
            'neural_hive_specialist_cache_hit_ratio',
            'Hit ratio do cache (hits / (hits + misses))',
            ['specialist_type']
        )

        self.cache_operation_duration_seconds = Histogram(
            'neural_hive_specialist_cache_operation_duration_seconds',
            'Duração de operações de cache',
            ['specialist_type', 'operation'],  # operation: get, set
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
        )

        self.cache_size_bytes = Gauge(
            'neural_hive_specialist_cache_size_bytes',
            'Tamanho estimado do cache em bytes',
            ['specialist_type']
        )

        self.cache_evictions_total = Counter(
            'neural_hive_specialist_cache_evictions_total',
            'Total de evictions de cache (TTL expirado)',
            ['specialist_type']
        )

        # Batch Evaluation Metrics
        self.batch_evaluations_total = Counter(
            'neural_hive_specialist_batch_evaluations_total',
            'Total de batch evaluations',
            ['specialist_type', 'status']  # status: success, partial, error
        )

        self.batch_evaluation_duration_seconds = Histogram(
            'neural_hive_specialist_batch_evaluation_duration_seconds',
            'Duração total de batch evaluation',
            ['specialist_type'],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
        )

        self.batch_size_histogram = Histogram(
            'neural_hive_specialist_batch_size',
            'Tamanho dos batches processados',
            ['specialist_type'],
            buckets=[1, 5, 10, 20, 50, 100]
        )

        self.batch_success_rate = Gauge(
            'neural_hive_specialist_batch_success_rate',
            'Taxa de sucesso em batch (successful_plans / total_plans)',
            ['specialist_type']
        )

        self.batch_concurrency_utilization = Gauge(
            'neural_hive_specialist_batch_concurrency_utilization',
            'Utilização de concorrência (active_tasks / max_concurrency)',
            ['specialist_type']
        )

        # Warmup Metrics
        self.warmup_duration_seconds = Histogram(
            'neural_hive_specialist_warmup_duration_seconds',
            'Duração de warmup',
            ['specialist_type'],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
        )

        self.warmup_total = Counter(
            'neural_hive_specialist_warmup_total',
            'Total de warmups executados',
            ['specialist_type', 'status']  # status: success, error
        )

        self.warmup_last_timestamp = Gauge(
            'neural_hive_specialist_warmup_last_timestamp',
            'Timestamp do último warmup',
            ['specialist_type']
        )

        # Compliance Metrics - PII Detection
        self.compliance_pii_entities_detected_total = Counter(
            'neural_hive_compliance_pii_entities_detected_total',
            'Total de entidades PII detectadas',
            ['specialist_type', 'entity_type']
        )

        self.compliance_pii_detection_duration_seconds = Histogram(
            'neural_hive_compliance_pii_detection_duration_seconds',
            'Duração de detecção PII',
            ['specialist_type'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
        )

        self.compliance_pii_anonymization_total = Counter(
            'neural_hive_compliance_pii_anonymization_total',
            'Total de anonimizações aplicadas',
            ['specialist_type', 'strategy']
        )

        self.compliance_pii_detection_errors_total = Counter(
            'neural_hive_compliance_pii_detection_errors_total',
            'Erros em detecção PII',
            ['specialist_type', 'error_type']
        )

        # Compliance Metrics - Encryption
        self.compliance_fields_encrypted_total = Counter(
            'neural_hive_compliance_fields_encrypted_total',
            'Total de campos criptografados',
            ['specialist_type', 'field_name']
        )

        self.compliance_fields_decrypted_total = Counter(
            'neural_hive_compliance_fields_decrypted_total',
            'Total de campos descriptografados',
            ['specialist_type', 'field_name']
        )

        self.compliance_encryption_duration_seconds = Histogram(
            'neural_hive_compliance_encryption_duration_seconds',
            'Duração de operações de criptografia',
            ['specialist_type', 'operation'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1]
        )

        self.compliance_encryption_errors_total = Counter(
            'neural_hive_compliance_encryption_errors_total',
            'Erros de criptografia',
            ['specialist_type', 'error_type']
        )

        # Compliance Metrics - Audit Logging
        self.compliance_audit_events_total = Counter(
            'neural_hive_compliance_audit_events_total',
            'Total de eventos auditados',
            ['specialist_type', 'event_type']
        )

        self.compliance_audit_logging_errors_total = Counter(
            'neural_hive_compliance_audit_logging_errors_total',
            'Erros ao logar auditoria',
            ['specialist_type', 'error_type']
        )

        # Compliance Metrics - Retention Policy
        self.compliance_retention_documents_processed_total = Counter(
            'neural_hive_compliance_retention_documents_processed_total',
            'Documentos processados por políticas de retenção',
            ['specialist_type', 'action']
        )

        self.compliance_retention_policy_executions_total = Counter(
            'neural_hive_compliance_retention_policy_executions_total',
            'Execuções de política de retenção',
            ['specialist_type', 'policy_name', 'status']
        )

        self.compliance_retention_execution_duration_seconds = Histogram(
            'neural_hive_compliance_retention_execution_duration_seconds',
            'Duração de execução de políticas de retenção',
            ['specialist_type'],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0]
        )

        # Business Metrics - Consensus Agreement
        self.business_consensus_agreement_rate = Gauge(
            'neural_hive_business_consensus_agreement_rate',
            'Taxa de concordância com decisão final do consenso (0.0-1.0)',
            ['specialist_type']
        )

        self.business_false_positive_rate = Gauge(
            'neural_hive_business_false_positive_rate',
            'Taxa de falsos positivos (aprovou mas consenso rejeitou)',
            ['specialist_type']
        )

        self.business_false_negative_rate = Gauge(
            'neural_hive_business_false_negative_rate',
            'Taxa de falsos negativos (rejeitou mas consenso aprovou)',
            ['specialist_type']
        )

        self.business_precision_score = Gauge(
            'neural_hive_business_precision_score',
            'Precision pós-consenso (TP / (TP + FP))',
            ['specialist_type']
        )

        self.business_recall_score = Gauge(
            'neural_hive_business_recall_score',
            'Recall pós-consenso (TP / (TP + FN))',
            ['specialist_type']
        )

        self.business_f1_score = Gauge(
            'neural_hive_business_f1_score',
            'F1-score pós-consenso',
            ['specialist_type']
        )

        self.business_value_generated_total = Counter(
            'neural_hive_business_value_generated_total',
            'Valor de negócio gerado (planos aprovados × tickets completados)',
            ['specialist_type']
        )

        self.business_metrics_last_update_timestamp = Gauge(
            'neural_hive_business_metrics_last_update_timestamp',
            'Timestamp da última atualização de métricas de negócio',
            ['specialist_type']
        )

        # Business Metrics - Confusion Matrix
        self.business_true_positives_total = Counter(
            'neural_hive_business_true_positives_total',
            'True positives (aprovou e consenso aprovou)',
            ['specialist_type']
        )

        self.business_true_negatives_total = Counter(
            'neural_hive_business_true_negatives_total',
            'True negatives (rejeitou e consenso rejeitou)',
            ['specialist_type']
        )

        self.business_false_positives_total = Counter(
            'neural_hive_business_false_positives_total',
            'False positives (aprovou mas consenso rejeitou)',
            ['specialist_type']
        )

        self.business_false_negatives_total = Counter(
            'neural_hive_business_false_negatives_total',
            'False negatives (rejeitou mas consenso aprovou)',
            ['specialist_type']
        )

        # Anomaly Detection
        self.anomaly_detected_total = Counter(
            'neural_hive_anomaly_detected_total',
            'Total de anomalias detectadas em métricas',
            ['specialist_type', 'severity']
        )

        # Multi-Tenancy Metrics com cardinality cap
        self.tenant_evaluations_total = Counter(
            'neural_hive_tenant_evaluations_total',
            'Total de avaliações por tenant',
            ['specialist_type', 'tenant_id']
        )

        self.tenant_evaluation_duration_seconds = Histogram(
            'neural_hive_tenant_evaluation_duration_seconds',
            'Duração de avaliação por tenant',
            ['specialist_type', 'tenant_id'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )

        self.tenant_errors_total = Counter(
            'neural_hive_tenant_errors_total',
            'Total de erros por tenant',
            ['specialist_type', 'tenant_id', 'error_type']
        )

        self.tenant_active_gauge = Gauge(
            'neural_hive_tenant_active',
            'Tenant ativo (1) ou inativo (0)',
            ['specialist_type', 'tenant_id']
        )

        self.tenant_cache_hits_total = Counter(
            'neural_hive_tenant_cache_hits_total',
            'Cache hits por tenant',
            ['specialist_type', 'tenant_id']
        )

        self.tenant_cache_misses_total = Counter(
            'neural_hive_tenant_cache_misses_total',
            'Cache misses por tenant',
            ['specialist_type', 'tenant_id']
        )

        # Rastrear tenants conhecidos para cardinality cap
        self._known_tenants = set()
        self._max_tracked_tenants = self.config.max_tenants if hasattr(self.config, 'max_tenants') else 100

        # ============================================================================
        # Disaster Recovery Metrics
        # ============================================================================
        self.dr_backup_last_success_timestamp = Gauge(
            'neural_hive_dr_backup_last_success_timestamp',
            'Timestamp do último backup bem-sucedido',
            ['specialist_type', 'tenant_id']
        )

        self.dr_backup_duration_seconds = Histogram(
            'neural_hive_dr_backup_duration_seconds',
            'Duração de backup',
            ['specialist_type'],
            buckets=[10, 30, 60, 120, 300, 600]
        )

        self.dr_backup_size_bytes = Gauge(
            'neural_hive_dr_backup_size_bytes',
            'Tamanho do último backup em bytes',
            ['specialist_type', 'tenant_id']
        )

        self.dr_backup_total = Counter(
            'neural_hive_dr_backup_total',
            'Total de backups executados',
            ['specialist_type', 'status']
        )

        self.dr_backup_component_duration_seconds = Histogram(
            'neural_hive_dr_backup_component_duration_seconds',
            'Duração por componente de backup',
            ['specialist_type', 'component'],
            buckets=[1, 5, 10, 30, 60, 120]
        )

        self.dr_backup_component_size_bytes = Gauge(
            'neural_hive_dr_backup_component_size_bytes',
            'Tamanho por componente de backup',
            ['specialist_type', 'component']
        )

        self.dr_restore_total = Counter(
            'neural_hive_dr_restore_total',
            'Total de restores executados',
            ['specialist_type', 'status']
        )

        self.dr_restore_duration_seconds = Histogram(
            'neural_hive_dr_restore_duration_seconds',
            'Duração de restore',
            ['specialist_type'],
            buckets=[30, 60, 120, 300, 600, 1200]
        )

        self.dr_recovery_test_last_status = Gauge(
            'neural_hive_dr_recovery_test_last_status',
            'Status do último teste de recovery (1=success, 0=failed)',
            ['specialist_type']
        )

        self.dr_recovery_test_last_timestamp = Gauge(
            'neural_hive_dr_recovery_test_last_timestamp',
            'Timestamp do último teste de recovery',
            ['specialist_type']
        )

        self.dr_recovery_test_duration_seconds = Histogram(
            'neural_hive_dr_recovery_test_duration_seconds',
            'Duração de teste de recovery',
            ['specialist_type'],
            buckets=[10, 30, 60, 120, 300]
        )

        self.dr_storage_upload_errors_total = Counter(
            'neural_hive_dr_storage_upload_errors_total',
            'Erros de upload para storage',
            ['specialist_type', 'storage_provider']
        )

        self.dr_storage_download_errors_total = Counter(
            'neural_hive_dr_storage_download_errors_total',
            'Erros de download de storage',
            ['specialist_type', 'storage_provider']
        )

        # ============================================================================
        # Ensemble Metrics
        # ============================================================================
        self.ensemble_predictions_total = Counter(
            'neural_hive_ensemble_predictions_total',
            'Total de predições de ensemble',
            ['specialist_type']
        )
        self.ensemble_model_inference_duration_seconds = Histogram(
            'neural_hive_ensemble_model_inference_duration_seconds',
            'Duração de inferência por modelo individual no ensemble',
            ['specialist_type', 'model_name'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
        )
        self.ensemble_prediction_variance = Histogram(
            'neural_hive_ensemble_prediction_variance',
            'Variância entre predições dos modelos do ensemble',
            ['specialist_type'],
            buckets=[0.01, 0.05, 0.1, 0.2, 0.5]
        )
        self.ensemble_model_failures_total = Counter(
            'neural_hive_ensemble_model_failures_total',
            'Falhas de modelos individuais no ensemble',
            ['specialist_type', 'model_name']
        )
        self.ensemble_weights_gauge = Gauge(
            'neural_hive_ensemble_weights_gauge',
            'Pesos atuais do ensemble por modelo',
            ['specialist_type', 'model_name']
        )
        self.ensemble_calibration_coverage = Histogram(
            'neural_hive_ensemble_calibration_coverage',
            'Cobertura de calibração no ensemble (percentual de modelos usando predict_proba)',
            ['specialist_type'],
            buckets=[0.0, 0.25, 0.5, 0.75, 1.0]
        )
        self.ensemble_probabilistic_predictions_total = Counter(
            'neural_hive_ensemble_probabilistic_predictions_total',
            'Total de predições ensemble por método de agregação e status de calibração',
            ['specialist_type', 'aggregation_method', 'calibrated']
        )

        # ============================================================================
        # A/B Testing Metrics
        # ============================================================================
        self.ab_test_variant_usage_total = Counter(
            'neural_hive_ab_test_variant_usage_total',
            'Total de uso por variante de A/B test',
            ['specialist_type', 'variant']
        )
        self.ab_test_variant_confidence_score = Histogram(
            'neural_hive_ab_test_variant_confidence_score',
            'Distribuição de confidence score por variante',
            ['specialist_type', 'variant'],
            buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        )
        self.ab_test_variant_risk_score = Histogram(
            'neural_hive_ab_test_variant_risk_score',
            'Distribuição de risk score por variante',
            ['specialist_type', 'variant'],
            buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        )
        self.ab_test_variant_processing_time_seconds = Histogram(
            'neural_hive_ab_test_variant_processing_time_seconds',
            'Latência de processamento por variante',
            ['specialist_type', 'variant'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
        )
        self.ab_test_variant_consensus_agreement = Gauge(
            'neural_hive_ab_test_variant_consensus_agreement',
            'Taxa de concordância com consenso por variante',
            ['specialist_type', 'variant']
        )
        self.ab_test_variant_recommendation_distribution = Counter(
            'neural_hive_ab_test_variant_recommendation_distribution',
            'Distribuição de recomendações por variante',
            ['specialist_type', 'variant', 'recommendation']
        )
        self.ab_test_traffic_split_gauge = Gauge(
            'neural_hive_ab_test_traffic_split_gauge',
            'Traffic split configurado para A/B test',
            ['specialist_type']
        )
        self.ab_test_sample_size = Gauge(
            'neural_hive_ab_test_sample_size',
            'Tamanho de amostra por variante de A/B test',
            ['specialist_type', 'variant']
        )

        # ============================================================================
        # Feedback and Continuous Learning Metrics
        # ============================================================================
        self.feedback_submissions_total = Counter(
            'neural_hive_feedback_submissions_total',
            'Total de feedbacks submetidos',
            ['specialist_type', 'submitted_by_role']
        )
        self.feedback_rating_distribution = Histogram(
            'neural_hive_feedback_rating_distribution',
            'Distribuição de ratings de feedback',
            ['specialist_type'],
            buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        )
        self.feedback_recommendation_distribution = Counter(
            'neural_hive_feedback_recommendation_distribution',
            'Distribuição de recomendações humanas',
            ['specialist_type', 'human_recommendation']
        )
        self.feedback_count_current = Gauge(
            'neural_hive_feedback_count_current',
            'Quantidade atual de feedbacks na janela de trigger',
            ['specialist_type']
        )
        self.feedback_avg_rating = Gauge(
            'neural_hive_feedback_avg_rating',
            'Rating médio dos feedbacks',
            ['specialist_type']
        )
        self.feedback_api_errors_total = Counter(
            'neural_hive_feedback_api_errors_total',
            'Erros na API de feedback',
            ['specialist_type', 'error_type']
        )

        # Retraining Trigger Metrics
        self.retraining_triggers_total = Counter(
            'neural_hive_retraining_triggers_total',
            'Total de triggers de re-treinamento disparados',
            ['specialist_type', 'status']
        )
        self.retraining_feedback_threshold = Gauge(
            'neural_hive_retraining_feedback_threshold',
            'Threshold configurado de feedbacks para re-treinamento',
            ['specialist_type']
        )
        self.retraining_last_trigger_timestamp = Gauge(
            'neural_hive_retraining_last_trigger_timestamp',
            'Timestamp do último trigger de re-treinamento',
            ['specialist_type']
        )
        self.retraining_mlflow_run_duration_seconds = Histogram(
            'neural_hive_retraining_mlflow_run_duration_seconds',
            'Duração de runs MLflow de re-treinamento',
            ['specialist_type'],
            buckets=[60, 300, 600, 1800, 3600]
        )
        self.retraining_model_performance = Gauge(
            'neural_hive_retraining_model_performance',
            'Performance do modelo re-treinado (precision/recall)',
            ['specialist_type', 'metric_name']
        )
        self.retraining_dataset_size = Gauge(
            'neural_hive_retraining_dataset_size',
            'Tamanho do dataset enriquecido',
            ['specialist_type', 'dataset_type']
        )

        # Inicializar contadores de cache
        self._cache_hits = 0
        self._cache_misses = 0

    def observe_evaluation_duration(self, duration: float):
        """
        Observa duração de avaliação.

        Args:
            duration: Duração em segundos
        """
        self.evaluation_duration_seconds.labels(self.specialist_type).observe(duration)
        self._total_processing_time += duration

        logger.debug(
            "Evaluation duration observed",
            specialist_type=self.specialist_type,
            duration_seconds=duration
        )

    def observe_confidence_score(self, score: float):
        """
        Observa score de confiança.

        Args:
            score: Score de confiança (0.0-1.0)
        """
        self.confidence_score_histogram.labels(self.specialist_type).observe(score)
        self._total_confidence_score += score

        logger.debug(
            "Confidence score observed",
            specialist_type=self.specialist_type,
            confidence_score=score
        )

    def observe_risk_score(self, score: float):
        """
        Observa score de risco.

        Args:
            score: Score de risco (0.0-1.0)
        """
        self.risk_score_histogram.labels(self.specialist_type).observe(score)

        logger.debug(
            "Risk score observed",
            specialist_type=self.specialist_type,
            risk_score=score
        )

    def increment_evaluations(self, status: str = 'success'):
        """
        Incrementa contador de avaliações.

        Args:
            status: Status da avaliação (success, error)
        """
        self.evaluations_total.labels(self.specialist_type, status).inc()
        self._total_evaluations += 1

        if status == 'success':
            self._success_evaluations += 1
        elif status == 'error':
            self._error_evaluations += 1

        logger.debug(
            "Evaluation counter incremented",
            specialist_type=self.specialist_type,
            status=status,
            total=self._total_evaluations
        )

    def increment_recommendation(self, recommendation: str):
        """
        Incrementa contador de recomendações.

        Args:
            recommendation: Tipo de recomendação (approve, reject, review_required, conditional)
        """
        self.recommendations_total.labels(self.specialist_type, recommendation).inc()

        logger.debug(
            "Recommendation counter incremented",
            specialist_type=self.specialist_type,
            recommendation=recommendation
        )

    def set_accuracy_score(self, score: float):
        """
        Define score de precisão do especialista.

        Args:
            score: Score de precisão (0.0-1.0)
        """
        self.accuracy_score.labels(self.specialist_type).set(score)

        logger.info(
            "Accuracy score updated",
            specialist_type=self.specialist_type,
            accuracy_score=score
        )

    def set_divergence_score(self, score: float):
        """
        Define score de divergência.

        Args:
            score: Score de divergência (0.0-1.0)
        """
        self.divergence_score.labels(self.specialist_type).set(score)

        logger.info(
            "Divergence score updated",
            specialist_type=self.specialist_type,
            divergence_score=score
        )

    def set_model_info(self, model_version: str, model_type: str):
        """
        Define informações do modelo carregado.

        Args:
            model_version: Versão do modelo
            model_type: Tipo do modelo
        """
        self.model_info.labels(self.specialist_type, model_version, model_type).set(1)

        logger.info(
            "Model info updated",
            specialist_type=self.specialist_type,
            model_version=model_version,
            model_type=model_type
        )

    def set_circuit_breaker_state(self, client_name: str, state: str):
        """
        Define estado do circuit breaker.

        Args:
            client_name: Nome do cliente (mlflow, ledger, explainability)
            state: Estado (closed, open, half-open)
        """
        state_value = {'closed': 0, 'open': 1, 'half-open': 2}.get(state, 0)
        self.circuit_breaker_state.labels(self.specialist_type, client_name).set(state_value)

        logger.debug(
            "Circuit breaker state updated",
            specialist_type=self.specialist_type,
            client_name=client_name,
            state=state
        )

    def increment_circuit_breaker_transition(
        self,
        client_name: str,
        from_state: str,
        to_state: str
    ):
        """
        Incrementa contador de transições de circuit breaker.

        Args:
            client_name: Nome do cliente
            from_state: Estado de origem
            to_state: Estado de destino
        """
        self.circuit_breaker_transitions_total.labels(
            self.specialist_type,
            client_name,
            from_state,
            to_state
        ).inc()

        logger.debug(
            "Circuit breaker transition recorded",
            specialist_type=self.specialist_type,
            client_name=client_name,
            from_state=from_state,
            to_state=to_state
        )

    def increment_circuit_breaker_failure(
        self,
        client_name: str,
        exception_type: str
    ):
        """
        Incrementa contador de falhas do circuit breaker.

        Args:
            client_name: Nome do cliente
            exception_type: Tipo da exceção
        """
        self.circuit_breaker_failures_total.labels(
            self.specialist_type,
            client_name,
            exception_type
        ).inc()

        logger.debug(
            "Circuit breaker failure recorded",
            specialist_type=self.specialist_type,
            client_name=client_name,
            exception_type=exception_type
        )

    def increment_circuit_breaker_success_after_halfopen(self, client_name: str):
        """
        Incrementa contador de sucessos após half-open.

        Args:
            client_name: Nome do cliente
        """
        self.circuit_breaker_success_after_halfopen_total.labels(
            self.specialist_type,
            client_name
        ).inc()

        logger.debug(
            "Circuit breaker success after half-open recorded",
            specialist_type=self.specialist_type,
            client_name=client_name
        )

    def increment_fallback_invocation(
        self,
        client_name: str,
        fallback_type: str
    ):
        """
        Incrementa contador de invocações de fallback.

        Args:
            client_name: Nome do cliente
            fallback_type: Tipo de fallback (cached_model, in_memory_buffer, skip_persistence)
        """
        self.fallback_invocations_total.labels(
            self.specialist_type,
            client_name,
            fallback_type
        ).inc()

        logger.debug(
            "Fallback invocation recorded",
            specialist_type=self.specialist_type,
            client_name=client_name,
            fallback_type=fallback_type
        )

    def increment_auth_request(self, method: str, status: str):
        """
        Incrementa contador unificado de requisições de autenticação.

        Args:
            method: Método gRPC (ex: /grpc.health.v1.Health/Check, EvaluatePlan)
            status: Status da autenticação (bypassed, success, failed)
        """
        self.auth_requests_total.labels(self.specialist_type, method, status).inc()

        logger.debug(
            "Auth request recorded",
            specialist_type=self.specialist_type,
            method=method,
            status=status
        )

    def increment_auth_success(self, service_type: str = 'unknown'):
        """
        Incrementa contador de autenticações bem-sucedidas.

        Args:
            service_type: Tipo de serviço que se autenticou (ex: consensus-engine)
        """
        self.auth_attempts_total.labels(self.specialist_type, 'success').inc()
        self.auth_success_by_service.labels(self.specialist_type, service_type).inc()

        logger.debug(
            "Authentication success recorded",
            specialist_type=self.specialist_type,
            service_type=service_type
        )

    def increment_auth_failure(self, failure_type: str):
        """
        Incrementa contador de falhas de autenticação.

        Args:
            failure_type: Tipo de falha (missing_token, invalid_token, expired_token, invalid_format, insufficient_permissions)
        """
        self.auth_attempts_total.labels(self.specialist_type, 'failure').inc()
        self.auth_failures_total.labels(self.specialist_type, failure_type).inc()

        logger.debug(
            "Authentication failure recorded",
            specialist_type=self.specialist_type,
            failure_type=failure_type
        )

    def observe_auth_validation_duration(self, duration: float):
        """
        Observa duração da validação de token.

        Args:
            duration: Duração em segundos
        """
        self.auth_token_validation_duration_seconds.labels(self.specialist_type).observe(duration)

        logger.debug(
            "Auth validation duration observed",
            specialist_type=self.specialist_type,
            duration_seconds=duration
        )

    def observe_model_inference_duration(self, duration_seconds: float, model_version: str = 'unknown'):
        """Registra duração de inferência de modelo."""
        self.model_inference_duration.labels(
            specialist_type=self.specialist_type,
            model_version=model_version
        ).observe(duration_seconds)

    def increment_model_inference(self, status: str = 'success'):
        """Incrementa contador de inferências."""
        self.model_inference_total.labels(
            specialist_type=self.specialist_type,
            status=status
        ).inc()

    def increment_model_timeout(self):
        """Incrementa contador de timeouts de modelo."""
        self.model_inference_total.labels(
            specialist_type=self.specialist_type,
            status='timeout'
        ).inc()
        self.model_fallback_total.labels(
            specialist_type=self.specialist_type,
            reason='timeout'
        ).inc()

    def increment_model_error(self):
        """Incrementa contador de erros de modelo."""
        self.model_inference_total.labels(
            specialist_type=self.specialist_type,
            status='error'
        ).inc()
        self.model_fallback_total.labels(
            specialist_type=self.specialist_type,
            reason='error'
        ).inc()

    def observe_feature_extraction_duration(self, duration_seconds: float):
        """Registra duração de extração de features."""
        self.feature_extraction_duration.labels(
            specialist_type=self.specialist_type
        ).observe(duration_seconds)

    def set_feature_vector_size(self, size: int):
        """Define tamanho do vetor de features."""
        self.feature_vector_size.labels(
            specialist_type=self.specialist_type
        ).set(size)

    def observe_explainability_computation_time(self, method: str, duration_seconds: float):
        """Registra tempo de computação de explicabilidade."""
        self.explainability_computation_time.labels(
            specialist_type=self.specialist_type,
            method=method
        ).observe(duration_seconds)

    def increment_explainability_method_usage(self, method: str):
        """Incrementa contador de uso de método."""
        self.explainability_method_usage.labels(
            specialist_type=self.specialist_type,
            method=method
        ).inc()

    def increment_explainability_errors(self, method: str, error_type: str = 'unknown'):
        """Incrementa contador de erros."""
        self.explainability_errors.labels(
            specialist_type=self.specialist_type,
            method=method,
            error_type=error_type
        ).inc()

    def observe_explainability_feature_count(self, method: str, count: int):
        """Registra número de features com importância."""
        self.explainability_feature_count.labels(
            specialist_type=self.specialist_type,
            method=method
        ).observe(count)

    def increment_ledger_v2_persistence(self, status: str):
        """Incrementa contador de persistências no ledger v2."""
        self.explainability_ledger_v2_persistence.labels(
            specialist_type=self.specialist_type,
            status=status
        ).inc()

    def observe_narrative_generation_time(self, language: str, duration_seconds: float):
        """Registra tempo de geração de narrativa."""
        self.narrative_generation_time.labels(
            specialist_type=self.specialist_type,
            language=language
        ).observe(duration_seconds)

    def increment_cache_hit(self):
        """Incrementa contador de cache hits e atualiza hit ratio."""
        self.cache_hits_total.labels(
            specialist_type=self.specialist_type
        ).inc()
        self._cache_hits += 1
        self.update_cache_hit_ratio()

        logger.debug(
            "Cache hit recorded",
            specialist_type=self.specialist_type,
            total_hits=self._cache_hits
        )

    def increment_cache_miss(self):
        """Incrementa contador de cache misses e atualiza hit ratio."""
        self.cache_misses_total.labels(
            specialist_type=self.specialist_type
        ).inc()
        self._cache_misses += 1
        self.update_cache_hit_ratio()

        logger.debug(
            "Cache miss recorded",
            specialist_type=self.specialist_type,
            total_misses=self._cache_misses
        )

    def observe_cache_operation_duration(self, operation: str, duration: float):
        """
        Registra duração de operação de cache.

        Args:
            operation: Tipo de operação ('get' ou 'set')
            duration: Duração em segundos
        """
        self.cache_operation_duration_seconds.labels(
            specialist_type=self.specialist_type,
            operation=operation
        ).observe(duration)

        logger.debug(
            "Cache operation duration observed",
            specialist_type=self.specialist_type,
            operation=operation,
            duration_seconds=duration
        )

    def update_cache_hit_ratio(self):
        """Calcula e atualiza gauge de cache hit ratio."""
        total = self._cache_hits + self._cache_misses
        if total > 0:
            hit_ratio = self._cache_hits / total
            self.cache_hit_ratio.labels(
                specialist_type=self.specialist_type
            ).set(hit_ratio)
        else:
            self.cache_hit_ratio.labels(
                specialist_type=self.specialist_type
            ).set(0.0)

    def observe_batch_evaluation(self, total: int, successful: int, failed: int, duration: float):
        """
        Registra métricas de batch evaluation.

        Args:
            total: Total de planos no batch
            successful: Planos avaliados com sucesso
            failed: Planos que falharam
            duration: Duração total do batch em segundos
        """
        # Determinar status do batch
        if failed == 0:
            status = 'success'
        elif successful > 0:
            status = 'partial'
        else:
            status = 'error'

        # Incrementar contador de batches
        self.batch_evaluations_total.labels(
            specialist_type=self.specialist_type,
            status=status
        ).inc()

        # Registrar duração
        self.batch_evaluation_duration_seconds.labels(
            specialist_type=self.specialist_type
        ).observe(duration)

        # Registrar tamanho do batch
        self.batch_size_histogram.labels(
            specialist_type=self.specialist_type
        ).observe(total)

        # Calcular e registrar taxa de sucesso
        if total > 0:
            success_rate = successful / total
            self.batch_success_rate.labels(
                specialist_type=self.specialist_type
            ).set(success_rate)

        logger.info(
            "Batch evaluation metrics recorded",
            specialist_type=self.specialist_type,
            total=total,
            successful=successful,
            failed=failed,
            status=status,
            duration_seconds=duration
        )

    def observe_warmup_duration(self, duration: float, status: str):
        """
        Registra duração de warmup.

        Args:
            duration: Duração em segundos
            status: Status do warmup ('success' ou 'error')
        """
        import time

        # Registrar duração
        self.warmup_duration_seconds.labels(
            specialist_type=self.specialist_type
        ).observe(duration)

        # Incrementar contador
        self.warmup_total.labels(
            specialist_type=self.specialist_type,
            status=status
        ).inc()

        # Atualizar timestamp
        self.warmup_last_timestamp.labels(
            specialist_type=self.specialist_type
        ).set(time.time())

        logger.info(
            "Warmup metrics recorded",
            specialist_type=self.specialist_type,
            duration_seconds=duration,
            status=status
        )

    def _apply_tenant_cardinality_cap(self, tenant_id: str) -> str:
        """
        Aplica cardinality cap para evitar explosão de métricas por tenant.

        Args:
            tenant_id: ID do tenant original

        Returns:
            tenant_id ou 'other' se excedeu limite
        """
        if tenant_id in self._known_tenants:
            return tenant_id

        if len(self._known_tenants) < self._max_tracked_tenants:
            self._known_tenants.add(tenant_id)
            return tenant_id

        # Excedeu limite, agregar em 'other'
        return 'other'

    def increment_tenant_evaluation(self, tenant_id: str):
        """
        Incrementa contador de avaliações por tenant com cardinality cap.

        Args:
            tenant_id: ID do tenant
        """
        capped_tenant_id = self._apply_tenant_cardinality_cap(tenant_id)
        self.tenant_evaluations_total.labels(
            self.specialist_type,
            capped_tenant_id
        ).inc()

        logger.debug(
            "Tenant evaluation incremented",
            specialist_type=self.specialist_type,
            tenant_id=tenant_id,
            capped_tenant_id=capped_tenant_id
        )

    def observe_tenant_evaluation_duration(self, tenant_id: str, duration_seconds: float):
        """
        Registra duração de avaliação por tenant com cardinality cap.

        Args:
            tenant_id: ID do tenant
            duration_seconds: Duração em segundos
        """
        capped_tenant_id = self._apply_tenant_cardinality_cap(tenant_id)
        self.tenant_evaluation_duration_seconds.labels(
            self.specialist_type,
            capped_tenant_id
        ).observe(duration_seconds)

        logger.debug(
            "Tenant evaluation duration observed",
            specialist_type=self.specialist_type,
            tenant_id=tenant_id,
            duration_seconds=duration_seconds
        )

    def increment_tenant_error(self, tenant_id: str, error_type: str):
        """
        Incrementa contador de erros por tenant com cardinality cap.

        Args:
            tenant_id: ID do tenant
            error_type: Tipo do erro
        """
        capped_tenant_id = self._apply_tenant_cardinality_cap(tenant_id)
        self.tenant_errors_total.labels(
            self.specialist_type,
            capped_tenant_id,
            error_type
        ).inc()

        logger.debug(
            "Tenant error incremented",
            specialist_type=self.specialist_type,
            tenant_id=tenant_id,
            error_type=error_type
        )

    def set_tenant_active(self, tenant_id: str, is_active: bool):
        """
        Define se tenant está ativo com cardinality cap.

        Args:
            tenant_id: ID do tenant
            is_active: True se ativo, False se inativo
        """
        capped_tenant_id = self._apply_tenant_cardinality_cap(tenant_id)
        self.tenant_active_gauge.labels(
            self.specialist_type,
            capped_tenant_id
        ).set(1 if is_active else 0)

        logger.debug(
            "Tenant active status set",
            specialist_type=self.specialist_type,
            tenant_id=tenant_id,
            is_active=is_active
        )

    def increment_tenant_cache_hit(self, tenant_id: str):
        """
        Incrementa contador de cache hits por tenant com cardinality cap.

        Args:
            tenant_id: ID do tenant
        """
        capped_tenant_id = self._apply_tenant_cardinality_cap(tenant_id)
        self.tenant_cache_hits_total.labels(
            self.specialist_type,
            capped_tenant_id
        ).inc()

    def increment_tenant_cache_miss(self, tenant_id: str):
        """
        Incrementa contador de cache misses por tenant com cardinality cap.

        Args:
            tenant_id: ID do tenant
        """
        capped_tenant_id = self._apply_tenant_cardinality_cap(tenant_id)
        self.tenant_cache_misses_total.labels(
            self.specialist_type,
            capped_tenant_id
        ).inc()

    # ============================================================================
    # Disaster Recovery Helper Methods
    # ============================================================================

    def set_backup_last_success_timestamp(self, tenant_id: str, timestamp: float):
        """Define timestamp de último backup bem-sucedido."""
        self.dr_backup_last_success_timestamp.labels(
            self.specialist_type,
            tenant_id
        ).set(timestamp)

    def observe_backup_duration(self, duration: float):
        """Observa duração de backup."""
        self.dr_backup_duration_seconds.labels(self.specialist_type).observe(duration)

    def set_backup_size(self, tenant_id: str, size_bytes: int):
        """Define tamanho de backup."""
        self.dr_backup_size_bytes.labels(
            self.specialist_type,
            tenant_id
        ).set(size_bytes)

    def increment_backup_total(self, status: str):
        """Incrementa contador de backups."""
        self.dr_backup_total.labels(
            self.specialist_type,
            status
        ).inc()

    def observe_backup_component_duration(self, component: str, duration: float):
        """Observa duração por componente."""
        self.dr_backup_component_duration_seconds.labels(
            self.specialist_type,
            component
        ).observe(duration)

    def set_backup_component_size(self, component: str, size_bytes: int):
        """Define tamanho por componente."""
        self.dr_backup_component_size_bytes.labels(
            self.specialist_type,
            component
        ).set(size_bytes)

    def increment_restore_total(self, status: str):
        """Incrementa contador de restores."""
        self.dr_restore_total.labels(
            self.specialist_type,
            status
        ).inc()

    def observe_restore_duration(self, duration: float):
        """Observa duração de restore."""
        self.dr_restore_duration_seconds.labels(self.specialist_type).observe(duration)

    def set_recovery_test_status(self, status: int):
        """Define status de teste de recovery (1 ou 0)."""
        self.dr_recovery_test_last_status.labels(self.specialist_type).set(status)

    def set_recovery_test_timestamp(self, timestamp: float):
        """Define timestamp de teste de recovery."""
        self.dr_recovery_test_last_timestamp.labels(self.specialist_type).set(timestamp)

    def observe_recovery_test_duration(self, duration: float):
        """Observa duração de teste de recovery."""
        self.dr_recovery_test_duration_seconds.labels(self.specialist_type).observe(duration)

    def increment_storage_upload_error(self, storage_provider: str):
        """Incrementa erros de upload."""
        self.dr_storage_upload_errors_total.labels(
            self.specialist_type,
            storage_provider
        ).inc()

    def increment_storage_download_error(self, storage_provider: str):
        """Incrementa erros de download."""
        self.dr_storage_download_errors_total.labels(
            self.specialist_type,
            storage_provider
        ).inc()

    def get_summary(self) -> Dict[str, Any]:
        """
        Retorna resumo de métricas.

        Returns:
            Dicionário com métricas agregadas
        """
        avg_processing_time = 0.0
        avg_confidence_score = 0.0
        success_rate = 0.0

        if self._total_evaluations > 0:
            avg_processing_time = (self._total_processing_time / self._total_evaluations) * 1000  # ms
            avg_confidence_score = self._total_confidence_score / self._total_evaluations
            success_rate = (self._success_evaluations / self._total_evaluations) * 100

        summary = {
            'avg_processing_time_ms': avg_processing_time,
            'accuracy_score': avg_confidence_score,  # Usando confidence como proxy de accuracy
            'total_evaluations': self._total_evaluations,
            'success_evaluations': self._success_evaluations,
            'error_evaluations': self._error_evaluations,
            'success_rate': success_rate
        }

        # Estatísticas de autenticação (se disponíveis)
        try:
            auth_success = self.auth_attempts_total.labels(self.specialist_type, 'success')._value.get()
            auth_failure = self.auth_attempts_total.labels(self.specialist_type, 'failure')._value.get()
            total_auth = auth_success + auth_failure

            if total_auth > 0:
                summary['auth_success_rate'] = (auth_success / total_auth) * 100
                summary['total_auth_attempts'] = total_auth
        except Exception:
            pass  # Métricas de auth podem não estar disponíveis

        # Estatísticas de cache
        total_cache_ops = self._cache_hits + self._cache_misses
        if total_cache_ops > 0:
            cache_hit_ratio = self._cache_hits / total_cache_ops
            summary['cache_hit_ratio'] = cache_hit_ratio
            summary['cache_total_hits'] = self._cache_hits
            summary['cache_total_misses'] = self._cache_misses
            summary['cache_total_operations'] = total_cache_ops

        # Estatísticas de batch (se disponíveis)
        try:
            batch_success = self.batch_evaluations_total.labels(self.specialist_type, 'success')._value.get()
            batch_partial = self.batch_evaluations_total.labels(self.specialist_type, 'partial')._value.get()
            batch_error = self.batch_evaluations_total.labels(self.specialist_type, 'error')._value.get()
            total_batches = batch_success + batch_partial + batch_error

            if total_batches > 0:
                summary['total_batches'] = total_batches
                summary['batch_success_count'] = batch_success
                summary['batch_partial_count'] = batch_partial
                summary['batch_error_count'] = batch_error
        except Exception:
            pass  # Métricas de batch podem não estar disponíveis

        # Estatísticas de warmup (se disponíveis)
        try:
            warmup_success = self.warmup_total.labels(self.specialist_type, 'success')._value.get()
            warmup_error = self.warmup_total.labels(self.specialist_type, 'error')._value.get()
            total_warmups = warmup_success + warmup_error

            if total_warmups > 0:
                summary['total_warmups'] = total_warmups
                summary['warmup_success_count'] = warmup_success
                summary['warmup_error_count'] = warmup_error

                # Timestamp do último warmup
                try:
                    last_warmup = self.warmup_last_timestamp.labels(self.specialist_type)._value.get()
                    if last_warmup > 0:
                        summary['last_warmup_timestamp'] = last_warmup
                except Exception:
                    pass
        except Exception:
            pass  # Métricas de warmup podem não estar disponíveis

        # Business metrics (se disponíveis)
        try:
            summary['business_metrics'] = {
                'consensus_agreement_rate': self.business_consensus_agreement_rate.labels(self.specialist_type)._value.get(),
                'false_positive_rate': self.business_false_positive_rate.labels(self.specialist_type)._value.get(),
                'false_negative_rate': self.business_false_negative_rate.labels(self.specialist_type)._value.get(),
                'precision': self.business_precision_score.labels(self.specialist_type)._value.get(),
                'recall': self.business_recall_score.labels(self.specialist_type)._value.get(),
                'f1_score': self.business_f1_score.labels(self.specialist_type)._value.get(),
                'business_value_generated': self.business_value_generated_total.labels(self.specialist_type)._value.get()
            }
        except Exception:
            pass  # Business metrics podem não estar disponíveis

        # Ensemble metrics (se habilitado)
        try:
            ensemble_total = self.ensemble_predictions_total.labels(self.specialist_type)._value.get()
            if ensemble_total > 0:
                summary['ensemble'] = {
                    'total_predictions': ensemble_total
                }
        except Exception:
            pass  # Ensemble metrics podem não estar disponíveis

        # A/B test metrics (se habilitado)
        try:
            variant_a_usage = self.ab_test_variant_usage_total.labels(self.specialist_type, 'model_a')._value.get()
            variant_b_usage = self.ab_test_variant_usage_total.labels(self.specialist_type, 'model_b')._value.get()
            if variant_a_usage > 0 or variant_b_usage > 0:
                summary['ab_test'] = {
                    'variant_a_usage': variant_a_usage,
                    'variant_b_usage': variant_b_usage,
                    'traffic_split': self.ab_test_traffic_split_gauge.labels(self.specialist_type)._value.get()
                }
        except Exception:
            pass  # A/B test metrics podem não estar disponíveis

        # Estatísticas de multi-tenancy
        try:
            summary['multi_tenancy'] = {
                'tracked_tenants_count': len(self._known_tenants),
                'max_tracked_tenants': self._max_tracked_tenants,
                'tracked_tenants': list(self._known_tenants)
            }
        except Exception:
            pass  # Métricas de multi-tenancy podem não estar disponíveis

        # Disaster recovery metrics (se disponíveis)
        try:
            summary['disaster_recovery'] = {
                'last_backup_timestamp': self.dr_backup_last_success_timestamp.labels(
                    self.specialist_type, 'default'
                )._value.get(),
                'last_backup_size_bytes': self.dr_backup_size_bytes.labels(
                    self.specialist_type, 'default'
                )._value.get(),
                'last_recovery_test_status': self.dr_recovery_test_last_status.labels(
                    self.specialist_type
                )._value.get(),
                'last_recovery_test_timestamp': self.dr_recovery_test_last_timestamp.labels(
                    self.specialist_type
                )._value.get()
            }
        except Exception:
            pass  # Métricas de DR podem não estar disponíveis

        logger.debug(
            "Metrics summary generated",
            specialist_type=self.specialist_type,
            summary=summary
        )

        return summary

    # Compliance Metrics Helper Methods

    def increment_pii_entities_detected(self, entity_type: str, count: int = 1):
        """Incrementa contador de entidades PII detectadas."""
        self.compliance_pii_entities_detected_total.labels(
            self.specialist_type,
            entity_type
        ).inc(count)
        logger.debug(
            "PII entities detected",
            specialist_type=self.specialist_type,
            entity_type=entity_type,
            count=count
        )

    def observe_pii_detection_duration(self, duration: float):
        """Observa duração de detecção PII."""
        self.compliance_pii_detection_duration_seconds.labels(
            self.specialist_type
        ).observe(duration)
        logger.debug(
            "PII detection duration observed",
            specialist_type=self.specialist_type,
            duration_seconds=duration
        )

    def increment_pii_anonymization(self, strategy: str):
        """Incrementa contador de anonimizações."""
        self.compliance_pii_anonymization_total.labels(
            self.specialist_type,
            strategy
        ).inc()
        logger.debug(
            "PII anonymization applied",
            specialist_type=self.specialist_type,
            strategy=strategy
        )

    def increment_pii_detection_error(self, error_type: str):
        """Incrementa contador de erros de detecção PII."""
        self.compliance_pii_detection_errors_total.labels(
            self.specialist_type,
            error_type
        ).inc()
        logger.debug(
            "PII detection error",
            specialist_type=self.specialist_type,
            error_type=error_type
        )

    def increment_fields_encrypted(self, field_name: str):
        """Incrementa contador de campos criptografados."""
        self.compliance_fields_encrypted_total.labels(
            self.specialist_type,
            field_name
        ).inc()
        logger.debug(
            "Field encrypted",
            specialist_type=self.specialist_type,
            field_name=field_name
        )

    def increment_fields_decrypted(self, field_name: str):
        """Incrementa contador de campos descriptografados."""
        self.compliance_fields_decrypted_total.labels(
            self.specialist_type,
            field_name
        ).inc()
        logger.debug(
            "Field decrypted",
            specialist_type=self.specialist_type,
            field_name=field_name
        )

    def observe_encryption_duration(self, operation: str, duration: float):
        """Observa duração de operação de criptografia."""
        self.compliance_encryption_duration_seconds.labels(
            self.specialist_type,
            operation
        ).observe(duration)
        logger.debug(
            "Encryption operation duration observed",
            specialist_type=self.specialist_type,
            operation=operation,
            duration_seconds=duration
        )

    def increment_encryption_error(self, error_type: str):
        """Incrementa contador de erros de criptografia."""
        self.compliance_encryption_errors_total.labels(
            self.specialist_type,
            error_type
        ).inc()
        logger.debug(
            "Encryption error",
            specialist_type=self.specialist_type,
            error_type=error_type
        )

    def increment_audit_event(self, event_type: str):
        """Incrementa contador de eventos auditados."""
        self.compliance_audit_events_total.labels(
            self.specialist_type,
            event_type
        ).inc()
        logger.debug(
            "Audit event logged",
            specialist_type=self.specialist_type,
            event_type=event_type
        )

    def increment_audit_error(self, error_type: str):
        """Incrementa contador de erros de auditoria."""
        self.compliance_audit_logging_errors_total.labels(
            self.specialist_type,
            error_type
        ).inc()
        logger.debug(
            "Audit logging error",
            specialist_type=self.specialist_type,
            error_type=error_type
        )

    def increment_retention_documents_processed(self, action: str, count: int):
        """Incrementa contador de documentos processados por retenção."""
        self.compliance_retention_documents_processed_total.labels(
            self.specialist_type,
            action
        ).inc(count)
        logger.debug(
            "Retention documents processed",
            specialist_type=self.specialist_type,
            action=action,
            count=count
        )

    def increment_retention_policy_execution(self, policy_name: str, status: str):
        """Incrementa contador de execuções de política de retenção."""
        self.compliance_retention_policy_executions_total.labels(
            self.specialist_type,
            policy_name,
            status
        ).inc()
        logger.debug(
            "Retention policy execution",
            specialist_type=self.specialist_type,
            policy_name=policy_name,
            status=status
        )

    def observe_retention_execution_duration(self, duration: float):
        """Observa duração de execução de retenção."""
        self.compliance_retention_execution_duration_seconds.labels(
            self.specialist_type
        ).observe(duration)
        logger.debug(
            "Retention execution duration observed",
            specialist_type=self.specialist_type,
            duration_seconds=duration
        )

    def set_consensus_agreement_rate(self, rate: float):
        """Define taxa de concordância com consenso."""
        self.business_consensus_agreement_rate.labels(
            self.specialist_type
        ).set(rate)
        logger.debug(
            "Consensus agreement rate set",
            specialist_type=self.specialist_type,
            rate=rate
        )

    def set_false_positive_rate(self, rate: float):
        """Define taxa de falsos positivos."""
        self.business_false_positive_rate.labels(
            self.specialist_type
        ).set(rate)
        logger.debug(
            "False positive rate set",
            specialist_type=self.specialist_type,
            rate=rate
        )

    def set_false_negative_rate(self, rate: float):
        """Define taxa de falsos negativos."""
        self.business_false_negative_rate.labels(
            self.specialist_type
        ).set(rate)
        logger.debug(
            "False negative rate set",
            specialist_type=self.specialist_type,
            rate=rate
        )

    def set_precision_score(self, score: float):
        """Define precision score."""
        self.business_precision_score.labels(
            self.specialist_type
        ).set(score)
        logger.debug(
            "Precision score set",
            specialist_type=self.specialist_type,
            score=score
        )

    def set_recall_score(self, score: float):
        """Define recall score."""
        self.business_recall_score.labels(
            self.specialist_type
        ).set(score)
        logger.debug(
            "Recall score set",
            specialist_type=self.specialist_type,
            score=score
        )

    def set_f1_score(self, score: float):
        """Define F1 score."""
        self.business_f1_score.labels(
            self.specialist_type
        ).set(score)
        logger.debug(
            "F1 score set",
            specialist_type=self.specialist_type,
            score=score
        )

    def increment_business_value(self, value: float = 1.0):
        """Incrementa valor de negócio gerado."""
        self.business_value_generated_total.labels(
            self.specialist_type
        ).inc(value)
        logger.debug(
            "Business value incremented",
            specialist_type=self.specialist_type,
            value=value
        )

    def increment_confusion_matrix(self, category: str):
        """
        Incrementa contador de confusion matrix.

        Args:
            category: Uma de 'tp', 'tn', 'fp', 'fn'
        """
        if category == 'tp':
            self.business_true_positives_total.labels(self.specialist_type).inc()
        elif category == 'tn':
            self.business_true_negatives_total.labels(self.specialist_type).inc()
        elif category == 'fp':
            self.business_false_positives_total.labels(self.specialist_type).inc()
        elif category == 'fn':
            self.business_false_negatives_total.labels(self.specialist_type).inc()

        logger.debug(
            "Confusion matrix incremented",
            specialist_type=self.specialist_type,
            category=category
        )

    def update_business_metrics_timestamp(self):
        """Atualiza timestamp de última atualização de métricas de negócio."""
        import time
        self.business_metrics_last_update_timestamp.labels(
            self.specialist_type
        ).set(time.time())
        logger.debug(
            "Business metrics timestamp updated",
            specialist_type=self.specialist_type
        )

    def increment_anomaly_detected(self, severity: str = 'warning'):
        """
        Incrementa contador de anomalias detectadas.

        Args:
            severity: 'info', 'warning', ou 'critical'
        """
        self.anomaly_detected_total.labels(
            self.specialist_type,
            severity
        ).inc()
        logger.debug(
            "Anomaly detected",
            specialist_type=self.specialist_type,
            severity=severity
        )

    # ============================================================================
    # Ensemble Metrics Helper Methods
    # ============================================================================

    def increment_ensemble_prediction(self):
        """Incrementa contador de predições de ensemble."""
        self.ensemble_predictions_total.labels(self.specialist_type).inc()

    def observe_ensemble_model_duration(self, model_name: str, duration: float):
        """
        Observa duração de inferência de modelo individual no ensemble.

        Args:
            model_name: Nome do modelo
            duration: Duração em segundos
        """
        self.ensemble_model_inference_duration_seconds.labels(
            self.specialist_type,
            model_name
        ).observe(duration)

    def observe_ensemble_variance(self, variance: float):
        """
        Observa variância entre predições dos modelos do ensemble.

        Args:
            variance: Variância (desvio padrão) entre predições
        """
        self.ensemble_prediction_variance.labels(self.specialist_type).observe(variance)

    def increment_ensemble_model_failure(self, model_name: str):
        """
        Incrementa contador de falhas de modelo individual.

        Args:
            model_name: Nome do modelo que falhou
        """
        self.ensemble_model_failures_total.labels(
            self.specialist_type,
            model_name
        ).inc()

    def set_ensemble_weight(self, model_name: str, weight: float):
        """
        Define peso de modelo no ensemble.

        Args:
            model_name: Nome do modelo
            weight: Peso (0.0 a 1.0)
        """
        self.ensemble_weights_gauge.labels(
            self.specialist_type,
            model_name
        ).set(weight)

    def observe_ensemble_calibration_coverage(self, coverage: float):
        """
        Observa cobertura de calibração no ensemble.

        Registra o percentual de modelos que usaram predict_proba()
        em uma predição ensemble.

        Args:
            coverage: Percentual de modelos calibrados (0.0 a 1.0)
        """
        self.ensemble_calibration_coverage.labels(
            self.specialist_type
        ).observe(coverage)

    def increment_ensemble_probabilistic_prediction(self, method: str, calibrated: bool):
        """
        Incrementa contador de predições probabilísticas do ensemble.

        Args:
            method: Método de agregação usado ('weighted_average', 'voting', 'stacking')
            calibrated: Se a maioria dos modelos usou predict_proba()
        """
        self.ensemble_probabilistic_predictions_total.labels(
            self.specialist_type,
            method,
            str(calibrated).lower()
        ).inc()

    # ============================================================================
    # A/B Testing Metrics Helper Methods
    # ============================================================================

    def increment_ab_test_variant_usage(self, variant: str):
        """
        Incrementa contador de uso de variante.

        Args:
            variant: 'model_a' ou 'model_b'
        """
        self.ab_test_variant_usage_total.labels(
            self.specialist_type,
            variant
        ).inc()

    def observe_ab_test_variant_confidence(self, variant: str, score: float):
        """
        Observa confidence score de variante.

        Args:
            variant: 'model_a' ou 'model_b'
            score: Confidence score (0.0 a 1.0)
        """
        self.ab_test_variant_confidence_score.labels(
            self.specialist_type,
            variant
        ).observe(score)

    def observe_ab_test_variant_risk(self, variant: str, score: float):
        """
        Observa risk score de variante.

        Args:
            variant: 'model_a' ou 'model_b'
            score: Risk score (0.0 a 1.0)
        """
        self.ab_test_variant_risk_score.labels(
            self.specialist_type,
            variant
        ).observe(score)

    def observe_ab_test_variant_processing_time(self, variant: str, duration: float):
        """
        Observa tempo de processamento de variante.

        Args:
            variant: 'model_a' ou 'model_b'
            duration: Duração em segundos
        """
        self.ab_test_variant_processing_time_seconds.labels(
            self.specialist_type,
            variant
        ).observe(duration)

    def set_ab_test_variant_agreement(self, variant: str, rate: float):
        """
        Define taxa de concordância com consenso de variante.

        Args:
            variant: 'model_a' ou 'model_b'
            rate: Taxa de concordância (0.0 a 1.0)
        """
        self.ab_test_variant_consensus_agreement.labels(
            self.specialist_type,
            variant
        ).set(rate)

    def increment_ab_test_recommendation(self, variant: str, recommendation: str):
        """
        Incrementa contador de recomendação de variante.

        Args:
            variant: 'model_a' ou 'model_b'
            recommendation: 'approve', 'reject', 'review_required'
        """
        self.ab_test_variant_recommendation_distribution.labels(
            self.specialist_type,
            variant,
            recommendation
        ).inc()

    def set_ab_test_traffic_split(self, split: float):
        """
        Define traffic split configurado.

        Args:
            split: Porcentagem para modelo A (0.0 a 1.0)
        """
        self.ab_test_traffic_split_gauge.labels(self.specialist_type).set(split)

    def set_ab_test_sample_size(self, variant: str, size: int):
        """
        Define tamanho de amostra de variante.

        Args:
            variant: 'model_a' ou 'model_b'
            size: Número de avaliações
        """
        self.ab_test_sample_size.labels(
            self.specialist_type,
            variant
        ).set(size)

    # ============================================================================
    # Feedback and Continuous Learning Helper Methods
    # ============================================================================

    def increment_feedback_submission(self, submitted_by_role: str = 'human_expert'):
        """
        Incrementa contador de submissões de feedback.

        Args:
            submitted_by_role: Role do revisor que submeteu feedback
        """
        self.feedback_submissions_total.labels(
            self.specialist_type,
            submitted_by_role
        ).inc()

    def observe_feedback_rating(self, rating: float):
        """
        Observa rating de feedback.

        Args:
            rating: Rating de concordância (0.0-1.0)
        """
        self.feedback_rating_distribution.labels(self.specialist_type).observe(rating)

    def increment_feedback_recommendation(self, human_recommendation: str):
        """
        Incrementa distribuição de recomendações humanas.

        Args:
            human_recommendation: 'approve', 'reject', 'review_required'
        """
        self.feedback_recommendation_distribution.labels(
            self.specialist_type,
            human_recommendation
        ).inc()

    def set_feedback_count_current(self, count: int):
        """
        Define contagem atual de feedbacks na janela de trigger.

        Args:
            count: Quantidade de feedbacks
        """
        self.feedback_count_current.labels(self.specialist_type).set(count)

    def set_feedback_avg_rating(self, avg_rating: float):
        """
        Define rating médio dos feedbacks.

        Args:
            avg_rating: Rating médio (0.0-1.0)
        """
        self.feedback_avg_rating.labels(self.specialist_type).set(avg_rating)

    def increment_feedback_api_error(self, error_type: str):
        """
        Incrementa erros na API de feedback.

        Args:
            error_type: Tipo de erro (validation, not_found, service_unavailable, etc.)
        """
        self.feedback_api_errors_total.labels(
            self.specialist_type,
            error_type
        ).inc()

    def increment_retraining_trigger(self, status: str):
        """
        Incrementa contador de triggers de re-treinamento.

        Args:
            status: 'success' ou 'failed'
        """
        self.retraining_triggers_total.labels(
            self.specialist_type,
            status
        ).inc()

    def set_retraining_threshold(self, threshold: int):
        """
        Define threshold configurado de feedbacks.

        Args:
            threshold: Threshold de feedbacks
        """
        self.retraining_feedback_threshold.labels(self.specialist_type).set(threshold)

    def set_retraining_last_trigger_timestamp(self, timestamp: float):
        """
        Define timestamp do último trigger.

        Args:
            timestamp: Unix timestamp
        """
        self.retraining_last_trigger_timestamp.labels(self.specialist_type).set(timestamp)

    def observe_retraining_run_duration(self, duration: float):
        """
        Observa duração de run MLflow de re-treinamento.

        Args:
            duration: Duração em segundos
        """
        self.retraining_mlflow_run_duration_seconds.labels(self.specialist_type).observe(duration)

    def set_retraining_model_performance(self, metric_name: str, value: float):
        """
        Define performance do modelo re-treinado.

        Args:
            metric_name: 'precision', 'recall', 'f1', etc.
            value: Valor da métrica (0.0-1.0)
        """
        self.retraining_model_performance.labels(
            self.specialist_type,
            metric_name
        ).set(value)

    def set_retraining_dataset_size(self, dataset_type: str, size: int):
        """
        Define tamanho do dataset enriquecido.

        Args:
            dataset_type: 'base', 'feedback', 'total'
            size: Tamanho do dataset
        """
        self.retraining_dataset_size.labels(
            self.specialist_type,
            dataset_type
        ).set(size)
