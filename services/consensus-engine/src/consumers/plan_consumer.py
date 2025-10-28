import asyncio
import json
from typing import Dict, Any
from aiokafka import AIOKafkaConsumer
import structlog
from src.services.consensus_orchestrator import ConsensusOrchestrator

logger = structlog.get_logger()


class PlanConsumer:
    '''Consumer Kafka para tópico plans.ready'''

    def __init__(self, config, specialists_client, mongodb_client, pheromone_client):
        self.config = config
        self.specialists_client = specialists_client
        self.mongodb_client = mongodb_client
        self.orchestrator = ConsensusOrchestrator(config, pheromone_client)
        self.consumer = None
        self.running = False

    async def initialize(self):
        '''Inicializa consumer Kafka'''
        self.consumer = AIOKafkaConsumer(
            self.config.kafka_plans_topic,
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            group_id=self.config.kafka_consumer_group_id,
            auto_offset_reset=self.config.kafka_auto_offset_reset,
            enable_auto_commit=self.config.kafka_enable_auto_commit,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )

        await self.consumer.start()
        logger.info(
            'Plan consumer inicializado',
            topic=self.config.kafka_plans_topic,
            group_id=self.config.kafka_consumer_group_id
        )

    async def start(self):
        '''Inicia loop de consumo'''
        if not self.consumer:
            raise RuntimeError('Consumer não inicializado')

        self.running = True
        logger.info('Plan consumer iniciado')

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                await self._process_message(message)

        except Exception as e:
            logger.error('Erro no loop de consumo', error=str(e))
            raise

    async def stop(self):
        '''Para consumer gracefully'''
        self.running = False
        if self.consumer:
            await self.consumer.stop()
        logger.info('Plan consumer parado')

    async def _process_message(self, message):
        '''Processa mensagem do Kafka'''
        try:
            cognitive_plan = message.value

            logger.info(
                'Mensagem recebida',
                topic=message.topic,
                partition=message.partition,
                offset=message.offset,
                plan_id=cognitive_plan.get('plan_id')
            )

            # 1. Invocar especialistas via gRPC
            specialist_opinions = await self._invoke_specialists(cognitive_plan)

            # 2. Processar consenso
            decision = await self.orchestrator.process_consensus(
                cognitive_plan,
                specialist_opinions
            )

            # 3. Persistir no ledger (MongoDB)
            await self.mongodb_client.save_consensus_decision(decision)

            # 4. Publicar decisão no Kafka (será feito pelo producer)
            # Armazenar na fila de produção
            from src.main import state
            if hasattr(state, 'decision_queue'):
                await state.decision_queue.put(decision)

            # 5. Commit manual do offset
            if not self.config.kafka_enable_auto_commit:
                await self.consumer.commit()

            logger.info(
                'Mensagem processada com sucesso',
                plan_id=cognitive_plan['plan_id'],
                decision_id=decision.decision_id,
                final_decision=decision.final_decision.value
            )

        except Exception as e:
            logger.error(
                'Erro processando mensagem',
                error=str(e),
                topic=message.topic,
                partition=message.partition,
                offset=message.offset
            )
            # Não commitar offset em caso de erro (permitir retry)
            raise

    async def _invoke_specialists(self, cognitive_plan: Dict[str, Any]):
        '''Invoca todos os especialistas em paralelo via gRPC'''
        logger.info(
            'Invocando especialistas',
            plan_id=cognitive_plan['plan_id']
        )

        # Extrair trace context das mensagens Kafka ou criar novo
        trace_context = {
            'trace_id': cognitive_plan.get('trace_id', ''),
            'span_id': cognitive_plan.get('span_id', '')
        }

        # Invocar todos em paralelo se habilitado
        if self.config.enable_parallel_invocation:
            opinions = await self.specialists_client.evaluate_plan_parallel(
                cognitive_plan,
                trace_context
            )
        else:
            # Sequencial (fallback)
            opinions = []
            for specialist_type in ['business', 'technical', 'behavior', 'evolution', 'architecture']:
                try:
                    opinion = await self.specialists_client.evaluate_plan(
                        specialist_type,
                        cognitive_plan,
                        trace_context
                    )
                    opinions.append(opinion)
                except Exception as e:
                    logger.error(
                        'Erro invocando especialista',
                        specialist_type=specialist_type,
                        error=str(e)
                    )

        logger.info(
            'Especialistas invocados',
            plan_id=cognitive_plan['plan_id'],
            num_opinions=len(opinions)
        )

        return opinions
