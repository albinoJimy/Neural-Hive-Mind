import asyncio
import json
import os
import time
from typing import Dict, Any, Optional
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
import structlog
import grpc
from src.services.consensus_orchestrator import ConsensusOrchestrator
from src.observability.metrics import ConsensusMetrics

logger = structlog.get_logger()


class PlanConsumer:
    '''Consumer Kafka para tópico plans.ready usando confluent-kafka'''

    def __init__(self, config, specialists_client, mongodb_client, pheromone_client):
        self.config = config
        self.specialists_client = specialists_client
        self.mongodb_client = mongodb_client
        self.orchestrator = ConsensusOrchestrator(config, pheromone_client)
        self.consumer: Optional[Consumer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_deserializer: Optional[AvroDeserializer] = None
        self.running = False
        self.circuit_breaker_open = False

    async def initialize(self):
        '''Inicializa consumer Kafka com confluent-kafka'''
        consumer_config = {
            'bootstrap.servers': self.config.kafka_bootstrap_servers,
            'group.id': self.config.kafka_consumer_group_id,
            'auto.offset.reset': self.config.kafka_auto_offset_reset,
            'enable.auto.commit': self.config.kafka_enable_auto_commit,
        }

        self.consumer = Consumer(consumer_config)
        self.consumer.subscribe([self.config.kafka_plans_topic])

        # Configurar Schema Registry para deserialização Avro
        schema_registry_url = os.getenv('SCHEMA_REGISTRY_URL')
        if schema_registry_url and schema_registry_url.strip():
            schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'

            if os.path.exists(schema_path):
                self.schema_registry_client = SchemaRegistryClient({'url': schema_registry_url})

                with open(schema_path, 'r') as f:
                    schema_str = f.read()

                self.avro_deserializer = AvroDeserializer(
                    self.schema_registry_client,
                    schema_str
                )
                logger.info('Schema Registry configurado para consumer',
                           url=schema_registry_url,
                           schema_path=schema_path)
            else:
                logger.warning('Schema Avro não encontrado', path=schema_path)
                self.avro_deserializer = None
        else:
            logger.warning('Schema Registry não configurado - usando JSON fallback')
            self.avro_deserializer = None

        logger.info(
            'Plan consumer inicializado',
            topic=self.config.kafka_plans_topic,
            group_id=self.config.kafka_consumer_group_id
        )

    async def start(self):
        '''
        Inicia loop de consumo com confluent-kafka.

        Implementa padrão de resiliência com:
        - Retry automático em caso de erros transientes
        - Exponential backoff para evitar sobrecarga
        - Isolamento de erros por mensagem (não para o consumer por uma falha)

        Comportamento de commit de offset:
        - Erros sistêmicos (gRPC, MongoDB, rede): offset NÃO commitado, permite retry
        - Erros de negócio (validação, dados inválidos): offset NÃO commitado por padrão,
          permitindo retry manual ou análise. A mensagem permanece no Kafka.

        NOTA: DLQ ainda não está implementado. Configurações consumer_enable_dlq e
        kafka_dlq_topic são reservadas para implementação futura.
        '''
        if not self.consumer:
            raise RuntimeError('Consumer não inicializado')

        self.running = True
        consecutive_errors = 0
        # Usar configurações externalizadas
        max_consecutive_errors = self.config.consumer_max_consecutive_errors
        base_backoff_seconds = self.config.consumer_base_backoff_seconds
        max_backoff_seconds = self.config.consumer_max_backoff_seconds
        poll_timeout = self.config.consumer_poll_timeout_seconds

        # Inicializar estado do circuit breaker
        self.circuit_breaker_open = False
        ConsensusMetrics.set_circuit_breaker_state(False)
        ConsensusMetrics.set_consecutive_errors(0)

        logger.info('Plan consumer iniciado')

        while self.running:
            try:
                # Poll com timeout configurável (non-blocking)
                msg = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.consumer.poll(timeout=poll_timeout)
                )

                if msg is None:
                    # Reset consecutive errors on successful poll (even if empty)
                    consecutive_errors = 0
                    ConsensusMetrics.set_consecutive_errors(0)
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug('Reached end of partition')
                        consecutive_errors = 0
                        ConsensusMetrics.set_consecutive_errors(0)
                        continue
                    else:
                        logger.error('Erro no consumer Kafka', error=msg.error())
                        consecutive_errors += 1
                        ConsensusMetrics.set_consecutive_errors(consecutive_errors)
                        ConsensusMetrics.increment_consumer_error('kafka_error', is_systemic=True)

                        if consecutive_errors >= max_consecutive_errors:
                            logger.critical(
                                'Muitos erros consecutivos no consumer - parando',
                                consecutive_errors=consecutive_errors
                            )
                            self.circuit_breaker_open = True
                            ConsensusMetrics.set_circuit_breaker_state(True)
                            ConsensusMetrics.increment_circuit_breaker_trip()
                            break

                        # Backoff exponencial
                        backoff = min(
                            base_backoff_seconds * (2 ** consecutive_errors),
                            max_backoff_seconds
                        )
                        ConsensusMetrics.increment_backoff_event('kafka_error')
                        ConsensusMetrics.observe_backoff_duration(backoff, 'kafka_error')
                        logger.warning(
                            'Backoff antes de retry',
                            backoff_seconds=backoff,
                            consecutive_errors=consecutive_errors
                        )
                        await asyncio.sleep(backoff)
                        continue

                # Deserializar mensagem
                cognitive_plan = self._deserialize_value(msg)

                if cognitive_plan:
                    # Processar com isolamento de erro por mensagem
                    start_time = time.time()
                    try:
                        await self._process_message(msg, cognitive_plan)
                        # Reset consecutive errors após sucesso
                        consecutive_errors = 0
                        ConsensusMetrics.set_consecutive_errors(0)
                        # Métricas de sucesso
                        duration = time.time() - start_time
                        ConsensusMetrics.observe_processing_duration(duration, 'success')
                        ConsensusMetrics.increment_message_processed('success')
                    except Exception as process_error:
                        # Métricas de falha
                        duration = time.time() - start_time
                        ConsensusMetrics.observe_processing_duration(duration, 'failed')
                        ConsensusMetrics.increment_message_processed('failed', type(process_error).__name__)

                        # Erro ao processar mensagem específica
                        # NÃO para o consumer - apenas loga e continua
                        logger.error(
                            'Erro processando mensagem - continuando consumer',
                            error=str(process_error),
                            error_type=type(process_error).__name__,
                            topic=msg.topic(),
                            partition=msg.partition(),
                            offset=msg.offset(),
                            plan_id=cognitive_plan.get('plan_id', 'unknown')
                        )

                        # Incrementar apenas se for erro repetido no mesmo tipo
                        # Erros de processamento individual não devem parar o consumer
                        # mas erros sistêmicos (gRPC, MongoDB down) devem ser detectados
                        if self._is_systemic_error(process_error):
                            consecutive_errors += 1
                            ConsensusMetrics.set_consecutive_errors(consecutive_errors)
                            ConsensusMetrics.increment_consumer_error(type(process_error).__name__, is_systemic=True)

                            if consecutive_errors >= max_consecutive_errors:
                                logger.critical(
                                    'Erros sistêmicos detectados - parando consumer',
                                    consecutive_errors=consecutive_errors,
                                    error_type=type(process_error).__name__
                                )
                                self.circuit_breaker_open = True
                                ConsensusMetrics.set_circuit_breaker_state(True)
                                ConsensusMetrics.increment_circuit_breaker_trip()
                                break

                            # Backoff para erros sistêmicos
                            backoff = min(
                                base_backoff_seconds * (2 ** consecutive_errors),
                                max_backoff_seconds
                            )
                            ConsensusMetrics.increment_backoff_event('systemic_error')
                            ConsensusMetrics.observe_backoff_duration(backoff, 'systemic_error')
                            logger.warning(
                                'Backoff para erro sistêmico',
                                backoff_seconds=backoff
                            )
                            await asyncio.sleep(backoff)
                        else:
                            # Erro de negócio - NÃO commita offset, permite retry/análise
                            ConsensusMetrics.increment_consumer_error(type(process_error).__name__, is_systemic=False)
                            logger.warning(
                                'Erro de negócio - offset NÃO commitado, mensagem permanece no Kafka',
                                offset=msg.offset(),
                                plan_id=cognitive_plan.get('plan_id', 'unknown'),
                                error_type=type(process_error).__name__
                            )

            except asyncio.CancelledError:
                logger.info('Consumer cancelado via asyncio')
                break
            except Exception as loop_error:
                # Erro inesperado no loop principal
                logger.error(
                    'Erro inesperado no loop de consumo',
                    error=str(loop_error),
                    error_type=type(loop_error).__name__
                )
                consecutive_errors += 1
                ConsensusMetrics.set_consecutive_errors(consecutive_errors)
                ConsensusMetrics.increment_consumer_error(type(loop_error).__name__, is_systemic=True)

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        'Erros críticos no loop - parando consumer',
                        consecutive_errors=consecutive_errors
                    )
                    self.circuit_breaker_open = True
                    ConsensusMetrics.set_circuit_breaker_state(True)
                    ConsensusMetrics.increment_circuit_breaker_trip()
                    break

                # Backoff
                backoff = min(
                    base_backoff_seconds * (2 ** consecutive_errors),
                    max_backoff_seconds
                )
                ConsensusMetrics.increment_backoff_event('loop_error')
                ConsensusMetrics.observe_backoff_duration(backoff, 'loop_error')
                await asyncio.sleep(backoff)

        logger.info(
            'Consumer loop finalizado',
            consecutive_errors=consecutive_errors,
            was_running=self.running,
            circuit_breaker_open=self.circuit_breaker_open
        )

    def _is_systemic_error(self, error: Exception) -> bool:
        '''
        Determina se um erro é sistêmico (infraestrutura) vs erro de negócio.

        Erros sistêmicos indicam problemas com:
        - Conectividade gRPC (specialists down)
        - MongoDB indisponível
        - Kafka producer falhou
        - Timeout de rede

        Erros de negócio são:
        - Validação de dados
        - Lógica de negócio
        - Dados inválidos no plano
        '''
        systemic_error_types = (
            ConnectionError,
            TimeoutError,
            OSError,
            grpc.RpcError,  # Falhas gRPC nos specialists
        )

        systemic_error_keywords = [
            'connection', 'timeout', 'unavailable', 'refused',
            'network', 'socket', 'dns', 'grpc', 'mongodb', 'kafka',
            'unreachable', 'connect', 'deadline exceeded'
        ]

        # Check by exception type
        if isinstance(error, systemic_error_types):
            return True

        # Check by error message
        error_msg = str(error).lower()
        return any(keyword in error_msg for keyword in systemic_error_keywords)

    def _deserialize_value(self, msg):
        '''Deserializa o valor da mensagem (Avro ou JSON)'''
        try:
            if self.avro_deserializer:
                # Deserializar com Avro
                ctx = SerializationContext(msg.topic(), MessageField.VALUE)
                return self.avro_deserializer(msg.value(), ctx)
            else:
                # Fallback JSON
                return json.loads(msg.value().decode('utf-8'))
        except Exception as e:
            logger.error('Erro deserializando mensagem',
                        error=str(e),
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset())
            return None

    async def stop(self):
        '''Para consumer gracefully'''
        self.running = False
        if self.consumer:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.consumer.close
            )
        logger.info('Plan consumer parado')

    async def _process_message(self, msg, cognitive_plan):
        '''Processa mensagem do Kafka'''
        try:
            logger.info(
                'Mensagem recebida',
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
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

            logger.info(
                'Decisao salva no ledger',
                decision_id=decision.decision_id,
                plan_id=cognitive_plan['plan_id'],
                final_decision=decision.final_decision.value
            )

            # 4. Publicar decisão no Kafka (será feito pelo producer)
            # Armazenar na fila de produção
            from src.main import state
            if hasattr(state, 'decision_queue'):
                await state.decision_queue.put(decision)

            # 5. Commit manual do offset
            if not self.config.kafka_enable_auto_commit:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.consumer.commit(msg)
                    )
                    ConsensusMetrics.increment_offset_commit('success')
                except Exception as commit_err:
                    ConsensusMetrics.increment_offset_commit('failed')
                    raise commit_err

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
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
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
