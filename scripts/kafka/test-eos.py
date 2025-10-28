#!/usr/bin/env python3
"""
Script para testar Exactly-Once Semantics (EOS) do Kafka
Publica 10k mensagens com IDs únicos e valida duplicatas
"""

import asyncio
import json
import uuid
import time
from typing import Dict, Set, List
from datetime import datetime
from dataclasses import dataclass
from confluent_kafka import Producer, Consumer, KafkaError
from confluent_kafka.admin import AdminClient, NewTopic
import argparse
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EOSTestConfig:
    """Configurações do teste EOS"""
    bootstrap_servers: str
    topic_name: str
    num_messages: int
    num_producers: int
    num_consumers: int
    consumer_groups: List[str]
    test_duration_seconds: int


@dataclass
class EOSTestResults:
    """Resultados do teste EOS"""
    messages_sent: int
    messages_received: Dict[str, int]  # consumer_group -> count
    duplicates_found: Dict[str, int]   # consumer_group -> duplicate_count
    test_duration: float
    success: bool
    errors: List[str]


class EOSProducer:
    """Producer configurado para EOS"""

    def __init__(self, config: EOSTestConfig, producer_id: int):
        self.config = config
        self.producer_id = producer_id
        self.transactional_id = f"eos-test-producer-{producer_id}-{int(time.time())}"

        producer_config = {
            'bootstrap.servers': config.bootstrap_servers,
            'transactional.id': self.transactional_id,
            'enable.idempotence': True,
            'acks': 'all',
            'retries': 2147483647,
            'max.in.flight.requests.per.connection': 5,
            'compression.type': 'snappy',
            'batch.size': 16384,
            'linger.ms': 10,
            'delivery.timeout.ms': 300000,
            'request.timeout.ms': 30000
        }

        self.producer = Producer(producer_config)
        self.producer.init_transactions()

    async def send_messages(self, start_id: int, count: int) -> int:
        """Enviar mensagens com EOS"""
        sent_count = 0

        try:
            self.producer.begin_transaction()

            for i in range(count):
                message_id = f"eos-test-{start_id + i}-{uuid.uuid4()}"
                message_data = {
                    'id': message_id,
                    'producer_id': self.producer_id,
                    'sequence': i,
                    'timestamp': datetime.utcnow().isoformat(),
                    'test_payload': f"Test message {start_id + i} from producer {self.producer_id}"
                }

                key = f"producer-{self.producer_id}"
                value = json.dumps(message_data)

                # Callback para tracking
                def delivery_callback(err, msg, msg_id=message_id):
                    if err:
                        logger.error(f"Failed to deliver message {msg_id}: {err}")
                    else:
                        logger.debug(f"Message {msg_id} delivered to {msg.topic()}[{msg.partition()}] @ {msg.offset()}")

                self.producer.produce(
                    topic=self.config.topic_name,
                    key=key,
                    value=value,
                    callback=delivery_callback
                )

                sent_count += 1

                # Flush periodicamente para evitar buffer overflow
                if i % 1000 == 0:
                    self.producer.flush(timeout=10.0)

            # Flush final antes do commit
            self.producer.flush(timeout=30.0)

            # Commit da transação
            self.producer.commit_transaction()

            logger.info(f"Producer {self.producer_id} sent {sent_count} messages successfully")

        except Exception as e:
            logger.error(f"Error in producer {self.producer_id}: {e}")
            try:
                self.producer.abort_transaction()
            except:
                pass
            raise

        return sent_count

    def close(self):
        """Fechar producer"""
        if hasattr(self, 'producer'):
            self.producer.flush(timeout=30.0)


