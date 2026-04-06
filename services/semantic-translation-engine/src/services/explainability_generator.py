"""
Explainability Generator - Generates explainability tokens and narratives

Creates human-readable explanations for plan generation decisions.
"""

import uuid
from datetime import datetime, timezone
UTC = timezone.utc  # type: ignore

import structlog
from src.clients.mongodb_client import MongoDBClient
from src.models.cognitive_plan import TaskNode

logger = structlog.get_logger()


class ExplainabilityGenerator:
    """Generator of explainability tokens and narratives"""

    def __init__(self, mongodb_client: MongoDBClient):
        self.mongodb = mongodb_client

    def generate(
        self, intermediate_repr: dict, tasks: list[TaskNode], risk_factors: dict[str, float]
    ) -> tuple[str, str]:
        """
        Generate explainability token and reasoning summary

        Args:
            intermediate_repr: Parsed intent representation
            tasks: Generated tasks
            risk_factors: Risk assessment factors

        Returns:
            Tuple of (explainability_token, reasoning_summary)
        """
        # Generate unique token
        explainability_token = str(uuid.uuid4())

        # Generate reasoning summary
        reasoning_summary = self._generate_reasoning_summary(intermediate_repr, tasks, risk_factors)

        # Generate detailed explanation for audit
        detailed_explanation = self._generate_detailed_explanation(
            intermediate_repr, tasks, risk_factors
        )

        # Persist explanation asynchronously
        import asyncio

        asyncio.create_task(self._persist_explanation(explainability_token, detailed_explanation))

        return explainability_token, reasoning_summary

    def _generate_reasoning_summary(
        self, intermediate_repr: dict, tasks: list[TaskNode], risk_factors: dict
    ) -> str:
        """Generate human-readable reasoning summary"""
        objectives = intermediate_repr["objectives"]
        domain = intermediate_repr["domain"]
        num_tasks = len(tasks)
        risk_score = risk_factors["weighted_score"]

        summary = f"Plano gerado para domínio {domain} com {num_tasks} tarefas. "
        summary += f"Objetivos identificados: {', '.join(objectives)}. "
        summary += f"Score de risco: {risk_score:.2f} "
        summary += f"(prioridade: {risk_factors['priority']:.2f}, "
        summary += f"segurança: {risk_factors['security']:.2f}, "
        summary += f"complexidade: {risk_factors['complexity']:.2f}). "

        if intermediate_repr["known_patterns"]:
            summary += f"Padrões conhecidos aplicados: {len(intermediate_repr['known_patterns'])}. "

        similar_intents = intermediate_repr["historical_context"].get("similar_intents", [])
        if similar_intents:
            summary += f"Baseado em {len(similar_intents)} intenções similares. "

        return summary

    def _generate_detailed_explanation(
        self, intermediate_repr: dict, tasks: list[TaskNode], risk_factors: dict
    ) -> dict:
        """Generate detailed explanation for audit"""
        return {
            "intent_id": intermediate_repr["intent_id"],
            "domain": intermediate_repr["domain"],
            "objectives": intermediate_repr["objectives"],
            "entities": intermediate_repr["entities"],
            "constraints": intermediate_repr["constraints"],
            "tasks_generated": [
                {
                    "task_id": task.task_id,
                    "type": task.task_type,
                    "description": task.description,
                    "dependencies": task.dependencies,
                    "rationale": f'Tarefa gerada para objetivo {task.parameters.get("objective")}',
                }
                for task in tasks
            ],
            "risk_assessment": {
                "score": risk_factors["weighted_score"],
                "factors": risk_factors,
                "rationale": "Score calculado com base em prioridade, segurança e complexidade",
            },
            "historical_context": intermediate_repr["historical_context"],
            "decision_timestamp": datetime.now(UTC).isoformat(),
            "version": "1.0.0",
        }

    async def _persist_explanation(self, token: str, explanation: dict):
        """Persist explanation in MongoDB"""
        try:
            collection = self.mongodb.db["explainability_ledger"]
            await collection.insert_one(
                {
                    "token": token,
                    "explanation": explanation,
                    "timestamp": datetime.now(UTC),
                }
            )

            logger.info("Explicação persistida", token=token)

        except Exception as e:
            logger.exception("Erro persistindo explicação", token=token, error=str(e))

    async def retrieve_explanation(self, token: str) -> dict:
        """Retrieve explanation by token"""
        collection = self.mongodb.db["explainability_ledger"]
        result = await collection.find_one({"token": token})
        return result["explanation"] if result else None
