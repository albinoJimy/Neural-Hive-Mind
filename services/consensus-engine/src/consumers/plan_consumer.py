import asyncio
import json
import os
import re
import time
from typing import Any, Optional

import grpc
import structlog
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext
from src.observability.metrics import ConsensusMetrics
from src.services.consensus_orchestrator import ConsensusOrchestrator

from neural_hive_observability.context import extract_context_from_headers, set_baggage
from neural_hive_observability.tracing import get_current_span_id, get_current_trace_id

logger = structlog.get_logger()


class PlanConsumer:
    """Consumer Kafka para tópico plans.ready usando confluent-kafka"""

    def __init__(
        self, config, specialists_client, mongodb_client, pheromone_client, dlq_producer=None
    ):
        self.config = config
        self.specialists_client = specialists_client
        self.mongodb_client = mongodb_client
        self.orchestrator = ConsensusOrchestrator(config, pheromone_client)
        self.consumer: Optional[Consumer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_deserializer: Optional[AvroDeserializer] = None
        self.running = False
        self.circuit_breaker_open = False
        self.dlq_producer = dlq_producer

        # Tracking de falhas por mensagem (para retry com backoff)
        self._message_failures: dict[str, int] = {}
        self._message_last_failure: dict[str, float] = {}

        # Concorrência bounded de processamento de planos (feature-flag).
        # Default (consensus_max_concurrent_plans=1) => modo SÉRIE inalterado.
        # Estado abaixo só é exercido quando o modo concorrente está ativo (>1).
        self._max_concurrent_plans: int = max(
            1, int(getattr(config, "consensus_max_concurrent_plans", 1))
        )
        self._concurrent_enabled: bool = self._max_concurrent_plans > 1
        # Semaphore que limita o nº de planos em processamento simultâneo.
        self._plan_semaphore: Optional[asyncio.Semaphore] = None
        # Tasks em curso (supervisionadas) no modo concorrente.
        self._inflight_tasks: set[asyncio.Task] = set()
        # Offset tracking por partição para commit de prefixo CONTÍGUO:
        #   _partition_next_commit[(topic, partition)] = próximo offset a commitar
        #     (= maior offset contíguo concluído + 1)
        #   _partition_completed[(topic, partition)] = set de offsets concluídos
        #     ainda à frente de buracos (não contíguos)
        self._partition_next_commit: dict[tuple[str, int], int] = {}
        self._partition_completed: dict[tuple[str, int], set[int]] = {}
        # Partições atualmente atribuídas (modo concorrente). Mantido pelos callbacks
        # de rebalance para impedir commits de partições já revogadas.
        self._assigned_partitions: set[tuple[str, int]] = set()
        # Protege a estrutura de offset tracking contra updates concorrentes.
        self._offset_lock: Optional[asyncio.Lock] = None

    async def initialize(self):
        """Inicializa consumer Kafka com confluent-kafka"""
        consumer_config = {
            "bootstrap.servers": self.config.kafka_bootstrap_servers,
            "group.id": self.config.kafka_consumer_group_id,
            "auto.offset.reset": self.config.kafka_auto_offset_reset,
            "enable.auto.commit": self.config.kafka_enable_auto_commit,
            # Evita expulsão do consumer durante processamento longo (5 especialistas
            # gRPC + consolidação). Default do confluent-kafka (5min) era insuficiente.
            "max.poll.interval.ms": self.config.kafka_max_poll_interval_ms,
        }

        # Configuração de segurança SASL (se não for PLAINTEXT)
        if self.config.kafka_security_protocol != "PLAINTEXT":
            consumer_config["security.protocol"] = self.config.kafka_security_protocol
            if self.config.kafka_sasl_mechanism:
                consumer_config["sasl.mechanism"] = self.config.kafka_sasl_mechanism
            if self.config.kafka_sasl_username:
                consumer_config["sasl.username"] = self.config.kafka_sasl_username
            if self.config.kafka_sasl_password:
                consumer_config["sasl.password"] = self.config.kafka_sasl_password

            logger.info(
                "Configuração de segurança SASL aplicada ao consumer",
                security_protocol=self.config.kafka_security_protocol,
                sasl_mechanism=self.config.kafka_sasl_mechanism,
            )

        self.consumer = Consumer(consumer_config)
        # No modo concorrente, registamos callbacks de rebalance para drenar tasks
        # em curso e limpar o tracking de offset das partições revogadas, evitando
        # commits para partições já não atribuídas e reprocessamento após reassignment.
        # No modo série (default), subscribe simples — comportamento inalterado.
        if self._concurrent_enabled:
            self.consumer.subscribe(
                [self.config.kafka_plans_topic],
                on_assign=self._on_partitions_assigned,
                on_revoke=self._on_partitions_revoked,
            )
        else:
            self.consumer.subscribe([self.config.kafka_plans_topic])

        # Configurar Schema Registry para deserialização Avro
        schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL")
        if schema_registry_url and schema_registry_url.strip():
            schema_path = "/app/schemas/cognitive-plan/cognitive-plan.avsc"

            # Carregar schema com retry
            schema_str = self._load_schema_with_retry(schema_path, max_retries=3)

            if schema_str:
                # Inicializar Schema Registry com retry
                self.avro_deserializer = self._initialize_schema_registry_with_retry(
                    schema_registry_url, schema_str, max_retries=3
                )

                if self.avro_deserializer:
                    logger.info(
                        "Schema Registry configurado para consumer",
                        url=schema_registry_url,
                        schema_path=schema_path,
                    )
                else:
                    logger.warning(
                        "Falha inicializando Schema Registry - usando JSON fallback",
                        url=schema_registry_url,
                    )
            else:
                logger.warning(
                    "Schema Avro não encontrado - usando JSON fallback", path=schema_path
                )
                self.avro_deserializer = None
        else:
            logger.warning("Schema Registry não configurado - usando JSON fallback")
            self.avro_deserializer = None

        logger.info(
            "Plan consumer inicializado",
            topic=self.config.kafka_plans_topic,
            group_id=self.config.kafka_consumer_group_id,
            avro_enabled=self.avro_deserializer is not None,
            schema_registry_url=os.getenv("SCHEMA_REGISTRY_URL", "não configurado"),
            fallback_mode="JSON" if not self.avro_deserializer else "Avro",
            dlq_enabled=self.config.consumer_enable_dlq,
        )

        # Inicializar DLQ producer se fornecido
        if self.dlq_producer:
            await self.dlq_producer.initialize()
            logger.info("DLQ producer inicializado no consumer")

    async def start(self):
        """
        Inicia loop de consumo com confluent-kafka.

        Implementa padrão de resiliência com:
        - Retry automático em caso de erros transientes
        - Exponential backoff para evitar sobrecarga
        - Isolamento de erros por mensagem (não para o consumer por uma falha)
        - Dead Letter Queue (DLQ) para mensagens que excedem limite de retries

        Comportamento de commit de offset:
        - Erros sistêmicos (gRPC, MongoDB, rede): offset NÃO commitado, permite retry
        - Erros de negócio (validação, dados inválidos): offset NÃO commitado por padrão,
          permitindo retry manual ou análise. A mensagem permanece no Kafka.
        - Após exceder max_retries: mensagem enviada para DLQ e offset commitado

        DLQ (Gap P0-1):
        - Configuração: consumer_enable_dlq=true
        - Tópico: kafka_dlq_topic (default: plans.ready.dlq)
        - Max retries: consumer_max_retries_before_dlq (default: 3)
        """
        if not self.consumer:
            raise RuntimeError("Consumer não inicializado")

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

        # Inicializar primitivos de concorrência (só usados se modo concorrente ativo).
        # Criados aqui (dentro do event loop em execução) para ficarem ligados ao loop correto.
        if self._concurrent_enabled and self._plan_semaphore is None:
            self._plan_semaphore = asyncio.Semaphore(self._max_concurrent_plans)
            self._offset_lock = asyncio.Lock()

        logger.info(
            "Plan consumer iniciado",
            concurrency_mode="concurrent" if self._concurrent_enabled else "serial",
            max_concurrent_plans=self._max_concurrent_plans,
        )

        while self.running:
            try:
                # Poll com timeout configurável (non-blocking)
                msg = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.consumer.poll(timeout=poll_timeout)
                )

                if msg is None:
                    # Reset consecutive errors on successful poll (even if empty)
                    consecutive_errors = 0
                    ConsensusMetrics.set_consecutive_errors(0)
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("Reached end of partition")
                        consecutive_errors = 0
                        ConsensusMetrics.set_consecutive_errors(0)
                        continue
                    else:
                        logger.error("Erro no consumer Kafka", error=msg.error())
                        consecutive_errors += 1
                        ConsensusMetrics.set_consecutive_errors(consecutive_errors)
                        ConsensusMetrics.increment_consumer_error("kafka_error", is_systemic=True)

                        if consecutive_errors >= max_consecutive_errors:
                            logger.critical(
                                "Muitos erros consecutivos no consumer - parando",
                                consecutive_errors=consecutive_errors,
                            )
                            self.circuit_breaker_open = True
                            ConsensusMetrics.set_circuit_breaker_state(True)
                            ConsensusMetrics.increment_circuit_breaker_trip()
                            break

                        # Backoff exponencial
                        backoff = min(
                            base_backoff_seconds * (2**consecutive_errors), max_backoff_seconds
                        )
                        ConsensusMetrics.increment_backoff_event("kafka_error")
                        ConsensusMetrics.observe_backoff_duration(backoff, "kafka_error")
                        logger.warning(
                            "Backoff antes de retry",
                            backoff_seconds=backoff,
                            consecutive_errors=consecutive_errors,
                        )
                        await asyncio.sleep(backoff)
                        continue

                # Deserializar mensagem
                cognitive_plan = await self._deserialize_value(msg)

                if cognitive_plan and self._concurrent_enabled:
                    # MODO CONCORRENTE (feature-flag consensus_max_concurrent_plans > 1):
                    # despachar como task supervisionada governada por semaphore.
                    # O commit de offset é feito por prefixo CONTÍGUO por partição
                    # (ver _process_plan_concurrent / _mark_offset_completed), NUNCA
                    # commitando o offset de uma mensagem ainda em curso.
                    # `await acquire` aplica backpressure: o poll só avança quando há
                    # capacidade, evitando acumular tasks ilimitadas em memória.
                    await self._plan_semaphore.acquire()
                    self._register_inflight_offset(msg)
                    task = asyncio.ensure_future(self._process_plan_concurrent(msg, cognitive_plan))
                    self._inflight_tasks.add(task)
                    task.add_done_callback(self._inflight_tasks.discard)
                    # No modo concorrente, erros individuais são tratados dentro da
                    # task; consecutive_errors continua a refletir erros de poll/loop.
                    consecutive_errors = 0
                    ConsensusMetrics.set_consecutive_errors(0)
                elif cognitive_plan:
                    # Processar com isolamento de erro por mensagem e suporte DLQ
                    start_time = time.time()
                    try:
                        await self._process_message_with_retry(msg, cognitive_plan)
                        # Reset consecutive errors após sucesso
                        consecutive_errors = 0
                        ConsensusMetrics.set_consecutive_errors(0)
                        # Métricas de sucesso
                        duration = time.time() - start_time
                        ConsensusMetrics.observe_processing_duration(duration, "success")
                        ConsensusMetrics.increment_message_processed("success")
                    except Exception as process_error:
                        # Métricas de falha
                        duration = time.time() - start_time
                        ConsensusMetrics.observe_processing_duration(duration, "failed")
                        ConsensusMetrics.increment_message_processed(
                            "failed", type(process_error).__name__
                        )

                        # Erro ao processar mensagem específica
                        # NÃO para o consumer - apenas loga e continua
                        logger.error(
                            "Erro processando mensagem - continuando consumer",
                            error=str(process_error),
                            error_type=type(process_error).__name__,
                            topic=msg.topic(),
                            partition=msg.partition(),
                            offset=msg.offset(),
                            plan_id=cognitive_plan.get("plan_id", "unknown"),
                        )

                        # Incrementar apenas se for erro repetido no mesmo tipo
                        # Erros de processamento individual não devem parar o consumer
                        # mas erros sistêmicos (gRPC, MongoDB down) devem ser detectados
                        if self._is_systemic_error(process_error):
                            consecutive_errors += 1
                            ConsensusMetrics.set_consecutive_errors(consecutive_errors)
                            ConsensusMetrics.increment_consumer_error(
                                type(process_error).__name__, is_systemic=True
                            )

                            if consecutive_errors >= max_consecutive_errors:
                                logger.critical(
                                    "Erros sistêmicos detectados - parando consumer",
                                    consecutive_errors=consecutive_errors,
                                    error_type=type(process_error).__name__,
                                )
                                self.circuit_breaker_open = True
                                ConsensusMetrics.set_circuit_breaker_state(True)
                                ConsensusMetrics.increment_circuit_breaker_trip()
                                break

                            # Backoff para erros sistêmicos
                            backoff = min(
                                base_backoff_seconds * (2**consecutive_errors),
                                max_backoff_seconds,
                            )
                            ConsensusMetrics.increment_backoff_event("systemic_error")
                            ConsensusMetrics.observe_backoff_duration(backoff, "systemic_error")
                            logger.warning("Backoff para erro sistêmico", backoff_seconds=backoff)
                            await asyncio.sleep(backoff)
                        else:
                            # Erro de negócio - NÃO commita offset, permite retry/análise
                            ConsensusMetrics.increment_consumer_error(
                                type(process_error).__name__, is_systemic=False
                            )
                            logger.warning(
                                "Erro de negócio - offset NÃO commitado, mensagem permanece no Kafka",
                                offset=msg.offset(),
                                plan_id=cognitive_plan.get("plan_id", "unknown"),
                                error_type=type(process_error).__name__,
                            )
                            # FIX-CP-001/BUG-2: sem este sleep, o offset não-commitado
                            # faz o próximo poll devolver a MESMA mensagem imediatamente,
                            # criando um tight-loop (CPU 100%, lag estagnado) enquanto a
                            # mensagem está em backoff. Dormir o tempo de backoff restante
                            # (ou o base backoff) evita o reprocessamento em busy-loop.
                            backoff_sleep = self._extract_backoff_seconds(process_error)
                            if backoff_sleep is None:
                                backoff_sleep = self.config.consumer_base_backoff_seconds
                            backoff_sleep = min(
                                backoff_sleep, self.config.consumer_max_backoff_seconds
                            )
                            ConsensusMetrics.increment_backoff_event("business_error")
                            ConsensusMetrics.observe_backoff_duration(
                                backoff_sleep, "business_error"
                            )
                            await asyncio.sleep(backoff_sleep)

            except asyncio.CancelledError:
                logger.info("Consumer cancelado via asyncio")
                break
            except Exception as loop_error:
                # Erro inesperado no loop principal
                logger.error(
                    "Erro inesperado no loop de consumo",
                    error=str(loop_error),
                    error_type=type(loop_error).__name__,
                )
                consecutive_errors += 1
                ConsensusMetrics.set_consecutive_errors(consecutive_errors)
                ConsensusMetrics.increment_consumer_error(
                    type(loop_error).__name__, is_systemic=True
                )

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        "Erros críticos no loop - parando consumer",
                        consecutive_errors=consecutive_errors,
                    )
                    self.circuit_breaker_open = True
                    ConsensusMetrics.set_circuit_breaker_state(True)
                    ConsensusMetrics.increment_circuit_breaker_trip()
                    break

                # Backoff
                backoff = min(base_backoff_seconds * (2**consecutive_errors), max_backoff_seconds)
                ConsensusMetrics.increment_backoff_event("loop_error")
                ConsensusMetrics.observe_backoff_duration(backoff, "loop_error")
                await asyncio.sleep(backoff)

        # Drenar tasks em curso (modo concorrente) antes de finalizar para garantir
        # que offsets concluídos sejam commitados e nenhuma consolidação fique a meio.
        if self._concurrent_enabled and self._inflight_tasks:
            logger.info(
                "Aguardando conclusão de planos em curso antes de finalizar",
                inflight=len(self._inflight_tasks),
            )
            await asyncio.gather(*list(self._inflight_tasks), return_exceptions=True)
            await self._commit_contiguous_offsets()

        logger.info(
            "Consumer loop finalizado",
            consecutive_errors=consecutive_errors,
            was_running=self.running,
            circuit_breaker_open=self.circuit_breaker_open,
        )

    def _on_partitions_assigned(self, consumer, partitions) -> None:
        """Callback de atribuição de partições (modo concorrente).

        Executado sincronamente dentro de poll(). Apenas regista as partições
        atualmente atribuídas para que _commit_offset possa rejeitar commits de
        partições não-possuídas. Não inicializa tracking de offset aqui — isso é
        feito por mensagem em _register_inflight_offset com o offset real recebido.
        """
        self._assigned_partitions = {(tp.topic, tp.partition) for tp in partitions}
        logger.info(
            "Partições atribuídas (modo concorrente)",
            partitions=[f"{tp.topic}:{tp.partition}" for tp in partitions],
        )

    def _on_partitions_revoked(self, consumer, partitions) -> None:
        """Callback de revogação de partições (modo concorrente).

        Executado sincronamente dentro de poll(). Limpa o tracking de offset das
        partições revogadas para evitar estado obsoleto e commits para partições
        já não atribuídas após reassignment. Tasks em curso para estas partições,
        ao concluírem, encontrarão a partição fora de `_assigned_partitions` e o
        commit será ignorado (ver _commit_offset), pelo que a mensagem será
        reprocessada pelo novo dono — semântica at-least-once preservada.

        PRÉ-CONDIÇÃO (documentada): ative-se o modo concorrente apenas com o nº de
        réplicas estável; rebalances frequentes durante carga podem causar
        reprocessamento de planos em curso (idempotência por decision_id/dedup por
        message_key mitiga efeitos colaterais).
        """
        revoked = {(tp.topic, tp.partition) for tp in partitions}
        for key in revoked:
            self._partition_next_commit.pop(key, None)
            self._partition_completed.pop(key, None)
            if hasattr(self, "_assigned_partitions"):
                self._assigned_partitions.discard(key)
        logger.warning(
            "Partições revogadas (modo concorrente) - tracking de offset limpo",
            partitions=[f"{tp.topic}:{tp.partition}" for tp in partitions],
            inflight=len(self._inflight_tasks),
        )

    def _register_inflight_offset(self, msg) -> None:
        """Regista o offset de uma mensagem despachada para processamento concorrente.

        Inicializa o ponteiro de commit da partição (na primeira mensagem vista)
        com o offset atual, de modo a que apenas offsets >= a este ponteiro sejam
        considerados para commit contíguo. Não commita nada — apenas tracking.
        """
        key = (msg.topic(), msg.partition())
        if key not in self._partition_next_commit:
            self._partition_next_commit[key] = msg.offset()
            self._partition_completed.setdefault(key, set())

    async def _process_plan_concurrent(self, msg, cognitive_plan) -> None:
        """Processa um plano no modo concorrente, com a mesma semântica de retry/DLQ.

        Diferenças face ao caminho série:
        - O commit por-mensagem de _process_message é SUPRIMIDO; o offset só é
          commitado via prefixo contíguo por partição quando esta e todas as
          mensagens anteriores da partição concluírem com sucesso.
        - Em caso de falha, o offset NÃO é marcado concluído (mantém-se o gap),
          pelo que o commit contíguo nunca ultrapassa uma mensagem ainda não OK.
        """
        start_time = time.time()
        try:
            await self._process_message_with_retry(msg, cognitive_plan)
            duration = time.time() - start_time
            ConsensusMetrics.observe_processing_duration(duration, "success")
            ConsensusMetrics.increment_message_processed("success")
            # Marcar offset como concluído e tentar avançar o prefixo contíguo.
            await self._mark_offset_completed(msg)
        except Exception as process_error:
            duration = time.time() - start_time
            ConsensusMetrics.observe_processing_duration(duration, "failed")
            ConsensusMetrics.increment_message_processed("failed", type(process_error).__name__)
            # NÃO marcar offset concluído: o prefixo contíguo fica retido neste
            # offset, garantindo que a mensagem falhada (e as posteriores) não têm
            # o offset commitado → permite retry/análise, idêntico ao modo série.
            logger.error(
                "Erro processando plano (modo concorrente) - offset retido",
                error=str(process_error),
                error_type=type(process_error).__name__,
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                plan_id=cognitive_plan.get("plan_id", "unknown"),
            )
        finally:
            if self._plan_semaphore is not None:
                self._plan_semaphore.release()

    async def _mark_offset_completed(self, msg) -> None:
        """Marca um offset como concluído e commita o maior prefixo contíguo da partição.

        Mantém, por partição, `_partition_next_commit` (próximo offset esperado) e
        um conjunto de offsets concluídos à frente. Quando o próximo offset esperado
        está concluído, avança o ponteiro consumindo offsets contíguos e commita
        UMA vez o offset mais alto contíguo (confluent-kafka commita offset+1).
        """
        key = (msg.topic(), msg.partition())
        async with self._offset_lock:
            completed = self._partition_completed.setdefault(key, set())
            completed.add(msg.offset())
            # Garantir ponteiro inicializado (defensivo).
            if key not in self._partition_next_commit:
                self._partition_next_commit[key] = msg.offset()

            next_offset = self._partition_next_commit[key]
            highest_contiguous: Optional[int] = None
            while next_offset in completed:
                completed.discard(next_offset)
                highest_contiguous = next_offset
                next_offset += 1
            self._partition_next_commit[key] = next_offset

            if highest_contiguous is not None:
                await self._commit_offset(msg.topic(), msg.partition(), highest_contiguous)

    async def _commit_offset(self, topic: str, partition: int, offset: int) -> None:
        """Commita explicitamente offset+1 para (topic, partition) via TopicPartition."""
        if self.config.kafka_enable_auto_commit:
            return
        # Não commitar partições já revogadas: o novo dono é responsável por elas;
        # commitar aqui poderia sobrepor o progresso do novo consumer. A mensagem
        # será reprocessada pelo novo dono (at-least-once + idempotência por
        # decision_id), o que é seguro.
        if self._concurrent_enabled and (topic, partition) not in self._assigned_partitions:
            logger.warning(
                "Commit ignorado - partição já revogada (modo concorrente)",
                topic=topic,
                partition=partition,
                offset=offset,
            )
            return
        try:
            from confluent_kafka import TopicPartition

            tp = TopicPartition(topic, partition, offset + 1)
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.consumer.commit(offsets=[tp])
            )
            ConsensusMetrics.increment_offset_commit("success")
            logger.debug(
                "Offset contíguo commitado",
                topic=topic,
                partition=partition,
                committed_offset=offset,
            )
        except Exception as commit_err:
            ConsensusMetrics.increment_offset_commit("failed")
            logger.error(
                "Falha ao commitar offset contíguo",
                topic=topic,
                partition=partition,
                offset=offset,
                error=str(commit_err),
            )

    async def _commit_contiguous_offsets(self) -> None:
        """Commita o prefixo contíguo atual de todas as partições (usado no drain)."""
        for (topic, partition), next_offset in list(self._partition_next_commit.items()):
            completed = self._partition_completed.get((topic, partition), set())
            highest_contiguous: Optional[int] = None
            cursor = next_offset
            while cursor in completed:
                completed.discard(cursor)
                highest_contiguous = cursor
                cursor += 1
            self._partition_next_commit[(topic, partition)] = cursor
            if highest_contiguous is not None:
                await self._commit_offset(topic, partition, highest_contiguous)

    def _extract_backoff_seconds(self, error: Exception) -> Optional[float]:
        """Extrai o tempo de backoff restante (s) da exceção "Backoff em andamento".

        Devolve None se a exceção não for de backoff. Usado para dormir o tempo
        certo e evitar o tight-loop de reprocessamento (FIX-CP-001/BUG-2).
        """
        msg = str(error)
        if "Backoff em andamento" not in msg:
            return None
        match = re.search(r"([0-9]+\.?[0-9]*)s", msg)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def _is_systemic_error(self, error: Exception) -> bool:
        """
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
        """
        systemic_error_types = (
            ConnectionError,
            TimeoutError,
            OSError,
            grpc.RpcError,  # Falhas gRPC nos specialists
        )

        systemic_error_keywords = [
            "connection",
            "timeout",
            "unavailable",
            "refused",
            "network",
            "socket",
            "dns",
            "grpc",
            "mongodb",
            "kafka",
            "unreachable",
            "connect",
            "deadline exceeded",
        ]

        # Check by exception type
        if isinstance(error, systemic_error_types):
            return True

        # Check by error message
        error_msg = str(error).lower()
        return any(keyword in error_msg for keyword in systemic_error_keywords)

    def _load_schema_with_retry(self, schema_path: str, max_retries: int = 3) -> Optional[str]:
        """
        Carrega schema Avro com retry para falhas transientes.

        Retries são aplicados para:
        - FileNotFoundError (schema não copiado ainda)
        - IOError (filesystem temporariamente indisponível)

        Não faz retry para:
        - Schema inválido (JSON parse error)
        - Permissões negadas
        """
        backoff_seconds = 1.0

        for attempt in range(max_retries):
            try:
                with open(schema_path) as f:
                    schema_str = f.read()
                logger.info(
                    "Schema Avro carregado com sucesso", path=schema_path, attempt=attempt + 1
                )
                return schema_str
            except FileNotFoundError:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Schema não encontrado - retry",
                        path=schema_path,
                        attempt=attempt + 1,
                        backoff_seconds=backoff_seconds,
                    )
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2
                else:
                    logger.error(
                        "Schema não encontrado após retries",
                        path=schema_path,
                        max_retries=max_retries,
                    )
                    return None
            except Exception as e:
                logger.error(
                    "Erro carregando schema",
                    path=schema_path,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return None

        return None

    def _initialize_schema_registry_with_retry(
        self, schema_registry_url: str, schema_str: str, max_retries: int = 3
    ) -> Optional[AvroDeserializer]:
        """
        Inicializa Schema Registry client com retry para falhas transientes.

        Retries são aplicados para:
        - ConnectionError (registry indisponível)
        - TimeoutError (registry lento)
        - HTTP 503 (registry em manutenção)

        Não faz retry para:
        - HTTP 401/403 (autenticação/autorização)
        - Schema inválido
        """
        backoff_seconds = 1.0

        for attempt in range(max_retries):
            start_time = time.time()
            try:
                schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})
                avro_deserializer = AvroDeserializer(schema_registry_client, schema_str)

                # Métricas de sucesso na inicialização
                duration = time.time() - start_time
                ConsensusMetrics.increment_schema_registry_request("initialize", "success")
                ConsensusMetrics.observe_schema_registry_latency(duration, "initialize")

                logger.info(
                    "Schema Registry inicializado com sucesso",
                    url=schema_registry_url,
                    attempt=attempt + 1,
                )
                return avro_deserializer
            except (ConnectionError, TimeoutError) as e:
                # Métricas de falha transiente
                duration = time.time() - start_time
                ConsensusMetrics.increment_schema_registry_request(
                    "initialize", "transient_failure"
                )
                ConsensusMetrics.observe_schema_registry_latency(duration, "initialize")

                if attempt < max_retries - 1:
                    logger.warning(
                        "Falha conectando Schema Registry - retry",
                        url=schema_registry_url,
                        attempt=attempt + 1,
                        backoff_seconds=backoff_seconds,
                        error=str(e),
                    )
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2
                else:
                    # Métricas de falha final após todos os retries
                    ConsensusMetrics.increment_schema_registry_request("initialize", "failed")
                    logger.error(
                        "Schema Registry indisponível após retries",
                        url=schema_registry_url,
                        max_retries=max_retries,
                        error=str(e),
                    )
                    return None
            except Exception as e:
                # Métricas de erro não-transiente (sem retry)
                duration = time.time() - start_time
                ConsensusMetrics.increment_schema_registry_request("initialize", "error")
                ConsensusMetrics.observe_schema_registry_latency(duration, "initialize")

                logger.error(
                    "Erro inicializando Schema Registry",
                    url=schema_registry_url,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return None

        return None

    def _is_transient_deserialization_error(self, error: Exception) -> bool:
        """
        Verifica se um erro de deserialização é transiente (timeout/conexão).

        Erros transientes são candidatos a retry:
        - TimeoutError
        - ConnectionError
        - Erros com keywords: timeout, connection, unavailable

        Erros não-transientes (sem retry):
        - Invalid magic byte (mensagem não é Avro)
        - Schema not found (schema não registrado)
        - Erros de parsing/validação
        """
        error_msg = str(error).lower()

        # Erros de formato/schema não são transientes
        if "magic byte" in error_msg or "invalid magic" in error_msg:
            return False
        if "schema" in error_msg and ("not found" in error_msg or "unknown" in error_msg):
            return False

        # Verificar por tipo de exceção
        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return True

        # Verificar por keywords no erro
        transient_keywords = ["timeout", "connection", "unavailable", "refused", "reset", "network"]
        return any(keyword in error_msg for keyword in transient_keywords)

    async def _deserialize_value(self, msg):
        """
        Deserializa o valor da mensagem (Avro ou JSON).

        Implementa retry com exponential backoff para falhas transientes
        do Schema Registry (timeout/conexão). Erros não-transientes
        (invalid magic byte, schema not found) não são retentados.
        """
        max_retries = 3
        backoff_seconds = 1.0

        if not self.avro_deserializer:
            # Fallback JSON - sem retry necessário (não usa Schema Registry)
            return self._deserialize_json(msg)

        # Deserialização Avro com retry para erros transientes
        for attempt in range(max_retries):
            start_time = time.time()
            try:
                ctx = SerializationContext(msg.topic(), MessageField.VALUE)
                value = self.avro_deserializer(msg.value(), ctx)

                # Métricas de sucesso
                duration = time.time() - start_time
                ConsensusMetrics.increment_deserialization("avro", "success")
                ConsensusMetrics.observe_deserialization_duration(duration, "avro")
                ConsensusMetrics.increment_schema_registry_request("deserialize", "success")
                ConsensusMetrics.observe_schema_registry_latency(duration, "deserialize")

                return value

            except Exception as e:
                duration = time.time() - start_time
                str(e).lower()

                # Verificar se é erro transiente (candidato a retry)
                is_transient = self._is_transient_deserialization_error(e)

                if is_transient and attempt < max_retries - 1:
                    # Erro transiente - fazer retry com backoff
                    ConsensusMetrics.increment_schema_registry_request(
                        "deserialize", "transient_failure"
                    )
                    ConsensusMetrics.observe_schema_registry_latency(duration, "deserialize")

                    logger.warning(
                        "Erro transiente na deserialização - retry",
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset(),
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        backoff_seconds=backoff_seconds,
                        error=str(e),
                    )
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds *= 2
                    continue

                # Erro final (não-transiente ou esgotou retries)
                ConsensusMetrics.observe_deserialization_duration(duration, "avro")

                if is_transient:
                    # Erro transiente mas esgotou retries - não tentar fallback
                    ConsensusMetrics.increment_deserialization("avro", "registry_timeout")
                    ConsensusMetrics.increment_schema_registry_request("deserialize", "failed")
                    ConsensusMetrics.observe_schema_registry_latency(duration, "deserialize")
                    logger.error(
                        "Erro de deserialização: falha conectando Schema Registry após retries",
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset(),
                        error=str(e),
                        attempts=attempt + 1,
                        causa_provavel="Schema Registry indisponível ou timeout de rede",
                        solucao="Verificar conectividade com Schema Registry e aumentar timeout",
                        schema_registry_url=os.getenv("SCHEMA_REGISTRY_URL", "não configurado"),
                    )
                    return None

                # Para erros não-transientes, tentar JSON fallback como última tentativa
                logger.warning(
                    "Erro de deserialização Avro não-transiente - tentando JSON fallback",
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                    error=str(e),
                    error_type=type(e).__name__,
                )

                # Tentar JSON fallback com normalização
                fallback_value = self._deserialize_json_with_normalization(msg)
                if fallback_value:
                    ConsensusMetrics.increment_deserialization("json", "fallback_success")
                    logger.info(
                        "JSON fallback bem-sucedido para mensagem",
                        topic=msg.topic(),
                        offset=msg.offset(),
                    )
                    return fallback_value
                else:
                    ConsensusMetrics.increment_deserialization("avro", "fallback_failed")
                    logger.error(
                        "JSON fallback falhou - mensagem será pulada (offset não commitado)",
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset(),
                        error=str(e),
                    )
                    return None

        return None

    def _deserialize_json(self, msg):
        """Deserializa mensagem usando JSON fallback"""
        start_time = time.time()
        try:
            value = json.loads(msg.value().decode("utf-8"))

            duration = time.time() - start_time
            ConsensusMetrics.increment_deserialization("json", "success")
            ConsensusMetrics.observe_deserialization_duration(duration, "json")

            logger.debug(
                "Mensagem deserializada via JSON fallback", topic=msg.topic(), offset=msg.offset()
            )

            return value
        except Exception as e:
            duration = time.time() - start_time
            ConsensusMetrics.increment_deserialization("json", "error")
            ConsensusMetrics.observe_deserialization_duration(duration, "json")

            logger.error(
                "Erro deserializando mensagem JSON",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def _deserialize_json_with_normalization(self, msg):
        """
        Deserializa mensagem usando JSON e normaliza campos para compatibilidade.

        Este método é usado como fallback quando a deserialização Avro falha
        devido a incompatibilidades de schema (ex: enum em minúsculas vs maiúsculas).

        Normalizações aplicadas:
        - original_domain: converte para uppercase se for string
        """
        start_time = time.time()
        try:
            value = json.loads(msg.value().decode("utf-8"))

            # Normalizar campos para compatibilidade backward
            if isinstance(value, dict):
                # Normalizar original_domain para uppercase
                if "original_domain" in value and isinstance(value["original_domain"], str):
                    old_domain = value["original_domain"]
                    value["original_domain"] = old_domain.upper()
                    logger.info(
                        "original_domain normalizado de minúsculas para maiúsculas",
                        old_domain=old_domain,
                        new_domain=value["original_domain"],
                        offset=msg.offset(),
                    )

                # Normalizar risk_band para lowercase (caso esteja em maiúsculas)
                if "risk_band" in value and isinstance(value["risk_band"], str):
                    old_band = value["risk_band"]
                    value["risk_band"] = old_band.lower()
                    if old_band != value["risk_band"]:
                        logger.info(
                            "risk_band normalizado de maiúsculas para minúsculas",
                            old_band=old_band,
                            new_band=value["risk_band"],
                            offset=msg.offset(),
                        )

            duration = time.time() - start_time
            ConsensusMetrics.increment_deserialization("json", "success_normalized")
            ConsensusMetrics.observe_deserialization_duration(duration, "json")

            logger.debug(
                "Mensagem deserializada via JSON com normalização",
                topic=msg.topic(),
                offset=msg.offset(),
            )

            return value
        except Exception as e:
            duration = time.time() - start_time
            ConsensusMetrics.increment_deserialization("json", "error")
            ConsensusMetrics.observe_deserialization_duration(duration, "json")

            logger.error(
                "Erro deserializando mensagem JSON com normalização",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def stop(self):
        """Para consumer gracefully"""
        self.running = False
        # Drenar planos em curso (modo concorrente) e commitar offsets contíguos
        # antes de fechar o consumer, evitando reprocessamento desnecessário.
        if self._concurrent_enabled and self._inflight_tasks:
            await asyncio.gather(*list(self._inflight_tasks), return_exceptions=True)
            await self._commit_contiguous_offsets()
        if self.consumer:
            await asyncio.get_event_loop().run_in_executor(None, self.consumer.close)
        if self.dlq_producer:
            await self.dlq_producer.stop()
        logger.info("Plan consumer parado")

    async def _process_message(self, msg, cognitive_plan):
        """Processa mensagem do Kafka"""
        try:
            # Extract W3C trace context from Kafka headers (traceparent)
            headers_dict = {
                k: v.decode("utf-8") if isinstance(v, bytes) else v
                for k, v in (msg.headers() or [])
            }
            extract_context_from_headers(headers_dict)

            # Extrair trace_id/span_id do contexto OTEL atual (já anexado pelo
            # extract_context_from_headers acima) para propagar até à decisão de
            # consenso. Envolvido em try/except para nunca ser fatal (P3-trace).
            trace_id_extracted: str | None = None
            span_id_extracted: str | None = None
            try:
                trace_id_extracted = get_current_trace_id()
                span_id_extracted = get_current_span_id()
            except Exception as exc:  # tracing nunca deve bloquear consumo
                logger.exception(
                    "Falha ao extrair trace context do contexto OTEL",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

            # Set baggage for correlation
            plan_id = cognitive_plan.get("plan_id")
            if plan_id:
                set_baggage("neural.hive.plan.id", plan_id)

            logger.info(
                "Mensagem recebida",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                plan_id=plan_id,
                trace_id_extracted=trace_id_extracted,
                span_id_extracted=span_id_extracted,
            )

            # 1. Invocar especialistas via gRPC
            specialist_opinions = await self._invoke_specialists(cognitive_plan)

            # 2. Processar consenso (propagar trace context extraído dos headers Kafka)
            logger.info(
                "Propagando trace context para o orchestrator de consenso",
                plan_id=plan_id,
                trace_id_passed_to_orchestrator=trace_id_extracted,
                span_id_passed_to_orchestrator=span_id_extracted,
            )
            decision = await self.orchestrator.process_consensus(
                cognitive_plan,
                specialist_opinions,
                trace_id=trace_id_extracted,
                span_id=span_id_extracted,
            )

            # 3. Persistir no ledger (MongoDB)
            await self.mongodb_client.save_consensus_decision(decision)

            logger.info(
                "Decisao salva no ledger",
                decision_id=decision.decision_id,
                plan_id=cognitive_plan["plan_id"],
                final_decision=decision.final_decision.value,
            )

            # 4. Publicar decisão no Kafka (será feito pelo producer)
            # Armazenar na fila de produção
            from src.main import state

            if state.decision_queue is not None:
                await state.decision_queue.put(decision)
                logger.info(
                    "Decisao adicionada a fila de publicacao",
                    decision_id=decision.decision_id,
                    plan_id=cognitive_plan["plan_id"],
                )
            else:
                logger.error(
                    "decision_queue nao inicializada - decisao nao sera publicada",
                    decision_id=decision.decision_id,
                    plan_id=cognitive_plan["plan_id"],
                )

            # 5. Commit manual do offset
            # No modo concorrente o commit é diferido para o prefixo CONTÍGUO por
            # partição (_mark_offset_completed), pelo que NÃO se commita por-msg aqui:
            # commitar o offset desta mensagem poderia ultrapassar mensagens anteriores
            # da mesma partição ainda em curso → gap/perda em rebalance.
            if not self.config.kafka_enable_auto_commit and not self._concurrent_enabled:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.consumer.commit(msg)
                    )
                    ConsensusMetrics.increment_offset_commit("success")
                except Exception as commit_err:
                    ConsensusMetrics.increment_offset_commit("failed")
                    raise commit_err

            logger.info(
                "Mensagem processada com sucesso",
                plan_id=cognitive_plan["plan_id"],
                decision_id=decision.decision_id,
                final_decision=decision.final_decision.value,
            )

            # Limpar tracking de falhas em caso de sucesso
            message_key = f"{msg.topic()}:{msg.partition()}:{msg.offset()}"
            self._message_failures.pop(message_key, None)
            self._message_last_failure.pop(message_key, None)

        except Exception as e:
            logger.error(
                "Erro processando mensagem",
                error=str(e),
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
            )
            # Não commitar offset em caso de erro (permitir retry)
            raise

    async def _process_message_with_retry(
        self, msg, cognitive_plan, max_retries: Optional[int] = None
    ):
        """
        Processa mensagem com retry e backoff exponencial.

        Após exceder o limite de retries, envia para DLQ se disponível.

        Args:
            msg: Mensagem Kafka
            cognitive_plan: Plano cognitivo deserializado
            max_retries: Máximo de retries (usa config se não especificado)
        """
        if max_retries is None:
            max_retries = self.config.consumer_max_retries_before_dlq

        message_key = f"{msg.topic()}:{msg.partition()}:{msg.offset()}"
        current_failure_count = self._message_failures.get(message_key, 0)
        last_failure_time = self._message_last_failure.get(message_key, 0)

        # Verificar se deve fazer retry (backoff)
        if current_failure_count > 0:
            time_since_last_failure = time.time() - last_failure_time

            # Calcular backoff exponencial
            if self.dlq_producer:
                backoff = self.dlq_producer.calculate_backoff(current_failure_count)
            else:
                backoff = min(
                    self.config.consumer_base_backoff_seconds * (2**current_failure_count),
                    self.config.consumer_max_backoff_seconds,
                )

            if time_since_last_failure < backoff:
                # Ainda em período de backoff - não processar ainda
                logger.debug(
                    "Mensagem em backoff - aguardando",
                    message_key=message_key,
                    backoff_remaining=backoff - time_since_last_failure,
                )
                raise Exception(
                    f"Backoff em andamento: {backoff - time_since_last_failure:.1f}s restantes"
                )

        # Tentar processar mensagem
        try:
            await self._process_message(msg, cognitive_plan)
        except Exception as process_error:
            # Incrementar contador de falhas
            current_failure_count += 1
            self._message_failures[message_key] = current_failure_count
            self._message_last_failure[message_key] = time.time()

            is_systemic = self._is_systemic_error(process_error)

            # Verificar se deve enviar para DLQ
            should_dlq = False
            if self.dlq_producer:
                should_dlq = self.dlq_producer.should_send_to_dlq(
                    current_failure_count, is_systemic
                )

            if should_dlq:
                # Enviar para DLQ
                logger.warning(
                    "Mensagem enviada para DLQ após exceder retries",
                    message_key=message_key,
                    failure_count=current_failure_count,
                    error=str(process_error),
                )

                tracing_context = {
                    k: v.decode("utf-8") if isinstance(v, bytes) else v
                    for k, v in (msg.headers() or [])
                }

                dlq_sent = await self.dlq_producer.send_to_dlq(
                    message=msg,
                    exception=process_error,
                    failure_count=current_failure_count,
                    tracing_context=tracing_context,
                )

                if dlq_sent:
                    # Limpar tracking e commitar offset (mensagem foi para DLQ)
                    self._message_failures.pop(message_key, None)
                    self._message_last_failure.pop(message_key, None)

                    # Commitar offset para remover mensagem do tópico principal.
                    # No modo concorrente, a mensagem foi resolvida (DLQ) e não retorna:
                    # marca-se o offset como concluído para o prefixo contíguo avançar,
                    # em vez de commitar diretamente este offset (que poderia ultrapassar
                    # mensagens anteriores da partição ainda em curso).
                    if not self.config.kafka_enable_auto_commit:
                        if self._concurrent_enabled:
                            await self._mark_offset_completed(msg)
                        else:
                            await asyncio.get_event_loop().run_in_executor(
                                None, lambda: self.consumer.commit(msg)
                            )
                            ConsensusMetrics.increment_offset_commit("success")
                else:
                    # DLQ falhou - manter tracking para retry
                    logger.error(
                        "Falha ao enviar para DLQ - mantendo mensagem para retry",
                        message_key=message_key,
                    )
            else:
                # Ainda em limite de retries - log e lançar exceção para retry
                logger.warning(
                    "Mensagem falhou mas ainda dentro do limite de retries",
                    message_key=message_key,
                    failure_count=current_failure_count,
                    max_retries=max_retries if not is_systemic else max_retries,
                    is_systemic=is_systemic,
                )

            # Sempre lançar exceção para não commitar offset
            raise process_error

    async def _invoke_specialists(self, cognitive_plan: dict[str, Any]):
        """Invoca todos os especialistas em paralelo via gRPC"""
        logger.info("Invocando especialistas", plan_id=cognitive_plan["plan_id"])

        # Extrair trace context das mensagens Kafka ou criar novo
        trace_context = {
            "trace_id": cognitive_plan.get("trace_id", ""),
            "span_id": cognitive_plan.get("span_id", ""),
        }

        # Invocar todos em paralelo se habilitado
        if self.config.enable_parallel_invocation:
            opinions = await self.specialists_client.evaluate_plan_parallel(
                cognitive_plan, trace_context
            )
        else:
            # Sequencial (fallback)
            opinions = []
            for specialist_type in [
                "business",
                "technical",
                "behavior",
                "evolution",
                "architecture",
            ]:
                try:
                    opinion = await self.specialists_client.evaluate_plan(
                        specialist_type, cognitive_plan, trace_context
                    )
                    opinions.append(opinion)
                except Exception as e:
                    logger.error(
                        "Erro invocando especialista", specialist_type=specialist_type, error=str(e)
                    )

        logger.info(
            "Especialistas invocados", plan_id=cognitive_plan["plan_id"], num_opinions=len(opinions)
        )

        return opinions
