"""Consumer Kafka para geração on-demand de documentos de aprendizado

Processa eventos de:
- experiment.completed: Gera relatório de experimento
- model.promoted: Gera relatório de promoção
- deployment.rolled_back: Gera análise de rollback

Publica resultados no tópico learning.doc.generated
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional

import structlog
from aiokafka import AIOKafkaConsumer
from src.config import get_settings
from src.models import (
    DocumentFormat,
    DocumentStatus,
    DocumentType,
    ExperimentRun,
    Insight,
    InsightConfidence,
    LearningDocument,
)
from src.services import (
    DocumentRepository,
    ExperimentInsightExtractor,
    MarkdownReportGenerator,
)

from neural_hive_observability import instrument_kafka_consumer

logger = structlog.get_logger()


class LearningEventConsumer:
    """Consumer Kafka para eventos de aprendizado"""

    # Tópicos
    TOPIC_EXPERIMENT_COMPLETED = "experiment.completed"
    TOPIC_MODEL_PROMOTED = "model.promoted"
    TOPIC_DEPLOYMENT_ROLLED_BACK = "deployment.rolled_back"

    def __init__(
        self,
        repository: DocumentRepository,
        insight_extractor: ExperimentInsightExtractor,
        report_generator: MarkdownReportGenerator,
        kafka_producer=None,
    ):
        """Inicializa o consumer

        Args:
            repository: Repositório MongoDB
            insight_extractor: Extrator de insights do MLflow
            report_generator: Gerador de relatórios Markdown
            kafka_producer: Producer Kafka para publicar eventos (opcional)
        """
        self.settings = get_settings()
        self.repository = repository
        self.insight_extractor = insight_extractor
        self.report_generator = report_generator
        self.kafka_producer = kafka_producer

        self.consumer: Optional[AIOKafkaConsumer] = None
        self._consume_task: Optional[asyncio.Task] = None
        self._running = False
        self._retry_queue: asyncio.Queue = asyncio.Queue()
        self._retry_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Inicia o consumer Kafka"""
        if self._running:
            logger.warning("consumer_ja_em_execucao")
            return

        try:
            # Configurar consumer
            consumer_config = {
                "bootstrap_servers": self.settings.kafka_bootstrap_servers,
                "group_id": self.settings.kafka_consumer_group_id,
                "auto_offset_reset": "latest",
                "enable_auto_commit": False,
            }

            # Configurar segurança se necessário
            if self.settings.kafka_security_protocol != "PLAINTEXT":
                consumer_config.update(
                    {
                        "security_protocol": self.settings.kafka_security_protocol,
                        "sasl_mechanism": self.settings.kafka_sasl_mechanism,
                        "sasl_plain_username": self.settings.kafka_sasl_username,
                        "sasl_plain_password": self.settings.kafka_sasl_password,
                    }
                )

            # Criar consumer com múltiplos tópicos
            topics = [
                self.settings.kafka_experiment_completed_topic,
                self.settings.kafka_model_promoted_topic,
                self.settings.kafka_deployment_rollback_topic,
            ]

            self.consumer = AIOKafkaConsumer(*topics, **consumer_config)
            self.consumer = instrument_kafka_consumer(self.consumer)

            await self.consumer.start()

            # Iniciar tarefas
            self._running = True
            self._consume_task = asyncio.create_task(self._consume_loop())
            self._retry_task = asyncio.create_task(self._retry_loop())

            logger.info(
                "kafka_consumer_iniciado",
                topics=topics,
                group_id=self.settings.kafka_consumer_group_id,
            )

        except Exception as e:
            logger.error("erro_ao_iniciar_consumer", error=str(e), exc_info=True)
            raise

    async def _consume_loop(self) -> None:
        """Loop principal de consumo"""
        try:
            async for message in self.consumer:
                if not self._running:
                    break

                try:
                    await self._process_message(message)

                    # Commit após processamento bem-sucedido
                    if not self.consumer._consumer._enable_auto_commit:
                        await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        "erro_ao_processar_mensagem",
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=True,
                    )

                    # Adicionar à fila de retry
                    await self._retry_queue.put((message, e))

                    # Commit mesmo assim para não bloquear o tópico
                    try:
                        await self.consumer.commit()
                    except:
                        pass

        except Exception as e:
            logger.error("erro_no_loop_de_consumo", error=str(e), exc_info=True)
        finally:
            await self.stop()

    async def _retry_loop(self) -> None:
        """Loop de retry de mensagens falhadas"""
        retry_delays = {1: 5, 2: 30, 3: 120}  # 5s, 30s, 2min

        while self._running:
            try:
                message, original_error = await asyncio.wait_for(
                    self._retry_queue.get(), timeout=1.0
                )

                # Extrair retry count dos headers
                retry_count = 0
                for header in message.headers or []:
                    if header[0] == "retry_count":
                        retry_count = int(header[1])
                        break

                if retry_count >= 3:
                    logger.warning(
                        "max_retries_alcancado",
                        topic=message.topic,
                        offset=message.offset,
                        retry_count=retry_count,
                    )
                    continue

                # Calcular delay
                delay = retry_delays.get(retry_count + 1, 300)
                await asyncio.sleep(delay)

                # Tentar processar novamente
                try:
                    await self._process_message(message)
                    logger.info(
                        "retry_sucesso",
                        topic=message.topic,
                        offset=message.offset,
                        retry_count=retry_count + 1,
                    )

                except Exception as e:
                    # Incrementar retry count e re-enfileirar
                    new_headers = list(message.headers or [])
                    new_headers.append(("retry_count", str(retry_count + 1).encode()))
                    message.headers = new_headers

                    await self._retry_queue.put((message, e))

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("erro_no_loop_de_retry", error=str(e), exc_info=True)

    async def _process_message(self, message) -> None:
        """Processa uma mensagem baseada no tópico

        Args:
            message: Mensagem Kafka
        """
        topic = message.topic

        # Deserializar payload
        try:
            event_data = self._deserialize(message.value)
        except Exception as e:
            logger.error("erro_ao_deserializar_mensagem", error=str(e))
            return

        # Roteamento baseado no tópico
        if topic == self.settings.kafka_experiment_completed_topic:
            await self._handle_experiment_completed(event_data)
        elif topic == self.settings.kafka_model_promoted_topic:
            await self._handle_model_promoted(event_data)
        elif topic == self.settings.kafka_deployment_rollback_topic:
            await self._handle_deployment_rollback(event_data)
        else:
            logger.warning("topico_desconhecido", topic=topic)

    def _deserialize(self, value: bytes) -> dict:
        """Deserializa mensagem JSON"""
        if isinstance(value, bytes):
            return json.loads(value.decode("utf-8"))
        return value

    async def _handle_experiment_completed(self, event_data: dict) -> None:
        """Handler para evento experiment.completed

        Args:
            event_data: Dados do evento
        """
        run_id = event_data.get("run_id")
        if not run_id:
            logger.warning("experiment_completed_sem_run_id", event_data=event_data)
            return

        logger.info("processando_experiment_completed", run_id=run_id)

        try:
            # Buscar detalhes do run no MLflow
            run = await self.insight_extractor.get_run_by_id(run_id)
            if not run:
                logger.warning("run_nao_encontrado", run_id=run_id)
                return

            # Converter para ExperimentRun
            experiment_run = ExperimentRun(
                run_id=run.info.run_id,
                experiment_id=run.info.experiment_id,
                name=run.data.tags.get("mlflow.runName", run_id),
                status=run.info.status,
                start_time=(
                    datetime.fromtimestamp(run.info.start_time / 1000)
                    if run.info.start_time
                    else None
                ),
                end_time=(
                    datetime.fromtimestamp(run.info.end_time / 1000) if run.info.end_time else None
                ),
                metrics=run.data.metrics,
                params={p.key: p.value for p in run.data.params},
                tags=run.data.tags,
                artifact_uri=run.info.artifact_uri,
            )

            # Extrair insights do run
            insights = await self.insight_extractor.extract_insights_from_runs([experiment_run])

            # Gerar resumo
            summary = self._generate_experiment_summary(experiment_run, insights)

            # Criar documento
            title = f"Relatório de Experimento - {experiment_run.name}"
            document = LearningDocument(
                title=title,
                type=DocumentType.EXPERIMENT_REPORT,
                status=DocumentStatus.COMPLETED,
                format=DocumentFormat.MARKDOWN,
                period_start=experiment_run.start_time,
                period_end=experiment_run.end_time or datetime.utcnow(),
                summary=summary,
                insights=insights,
                experiment_runs=[experiment_run],
                recommendations=self._generate_experiment_recommendations(insights),
                metadata={
                    "event_type": "experiment.completed",
                    "run_id": run_id,
                    "experiment_id": experiment_run.experiment_id,
                },
                generated_at=datetime.utcnow(),
            )

            # Salvar no MongoDB
            doc_id = await self.repository.save(document)

            logger.info(
                "documento_experimento_gerado",
                doc_id=doc_id,
                run_id=run_id,
                title=title,
            )

            # Publicar evento de documento gerado
            await self._publish_doc_generated_event(document, doc_id)

        except Exception as e:
            logger.error(
                "erro_ao_processar_experiment_completed",
                run_id=run_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _handle_model_promoted(self, event_data: dict) -> None:
        """Handler para evento model.promoted

        Args:
            event_data: Dados do evento
        """
        run_id = event_data.get("run_id")
        if not run_id:
            logger.warning("model_promoted_sem_run_id", event_data=event_data)
            return

        logger.info("processando_model_promoted", run_id=run_id)

        try:
            # Buscar run e runs relacionados (baseline + experiment)
            promoted_run = await self.insight_extractor.get_run_by_id(run_id)
            if not promoted_run:
                logger.warning("run_promovido_nao_encontrado", run_id=run_id)
                return

            # Buscar runs do mesmo experimento para comparação
            experiment_runs = await self.insight_extractor.get_runs_by_period(
                start_time=datetime.utcnow() - timedelta(days=30),
                end_time=datetime.utcnow(),
                experiment_id=promoted_run.info.experiment_id,
                limit=10,
            )

            # Converter para ExperimentRun
            runs = []
            for run in experiment_runs:
                runs.append(
                    ExperimentRun(
                        run_id=run.info.run_id,
                        experiment_id=run.info.experiment_id,
                        name=run.data.tags.get("mlflow.runName", run.info.run_id),
                        status=run.info.status,
                        start_time=(
                            datetime.fromtimestamp(run.info.start_time / 1000)
                            if run.info.start_time
                            else None
                        ),
                        end_time=(
                            datetime.fromtimestamp(run.info.end_time / 1000)
                            if run.info.end_time
                            else None
                        ),
                        metrics=run.data.metrics,
                        params={p.key: p.value for p in run.data.params},
                        tags=run.data.tags,
                        artifact_uri=run.info.artifact_uri,
                    )
                )

            # Extrair insights de comparação
            insights = await self.insight_extractor.extract_insights_from_runs(runs)

            # Adicionar insight específico de promoção
            if runs:
                best_run = promoted_run
                if hasattr(best_run, "data") and best_run.data.metrics:
                    val_acc = best_run.data.metrics.get("val_accuracy", 0)
                    insights.append(
                        Insight(
                            title="Modelo Promovido para Produção",
                            description=f"Modelo com val_accuracy={val_acc:.4f} promovido para produção",
                            evidence={"val_accuracy": val_acc, "run_id": run_id},
                            confidence=InsightConfidence.HIGH,
                            experiment_ids=[run_id],
                            category="promotion",
                        )
                    )

            # Gerar resumo
            summary = (
                f"Modelo baseado no run {run_id[:8]} foi promovido para produção. "
                f"Comparado com {len(runs) - 1} outros runs do mesmo período."
            )

            # Criar documento
            title = f"Relatório de Promoção de Modelo - {datetime.utcnow().strftime('%Y-%m-%d')}"
            document = LearningDocument(
                title=title,
                type=DocumentType.PROMOTION_REPORT,
                status=DocumentStatus.COMPLETED,
                format=DocumentFormat.MARKDOWN,
                period_start=datetime.utcnow() - timedelta(days=30),
                period_end=datetime.utcnow(),
                summary=summary,
                insights=insights,
                experiment_runs=runs,
                recommendations=[
                    "Monitorar métricas em produção nas próximas 24h",
                    "Comparar com baseline para validar melhoria",
                    "Preparar rollback se necessário",
                ],
                metadata={
                    "event_type": "model.promoted",
                    "run_id": run_id,
                    "approved_by": event_data.get("approved_by", "unknown"),
                    "approved_at": event_data.get("approved_at"),
                },
                generated_at=datetime.utcnow(),
            )

            # Salvar no MongoDB
            doc_id = await self.repository.save(document)

            logger.info(
                "documento_promocao_gerado",
                doc_id=doc_id,
                run_id=run_id,
            )

            # Publicar evento de documento gerado
            await self._publish_doc_generated_event(document, doc_id)

        except Exception as e:
            logger.error(
                "erro_ao_processar_model_promoted",
                run_id=run_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _handle_deployment_rollback(self, event_data: dict) -> None:
        """Handler para evento deployment.rolled_back

        Args:
            event_data: Dados do evento
        """
        run_id = event_data.get("run_id")
        rollback_reason = event_data.get("reason", "Unknown")

        logger.info("processando_deployment_rollback", run_id=run_id, reason=rollback_reason)

        try:
            # Buscar run que causou rollback
            problem_run = await self.insight_extractor.get_run_by_id(run_id)
            if not problem_run:
                logger.warning("run_problematico_nao_encontrado", run_id=run_id)
                return

            # Buscar run anterior (baseline para rollback)
            previous_runs = await self.insight_extractor.get_runs_by_period(
                start_time=datetime.utcnow() - timedelta(days=7),
                end_time=datetime.utcnow(),
                limit=10,
            )

            # Converter runs
            runs = []
            if problem_run:
                runs.append(
                    ExperimentRun(
                        run_id=problem_run.info.run_id,
                        experiment_id=problem_run.info.experiment_id,
                        name=problem_run.data.tags.get("mlflow.runName", run_id),
                        status=problem_run.info.status,
                        start_time=(
                            datetime.fromtimestamp(problem_run.info.start_time / 1000)
                            if problem_run.info.start_time
                            else None
                        ),
                        end_time=(
                            datetime.fromtimestamp(problem_run.info.end_time / 1000)
                            if problem_run.info.end_time
                            else None
                        ),
                        metrics=problem_run.data.metrics,
                        params={p.key: p.value for p in problem_run.data.params},
                        tags=problem_run.data.tags,
                        artifact_uri=problem_run.info.artifact_uri,
                    )
                )

            # Gerar insights sobre o rollback
            insights = [
                Insight(
                    title="Rollback Executado",
                    description=f"Deploy do modelo {run_id[:8]} foi revertido devido a: {rollback_reason}",
                    evidence={"rollback_reason": rollback_reason, "run_id": run_id},
                    confidence=InsightConfidence.HIGH,
                    experiment_ids=[run_id] if run_id else [],
                    category="rollback",
                )
            ]

            # Gerar resumo
            summary = (
                f"Rollback executado para o run {run_id[:8] if run_id else 'unknown'}. "
                f"Motivo: {rollback_reason}"
            )

            # Criar documento
            title = f"Análise de Rollback - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
            document = LearningDocument(
                title=title,
                type=DocumentType.ROLLBACK_ANALYSIS,
                status=DocumentStatus.COMPLETED,
                format=DocumentFormat.MARKDOWN,
                period_start=datetime.utcnow() - timedelta(hours=1),
                period_end=datetime.utcnow(),
                summary=summary,
                insights=insights,
                experiment_runs=runs,
                recommendations=[
                    "Investigar logs de produção para identificar causa raiz",
                    "Adicionar testes adicionais antes do próximo deploy",
                    "Revisar métricas de validação do modelo",
                    "Considerar implementar canary deployment",
                ],
                metadata={
                    "event_type": "deployment.rolled_back",
                    "run_id": run_id,
                    "rollback_reason": rollback_reason,
                    "detected_by": event_data.get("detected_by", "unknown"),
                },
                generated_at=datetime.utcnow(),
            )

            # Salvar no MongoDB
            doc_id = await self.repository.save(document)

            logger.info(
                "documento_rollback_gerado",
                doc_id=doc_id,
                run_id=run_id,
            )

            # Publicar evento de documento gerado
            await self._publish_doc_generated_event(document, doc_id)

        except Exception as e:
            logger.error(
                "erro_ao_processar_deployment_rollback",
                run_id=run_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _publish_doc_generated_event(self, document: LearningDocument, doc_id: str) -> None:
        """Publica evento no tópico learning.doc.generated

        Args:
            document: Documento gerado
            doc_id: ID do documento
        """
        if self.kafka_producer:
            try:
                await self.kafka_producer.publish_doc_generated(
                    doc_id=doc_id,
                    doc_type=document.type.value,
                    title=document.title,
                    metadata={
                        "generated_at": (
                            document.generated_at.isoformat() if document.generated_at else None
                        ),
                        "period_start": (
                            document.period_start.isoformat() if document.period_start else None
                        ),
                        "period_end": (
                            document.period_end.isoformat() if document.period_end else None
                        ),
                        **document.metadata,
                    },
                )
            except Exception as e:
                logger.error("erro_ao_publicar_doc_generated", doc_id=doc_id, error=str(e))

        logger.info(
            "doc_generated_event",
            doc_id=doc_id,
            doc_type=document.type,
            title=document.title,
        )

    def _generate_experiment_summary(self, run: ExperimentRun, insights: list) -> str:
        """Gera resumo do experimento"""
        status_emoji = {"FINISHED": "✅", "FAILED": "❌", "RUNNING": "🔄", "SCHEDULED": "⏳"}
        emoji = status_emoji.get(run.status, "❓")

        summary = f"{emoji} Experimento {run.name} finalizado com status {run.status}."

        if run.metrics:
            top_metrics = list(run.metrics.items())[:3]
            metrics_str = ", ".join([f"{k}={v:.4f}" for k, v in top_metrics])
            summary += f" Métricas principais: {metrics_str}."

        if insights:
            summary += f" {len(insights)} insights identificados."

        return summary

    def _generate_experiment_recommendations(self, insights: list) -> list:
        """Gera recomendações baseadas em insights do experimento"""
        recommendations = []

        for insight in insights:
            if insight.category == "performance" and insight.confidence == InsightConfidence.HIGH:
                recommendations.append(
                    "Considerar promover modelo para produção baseado em performance"
                )

            elif insight.category == "improvement":
                recommendations.append("Investigar hiperparâmetros que causaram melhoria")

            elif insight.category == "regression":
                recommendations.append("Revisar mudanças que causaram regressão")

        if not recommendations:
            recommendations.append("Continuar experimentando com variações de hiperparâmetros")

        return recommendations

    async def stop(self) -> None:
        """Para o consumer gracefulmente"""
        if not self._running:
            return

        logger.info("parando_consumer_kafka")
        self._running = False

        # Cancelar tarefas
        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass

        # Parar consumer
        if self.consumer:
            await self.consumer.stop()

        logger.info("consumer_kafka_parado")

    def is_running(self) -> bool:
        """Verifica se o consumer está em execução"""
        return self._running
