"""Message handler service for processing Kafka events"""
import json
from typing import TYPE_CHECKING
import structlog

from neural_hive_observability.context import (
    extract_context_from_headers,
    set_baggage
)

if TYPE_CHECKING:
    from aiokafka import ConsumerRecord
    from src.clients.mongodb_client import MongoDBClient
    from src.clients.redis_client import RedisClient
    from src.clients.kubernetes_client import KubernetesClient

logger = structlog.get_logger()


class MessageHandler:
    """Processa mensagens do Kafka e coordena resposta a incidentes"""

    def __init__(
        self,
        mongodb_client: "MongoDBClient",
        redis_client: "RedisClient",
        k8s_client: "KubernetesClient" = None,
        kafka_producer=None,
        self_healing_client=None,
        opa_client=None,
        istio_client=None,
        prometheus_client=None,
        threat_detector=None,
        chaosmesh_client=None,
        script_executor=None,
        itsm_client=None
    ):
        self.mongodb = mongodb_client
        self.redis = redis_client
        self.k8s = k8s_client
        self.kafka_producer = kafka_producer
        self.self_healing_client = self_healing_client
        self.opa_client = opa_client
        self.istio_client = istio_client
        self.prometheus_client = prometheus_client
        self.chaosmesh_client = chaosmesh_client
        self.script_executor = script_executor
        self.itsm_client = itsm_client

        # Inicializar componentes do fluxo E1-E6
        from src.services.threat_detector import ThreatDetector
        from src.services.incident_classifier import IncidentClassifier
        from src.services.policy_enforcer import PolicyEnforcer
        from src.services.remediation_coordinator import RemediationCoordinator
        from src.services.incident_orchestrator import IncidentOrchestrator

        # Usar ThreatDetector injetado ou criar novo
        self.threat_detector = threat_detector if threat_detector else ThreatDetector(redis_client=redis_client)
        self.incident_classifier = IncidentClassifier(mongodb_client=mongodb_client)
        self.policy_enforcer = PolicyEnforcer(
            k8s_client=k8s_client,
            redis_client=redis_client,
            opa_client=opa_client,
            istio_client=istio_client
        )
        self.remediation_coordinator = RemediationCoordinator(
            k8s_client=k8s_client,
            mongodb_client=mongodb_client,
            kafka_producer=kafka_producer,
            self_healing_client=self_healing_client,
            redis_client=redis_client,
            chaosmesh_client=chaosmesh_client,
            script_executor=script_executor
        )

        # Orquestrador que coordena E1-E6
        self.orchestrator = IncidentOrchestrator(
            threat_detector=self.threat_detector,
            incident_classifier=self.incident_classifier,
            policy_enforcer=self.policy_enforcer,
            remediation_coordinator=self.remediation_coordinator,
            mongodb_client=mongodb_client,
            kafka_producer=kafka_producer,
            prometheus_client=prometheus_client,
            itsm_client=itsm_client
        )

    async def handle_security_incident(self, message: "ConsumerRecord"):
        """
        Processa incidentes de segurança através do fluxo completo E1-E6

        Fluxo:
        E1: Detectar anomalia (enriquecimento de contexto)
        E2: Classificar severidade (mapeado a runbooks)
        E3: Enforçar políticas (OPA/Istio)
        E4: Executar playbooks de autocura
        E5: Validar restauração de SLA
        E6: Documentar lições aprendidas
        """
        try:
            headers_dict = {k: v for k, v in (message.headers or [])}
            extract_context_from_headers(headers_dict)
            incident_data = json.loads(message.value.decode('utf-8'))
            if incident_data.get("user_id"):
                set_baggage("user_id", incident_data.get("user_id"))
            if incident_data.get("incident_id"):
                set_baggage("incident_id", incident_data.get("incident_id"))

            logger.info(
                "security_incident.received",
                incident_id=incident_data.get("incident_id"),
                severity=incident_data.get("severity"),
                type=incident_data.get("type")
            )

            # Converter incident_data em formato de evento para o orquestrador
            event = {
                "type": "security_incident",
                "event_id": incident_data.get("incident_id"),
                "severity": incident_data.get("severity"),
                "threat_type": incident_data.get("threat_type"),
                "source_ip": incident_data.get("source_ip"),
                "user_id": incident_data.get("user_id"),
                "payload": incident_data.get("payload"),
                "timestamp": incident_data.get("timestamp"),
                "raw_data": incident_data,
            }

            # Contexto adicional
            context = {
                "environment": incident_data.get("environment", "production"),
                "is_critical_resource": incident_data.get("is_critical", False),
                "affected_resources": incident_data.get("affected_resources", []),
            }

            # Processar através do fluxo completo E1-E6
            result = await self.orchestrator.process_incident_flow(event, context)

            logger.info(
                "security_incident.processed",
                incident_id=result.get("incident_id"),
                flow=result.get("flow"),
                sla_met=result.get("e5_sla_validation", {}).get("sla_met"),
                duration_ms=result.get("duration_ms")
            )

        except Exception as e:
            logger.error("security_incident.processing_failed", error=str(e))
            raise

    async def handle_orchestration_incident(self, message: "ConsumerRecord"):
        """
        Processa incidentes de orquestração (falhas de pods, degradações, etc)
        através do fluxo completo E1-E6
        """
        try:
            headers_dict = {k: v for k, v in (message.headers or [])}
            extract_context_from_headers(headers_dict)
            incident_data = json.loads(message.value.decode('utf-8'))
            if incident_data.get("incident_id"):
                set_baggage("incident_id", incident_data.get("incident_id"))

            logger.info(
                "orchestration_incident.received",
                incident_id=incident_data.get("incident_id"),
                resource_type=incident_data.get("resource_type"),
                resource_name=incident_data.get("resource_name")
            )

            # Converter incident_data em formato de evento para o orquestrador
            event = {
                "type": "resource_metrics",
                "event_id": incident_data.get("incident_id"),
                "resource_type": incident_data.get("resource_type"),
                "resource_name": incident_data.get("resource_name"),
                "metrics": incident_data.get("metrics", {}),
                "namespace": incident_data.get("namespace"),
                "timestamp": incident_data.get("timestamp"),
                "raw_data": incident_data,
            }

            # Contexto adicional para recursos K8s
            context = {
                "environment": incident_data.get("environment", "production"),
                "is_critical_resource": incident_data.get("is_critical", False),
                "affected_resources": [incident_data.get("resource_name")],
                "namespace": incident_data.get("namespace"),
            }

            # Processar através do fluxo completo E1-E6
            result = await self.orchestrator.process_incident_flow(event, context)

            logger.info(
                "orchestration_incident.processed",
                incident_id=result.get("incident_id"),
                flow=result.get("flow"),
                sla_met=result.get("e5_sla_validation", {}).get("sla_met"),
                duration_ms=result.get("duration_ms")
            )

        except Exception as e:
            logger.error("orchestration_incident.processing_failed", error=str(e))
            raise
