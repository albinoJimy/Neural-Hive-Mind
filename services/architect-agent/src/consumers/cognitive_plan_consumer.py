"""Consumidor de CognitivePlans para arquitetura."""

import json

import structlog

from src.config.settings import get_settings
from src.consumers.base import BaseKafkaConsumer
from src.planners.design_planner import DesignPlanner
from src.repositories.architecture_repository import ArchitectureRepository

logger = structlog.get_logger(__name__)


class CognitivePlanConsumer(BaseKafkaConsumer):
    """Consome CognitivePlans e gera arquiteturas."""

    def __init__(self, producer=None) -> None:
        """Inicializa consumidor de CognitivePlans.

        Args:
            producer: ArchitecturePlanProducer opcional para publicar eventos
        """
        super().__init__()
        self.planner = DesignPlanner()
        self.repository = ArchitectureRepository()
        self._producer = producer

    def get_topic(self) -> str:
        """Retorna o tópico de CognitivePlans."""
        settings = get_settings()
        return settings.kafka.cognitive_plans_topic

    async def process_message(self, message: dict) -> None:
        """Processa mensagem do CognitivePlan.

        Args:
            message: Mensagem Kafka com key, value, topic
        """
        try:
            # Parse JSON value
            value = message.get("value", "{}")
            plan_data = json.loads(value) if isinstance(value, str) else value

            # Extrair requisitos
            requirements = {
                "intent": plan_data.get("intent", ""),
                "context": plan_data.get("context", {}),
            }

            # Adicionar cognitive_plan_id se presente
            if "plan_id" in plan_data:
                requirements["cognitive_plan_id"] = plan_data["plan_id"]

            # Log com intent truncado
            intent_str = requirements.get("intent", "")
            truncated_intent = intent_str[:100] if intent_str else ""

            logger.info(
                "cognitive_plan_received",
                cognitive_plan_id=requirements.get("cognitive_plan_id"),
                intent=truncated_intent,
            )

            # Gerar arquitetura
            architecture_plan = await self.planner.plan(requirements)

            # Persistir no MongoDB
            await self.repository.create(architecture_plan)

            # Publicar evento Kafka se producer disponível
            if self._producer:
                await self._producer.publish_plan_created(
                    plan_id=architecture_plan.plan_id,
                    cognitive_plan_id=architecture_plan.cognitive_plan_id,
                    architecture_type=architecture_plan.architecture_type.value,
                    components=[c.model_dump() for c in architecture_plan.components],
                    rationale=architecture_plan.rationale,
                )

            logger.info(
                "architecture_plan_created",
                architecture_plan_id=architecture_plan.plan_id,
                cognitive_plan_id=requirements.get("cognitive_plan_id"),
                architecture_type=architecture_plan.architecture_type.value,
                components_count=len(architecture_plan.components),
            )

        except json.JSONDecodeError as e:
            logger.error("invalid_json_in_message", error=str(e))
        except Exception as e:
            logger.error("cognitive_plan_processing_error", error=str(e))
