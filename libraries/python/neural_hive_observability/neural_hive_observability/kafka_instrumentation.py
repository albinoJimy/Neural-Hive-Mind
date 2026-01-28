"""
Instrumentação Kafka para Neural Hive Observability.

Fornece wrappers para producers/consumers com injeção e extração de contexto,
garantindo correlação distribuída via headers e spans OpenTelemetry.
"""

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from opentelemetry import trace
from opentelemetry.context import attach
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import Status, StatusCode

from .config import ObservabilityConfig
from .context import ContextManager
from .tracing import get_correlation_context, get_tracer

logger = logging.getLogger(__name__)


class InstrumentedKafkaProducer:
    """Wrapper para confluent-kafka Producer com tracing e injeção de contexto."""

    def __init__(self, producer: Any, config: ObservabilityConfig):
        if config is None:
            logger.error(
                "Tentativa de criar InstrumentedKafkaProducer com config=None. "
                "Verifique se init_observability() foi chamado antes de instrumentar o producer."
            )
            raise ValueError(
                "config não pode ser None para InstrumentedKafkaProducer. "
                "Use instrument_kafka_producer() que valida o config."
            )

        if not isinstance(config, ObservabilityConfig):
            logger.error(
                f"Tentativa de criar InstrumentedKafkaProducer com config de tipo inválido: {type(config).__name__}. "
                "Use init_observability() para criar a configuração corretamente."
            )
            raise TypeError(
                f"config deve ser uma instância de ObservabilityConfig, recebido {type(config).__name__}. "
                "Use init_observability() para criar a configuração corretamente."
            )

        service_name = getattr(config, 'service_name', None)
        if not service_name:
            logger.error(
                f"Tentativa de criar InstrumentedKafkaProducer com service_name inválido: "
                f"config.service_name={service_name}. "
                "Verifique se init_observability() foi chamado com service_name válido."
            )
            raise ValueError(
                "config.service_name não pode ser None ou vazio para InstrumentedKafkaProducer."
            )

        self._producer = producer
        self._config = config
        self._context_manager = ContextManager(config)
        self._tracer = get_tracer() or trace.get_tracer(__name__)

    def produce(
        self,
        topic: str,
        value: Optional[bytes] = None,
        key: Optional[bytes] = None,
        headers: Optional[Any] = None,
        partition: Optional[int] = None,
        on_delivery=None,
        *args,
        **kwargs
    ):
        header_map = self._normalize_headers(headers)

        with self._tracer.start_as_current_span(f"kafka.produce.{topic}") as span:
            correlation = get_correlation_context()
            inject(header_map)
            header_map = self._context_manager.inject_kafka_headers(header_map)

            if correlation.get("intent_id"):
                header_map["x-neural-hive-intent-id"] = correlation["intent_id"]
                span.set_attribute("neural.hive.intent.id", correlation["intent_id"])

            if correlation.get("plan_id"):
                header_map["x-neural-hive-plan-id"] = correlation["plan_id"]
                span.set_attribute("neural.hive.plan.id", correlation["plan_id"])

            if correlation.get("user_id"):
                header_map["x-neural-hive-user-id"] = correlation["user_id"]

            if correlation.get("trace_id"):
                header_map["x-neural-hive-trace-id"] = correlation["trace_id"]

            if correlation.get("span_id"):
                header_map["x-neural-hive-span-id"] = correlation["span_id"]

            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination", topic)
            if partition is not None:
                span.set_attribute("messaging.kafka.partition", partition)

            if value:
                span.set_attribute("messaging.message_payload_size_bytes", len(value))

            if self._config:
                if self._config.neural_hive_component:
                    span.set_attribute("neural.hive.component", self._config.neural_hive_component)
                if self._config.neural_hive_layer:
                    span.set_attribute("neural.hive.layer", self._config.neural_hive_layer)

            try:
                # Build produce kwargs, only include partition if explicitly set
                produce_kwargs = {
                    'topic': topic,
                    'value': value,
                    'key': key,
                    'headers': self._headers_dict_to_sequence(header_map),
                    'on_delivery': on_delivery,
                }
                # Only add partition if it's a valid integer (not None)
                if partition is not None:
                    produce_kwargs['partition'] = partition
                
                # Merge any additional kwargs
                produce_kwargs.update(kwargs)
                self._producer.produce(*args, **produce_kwargs)
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    def flush(self, *args, **kwargs):
        return self._producer.flush(*args, **kwargs)

    def poll(self, *args, **kwargs):
        return self._producer.poll(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._producer, item)

    def _normalize_headers(self, headers: Optional[Any]) -> Dict[str, Any]:
        if headers is None:
            return {}

        if isinstance(headers, dict):
            return {k: v for k, v in headers.items()}

        if isinstance(headers, list):
            return {k: v for k, v in headers}

        return {}

    def _headers_dict_to_sequence(self, headers: Dict[str, Any]) -> List[Tuple[str, Any]]:
        sequence = []
        for key, value in headers.items():
            if isinstance(value, bytes):
                sequence.append((key, value))
            else:
                sequence.append((key, str(value)))
        return sequence


