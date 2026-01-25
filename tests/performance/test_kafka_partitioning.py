"""
Testes de carga para validar estratégia de particionamento Kafka.

Valida:
- Distribuição balanceada de mensagens por partition
- Ausência de hot partitions (> 2x média)
- Coeficiente de variação < 30%

Nota: Os testes usam offset snapshot antes de publicar mensagens para garantir
que apenas mensagens do teste atual sejam consumidas, evitando interferência
de mensagens históricas em ambientes compartilhados.
"""
import asyncio
import uuid
from collections import defaultdict
from typing import Dict, List, Optional

import pytest
from confluent_kafka import Consumer, KafkaError, TopicPartition
from confluent_kafka.admin import AdminClient

# Imports condicionais para evitar falhas em ambientes sem Kafka
try:
    from src.clients.kafka_producer import KafkaProducerClient
    from src.config import get_settings
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False


@pytest.mark.performance
@pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka client not available")
@pytest.mark.asyncio
async def test_partition_distribution_with_multiple_plans():
    """
    Testa distribuição de partitions com múltiplos plans.

    Cenário:
    - 10 plans diferentes
    - 100 tickets por plan (1000 tickets total)
    - Validar distribuição balanceada
    """
    config = get_settings()
    producer = KafkaProducerClient(config)
    await producer.initialize()

    num_plans = 10
    tickets_per_plan = 100

    # Capturar offsets atuais ANTES de publicar para evitar consumir mensagens históricas
    print("📍 Capturando offsets atuais...")
    start_offsets = await _get_current_end_offsets(
        config.kafka_bootstrap_servers,
        config.kafka_tickets_topic
    )

    # Gerar tickets
    plan_ids = [str(uuid.uuid4()) for _ in range(num_plans)]

    print(f"📊 Gerando {num_plans * tickets_per_plan} tickets para {num_plans} plans...")

    for plan_id in plan_ids:
        for i in range(tickets_per_plan):
            ticket = _create_test_ticket(plan_id, i)
            await producer.publish_ticket(ticket)

    await producer.close()

    # Consumir e analisar distribuição (apenas mensagens após start_offsets)
    print("🔍 Analisando distribuição...")

    partition_counts = await _consume_and_analyze(
        config.kafka_bootstrap_servers,
        config.kafka_tickets_topic,
        num_plans * tickets_per_plan,
        start_offsets=start_offsets
    )

    # Validações
    total_messages = sum(partition_counts.values())
    num_partitions = len(partition_counts)
    avg_per_partition = total_messages / num_partitions if num_partitions > 0 else 0

    print(f"✅ Total de mensagens: {total_messages}")
    print(f"   Partitions: {num_partitions}")
    print(f"   Média por partition: {avg_per_partition:.2f}")

    # Validar que nenhuma partition tem > 2x média (hot partition)
    hot_partitions = []
    for partition, count in partition_counts.items():
        ratio = count / avg_per_partition if avg_per_partition > 0 else 0
        print(f"   Partition {partition}: {count} mensagens ({ratio:.2f}x média)")

        if ratio > 2.0:
            hot_partitions.append(partition)

    assert len(hot_partitions) == 0, f"Hot partitions detectadas: {hot_partitions}"

    # Validar coeficiente de variação < 30%
    cv = _calculate_cv(list(partition_counts.values()), avg_per_partition)
    print(f"   Coeficiente de variação: {cv:.2%}")

    assert cv < 0.30, f"Coeficiente de variação muito alto: {cv:.2%} (> 30%)"

    print("✅ Distribuição balanceada validada!")


@pytest.mark.performance
@pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka client not available")
@pytest.mark.asyncio
async def test_partition_distribution_with_burst():
    """
    Testa distribuição com burst de tickets de um único plan.

    Cenário:
    - 1 plan com 500 tickets (burst)
    - 9 plans com 10 tickets cada
    - Validar que burst não causa hot partition inesperada
    """
    config = get_settings()
    producer = KafkaProducerClient(config)
    await producer.initialize()

    # Capturar offsets atuais ANTES de publicar para evitar consumir mensagens históricas
    print("📍 Capturando offsets atuais...")
    start_offsets = await _get_current_end_offsets(
        config.kafka_bootstrap_servers,
        config.kafka_tickets_topic
    )

    # Plan com burst
    burst_plan_id = str(uuid.uuid4())

    # Plans normais
    normal_plan_ids = [str(uuid.uuid4()) for _ in range(9)]

    print("📊 Gerando tickets com burst...")

    # Gerar burst
    for i in range(500):
        ticket = _create_test_ticket(burst_plan_id, i)
        await producer.publish_ticket(ticket)

    # Gerar tickets normais
    for plan_id in normal_plan_ids:
        for i in range(10):
            ticket = _create_test_ticket(plan_id, i)
            await producer.publish_ticket(ticket)

    await producer.close()

    # Analisar distribuição (apenas mensagens após start_offsets)
    partition_counts = await _consume_and_analyze(
        config.kafka_bootstrap_servers,
        config.kafka_tickets_topic,
        590,  # 500 + 90
        start_offsets=start_offsets
    )

    # Validar que burst não causou hot partition inesperada
    total_messages = sum(partition_counts.values())
    num_partitions = len(partition_counts)
    avg_per_partition = total_messages / num_partitions if num_partitions > 0 else 0

    hot_partitions = []
    for partition, count in partition_counts.items():
        ratio = count / avg_per_partition if avg_per_partition > 0 else 0
        if ratio > 2.0:
            hot_partitions.append((partition, count, ratio))

    # Com plan_id como partition key, burst deve ir para uma única partition
    # Mas isso é esperado e não é um problema (data locality)
    print(f"   Partitions com burst: {len(hot_partitions)}")
    for partition, count, ratio in hot_partitions:
        print(f"   Partition {partition}: {count} mensagens ({ratio:.2f}x média)")

    # Validar que apenas 1 partition tem burst (a do burst_plan_id)
    assert len(hot_partitions) <= 1, f"Múltiplas hot partitions detectadas: {hot_partitions}"

    print("✅ Burst isolado em uma única partition (data locality OK)!")


