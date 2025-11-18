"""
Métricas Prometheus customizadas para o Orchestrator Dynamic.
"""
from functools import lru_cache

from prometheus_client import Counter, Histogram, Gauge
import structlog

logger = structlog.get_logger()


class OrchestratorMetrics:
    """Métricas Prometheus do Orchestrator Dynamic."""

    def __init__(self, service_name: str = 'orchestrator-dynamic', component: str = 'orchestration', layer: str = 'orchestration'):
        """
        Inicializa métricas Prometheus.

        Args:
            service_name: Nome do serviço
            component: Nome do componente
            layer: Camada da arquitetura
        """
        self.service_name = service_name
        self.component = component
        self.layer = layer

        # Métricas de Workflows
        self.workflows_started_total = Counter(
            'orchestration_workflows_started_total',
            'Total de workflows iniciados',
            ['status', 'risk_band']
        )

        self.workflows_completed_total = Counter(
            'orchestration_workflows_completed_total',
            'Total de workflows concluídos',
            ['status', 'risk_band']
        )

        self.workflow_duration_seconds = Histogram(
            'orchestration_workflow_duration_seconds',
            'Duração de workflows em segundos',
            ['status', 'risk_band'],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600, 7200, 14400]
        )

        self.workflows_active = Gauge(
            'orchestration_workflows_active',
            'Workflows ativos no momento'
        )

        # Métricas de Tickets
        self.tickets_generated_total = Counter(
            'orchestration_tickets_generated_total',
            'Total de tickets gerados',
            ['task_type', 'risk_band', 'priority']
        )

        self.tickets_published_total = Counter(
            'orchestration_tickets_published_total',
            'Total de tickets publicados no Kafka',
            ['status']
        )

        self.tickets_completed_total = Counter(
            'orchestration_tickets_completed_total',
            'Total de tickets concluídos',
            ['status', 'task_type']
        )

        self.ticket_generation_duration_seconds = Histogram(
            'orchestration_ticket_generation_duration_seconds',
            'Tempo de geração de tickets',
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10]
        )

        # Métricas de SLA
        self.sla_violations_total = Counter(
            'orchestration_sla_violations_total',
            'Total de violações de SLA',
            ['risk_band', 'task_type']
        )

        self.sla_remaining_seconds = Gauge(
            'orchestration_sla_remaining_seconds',
            'Tempo restante de SLA em segundos',
            ['workflow_id', 'risk_band']
        )

        self.deadline_approaching_total = Counter(
            'orchestration_deadline_approaching_total',
            'Workflows próximos do deadline (>80% consumido)'
        )

        # Métricas de SLA Monitoring
        self.sla_budget_remaining_percent = Gauge(
            'orchestration_sla_budget_remaining_percent',
            'Percentual de error budget restante',
            ['service_name', 'slo_id']
        )

        self.sla_budget_status = Gauge(
            'orchestration_sla_budget_status',
            'Status do budget (0=HEALTHY, 1=WARNING, 2=CRITICAL, 3=EXHAUSTED)',
            ['service_name', 'slo_id']
        )

        self.sla_burn_rate = Gauge(
            'orchestration_sla_burn_rate',
            'Taxa de consumo do error budget',
            ['service_name', 'window_hours']
        )

        self.sla_alerts_sent_total = Counter(
            'orchestration_sla_alerts_sent_total',
            'Total de alertas SLA enviados',
            ['alert_type', 'severity']
        )

        self.sla_violations_published_total = Counter(
            'orchestration_sla_violations_published_total',
            'Total de violações SLA publicadas no Kafka',
            ['violation_type']
        )

        self.sla_monitor_errors_total = Counter(
            'orchestration_sla_monitor_errors_total',
            'Total de erros no SLA monitoring',
            ['error_type']
        )

        self.sla_alert_deduplication_hits_total = Counter(
            'orchestration_sla_alert_deduplication_hits_total',
            'Total de alertas bloqueados por deduplicação'
        )

        self.sla_check_duration_seconds = Histogram(
            'orchestration_sla_check_duration_seconds',
            'Duração de verificações de SLA',
            ['check_type'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10]
        )

        # Métricas de Retry e Compensação
        self.retries_total = Counter(
            'orchestration_retries_total',
            'Total de retries',
            ['task_type', 'retry_attempt']
        )

        self.compensations_triggered_total = Counter(
            'orchestration_compensations_triggered_total',
            'Total de compensações acionadas',
            ['reason']
        )

        # Métricas de Kafka
        self.kafka_messages_consumed_total = Counter(
            'orchestration_kafka_messages_consumed_total',
            'Total de mensagens consumidas de plans.consensus'
        )

        self.kafka_messages_produced_total = Counter(
            'orchestration_kafka_messages_produced_total',
            'Total de mensagens produzidas em execution.tickets'
        )

        self.kafka_consumer_lag = Gauge(
            'orchestration_kafka_consumer_lag',
            'Lag do consumer Kafka'
        )

        self.kafka_errors_total = Counter(
            'orchestration_kafka_errors_total',
            'Total de erros Kafka',
            ['operation', 'error_type']
        )

        # Métricas de Validação
        self.plan_validations_total = Counter(
            'orchestration_plan_validations_total',
            'Total de validações de planos',
            ['result']
        )

        self.dag_optimizations_total = Counter(
            'orchestration_dag_optimizations_total',
            'Total de otimizações de DAG'
        )

        # Métricas de Recursos
        self.resource_allocations_total = Counter(
            'orchestration_resource_allocations_total',
            'Total de alocações de recursos',
            ['status']
        )

        self.burst_capacity_activations_total = Counter(
            'orchestration_burst_capacity_activations_total',
            'Total de ativações de burst capacity'
        )

        # Métricas de Scheduler
        self.scheduler_allocations_total = Counter(
            'orchestration_scheduler_allocations_total',
            'Total de alocações pelo scheduler',
            ['status', 'fallback', 'has_predictions']
        )

        self.scheduler_allocation_duration_seconds = Histogram(
            'orchestration_scheduler_allocation_duration_seconds',
            'Duração de alocações do scheduler',
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30]
        )

        self.scheduler_workers_discovered = Histogram(
            'orchestration_scheduler_workers_discovered',
            'Número de workers descobertos por alocação'
        )

        self.scheduler_discovery_failures_total = Counter(
            'orchestration_scheduler_discovery_failures_total',
            'Total de falhas de discovery no Service Registry',
            ['error_type']
        )

        self.scheduler_priority_score = Histogram(
            'orchestration_scheduler_priority_score',
            'Scores de prioridade calculados',
            ['risk_band', 'boosted']
        )

        self.scheduler_cache_hits_total = Counter(
            'orchestration_scheduler_cache_hits_total',
            'Total de cache hits em descobertas'
        )

        self.scheduler_rejections_total = Counter(
            'orchestration_scheduler_rejections_total',
            'Total de rejeições de alocação pelo scheduler',
            ['reason']
        )

        # Métricas de OPA Policy Validation
        self.opa_validations_total = Counter(
            'orchestration_opa_validations_total',
            'Total de validações OPA',
            ['policy_name', 'result']  # result: allowed, denied, error
        )

        self.opa_validation_duration_seconds = Histogram(
            'orchestration_opa_validation_duration_seconds',
            'Duração de validações OPA',
            ['policy_name'],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5]
        )

        self.opa_policy_rejections_total = Counter(
            'orchestration_opa_policy_rejections_total',
            'Total de rejeições por políticas OPA',
            ['policy_name', 'rule', 'severity']  # severity: critical, high, medium, low
        )

        self.opa_policy_warnings_total = Counter(
            'orchestration_opa_policy_warnings_total',
            'Total de warnings de políticas OPA',
            ['policy_name', 'rule']
        )

        self.opa_evaluation_errors_total = Counter(
            'orchestration_opa_evaluation_errors_total',
            'Total de erros na avaliação OPA',
            ['error_type']  # error_type: connection, timeout, policy_not_found, evaluation_error
        )

        self.opa_cache_hits_total = Counter(
            'orchestration_opa_cache_hits_total',
            'Total de cache hits em decisões OPA'
        )

        self.opa_feature_flags = Gauge(
            'orchestration_opa_feature_flags',
            'Status de feature flags (1=enabled, 0=disabled)',
            ['flag_name', 'namespace']
        )

        self.opa_circuit_breaker_state = Gauge(
            'orchestration_opa_circuit_breaker_state',
            'Estado do circuit breaker OPA (0=closed, 1=half_open, 2=open)',
            ['circuit_name']
        )

        # ML Predictions Metrics
        self.ml_predictions_total = Counter(
            'orchestration_ml_predictions_total',
            'Total de predições ML executadas',
            ['model_type', 'status']
        )

        self.ml_prediction_duration_seconds = Histogram(
            'orchestration_ml_prediction_duration_seconds',
            'Latência de predições ML',
            ['model_type'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5]
        )

        self.ml_prediction_error = Histogram(
            'orchestration_ml_prediction_error',
            'Erro de predição (actual - predicted)',
            ['model_type'],
            buckets=[0, 1000, 5000, 10000, 30000, 60000, 120000, 300000]
        )

        self.ml_anomalies_detected_total = Counter(
            'orchestration_ml_anomalies_detected_total',
            'Anomalias detectadas por tipo',
            ['anomaly_type']
        )

        self.ml_model_load_errors_total = Counter(
            'orchestration_ml_model_load_errors_total',
            'Erros ao carregar modelos',
            ['model_name']
        )

        self.ml_training_duration_seconds = Histogram(
            'orchestration_ml_training_duration_seconds',
            'Duração do treinamento de modelos',
            ['model_type'],
            buckets=[10, 30, 60, 120, 300, 600, 1800]
        )

        self.ml_model_accuracy = Gauge(
            'orchestration_ml_model_accuracy',
            'Métricas de acurácia dos modelos',
            ['model_name', 'metric_type']
        )

        self.ml_feature_extraction_errors_total = Counter(
            'orchestration_ml_feature_extraction_errors_total',
            'Erros ao extrair features para ML'
        )

        # ML Drift Detection Metrics
        self.ml_drift_score = Gauge(
            'orchestration_ml_drift_score',
            'Scores de drift detection (PSI, MAE ratio, K-S statistic)',
            ['drift_type', 'feature', 'model_name']
        )

        self.ml_drift_status = Gauge(
            'orchestration_ml_drift_status',
            'Status geral de drift (0=ok, 1=warning, 2=critical)',
            ['model_name', 'drift_type']
        )

        # ML Training Job Metrics
        self.ml_training_jobs_total = Counter(
            'orchestration_ml_training_jobs_total',
            'Total de jobs de treinamento executados',
            ['status', 'trigger']
        )

        self.ml_training_samples_used = Gauge(
            'orchestration_ml_training_samples_used',
            'Número de amostras usadas no treinamento',
            ['model_name', 'data_source']
        )

        self.ml_model_promotion_total = Counter(
            'orchestration_ml_model_promotion_total',
            'Total de promoções de modelos',
            ['model_name', 'from_stage', 'to_stage', 'result']
        )

        self.ml_prediction_cache_hits_total = Counter(
            'orchestration_ml_prediction_cache_hits_total',
            'Cache hits de modelos ML',
            ['model_name']
        )

        # ML Scheduling Optimization Metrics
        self.scheduler_ml_optimizations_applied_total = Counter(
            'orchestration_scheduler_ml_optimizations_applied_total',
            'Total de otimizações ML aplicadas',
            ['optimization_type', 'source']  # source: remote, local, fallback
        )

        self.scheduler_ml_optimization_latency_seconds = Histogram(
            'orchestration_scheduler_ml_optimization_latency_seconds',
            'Latência de otimizações ML de scheduling',
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10]
        )

        self.scheduler_queue_prediction_error_ms = Histogram(
            'orchestration_scheduler_queue_prediction_error_ms',
            'Erro de predição de queue time (|predicted - actual|)',
            buckets=[0, 500, 1000, 2000, 5000, 10000, 30000, 60000]
        )

        self.scheduler_load_prediction_accuracy = Gauge(
            'orchestration_scheduler_load_prediction_accuracy',
            'Acurácia de predição de carga (predicted vs actual)',
            ['worker_id']
        )

        self.scheduler_allocation_quality_score = Histogram(
            'orchestration_scheduler_allocation_quality_score',
            'Score de qualidade da alocação (0-1)',
            ['used_ml_optimization'],
            buckets=[0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
        )

        self.scheduler_optimizer_availability = Gauge(
            'orchestration_scheduler_optimizer_availability',
            'Disponibilidade do optimizer-agents remoto (1=available, 0=unavailable)'
        )

        self.scheduler_predicted_queue_time_ms = Histogram(
            'orchestration_scheduler_predicted_queue_time_ms',
            'Queue times preditos pelos modelos ML',
            ['source'],  # source: local, remote
            buckets=[0, 100, 500, 1000, 2000, 5000, 10000, 30000, 60000]
        )

        self.scheduler_predicted_worker_load_pct = Histogram(
            'orchestration_scheduler_predicted_worker_load_pct',
            'Worker load predito como percentual (0-1)',
            ['source'],  # source: local, remote
            buckets=[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        )

        logger.info('Métricas Prometheus inicializadas', service=service_name, component=component)

    # Métodos helper para registrar métricas

    def record_workflow_started(self, risk_band: str, status: str = 'started'):
        """Registra início de workflow."""
        self.workflows_started_total.labels(status=status, risk_band=risk_band).inc()
        self.workflows_active.inc()

    def record_workflow_completed(self, status: str, risk_band: str, duration_seconds: float):
        """Registra conclusão de workflow."""
        self.workflows_completed_total.labels(status=status, risk_band=risk_band).inc()
        self.workflow_duration_seconds.labels(status=status, risk_band=risk_band).observe(duration_seconds)
        self.workflows_active.dec()

    def record_ticket_generated(self, task_type: str, risk_band: str, priority: str):
        """Registra geração de ticket."""
        self.tickets_generated_total.labels(
            task_type=task_type,
            risk_band=risk_band,
            priority=priority
        ).inc()

    def record_ticket_published(self, status: str = 'published'):
        """Registra publicação de ticket no Kafka."""
        self.tickets_published_total.labels(status=status).inc()

    def record_ticket_completed(self, status: str, task_type: str):
        """Registra conclusão de ticket."""
        self.tickets_completed_total.labels(status=status, task_type=task_type).inc()

    def record_sla_violation(self, risk_band: str, task_type: str):
        """Registra violação de SLA."""
        self.sla_violations_total.labels(risk_band=risk_band, task_type=task_type).inc()

    def update_sla_remaining(self, workflow_id: str, risk_band: str, seconds: float):
        """Atualiza gauge de SLA restante."""
        self.sla_remaining_seconds.labels(workflow_id=workflow_id, risk_band=risk_band).set(seconds)

    def record_deadline_approaching(self):
        """Registra deadline próximo."""
        self.deadline_approaching_total.inc()

    def record_retry(self, task_type: str, attempt: int):
        """Registra retry de tarefa."""
        self.retries_total.labels(task_type=task_type, retry_attempt=str(attempt)).inc()

    def record_compensation(self, reason: str):
        """Registra compensação acionada."""
        self.compensations_triggered_total.labels(reason=reason).inc()

    def record_kafka_message_consumed(self):
        """Registra mensagem consumida do Kafka."""
        self.kafka_messages_consumed_total.inc()

    def record_kafka_message_produced(self):
        """Registra mensagem produzida no Kafka."""
        self.kafka_messages_produced_total.inc()

    def update_kafka_consumer_lag(self, lag: int):
        """Atualiza lag do consumer Kafka."""
        self.kafka_consumer_lag.set(lag)

    def record_kafka_error(self, operation: str, error_type: str):
        """Registra erro Kafka."""
        self.kafka_errors_total.labels(operation=operation, error_type=error_type).inc()

    def record_plan_validation(self, result: str):
        """Registra validação de plano."""
        self.plan_validations_total.labels(result=result).inc()

    def record_dag_optimization(self):
        """Registra otimização de DAG."""
        self.dag_optimizations_total.inc()

    def record_resource_allocation(self, status: str):
        """Registra alocação de recurso."""
        self.resource_allocations_total.labels(status=status).inc()

    def record_burst_capacity_activation(self):
        """Registra ativação de burst capacity."""
        self.burst_capacity_activations_total.inc()

    def record_scheduler_allocation(self, status: str, fallback: bool, duration_seconds: float, has_predictions: bool = False):
        """Registra alocação do scheduler."""
        self.scheduler_allocations_total.labels(
            status=status,
            fallback=str(fallback),
            has_predictions=str(has_predictions)
        ).inc()
        self.scheduler_allocation_duration_seconds.observe(duration_seconds)

    def record_workers_discovered(self, count: int):
        """Registra workers descobertos."""
        self.scheduler_workers_discovered.observe(count)

    def record_discovery_failure(self, error_type: str):
        """Registra falha de discovery."""
        self.scheduler_discovery_failures_total.labels(error_type=error_type).inc()

    def record_priority_score(self, risk_band: str, score: float, boosted: bool = False):
        """Registra score de prioridade."""
        self.scheduler_priority_score.labels(risk_band=risk_band, boosted=str(boosted)).observe(score)

    def record_cache_hit(self):
        """Registra cache hit."""
        self.scheduler_cache_hits_total.inc()

    def record_scheduler_rejection(self, reason: str):
        """Registra rejeição de alocação pelo scheduler."""
        self.scheduler_rejections_total.labels(reason=reason).inc()

    def record_opa_validation(self, policy_name: str, result: str, duration_seconds: float):
        """Registra validação OPA."""
        self.opa_validations_total.labels(policy_name=policy_name, result=result).inc()
        self.opa_validation_duration_seconds.labels(policy_name=policy_name).observe(duration_seconds)

    def record_opa_rejection(self, policy_name: str, rule: str, severity: str):
        """Registra rejeição por política OPA."""
        self.opa_policy_rejections_total.labels(
            policy_name=policy_name,
            rule=rule,
            severity=severity
        ).inc()

    def record_ml_prediction(self, model_type: str, status: str, duration: float):
        """Registra predição ML."""
        self.ml_predictions_total.labels(model_type=model_type, status=status).inc()
        self.ml_prediction_duration_seconds.labels(model_type=model_type).observe(duration)

    def record_ml_anomaly(self, anomaly_type: str):
        """Registra anomalia detectada."""
        self.ml_anomalies_detected_total.labels(anomaly_type=anomaly_type).inc()

    def record_ml_training(self, model_type: str, duration: float, metrics: dict):
        """Registra treinamento de modelo ML."""
        self.ml_training_duration_seconds.labels(model_type=model_type).observe(duration)

        # Atualiza gauges de acurácia
        model_name = f'{model_type}-predictor'
        if model_type == 'duration':
            if 'mae_percentage' in metrics:
                self.ml_model_accuracy.labels(model_name=model_name, metric_type='mae_pct').set(
                    metrics['mae_percentage']
                )
            if 'r2' in metrics:
                self.ml_model_accuracy.labels(model_name=model_name, metric_type='r2').set(
                    metrics['r2']
                )
            if 'train_samples' in metrics:
                self.ml_model_accuracy.labels(model_name=model_name, metric_type='train_samples').set(
                    metrics['train_samples']
                )
            if 'test_samples' in metrics:
                self.ml_model_accuracy.labels(model_name=model_name, metric_type='test_samples').set(
                    metrics['test_samples']
                )
        elif model_type == 'anomaly':
            if 'precision' in metrics:
                self.ml_model_accuracy.labels(model_name=model_name, metric_type='precision').set(
                    metrics['precision']
                )
            if 'recall' in metrics:
                self.ml_model_accuracy.labels(model_name=model_name, metric_type='recall').set(
                    metrics['recall']
                )
            if 'f1_score' in metrics:
                self.ml_model_accuracy.labels(model_name=model_name, metric_type='f1').set(
                    metrics['f1_score']
                )
            if 'train_samples' in metrics:
                self.ml_model_accuracy.labels(model_name=model_name, metric_type='train_samples').set(
                    metrics['train_samples']
                )
            if 'test_samples' in metrics:
                self.ml_model_accuracy.labels(model_name=model_name, metric_type='test_samples').set(
                    metrics['test_samples']
                )

    def record_ml_prediction_error(self, model_type: str, error: float):
        """Registra erro de predição ML (actual - predicted)."""
        self.ml_prediction_error.labels(model_type=model_type).observe(abs(error))

    def record_ml_prediction_error_with_logging(
        self,
        model_type: str,
        error_ms: float,
        ticket_id: str,
        predicted_ms: float,
        actual_ms: float
    ):
        """
        Registra erro de predição ML com logging estruturado.

        Calcula erro percentual e registra em Prometheus + logs.

        Args:
            model_type: Tipo do modelo (ex: 'duration')
            error_ms: Erro absoluto em milissegundos (actual - predicted)
            ticket_id: ID do ticket para correlação
            predicted_ms: Duração prevista em ms
            actual_ms: Duração real em ms
        """
        # Registra histograma de erro absoluto
        self.ml_prediction_error.labels(model_type=model_type).observe(abs(error_ms))

        # Calcula erro percentual
        error_pct = (abs(error_ms) / actual_ms * 100) if actual_ms > 0 else 100.0

        # Log estruturado
        logger.info(
            'ml_prediction_error_recorded',
            ticket_id=ticket_id,
            model_type=model_type,
            predicted_ms=predicted_ms,
            actual_ms=actual_ms,
            error_ms=error_ms,
            error_pct=round(error_pct, 2)
        )

    def record_ml_error(self, error_type: str):
        """Registra erro ML."""
        if error_type == 'model_load':
            self.ml_model_load_errors_total.labels(model_name='unknown').inc()
        elif error_type == 'feature_extraction':
            self.ml_feature_extraction_errors_total.inc()
        elif error_type in ['prediction', 'training']:
            self.ml_predictions_total.labels(model_type='unknown', status='error').inc()

    # ML Drift Detection Methods
    def record_drift_score(
        self,
        drift_type: str,
        score: float,
        feature: str = '',
        model_name: str = 'duration-predictor'
    ):
        """
        Registra score de drift detection.

        Args:
            drift_type: Tipo de drift (feature, prediction, target)
            score: Valor do score (PSI, MAE ratio, K-S statistic)
            feature: Nome da feature (para feature drift)
            model_name: Nome do modelo
        """
        self.ml_drift_score.labels(
            drift_type=drift_type,
            feature=feature,
            model_name=model_name
        ).set(score)

    def update_drift_status(
        self,
        model_name: str,
        drift_type: str,
        status: str
    ):
        """
        Atualiza status de drift.

        Args:
            model_name: Nome do modelo
            drift_type: Tipo de drift
            status: Status (ok, warning, critical)
        """
        status_value = {'ok': 0, 'warning': 1, 'critical': 2}.get(status, 0)
        self.ml_drift_status.labels(
            model_name=model_name,
            drift_type=drift_type
        ).set(status_value)

    # ML Training Job Methods
    def record_training_job(self, status: str, trigger: str = 'scheduled'):
        """
        Registra execução de job de treinamento.

        Args:
            status: Status (success, failure, timeout)
            trigger: Trigger do treinamento (scheduled, manual, drift)
        """
        self.ml_training_jobs_total.labels(
            status=status,
            trigger=trigger
        ).inc()

    def record_training_samples(
        self,
        model_name: str,
        samples: int,
        data_source: str = 'mongodb'
    ):
        """
        Registra número de amostras usadas no treinamento.

        Args:
            model_name: Nome do modelo
            samples: Número de amostras
            data_source: Fonte dos dados
        """
        self.ml_training_samples_used.labels(
            model_name=model_name,
            data_source=data_source
        ).set(samples)

    def record_model_promotion(
        self,
        model_name: str,
        from_stage: str,
        to_stage: str,
        result: str
    ):
        """
        Registra promoção de modelo.

        Args:
            model_name: Nome do modelo
            from_stage: Stage de origem
            to_stage: Stage de destino
            result: Resultado (success, rejected)
        """
        self.ml_model_promotion_total.labels(
            model_name=model_name,
            from_stage=from_stage,
            to_stage=to_stage,
            result=result
        ).inc()

    def record_model_cache_hit(self, model_name: str):
        """
        Registra cache hit de modelo.

        Args:
            model_name: Nome do modelo
        """
        self.ml_prediction_cache_hits_total.labels(
            model_name=model_name
        ).inc()

    def record_opa_warning(self, policy_name: str, rule: str):
        """Registra warning de política OPA."""
        self.opa_policy_warnings_total.labels(policy_name=policy_name, rule=rule).inc()

    def record_opa_error(self, error_type: str):
        """Registra erro de avaliação OPA."""
        self.opa_evaluation_errors_total.labels(error_type=error_type).inc()

    def record_opa_cache_hit(self):
        """Registra cache hit OPA."""
        self.opa_cache_hits_total.inc()

    def update_feature_flag(self, flag_name: str, namespace: str, enabled: bool):
        """Atualiza status de feature flag."""
        self.opa_feature_flags.labels(flag_name=flag_name, namespace=namespace).set(1 if enabled else 0)

    def record_opa_circuit_breaker_state(self, state: str, failure_count: int):
        """Registra estado do circuit breaker OPA."""
        state_map = {'closed': 0, 'half_open': 1, 'open': 2}
        self.opa_circuit_breaker_state.labels(circuit_name='opa_client').set(
            state_map.get(state.lower(), -1)
        )
        logger.info(
            'opa_circuit_breaker_state_changed',
            state=state,
            failure_count=failure_count
        )

    def update_budget_remaining(self, service_name: str, slo_id: str, percent: float):
        """Atualiza gauge de budget restante."""
        self.sla_budget_remaining_percent.labels(
            service_name=service_name,
            slo_id=slo_id
        ).set(percent)

    def update_budget_status(self, service_name: str, slo_id: str, status: str):
        """Atualiza gauge de status do budget."""
        status_map = {'HEALTHY': 0, 'WARNING': 1, 'CRITICAL': 2, 'EXHAUSTED': 3}
        self.sla_budget_status.labels(
            service_name=service_name,
            slo_id=slo_id
        ).set(status_map.get(status, 0))

    def update_burn_rate(self, service_name: str, window_hours: int, rate: float):
        """Atualiza gauge de burn rate."""
        self.sla_burn_rate.labels(
            service_name=service_name,
            window_hours=str(window_hours)
        ).set(rate)

    def record_sla_alert_sent(self, alert_type: str, severity: str):
        """Registra alerta SLA enviado."""
        self.sla_alerts_sent_total.labels(
            alert_type=alert_type,
            severity=severity
        ).inc()

    def record_sla_violation_published(self, violation_type: str):
        """Registra violação SLA publicada."""
        self.sla_violations_published_total.labels(
            violation_type=violation_type
        ).inc()

    def record_sla_monitor_error(self, error_type: str):
        """Registra erro no SLA monitoring."""
        self.sla_monitor_errors_total.labels(error_type=error_type).inc()

    def record_sla_alert_deduplicated(self):
        """Registra alerta bloqueado por deduplicação."""
        self.sla_alert_deduplication_hits_total.inc()

    def record_sla_check_duration(self, check_type: str, duration_seconds: float):
        """Registra duração de verificação SLA."""
        self.sla_check_duration_seconds.labels(check_type=check_type).observe(duration_seconds)

    # ML Scheduling Optimization Helper Methods

    def record_ml_optimization(
        self,
        optimization_type: str,
        source: str,
        duration_seconds: float
    ):
        """
        Registra aplicação de otimização ML.

        Args:
            optimization_type: Tipo de otimização (load_forecast, rl_recommendation, heuristic)
            source: Origem (remote, local, fallback)
            duration_seconds: Duração da operação
        """
        self.scheduler_ml_optimizations_applied_total.labels(
            optimization_type=optimization_type,
            source=source
        ).inc()
        self.scheduler_ml_optimization_latency_seconds.observe(duration_seconds)

    def record_queue_prediction_error(self, predicted_ms: float, actual_ms: float):
        """
        Registra erro de predição de queue time.

        Args:
            predicted_ms: Queue time previsto em ms
            actual_ms: Queue time real em ms
        """
        error_ms = abs(predicted_ms - actual_ms)
        self.scheduler_queue_prediction_error_ms.observe(error_ms)

    def record_allocation_quality(self, quality_score: float, used_ml_optimization: bool):
        """
        Registra score de qualidade da alocação.

        Args:
            quality_score: Score de qualidade (0-1)
            used_ml_optimization: Se usou otimização ML
        """
        self.scheduler_allocation_quality_score.labels(
            used_ml_optimization=str(used_ml_optimization).lower()
        ).observe(quality_score)

    def update_optimizer_availability(self, available: bool):
        """
        Atualiza gauge de disponibilidade do optimizer.

        Args:
            available: True se optimizer disponível, False caso contrário
        """
        self.scheduler_optimizer_availability.set(1.0 if available else 0.0)

    def record_predicted_queue_time(self, predicted_ms: float, source: str = 'local'):
        """
        Registra queue time predito.

        Args:
            predicted_ms: Queue time previsto em ms
            source: Origem da predição (local, remote)
        """
        self.scheduler_predicted_queue_time_ms.labels(source=source).observe(predicted_ms)

    def record_predicted_worker_load(self, predicted_pct: float, source: str = 'local'):
        """
        Registra worker load predito.

        Args:
            predicted_pct: Load previsto como percentual (0-1)
            source: Origem da predição (local, remote)
        """
        self.scheduler_predicted_worker_load_pct.labels(source=source).observe(predicted_pct)

    def record_prediction(
        self,
        model_type: str,
        predicted_value: float,
        actual_value: float = None,
        latency: float = 0.0,
        confidence: float = 0.0
    ):
        """
        Registra predição ML centralizada.

        Args:
            model_type: Tipo de modelo (scheduling, load, anomaly)
            predicted_value: Valor predito
            actual_value: Valor real (se disponível)
            latency: Latência da predição em segundos
            confidence: Score de confiança
        """
        self.ml_predictions_total.labels(model_type=model_type, status='success').inc()
        if latency > 0:
            self.ml_prediction_duration_seconds.labels(model_type=model_type).observe(latency)

    def record_anomaly_detection(self, anomaly_type: str, severity: str, score: float):
        """
        Registra detecção de anomalia.

        Args:
            anomaly_type: Tipo de anomalia detectada
            severity: Severidade (LOW, MEDIUM, HIGH, CRITICAL)
            score: Score de anomalia
        """
        self.ml_anomalies_detected_total.labels(anomaly_type=anomaly_type).inc()

    async def record_load_forecast(
        self,
        horizon_minutes: int,
        status: str,
        latency: float,
        mape: float
    ):
        """
        Registra geração de forecast de carga.

        Args:
            horizon_minutes: Horizonte de previsão
            status: Status (success/error)
            latency: Latência em segundos
            mape: Mean Absolute Percentage Error
        """
        self.ml_predictions_total.labels(model_type='load', status=status).inc()
        if latency > 0:
            self.ml_prediction_duration_seconds.labels(model_type='load').observe(latency)

    async def record_bottleneck_prediction(
        self,
        bottleneck_type: str,
        severity: str,
        timestamp: str
    ):
        """Registra predição de bottleneck (stub para compatibilidade)."""
        pass

    async def record_forecast_cache_hit(self, hit: bool):
        """Registra cache hit/miss de forecast (stub para compatibilidade)."""
        if hit:
            self.ml_prediction_cache_hits_total.labels(model_name='load-predictor').inc()


@lru_cache()
def get_metrics() -> OrchestratorMetrics:
    """
    Retorna instância singleton das métricas.

    Returns:
        Instância de OrchestratorMetrics
    """
    return OrchestratorMetrics()