class EOSConsumer:
    """Consumer configurado para EOS"""

    def __init__(self, config: EOSTestConfig, group_id: str):
        self.config = config
        self.group_id = group_id

        consumer_config = {
            'bootstrap.servers': config.bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,
            'isolation.level': 'read_committed',  # Crítico para EOS
            'max.poll.interval.ms': 300000,
            'session.timeout.ms': 30000,
            'heartbeat.interval.ms': 10000
        }

        self.consumer = Consumer(consumer_config)
        self.consumer.subscribe([config.topic_name])

    async def consume_messages(self, duration_seconds: int) -> Dict[str, int]:
        """Consumir mensagens por um período determinado"""
        messages_received = 0
        unique_ids: Set[str] = set()
        duplicates = 0

        start_time = time.time()

        try:
            while time.time() - start_time < duration_seconds:
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error(f"Consumer {self.group_id} error: {msg.error()}")
                        continue

                try:
                    message_data = json.loads(msg.value().decode('utf-8'))
                    message_id = message_data.get('id')

                    if message_id:
                        if message_id in unique_ids:
                            duplicates += 1
                            logger.warning(f"Duplicate message found in group {self.group_id}: {message_id}")
                        else:
                            unique_ids.add(message_id)

                        messages_received += 1

                        # Commit offset periodicamente
                        if messages_received % 1000 == 0:
                            self.consumer.commit(asynchronous=False)
                            logger.info(f"Consumer {self.group_id} processed {messages_received} messages")

                except json.JSONDecodeError:
                    logger.error(f"Failed to decode message in group {self.group_id}")
                    continue

        except KeyboardInterrupt:
            logger.info(f"Consumer {self.group_id} interrupted")
        except Exception as e:
            logger.error(f"Error in consumer {self.group_id}: {e}")
        finally:
            # Final commit
            try:
                self.consumer.commit(asynchronous=False)
            except:
                pass

        logger.info(f"Consumer {self.group_id}: {messages_received} messages, {duplicates} duplicates")

        return {
            'messages': messages_received,
            'duplicates': duplicates,
            'unique_ids': len(unique_ids)
        }

    def close(self):
        """Fechar consumer"""
        if hasattr(self, 'consumer'):
            self.consumer.close()


class EOSTestRunner:
    """Executor do teste EOS"""

    def __init__(self, config: EOSTestConfig):
        self.config = config
        self.admin_client = AdminClient({'bootstrap.servers': config.bootstrap_servers})

    async def setup_topic(self):
        """Criar tópico de teste"""
        topic = NewTopic(
            topic=self.config.topic_name,
            num_partitions=6,
            replication_factor=3,
            config={
                'cleanup.policy': 'delete',
                'retention.ms': '3600000',  # 1 hora
                'max.message.bytes': '1000012',  # ~1MB
                'min.insync.replicas': '2'
            }
        )

        try:
            futures = self.admin_client.create_topics([topic])
            for topic_name, future in futures.items():
                future.result()  # Block for result
                logger.info(f"Topic {topic_name} created successfully")
        except Exception as e:
            if "already exists" in str(e):
                logger.info(f"Topic {self.config.topic_name} already exists")
            else:
                logger.error(f"Failed to create topic: {e}")
                raise

    async def run_producers(self) -> int:
        """Executar producers em paralelo"""
        messages_per_producer = self.config.num_messages // self.config.num_producers
        producers = []
        tasks = []

        try:
            # Criar producers
            for i in range(self.config.num_producers):
                producer = EOSProducer(self.config, i)
                producers.append(producer)

                start_id = i * messages_per_producer
                task = asyncio.create_task(
                    producer.send_messages(start_id, messages_per_producer)
                )
                tasks.append(task)

            # Aguardar conclusão
            results = await asyncio.gather(*tasks, return_exceptions=True)

            total_sent = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Producer {i} failed: {result}")
                else:
                    total_sent += result

            return total_sent

        finally:
            # Cleanup producers
            for producer in producers:
                try:
                    producer.close()
                except:
                    pass

    async def run_consumers(self) -> Dict[str, Dict[str, int]]:
        """Executar consumers em paralelo"""
        consumers = []
        tasks = []

        try:
            # Criar consumers para cada group
            for group_id in self.config.consumer_groups:
                consumer = EOSConsumer(self.config, group_id)
                consumers.append(consumer)

                task = asyncio.create_task(
                    consumer.consume_messages(self.config.test_duration_seconds)
                )
                tasks.append((group_id, task))

            # Aguardar conclusão
            results = {}
            for group_id, task in tasks:
                try:
                    result = await task
                    results[group_id] = result
                except Exception as e:
                    logger.error(f"Consumer group {group_id} failed: {e}")
                    results[group_id] = {'messages': 0, 'duplicates': 0, 'unique_ids': 0}

            return results

        finally:
            # Cleanup consumers
            for consumer in consumers:
                try:
                    consumer.close()
                except:
                    pass

    async def run_test(self) -> EOSTestResults:
        """Executar teste completo"""
        logger.info(f"Starting EOS test with {self.config.num_messages} messages")
        start_time = time.time()
        errors = []

        try:
            # Setup
            await self.setup_topic()

            # Aguardar tópico ficar disponível
            await asyncio.sleep(5)

            # Executar producers e consumers em paralelo
            producer_task = asyncio.create_task(self.run_producers())

            # Aguardar um pouco antes de iniciar consumers
            await asyncio.sleep(2)

            consumer_task = asyncio.create_task(self.run_consumers())

            # Aguardar resultados
            messages_sent = await producer_task
            consumer_results = await consumer_task

            # Processar resultados
            messages_received = {group: data['messages'] for group, data in consumer_results.items()}
            duplicates_found = {group: data['duplicates'] for group, data in consumer_results.items()}

            total_duration = time.time() - start_time

            # Determinar sucesso
            total_duplicates = sum(duplicates_found.values())
            success = total_duplicates == 0 and messages_sent == self.config.num_messages

            if total_duplicates > 0:
                errors.append(f"Found {total_duplicates} duplicate messages across all consumer groups")

            if messages_sent != self.config.num_messages:
                errors.append(f"Expected {self.config.num_messages} messages, but sent {messages_sent}")

            return EOSTestResults(
                messages_sent=messages_sent,
                messages_received=messages_received,
                duplicates_found=duplicates_found,
                test_duration=total_duration,
                success=success,
                errors=errors
            )

        except Exception as e:
            errors.append(f"Test execution failed: {str(e)}")
            return EOSTestResults(
                messages_sent=0,
                messages_received={},
                duplicates_found={},
                test_duration=time.time() - start_time,
                success=False,
                errors=errors
            )


