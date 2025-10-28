import asyncio
import json
from typing import Optional
from aiokafka import AIOKafkaProducer
import structlog
from src.models.consolidated_decision import ConsolidatedDecision

logger = structlog.get_logger()


class DecisionProducer:
    '''Producer Kafka para tópico plans.consensus'''

    def __init__(self, config):
        self.config = config
        self.producer = None
        self.running = False

    async def initialize(self):
        '''Inicializa producer Kafka'''
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            enable_idempotence=self.config.kafka_enable_idempotence,
            transactional_id=self.config.kafka_transactional_id
        )

        await self.producer.start()
        logger.info(
            'Decision producer inicializado',
            topic=self.config.kafka_consensus_topic
        )

    async def start(self, decision_queue: asyncio.Queue):
        '''Inicia loop de produção

        Args:
            decision_queue: Fila assíncrona de decisões a publicar
        '''
        if not self.producer:
            raise RuntimeError('Producer não inicializado')

        self.running = True
        logger.info('Decision producer iniciado')

        try:
            while self.running:
                try:
                    # Aguardar decisão na fila (com timeout)
                    decision = await asyncio.wait_for(
                        decision_queue.get(),
                        timeout=1.0
                    )

                    await self._publish_decision(decision)

                except asyncio.TimeoutError:
                    # Timeout é esperado, continuar loop
                    continue

        except Exception as e:
            logger.error('Erro no loop de produção', error=str(e))
            raise

    async def stop(self):
        '''Para producer gracefully'''
        self.running = False
        if self.producer:
            await self.producer.stop()
        logger.info('Decision producer parado')

    async def _publish_decision(self, decision: ConsolidatedDecision):
        '''Publica decisão consolidada no Kafka'''
        try:
            # Converter para formato Avro-compatível
            decision_dict = decision.to_avro_dict()

            # Publicar no tópico
            await self.producer.send_and_wait(
                self.config.kafka_consensus_topic,
                value=decision_dict,
                key=decision.plan_id.encode('utf-8')
            )

            logger.info(
                'Decisão publicada',
                topic=self.config.kafka_consensus_topic,
                decision_id=decision.decision_id,
                plan_id=decision.plan_id,
                final_decision=decision.final_decision.value
            )

        except Exception as e:
            logger.error(
                'Erro publicando decisão',
                decision_id=decision.decision_id,
                plan_id=decision.plan_id,
                error=str(e)
            )
            raise
