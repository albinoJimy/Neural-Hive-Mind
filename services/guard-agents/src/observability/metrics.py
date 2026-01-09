"""Métricas e telemetria para Guard Agents conforme camada-resiliencia.md"""
from prometheus_client import Counter, Histogram, Gauge
import structlog

logger = structlog.get_logger()

# Métricas de Detecção de Ameaças (E1)
threat_detection_total = Counter(
    'guard_agent_threat_detection_total',
    'Total de ameaças detectadas',
    ['threat_type', 'severity']
)

threat_detection_duration = Histogram(
    'guard_agent_threat_detection_duration_seconds',
    'Tempo de detecção de ameaças (MTTD)',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 15.0]
)

false_positives_total = Counter(
    'guard_agent_false_positives_total',
    'Total de falsos positivos detectados'
)

# Métricas de Classificação (E2)
incident_classification_total = Counter(
    'guard_agent_incident_classification_total',
    'Total de incidentes classificados',
    ['severity', 'runbook_id']
)

incident_classification_duration = Histogram(
    'guard_agent_incident_classification_duration_seconds',
    'Tempo de classificação de incidentes'
)

human_review_required_total = Counter(
    'guard_agent_human_review_required_total',
    'Total de incidentes que requerem revisão humana'
)

# Métricas de Enforcement (E3)
policy_enforcement_total = Counter(
    'guard_agent_policy_enforcement_total',
    'Total de políticas enforçadas',
    ['action', 'success']
)

policy_enforcement_duration = Histogram(
    'guard_agent_policy_enforcement_duration_seconds',
    'Tempo de enforcement de políticas'
)

opa_denials_total = Counter(
    'guard_agent_opa_denials_total',
    'Total de políticas negadas pelo OPA'
)

# Métricas de Remediação (E4)
remediation_total = Counter(
    'guard_agent_remediation_total',
    'Total de remediações executadas',
    ['status', 'playbook']
)

remediation_duration = Histogram(
    'guard_agent_remediation_duration_seconds',
    'Tempo de execução de remediação (MTTR)',
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 90.0, 120.0, 300.0]
)

remediation_actions_total = Counter(
    'guard_agent_remediation_actions_total',
    'Total de ações de remediação',
    ['action_type', 'success']
)

rollback_total = Counter(
    'guard_agent_rollback_total',
    'Total de rollbacks executados'
)

# Métricas de SLA (E5)
sla_restoration_total = Counter(
    'guard_agent_sla_restoration_total',
    'Total de restaurações de SLA',
    ['met']
)

mttr_seconds = Histogram(
    'guard_agent_mttr_seconds',
    'Mean Time To Recover',
    buckets=[10.0, 30.0, 60.0, 90.0, 120.0, 180.0, 300.0, 600.0]
)

mttd_seconds = Histogram(
    'guard_agent_mttd_seconds',
    'Mean Time To Detect',
    buckets=[1.0, 5.0, 10.0, 15.0, 30.0, 60.0]
)

sla_breach_total = Counter(
    'guard_agent_sla_breach_total',
    'Total de quebras de SLA',
    ['reason']
)

# Métricas de Autocorreção
auto_correction_total = Counter(
    'guard_agent_auto_correction_total',
    'Total de autocorreções bem-sucedidas'
)

auto_correction_rate = Gauge(
    'guard_agent_auto_correction_rate',
    'Taxa de autocorreção (% incidentes autocorrigidos)'
)

# Métricas de Fluxo Completo (E1-E6)
incident_flow_total = Counter(
    'guard_agent_incident_flow_total',
    'Total de fluxos de incidentes processados',
    ['completed']
)

incident_flow_duration = Histogram(
    'guard_agent_incident_flow_duration_seconds',
    'Tempo total do fluxo E1-E6',
    buckets=[10.0, 30.0, 60.0, 90.0, 120.0, 180.0, 300.0]
)

# Métricas de Validação Proativa de Tickets
guard_agent_tickets_validated_total = Counter(
    'guard_agent_tickets_validated_total',
    'Total de execution tickets validados',
    ['status', 'validator_type']
)