class InstrumentedAIOKafkaProducer:
    """Wrapper assíncrono para aiokafka AIOKafkaProducer com tracing."""

    def __init__(self, producer: Any, config: ObservabilityConfig):
        if config is None:
            logger.error(
                "Tentativa de criar InstrumentedAIOKafkaProducer com config=None. "
                "Verifique se init_observability() foi chamado antes de instrumentar o producer assíncrono."
            )
            raise ValueError(
                "config não pode ser None para InstrumentedAIOKafkaProducer. "
                "Use instrument_kafka_producer() que valida o config."
            )

        if not isinstance(config, ObservabilityConfig):
            logger.error(
                f"Tentativa de criar InstrumentedAIOKafkaProducer com config de tipo inválido: {type(config).__name__}. "
                "Use init_observability() para criar a configuração corretamente."
            )
            raise TypeError(
                f"config deve ser uma instância de ObservabilityConfig, recebido {type(config).__name__}. "
                "Use init_observability() para criar a configuração corretamente."
            )

        service_name = getattr(config, 'service_name', None)
        if not service_name:
            logger.error(
                f"Tentativa de criar InstrumentedAIOKafkaProducer com service_name inválido: "
                f"config.service_name={service_name}. "
                "Verifique se init_observability() foi chamado com service_name válido."
            )
            raise ValueError(
                "config.service_name não pode ser None ou vazio para InstrumentedAIOKafkaProducer."
            )

        self._producer = producer
        self._config = config
        self._context_manager = ContextManager(config)
        self._tracer = get_tracer() or trace.get_tracer(__name__)

    async def send(self, topic: str, value: Any = None, key: Any = None, headers: Optional[Any] = None, partition: Optional[int] = None, **kwargs):
        header_map = self._normalize_headers(headers)
        with self._tracer.start_as_current_span(f"kafka.produce.{topic}") as span:
            correlation = get_correlation_context()
            inject(header_map)
            header_map = self._context_manager.inject_kafka_headers(header_map)

            if correlation.get("intent_id"):
                header_map["x-neural-hive-intent-id"] = correlation["intent_id"]
                span.set_attribute("neural.hive.intent.id", correlation["intent_id"])

            if correlation.get("plan_id"):
                header_map["x-neural-hive-plan-id"] = correlation["plan_id"]
                span.set_attribute("neural.hive.plan.id", correlation["plan_id"])

            if correlation.get("trace_id"):
                header_map["x-neural-hive-trace-id"] = correlation["trace_id"]

            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination", topic)
            if partition is not None:
                span.set_attribute("messaging.kafka.partition", partition)

            try:
                result = await self._producer.send(
                    topic,
                    value=value,
                    key=key,
                    headers=self._headers_dict_to_sequence(header_map),
                    partition=partition,
                    **kwargs
                )
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    async def send_and_wait(self, topic: str, value: Any = None, key: Any = None, headers: Optional[Any] = None, partition: Optional[int] = None, **kwargs):
        return await self.send(topic, value=value, key=key, headers=headers, partition=partition, **kwargs)

    async def start(self):
        return await self._producer.start()

    async def stop(self):
        return await self._producer.stop()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    def __getattr__(self, item):
        return getattr(self._producer, item)

    def _normalize_headers(self, headers: Optional[Any]) -> Dict[str, Any]:
        if headers is None:
            return {}

        if isinstance(headers, dict):
            return {k: v for k, v in headers.items()}

        if isinstance(headers, list):
            return {k: v for k, v in headers}

        return {}

    def _headers_dict_to_sequence(self, headers: Dict[str, Any]) -> List[Tuple[str, Any]]:
        sequence = []
        for key, value in headers.items():
            if isinstance(value, bytes):
                sequence.append((key, value))
            else:
                sequence.append((key, str(value)))
        return sequence