async def main():
    parser = argparse.ArgumentParser(description='Test Kafka Exactly-Once Semantics')
    parser.add_argument('--bootstrap-servers', default='localhost:9092', help='Kafka bootstrap servers')
    parser.add_argument('--topic', default='eos-test-topic', help='Test topic name')
    parser.add_argument('--messages', type=int, default=10000, help='Number of messages to send')
    parser.add_argument('--producers', type=int, default=3, help='Number of producer instances')
    parser.add_argument('--consumer-groups', nargs='+', default=['eos-test-group-1', 'eos-test-group-2'], help='Consumer groups')
    parser.add_argument('--duration', type=int, default=120, help='Test duration in seconds')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = EOSTestConfig(
        bootstrap_servers=args.bootstrap_servers,
        topic_name=args.topic,
        num_messages=args.messages,
        num_producers=args.producers,
        num_consumers=len(args.consumer_groups),
        consumer_groups=args.consumer_groups,
        test_duration_seconds=args.duration
    )

    logger.info("=== Kafka EOS Test Configuration ===")
    logger.info(f"Bootstrap Servers: {config.bootstrap_servers}")
    logger.info(f"Topic: {config.topic_name}")
    logger.info(f"Messages: {config.num_messages}")
    logger.info(f"Producers: {config.num_producers}")
    logger.info(f"Consumer Groups: {config.consumer_groups}")
    logger.info(f"Duration: {config.test_duration_seconds}s")
    logger.info("=" * 40)

    test_runner = EOSTestRunner(config)
    results = await test_runner.run_test()

    # Print results
    print("\n=== EOS Test Results ===")
    print(f"Success: {'✅ PASS' if results.success else '❌ FAIL'}")
    print(f"Messages Sent: {results.messages_sent}")
    print(f"Test Duration: {results.test_duration:.2f} seconds")

    print("\nMessages Received by Consumer Group:")
    for group, count in results.messages_received.items():
        print(f"  {group}: {count}")

    print("\nDuplicates Found by Consumer Group:")
    for group, count in results.duplicates_found.items():
        print(f"  {group}: {count}")

    if results.errors:
        print("\nErrors:")
        for error in results.errors:
            print(f"  - {error}")

    print("=" * 40)

    # Exit with appropriate code
    exit(0 if results.success else 1)


if __name__ == "__main__":
    asyncio.run(main())