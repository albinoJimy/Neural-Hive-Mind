"""
Risk Alerts

Sistema de alertas baseado em thresholds dinâmicos e anomalias.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Optional, Tuple

import structlog

from neural_hive_domain import UnifiedDomain

from .config import RiskBand, RiskScoringConfig
from .history import AnomalyDetection, RiskHistory, TrendDirection
from .models import RiskAssessment
from .thresholds import ThresholdMonitor

logger = structlog.get_logger(__name__)


class AlertSeverity(str, Enum):
    """Severidade do alerta."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Tipo de alerta."""

    THRESHOLD_VIOLATION = "threshold_violation"
    ANOMALY_DETECTED = "anomaly_detected"
    TREND_WORSENING = "trend_worsening"
    RAPID_ESCALATION = "rapid_escalation"
    CONSECUTIVE_HIGH_RISK = "consecutive_high_risk"
    CROSS_DOMAIN_SPIKE = "cross_domain_spike"


@dataclass
class RiskAlert:
    """Alerta de risco."""

    id: str
    alert_type: AlertType
    severity: AlertSeverity
    entity_id: str
    domain: Optional[UnifiedDomain]
    score: float
    band: RiskBand
    message: str
    details: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "entity_id": self.entity_id,
            "domain": self.domain.value if self.domain else None,
            "score": self.score,
            "band": self.band.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class AlertRule:
    """Regra de geração de alertas."""

    name: str
    alert_type: AlertType
    enabled: bool = True
    min_severity: AlertSeverity = AlertSeverity.WARNING
    cooldown_minutes: int = 60  # Tempo mínimo entre alertas do mesmo tipo
    conditions: dict[str, Any] = field(default_factory=dict)

    def should_trigger(
        self,
        entity_id: str,
        context: dict[str, Any],
        last_alert_time: Optional[datetime],
    ) -> bool:
        """Verifica se regra deve ser disparada."""
        if not self.enabled:
            return False

        # Verificar cooldown
        if last_alert_time:
            cooldown = timedelta(minutes=self.cooldown_minutes)
            if datetime.now(UTC) - last_alert_time < cooldown:
                return False

        # Verificar condições específicas
        return self._check_conditions(context)

    def _check_conditions(self, context: dict[str, Any]) -> bool:
        """Verifica condições específicas da regra."""
        if self.alert_type == AlertType.THRESHOLD_VIOLATION:
            return context.get("threshold_violation", False)

        elif self.alert_type == AlertType.ANOMALY_DETECTED:
            anomaly: AnomalyDetection = context.get("anomaly")
            return anomaly is not None and anomaly.is_anomaly

        elif self.alert_type == AlertType.TREND_WORSENING:
            trend = context.get("trend")
            return trend is not None and trend.direction == TrendDirection.WORSENING

        elif self.alert_type == AlertType.RAPID_ESCALATION:
            # Aumento rápido de score
            score_delta = context.get("score_delta", 0)
            time_delta_hours = context.get("time_delta_hours", 1)
            escalation_rate = score_delta / time_delta_hours if time_delta_hours > 0 else 0
            return escalation_rate > self.conditions.get("max_escalation_rate", 0.5)

        elif self.alert_type == AlertType.CONSECUTIVE_HIGH_RISK:
            consecutive_count = context.get("consecutive_high_risk_count", 0)
            return consecutive_count >= self.conditions.get("min_consecutive", 3)

        elif self.alert_type == AlertType.CROSS_DOMAIN_SPIKE:
            # Spike em múltiplos domínios
            spiking_domains = context.get("spiking_domains", [])
            return len(spiking_domains) >= self.conditions.get("min_domains", 2)

        return False


