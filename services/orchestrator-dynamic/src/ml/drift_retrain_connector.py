"""
Drift-Retrain Connector - Integra Drift Detection com Auto-Retrain.

Funcionalidade:
- Recebe alertas de drift do DriftDetector
- Avalia se o drift justifica retrain
- Trigger AutoRetrainOrchestrator se necessário
- Monitora e reporta status

FASE 0 - IA/ML Integration
"""

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

import structlog

from ..notifications import NotificationManager, get_notification_manager

logger = structlog.get_logger(__name__)


@dataclass
class DriftAlert:
    """Alerta de drift."""

    timestamp: datetime
    model_name: str
    model_version: str
    drift_type: str  # "feature", "prediction", "target"
    severity: str  # "ok", "warning", "critical"
    score: float
    details: Dict[str, Any]


@dataclass
class RetrainDecision:
    """Decisão de retrain."""

    should_retrain: bool
    reason: str
    priority: str  # "low", "medium", "high", "critical"
    estimated_duration_minutes: int


class DriftRetrainConnector:
    """
    Conecta drift detection com auto-retrain.

    Avalia alertas de drift e decide se deve trigger retrain.
    """

    # Thresholds para decisão de retrain
    DEFAULT_THRESHOLDS = {
        "critical_psi": 0.4,  # PSI acima disso = retrain imediato
        "critical_mae_ratio": 2.0,  # MAE ratio acima disso = retrain imediato
        "warning_psi": 0.3,  # PSI acima disso = considerar retrain
        "warning_mae_ratio": 1.7,  # MAE ratio acima disso = considerar retrain
        "min_time_between_retrains_hours": 6,  # Tempo mínimo entre retrains
        "max_retrains_per_day": 2,  # Máximo de retrains por dia
    }

    def __init__(
        self,
        orchestrator_settings: Any = None,
        on_retrain_callback: Optional[Callable] = None,
        thresholds: Optional[Dict[str, float]] = None,
        enable_auto_retrain: bool = True,
        notification_manager: Optional[NotificationManager] = None,
    ):
        """
        Inicializa o connector.

        Args:
            orchestrator_settings: Configurações do orchestrator
            on_retrain_callback: Callback para executar retrain
            thresholds: Thresholds customizados
            enable_auto_retrain: Habilita auto-retrain
            notification_manager: Gerenciador de notificações
        """
        self.orchestrator_settings = orchestrator_settings
        self.on_retrain_callback = on_retrain_callback
        self.enable_auto_retrain = enable_auto_retrain

        # Load thresholds
        self.thresholds = {**self.DEFAULT_THRESHOLDS}
        if thresholds:
            self.thresholds.update(thresholds)

        # Load from settings if available
        if orchestrator_settings:
            for key in self.DEFAULT_THRESHOLDS:
                setting_key = f"ml_retrain_{key}"
                if hasattr(orchestrator_settings, setting_key):
                    self.thresholds[key] = getattr(orchestrator_settings, setting_key)

        # Track retrain history
        self._retrain_history: Dict[str, list] = {}  # model_name -> [timestamps]
        self._last_retrain_time: Optional[datetime] = None

        # Inicializa gerenciador de notificações
        self.notification_manager = notification_manager

        logger.info(
            "drift_retrain_connector_initialized",
            enable_auto_retrain=self.enable_auto_retrain,
            thresholds=self.thresholds,
            notifications_enabled=notification_manager is not None,
        )

    def evaluate_drift_alert(self, alert: DriftAlert) -> RetrainDecision:
        """
        Avalia um alerta de drift e decide se deve retrain.

        Args:
            alert: Alerta de drift

        Returns:
            RetrainDecision
        """
        logger.info(
            "evaluating_drift_alert",
            model_name=alert.model_name,
            drift_type=alert.drift_type,
            severity=alert.severity,
            score=alert.score,
        )

        # 1. Check severity - critical sempre retrain
        if alert.severity == "critical":
            return self._create_critical_decision(alert)

        # 2. Check warning levels
        if alert.severity == "warning":
            return self._create_warning_decision(alert)

        # 3. OK - no retrain needed
        return RetrainDecision(
            should_retrain=False,
            reason=f"Drift score {alert.score:.3f} dentro do limite normal",
            priority="low",
            estimated_duration_minutes=0,
        )

    def _create_critical_decision(self, alert: DriftAlert) -> RetrainDecision:
        """Cria decisão para drift crítico."""
        # Check rate limiting
        if not self._can_retrain(alert.model_name):
            return RetrainDecision(
                should_retrain=False,
                reason=f"Rate limiting: máximo de {self.thresholds['max_retrains_per_day']} retrains por dia ou "
                f"mínimo de {self.thresholds['min_time_between_retrains_hours']}h entre retrains",
                priority="medium",
                estimated_duration_minutes=0,
            )

        reason = f"Drift CRÍTICO detectado: {alert.drift_type}={alert.score:.3f}"

        if alert.drift_type == "feature":
            reason += f" (PSI > {self.thresholds['critical_psi']})"
        elif alert.drift_type == "prediction":
            reason += f" (MAE ratio > {self.thresholds['critical_mae_ratio']})"
        elif alert.drift_type == "target":
            reason += " (distribuição do target mudou significativamente)"

        return RetrainDecision(
            should_retrain=True,
            reason=reason,
            priority="critical",
            estimated_duration_minutes=60,
        )

    def _create_warning_decision(self, alert: DriftAlert) -> RetrainDecision:
        """Cria decisão para drift warning."""
        # Check if above warning threshold
        above_threshold = False

        if alert.drift_type == "feature" and alert.score > self.thresholds["warning_psi"]:
            above_threshold = True
        elif (
            alert.drift_type == "prediction"
            and alert.details.get("drift_ratio", 0) > self.thresholds["warning_mae_ratio"]
        ):
            above_threshold = True

        if not above_threshold:
            return RetrainDecision(
                should_retrain=False,
                reason="Drift warning dentro dos limites aceitáveis",
                priority="low",
                estimated_duration_minutes=0,
            )

        # Check rate limiting
        if not self._can_retrain(alert.model_name):
            return RetrainDecision(
                should_retrain=False,
                reason="Rate limiting: aguardar intervalo mínimo entre retrains",
                priority="medium",
                estimated_duration_minutes=0,
            )

        return RetrainDecision(
            should_retrain=True,
            reason=f"Drift WARNING acima do threshold: {alert.drift_type}={alert.score:.3f}",
            priority="medium",
            estimated_duration_minutes=60,
        )

    def _can_retrain(self, model_name: str) -> bool:
        """
        Verifica se pode fazer retrain (rate limiting).

        Args:
            model_name: Nome do modelo

        Returns:
            True se pode retrain
        """
        now = datetime.now()

        # Initialize history if needed
        if model_name not in self._retrain_history:
            self._retrain_history[model_name] = []

        # Clean old history (> 24h)
        cutoff = now - timedelta(hours=24)
        self._retrain_history[model_name] = [
            t for t in self._retrain_history[model_name] if t > cutoff
        ]

        # Check max per day
        if len(self._retrain_history[model_name]) >= self.thresholds["max_retrains_per_day"]:
            logger.warning(
                "max_retrains_per_day_reached",
                model_name=model_name,
                count=len(self._retrain_history[model_name]),
            )
            return False

        # Check min time between
        if self._last_retrain_time:
            elapsed = (now - self._last_retrain_time).total_seconds() / 3600
            if elapsed < self.thresholds["min_time_between_retrains_hours"]:
                logger.warning(
                    "min_time_between_retrains_not_met",
                    model_name=model_name,
                    elapsed_hours=elapsed,
                    required_hours=self.thresholds["min_time_between_retrains_hours"],
                )
                return False

        return True

    async def trigger_retrain_if_needed(self, alert: DriftAlert) -> Dict[str, Any]:
        """
        Trigger retrain se drift alert justificar.

        Args:
            alert: Alerta de drift

        Returns:
            Resultado do trigger
        """
        if not self.enable_auto_retrain:
            logger.info("auto_retrain_disabled_skipping", alert=alert)
            return {"triggered": False, "reason": "Auto-retrain desabilitado"}

        # Evaluate
        decision = self.evaluate_drift_alert(alert)

        logger.info(
            "retrain_decision",
            should_retrain=decision.should_retrain,
            reason=decision.reason,
            priority=decision.priority,
        )

        # Notifica drift detectado (independente de retrain)
        if self.notification_manager:
            try:
                await self.notification_manager.notify_drift_detected(
                    model_name=alert.model_name,
                    drift_type=alert.drift_type,
                    drift_score=alert.score,
                    severity=alert.severity,
                )
            except Exception as e:
                logger.warning(
                    "failed_to_send_drift_notification",
                    error=str(e),
                )

        if not decision.should_retrain:
            return {
                "triggered": False,
                "reason": decision.reason,
                "priority": decision.priority,
            }

        # Trigger retrain
        return await self._execute_retrain(alert, decision)

    async def _execute_retrain(
        self, alert: DriftAlert, decision: RetrainDecision
    ) -> Dict[str, Any]:
        """
        Executa o retrain.

        Args:
            alert: Alerta de drift
            decision: Decisão de retrain

        Returns:
            Resultado da execução
        """
        logger.info(
            "triggering_retrain",
            model_name=alert.model_name,
            reason=decision.reason,
            priority=decision.priority,
        )

        # Update history
        now = datetime.now()
        if alert.model_name not in self._retrain_history:
            self._retrain_history[alert.model_name] = []
        self._retrain_history[alert.model_name].append(now)
        self._last_retrain_time = now

        # Notifica início do retrain
        if self.notification_manager:
            try:
                await self.notification_manager.notify_retrain_triggered(
                    model_name=alert.model_name,
                    model_version=alert.model_version,
                    drift_type=alert.drift_type,
                    drift_score=alert.score,
                    priority=decision.priority,
                )
            except Exception as e:
                logger.warning(
                    "failed_to_send_retrain_triggered_notification",
                    error=str(e),
                )

        # Call callback if provided
        if self.on_retrain_callback:
            try:
                result = await self._run_callback(alert, decision)

                # Notifica sucesso do retrain
                if self.notification_manager and result.get("status") == "success":
                    try:
                        await self.notification_manager.notify_retrain_success(
                            model_name=alert.model_name,
                            model_version=alert.model_version,
                            new_version=result.get("new_version", "unknown"),
                            duration_seconds=result.get("duration_seconds", 0),
                            metrics=result.get("metrics"),
                        )
                    except Exception as e:
                        logger.warning(
                            "failed_to_send_retrain_success_notification",
                            error=str(e),
                        )

                # Notifica falha do retrain
                if self.notification_manager and result.get("status") == "failed":
                    try:
                        await self.notification_manager.notify_retrain_failed(
                            model_name=alert.model_name,
                            model_version=alert.model_version,
                            error_message=result.get("error", "Unknown error"),
                            retry_attempt=result.get("retry_attempt"),
                        )
                    except Exception as e:
                        logger.warning(
                            "failed_to_send_retrain_failed_notification",
                            error=str(e),
                        )

                return result
            except Exception as e:
                logger.error("retrain_callback_failed", error=str(e))

                # Notifica exceção durante retrain
                if self.notification_manager:
                    try:
                        await self.notification_manager.notify_retrain_failed(
                            model_name=alert.model_name,
                            model_version=alert.model_version,
                            error_message=str(e),
                        )
                    except Exception as notif_error:
                        logger.warning(
                            "failed_to_send_retrain_failed_notification",
                            error=str(notif_error),
                        )

                return {
                    "triggered": True,
                    "status": "failed",
                    "error": str(e),
                }
        else:
            # No callback - log only
            logger.warning(
                "no_retrain_callback_configured",
                model_name=alert.model_name,
                decision=decision,
            )
            return {
                "triggered": True,
                "status": "no_callback",
                "reason": "Nenhum callback de retrain configurado",
            }

    async def _run_callback(self, alert: DriftAlert, decision: RetrainDecision) -> Dict[str, Any]:
        """
        Executa o callback de retrain.

        Args:
            alert: Alerta de drift
            decision: Decisão de retrain

        Returns:
            Resultado
        """
        if asyncio.iscoroutinefunction(self.on_retrain_callback):
            return await self.on_retrain_callback(alert, decision)
        else:
            # Run in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.on_retrain_callback, alert, decision)

    def get_retrain_history(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna histórico de retrains.

        Args:
            model_name: Nome do modelo (opcional)

        Returns:
            Histórico de retrains
        """
        if model_name:
            history = self._retrain_history.get(model_name, [])
            return {
                "model_name": model_name,
                "retrain_count": len(history),
                "last_retrain": history[-1] if history else None,
                "history": [t.isoformat() for t in history],
            }

        return {
            name: {
                "count": len(times),
                "last": times[-1].isoformat() if times else None,
            }
            for name, times in self._retrain_history.items()
        }


def get_drift_retrain_connector(
    orchestrator_settings: Any = None,
    enable_auto_retrain: bool = None,
    enable_notifications: bool = None,
) -> DriftRetrainConnector:
    """
    Factory para DriftRetrainConnector.

    Args:
        orchestrator_settings: Configurações do orchestrator
        enable_auto_retrain: Habilita auto-retrain
        enable_notifications: Habilita notificações

    Returns:
        Instância de DriftRetrainConnector
    """
    if enable_auto_retrain is None:
        enable_auto_retrain = os.getenv("ML_AUTO_RETRAIN_ENABLED", "true").lower() == "true"

    # Inicializa gerenciador de notificações se habilitado
    notification_manager = None
    if enable_notifications is None:
        enable_notifications = os.getenv("ML_NOTIFICATIONS_ENABLED", "true").lower() == "true"

    if enable_notifications:
        try:
            notification_manager = get_notification_manager()
            logger.info("notification_manager_initialized_for_connector")
        except Exception as e:
            logger.warning(
                "failed_to_initialize_notification_manager",
                error=str(e),
            )

    return DriftRetrainConnector(
        orchestrator_settings=orchestrator_settings,
        enable_auto_retrain=enable_auto_retrain,
        notification_manager=notification_manager,
    )
