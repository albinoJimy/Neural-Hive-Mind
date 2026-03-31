"""
Kafka consumer para tópico digital.events.

Consome eventos de canais digitais (web, mobile, API, etc.) e
processa através do ExplorationEngine para detecção de sinais.

Author: Neural-Hive-Mind
Created: 2026-03-31 (CR-02)
"""
import json
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from neural_hive_observability import instrument_kafka_consumer
from neural_hive_observability.context import (
    extract_context_from_headers,
    set_baggage
)

from ..models.digital_event import DigitalEvent, DigitalEventType, DigitalChannel

logger = structlog.get_logger(__name__)


class DigitalEventsConsumer:
    """
    Consumer Kafka para tópico digital.events.

    Processa eventos de canais digitais e os converte em sinais
    de exploração através do ExplorationEngine.
    """

    def __init__(
        self,
        settings,
        exploration_engine=None,
        metrics=None
    ):
        """
        Inicializa o consumer.

        Args:
            settings: Configurações da aplicação
            exploration_engine: Engine de exploração para processamento
            metrics: Instância de métricas para monitoramento
        """
        self.settings = settings
        self.exploration_engine = exploration_engine
        self.metrics = metrics
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False

        # Estatísticas de processamento
        self.stats = {
            'events_consumed': 0,
            'events_processed': 0,
            'events_failed': 0,
            'last_event_at': None
        }

    async def initialize(self):
        """Inicializa o consumer Kafka."""
        topic = getattr(self.settings.kafka, 'topics_digital_events', 'digital.events')
        logger.info('Inicializando DigitalEventsConsumer', topic=topic)

        self.consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.settings.kafka.bootstrap_servers,
            group_id=self.settings.kafka.consumer_group_id + '-digital',
            auto_offset_reset='latest',
            enable_auto_commit=False,
            value_deserializer=lambda m: m.decode('utf-8') if isinstance(m, bytes) else m
        )

        self.consumer = instrument_kafka_consumer(self.consumer)
        await self.consumer.start()
        logger.info('DigitalEventsConsumer inicializado com sucesso', topic=topic)

    async def start(self):
        """
        Inicia loop de consumo de mensagens.

        Este método roda em loop até que self.running seja False.
        """
        if not self.consumer:
            raise RuntimeError('Consumer não foi inicializado. Chame initialize() primeiro.')

        logger.info('Iniciando consumo de eventos digitais')
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_message(message)
                    # Commit após processamento bem-sucedido
                    await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        'Erro ao processar evento digital',
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=False
                    )
                    self.stats['events_failed'] += 1
                    # Não commitar offset em caso de erro para permitir retry

        except Exception as e:
            logger.error('Erro no loop de consumo', error=str(e), exc_info=True)
            raise

    async def stop(self):
        """Para o consumer gracefulmente."""
        logger.info('Parando DigitalEventsConsumer')
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info(
            'DigitalEventsConsumer parado',
            stats=self.stats
        )

    def _deserialize_event(self, event_data: str) -> Optional[DigitalEvent]:
        """
        Deserializa dados JSON para um DigitalEvent.

        Args:
            event_data: String JSON com dados do evento

        Returns:
            DigitalEvent se válido, None caso contrário
        """
        try:
            data = json.loads(event_data) if isinstance(event_data, str) else event_data

            # Validar campos obrigatórios
            if 'event_id' not in data:
                logger.warning('evento_sem_event_id', data=event_data)
                return None

            if 'event_type' not in data:
                logger.warning('evento_sem_event_type', event_id=data.get('event_id'))
                return None

            if 'channel' not in data:
                logger.warning('evento_sem_channel', event_id=data.get('event_id'))
                return None

            # Criar DigitalEvent
            event = DigitalEvent(**data)

            if not event.is_valid():
                logger.warning('evento_invalido', event_id=event.event_id)
                return None

            return event

        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error('erro_desserializacao', error=str(e))
            return None
        except Exception as e:
            logger.error('erro_inesperado_desserializacao', error=str(e))
            return None

    async def _process_message(self, message) -> None:
        """
        Processa uma mensagem do Kafka.

        Args:
            message: Mensagem Kafka contendo DigitalEvent
        """
        # Extrair headers para contexto de tracing
        extract_context_from_headers(message.headers or [])

        # Desserializar evento
        event = self._deserialize_event(message.value)

        if not event:
            logger.debug(
                'evento_ignorado',
                topic=message.topic,
                partition=message.partition,
                offset=message.offset
            )
            return

        self.stats['events_consumed'] += 1

        logger.info(
            'evento_digital_recebido',
            event_id=event.event_id,
            type=str(event.event_type),
            channel=str(event.channel),
            partition=message.partition,
            offset=message.offset
        )

        # Definir baggage para tracing
        correlation_id = event.metadata.get('correlation_id')
        if correlation_id:
            set_baggage('correlation_id', correlation_id)

        # Processar evento através da exploration engine
        await self._forward_to_exploration_engine(event)

        # Atualizar métricas
        if self.metrics:
            self.metrics.digital_events_consumed_total.labels(
                type=str(event.event_type),
                channel=str(event.channel)
            ).inc()

        self.stats['events_processed'] += 1
        self.stats['last_event_at'] = datetime.utcnow()

        logger.debug('evento_digital_processado', event_id=event.event_id)

    async def _forward_to_exploration_engine(self, event: DigitalEvent) -> None:
        """
        Encaminha evento para a ExplorationEngine processar.

        Args:
            event: Evento digital processado
        """
        if not self.exploration_engine:
            logger.debug('exploration_engine_nao_configada')
            return

        try:
            # Converter para formato compatível com RawEvent
            raw_event_data = event.to_raw_event()

            # Chamar método de processamento da engine
            # Se a engine tiver método específico para eventos digitais, usá-lo
            if hasattr(self.exploration_engine, 'process_digital_event'):
                await self.exploration_engine.process_digital_event(event)
            else:
                # Fallback: converter para RawEvent e usar process_event
                from ..models.raw_event import RawEvent
                from neural_hive_domain import UnifiedDomain

                raw_event = RawEvent(
                    event_id=raw_event_data['event_id'],
                    event_type=raw_event_data['event_type'],
                    source=raw_event_data['source'],
                    timestamp=datetime.fromisoformat(raw_event_data['timestamp']),
                    payload=raw_event_data['payload'],
                    metadata=raw_event_data['metadata']
                )

                # Usar domínio BEHAVIOR para eventos digitais
                await self.exploration_engine.process_event(
                    event=raw_event,
                    domain=UnifiedDomain.BEHAVIOR
                )

            logger.debug(
                'evento_encaminhado_para_engine',
                event_id=event.event_id
            )

        except Exception as e:
            logger.error(
                'erro_encaminhar_para_engine',
                event_id=event.event_id,
                error=str(e)
            )
            raise

    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas de consumo.

        Returns:
            Dicionário com estatísticas agregadas
        """
        return {
            **self.stats,
            'running': self.running
        }