class AlertHandler:
    """
    Handler base para processamento de alertas.

    Subclasses devem implementar o método handle().
    """

    def __init__(self, name: str):
        self.name = name

    def handle(self, alert: RiskAlert) -> bool:
        """
        Processa alerta.

        Args:
            alert: Alerta a ser processado

        Returns:
            True se processado com sucesso, False caso contrário

        Raises:
            NotImplementedError: Se a subclasse não implementar este método
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement handle()")


class LoggingAlertHandler(AlertHandler):
    """Handler que loga alertas."""

    def __init__(self):
        super().__init__("logging")

    def handle(self, alert: RiskAlert) -> bool:
        """Loga alerta com nível apropriado."""
        log_func = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.ERROR: logger.error,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(alert.severity, logger.info)

        log_func(
            "risk_alert",
            alert_id=alert.id,
            alert_type=alert.alert_type.value,
            severity=alert.severity.value,
            entity_id=alert.entity_id,
            domain=alert.domain.value if alert.domain else None,
            score=alert.score,
            band=alert.band.value,
            message=alert.message,
        )

        return True


class CallbackAlertHandler(AlertHandler):
    """Handler que executa callback."""

    def __init__(self, name: str, callback: Callable[[RiskAlert], bool]):
        super().__init__(name)
        self.callback = callback

    def handle(self, alert: RiskAlert) -> bool:
        """Executa callback."""
        try:
            return self.callback(alert)
        except Exception as e:
            logger.error(
                "alert_callback_failed",
                handler=self.name,
                alert_id=alert.id,
                error=str(e),
            )
            return False


class RiskAlertManager:
    """Gerencia alertas de risco."""

    def __init__(
        self,
        threshold_monitor: ThresholdMonitor,
        risk_history: RiskHistory,
        config: Optional[RiskScoringConfig] = None,
    ):
        """Inicializa gerenciador de alertas.

        Args:
            threshold_monitor: Monitor de thresholds
            risk_history: Histórico de risco
            config: Configuração de risk scoring
        """
        self.threshold_monitor = threshold_monitor
        self.risk_history = risk_history
        self.config = config

        # Regras de alerta
        self._rules: list[AlertRule] = self._default_rules()

        # Histórico de alertas
        self._alerts: list[RiskAlert] = []
        self._alerts_by_entity: dict[str, list[RiskAlert]] = defaultdict(list)
        self._last_alert_time: dict[Tuple[str, AlertType], datetime] = {}

        # Estado para detecção de padrões
        self._consecutive_high_risk: dict[str, int] = defaultdict(int)
        self._previous_scores: dict[str, float] = {}

        # Handlers
        self._handlers: list[AlertHandler] = [LoggingAlertHandler()]

        # Contador de IDs
        self._alert_id_counter = 0

    def _default_rules(self) -> list[AlertRule]:
        """Retorna regras padrão."""
        return [
            AlertRule(
                name="threshold_violation_critical",
                alert_type=AlertType.THRESHOLD_VIOLATION,
                min_severity=AlertSeverity.CRITICAL,
                cooldown_minutes=30,
            ),
            AlertRule(
                name="anomaly_high_severity",
                alert_type=AlertType.ANOMALY_DETECTED,
                min_severity=AlertSeverity.ERROR,
                cooldown_minutes=60,
                conditions={"min_severity": "high"},
            ),
            AlertRule(
                name="trend_worsening",
                alert_type=AlertType.TREND_WORSENING,
                min_severity=AlertSeverity.WARNING,
                cooldown_minutes=120,
            ),
            AlertRule(
                name="rapid_escalation",
                alert_type=AlertType.RAPID_ESCALATION,
                min_severity=AlertSeverity.WARNING,
                cooldown_minutes=60,
                conditions={"max_escalation_rate": 0.3},
            ),
            AlertRule(
                name="consecutive_high_risk",
                alert_type=AlertType.CONSECUTIVE_HIGH_RISK,
                min_severity=AlertSeverity.WARNING,
                cooldown_minutes=180,
                conditions={"min_consecutive": 3},
            ),
        ]

    def add_rule(self, rule: AlertRule):
        """Adiciona regra de alerta."""
        self._rules.append(rule)
        logger.info("alert_rule_added", rule_name=rule.name)

    def add_handler(self, handler: AlertHandler):
        """Adiciona handler de alerta."""
        self._handlers.append(handler)
        logger.info("alert_handler_added", handler_name=handler.name)

    def process_assessment(self, assessment: RiskAssessment, entity_id: str) -> list[RiskAlert]:
        """Processa avaliação e gera alertas se necessário.

        Args:
            assessment: Avaliação de risco
            entity_id: ID da entidade

        Returns:
            Lista de alertas gerados
        """
        generated_alerts = []

        # Contexto para avaliação de regras
        context = self._build_context(assessment, entity_id)

        # Verificar cada regra
        for rule in self._rules:
            last_alert_time = self._last_alert_time.get((entity_id, rule.alert_type))

            if rule.should_trigger(entity_id, context, last_alert_time):
                alert = self._create_alert(rule, assessment, entity_id, context)
                if alert:
                    generated_alerts.append(alert)
                    self._store_alert(alert)
                    self._last_alert_time[(entity_id, rule.alert_type)] = alert.timestamp

        # Notificar handlers
        for alert in generated_alerts:
            for handler in self._handlers:
                try:
                    handler.handle(alert)
                except Exception as e:
                    logger.error(
                        "alert_handler_error",
                        handler=handler.name,
                        alert_id=alert.id,
                        error=str(e),
                    )

        # Atualizar estado
        self._update_state(assessment, entity_id)

        return generated_alerts

    def _build_context(self, assessment: RiskAssessment, entity_id: str) -> dict[str, Any]:
        """Constrói contexto para avaliação de regras."""
        context = {
            "assessment": assessment,
            "entity_id": entity_id,
            "domain": assessment.domain,
            "score": assessment.score,
            "band": assessment.band,
        }

        # Verificar violação de threshold
        violation = self.threshold_monitor.check_violation(assessment.domain, assessment.score)
        context["threshold_violation"] = violation is not None
        context["violation"] = violation

        # Detectar anomalia
        anomaly = self.risk_history.detect_anomaly(entity_id, assessment.domain)
        context["anomaly"] = anomaly

        # Analisar tendência
        trend = self.risk_history.analyze_trend(entity_id, assessment.domain)
        context["trend"] = trend

        # Calcular delta de score
        previous_score = self._previous_scores.get(entity_id)
        if previous_score is not None:
            score_delta = assessment.score - previous_score
            context["score_delta"] = score_delta
            context["time_delta_hours"] = 1.0  # Simplificado
        else:
            context["score_delta"] = 0.0
            context["time_delta_hours"] = 1.0

        # Contar risco alto consecutivo
        if assessment.band in [RiskBand.HIGH, RiskBand.CRITICAL]:
            self._consecutive_high_risk[entity_id] += 1
        else:
            self._consecutive_high_risk[entity_id] = 0

        context["consecutive_high_risk_count"] = self._consecutive_high_risk.get(entity_id, 0)

        return context

    def _create_alert(
        self,
        rule: AlertRule,
        assessment: RiskAssessment,
        entity_id: str,
        context: dict[str, Any],
    ) -> Optional[RiskAlert]:
        """Cria alerta baseado na regra."""
        self._alert_id_counter += 1
        alert_id = f"ALT-{datetime.now(UTC).strftime('%Y%m%d')}-{self._alert_id_counter:06d}"

        # Determinar severidade
        severity = self._determine_severity(rule, assessment, context)

        # Gerar mensagem
        message = self._generate_message(rule, assessment, context)

        # Detalhes
        details = {
            "rule_name": rule.name,
            "factors": assessment.factors.copy(),
        }

        if context.get("violation"):
            details["violation"] = context["violation"].to_dict()
        if context.get("anomaly"):
            details["anomaly"] = {
                "is_anomaly": context["anomaly"].is_anomaly,
                "severity": context["anomaly"].severity,
            }
        if context.get("trend"):
            details["trend"] = {
                "direction": context["trend"].direction.value,
                "delta": context["trend"].delta,
            }

        alert = RiskAlert(
            id=alert_id,
            alert_type=rule.alert_type,
            severity=severity,
            entity_id=entity_id,
            domain=assessment.domain,
            score=assessment.score,
            band=assessment.band,
            message=message,
            details=details,
        )

        return alert

    def _determine_severity(
        self, rule: AlertRule, assessment: RiskAssessment, context: dict[str, Any]
    ) -> AlertSeverity:
        """Determina severidade do alerta."""
        # Baseado na band
        if assessment.band == RiskBand.CRITICAL:
            return AlertSeverity.CRITICAL
        elif assessment.band == RiskBand.HIGH:
            return AlertSeverity.ERROR
        elif assessment.band == RiskBand.MEDIUM:
            return AlertSeverity.WARNING
        else:
            return AlertSeverity.INFO

    def _generate_message(
        self, rule: AlertRule, assessment: RiskAssessment, context: dict[str, Any]
    ) -> str:
        """Gera mensagem do alerta."""
        entity_id = context.get("entity_id", "unknown")
        score_delta = context.get("score_delta", 0)
        consecutive_count = context.get("consecutive_high_risk_count", 0)

        templates = {
            AlertType.THRESHOLD_VIOLATION: (
                "Threshold violation for {entity_id}: "
                "score {score:.2f} exceeds "
                "{band} threshold"
            ),
            AlertType.ANOMALY_DETECTED: (
                "Anomaly detected for {entity_id} " "in {domain} domain: " "score {score:.2f}"
            ),
            AlertType.TREND_WORSENING: (
                "Worsening trend detected for {entity_id}: "
                "risk score increasing in {domain} domain"
            ),
            AlertType.RAPID_ESCALATION: (
                "Rapid risk escalation for {entity_id}: "
                "score increased by {score_delta:.2f} "
                "in {domain} domain"
            ),
            AlertType.CONSECUTIVE_HIGH_RISK: (
                "Consecutive high risk for {entity_id}: "
                "{consecutive_count} "
                "consecutive {band} assessments "
                "in {domain} domain"
            ),
            AlertType.CROSS_DOMAIN_SPIKE: (
                "Cross-domain spike detected for {entity_id}: " "risk elevated in multiple domains"
            ),
        }

        template = templates.get(rule.alert_type, "Risk alert for {entity_id}")

        # Personalizar mensagem
        message = template.format(
            entity_id=entity_id,
            score=assessment.score,
            band=assessment.band.value,
            domain=assessment.domain.value,
            score_delta=score_delta,
            consecutive_count=consecutive_count,
        )

        return message

    def _store_alert(self, alert: RiskAlert):
        """Armazena alerta."""
        self._alerts.append(alert)
        self._alerts_by_entity[alert.entity_id].append(alert)

        # Manter apenas últimos 1000 alertas
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-1000:]

    def _update_state(self, assessment: RiskAssessment, entity_id: str):
        """Atualiza estado interno."""
        self._previous_scores[entity_id] = assessment.score

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Confirma alerta.

        Args:
            alert_id: ID do alerta
            acknowledged_by: Usuário que confirmou

        Returns:
            True se confirmado com sucesso
        """
        for alert in self._alerts:
            if alert.id == alert_id and not alert.acknowledged:
                alert.acknowledged = True
                alert.acknowledged_by = acknowledged_by
                alert.acknowledged_at = datetime.now(UTC)

                logger.info(
                    "alert_acknowledged",
                    alert_id=alert_id,
                    acknowledged_by=acknowledged_by,
                )

                return True

        return False

    def resolve_alert(self, alert_id: str, resolved_by: str) -> bool:
        """Resolve alerta.

        Args:
            alert_id: ID do alerta
            resolved_by: Usuário que resolveu

        Returns:
            True se resolvido com sucesso
        """
        for alert in self._alerts:
            if alert.id == alert_id and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = datetime.now(UTC)

                logger.info("alert_resolved", alert_id=alert_id, resolved_by=resolved_by)

                return True

        return False

    def get_alerts(
        self,
        entity_id: Optional[str] = None,
        alert_type: Optional[AlertType] = None,
        severity: Optional[AlertSeverity] = None,
        unacknowledged_only: bool = False,
        unresolved_only: bool = False,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[RiskAlert]:
        """Retorna alertas filtrados.

        Args:
            entity_id: Filtrar por entidade
            alert_type: Filtrar por tipo
            severity: Filtrar por severidade
            unacknowledged_only: Apenas não confirmados
            unresolved_only: Apenas não resolvidos
            start: Data inicial
            end: Data final
            limit: Limite de resultados

        Returns:
            Lista de alertas
        """
        alerts = self._alerts

        if entity_id:
            alerts = self._alerts_by_entity.get(entity_id, [])

        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]

        if unresolved_only:
            alerts = [a for a in alerts if not a.resolved]

        if start:
            alerts = [a for a in alerts if a.timestamp >= start]

        if end:
            alerts = [a for a in alerts if a.timestamp <= end]

        # Ordenar por timestamp (mais recente primeiro)
        alerts = sorted(alerts, key=lambda a: a.timestamp, reverse=True)

        if limit:
            alerts = alerts[:limit]

        return alerts

    def get_alert_stats(self) -> dict:
        """Retorna estatísticas de alertas."""
        total = len(self._alerts)
        unacknowledged = sum(1 for a in self._alerts if not a.acknowledged)
        unresolved = sum(1 for a in self._alerts if not a.resolved)

        # Por tipo
        by_type: dict[str, int] = defaultdict(int)
        for a in self._alerts:
            by_type[a.alert_type.value] += 1

        # Por severidade
        by_severity: dict[str, int] = defaultdict(int)
        for a in self._alerts:
            by_severity[a.severity.value] += 1

        # Por entidade (top 10)
        by_entity: dict[str, int] = defaultdict(int)
        for a in self._alerts:
            by_entity[a.entity_id] += 1
        top_entities = sorted(by_entity.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_alerts": total,
            "unacknowledged": unacknowledged,
            "unresolved": unresolved,
            "by_type": dict(by_type),
            "by_severity": dict(by_severity),
            "top_entities": top_entities,
        }

    def cleanup_old_alerts(self, days: int = 30):
        """Remove alertas antigos."""
        cutoff = datetime.now(UTC) - timedelta(days=days)

        self._alerts = [a for a in self._alerts if a.timestamp >= cutoff]

        # Rebuild índice
        self._alerts_by_entity = defaultdict(list)
        for alert in self._alerts:
            self._alerts_by_entity[alert.entity_id].append(alert)

        logger.info("old_alerts_cleaned", cutoff=cutoff.isoformat())
