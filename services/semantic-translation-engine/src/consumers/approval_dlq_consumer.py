"""
Approval DLQ Consumer - Kafka consumer para reprocessamento de Dead Letter Queue

Consome mensagens da DLQ de aprovações e tenta reprocessá-las com backoff
exponencial progressivo baseado no retry_count de cada mensagem.
"""

import asyncio
import json
import structlog
import time
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from confluent_kafka import Consumer, KafkaError, TopicPartition

from src.config.settings import Settings
from src.models.approval_dlq import ApprovalDLQEntry
from src.observability.metrics import NeuralHiveMetrics

logger = structlog.get_logger()


class ApprovalDLQConsumer:
    """
    Kafka consumer dedicado para reprocessamento da Dead Letter Queue de aprovações.

    Implementa polling periódico com backoff progressivo baseado no retry_count
    de cada mensagem DLQ. Mensagens que ainda não atingiram o backoff necessário
    são skipped e reprocessadas no próximo ciclo de polling.
    """

    def __init__(self, settings: Settings, metrics: Optional[NeuralHiveMetrics] = None):
        self.settings = settings
        self.metrics = metrics
        self.consumer: Optional[Consumer] = None
        self.running = False
        self.last_poll_time: Optional[float] = None
        self.messages_processed: int = 0
        self.messages_skipped: int = 0
        self._topic = settings.kafka_approval_dlq_topic
        self._consumer_group = f'{settings.kafka_consumer_group_id}-dlq-reprocessor'
        self._current_backlog: int = 0  # Estimativa de mensagens pendentes na DLQ

    async def initialize(self):
        """Inicializa Kafka consumer para DLQ de aprovações"""
        logger.info(
            'Iniciando inicialização do Approval DLQ Consumer',
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            consumer_group=self._consumer_group,
            topic=self._topic,
            polling_interval_seconds=self.settings.dlq_polling_interval_seconds
        )

        consumer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'group.id': self._consumer_group,
            'auto.offset.reset': 'earliest',  # Processar desde o início
            'enable.auto.commit': False,  # Manual commit para controle de reprocessamento
            'isolation.level': 'read_committed',
            'session.timeout.ms': self.settings.kafka_session_timeout_ms,
            'connections.max.idle.ms': 540000,
            'socket.keepalive.enable': True,
            'heartbeat.interval.ms': 3000,
            'max.poll.interval.ms': 600000,  # 10 minutos para DLQ
        }

        # Configurações de segurança
        if self.settings.kafka_security_protocol != 'PLAINTEXT':
            consumer_config.update({
                'security.protocol': self.settings.kafka_security_protocol,
                'sasl.mechanism': self.settings.kafka_sasl_mechanism,
                'sasl.username': self.settings.kafka_sasl_username,
                'sasl.password': self.settings.kafka_sasl_password,
            })

        self.consumer = Consumer(consumer_config)
        logger.info(
            'Consumer Kafka criado para DLQ de aprovações',
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            consumer_group=self._consumer_group
        )

        # Validar existência do tópico DLQ
        logger.info('Validando existência do tópico DLQ', topic=self._topic)

        try:
            cluster_metadata = self.consumer.list_topics(timeout=10)
            available_topics = set(cluster_metadata.topics.keys())

            if self._topic not in available_topics:
                logger.error(
                    'Tópico DLQ não encontrado',
                    topic=self._topic,
                    available_topics=sorted(list(available_topics))[:20]
                )
                raise RuntimeError(
                    f"Tópico DLQ não encontrado: {self._topic}. "
                    f"Verifique se o tópico foi criado no cluster."
                )

            logger.info('Tópico DLQ validado', topic=self._topic)

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(
                'Falha ao validar tópico DLQ',
                error=str(e),
                error_type=type(e).__name__
            )
            raise RuntimeError(f"Não foi possível validar tópico DLQ: {e}") from e

        # Subscribe ao tópico
        logger.info('Subscribing ao tópico DLQ', topic=self._topic)
        self.consumer.subscribe([self._topic])

        # Aguardar assignments
        logger.info('Aguardando consumer assignments (timeout: 30s)')
        max_wait_seconds = 30
        poll_interval_seconds = 0.5
        start_time = time.time()
        assignments_received = False

        while time.time() - start_time < max_wait_seconds:
            msg = self.consumer.poll(timeout=0.1)

            if msg is not None and not msg.error():
                tp = TopicPartition(msg.topic(), msg.partition(), msg.offset())
                self.consumer.seek(tp)
                logger.debug(
                    'Mensagem recebida durante espera de assignments - seek realizado',
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset()
                )

            assignments = self.consumer.assignment()
            if assignments:
                assignment_info = [
                    f"{tp.topic}:{tp.partition}"
                    for tp in assignments
                ]
                logger.info(
                    'DLQ Consumer assignments recebidos',
                    assignments=assignment_info,
                    total_partitions=len(assignments),
                    elapsed_seconds=round(time.time() - start_time, 2)
                )
                assignments_received = True
                break

            await asyncio.sleep(poll_interval_seconds)

        if not assignments_received:
            logger.error(
                'Timeout aguardando consumer assignments',
                timeout_seconds=max_wait_seconds,
                consumer_group=self._consumer_group,
                topic=self._topic
            )
            raise RuntimeError(
                f"DLQ Consumer não recebeu assignments após {max_wait_seconds}s. "
                f"Verifique se o consumer group '{self._consumer_group}' "
                f"está configurado corretamente."
            )

        logger.info(
            'Approval DLQ Consumer inicializado com sucesso',
            topic=self._topic,
            group_id=self._consumer_group,
            assignments=len(self.consumer.assignment()) if self.consumer else 0,
            polling_interval=self.settings.dlq_polling_interval_seconds
        )

    async def start_consuming(self, reprocessor_callback: Callable):
        """
        Inicia loop de consumo da DLQ com polling periódico.

        Args:
            reprocessor_callback: Função async para reprocessar entrada DLQ.
                                   Assinatura: async def callback(dlq_entry, trace_context) -> bool
        """
        self.running = True
        logger.info(
            'Iniciando DLQ consumer loop',
            polling_interval_seconds=self.settings.dlq_polling_interval_seconds
        )

        await self._consume_dlq_loop(reprocessor_callback)

        logger.info('DLQ consumer loop encerrado')

    async def _consume_dlq_loop(self, reprocessor_callback: Callable):
        """
        Loop assíncrono de consumo da DLQ com polling não-bloqueante.

        Args:
            reprocessor_callback: Função async para reprocessar entrada DLQ
        """
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="kafka-dlq-poller"
        )

        poll_cycle = 0
        logger.info('DLQ consumer loop inicializado, iniciando poll...')

        while self.running:
            try:
                poll_start = time.time()
                poll_cycle += 1
                messages_in_cycle = 0
                reprocessed_in_cycle = 0
                skipped_in_cycle = 0

                logger.debug(
                    'Iniciando ciclo de polling DLQ',
                    poll_cycle=poll_cycle
                )

                # Poll todas as mensagens disponíveis neste ciclo
                while self.running:
                    loop = asyncio.get_running_loop()
                    msg = await loop.run_in_executor(
                        executor,
                        self.consumer.poll,
                        1.0
                    )

                    self.last_poll_time = time.time()

                    if msg is None:
                        # Sem mais mensagens - terminar ciclo
                        break

                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            break
                        else:
                            logger.error('Kafka DLQ consumer error', error=msg.error())
                            continue

                    messages_in_cycle += 1

                    # Deserializar mensagem DLQ
                    try:
                        dlq_entry = self._deserialize_dlq_message(msg)
                    except Exception as e:
                        logger.error(
                            'Erro ao deserializar mensagem DLQ',
                            error=str(e),
                            topic=msg.topic(),
                            partition=msg.partition(),
                            offset=msg.offset()
                        )
                        # Commit para não reprocessar mensagem inválida
                        await loop.run_in_executor(
                            executor,
                            lambda: self.consumer.commit(asynchronous=False)
                        )
                        continue

                    # Calcular backoff progressivo
                    backoff_seconds = self._calculate_backoff(dlq_entry.retry_count)
                    time_since_failure = (datetime.utcnow() - dlq_entry.failed_at).total_seconds()

                    # Verificar se mensagem está pronta para reprocessamento
                    if time_since_failure < backoff_seconds:
                        # Mensagem ainda em backoff - skip
                        skipped_in_cycle += 1
                        self.messages_skipped += 1
                        logger.debug(
                            'Mensagem DLQ em backoff - skipped',
                            plan_id=dlq_entry.plan_id,
                            retry_count=dlq_entry.retry_count,
                            backoff_seconds=backoff_seconds,
                            time_since_failure=round(time_since_failure, 1),
                            remaining_seconds=round(backoff_seconds - time_since_failure, 1)
                        )
                        # Não faz commit - mensagem será reprocessada no próximo poll
                        continue

                    # Extrair trace context
                    trace_context = {
                        'correlation_id': dlq_entry.correlation_id,
                        'trace_id': dlq_entry.trace_id,
                        'span_id': dlq_entry.span_id
                    }

                    # Mensagem pronta - tentar reprocessar
                    logger.info(
                        'Processando entrada DLQ',
                        plan_id=dlq_entry.plan_id,
                        intent_id=dlq_entry.intent_id,
                        retry_count=dlq_entry.retry_count,
                        backoff_seconds=backoff_seconds,
                        time_since_failure=round(time_since_failure, 1),
                        correlation_id=dlq_entry.correlation_id
                    )

                    try:
                        success = await reprocessor_callback(dlq_entry, trace_context)

                        if success:
                            reprocessed_in_cycle += 1
                            self.messages_processed += 1
                            logger.info(
                                'Entrada DLQ reprocessada com sucesso',
                                plan_id=dlq_entry.plan_id,
                                intent_id=dlq_entry.intent_id,
                                retry_count=dlq_entry.retry_count
                            )
                            # Commit offset apenas quando reprocessamento foi bem-sucedido
                            # (inclui: sucesso real, falha permanente tratada, ou republicação na DLQ com retry_count incrementado)
                            await loop.run_in_executor(
                                executor,
                                lambda: self.consumer.commit(asynchronous=False)
                            )
                        else:
                            # Reprocessador retornou False - não commitar para retry no próximo poll
                            # Isso ocorre quando não há DLQ producer configurado para incrementar retry_count
                            logger.warning(
                                'Reprocessamento DLQ retornou falha - mensagem será retentada',
                                plan_id=dlq_entry.plan_id,
                                intent_id=dlq_entry.intent_id,
                                retry_count=dlq_entry.retry_count
                            )
                            # NÃO faz commit - mensagem será reprocessada no próximo ciclo

                    except Exception as e:
                        logger.error(
                            'Erro ao reprocessar entrada DLQ',
                            error=str(e),
                            plan_id=dlq_entry.plan_id,
                            intent_id=dlq_entry.intent_id,
                            retry_count=dlq_entry.retry_count
                        )
                        # Não faz commit - será retentado no próximo poll

                poll_duration = time.time() - poll_start

                # Atualizar estimativa de backlog da DLQ
                # Backlog = mensagens skipped (em backoff) + mensagens que falharam reprocessamento
                self._current_backlog = skipped_in_cycle + (messages_in_cycle - reprocessed_in_cycle - skipped_in_cycle)
                if self._current_backlog < 0:
                    self._current_backlog = 0

                # Atualizar gauge de tamanho da DLQ
                if self.metrics:
                    self.metrics.set_approval_dlq_size(self._current_backlog)

                if messages_in_cycle > 0:
                    logger.info(
                        'Ciclo de polling DLQ concluído',
                        poll_cycle=poll_cycle,
                        messages_found=messages_in_cycle,
                        reprocessed=reprocessed_in_cycle,
                        skipped=skipped_in_cycle,
                        backlog_estimate=self._current_backlog,
                        duration_seconds=round(poll_duration, 2)
                    )
                else:
                    logger.debug(
                        'Ciclo de polling DLQ concluído - sem mensagens',
                        poll_cycle=poll_cycle,
                        backlog_estimate=self._current_backlog,
                        duration_seconds=round(poll_duration, 2)
                    )

                # Aguardar intervalo de polling
                if self.running:
                    await asyncio.sleep(self.settings.dlq_polling_interval_seconds)

            except Exception as e:
                logger.error(
                    'Erro no DLQ consumer loop',
                    error=str(e),
                    poll_cycle=poll_cycle
                )
                await asyncio.sleep(5.0)  # Backoff curto em caso de erro

        executor.shutdown(wait=True)

    def _deserialize_dlq_message(self, msg) -> ApprovalDLQEntry:
        """
        Deserializa mensagem Kafka DLQ para ApprovalDLQEntry.

        DLQ usa formato JSON (não Avro).

        Args:
            msg: Mensagem Kafka

        Returns:
            ApprovalDLQEntry validado

        Raises:
            ValueError: Se campos obrigatórios ausentes
            json.JSONDecodeError: Se JSON inválido
        """
        data = json.loads(msg.value().decode('utf-8'))

        # Validar campos obrigatórios
        required_fields = ['plan_id', 'intent_id', 'original_approval_response', 'retry_count']
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Campo obrigatório ausente na mensagem DLQ: {field}")

        # Converter failed_at de millis para datetime
        if 'failed_at' in data and isinstance(data['failed_at'], (int, float)):
            data['failed_at'] = datetime.utcfromtimestamp(data['failed_at'] / 1000)

        logger.debug(
            'Mensagem DLQ deserializada',
            plan_id=data.get('plan_id'),
            intent_id=data.get('intent_id'),
            retry_count=data.get('retry_count')
        )

        return ApprovalDLQEntry(**data)

    def _calculate_backoff(self, retry_count: int) -> float:
        """
        Calcula backoff progressivo baseado no retry_count.

        Fórmula: backoff_base ^ retry_count * 60 (em segundos)

        Args:
            retry_count: Número de tentativas já realizadas

        Returns:
            Backoff em segundos
        """
        base_minutes = self.settings.dlq_backoff_base_minutes
        backoff_seconds = (base_minutes ** retry_count) * 60

        # Limitar backoff máximo a 24 horas
        max_backoff = 24 * 60 * 60
        return min(backoff_seconds, max_backoff)

    def is_healthy(self, max_poll_age_seconds: float = 600.0) -> tuple[bool, str]:
        """
        Verifica se o consumer DLQ está saudável baseado em atividade recente.

        Args:
            max_poll_age_seconds: Tempo máximo em segundos desde o último poll
                                   (padrão: 2x polling interval)

        Returns:
            Tuple de (is_healthy, reason)
        """
        if not self.running:
            return False, "DLQ Consumer não está em estado running"

        if not self.consumer:
            return False, "DLQ Consumer Kafka não inicializado"

        if self.last_poll_time is None:
            return False, "DLQ Consumer ainda não iniciou polling"

        poll_age = time.time() - self.last_poll_time
        if poll_age > max_poll_age_seconds:
            return False, f"Último poll há {poll_age:.1f}s (máx: {max_poll_age_seconds}s)"

        return True, (
            f"DLQ Consumer ativo (último poll há {poll_age:.1f}s, "
            f"{self.messages_processed} reprocessadas, "
            f"{self.messages_skipped} skipped)"
        )

    async def close(self):
        """Fecha consumer gracefully"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info(
                'Approval DLQ Consumer fechado',
                messages_processed=self.messages_processed,
                messages_skipped=self.messages_skipped
            )
