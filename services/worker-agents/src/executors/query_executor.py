"""
Executor para task_type=QUERY com suporte a múltiplas fontes de dados.

Suporta execução de queries em:
- MongoDB (coleções e agregações)
- Neo4j (Cypher queries)
- Kafka (consumo de mensagens)
- Redis (chaves e valores)
"""

import asyncio
import json
import time
from typing import Any, Dict, Optional, List
from neural_hive_observability import get_tracer
from .base_executor import BaseTaskExecutor


class QueryExecutor(BaseTaskExecutor):
    """Executor para task_type=QUERY com suporte a múltiplas fontes de dados."""

    def get_task_type(self) -> str:
        return 'QUERY'

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client=None,
        metrics=None,
        mongodb_client=None,
        redis_client=None,
        neo4j_client=None,
        kafka_consumer=None
    ):
        """
        Inicializa QueryExecutor com clientes de fontes de dados.

        Args:
            config: Configurações do worker agent
            vault_client: Cliente Vault para secrets
            code_forge_client: Cliente Code Forge para geração de código
            metrics: Objeto de métricas Prometheus
            mongodb_client: Cliente MongoDB para queries
            redis_client: Cliente Redis para queries
            neo4j_client: Cliente Neo4j para queries Cypher
            kafka_consumer: Consumer Kafka para queries em tópicos
        """
        super().__init__(config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics)
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.neo4j_client = neo4j_client
        self.kafka_consumer = kafka_consumer

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executar tarefa QUERY com dispatch baseado em query_type.

        Args:
            ticket: Ticket de execução com parâmetros

        Returns:
            Resultado da query
        """
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})
        query_type = parameters.get('query_type', 'mongodb')

        tracer = get_tracer()
        with tracer.start_as_current_span('task_execution') as span:
            span.set_attribute('neural.hive.task_id', ticket_id)
            span.set_attribute('neural.hive.task_type', self.get_task_type())
            span.set_attribute('neural.hive.executor', self.__class__.__name__)
            span.set_attribute('neural.hive.query_type', query_type)

            self.log_execution(
                ticket_id,
                'query_execution_started',
                query_type=query_type,
                parameters=parameters
            )

            try:
                start_time = time.monotonic()

                # Dispatch baseado em query_type
                if query_type == 'mongodb':
                    result = await self._execute_mongodb_query(ticket_id, parameters, span)
                elif query_type == 'neo4j':
                    result = await self._execute_neo4j_query(ticket_id, parameters, span)
                elif query_type == 'kafka':
                    result = await self._execute_kafka_query(ticket_id, parameters, span)
                elif query_type == 'redis':
                    result = await self._execute_redis_query(ticket_id, parameters, span)
                else:
                    raise ValueError(f"Unsupported query_type: {query_type}")

                elapsed_seconds = time.monotonic() - start_time

                # Registrar métricas de duração
                if self.metrics and hasattr(self.metrics, 'query_duration_seconds'):
                    self.metrics.query_duration_seconds.labels(query_type=query_type).observe(elapsed_seconds)

                # Registrar métricas de sucesso
                if self.metrics and hasattr(self.metrics, 'query_executed_total'):
                    status = 'success' if result.get('success') else 'failed'
                    self.metrics.query_executed_total.labels(status=status, query_type=query_type).inc()

                span.set_attribute('neural.hive.execution_status', 'success' if result.get('success') else 'failed')
                span.set_attribute('neural.hive.duration_seconds', elapsed_seconds)

                return result

            except Exception as e:
                self.log_execution(
                    ticket_id,
                    'query_execution_failed',
                    level='error',
                    query_type=query_type,
                    error=str(e)
                )

                if self.metrics and hasattr(self.metrics, 'query_executed_total'):
                    self.metrics.query_executed_total.labels(status='failed', query_type=query_type).inc()

                return {
                    'success': False,
                    'output': None,
                    'metadata': {
                        'executor': 'QueryExecutor',
                        'query_type': query_type,
                        'error': str(e)
                    },
                    'logs': [
                        f'Query execution failed: {str(e)}'
                    ]
                }

    async def _execute_mongodb_query(self, ticket_id: str, parameters: Dict[str, Any], span) -> Dict[str, Any]:
        """Executa query no MongoDB."""
        if not self.mongodb_client:
            return self._error_result('MongoDB client not available', 'mongodb')

        try:
            collection_name = parameters.get('collection')
            if not collection_name:
                raise ValueError("Missing 'collection' parameter for MongoDB query")

            filter_query = parameters.get('filter', {})
            projection = parameters.get('projection')
            limit = parameters.get('limit')
            sort = parameters.get('sort')
            skip = parameters.get('skip', 0)

            # Obter coleção
            collection = self.mongodb_client.db[collection_name]

            # Construir cursor
            cursor = collection.find(filter_query, projection)

            # Aplicar sorting se especificado
            if sort:
                cursor = cursor.sort(sort)

            # Aplicar skip se especificado
            if skip:
                cursor = cursor.skip(skip)

            # Aplicar limite se especificado
            if limit:
                cursor = cursor.limit(limit)

            # Executar query e converter documentos para JSON serializável
            documents = await cursor.to_list(length=limit or 1000)
            serialized_docs = [self._serialize_doc(doc) for doc in documents]

            span.set_attribute('neural.hive.mongodb_collection', collection_name)
            span.set_attribute('neural.hive.document_count', len(serialized_docs))

            self.log_execution(
                ticket_id,
                'mongodb_query_completed',
                collection=collection_name,
                document_count=len(serialized_docs)
            )

            return {
                'success': True,
                'output': {
                    'documents': serialized_docs,
                    'count': len(serialized_docs)
                },
                'metadata': {
                    'executor': 'QueryExecutor',
                    'query_type': 'mongodb',
                    'collection': collection_name,
                    'filter': filter_query
                },
                'logs': [
                    f'MongoDB query executed on {collection_name}',
                    f'Returned {len(serialized_docs)} documents',
                    'Query completed successfully'
                ]
            }

        except Exception as e:
            self.log_execution(
                ticket_id,
                'mongodb_query_failed',
                level='error',
                error=str(e)
            )
            return {
                'success': False,
                'output': None,
                'metadata': {
                    'executor': 'QueryExecutor',
                    'query_type': 'mongodb',
                    'error': str(e)
                },
                'logs': [
                    f'MongoDB query failed: {str(e)}'
                ]
            }

    async def _execute_neo4j_query(self, ticket_id: str, parameters: Dict[str, Any], span) -> Dict[str, Any]:
        """Executa query Cypher no Neo4j."""
        if not self.neo4j_client:
            return self._error_result('Neo4j client not available', 'neo4j')

        try:
            cypher_query = parameters.get('cypher_query')
            if not cypher_query:
                raise ValueError("Missing 'cypher_query' parameter for Neo4j query")

            query_params = parameters.get('parameters', {})
            timeout = parameters.get('timeout')

            # Executar query
            results = await self.neo4j_client.execute_query(
                query=cypher_query,
                parameters=query_params,
                timeout=timeout
            )

            # Converter resultados para JSON serializável
            serialized_results = self._serialize_neo4j_results(results)

            span.set_attribute('neural.hive.neo4j_query', cypher_query[:100] if len(cypher_query) > 100 else cypher_query)
            span.set_attribute('neural.hive.result_count', len(serialized_results))

            self.log_execution(
                ticket_id,
                'neo4j_query_completed',
                result_count=len(serialized_results)
            )

            return {
                'success': True,
                'output': {
                    'results': serialized_results,
                    'count': len(serialized_results)
                },
                'metadata': {
                    'executor': 'QueryExecutor',
                    'query_type': 'neo4j',
                    'cypher_query': cypher_query
                },
                'logs': [
                    f'Neo4j query executed',
                    f'Returned {len(serialized_results)} results',
                    'Query completed successfully'
                ]
            }

        except Exception as e:
            self.log_execution(
                ticket_id,
                'neo4j_query_failed',
                level='error',
                error=str(e)
            )
            return {
                'success': False,
                'output': None,
                'metadata': {
                    'executor': 'QueryExecutor',
                    'query_type': 'neo4j',
                    'error': str(e)
                },
                'logs': [
                    f'Neo4j query failed: {str(e)}'
                ]
            }

    async def _execute_kafka_query(self, ticket_id: str, parameters: Dict[str, Any], span) -> Dict[str, Any]:
        """Consome mensagens de um tópico Kafka."""
        try:
            from aiokafka import AIOKafkaConsumer
            from aiokafka.structs import TopicPartition

            topic = parameters.get('topic')
            if not topic:
                raise ValueError("Missing 'topic' parameter for Kafka query")

            partition = parameters.get('partition')
            offset = parameters.get('offset', 0)
            max_messages = parameters.get('max_messages', 100)
            timeout_ms = parameters.get('timeout_ms', 5000)

            # Configuração do consumer temporário
            config = self.config

            consumer_config = {
                'bootstrap_servers': config.kafka_bootstrap_servers,
                'group_id': f'query_executor_{ticket_id}',
                'auto_offset_reset': 'earliest' if offset == 0 else 'specific',
                'enable_auto_commit': False
            }

            # Adicionar SASL se configurado
            if hasattr(config, 'kafka_sasl_mechanism') and config.kafka_sasl_mechanism:
                consumer_config.update({
                    'security_protocol': 'SASL_SSL',
                    'sasl_mechanism': config.kafka_sasl_mechanism,
                    'sasl_plain_username': getattr(config, 'kafka_sasl_username', None),
                    'sasl_plain_password': getattr(config, 'kafka_sasl_password', None)
                })

            consumer = AIOKafkaConsumer(**consumer_config)

            try:
                await consumer.start()

                # Buscar particionar se especificado
                if partition is not None:
                    tp = TopicPartition(topic, partition)
                    consumer.assign([tp])
                    if offset > 0:
                        consumer.seek(tp, offset)
                else:
                    consumer.subscribe([topic])

                # Consumir mensagens
                messages = []
                end_time = time.monotonic() + (timeout_ms / 1000)

                while len(messages) < max_messages and time.monotonic() < end_time:
                    async for msg in consumer:
                        message_data = {
                            'topic': msg.topic,
                            'partition': msg.partition,
                            'offset': msg.offset,
                            'timestamp': msg.timestamp,
                            'key': msg.key.decode('utf-8') if msg.key else None,
                            'value': json.loads(msg.value.decode('utf-8')) if msg.value else None
                        }
                        messages.append(message_data)

                        if len(messages) >= max_messages:
                            break

                    if len(messages) == 0:
                        await asyncio.sleep(0.1)

                span.set_attribute('neural.hive.kafka_topic', topic)
                span.set_attribute('neural.hive.message_count', len(messages))

                self.log_execution(
                    ticket_id,
                    'kafka_query_completed',
                    topic=topic,
                    message_count=len(messages)
                )

                return {
                    'success': True,
                    'output': {
                        'messages': messages,
                        'count': len(messages)
                    },
                    'metadata': {
                        'executor': 'QueryExecutor',
                        'query_type': 'kafka',
                        'topic': topic,
                        'partition': partition,
                        'offset': offset
                    },
                    'logs': [
                        f'Kafka query on {topic}',
                        f'Consumed {len(messages)} messages',
                        'Query completed successfully'
                    ]
                }

            finally:
                await consumer.stop()

        except ImportError:
            return self._error_result('aiokafka not installed', 'kafka')
        except Exception as e:
            self.log_execution(
                ticket_id,
                'kafka_query_failed',
                level='error',
                error=str(e)
            )
            return {
                'success': False,
                'output': None,
                'metadata': {
                    'executor': 'QueryExecutor',
                    'query_type': 'kafka',
                    'error': str(e)
                },
                'logs': [
                    f'Kafka query failed: {str(e)}'
                ]
            }

    async def _execute_redis_query(self, ticket_id: str, parameters: Dict[str, Any], span) -> Dict[str, Any]:
        """Executa query no Redis."""
        if not self.redis_client:
            return self._error_result('Redis client not available', 'redis')

        try:
            operation = parameters.get('operation', 'get')

            if operation == 'get':
                key = parameters.get('key')
                if not key:
                    raise ValueError("Missing 'key' parameter for Redis GET operation")

                value = await self.redis_client.get(key)
                result = {
                    'key': key,
                    'value': json.loads(value) if value and self._is_json(value) else value,
                    'exists': value is not None
                }

                span.set_attribute('neural.hive.redis_key', key)

                self.log_execution(
                    ticket_id,
                    'redis_get_completed',
                    key=key,
                    exists=value is not None
                )

                return {
                    'success': True,
                    'output': result,
                    'metadata': {
                        'executor': 'QueryExecutor',
                        'query_type': 'redis',
                        'operation': 'get'
                    },
                    'logs': [
                        f'Redis GET on {key}',
                        'Query completed successfully'
                    ]
                }

            elif operation == 'scan':
                pattern = parameters.get('pattern', '*')
                count = parameters.get('count', 100)

                keys = []
                async for key in self.redis_client.scan_iter(match=pattern, count=count):
                    if len(keys) >= count:
                        break
                    keys.append(key)

                # Buscar valores se solicitado
                values = None
                if parameters.get('fetch_values', False):
                    values = {}
                    for key in keys:
                        value = await self.redis_client.get(key)
                        if value:
                            try:
                                values[key] = json.loads(value)
                            except:
                                values[key] = value

                result = {
                    'keys': keys,
                    'count': len(keys),
                    'pattern': pattern
                }

                if values:
                    result['values'] = values

                span.set_attribute('neural.hive.redis_pattern', pattern)
                span.set_attribute('neural.hive.redis_key_count', len(keys))

                self.log_execution(
                    ticket_id,
                    'redis_scan_completed',
                    pattern=pattern,
                    key_count=len(keys)
                )

                return {
                    'success': True,
                    'output': result,
                    'metadata': {
                        'executor': 'QueryExecutor',
                        'query_type': 'redis',
                        'operation': 'scan'
                    },
                    'logs': [
                        f'Redis SCAN with pattern {pattern}',
                        f'Found {len(keys)} keys',
                        'Query completed successfully'
                    ]
                }

            elif operation == 'keys':
                pattern = parameters.get('pattern', '*')
                keys = await self.redis_client.keys(pattern)

                result = {
                    'keys': keys,
                    'count': len(keys),
                    'pattern': pattern
                }

                span.set_attribute('neural.hive.redis_pattern', pattern)
                span.set_attribute('neural.hive.redis_key_count', len(keys))

                self.log_execution(
                    ticket_id,
                    'redis_keys_completed',
                    pattern=pattern,
                    key_count=len(keys)
                )

                return {
                    'success': True,
                    'output': result,
                    'metadata': {
                        'executor': 'QueryExecutor',
                        'query_type': 'redis',
                        'operation': 'keys'
                    },
                    'logs': [
                        f'Redis KEYS with pattern {pattern}',
                        f'Found {len(keys)} keys',
                        'Query completed successfully'
                    ]
                }

            else:
                raise ValueError(f"Unsupported Redis operation: {operation}")

        except Exception as e:
            self.log_execution(
                ticket_id,
                'redis_query_failed',
                level='error',
                operation=operation,
                error=str(e)
            )
            return {
                'success': False,
                'output': None,
                'metadata': {
                    'executor': 'QueryExecutor',
                    'query_type': 'redis',
                    'operation': operation,
                    'error': str(e)
                },
                'logs': [
                    f'Redis {operation} failed: {str(e)}'
                ]
            }

    def _error_result(self, message: str, query_type: str) -> Dict[str, Any]:
        """Retorna resultado de erro padronizado."""
        return {
            'success': False,
            'output': None,
            'metadata': {
                'executor': 'QueryExecutor',
                'query_type': query_type,
                'error': message
            },
            'logs': [message]
        }

    def _serialize_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Serializa documento MongoDB para JSON."""
        if '_id' in doc:
            doc = dict(doc)
            doc['_id'] = str(doc['_id'])
        return doc

    def _serialize_neo4j_results(self, results: List[Dict]) -> List[Dict]:
        """Serializa resultados Neo4j para JSON."""
        serialized = []
        for record in results:
            serialized_record = {}
            for key, value in record.items():
                # Converter nós e relacionamentos para dict
                if hasattr(value, '__dict__'):
                    serialized_record[key] = self._neo4j_entity_to_dict(value)
                elif isinstance(value, list):
                    serialized_record[key] = [
                        self._neo4j_entity_to_dict(item) if hasattr(item, '__dict__') else item
                        for item in value
                    ]
                else:
                    serialized_record[key] = value
            serialized.append(serialized_record)
        return serialized

    def _neo4j_entity_to_dict(self, entity) -> Dict[str, Any]:
        """Converte entidade Neo4j para dict."""
        if hasattr(entity, 'labels'):
            return {
                'id': str(entity.element_id) if hasattr(entity, 'element_id') else str(entity.id),
                'labels': list(entity.labels) if hasattr(entity, 'labels') else [],
                'properties': dict(entity) if hasattr(entity, '__iter__') else {}
            }
        elif hasattr(entity, 'type'):
            return {
                'id': str(entity.element_id) if hasattr(entity, 'element_id') else str(entity.id),
                'type': entity.type,
                'properties': dict(entity) if hasattr(entity, '__iter__') else {}
            }
        return entity

    def _is_json(self, value: str) -> bool:
        """Verifica se string é JSON válido."""
        try:
            json.loads(value)
            return True
        except:
            return False
