"""
ConsensusDecisionConsumer - Consumer Kafka para decisões de consenso.

Responsável por:
- Consumir eventos do tópico consensus.decision.created
- Gerar explicações automaticamente para novas decisões
- Publicar explicações no tópico consensus.explanations
- Reutilizar explicações existentes quando disponível

GAPS-04 Task 6
"""

from typing import Optional
import structlog
import json
import asyncio
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

logger = structlog.get_logger(__name__)


class ConsensusDecisionConsumer:
    """
    Consumer Kafka para eventos de decisão de consenso.

    Escuta o tópico consensus.decision.created e gera explicações
    automaticamente usando ExplainabilityAPIExtensions.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        explainability_service,
        explanation_producer,
        input_topic: str = 'consensus.decision.created',
        output_topic: str = 'consensus.explanations'
    ):
        """
        Inicializa o ConsensusDecisionConsumer.

        Args:
            bootstrap_servers: Servidores Kafka
            group_id: ID do consumer group
            explainability_service: ExplainabilityAPIExtensions para gerar explicações
            explanation_producer: Producer para publicar explicações
            input_topic: Tópico de entrada (padrão: consensus.decision.created)
            output_topic: Tópico de saída (padrão: consensus.explanations)
        """
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.explainability_service = explainability_service
        self.explanation_producer = explanation_producer
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._consuming = False
        self._consumer_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """
        Inicializa consumer Kafka.

        Raises:
            Exception se falhar ao conectar
        """
        try:
            self.consumer = AIOKafkaConsumer(
                self.input_topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=False,  # Commit manual
                max_poll_records=10,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )

            await self.consumer.start()

            logger.info(
                "consensus_decision_consumer.connected",
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                input_topic=self.input_topic
            )

        except Exception as e:
            logger.error(
                "consensus_decision_consumer.connection_failed",
                error=str(e)
            )
            raise

    async def start_consuming(self) -> None:
        """
        Inicia loop de consumo de mensagens em background.
        """
        if self._consuming:
            logger.warning("consensus_decision_consumer.already_consuming")
            return

        self._consuming = True
        self._consumer_task = asyncio.create_task(self._consume_loop())

        logger.info("consensus_decision_consumer.started")

    async def stop(self) -> None:
        """
        Para consumo e fecha consumer.
        """
        logger.info("consensus_decision_consumer.stopping")

        self._consuming = False

        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        if self.consumer:
            await self.consumer.stop()

        logger.info("consensus_decision_consumer.stopped")

    async def _consume_loop(self) -> None:
        """
        Loop principal de consumo de mensagens.
        """
        try:
            while self._consuming:
                try:
                    # Buscar mensagens (timeout 1s)
                    messages = await asyncio.wait_for(
                        self.consumer.getmany(timeout_ms=1000),
                        timeout=2.0
                    )

                    # Processar mensagens
                    for tp, msgs in messages.items():
                        for message in msgs:
                            try:
                                await self.handle_decision(message.value)

                                # Commit offset após processamento bem-sucedido
                                await self.consumer.commit()

                            except Exception as e:
                                logger.error(
                                    "consensus_decision_consumer.message_processing_failed",
                                    error=str(e),
                                    partition=tp.partition,
                                    offset=message.offset
                                )
                                # Não commitar offset em caso de erro
                                # Mensagem será reprocessada

                except asyncio.TimeoutError:
                    # Timeout normal, continuar loop
                    continue

                except KafkaError as e:
                    logger.error(
                        "consensus_decision_consumer.kafka_error",
                        error=str(e)
                    )
                    await asyncio.sleep(5)  # Backoff

        except asyncio.CancelledError:
            logger.info("consensus_decision_consumer.consume_loop_cancelled")
            raise

        except Exception as e:
            logger.error(
                "consensus_decision_consumer.consume_loop_error",
                error=str(e)
            )
            self._consuming = False

    async def handle_decision(self, decision: dict) -> None:
        """
        Processa evento de decisão e gera/publica explicação.

        Args:
            decision: Dicionário com dados da decisão de consenso
        """
        decision_id = decision.get("decision_id", "unknown")

        logger.info(
            "consensus_decision_consumer.handling_decision",
            decision_id=decision_id,
            final_decision=decision.get("final_decision")
        )

        try:
            # 1. Verificar se explicação já existe
            existing = await self.explainability_service.get_explainability_by_decision_id(decision_id)

            if existing:
                logger.info(
                    "consensus_decision_consumer.existing_explanation_found",
                    decision_id=decision_id,
                    explainability_token=existing.get("explainability_token")
                )
                explanation = existing
            else:
                # 2. Gerar nova explicação
                logger.info(
                    "consensus_decision_consumer.generating_new_explanation",
                    decision_id=decision_id
                )

                generation_request = {
                    'decision_id': decision_id,
                    'format': 'json',
                    'include_shap': True,
                    'include_reasoning_extraction': True,
                    'include_quality_score': True,
                    'specialist_votes': decision.get('specialist_opinions', []),
                    'final_decision': decision.get('final_decision'),
                    'reasoning_text': decision.get('reasoning_summary', '')
                }

                explanation = await self.explainability_service.generate_explanation(generation_request)

            # 3. Publicar explicação
            await self.explanation_producer.publish_explanation(explanation)

            logger.info(
                "consensus_decision_consumer.explanation_published",
                decision_id=decision_id,
                explainability_token=explanation.get("explainability_token")
            )

        except Exception as e:
            logger.error(
                "consensus_decision_consumer.handle_decision_failed",
                decision_id=decision_id,
                error=str(e)
            )
            raise
