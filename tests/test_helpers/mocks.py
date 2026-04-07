"""
Mock helpers para testes.

Este módulo fornece classes mock reutilizáveis e fáceis de configurar
para testes de componentes do Neural Hive Mind.
"""

from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4
import json


# =============================================================================
# Kafka Mocks
# =============================================================================


class MockKafkaMessage:
    """Mock de mensagem Kafka para testes de consumers."""

    def __init__(
        self,
        value: Union[str, bytes, dict],
        key: Optional[Union[str, bytes]] = None,
        topic: str = "test-topic",
        partition: int = 0,
        offset: int = 0,
        headers: Optional[Dict[str, bytes]] = None,
    ):
        """
        Inicializa uma mensagem Kafka mock.

        Args:
            value: Conteúdo da mensagem
            key: Chave da mensagem
            topic: Tópico de origem
            partition: Partição
            offset: Offset
            headers: Headers adicionais
        """
        self.topic = topic
        self.partition = partition
        self.offset = offset
        self.key = key
        self.headers = headers or {}

        # Converter dict para JSON bytes se necessário
        if isinstance(value, dict):
            self.value = json.dumps(value).encode("utf-8")
        elif isinstance(value, str):
            self.value = value.encode("utf-8")
        else:
            self.value = value

    def set_topic(self, topic: str) -> None:
        """Define o tópico da mensagem."""
        self.topic = topic

    def set_value(self, value: bytes) -> None:
        """Define o valor da mensagem."""
        self.value = value

    def error(self) -> Optional[Exception]:
        """Retorna erro se existir."""
        return None

    def value(self) -> bytes:
        """Retorna o valor da mensagem."""
        return self.value

    def key(self) -> Optional[bytes]:
        """Retorna a chave da mensagem."""
        return self.key if isinstance(self.key, bytes) else self.key.encode() if self.key else None


class MockKafkaProducer:
    """Mock de Producer Kafka para testes."""

    def __init__(self):
        """Inicializa o producer mock."""
        self.messages: List[Dict[str, Any]] = []
        self.flush_called = False

    async def produce(
        self,
        topic: str,
        value: Union[str, bytes, dict],
        key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        on_delivery: Optional[Callable] = None,
    ) -> bool:
        """
        Mock do método produce.

        Args:
            topic: Tópico destino
            value: Conteúdo da mensagem
            key: Chave da mensagem
            headers: Headers
            on_delivery: Callback de entrega

        Returns:
            True se enviado com sucesso
        """
        self.messages.append(
            {
                "topic": topic,
                "value": value,
                "key": key,
                "headers": headers,
            }
        )

        if on_delivery:
            on_delivery(None, None)

        return True

    async def flush(self, timeout: float = 10.0) -> bool:
        """Mock do método flush."""
        self.flush_called = True
        return True

    def poll(self, timeout: float = 0.0) -> int:
        """Mock do método poll."""
        return 0

    def get_messages(self) -> List[Dict[str, Any]]:
        """Retorna todas as mensagens enviadas."""
        return self.messages

    def clear(self) -> None:
        """Limpa o histórico de mensagens."""
        self.messages.clear()
        self.flush_called = False


class MockKafkaConsumer:
    """Mock de Consumer Kafka para testes."""

    def __init__(
        self,
        messages: Optional[List[MockKafkaMessage]] = None,
        subscribe_error: Optional[Exception] = None,
    ):
        """
        Inicializa o consumer mock.

        Args:
            messages: Lista de mensagens para retornar em poll
            subscribe_error: Erro a lançar no subscribe (opcional)
        """
        self.messages: List[MockKafkaMessage] = messages or []
        self.message_index = 0
        self.subscribed_topics: List[str] = []
        self.committed_offsets: Dict[str, int] = {}
        self.subscribe_error = subscribe_error
        self.closed = False

    def subscribe(self, topics: Union[List[str], str]) -> None:
        """Mock do método subscribe."""
        if self.subscribe_error:
            raise self.subscribe_error

        if isinstance(topics, str):
            topics = [topics]
        self.subscribed_topics.extend(topics)

    async def poll(self, timeout: float = 1.0) -> Optional[MockKafkaMessage]:
        """
        Mock do método poll.

        Args:
            timeout: Timeout em segundos

        Returns:
            Mensagem ou None se não houver mais mensagens
        """
        if self.message_index < len(self.messages):
            msg = self.messages[self.message_index]
            self.message_index += 1
            return msg
        return None

    async def commit(self, message: Optional[MockKafkaMessage] = None) -> None:
        """Mock do método commit."""
        if message:
            topic = message.topic
            offset = message.offset
            self.committed_offsets[topic] = offset

    async def close(self) -> None:
        """Mock do método close."""
        self.closed = True

    def get_subscribed_topics(self) -> List[str]:
        """Retorna tópicos subscritos."""
        return self.subscribed_topics