guard_agent_validation_duration_seconds = Histogram(
    'guard_agent_validation_duration_seconds',
    'Duração da validação de tickets',
    ['validator_type'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

guard_agent_violations_detected_total = Counter(
    'guard_agent_violations_detected_total',
    'Total de violações de guardrails detectadas',
    ['violation_type', 'severity']
)

guard_agent_secrets_detected_total = Counter(
    'guard_agent_secrets_detected_total',
    'Total de secrets detectados em tickets',
    ['secret_type']
)

guard_agent_approvals_pending = Gauge(
    'guard_agent_approvals_pending',
    'Número de tickets pendentes de aprovação humana'
)

guard_agent_approval_rate = Gauge(
    'guard_agent_approval_rate',
    'Percentual de tickets aprovados automaticamente'
)

guard_agent_risk_score_avg = Gauge(
    'guard_agent_risk_score_avg',
    'Risk score médio dos tickets validados'
)

# Metricas de ML - Deteccao de Anomalias
anomaly_detection_total = Counter(
    'guard_agent_anomaly_detection_total',
    'Total de deteccoes de anomalias via ML',
    ['model_type', 'is_anomaly']
)

anomaly_detection_latency_seconds = Histogram(
    'guard_agent_anomaly_detection_latency_seconds',
    'Latencia de inferencia do modelo de anomalias',
    ['model_type'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5]
)

anomaly_score_distribution = Histogram(
    'guard_agent_anomaly_score',
    'Distribuicao de scores de anomalia',
    ['model_type'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Metricas de Drift
model_drift_score = Gauge(
    'guard_agent_model_drift_score',
    'Score de drift atual do modelo',
    ['model_name']
)

drift_detection_total = Counter(
    'guard_agent_drift_detection_total',
    'Total de verificacoes de drift',
    ['drift_detected']
)

# Metricas de Retreinamento
ml_retraining_total = Counter(
    'guard_agent_ml_retraining_total',
    'Total de eventos de retreinamento',
    ['model_type', 'trigger', 'success']
)

ml_model_version_info = Gauge(
    'guard_agent_ml_model_version',
    'Versao atual do modelo carregado',
    ['model_name', 'stage']
)

validations_published_total = Counter(
    'guard_agent_validations_published_total',
    'Total de validações publicadas no Kafka',
    ['topic', 'status']
)

trivy_scans_total = Counter(
    'guard_agent_trivy_scans_total',
    'Total de scans Trivy executados',
    ['scan_type', 'status']
)

trivy_scan_duration_seconds = Histogram(
    'guard_agent_trivy_scan_duration_seconds',
    'Duração do scan Trivy',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

vault_requests_total = Counter(
    'guard_agent_vault_requests_total',
    'Total de requisições ao Vault',
    ['operation', 'status']
)

vault_request_duration_seconds = Histogram(
    'guard_agent_vault_request_duration_seconds',
    'Duração de requisições ao Vault',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)


class MetricsCollector:
    """Coletor centralizado de métricas para instrumentação"""

    @staticmethod
    def record_threat_detected(threat_type: str, severity: str, duration: float):
        """Registra detecção de ameaça (E1)"""
        threat_detection_total.labels(threat_type=threat_type, severity=severity).inc()
        threat_detection_duration.observe(duration)
        mttd_seconds.observe(duration)

    @staticmethod
    def record_false_positive():
        """Registra falso positivo (E1)"""
        false_positives_total.inc()

    @staticmethod
    def record_incident_classified(severity: str, runbook_id: str, duration: float):
        """Registra classificação de incidente (E2)"""
        incident_classification_total.labels(
            severity=severity, runbook_id=runbook_id
        ).inc()
        incident_classification_duration.observe(duration)

    @staticmethod
    def record_human_review_required():
        """Registra necessidade de revisão humana (E2)"""
        human_review_required_total.inc()

    @staticmethod
    def record_policy_enforced(action: str, success: bool, duration: float):
        """Registra enforcement de política (E3)"""
        policy_enforcement_total.labels(
            action=action, success=str(success).lower()
        ).inc()
        policy_enforcement_duration.observe(duration)

    @staticmethod
    def record_opa_denial():
        """Registra negação do OPA (E3)"""
        opa_denials_total.inc()

    @staticmethod
    def record_remediation(status: str, playbook: str, duration: float):
        """Registra remediação (E4)"""
        remediation_total.labels(status=status, playbook=playbook).inc()
        remediation_duration.observe(duration)
        mttr_seconds.observe(duration)

    @staticmethod
    def record_remediation_action(action_type: str, success: bool):
        """Registra ação de remediação (E4)"""
        remediation_actions_total.labels(
            action_type=action_type, success=str(success).lower()
        ).inc()

    @staticmethod
    def record_rollback():
        """Registra rollback (E4)"""
        rollback_total.inc()

    @staticmethod
    def record_sla_restoration(met: bool, recovery_time: float, reason: str = None):
        """Registra restauração de SLA (E5)"""
        sla_restoration_total.labels(met=str(met).lower()).inc()

        if not met and reason:
            sla_breach_total.labels(reason=reason).inc()

    @staticmethod
    def record_auto_correction():
        """Registra autocorreção bem-sucedida"""
        auto_correction_total.inc()

    @staticmethod
    def update_auto_correction_rate(rate: float):
        """Atualiza taxa de autocorreção"""
        auto_correction_rate.set(rate)

    @staticmethod
    def record_incident_flow_completed(completed: bool, duration: float):
        """Registra conclusão do fluxo E1-E6"""
        incident_flow_total.labels(completed=str(completed).lower()).inc()
        incident_flow_duration.observe(duration)

    @staticmethod
    def record_anomaly_detection(
        model_type: str,
        is_anomaly: bool,
        anomaly_score: float,
        latency_seconds: float
    ):
        """Registra deteccao de anomalia via ML."""
        anomaly_detection_total.labels(
            model_type=model_type,
            is_anomaly=str(is_anomaly).lower()
        ).inc()
        anomaly_detection_latency_seconds.labels(model_type=model_type).observe(latency_seconds)
        anomaly_score_distribution.labels(model_type=model_type).observe(anomaly_score)

    @staticmethod
    def record_drift_check(drift_detected: bool, drift_score: float, model_name: str):
        """Registra verificacao de drift."""
        drift_detection_total.labels(drift_detected=str(drift_detected).lower()).inc()
        model_drift_score.labels(model_name=model_name).set(drift_score)

    @staticmethod
    def record_ml_retraining(model_type: str, trigger: str, success: bool):
        """Registra evento de retreinamento ML."""
        ml_retraining_total.labels(
            model_type=model_type,
            trigger=trigger,
            success=str(success).lower()
        ).inc()

    @staticmethod
    def update_model_version(model_name: str, version: int, stage: str = "Production"):
        """Atualiza versao do modelo carregado."""
        ml_model_version_info.labels(model_name=model_name, stage=stage).set(version)
