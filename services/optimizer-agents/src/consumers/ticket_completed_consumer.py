"""Consumer Kafka para eventos ticket.completed."""

import asyncio
import json
from datetime import UTC, datetime

UTC = UTC  # type: ignore

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError
from motor.motor_asyncio import AsyncIOMotorClient
from structlog import get_logger

from src.analyzers.factory import AnalyzerFactory
from src.config.settings import get_settings
from src.repositories.optimization_repository import get_repository

logger = get_logger(__name__)


class TicketCompletedConsumer:
    """Consumer para eventos ticket.completed."""

    def __init__(self, settings: get_settings | None = None):
        """Inicializa consumer."""
        self.settings = settings or get_settings()
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False
        self._repository = None

    async def initialize(self) -> None:
        """Inicializa consumer Kafka e conexão MongoDB."""
        self._consumer = AIOKafkaConsumer(
            "ticket.completed",
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id="optimizer-agents",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="latest",
        )

        try:
            await self._consumer.start()
            logger.info("ticket_completed_consumer_started")

            # Inicializar MongoDB repository
            mongo_client = AsyncIOMotorClient(self.settings.mongodb_url)
            self._repository = await get_repository(
                mongo_client, self.settings.mongodb_database_name
            )
            logger.info("optimization_repository_initialized")

        except KafkaConnectionError as e:
            logger.error("kafka_consumer_connection_failed", error=str(e))
            raise

    async def start(self) -> None:
        """Inicia consumo de mensagens."""
        if not self._consumer:
            await self.initialize()

        self._running = True
        logger.info("ticket_completed_consumer_loop_started")

        while self._running:
            try:
                async for msg in self._consumer:
                    await self._process_message(msg)
            except Exception as e:
                logger.error("consumer_loop_error", error=str(e))
                if self._running:
                    await asyncio.sleep(5)

    async def _process_message(self, msg) -> None:
        """Processa mensagem Kafka e persiste recomendações."""
        try:
            data = msg.value
            ticket_id = data.get("ticket_id")
            workflow_id = data.get("workflow_id")

            logger.info("ticket_event_received", ticket_id=ticket_id, workflow_id=workflow_id)

            # Analisar tarefas e gerar recomendações
            recommendations_issues = []
            bottlenecks = []

            # Análise de performance
            performance_analysis = {
                "total_duration_ms": data.get("duration_ms", 0),
                "peak_memory_mb": data.get("peak_memory_mb", 0),
                "task_count": data.get("task_count", 0),
                "bottlenecks": [],
            }

            for task in data.get("tasks", []):
                task_id = task.get("task_id")
                executor_type = task.get("executor_type")

                # Determinar tipo de alvo baseado no executor
                if executor_type == "query":
                    database_type = self._infer_database_type(task)
                    analyzer = AnalyzerFactory.create_for_database(database_type)

                    context = {
                        "query": task.get("query"),
                        "collection": task.get("collection"),
                    }

                    result = await analyzer.analyze(context)

                    # Converter issues para recomendações
                    for issue in result.issues:
                        issue["target_type"] = database_type
                        issue["task_id"] = task_id
                        recommendations_issues.append(issue)

                elif executor_type in ["transform", "validate"]:
                    # Análise de código
                    analyzer = AnalyzerFactory.create_for_database("code")

                    context = {
                        "file_path": task.get("file_path"),
                        "code": task.get("code"),
                    }

                    result = await analyzer.analyze(context)

                    for issue in result.issues:
                        issue["target_type"] = "code"
                        issue["file_path"] = task.get("file_path")
                        issue["task_id"] = task_id
                        recommendations_issues.append(issue)

            # Consolidar bottlenecks
            for issue in recommendations_issues:
                if issue.get("severity") in ["high", "critical"]:
                    bottlenecks.append(
                        {
                            "task_id": issue.get("task_id"),
                            "task_type": issue.get("target_type"),
                            "issue": issue.get("description"),
                            "impact_score": 0.8 if issue.get("severity") == "critical" else 0.6,
                        }
                    )

            performance_analysis["bottlenecks"] = bottlenecks

            # Preparar recomendações finais
            final_recommendations = []
            for issue in recommendations_issues:
                final_recommendations.append(
                    {
                        "id": str(hash(f"{ticket_id}_{issue.get('task_id')}_{issue.get('type')}")),
                        "type": str(issue.get("type", "unknown")),
                        "severity": str(issue.get("severity", "medium")),
                        "target_type": issue.get("target_type", "code"),
                        "file_path": issue.get("file_path"),
                        "line_number": issue.get("line_number"),
                        "function_name": issue.get("function_name"),
                        "description": issue.get("description", ""),
                        "estimated_improvement_pct": issue.get("estimated_improvement_pct", 10.0),
                        "code_diff": issue.get("code_diff"),
                        "query_suggestion": issue.get("query_suggestion"),
                        "auto_apply": issue.get("auto_apply", False),
                        "status": "pending",
                    }
                )

            # Criar documento de recomendação
            if final_recommendations:
                recommendation_doc = {
                    "ticket_id": ticket_id,
                    "workflow_id": workflow_id,
                    "status": "pending",
                    "performance_analysis": performance_analysis,
                    "recommendations": final_recommendations,
                    "analyzed_by": "optimizer-agents",
                    "analyzed_at": datetime.now(UTC),
                }

                # Persistir no MongoDB
                rec_id = await self._repository.create(recommendation_doc)

                logger.info(
                    "optimization_recommendation_created",
                    ticket_id=ticket_id,
                    recommendation_id=rec_id,
                    recommendations_count=len(final_recommendations),
                )
            else:
                logger.info(
                    "no_optimization_recommendations", ticket_id=ticket_id, reason="no_issues_found"
                )

        except Exception as e:
            logger.error(
                "ticket_event_processing_failed",
                error=str(e),
                ticket_id=data.get("ticket_id") if data else None,
            )

    def _infer_database_type(self, task: dict) -> str:
        """Infere tipo de database baseado na task."""
        collection = task.get("collection", "")
        query = task.get("query", "")

        # Heurísticas para inferir tipo
        if "users" in collection or "orders" in collection:
            return "mongodb"
        elif "SELECT" in query.upper() or "INSERT" in query.upper():
            return "postgresql"
        elif "MATCH" in query.upper():
            return "neo4j"
        elif "EXISTS" in query.upper() or "TTL" in query.upper():
            return "redis"
        elif query and query.strip().startswith("{"):
            return "mongodb"
        else:
            return "code"

    async def stop(self) -> None:
        """Para consumo de mensagens."""
        self._running = False

        if self._consumer:
            await self._consumer.stop()
            logger.info("ticket_completed_consumer_stopped")

    async def close(self) -> None:
        """Fecha consumer."""
        await self.stop()
