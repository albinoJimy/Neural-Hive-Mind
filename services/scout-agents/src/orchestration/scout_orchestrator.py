"""
ScoutOrchestrator - Coordena múltiplos Scout Agents em paralelo.

Responsável por:
- Disparar múltiplos scouts simultaneamente
- Agregar resultados com deduplicação
- Publicar eventos Kafka para tracking
- Gerenciar timeout e cancelação
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


class ScoutOrchestrator:
    """Orchestrator para coordenação de múltiplos Scout Agents."""

    def __init__(
        self,
        scout_agent_id: str,
        kafka_producer: Any = None,
        mongo_client: Any = None,
        default_timeout_ms: int = 30000,
    ):
        """
        Inicializa o ScoutOrchestrator.

        Args:
            scout_agent_id: ID do agente scout
            kafka_producer: Producer Kafka para eventos
            mongo_client: Cliente MongoDB para persistência
            default_timeout_ms: Timeout padrão para explorações
        """
        self.scout_agent_id = scout_agent_id
        self.kafka_producer = kafka_producer
        self.mongo_client = mongo_client
        self.default_timeout_ms = default_timeout_ms

        # Scouts disponíveis (registrados dinamicamente)
        self.available_scouts: Dict[str, Any] = {}

        # Explorações ativas e completadas
        self.active_explorations: Dict[str, Dict] = {}
        self.completed_explorations: Dict[str, Dict] = {}

        # Stats
        self.stats = {
            "explorations_started": 0,
            "explorations_completed": 0,
            "explorations_failed": 0,
            "explorations_timeout": 0,
        }

    async def coordinate_exploration(
        self,
        plan_id: str,
        intent_text: str,
        scouts: Optional[List[str]] = None,
        timeout_ms: Optional[int] = None,
        exploration_type: str = "codebase",
    ) -> Dict[str, Any]:
        """
        Coordena exploração paralela com múltiplos scouts.

        Args:
            plan_id: ID do plano associado
            intent_text: Texto da intenção original
            scouts: Lista específica de scouts (default: todos disponíveis)
            timeout_ms: Timeout em ms (default: self.default_timeout_ms)
            exploration_type: Tipo de exploração

        Returns:
            Dict com exploration_id e status inicial
        """
        exploration_id = f"scout-exp-{uuid.uuid4().hex[:8]}"
        timeout = timeout_ms or self.default_timeout_ms

        # Publicar evento started
        await self.publish_kafka_events(
            exploration_id=exploration_id,
            event_type="started",
            plan_id=plan_id,
            exploration_type=exploration_type,
        )

        # Determinar scouts para deploy
        scouts_to_deploy = scouts or list(self.available_scouts.keys())

        # Registrar exploração ativa
        self.active_explorations[exploration_id] = {
            "exploration_id": exploration_id,
            "plan_id": plan_id,
            "intent_text": intent_text,
            "exploration_type": exploration_type,
            "scouts_deployed": scouts_to_deploy,
            "status": "running",
            "started_at": datetime.now(timezone.utc),
            "timeout_ms": timeout,
        }

        # Iniciar exploração em background
        asyncio.create_task(
            self._run_exploration(
                exploration_id, scouts_to_deploy, timeout, plan_id, intent_text, exploration_type
            )
        )

        self.stats["explorations_started"] += 1

        logger.info(
            "exploration_started",
            exploration_id=exploration_id,
            plan_id=plan_id,
            scouts=scouts_to_deploy,
        )

        return {
            "exploration_id": exploration_id,
            "status": "running",
            "estimated_completion_ms": timeout,
            "scouts_deployed": scouts_to_deploy,
        }

    async def _run_exploration(
        self,
        exploration_id: str,
        scouts: List[str],
        timeout_ms: int,
        plan_id: str,
        intent_text: str,
        exploration_type: str,
    ):
        """
        Executa exploração com múltiplos scouts em paralelo.

        Args:
            exploration_id: ID da exploração
            scouts: Lista de scouts para executar
            timeout_ms: Timeout em ms
            plan_id: ID do plano
            intent_text: Texto da intenção
            exploration_type: Tipo de exploração
        """
        timeout_sec = timeout_ms / 1000
        scout_tasks = []

        # Criar tasks para cada scout
        for scout_name in scouts:
            scout = self.available_scouts.get(scout_name)
            if scout and hasattr(scout, "explore"):
                task = asyncio.create_task(
                    self._run_scout_with_timeout(
                        scout, scout_name, plan_id, intent_text, timeout_sec
                    )
                )
                scout_tasks.append((scout_name, task))

        # Aguardar todos os scouts ou timeout
        try:
            results = await asyncio.wait_for(
                self._gather_scout_results(scout_tasks), timeout=timeout_sec
            )

            # Agregar resultados
            aggregated = self.aggregate_results(results)

            # Marcar como completada
            await self._mark_exploration_completed(exploration_id, aggregated)

            # Publicar evento completed
            await self.publish_kafka_events(
                exploration_id=exploration_id,
                event_type="completed",
                plan_id=plan_id,
                results=aggregated,
            )

            self.stats["explorations_completed"] += 1

            logger.info(
                "exploration_completed",
                exploration_id=exploration_id,
                results_count=len(aggregated),
            )

        except asyncio.TimeoutError:
            # Coletar resultados parciais
            partial = await self._collect_partial_results(scout_tasks)

            await self._mark_exploration_timeout(exploration_id, partial)

            await self.publish_kafka_events(
                exploration_id=exploration_id,
                event_type="timeout",
                plan_id=plan_id,
                partial_results=partial,
            )

            self.stats["explorations_timeout"] += 1

            logger.warning(
                "exploration_timeout", exploration_id=exploration_id, timeout_ms=timeout_ms
            )

        except Exception as e:
            logger.error("exploration_failed", exploration_id=exploration_id, error=str(e))

            await self._mark_exploration_failed(exploration_id, str(e))

            await self.publish_kafka_events(
                exploration_id=exploration_id, event_type="failed", plan_id=plan_id, error=str(e)
            )

            self.stats["explorations_failed"] += 1

    async def _run_scout_with_timeout(
        self, scout: Any, scout_name: str, plan_id: str, intent_text: str, timeout_sec: float
    ) -> tuple:
        """Executa um scout individual com timeout."""
        try:
            result = await asyncio.wait_for(
                scout.explore(plan_id, intent_text), timeout=timeout_sec
            )
            return (scout_name, result, None)
        except asyncio.TimeoutError:
            return (scout_name, None, "timeout")
        except Exception as e:
            return (scout_name, None, str(e))

    async def _gather_scout_results(self, scout_tasks: List[tuple]) -> Dict[str, Any]:
        """Coleta resultados de todos os scouts."""
        results = {}

        for scout_name, task in scout_tasks:
            try:
                _, result, error = await task
                if error:
                    results[scout_name] = {"error": error}
                else:
                    results[scout_name] = result
            except Exception as e:
                results[scout_name] = {"error": str(e)}

        return results

    async def _collect_partial_results(self, scout_tasks: List[tuple]) -> Dict[str, Any]:
        """Coleta resultados parciais de scouts que completaram."""
        partial = {}

        for scout_name, task in scout_tasks:
            if task.done():
                try:
                    _, result, error = task.result()
                    if result:
                        partial[scout_name] = result
                except Exception:
                    pass

        return partial

    def aggregate_results(self, scout_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Agrega resultados de múltiplos scouts com deduplicação.

        Args:
            scout_results: Dict com resultados por scout

        Returns:
            Dict agregado com todos os findings
        """
        aggregated = {
            "solutions_found": [],
            "patterns_discovered": [],
            "dependencies": {"internal": [], "external": [], "circular": []},
            "aggregate_confidence": 0.0,
            "scouts_reported": len(scout_results),
        }

        # Aggregate solutions
        for scout_name, result in scout_results.items():
            if "solutions" in result:
                for sol in result["solutions"]:
                    # Deduplicação por approach
                    if not any(
                        s.get("approach") == sol.get("approach")
                        for s in aggregated["solutions_found"]
                    ):
                        aggregated["solutions_found"].append(sol)

            # Aggregate patterns
            if "patterns" in result:
                for pattern in result["patterns"]:
                    existing = next(
                        (
                            p
                            for p in aggregated["patterns_discovered"]
                            if p.get("name") == pattern.get("name")
                        ),
                        None,
                    )
                    if existing:
                        existing["occurrences"] += pattern.get("occurrences", 0)
                        existing["locations"].extend(pattern.get("locations", []))
                    else:
                        aggregated["patterns_discovered"].append(
                            {**pattern, "locations": pattern.get("locations", [])}
                        )

            # Aggregate dependencies
            if "dependencies" in result:
                deps = result["dependencies"]
                aggregated["dependencies"]["internal"].extend(deps.get("internal", []))
                aggregated["dependencies"]["external"].extend(deps.get("external", []))
                aggregated["dependencies"]["circular"].extend(deps.get("circular", []))

            # Aggregate confidence
            if "confidence" in result:
                aggregated["aggregate_confidence"] += result["confidence"]

        # Calculate average confidence
        if aggregated["scouts_reported"] > 0:
            aggregated["aggregate_confidence"] /= aggregated["scouts_reported"]

        # Deduplicate lists
        aggregated["dependencies"]["internal"] = list(set(aggregated["dependencies"]["internal"]))
        aggregated["dependencies"]["external"] = list(set(aggregated["dependencies"]["external"]))

        return aggregated

    async def publish_kafka_events(
        self, exploration_id: str, event_type: str, plan_id: str, **kwargs
    ):
        """
        Publica eventos Kafka sobre a exploração.

        Args:
            exploration_id: ID da exploração
            event_type: Tipo do evento (started, completed, failed, timeout)
            plan_id: ID do plano associado
            **kwargs: Dados adicionais do evento
        """
        if not self.kafka_producer:
            return

        event = {
            "event_type": f"scout.exploration.{event_type}",
            "exploration_id": exploration_id,
            "plan_id": plan_id,
            "scout_agent_id": self.scout_agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }

        try:
            if hasattr(self.kafka_producer, "publish"):
                await self.kafka_producer.publish("scout.exploration.events", event)
            else:
                logger.warning("kafka_producer_missing_publish_method")
        except Exception as e:
            logger.error(
                "kafka_publish_failed",
                exploration_id=exploration_id,
                event_type=event_type,
                error=str(e),
            )

    async def get_exploration_status(self, exploration_id: str) -> Optional[Dict[str, Any]]:
        """
        Consulta status de uma exploração.

        Args:
            exploration_id: ID da exploração

        Returns:
            Dict com status e resultados (se completada), ou None se não encontrada
        """
        # Verificar explorações ativas
        if exploration_id in self.active_explorations:
            return self.active_explorations[exploration_id]

        # Verificar explorações completadas
        if exploration_id in self.completed_explorations:
            return self.completed_explorations[exploration_id]

        # Verificar no MongoDB
        if self.mongo_client:
            try:
                result = await self.mongo_client.find_exploration(exploration_id)
                if result:
                    return result
            except Exception as e:
                logger.error("mongo_find_failed", exploration_id=exploration_id, error=str(e))

        return None

    async def _mark_exploration_completed(self, exploration_id: str, results: Dict[str, Any]):
        """Marca exploração como completada."""
        if exploration_id in self.active_explorations:
            exploration = self.active_explorations.pop(exploration_id)
            exploration["status"] = "completed"
            exploration["completed_at"] = datetime.now(timezone.utc)
            exploration["duration_ms"] = int(
                (exploration["completed_at"] - exploration["started_at"]).total_seconds() * 1000
            )
            exploration["results"] = results
            self.completed_explorations[exploration_id] = exploration

    async def _mark_exploration_timeout(self, exploration_id: str, partial_results: Dict[str, Any]):
        """Marca exploração como timeout."""
        if exploration_id in self.active_explorations:
            exploration = self.active_explorations.pop(exploration_id)
            exploration["status"] = "timeout"
            exploration["completed_at"] = datetime.now(timezone.utc)
            exploration["partial_results"] = partial_results
            self.completed_explorations[exploration_id] = exploration

    async def _mark_exploration_failed(self, exploration_id: str, error: str):
        """Marca exploração como falha."""
        if exploration_id in self.active_explorations:
            exploration = self.active_explorations.pop(exploration_id)
            exploration["status"] = "failed"
            exploration["completed_at"] = datetime.now(timezone.utc)
            exploration["error"] = error
            self.completed_explorations[exploration_id] = exploration

    def register_scout(self, name: str, scout_instance: Any):
        """
        Registra um scout disponível.

        Args:
            name: Nome do scout
            scout_instance: Instância do scout
        """
        self.available_scouts[name] = scout_instance
        logger.info("scout_registered", scout_name=name)

    def unregister_scout(self, name: str):
        """Remove um scout do registro."""
        if name in self.available_scouts:
            del self.available_scouts[name]
            logger.info("scout_unregistered", scout_name=name)

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do orchestrator."""
        return {
            **self.stats,
            "active_explorations": len(self.active_explorations),
            "completed_explorations": len(self.completed_explorations),
            "available_scouts": list(self.available_scouts.keys()),
        }
