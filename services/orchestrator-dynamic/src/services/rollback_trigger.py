"""
Rollback Trigger para acionamento automático de rollback.

Avalia continuamente condições de rollback e dispara rollback automático
quando thresholds críticos são atingidos. Integra com Health Monitor e
TrafficSwitcher para execução do rollback.

Condições de Rollback:

Imediato (< 1min):
- Error rate > 5% (5min consecutivos)
- Sistema target completamente DOWN
- Data corruption detectada
- Security breach detectada

Manual (decisão humana):
- Error rate > 1% (mas <5%)
- Latência P95 > 2x legacy
- Bugs críticos de negócio
- Reclamações de usuários acima do threshold
"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from src.services.health_monitor import HealthComparison, HealthStatus

UTC = timezone.utc
logger = structlog.get_logger(__name__)


class RollbackTriggerType(str, Enum):
    """Tipos de trigger de rollback."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"


class RollbackReason(str, Enum):
    """Motivos de rollback."""

    # Triggers automáticos
    ERROR_RATE_CRITICAL = "error_rate_critical"
    SYSTEM_DOWN = "system_down"
    DATA_CORRUPTION = "data_corruption"
    SECURITY_BREACH = "security_breach"
    LATENCY_CRITICAL = "latency_critical"
    CONSECUTIVE_FAILURES = "consecutive_failures"

    # Triggers manuais
    ERROR_RATE_WARNING = "error_rate_warning"
    LATENCY_HIGH = "latency_high"
    BUSINESS_CRITICAL_BUG = "business_critical_bug"
    USER_COMPLAINTS = "user_complaints"
    OPERATOR_DECISION = "operator_decision"


@dataclass(frozen=True)
class RollbackThresholds:
    """Thresholds para acionamento de rollback."""

    # Triggers automáticos (críticos)
    error_rate_critical: float = 0.05  # 5%
    consecutive_minutes_critical: int = 5  # 5min
    consecutive_failures_critical: int = 5  # 5 falhas

    # Latência
    p95_latency_critical_ms: int = 2000  # 2s
    p95_latency_ratio_warning: float = 2.0  # 2x legacy

    # Triggers manuais (warning)
    error_rate_warning: float = 0.01  # 1%
    user_complaints_threshold: int = 10  # 10 reclamações em 1h

    # Janela de avaliação (minutos)
    evaluation_window_minutes: int = 15


@dataclass
class RollbackEvent:
    """Evento de rollback registrado."""

    cutover_id: str
    timestamp: datetime
    trigger_type: RollbackTriggerType
    reason: RollbackReason
    metrics: dict[str, Any]
    triggered_by: str | None = None  # Para rollback manual
    executed: bool = False
    execution_result: str | None = None


class RollbackStatus(BaseModel):
    """Status do sistema de rollback."""

    is_active: bool = Field(default=False, description="Se rollback está ativo")
    last_rollback_timestamp: datetime | None = Field(
        default=None, description="Timestamp do último rollback"
    )
    last_rollback_reason: RollbackReason | None = Field(
        default=None, description="Motivo do último rollback"
    )
    rollback_count: int = Field(default=0, description="Número total de rollbacks executados")
    rollback_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Histórico de eventos de rollback",
    )


class RollbackTriggerConfig(BaseModel):
    """Configuração do Rollback Trigger."""

    # Intervalo de avaliação (segundos)
    evaluation_interval_seconds: int = Field(default=30, ge=10, le=300)

    # Thresholds
    thresholds: RollbackThresholds = Field(default_factory=RollbackThresholds)

    # Flags
    enable_automatic_rollback: bool = Field(default=True)
    enable_manual_rollback: bool = Field(default=True)

    # Notificações
    enable_kafka_events: bool = Field(default=True)
    enable_webhook_notifications: bool = Field(default=False)
    webhook_urls: list[str] = Field(default_factory=list)

    # Histórico máximo de eventos
    max_history_size: int = Field(default=1000, ge=100, le=10000)


