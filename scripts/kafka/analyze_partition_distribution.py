#!/usr/bin/env python3
"""
Script para analisar distribuição de mensagens por partition no Kafka.

Uso:
    python scripts/kafka/analyze_partition_distribution.py \
        --topic execution.tickets \
        --bootstrap-servers localhost:9092 \
        --time-window 3600

Saída:
    - Distribuição de mensagens por partition
    - Identificação de hot partitions (> 2x média)
    - Recomendações de rebalanceamento
"""
import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.admin import AdminClient


def analyze_partition_distribution(
    bootstrap_servers: str,
    topic: str,
    time_window_seconds: int = 3600
):
    """Analisa distribuição de mensagens por partition."""

    # Configurar consumer
    consumer_config = {
        'bootstrap.servers': bootstrap_servers,
        'group.id': f'partition-analyzer-{datetime.now().timestamp()}',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False
    }

    consumer = Consumer(consumer_config)

    # Obter metadata do tópico
    admin_client = AdminClient({'bootstrap.servers': bootstrap_servers})
    metadata = admin_client.list_topics(topic=topic)

    if topic not in metadata.topics:
        print(f"❌ Tópico '{topic}' não encontrado")
        sys.exit(1)

    topic_metadata = metadata.topics[topic]
    num_partitions = len(topic_metadata.partitions)

    print(f"📊 Analisando tópico: {topic}")
    print(f"   Partitions: {num_partitions}")
    print(f"   Janela de tempo: {time_window_seconds}s")
    print()

    # Coletar mensagens por partition
    partition_counts = defaultdict(int)
    partition_bytes = defaultdict(int)
    partition_keys = defaultdict(set)

    # Subscrever todas as partitions
    from confluent_kafka import TopicPartition
    partitions = [TopicPartition(topic, p) for p in range(num_partitions)]
    consumer.assign(partitions)

    # Calcular offset inicial (time_window_seconds atrás)
    cutoff_time = datetime.now() - timedelta(seconds=time_window_seconds)
    cutoff_timestamp = int(cutoff_time.timestamp() * 1000)

    print(f"🔍 Coletando mensagens desde {cutoff_time.isoformat()}...")

    messages_processed = 0
    empty_polls = 0
    max_empty_polls = 10

    try:
        while empty_polls < max_empty_polls:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                empty_polls += 1
                continue

            empty_polls = 0

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    print(f"❌ Erro: {msg.error()}")
                    break

            # Verificar timestamp
            timestamp_type, timestamp = msg.timestamp()
            if timestamp < cutoff_timestamp:
                continue

            # Coletar estatísticas
            partition = msg.partition()
            partition_counts[partition] += 1
            partition_bytes[partition] += len(msg.value()) if msg.value() else 0

            if msg.key():
                partition_keys[partition].add(msg.key().decode('utf-8'))

            messages_processed += 1

            if messages_processed % 1000 == 0:
                print(f"   Processadas: {messages_processed} mensagens...")

    finally:
        consumer.close()

    # Calcular estatísticas
    total_messages = sum(partition_counts.values())
    total_bytes = sum(partition_bytes.values())
    avg_messages_per_partition = total_messages / num_partitions if num_partitions > 0 else 0

    print()
    print(f"✅ Análise concluída: {total_messages} mensagens processadas")
    print()

    # Exibir distribuição
    print("📈 Distribuição por Partition:")
    print(f"{'Partition':<10} {'Mensagens':<12} {'%':<8} {'Bytes':<12} {'Keys Únicas':<15} {'Status'}")
    print("-" * 80)

    hot_partitions = []

    for partition in range(num_partitions):
        count = partition_counts[partition]
        percentage = (count / total_messages * 100) if total_messages > 0 else 0
        bytes_size = partition_bytes[partition]
        unique_keys = len(partition_keys[partition])

        # Detectar hot partition (> 2x média)
        is_hot = count > (avg_messages_per_partition * 2) if avg_messages_per_partition > 0 else False
        status = "🔥 HOT" if is_hot else "✅ OK"

        if is_hot:
            hot_partitions.append(partition)

        print(f"{partition:<10} {count:<12} {percentage:<7.2f}% {bytes_size:<12} {unique_keys:<15} {status}")

    print("-" * 80)
    print(f"{'TOTAL':<10} {total_messages:<12} {'100.00%':<8} {total_bytes:<12}")
    print()

    # Estatísticas agregadas
    print("📊 Estatísticas:")
    print(f"   Média por partition: {avg_messages_per_partition:.2f} mensagens")
    if total_messages > 0:
        print(f"   Desvio padrão: {_calculate_stddev(list(partition_counts.values()), avg_messages_per_partition):.2f}")
        print(f"   Coeficiente de variação: {_calculate_cv(list(partition_counts.values()), avg_messages_per_partition):.2%}")
    print()

    # Recomendações
    if hot_partitions:
        print("⚠️  Hot Partitions Detectadas:")
        for partition in hot_partitions:
            count = partition_counts[partition]
            ratio = count / avg_messages_per_partition if avg_messages_per_partition > 0 else 0
            print(f"   Partition {partition}: {count} mensagens ({ratio:.2f}x média)")
        print()
        print("💡 Recomendações:")
        print("   1. Verificar se partition key está bem distribuída")
        print("   2. Considerar aumentar número de partitions")
        print("   3. Analisar padrão de geração de plans (burst?)")
    else:
        print("✅ Distribuição balanceada - nenhuma hot partition detectada")

    return {
        'total_messages': total_messages,
        'num_partitions': num_partitions,
        'partition_counts': dict(partition_counts),
        'hot_partitions': hot_partitions
    }


def _calculate_stddev(values, mean):
    """Calcula desvio padrão."""
    import math
    if not values:
        return 0.0
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def _calculate_cv(values, mean):
    """Calcula coeficiente de variação."""
    if mean == 0:
        return 0
    stddev = _calculate_stddev(values, mean)
    return stddev / mean


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Analisar distribuição de partitions Kafka')
    parser.add_argument('--topic', required=True, help='Nome do tópico')
    parser.add_argument('--bootstrap-servers', required=True, help='Kafka bootstrap servers')
    parser.add_argument('--time-window', type=int, default=3600, help='Janela de tempo em segundos (default: 3600)')

    args = parser.parse_args()

    analyze_partition_distribution(
        bootstrap_servers=args.bootstrap_servers,
        topic=args.topic,
        time_window_seconds=args.time_window
    )
