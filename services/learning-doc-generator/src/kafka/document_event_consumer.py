"""
Kafka Consumer para geração on-demand de documentos de aprendizado.

Consome eventos de conclusão de experimentos, promoção de modelos
e rollback de deployments para gerar documentação automaticamente.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError, KafkaError
import structlog

from src.config.settings import get_settings
from src.models.document import DocumentType, DocumentStatus
from src.services.document_repository import DocumentRepository
from src.services.experiment_insight_extractor import ExperimentInsightExtractor
from src.services.markdown_report_generator import MarkdownReportGenerator

UTC = timezone.utc
logger = structlog.get_logger()


class DocumentEventConsumer:
    """
    Consumer Kafka para geração de documentos on-demand.

    Processa eventos:
    - experiment.completed: Gerar relatório de experimento
    - model.promoted: Gerar relatório de promoção
    - deployment.rolled_back: Gerar análise de rollback
    """

    # Eventos suportados
    EVENT_EXPERIMENT_COMPLETED = "experiment.completed"
    EVENT_MODEL_PROMOTED = "model.promoted"
    EVENT_DEPLOYMENT_ROLLED_BACK = "deployment.rolled_back"

    def __init__(
        self,
        document_repository: DocumentRepository,
        insight_extractor: ExperimentInsightExtractor,
        report_generator: MarkdownReportGenerator,
    ):
        """
        Inicializar consumer.

        Args:
            document_repository: Repositório de documentos
            insight_extractor: Extrator de insights
            report_generator: Gerador de relatórios
        """
        self.settings = get_settings()
        self.document_repository = document_repository
        self.insight_extractor = insight_extractor
        self.report_generator = report_generator

        # Estado
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        self._tasks: set[asyncio.Task] = set()

        logger.info(
            "document_event_consumer_initialized",
            kafka_bootstrap_servers=self.settings.kafka_bootstrap_servers,
            consumer_group=self.settings.kafka_consumer_group,
        )

    async def start(self):
        """Iniciar consumer e processar eventos."""
        if self._running:
            logger.warning("consumer_already_running")
            return

        self._running = True

        # Criar consumer
        self._consumer = AIOKafkaConsumer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=self.settings.kafka_consumer_group,
            auto_offset_reset="latest",
            enable_auto_commit=False,
            value_deserializer=lambda m: m.decode("utf-8"),
        )

        # Subscrever tópicos
        topics = [
            self.settings.kafka_topic_experiments,
            self.settings.kafka_topic_models,
            self.settings.kafka_topic_deployments,
        ]

        try:
            await self._consumer.start()
            self._consumer.subscribe(topics)

            logger.info(
                "kafka_consumer_started",
                topics=topics,
                group_id=self.settings.kafka_consumer_group,
            )

            # Loop de processamento
            await self._consume_messages()

        except KafkaConnectionError as e:
            logger.error("kafka_connection_error", error=str(e))
            raise
        except KafkaError as e:
            logger.error("kafka_error", error=str(e))
            raise

    async def stop(self):
        """Parar consumer."""
        if not self._running:
            return

        self._running = False

        # Cancelar tarefas em background
        for task in self._tasks:
            task.cancel()

        # Aguardar conclusão das tarefas
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        # Fechar consumer
        if self._consumer:
            await self._consumer.stop()

        logger.info("kafka_consumer_stopped")

    async def _consume_messages(self):
        """Consumir e processar mensagens Kafka."""
        while self._running:
            try:
                # Batch de mensagens (timeout 1s)
                async for msg in self._consumer:
                    await self._process_message(msg)

            except asyncio.CancelledError:
                logger.info("consume_loop_cancelled")
                break
            except Exception as e:
                logger.error("error_consuming_message", error=str(e))
                # Backoff exponencial em caso de erro
                await asyncio.sleep(5)

    async def _process_message(self, message):
        """
        Processar mensagem Kafka individual.

        Args:
            message: Mensagem Kafka (topic, partition, offset, key, value)
        """
        try:
            topic = message.topic
            value = message.value

            # Parse JSON
            if isinstance(value, str):
                data = json.loads(value)
            else:
                data = value

            # Extrair tipo de evento
            event_type = data.get("event_type")
            event_id = data.get("event_id", str(uuid.uuid4()))

            logger.debug(
                "message_received",
                topic=topic,
                event_type=event_type,
                event_id=event_id,
            )

            # Roteamento por tipo de evento
            handler = self._get_handler(event_type)
            if handler:
                # Executar handler em background
                task = asyncio.create_task(
                    self._execute_with_retry(handler, event_type, data, event_id)
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            else:
                logger.warning(
                    "unknown_event_type",
                    event_type=event_type,
                    event_id=event_id,
                )

            # Commit offset após processamento bem-sucedido
            await self._consumer.commit()

        except json.JSONDecodeError as e:
            logger.error("invalid_json_message", error=str(e))
            # Não commit em caso de erro de parsing
        except Exception as e:
            logger.error("error_processing_message", error=str(e))
            # Não commit em caso de erro

    def _get_handler(self, event_type: str):
        """
        Obter handler para tipo de evento.

        Args:
            event_type: Tipo do evento

        Returns:
            Handler function ou None
        """
        handlers = {
            self.EVENT_EXPERIMENT_COMPLETED: self._handle_experiment_completed,
            self.EVENT_MODEL_PROMOTED: self._handle_model_promoted,
            self.EVENT_DEPLOYMENT_ROLLED_BACK: self._handle_deployment_rolled_back,
        }
        return handlers.get(event_type)

    async def _execute_with_retry(
        self,
        handler,
        event_type: str,
        data: Dict[str, Any],
        event_id: str,
    ):
        """
        Executar handler com retry em caso de falha.

        Args:
            handler: Handler function
            event_type: Tipo do evento
            data: Dados do evento
            event_id: ID do evento
        """
        max_retries = 3
        retry_delay = 5  # segundos

        for attempt in range(max_retries):
            try:
                await handler(data)
                logger.info(
                    "event_processed_successfully",
                    event_type=event_type,
                    event_id=event_id,
                    attempt=attempt + 1,
                )
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        "event_processing_failed_retrying",
                        event_type=event_type,
                        event_id=event_id,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        error=str(e),
                    )
                    await asyncio.sleep(retry_delay * (2**attempt))  # Exponential backoff
                else:
                    logger.error(
                        "event_processing_failed_max_retries",
                        event_type=event_type,
                        event_id=event_id,
                        error=str(e),
                    )

    async def _handle_experiment_completed(self, data: Dict[str, Any]):
        """
        Handler para evento experiment.completed.

        Gera relatório completo do experimento com insights e visualizações.

        Args:
            data: Dados do evento
                - experiment_id: ID do experimento
                - experiment_name: Nome do experimento
                - mlflow_run_ids: Lista de run IDs MLflow
                - metrics: Métricas coletadas
                - status: Status final (sucesso/falha)
        """
        experiment_id = data.get("experiment_id")
        if not experiment_id:
            logger.warning("experiment_completed_missing_id", data=data)
            return

        logger.info(
            "handling_experiment_completed",
            experiment_id=experiment_id,
        )

        # Verificar se documento já existe
        existing = await self.document_repository.find_by_experiment_id(experiment_id)
        if existing:
            logger.debug(
                "document_already_exists",
                experiment_id=experiment_id,
                doc_id=existing.get("doc_id"),
            )
            return

        # Extrair insights via MLflow
        mlflow_run_ids = data.get("mlflow_run_ids", [])
        insights = await self._extract_insights(mlflow_run_ids)

        # Gerar relatório Markdown
        report_content = await self.report_generator.generate_experiment_report(
            experiment_id=experiment_id,
            experiment_name=data.get("experiment_name", "Unknown"),
            experiment_type=data.get("experiment_type", "A_B_TEST"),
            insights=insights,
            metrics=data.get("metrics", {}),
            status=data.get("status", "completed"),
        )

        # Salvar documento
        doc_id = str(uuid.uuid4())
        document = {
            "doc_id": doc_id,
            "doc_type": DocumentType.EXPERIMENT_REPORT.value,
            "title": f"Experiment Report: {data.get('experiment_name', experiment_id)}",
            "content": report_content,
            "status": DocumentStatus.COMPLETED.value,
            "metadata": {
                "experiment_id": experiment_id,
                "experiment_name": data.get("experiment_name"),
                "mlflow_run_ids": mlflow_run_ids,
                "event_source": "kafka",
                "event_id": data.get("event_id"),
            },
            "experiment_ids": [experiment_id],
            "period_start": data.get("started_at"),
            "period_end": data.get("completed_at", datetime.now(UTC).isoformat()),
            "created_at": datetime.now(UTC).isoformat(),
            "insights": [i.model_dump() for i in insights],
        }

        await self.document_repository.create(document)

        logger.info(
            "experiment_report_generated",
            experiment_id=experiment_id,
            doc_id=doc_id,
        )

    async def _handle_model_promoted(self, data: Dict[str, Any]):
        """
        Handler para evento model.promoted.

        Gera relatório de promoção de modelo com comparação de versões.

        Args:
            data: Dados do evento
                - model_name: Nome do modelo
                - from_version: Versão anterior
                - to_version: Nova versão
                - promotion_reason: Razão da promoção
                - metrics_delta: Diferença de métricas
        """
        model_name = data.get("model_name")
        to_version = data.get("to_version")

        if not model_name or not to_version:
            logger.warning("model_promoted_missing_fields", data=data)
            return

        logger.info(
            "handling_model_promoted",
            model_name=model_name,
            to_version=to_version,
        )

        # Gerar relatório de promoção
        report_content = await self.report_generator.generate_promotion_report(
            model_name=model_name,
            from_version=data.get("from_version"),
            to_version=to_version,
            promotion_reason=data.get("promotion_reason", "Performance improved"),
            metrics_delta=data.get("metrics_delta", {}),
        )

        # Salvar documento
        doc_id = str(uuid.uuid4())
        document = {
            "doc_id": doc_id,
            "doc_type": DocumentType.PROMOTION_REPORT.value,
            "title": f"Promotion Report: {model_name} v{to_version}",
            "content": report_content,
            "status": DocumentStatus.COMPLETED.value,
            "metadata": {
                "model_name": model_name,
                "from_version": data.get("from_version"),
                "to_version": to_version,
                "promotion_reason": data.get("promotion_reason"),
                "event_source": "kafka",
            },
            "period_start": data.get("promoted_at"),
            "period_end": datetime.now(UTC).isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
        }

        await self.document_repository.create(document)

        logger.info(
            "promotion_report_generated",
            model_name=model_name,
            to_version=to_version,
            doc_id=doc_id,
        )

    async def _handle_deployment_rolled_back(self, data: Dict[str, Any]):
        """
        Handler para evento deployment.rolled_back.

        Gera análise de rollback com causa e impacto.

        Args:
            data: Dados do evento
                - component: Componente afetado
                - rollback_reason: Razão do rollback
                - from_version: Versão revertida
                - to_version: Versão restaurada
                - degradation_metrics: Métricas de degradação
        """
        component = data.get("component")
        rollback_reason = data.get("rollback_reason")

        if not component or not rollback_reason:
            logger.warning("deployment_rolled_back_missing_fields", data=data)
            return

        logger.info(
            "handling_deployment_rolled_back",
            component=component,
            rollback_reason=rollback_reason,
        )

        # Gerar análise de rollback
        report_content = await self.report_generator.generate_rollback_analysis(
            component=component,
            rollback_reason=rollback_reason,
            from_version=data.get("from_version"),
            to_version=data.get("to_version"),
            degradation_metrics=data.get("degradation_metrics", {}),
        )

        # Salvar documento
        doc_id = str(uuid.uuid4())
        document = {
            "doc_id": doc_id,
            "doc_type": DocumentType.ROLLBACK_ANALYSIS.value,
            "title": f"Rollback Analysis: {component}",
            "content": report_content,
            "status": DocumentStatus.COMPLETED.value,
            "metadata": {
                "component": component,
                "rollback_reason": rollback_reason,
                "from_version": data.get("from_version"),
                "to_version": data.get("to_version"),
                "event_source": "kafka",
            },
            "period_start": data.get("rolled_back_at"),
            "period_end": datetime.now(UTC).isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
        }

        await self.document_repository.create(document)

        logger.info(
            "rollback_analysis_generated",
            component=component,
            doc_id=doc_id,
        )

    async def _extract_insights(self, run_ids: list[str]):
        """
        Extrair insights dos runs MLflow.

        Args:
            run_ids: Lista de run IDs

        Returns:
            Lista de insights
        """
        if not run_ids:
            return []

        try:
            insights = []
            for run_id in run_ids:
                run_insights = await self.insight_extractor.extract_from_run(run_id)
                insights.extend(run_insights)
            return insights
        except Exception as e:
            logger.error("failed_to_extract_insights", error=str(e), run_ids=run_ids)
            return []


async def create_document_event_consumer(
    document_repository: DocumentRepository,
    insight_extractor: ExperimentInsightExtractor,
    report_generator: MarkdownReportGenerator,
) -> DocumentEventConsumer:
    """
    Factory para criar DocumentEventConsumer.

    Args:
        document_repository: Repositório de documentos
        insight_extractor: Extrator de insights
        report_generator: Gerador de relatórios

    Returns:
        Instância de DocumentEventConsumer
    """
    return DocumentEventConsumer(
        document_repository=document_repository,
        insight_extractor=insight_extractor,
        report_generator=report_generator,
    )