class InstrumentedAIOKafkaConsumer:
    """Wrapper assíncrono para aiokafka AIOKafkaConsumer com extração de contexto."""

    def __init__(self, consumer: Any, config: ObservabilityConfig):
        if config is None:
            logger.error(
                "Tentativa de criar InstrumentedAIOKafkaConsumer com config=None. "
                "Verifique se init_observability() foi chamado antes de instrumentar o consumer assíncrono."
            )
            raise ValueError(
                "config não pode ser None para InstrumentedAIOKafkaConsumer. "
                "Use instrument_kafka_consumer() que valida o config."
            )

        if not isinstance(config, ObservabilityConfig):
            logger.error(
                f"Tentativa de criar InstrumentedAIOKafkaConsumer com config de tipo inválido: {type(config).__name__}. "
                "Use init_observability() para criar a configuração corretamente."
            )
            raise TypeError(
                f"config deve ser uma instância de ObservabilityConfig, recebido {type(config).__name__}. "
                "Use init_observability() para criar a configuração corretamente."
            )

        service_name = getattr(config, 'service_name', None)
        if not service_name:
            logger.error(
                f"Tentativa de criar InstrumentedAIOKafkaConsumer com service_name inválido: "
                f"config.service_name={service_name}. "
                "Verifique se init_observability() foi chamado com service_name válido."
            )
            raise ValueError(
                "config.service_name não pode ser None ou vazio para InstrumentedAIOKafkaConsumer."
            )

        self._consumer = consumer
        self._config = config
        self._context_manager = ContextManager(config)
        self._tracer = get_tracer() or trace.get_tracer(__name__)

    async def __aiter__(self):
        async for message in self._consumer:
            headers_dict = self._headers_to_dict(message.headers)
            ctx = extract(headers_dict)
            attach(ctx)
            self._context_manager.extract_kafka_headers(headers_dict)

            with self._tracer.start_as_current_span(f"kafka.consume.{message.topic}") as span:
                span.set_attribute("messaging.system", "kafka")
                span.set_attribute("messaging.source", message.topic)
                span.set_attribute("messaging.kafka.partition", message.partition)
                span.set_attribute("messaging.kafka.offset", message.offset)
                if getattr(self._consumer, "group_id", None):
                    span.set_attribute("messaging.kafka.consumer_group", self._consumer.group_id)

                correlation = get_correlation_context()
                if correlation.get("intent_id"):
                    span.set_attribute("neural.hive.intent.id", correlation["intent_id"])
                if correlation.get("plan_id"):
                    span.set_attribute("neural.hive.plan.id", correlation["plan_id"])
                if correlation.get("user_id"):
                    span.set_attribute("neural.hive.user.id", correlation["user_id"])

                yield message

    def _headers_to_dict(self, headers: Optional[List[Tuple[str, bytes]]]) -> Dict[str, Any]:
        if not headers:
            return {}

        converted = {}
        for key, value in headers:
            if value is None:
                continue
            converted[key] = value.decode() if isinstance(value, (bytes, bytearray)) else value
        return converted

    async def start(self):
        return await self._consumer.start()

    async def stop(self):
        return await self._consumer.stop()

    async def commit(self, *args, **kwargs):
        return await self._consumer.commit(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._consumer, item)


