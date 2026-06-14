from datetime import datetime
from typing import Any

import structlog

from neural_hive_resilience.circuit_breaker import CircuitBreakerError
from src.clients import OrchestratorClient, RedisClient
from src.config import Settings
from src.models import QoSAdjustment

logger = structlog.get_logger()


class ReplanningCoordinator:
    """Coordenador de replanejamentos e ajustes de QoS"""

    def __init__(
        self,
        orchestrator_client: OrchestratorClient,
        redis_client: RedisClient,
        settings: Settings,
    ):
        self.orchestrator_client = orchestrator_client
        self.redis_client = redis_client
        self.settings = settings

    async def trigger_replanning(self, plan_id: str, reason: str, decision_id: str) -> bool:
        """Acionar replanejamento de um plano cognitivo"""
        try:
            # Verificar cooldown
            in_cooldown = await self.check_replanning_cooldown(plan_id)
            if in_cooldown:
                logger.warning(
                    "replanning_rejected_cooldown",
                    plan_id=plan_id,
                    cooldown_seconds=self.settings.REPLANNING_COOLDOWN_SECONDS,
                )
                return False

            # Chamar Orchestrator
            success = await self.orchestrator_client.trigger_replanning(plan_id, reason)

            if success:
                # Registrar evento de replanning
                await self.record_replanning_event(plan_id, decision_id)

                logger.info(
                    "replanning_triggered",
                    plan_id=plan_id,
                    reason=reason,
                    decision_id=decision_id,
                )

            return success

        except CircuitBreakerError:
            logger.warning("trigger_replanning_circuit_open", plan_id=plan_id, reason=reason)
            return False
        except Exception as e:
            logger.exception("trigger_replanning_failed", plan_id=plan_id, error=str(e))
            return False

    async def adjust_qos(self, adjustment: QoSAdjustment) -> bool:
        """Aplicar ajuste de QoS no Orchestrator"""
        try:
            success = await self.orchestrator_client.adjust_qos(adjustment)

            if success:
                adjustment.mark_applied()
                logger.info(
                    "qos_adjustment_applied",
                    adjustment_id=adjustment.adjustment_id,
                    type=adjustment.adjustment_type.value,
                    workflow_id=adjustment.target_workflow_id,
                )
            else:
                adjustment.mark_failed("Orchestrator rejected adjustment")
                logger.error("qos_adjustment_failed", adjustment_id=adjustment.adjustment_id)

            return success

        except CircuitBreakerError:
            logger.warning("qos_adjustment_circuit_open", adjustment_id=adjustment.adjustment_id)
            adjustment.mark_failed("circuit_open")
            return False
        except Exception as e:
            logger.exception("adjust_qos_failed", error=str(e))
            adjustment.mark_failed(str(e))
            return False

    async def pause_execution(self, workflow_id: str, reason: str) -> bool:
        """Pausar execução de workflow"""
        try:
            success = await self.orchestrator_client.pause_workflow(workflow_id, reason)

            logger.info(
                "execution_paused",
                workflow_id=workflow_id,
                reason=reason,
                success=success,
            )
            return success

        except CircuitBreakerError:
            logger.warning("pause_execution_circuit_open", workflow_id=workflow_id, reason=reason)
            return False
        except Exception as e:
            logger.exception("pause_execution_failed", workflow_id=workflow_id, error=str(e))
            return False

    async def resume_execution(self, workflow_id: str) -> bool:
        """Retomar execução pausada"""
        try:
            success = await self.orchestrator_client.resume_workflow(workflow_id)

            logger.info("execution_resumed", workflow_id=workflow_id, success=success)
            return success

        except CircuitBreakerError:
            logger.warning("resume_execution_circuit_open", workflow_id=workflow_id)
            return False
        except Exception as e:
            logger.exception("resume_execution_failed", workflow_id=workflow_id, error=str(e))
            return False

    async def check_replanning_cooldown(self, plan_id: str) -> bool:
        """Verificar se plano está em cooldown (anti-flapping)"""
        try:
            cooldown_key = f"replanning:cooldown:{plan_id}"
            data = await self.redis_client.get_cached_context(cooldown_key)

            return data is not None

        except Exception as e:
            logger.exception("check_cooldown_failed", plan_id=plan_id, error=str(e))
            return False

    async def record_replanning_event(self, plan_id: str, decision_id: str) -> None:
        """Registrar evento de replanning no Redis (inicia cooldown)"""
        try:
            cooldown_key = f"replanning:cooldown:{plan_id}"

            event_data = {
                "decision_id": decision_id,
                "timestamp": int(datetime.now().timestamp() * 1000),
            }

            await self.redis_client.cache_strategic_context(
                cooldown_key,
                event_data,
                ttl_seconds=self.settings.REPLANNING_COOLDOWN_SECONDS,
            )

            logger.debug("replanning_event_recorded", plan_id=plan_id, decision_id=decision_id)

        except Exception as e:
            logger.exception("record_replanning_event_failed", error=str(e))

    async def get_replanning_stats(self) -> dict[str, Any]:
        """Obter estatísticas de replanejamento do Redis"""
        try:
            # Buscar todas as chaves de cooldown ativas usando SCAN
            # TR-1: scan_iter é o caminho cluster-safe. O método scan(cursor=...)
            # standalone retorna (int, list) mas em RedisCluster retorna
            # (dict[node, int], list) — o loop manual quebra silenciosamente
            # (retorna zeros após TypeError apanhado pelo try/except). scan_iter
            # é stateless e faz fan-out implícito a todos os masters.
            cooldown_pattern = "replanning:cooldown:*"
            cooldown_keys = []

            async for key in self.redis_client.client.scan_iter(match=cooldown_pattern, count=100):
                cooldown_keys.append(key if isinstance(key, str) else key.decode("utf-8"))

            # Extrair plan_ids das chaves de cooldown
            cooldown_plans = []
            for key in cooldown_keys:
                plan_id = key.replace("replanning:cooldown:", "")
                cooldown_plans.append(plan_id)

            return {
                "total_replannings": len(cooldown_plans),
                "active_replannings": len(cooldown_plans),
                "cooldown_plans": cooldown_plans,
            }

        except Exception as e:
            logger.exception("get_replanning_stats_failed", error=str(e))
            return {
                "total_replannings": 0,
                "active_replannings": 0,
                "cooldown_plans": [],
            }
