"""Consumidor Kafka para requisições de inferência."""

import asyncio
import json
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

logger = structlog.get_logger(__name__)


class InferenceRequestConsumer:
    """Consome eventos inference.requests e processa inferências ML."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic: str = "inference.requests",
        group_id: str = "ml-inference-api",
    ):
        """Inicializa o consumidor.

        Args:
            bootstrap_servers: Endereço do Kafka
            topic: Tópico para consumir
            group_id: ID do grupo consumidor
        """
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False
        self._logger = logger

    async def start(self) -> None:
        """Inicia o consumidor Kafka."""
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self._consumer.start()
        self._running = True

        self._logger.info(
            "inference_request_consumer_started",
            topic=self._topic,
            group_id=self._group_id,
        )

        # Iniciar task de processamento
        asyncio.create_task(self._process_messages())

    async def stop(self) -> None:
        """Para o consumidor Kafka."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._logger.info("inference_request_consumer_stopped")

    async def _process_messages(self) -> None:
        """Processa mensagens do Kafka em loop."""
        try:
            async for msg in self._consumer:
                await self._handle_message(msg.value)
        except KafkaError as e:
            self._logger.error("kafka_error", error=str(e))
        except Exception as e:
            self._logger.error("consumer_error", error=str(e))
        finally:
            if self._running:
                await asyncio.sleep(1)

    async def _handle_message(self, message: bytes) -> None:
        """Handle uma mensagem do Kafka.

        Args:
            message: Mensagem em bytes (JSON)
        """
        try:
            data = json.loads(message.decode("utf-8"))
        except json.JSONDecodeError as e:
            self._logger.warning("invalid_json", error=str(e))
            return

        # Extrair informações da requisição
        request_id = data.get("request_id")
        model_name = data.get("model_name")
        features = data.get("features", {})

        self._logger.info(
            "inference_request_received",
            request_id=request_id,
            model_name=model_name,
        )

        # TODO: Processar inferência
        # - Carregar modelo
        # - Executar predição
        # - Publicar resultado em inference.results

        self._logger.info(
            "inference_processed",
            request_id=request_id,
        )