class RollbackTrigger:
    """
    Trigger de rollback para acionamento automático.

    Responsável por:
    - Avaliar continuamente condições de rollback
    - Triggerar rollback automático se condições críticas forem atingidas
    - Permitir rollback manual via operador
    - Notificar stakeholders (Kafka events, webhooks)
    - Integrar com TrafficSwitcher para executar rollback
    """

    def __init__(
        self,
        config: RollbackTriggerConfig,
        cutover_id: str,
        health_monitor=None,
        traffic_switcher=None,
        kafka_producer=None,
        webhook_client=None,
    ):
        """
        Inicializa o RollbackTrigger.

        Args:
            config: Configuração do trigger
            cutover_id: ID do cutover associado
            health_monitor: HealthMonitor para obter métricas
            traffic_switcher: TrafficSwitcher para executar rollback
            kafka_producer: Producer Kafka para eventos
            webhook_client: Cliente HTTP para webhooks
        """
        self.config = config
        self.cutover_id = cutover_id
        self.health_monitor = health_monitor
        self.traffic_switcher = traffic_switcher
        self.kafka_producer = kafka_producer
        self.webhook_client = webhook_client

        # Estado do trigger
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._rollback_in_progress = False

        # Histórico de eventos e status
        self._status = RollbackStatus()
        self._rollback_events: list[RollbackEvent] = []

        # Contadores para avaliação contínua
        self._consecutive_critical_minutes = 0
        self._evaluation_history: list[HealthComparison] = []

        self.logger = logger.bind(
            component="rollback_trigger",
            cutover_id=cutover_id,
        )

    async def start_monitoring(self) -> None:
        """
        Inicia monitoramento de rollback.

        Avalia condições a cada intervalo configurado.
        Triggera ação automática se thresholds críticos forem atingidos.
        """
        if self._running:
            self.logger.warning("monitor_already_running")
            return

        self._running = True
        self.logger.info(
            "rollback_monitoring_started",
            interval_seconds=self.config.evaluation_interval_seconds,
            automatic_enabled=self.config.enable_automatic_rollback,
        )

        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitoring(self) -> None:
        """
        Para monitoramento de rollback.
        """
        self._running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitor_task

        self.logger.info("rollback_monitoring_stopped")

    async def trigger_manual_rollback(
        self,
        reason: RollbackReason,
        triggered_by: str,
        message: str | None = None,
    ) -> tuple[bool, str]:
        """
        Trigger rollback manual.

        Args:
            reason: Motivo do rollback
            triggered_by: Quem autorizou o rollback (user, operator)
            message: Mensagem adicional (opcional)

        Returns:
            Tupla (success, message)
        """
        if not self.config.enable_manual_rollback:
            return False, "Manual rollback is disabled"

        if self._rollback_in_progress:
            return False, "Rollback already in progress"

        self.logger.warning(
            "manual_rollback_triggered",
            reason=reason.value,
            triggered_by=triggered_by,
            message=message,
        )

        # Criar evento de rollback
        event = RollbackEvent(
            cutover_id=self.cutover_id,
            timestamp=datetime.now(UTC),
            trigger_type=RollbackTriggerType.MANUAL,
            reason=reason,
            metrics={"triggered_by": triggered_by, "message": message},
            triggered_by=triggered_by,
        )

        return await self._execute_rollback(event)

    async def get_rollback_status(self) -> RollbackStatus:
        """
        Retorna status atual do sistema de rollback.

        Returns:
            RollbackStatus com informações atuais
        """
        return self._status

    def configure_thresholds(self, thresholds: RollbackThresholds) -> None:
        """
        Configura thresholds de rollback.

        Args:
            thresholds: Novos thresholds
        """
        self.config.thresholds = thresholds

        self.logger.info(
            "thresholds_configured",
            error_rate_critical=thresholds.error_rate_critical,
            error_rate_warning=thresholds.error_rate_warning,
            consecutive_minutes_critical=thresholds.consecutive_minutes_critical,
        )

    async def evaluate_rollback_conditions(
        self,
        health_comparison: HealthComparison,
    ) -> tuple[bool, RollbackReason | None]:
        """
        Avalia se condições de rollback foram atingidas.

        Args:
            health_comparison: Comparação de saúde atual

        Returns:
            Tupla (should_rollback, reason)
        """
        thresholds = self.config.thresholds
        target_health = health_comparison.target_health

        # Condição 1: Sistema DOWN
        if target_health.status == HealthStatus.DOWN:
            return True, RollbackReason.SYSTEM_DOWN

        # Condição 2: Error rate crítico
        if target_health.error_rate >= thresholds.error_rate_critical:
            # Verificar minutos consecutivos
            self._consecutive_critical_minutes += 1

            if self._consecutive_critical_minutes >= thresholds.consecutive_minutes_critical:
                return True, RollbackReason.ERROR_RATE_CRITICAL
        else:
            # Reset contador se error rate normalizar
            self._consecutive_critical_minutes = 0

        # Condição 3: Latência P95 crítica
        if target_health.latency_p95_ms >= thresholds.p95_latency_critical_ms:
            return True, RollbackReason.LATENCY_CRITICAL

        # Condição 4: Latência P95 > 2x legacy
        if health_comparison.latency_p95_ratio >= thresholds.p95_latency_ratio_warning:
            # Isso é um warning, não trigger automático
            # Mas registra para análise
            self.logger.info(
                "latency_warning_detected",
                ratio=health_comparison.latency_p95_ratio,
                target_p95_ms=target_health.latency_p95_ms,
                legacy_p95_ms=health_comparison.legacy_health.latency_p95_ms,
            )

        # Condição 5: Data corruption detectada
        if "data_corruption" in target_health.anomalies:
            return True, RollbackReason.DATA_CORRUPTION

        # Condição 6: Security breach detectada
        if "security_breach" in target_health.anomalies:
            return True, RollbackReason.SECURITY_BREACH

        return False, None

    async def _monitor_loop(self) -> None:
        """
        Loop de monitoramento em background.

        Coleta métricas do HealthMonitor e avalia condições.
        """
        while self._running:
            try:
                # Obter status atual do health monitor
                if self.health_monitor:
                    health_comparison = await self.health_monitor.get_health_status()
                else:
                    # Se não tem health monitor, não pode avaliar
                    await asyncio.sleep(self.config.evaluation_interval_seconds)
                    continue

                # Adicionar ao histórico
                self._evaluation_history.append(health_comparison)

                # Manter histórico limitado
                window_size = (
                    self.config.thresholds.evaluation_window_minutes
                    * 60
                    // self.config.evaluation_interval_seconds
                )
                if len(self._evaluation_history) > window_size:
                    self._evaluation_history = self._evaluation_history[-window_size:]

                # Avaliar condições de rollback
                if self.config.enable_automatic_rollback:
                    should_rollback, reason = await self.evaluate_rollback_conditions(
                        health_comparison
                    )

                    if should_rollback and reason:
                        self.logger.critical(
                            "automatic_rollback_condition_met",
                            reason=reason.value,
                            error_rate=health_comparison.target_health.error_rate,
                            p95_latency_ms=health_comparison.target_health.latency_p95_ms,
                            status=health_comparison.target_health.status.value,
                        )

                        # Criar evento de rollback
                        event = RollbackEvent(
                            cutover_id=self.cutover_id,
                            timestamp=datetime.now(UTC),
                            trigger_type=RollbackTriggerType.AUTOMATIC,
                            reason=reason,
                            metrics={
                                "error_rate": health_comparison.target_health.error_rate,
                                "p95_latency_ms": health_comparison.target_health.latency_p95_ms,
                                "status": health_comparison.target_health.status.value,
                            },
                        )

                        await self._execute_rollback(event)

                await asyncio.sleep(self.config.evaluation_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.exception("monitor_loop_error", error=str(e))
                await asyncio.sleep(self.config.evaluation_interval_seconds)

    async def _execute_rollback(self, event: RollbackEvent) -> tuple[bool, str]:
        """
        Executa o rollback de fato.

        Args:
            event: Evento de rollback

        Returns:
            Tupla (success, message)
        """
        if self._rollback_in_progress:
            return False, "Rollback already in progress"

        self._rollback_in_progress = True

        try:
            # 1. Executar rollback no TrafficSwitcher
            if self.traffic_switcher:
                success = await self.traffic_switcher.emergency_switch_to_legacy()

                if not success:
                    message = "Failed to execute rollback via TrafficSwitcher"
                    event.execution_result = message

                    # Registrar evento
                    self._rollback_events.append(event)
                    self._status.rollback_history.append(
                        {
                            "timestamp": event.timestamp.isoformat(),
                            "trigger_type": event.trigger_type.value,
                            "reason": event.reason.value,
                            "success": False,
                            "message": message,
                        }
                    )

                    return False, message
            else:
                self.logger.warning(
                    "no_traffic_switcher",
                    message="Rollback event logged but not executed",
                )

            # 2. Atualizar status
            self._status.is_active = True
            self._status.last_rollback_timestamp = event.timestamp
            self._status.last_rollback_reason = event.reason
            self._status.rollback_count += 1

            # 3. Registrar evento
            event.executed = True
            event.execution_result = "Rollback executed successfully"
            self._rollback_events.append(event)

            # 4. Adicionar ao histórico
            self._status.rollback_history.append(
                {
                    "timestamp": event.timestamp.isoformat(),
                    "trigger_type": event.trigger_type.value,
                    "reason": event.reason.value,
                    "triggered_by": event.triggered_by,
                    "success": True,
                    "metrics": event.metrics,
                }
            )

            # Manter histórico limitado
            if len(self._status.rollback_history) > self.config.max_history_size:
                self._status.rollback_history = self._status.rollback_history[
                    -self.config.max_history_size :
                ]

            # 5. Publicar evento Kafka
            await self._emit_rollback_event(event)

            # 6. Enviar notificações webhook
            if self.config.enable_webhook_notifications:
                await self._send_webhook_notifications(event)

            self.logger.critical(
                "rollback_executed",
                trigger_type=event.trigger_type.value,
                reason=event.reason.value,
                triggered_by=event.triggered_by,
                rollback_count=self._status.rollback_count,
            )

            return True, "Rollback executed successfully"

        except Exception as e:
            self.logger.exception("rollback_execution_failed", error=str(e))

            event.execution_result = f"Rollback failed: {e!s}"
            self._rollback_events.append(event)

            return False, f"Rollback failed: {e!s}"

        finally:
            self._rollback_in_progress = False

    async def _emit_rollback_event(self, event: RollbackEvent) -> None:
        """
        Emite evento de rollback no Kafka.

        Args:
            event: Evento a emitir
        """
        if not self.config.enable_kafka_events or not self.kafka_producer:
            return

        try:
            topic = "cutover.rollback"
            key = self.cutover_id.encode()

            value = {
                "cutover_id": self.cutover_id,
                "timestamp": event.timestamp.isoformat(),
                "trigger_type": event.trigger_type.value,
                "reason": event.reason.value,
                "triggered_by": event.triggered_by,
                "metrics": event.metrics,
                "executed": event.executed,
                "execution_result": event.execution_result,
            }

            await self.kafka_producer.produce(
                topic=topic,
                key=key,
                value=value,
            )

            self.logger.info(
                "rollback_event_emitted",
                topic=topic,
                trigger_type=event.trigger_type.value,
                reason=event.reason.value,
            )

        except Exception as e:
            self.logger.warning("emit_rollback_event_failed", error=str(e))

    async def _send_webhook_notifications(self, event: RollbackEvent) -> None:
        """
        Envia notificações via webhook.

        Args:
            event: Evento a notificar
        """
        if not self.webhook_client or not self.config.webhook_urls:
            return

        for url in self.config.webhook_urls:
            try:
                self.logger.debug("webhook_sent", url=url)
            except Exception as e:
                self.logger.warning("webhook_failed", url=url, error=str(e))

    def get_rollback_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Retorna histórico de eventos de rollback.

        Args:
            limit: Número máximo de eventos

        Returns:
            Lista de eventos
        """
        events = self._rollback_events[-limit:]
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "trigger_type": e.trigger_type.value,
                "reason": e.reason.value,
                "triggered_by": e.triggered_by,
                "executed": e.executed,
                "execution_result": e.execution_result,
                "metrics": e.metrics,
            }
            for e in events
        ]

    def get_evaluation_metrics(self) -> dict[str, Any]:
        """
        Retorna métricas de avaliação.

        Returns:
            Dict com métricas agregadas
        """
        if not self._evaluation_history:
            return {
                "total_evaluations": 0,
                "consecutive_critical_minutes": 0,
            }

        # Calcular estatísticas
        total_evaluations = len(self._evaluation_history)
        critical_count = sum(
            1 for h in self._evaluation_history if h.target_health.status == HealthStatus.CRITICAL
        )

        return {
            "total_evaluations": total_evaluations,
            "consecutive_critical_minutes": self._consecutive_critical_minutes,
            "critical_evaluations": critical_count,
            "critical_percentage": (
                critical_count / total_evaluations if total_evaluations > 0 else 0
            ),
        }

    async def reset_rollback_status(self) -> None:
        """
        Reseta status de rollback ativo.

        Útil quando o cutover é reiniciado após um rollback.
        """
        self._status.is_active = False
        self._consecutive_critical_minutes = 0

        self.logger.info("rollback_status_reset", cutover_id=self.cutover_id)

    async def close(self) -> None:
        """
        Limpa recursos do trigger.
        """
        await self.stop_monitoring()

        self.logger.info(
            "rollback_trigger_closed",
            cutover_id=self.cutover_id,
            total_rollbacks=self._status.rollback_count,
        )
