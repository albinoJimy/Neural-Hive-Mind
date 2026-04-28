"""
Consumidor Kafka para Relatorios de Exclusao GDPR
"""

import asyncio
import json

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from src.config.settings import Settings, get_settings

logger = structlog.get_logger()


class ErasureReportConsumer:
    """Consome relatorios de exclusao dos services"""

    def __init__(self, settings: Settings):
        """
        Inicializa o consumidor.

        Args:
            settings: Configuracoes
        """
        self.settings = settings
        self.consumer: AIOKafkaConsumer | None = None
        self.running = False
        self._erasure_service = None

    async def initialize(self) -> None:
        """Inicializa o consumidor Kafka"""
        self.consumer = AIOKafkaConsumer(
            self.settings.kafka_erasure_reports_topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id="gdpr-erasure-service",
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        await self.consumer.start()
        logger.info("ErasureReportConsumer inicializado")

    def set_erasure_service(self, service) -> None:
        """Define referencia para o servico de exclusao"""
        self._erasure_service = service

    async def start_consuming(self, handler=None) -> None:
        """
        Inicia o consumo de mensagens.

        Args:
            handler: Handler opcional para processar relatorios
        """
        if not self.consumer:
            raise RuntimeError("Consumer nao inicializado")

        if not self._erasure_service:
            raise RuntimeError("ErasureService nao configurado")

        self.running = True
        logger.info("Iniciando consumo de relatorios")

        try:
            async for msg in self.consumer:
                if not self.running:
                    break

                await self._process_message(msg.value)

        except KafkaError as e:
            logger.error("Erro no Kafka", error=str(e))
        finally:
            await self.close()

    async def _process_message(self, report_data: dict) -> None:
        """
        Processa um relatorio de exclusao.

        Args:
            report_data: Dados do relatorio
        """
        try:
            logger.info(
                "Processando relatorio de exclusao",
                request_id=report_data.get("request_id"),
                service=report_data.get("service"),
            )

            await self._erasure_service.handle_erasure_report(report_data)

        except Exception as e:
            logger.error(
                "Erro ao processar relatorio",
                request_id=report_data.get("request_id"),
                error=str(e),
            )

    async def close(self) -> None:
        """Fecha o consumidor"""
        self.running = False
        if self.consumer:
            await self.consumer.stop()
            logger.info("ErasureReportConsumer fechado")