def instrument_kafka_producer(producer: Any, config: ObservabilityConfig = None):
    """
    Instrumenta producer Kafka (confluent-kafka ou aiokafka).

    Args:
        producer: Instância do producer
        config: Configuração de observabilidade (opcional, usa config global se não fornecido)

    Returns:
        Producer instrumentado ou original se config inválido
    """
    logger.debug(
        f"instrument_kafka_producer chamado com producer={type(producer).__name__}, "
        f"config={config}"
    )

    # Se config não for fornecido, usar a configuração global
    if config is None:
        from . import _config as global_config
        config = global_config
        logger.debug(
            f"Config não fornecido para instrument_kafka_producer, usando config global: "
            f"{config.service_name if config and hasattr(config, 'service_name') else 'None'}"
        )

    # Validar config antes de instrumentar
    if config is None:
        logger.warning(
            "Config de observabilidade é None - retornando producer sem instrumentação. "
            "Verifique se init_observability() foi chamado antes. "
            "Para resolver: chame init_observability(service_name='seu-servico') no início da aplicação."
        )
        return producer

    if not getattr(config, 'service_name', None):
        logger.warning(
            "Config de observabilidade sem service_name válido - retornando producer sem instrumentação. "
            "Verifique se init_observability() foi chamado com service_name válido. "
            "Para resolver: chame init_observability(service_name='seu-servico') com um nome de serviço não vazio."
        )
        return producer

    try:
        from confluent_kafka import Producer as ConfluentProducer  # type: ignore
    except Exception:  # pragma: no cover - import opcional
        ConfluentProducer = None  # type: ignore

    try:
        from aiokafka import AIOKafkaProducer  # type: ignore
    except Exception:  # pragma: no cover - import opcional
        AIOKafkaProducer = None  # type: ignore

    if ConfluentProducer and isinstance(producer, ConfluentProducer):
        instrumented = InstrumentedKafkaProducer(producer, config)
        logger.info(
            f"Kafka producer (confluent-kafka) instrumentado com sucesso para "
            f"service_name={config.service_name}"
        )
        return instrumented

    if AIOKafkaProducer and isinstance(producer, AIOKafkaProducer):
        instrumented = InstrumentedAIOKafkaProducer(producer, config)
        logger.info(
            f"Kafka producer (aiokafka) instrumentado com sucesso para "
            f"service_name={config.service_name}"
        )
        return instrumented

    logger.warning(
        f"Tipo de producer Kafka não reconhecido para instrumentação: {type(producer).__name__}. "
        "Tipos suportados: confluent_kafka.Producer, aiokafka.AIOKafkaProducer"
    )
    return producer


def instrument_kafka_consumer(consumer: Any, config: ObservabilityConfig = None):
    """
    Instrumenta consumer Kafka (aiokafka).

    Args:
        consumer: Instância do consumer
        config: Configuração de observabilidade (opcional, usa config global se não fornecido)

    Returns:
        Consumer instrumentado ou original se config inválido
    """
    logger.debug(
        f"instrument_kafka_consumer chamado com consumer={type(consumer).__name__}, "
        f"config={config}"
    )

    # Se config não for fornecido, usar a configuração global
    if config is None:
        from . import _config as global_config
        config = global_config
        logger.debug(
            f"Config não fornecido para instrument_kafka_consumer, usando config global: "
            f"{config.service_name if config and hasattr(config, 'service_name') else 'None'}"
        )

    # Validar config antes de instrumentar
    if config is None:
        logger.warning(
            "Config de observabilidade é None - retornando consumer sem instrumentação. "
            "Verifique se init_observability() foi chamado antes. "
            "Para resolver: chame init_observability(service_name='seu-servico') no início da aplicação."
        )
        return consumer

    if not getattr(config, 'service_name', None):
        logger.warning(
            "Config de observabilidade sem service_name válido - retornando consumer sem instrumentação. "
            "Verifique se init_observability() foi chamado com service_name válido. "
            "Para resolver: chame init_observability(service_name='seu-servico') com um nome de serviço não vazio."
        )
        return consumer

    try:
        from aiokafka import AIOKafkaConsumer  # type: ignore
    except Exception:  # pragma: no cover - import opcional
        AIOKafkaConsumer = None  # type: ignore

    if AIOKafkaConsumer and isinstance(consumer, AIOKafkaConsumer):
        instrumented = InstrumentedAIOKafkaConsumer(consumer, config)
        logger.info(
            f"Kafka consumer (aiokafka) instrumentado com sucesso para "
            f"service_name={config.service_name}"
        )
        return instrumented

    logger.warning(
        f"Tipo de consumer Kafka não reconhecido para instrumentação: {type(consumer).__name__}. "
        "Tipos suportados: aiokafka.AIOKafkaConsumer"
    )
    return consumer