# =============================================================================
# Database Mocks
# =============================================================================


class MockMongoDBCollection:
    """Mock de coleção MongoDB para testes."""

    def __init__(self):
        """Inicializa a coleção mock."""
        self._data: Dict[str, Dict[str, Any]] = {}
        self.find_filters: List[Dict[str, Any]] = []
        self.insert_calls: List[Dict[str, Any]] = []
        self.update_calls: List[Dict[str, Any]] = []
        self.delete_calls: List[Dict[str, Any]] = []

    async def insert_one(self, document: Dict[str, Any]) -> Mock:
        """Mock do insert_one."""
        doc_id = document.get("_id", str(uuid4()))
        self._data[doc_id] = document
        self.insert_calls.append(document)

        result = Mock()
        result.inserted_id = doc_id
        result.acknowledged = True
        return result

    async def find_one(
        self,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mock do find_one."""
        self.find_filters.append(filter)

        for doc in self._data.values():
            match = True
            for key, value in filter.items():
                if doc.get(key) != value:
                    match = False
                    break
            if match:
                if projection:
                    return {
                        k: v for k, v in doc.items() if k in projection or projection.get(k) != 0
                    }
                return doc
        return None

    async def find(
        self,
        filter: Dict[str, Any] = None,
        projection: Optional[Dict[str, int]] = None,
        limit: int = 0,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Mock do find (async generator)."""
        self.find_filters.append(filter or {})

        count = 0
        for doc in self._data.values():
            if limit > 0 and count >= limit:
                break

            match = True
            for key, value in (filter or {}).items():
                if doc.get(key) != value:
                    match = False
                    break

            if match:
                result = doc
                if projection:
                    result = {
                        k: v for k, v in doc.items() if k in projection or projection.get(k) != 0
                    }
                yield result
                count += 1

    async def update_one(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
    ) -> Mock:
        """Mock do update_one."""
        self.update_calls.append({"filter": filter, "update": update})

        result = Mock()
        result.matched_count = 0
        result.modified_count = 0
        result.acknowledged = True

        for doc_id, doc in self._data.items():
            match = True
            for key, value in filter.items():
                if doc.get(key) != value:
                    match = False
                    break

            if match:
                result.matched_count = 1
                if "$set" in update:
                    doc.update(update["$set"])
                    result.modified_count = 1
                break

        return result

    async def delete_one(self, filter: Dict[str, Any]) -> Mock:
        """Mock do delete_one."""
        self.delete_calls.append(filter)

        result = Mock()
        result.deleted_count = 0
        result.acknowledged = True

        for doc_id in list(self._data.keys()):
            doc = self._data[doc_id]
            match = True
            for key, value in filter.items():
                if doc.get(key) != value:
                    match = False
                    break

            if match:
                del self._data[doc_id]
                result.deleted_count = 1
                break

        return result

    async def count_documents(self, filter: Dict[str, Any] = None) -> int:
        """Mock do count_documents."""
        count = 0
        for doc in self._data.values():
            match = True
            for key, value in (filter or {}).items():
                if doc.get(key) != value:
                    match = False
                    break
            if match:
                count += 1
        return count

    def get_data(self) -> Dict[str, Dict[str, Any]]:
        """Retorna todos os dados armazenados."""
        return self._data.copy()

    def clear(self) -> None:
        """Limpa todos os dados."""
        self._data.clear()
        self.find_filters.clear()
        self.insert_calls.clear()
        self.update_calls.clear()
        self.delete_calls.clear()


class MockMongoDBClient:
    """Mock de cliente MongoDB para testes."""

    def __init__(self):
        """Inicializa o cliente mock."""
        self.collections: Dict[str, MockMongoDBCollection] = {}
        self.closed = False

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()

    def get_database(self, name: str) -> "MockMongoDBClient":
        """Retorna/mocka a database."""
        return self

    def get_collection(self, name: str) -> MockMongoDBCollection:
        """Retorna/mocka uma coleção."""
        if name not in self.collections:
            self.collections[name] = MockMongoDBCollection()
        return self.collections[name]

    async def close(self) -> None:
        """Fecha o cliente mock."""
        self.closed = True

    def get_collection_mock(self, name: str) -> MockMongoDBCollection:
        """Retorna o mock de uma coleção específica."""
        return self.collections.get(name, MockMongoDBCollection())


class MockRedisClient:
    """Mock de cliente Redis para testes."""

    def __init__(self):
        """Inicializa o cliente mock."""
        self._data: Dict[str, Any] = {}
        self._ttl: Dict[str, int] = {}
        self.get_calls: List[str] = []
        self.set_calls: List[Dict[str, Any]] = []

    async def get(self, key: str) -> Optional[bytes]:
        """Mock do GET."""
        self.get_calls.append(key)
        value = self._data.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return value.encode("utf-8")
        return value

    async def set(
        self,
        key: str,
        value: Union[str, bytes],
        ex: Optional[int] = None,
    ) -> bool:
        """Mock do SET."""
        self.set_calls.append({"key": key, "value": value, "ex": ex})

        if isinstance(value, bytes):
            value = value.decode("utf-8")
        self._data[key] = value

        if ex:
            self._ttl[key] = ex

        return True

    async def setex(self, key: str, time: int, value: Union[str, bytes]) -> bool:
        """Mock do SETEX."""
        return await self.set(key, value, ex=time)

    async def delete(self, *keys: str) -> int:
        """Mock do DELETE."""
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                if key in self._ttl:
                    del self._ttl[key]
                count += 1
        return count

    async def exists(self, *keys: str) -> int:
        """Mock do EXISTS."""
        return sum(1 for key in keys if key in self._data)

    async def expire(self, key: str, time: int) -> bool:
        """Mock do EXPIRE."""
        if key in self._data:
            self._ttl[key] = time
            return True
        return False

    async def incr(self, key: str) -> int:
        """Mock do INCR."""
        current = int(self._data.get(key, 0))
        self._data[key] = str(current + 1)
        return current + 1

    async def decr(self, key: str) -> int:
        """Mock do DECR."""
        current = int(self._data.get(key, 0))
        self._data[key] = str(current - 1)
        return current - 1

    def get_data(self) -> Dict[str, Any]:
        """Retorna todos os dados armazenados."""
        return self._data.copy()

    def clear(self) -> None:
        """Limpa todos os dados."""
        self._data.clear()
        self._ttl.clear()
        self.get_calls.clear()
        self.set_calls.clear()


# =============================================================================
# Temporal Mocks
# =============================================================================


class MockTemporalWorkflowHandle:
    """Mock de handle de workflow Temporal."""

    def __init__(self, workflow_id: str):
        """Inicializa o handle mock."""
        self.workflow_id = workflow_id
        self.signals_sent: List[Dict[str, Any]] = []
        self.queries_made: List[Dict[str, Any]] = []
        self._result = None

    async def signal(
        self,
        signal_name: str,
        arg: Any = None,
    ) -> None:
        """Envia um sinal para o workflow."""
        self.signals_sent.append(
            {
                "signal_name": signal_name,
                "arg": arg,
            }
        )

    async def query(self, query_name: str, arg: Any = None) -> Any:
        """Consulta o workflow."""
        self.queries_made.append(
            {
                "query_name": query_name,
                "arg": arg,
            }
        )
        return self._result

    def set_result(self, result: Any) -> None:
        """Define o resultado a retornar em queries."""
        self._result = result


class MockTemporalClient:
    """Mock de cliente Temporal para testes."""

    def __init__(self):
        """Inicializa o cliente mock."""
        self.workflows_started: List[Dict[str, Any]] = []
        self.handles: Dict[str, MockTemporalWorkflowHandle] = {}

    async def start_workflow(
        self,
        workflow: type,
        args: List[Any] = None,
        id: str = None,
        task_queue: str = "default",
    ) -> Mock:
        """
        Inicia um workflow mock.

        Returns:
            Mock com id do workflow
        """
        workflow_id = id or f"workflow-{uuid4().hex[:8]}"
        self.workflows_started.append(
            {
                "workflow": workflow.__name__ if workflow else None,
                "args": args,
                "id": workflow_id,
                "task_queue": task_queue,
            }
        )

        handle = MockTemporalWorkflowHandle(workflow_id)
        self.handles[workflow_id] = handle

        result = Mock()
        result.id = workflow_id
        return result

    def get_workflow_handle(self, workflow_id: str) -> MockTemporalWorkflowHandle:
        """Retorna um handle para o workflow."""
        if workflow_id not in self.handles:
            self.handles[workflow_id] = MockTemporalWorkflowHandle(workflow_id)
        return self.handles[workflow_id]

    def get_started_workflows(self) -> List[Dict[str, Any]]:
        """Retorna workflows iniciados."""
        return self.workflows_started.copy()


# =============================================================================
# gRPC Mocks
# =============================================================================


class MockGRPCChannel:
    """Mock de canal gRPC."""

    def __init__(self):
        """Inicializa o canal mock."""
        self.closed = False

    def close(self) -> None:
        """Fecha o canal."""
        self.closed = True

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class MockGRPCServer:
    """Mock de servidor gRPC."""

    def __init__(self, port: int = 50051):
        """Inicializa o servidor mock."""
        self.port = port
        self.started = False
        self.stopped = False
        self.services: List[Any] = []

    def add_insecure_port(self, address: str) -> int:
        """Adiciona porta insegura."""
        return self.port

    def start(self) -> None:
        """Inicia o servidor."""
        self.started = True

    def stop(self, grace: float = None) -> None:
        """Para o servidor."""
        self.stopped = True

    def add_servicer(self, servicer: Any) -> None:
        """Adiciona um servicer."""
        self.services.append(servicer)


# =============================================================================
# HTTP Client Mocks
# =============================================================================


class MockHTTPResponse:
    """Mock de resposta HTTP."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: Any = None,
        text: str = "",
        headers: Dict[str, str] = None,
    ):
        """Inicializa a resposta mock."""
        self.status_code = status_code
        self._json_data = json_data
        self._text = text
        self.headers = headers or {}

    async def json(self) -> Any:
        """Retorna dados JSON."""
        return self._json_data

    async def text(self) -> str:
        """Retorna texto."""
        return self._text

    def raise_for_status(self) -> None:
        """Levanta exceção se status for erro."""
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class MockHTTPClient:
    """Mock de cliente HTTP."""

    def __init__(self):
        """Inicializa o cliente mock."""
        self.get_calls: List[Dict[str, Any]] = []
        self.post_calls: List[Dict[str, Any]] = []
        self.put_calls: List[Dict[str, Any]] = []
        self.delete_calls: List[Dict[str, Any]] = []
        self._response_to_return: Optional[MockHTTPResponse] = None

    def set_response(self, response: MockHTTPResponse) -> None:
        """Define a resposta a retornar."""
        self._response_to_return = response

    async def get(self, url: str, **kwargs) -> MockHTTPResponse:
        """Mock do GET."""
        self.get_calls.append({"url": url, **kwargs})
        return self._response_to_return or MockHTTPResponse()

    async def post(self, url: str, **kwargs) -> MockHTTPResponse:
        """Mock do POST."""
        self.post_calls.append({"url": url, **kwargs})
        return self._response_to_return or MockHTTPResponse()

    async def put(self, url: str, **kwargs) -> MockHTTPResponse:
        """Mock do PUT."""
        self.put_calls.append({"url": url, **kwargs})
        return self._response_to_return or MockHTTPResponse()

    async def delete(self, url: str, **kwargs) -> MockHTTPResponse:
        """Mock do DELETE."""
        self.delete_calls.append({"url": url, **kwargs})
        return self._response_to_return or MockHTTPResponse()
