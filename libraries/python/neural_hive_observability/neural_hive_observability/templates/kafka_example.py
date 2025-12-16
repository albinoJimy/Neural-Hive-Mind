"""
Exemplo de instrumentação Kafka com Neural Hive Observability.

Mostra como instrumentar producers/consumers e propagar intent_id/plan_id
através dos headers Kafka.
"""

import asyncio

from confluent_kafka import Producer
from aiokafka import AIOKafkaConsumer

from neural_hive_observability import (
    ObservabilityConfig,
    get_config,
    init_observability,
    instrument_kafka_consumer,
    instrument_kafka_producer,
)
from neural_hive_observability.tracing import correlation_context


def produce_example():
    """Produz mensagem com contexto propagado."""
    config = get_config() or ObservabilityConfig(
        service_name="gateway-intencoes",
        neural_hive_component="gateway",
        neural_hive_layer="experiencia",
    )

    producer = instrument_kafka_producer(
        Producer({"bootstrap.servers": "localhost:9092"}),
        config=config,
    )

    with correlation_context(intent_id="intent-123", plan_id="plan-456"):
        producer.produce(
            topic="neural.intentions",
            key=b"intent-123",
            value=b'{"text": "hello"}',
        )
        producer.flush()


async def consume_example():
    """Consome mensagens com extração automática de contexto."""
    config = get_config() or ObservabilityConfig(
        service_name="orchestrator",
        neural_hive_component="orchestrator",
        neural_hive_layer="orquestracao",
    )

    consumer = instrument_kafka_consumer(
        AIOKafkaConsumer(
            "neural.intentions",
            bootstrap_servers="localhost:9092",
            group_id="demo-group",
            enable_auto_commit=True,
        ),
        config=config,
    )

    await consumer.start()
    try:
        async for message in consumer:
            print(f"[{message.topic}] {message.value} (offset={message.offset})")
    finally:
        await consumer.stop()


def main():
    init_observability(
        service_name="gateway-intencoes",
        neural_hive_component="gateway",
        neural_hive_layer="experiencia",
    )

    produce_example()
    asyncio.run(consume_example())


if __name__ == "__main__":
    main()
