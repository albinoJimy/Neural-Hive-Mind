"""
Gerenciador de Cutover para migração gradual de sistemas.

Coordena o processo de cutover em múltiplas fases:
1. Shadow Mode - Execução paralela sem tráfego de produção
2. Canary Deployment - Tráfego gradual (5% → 25% → 50% → 100%)
3. Full Cutover - Tráfego total no novo sistema
4. Rollback automático em caso de falha
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog

from src.models.workflow import (
    CutoverConfig,
    CutoverEvent,
    CutoverMetrics,
    CutoverPhase,
    CutoverStatus,
    RollbackReason,
)

logger = structlog.get_logger(__name__)


def _get_phase_value(phase: CutoverPhase | str) -> str:
    """
    Retorna o valor string da fase, lidando com enum ou string.

    Args:
        phase: Fase como enum ou string

    Returns:
        Valor string da fase
    """
    if isinstance(phase, str):
        return phase
    return phase.value


class CutoverManager:
    """
    Gerencia o processo de cutover gradual.

    Responsável por:
    - Coletar métricas de ambos os sistemas (legacy e target)
    - Avaliar condições para promoção de fase
    - Executar rollback automático quando thresholds são excedidos
    - Publicar eventos de cutover no Kafka
    - Manter estado do cutover em MongoDB
    """

    def __init__(
        self,
        config: CutoverConfig,
        cutover_id: str | None = None,
        kafka_producer=None,
        mongodb_client=None,
        metrics_client=None,
    ):
        """
        Inicializa o CutoverManager.

        Args:
            config: Configuração do cutover
            cutover_id: ID existente (para retomada) ou None (novo cutover)
            kafka_producer: Producer Kafka para eventos cutover.*
            mongodb_client: Cliente MongoDB para persistência
            metrics_client: Cliente Prometheus/OpenTelemetry para métricas
        """
        self.config = config
        self.cutover_id = cutover_id or str(uuid.uuid4())
        self.kafka_producer = kafka_producer
        self.mongodb_client = mongodb_client
        self.metrics_client = metrics_client

        # Estado do cutover
        self.status = CutoverStatus(
            cutover_id=self.cutover_id,
            phase=CutoverPhase.SHADOW_MODE,
            traffic_percentage=0,
        )

        # Controle de execução
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._rollback_in_progress = False

        # Circuit breaker para falhas consecutivas
        self._consecutive_failures = 0
        self._max_consecutive_failures = 10

        self.logger = logger.bind(component="cutover_manager", cutover_id=self.cutover_id)

    async def start(self) -> CutoverStatus:
        """
        Inicia o processo de cutover.

        Returns:
            Status inicial do cutover
        """
        self._running = True
        self.status.started_at = datetime.now()
        self.status.current_phase_start = datetime.now()
        self.status.config_snapshot = self.config.model_dump()

        self.logger.info(
            "cutover_started",
            phase=_get_phase_value(self.status.phase),
            config=self.config.model_dump(),
        )

        # Persistir estado inicial
        await self._persist_status()

        # Publicar evento de início
        await self._emit_event(
            event_type="cutover.started",
            phase=self.status.phase,
            message=f"Cutover iniciado na fase {_get_phase_value(self.status.phase)}",
        )

        # Iniciar monitoramento em background
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        # Registrar métricas
        self._record_metrics("cutover_started", 1)

        return self.status

    async def pause(self) -> CutoverStatus:
        """
        Pausa o cutover na fase atual.

        Útil para investigação manual ou aguardando janela de manutenção.

        Returns:
            Status atual pausado
        """
        self._running = False

        self.logger.info(
            "cutover_paused",
            current_phase=_get_phase_value(self.status.phase),
            traffic_percentage=self.status.traffic_percentage,
        )

        await self._emit_event(
            event_type="cutover.paused",
            phase=self.status.phase,
            message=f"Cutover pausado na fase {_get_phase_value(self.status.phase)}",
        )

        return self.status

    async def resume(self) -> CutoverStatus:
        """
        Retoma cutover pausado.

        Returns:
            Status atual retomado
        """
        if self.status.phase == CutoverPhase.PAUSED:
            # Restaurar fase anterior
            self.status.phase = CutoverPhase.SHADOW_MODE

        self._running = True
        self.status.current_phase_start = datetime.now()

        # Reiniciar monitoramento
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop())

        self.logger.info(
            "cutover_resumed",
            current_phase=_get_phase_value(self.status.phase),
        )

        await self._emit_event(
            event_type="cutover.resumed",
            phase=self.status.phase,
            message=f"Cutover retomado na fase {_get_phase_value(self.status.phase)}",
        )

        return self.status

    async def promote_to_next_phase(self) -> tuple[bool, str]:
        """
        Promove manualmente para a próxima fase.

        Útil quando auto_promote está desabilitado.

        Returns:
            Tupla (success, message)
        """
        can_promote, reason = self.status.can_promote_to_next_phase(self.config)

        if not can_promote:
            self.logger.warning(
                "promotion_denied",
                reason=reason,
            )
            return False, reason

        next_phase = self._get_next_phase()
        return await self._transition_to(next_phase, trigger="manual")

    async def rollback(self, reason: RollbackReason, message: str | None = None) -> CutoverStatus:
        """
        Executa rollback para o sistema legado.

        Args:
            reason: Motivo do rollback
            message: Mensagem detalhada (opcional)

        Returns:
            Status após rollback
        """
        if self._rollback_in_progress:
            self.logger.warning("rollback_already_in_progress")
            return self.status

        self._rollback_in_progress = True
        previous_phase = self.status.phase

        # Atualizar status
        self.status.phase = CutoverPhase.ROLLED_BACK
        self.status.traffic_percentage = 0
        self.status.rollback_count += 1
        self.status.rollback_reason = reason
        self.status.rollback_message = message or _get_phase_value(reason)

        # Parar monitoramento
        self._running = False

        self.logger.error(
            "rollback_executed",
            reason=_get_phase_value(reason),
            message=message,
            previous_phase=_get_phase_value(previous_phase),
        )

        # Persistir estado
        await self._persist_status()

        # Publicar evento de rollback
        await self._emit_event(
            event_type="cutover.rolled_back",
            phase=CutoverPhase.ROLLED_BACK,
            previous_phase=previous_phase,
            success=True,
            message=message or f"Rollback executado: {_get_phase_value(reason)}",
        )

        # Registrar métricas
        self._record_metrics("rollback_executed", 1, {"reason": reason.value})

        self._rollback_in_progress = False
        return self.status

    async def collect_metrics(self, legacy_metrics: dict, target_metrics: dict) -> None:
        """
        Coleta e processa métricas de ambos os sistemas.

        Args:
            legacy_metrics: Métricas do sistema legado
            target_metrics: Métricas do sistema alvo
        """
        metrics = CutoverMetrics(
            phase=self.status.phase,
            error_rate=target_metrics.get("error_rate", 0.0),
            p50_latency_ms=target_metrics.get("p50_latency_ms", 0),
            p95_latency_ms=target_metrics.get("p95_latency_ms", 0),
            p99_latency_ms=target_metrics.get("p99_latency_ms", 0),
            requests_per_second=target_metrics.get("requests_per_second", 0.0),
            business_metrics=target_metrics.get("business_metrics", {}),
            legacy_p95_latency_ms=legacy_metrics.get("p95_latency_ms"),
            anomaly_detected=target_metrics.get("anomaly_detected", False),
        )

        self.status.add_metrics(metrics)

        # Verificar condições de rollback
        if self.config.enable_auto_rollback and self._running:
            should_rollback, rollback_reason = self.status.should_trigger_rollback(self.config)

            if should_rollback:
                self.logger.warning(
                    "rollback_condition_detected",
                    reason=rollback_reason,
                    error_rate=metrics.error_rate,
                    p95_latency_ms=metrics.p95_latency_ms,
                )

                # Determinar motivo do rollback
                rollback_trigger = RollbackReason.ERROR_RATE_EXCEEDED
                if "lat" in rollback_reason.lower():  # Captura "latência" ou "latency"
                    rollback_trigger = RollbackReason.LATENCY_HIGH
                elif "anomalia" in rollback_reason.lower() or "anomaly" in rollback_reason.lower():
                    rollback_trigger = RollbackReason.DATA_CORRUPTION

                await self.rollback(rollback_trigger, rollback_reason)

    async def _monitor_loop(self) -> None:
        """
        Loop de monitoramento em background.

        Coleta métricas periodicamente e avalia condições.
        """
        interval_seconds = 60  # Coletar métricas a cada minuto

        while self._running:
            try:
                # Simular coleta de métricas (na implementação real, viria dos clientes)
                # Por ora, apenas verificar condições de promoção
                if self.config.enable_auto_promote:
                    can_promote, _ = self.status.can_promote_to_next_phase(self.config)

                    if can_promote:
                        next_phase = self._get_next_phase()
                        await self._transition_to(next_phase, trigger="auto")

                await asyncio.sleep(interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.exception("monitor_loop_error", error=str(e))
                self._consecutive_failures += 1

                if self._consecutive_failures >= self._max_consecutive_failures:
                    self.logger.error(
                        "monitor_loop_max_failures",
                        failures=self._consecutive_failures,
                    )
                    break

                await asyncio.sleep(interval_seconds)

    async def _transition_to(
        self, next_phase: CutoverPhase, trigger: str = "auto"
    ) -> tuple[bool, str]:
        """
        Transiciona para a próxima fase do cutover.

        Args:
            next_phase: Próxima fase
            trigger: Tipo de trigger (auto, manual)

        Returns:
            Tupla (success, message)
        """
        previous_phase = self.status.phase
        previous_traffic = self.status.traffic_percentage

        # Determinar percentual de tráfego
        traffic_map = {
            CutoverPhase.SHADOW_MODE: 0,
            CutoverPhase.CANARY_5: 5,
            CutoverPhase.CANARY_25: 25,
            CutoverPhase.CANARY_50: 50,
            CutoverPhase.FULL_CUTOVER: 100,
            CutoverPhase.COMPLETED: 100,
        }

        # Lidar com string ou enum
        next_phase_key = next_phase if isinstance(next_phase, str) else next_phase
        new_traffic = traffic_map.get(
            CutoverPhase(next_phase_key) if isinstance(next_phase, str) else next_phase,
            previous_traffic,
        )

        # Atualizar status
        self.status.phase = next_phase
        self.status.traffic_percentage = new_traffic
        self.status.current_phase_start = datetime.now()
        self.status.phase_transitions += 1

        message = f"Transição de {_get_phase_value(previous_phase)} para {_get_phase_value(next_phase)} ({trigger})"

        self.logger.info(
            "phase_transition",
            previous=_get_phase_value(previous_phase),
            next=_get_phase_value(next_phase),
            traffic_percentage=new_traffic,
            trigger=trigger,
        )

        # Persistir estado
        await self._persist_status()

        # Publicar evento de transição
        await self._emit_event(
            event_type="cutover.phase_changed",
            phase=next_phase,
            previous_phase=previous_phase,
            message=message,
            metadata={
                "traffic_percentage": new_traffic,
                "trigger": trigger,
            },
        )

        # Registrar métricas
        self._record_metrics(
            "phase_transition",
            1,
            {"phase": next_phase.value, "traffic_percentage": new_traffic},
        )

        # Verificar conclusão
        if next_phase == CutoverPhase.FULL_CUTOVER:
            # Após 7 dias em full cutover, marcar como completed
            asyncio.create_task(self._finalize_after_full_cutover())

        return True, message

    def _get_next_phase(self) -> CutoverPhase:
        """
        Retorna a próxima fase baseado na fase atual.

        Returns:
            Próxima fase
        """
        phase_order = [
            CutoverPhase.SHADOW_MODE,
            CutoverPhase.CANARY_5,
            CutoverPhase.CANARY_25,
            CutoverPhase.CANARY_50,
            CutoverPhase.FULL_CUTOVER,
            CutoverPhase.COMPLETED,
        ]

        try:
            current_index = phase_order.index(self.status.phase)
            return phase_order[current_index + 1]
        except (ValueError, IndexError):
            return CutoverPhase.COMPLETED

    async def _finalize_after_full_cutover(self) -> None:
        """
        Finaliza cutover após período de estabilização em FULL_CUTOVER.

        Aguarda 7 dias e marca como COMPLETED.
        """
        stabilization_days = 7
        await asyncio.sleep(timedelta(days=stabilization_days).total_seconds())

        if self.status.phase == CutoverPhase.FULL_CUTOVER:
            await self._transition_to(CutoverPhase.COMPLETED, trigger="auto")

            self.status.completed_at = datetime.now()
            self._running = False

            self.logger.info(
                "cutover_completed",
                duration_days=(datetime.now() - self.status.started_at).days,
            )

            await self._emit_event(
                event_type="cutover.completed",
                phase=CutoverPhase.COMPLETED,
                message="Cutover completado com sucesso",
            )

    async def _persist_status(self) -> None:
        """Persiste status atual no MongoDB."""
        if not self.mongodb_client:
            return

        try:
            collection = self.mongodb_client.db.get("cutover_status")
            if collection is None:
                return

            await collection.update_one(
                {"cutover_id": self.cutover_id},
                {"$set": self.status.model_dump()},
                upsert=True,
            )
        except Exception as e:
            self.logger.warning("persist_status_failed", error=str(e))

    async def _emit_event(
        self,
        event_type: str,
        phase: CutoverPhase,
        previous_phase: CutoverPhase | None = None,
        success: bool = True,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Emite evento de cutover para o Kafka.

        Args:
            event_type: Tipo do evento
            phase: Fase atual
            previous_phase: Fase anterior (se aplicável)
            success: Se a operação foi bem-sucedida
            message: Mensagem descritiva
            metadata: Metadados adicionais
        """
        if not self.kafka_producer:
            return

        event = CutoverEvent(
            event_id=str(uuid.uuid4()),
            cutover_id=self.cutover_id,
            event_type=event_type,
            phase=phase,
            previous_phase=previous_phase,
            success=success,
            message=message,
            metadata=metadata or {},
        )

        try:
            topic = "cutover.events"
            await self.kafka_producer.produce(
                topic=topic,
                key=self.cutover_id.encode(),
                value=event.model_dump_json().encode(),
            )
        except Exception as e:
            self.logger.warning("emit_event_failed", error=str(e))

    def _record_metrics(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """
        Registra métricas no Prometheus/OpenTelemetry.

        Args:
            name: Nome da métrica
            value: Valor
            tags: Tags adicionais
        """
        if not self.metrics_client:
            return

        try:
            # Implementação depende do cliente de métricas
            # Exemplo com Prometheus (usar f"cutover_{name}" e tags do cutover):
            # tags = {"cutover_id": self.cutover_id, "phase": ..., **(tags or {})}
            # self.metrics_client.counter(f"cutover_{name}").labels(**tags).inc(value)
            pass
        except Exception as e:
            self.logger.warning("record_metrics_failed", error=str(e))

    async def get_status(self) -> CutoverStatus:
        """
        Retorna status atual do cutover.

        Returns:
            Status atual
        """
        return self.status

    async def get_metrics_history(self, limit: int = 100) -> list[CutoverMetrics]:
        """
        Retorna histórico de métricas.

        Args:
            limit: Número máximo de registros

        Returns:
            Lista de métricas
        """
        return self.status.metrics_history[-limit:]

    async def close(self) -> None:
        """
        Limpa recursos do gerenciador.
        """
        self._running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        self.logger.info(
            "cutover_manager_closed",
            cutover_id=self.cutover_id,
            final_phase=_get_phase_value(self.status.phase),
        )