async def _get_current_end_offsets(
    bootstrap_servers: str,
    topic: str
) -> Dict[int, int]:
    """
    Captura os offsets finais atuais de todas as partitions do tópico.

    Usado para garantir que testes consumam apenas mensagens publicadas
    após este ponto, evitando interferência de mensagens históricas.

    Returns:
        Dict mapeando partition -> offset final atual
    """
    consumer_config = {
        'bootstrap.servers': bootstrap_servers,
        'group.id': f'test-offset-checker-{uuid.uuid4()}',
        'auto.offset.reset': 'latest',
        'enable.auto.commit': False
    }

    consumer = Consumer(consumer_config)
    end_offsets: Dict[int, int] = {}

    try:
        # Obter metadata do tópico para descobrir partitions
        metadata = consumer.list_topics(topic, timeout=10.0)

        if topic not in metadata.topics:
            print(f"⚠️ Tópico {topic} não encontrado, retornando offsets vazios")
            return {}

        topic_metadata = metadata.topics[topic]
        partitions = list(topic_metadata.partitions.keys())

        # Criar TopicPartitions e obter offsets finais
        topic_partitions = [TopicPartition(topic, p) for p in partitions]

        # Obter high watermarks (end offsets) para cada partition
        for tp in topic_partitions:
            low, high = consumer.get_watermark_offsets(tp, timeout=10.0)
            end_offsets[tp.partition] = high

        print(f"   Offsets capturados: {end_offsets}")

    finally:
        consumer.close()

    return end_offsets


async def _consume_and_analyze(
    bootstrap_servers: str,
    topic: str,
    expected_messages: int,
    start_offsets: Optional[Dict[int, int]] = None
) -> Dict[int, int]:
    """
    Consome mensagens e retorna contagem por partition.

    Args:
        bootstrap_servers: Servidores Kafka
        topic: Nome do tópico
        expected_messages: Número esperado de mensagens
        start_offsets: Dict de offsets iniciais por partition. Se fornecido,
                       consume apenas mensagens a partir destes offsets,
                       evitando mensagens históricas de testes anteriores.

    Returns:
        Dict mapeando partition -> contagem de mensagens
    """
    consumer_config = {
        'bootstrap.servers': bootstrap_servers,
        'group.id': f'test-partition-analyzer-{uuid.uuid4()}',
        'auto.offset.reset': 'latest',  # Fallback seguro se não houver start_offsets
        'enable.auto.commit': False
    }

    consumer = Consumer(consumer_config)
    partition_counts = defaultdict(int)
    messages_consumed = 0
    empty_polls = 0
    max_empty_polls = 20

    try:
        if start_offsets:
            # Assign manualmente as partitions com offsets específicos
            topic_partitions = [
                TopicPartition(topic, p, offset)
                for p, offset in start_offsets.items()
            ]
            consumer.assign(topic_partitions)
            print(f"   Consumindo a partir dos offsets: {start_offsets}")
        else:
            # Fallback: subscribe normal (não recomendado para testes)
            consumer.subscribe([topic])

        while messages_consumed < expected_messages and empty_polls < max_empty_polls:
            msg = consumer.poll(timeout=5.0)

            if msg is None:
                empty_polls += 1
                continue

            empty_polls = 0

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    raise Exception(f"Kafka error: {msg.error()}")

            partition_counts[msg.partition()] += 1
            messages_consumed += 1

    finally:
        consumer.close()

    return dict(partition_counts)


def _create_test_ticket(plan_id: str, index: int) -> Dict:
    """Cria ticket de teste."""
    return {
        'ticket_id': str(uuid.uuid4()),
        'plan_id': plan_id,
        'intent_id': str(uuid.uuid4()),
        'decision_id': str(uuid.uuid4()),
        'task_id': f'task-{index}',
        'task_type': 'BUILD',
        'description': f'Test task {index}',
        'dependencies': [],
        'status': 'PENDING',
        'priority': 'NORMAL',
        'risk_band': 'low',
        'sla': {
            'deadline': 1234567890000,
            'timeout_ms': 60000,
            'max_retries': 3
        },
        'qos': {
            'delivery_mode': 'AT_LEAST_ONCE',
            'consistency': 'EVENTUAL',
            'durability': 'PERSISTENT'
        },
        'parameters': {},
        'required_capabilities': [],
        'security_level': 'INTERNAL',
        'created_at': 1234567890000,
        'started_at': None,
        'completed_at': None,
        'estimated_duration_ms': None,
        'actual_duration_ms': None,
        'retry_count': 0,
        'error_message': None,
        'compensation_ticket_id': None,
        'metadata': {},
        'schema_version': 1
    }


def _calculate_cv(values: List[int], mean: float) -> float:
    """Calcula coeficiente de variação."""
    import math
    if mean == 0 or not values:
        return 0
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    stddev = math.sqrt(variance)
    return stddev / mean
