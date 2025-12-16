"""Kafka consumer for orchestration incidents -> triggers remediation playbooks."""
import asyncio
import json
from io import BytesIO
from typing import Optional, Dict, Any

import structlog
from aiokafka import AIOKafkaConsumer

try:
    from fastavro import schemaless_reader  # type: ignore
except Exception:  # noqa: BLE001
    schemaless_reader = None

from src.models.remediation_models import RemediationRequest
from src.services.remediation_manager import RemediationManager
from src.services.playbook_executor import PlaybookExecutor

logger = structlog.get_logger()


class OrchestrationIncidentConsumer:
    """Consome incidentes de orquestração e aciona playbooks correspondentes."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topic: str,
        playbook_executor: PlaybookExecutor,
        remediation_manager: RemediationManager,
        incident_schema: Optional[Dict[str, Any]] = None
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.topic = topic
        self.playbook_executor = playbook_executor
        self.remediation_manager = remediation_manager
        self.incident_schema = incident_schema

        self.consumer: Optional[AIOKafkaConsumer] = None
        self._consume_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Inicia consumo do tópico orchestration.incidents."""
        try:
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=False
            )
            await self.consumer.start()
            self._running = True
            self._consume_task = asyncio.create_task(self._consume_loop())
            logger.info("incident_consumer.started", topic=self.topic)
        except Exception as exc:  # noqa: BLE001
            logger.error("incident_consumer.start_failed", error=str(exc))
            raise

    async def _consume_loop(self):
        """Loop principal de consumo."""
        assert self.consumer is not None
        try:
            async for msg in self.consumer:
                if not self._running:
                    break

                incident = self._deserialize(msg.value)
                if not incident:
                    logger.warning("incident_consumer.invalid_message", offset=msg.offset)
                    await self.consumer.commit()
                    continue

                playbook_name = incident.get("recommended_playbook") or self._recommend_playbook(incident.get("incident_type"))
                if not playbook_name:
                    logger.warning(
                        "incident_consumer.no_playbook_mapped",
                        incident_type=incident.get("incident_type"),
                        incident_id=incident.get("incident_id")
                    )
                    await self.consumer.commit()
                    continue

                parameters = self._build_parameters(incident, playbook_name)
                remediation_request = RemediationRequest(
                    remediation_id=incident.get("incident_id"),
                    incident_id=incident.get("incident_id"),
                    playbook_name=playbook_name,
                    parameters=parameters
                )

                metadata = self.playbook_executor.get_playbook_metadata(playbook_name)
                total_actions = len(metadata.get("actions", []))
                state = self.remediation_manager.start_remediation(remediation_request, total_actions=total_actions)
                await self.remediation_manager.execute_remediation(state, self.playbook_executor, remediation_request)

                await self.consumer.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("incident_consumer.consume_loop_failed", error=str(exc))

    def _deserialize(self, payload: bytes) -> Optional[Dict[str, Any]]:
        """Tenta deserializar payload como JSON, fallback para Avro se schema disponível."""
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception:
            if self.incident_schema and schemaless_reader:
                try:
                    bio = BytesIO(payload)
                    return schemaless_reader(bio, self.incident_schema)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("incident_consumer.avro_deserialize_failed", error=str(exc))
            return None

    def _recommend_playbook(self, incident_type: Optional[str]) -> Optional[str]:
        mapping = {
            "TICKET_TIMEOUT": "ticket_timeout_recovery",
            "WORKER_FAILURE": "worker_failure_recovery",
            "SLA_VIOLATION": "sla_violation_mitigation"
        }
        return mapping.get(incident_type or "")

    def _build_parameters(self, incident: Dict[str, Any], incident_type: str) -> Dict[str, Any]:
        """Monta parâmetros esperados pelos playbooks."""
        affected_tickets = incident.get("affected_tickets") or []
        namespace = incident.get("namespace") or "default"
        params: Dict[str, Any] = {
            "workflow_id": incident.get("workflow_id"),
            "incident_type": incident_type,
            "affected_tickets": affected_tickets
        }

        if incident_type == "TICKET_TIMEOUT":
            ticket_id = affected_tickets[0] if affected_tickets else incident.get("ticket_id") or "unknown-ticket"
            params.update({
                "ticket_id": ticket_id,
                "worker_id": incident.get("worker_id") or "unknown-worker",
                "previous_worker_id": incident.get("worker_id") or "unknown-worker",
                "namespace": namespace
            })
        elif incident_type == "WORKER_FAILURE":
            params.update({
                "worker_id": incident.get("worker_id") or "unknown-worker",
                "previous_worker_id": incident.get("worker_id") or "unknown-worker",
                "namespace": namespace,
                "affected_tickets": affected_tickets
            })
        elif incident_type == "SLA_VIOLATION":
            params.update({
                "workflow_id": incident.get("workflow_id"),
                "service_name": incident.get("service_name") or "orchestrator-dynamic",
                "violation_type": incident.get("violation_type") or "SLA_VIOLATION",
                "delay_ms": incident.get("delay_ms") or 0
            })

        return params

    async def stop(self):
        """Interrompe consumo."""
        self._running = False
        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        if self.consumer:
            await self.consumer.stop()

        logger.info("incident_consumer.stopped")
