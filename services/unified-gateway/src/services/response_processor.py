"""Response Processor para formatação unificada e eventos Kafka."""

import logging
import json
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer

from src.config.settings import get_settings
from src.models.classification import FlowType
from src.models.response import KafkaEvent, ResponseStatus, UnifiedResponse

logger = logging.getLogger(__name__)


class ResponseProcessor:
    """
    Processa respostas dos gateways downstream.

    Responsabilidades:
    1. Formatar resposta unificada
    2. Publicar eventos Kafka para rastreamento
    3. Adicionar metadados de tracing
    4. Calcular tempo de processamento
    """

    def __init__(self):
        """Inicializa o Response Processor."""
        self._kafka_producer: AIOKafkaProducer | None = None
        self._kafka_connected = False

    async def _get_kafka_producer(self) -> AIOKafkaProducer | None:
        """Obtém ou cria producer Kafka."""
        settings = get_settings()

        if not settings.KAFKA_ENABLED:
            return None

        if self._kafka_producer is None or not self._kafka_connected:
            try:
                self._kafka_producer = AIOKafkaProducer(
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=str.encode,
                    client_id="unified-gateway",
                    compression_type="snappy",
                    linger_ms=10,  # Batch messages
                )
                await self._kafka_producer.start()
                self._kafka_connected = True
                logger.info("Kafka producer connected")
            except Exception as e:
                logger.warning(f"Failed to connect to Kafka: {e}")
                self._kafka_connected = False
                return None

        return self._kafka_producer

    async def format_response(
        self,
        request_id: str,
        flow_type: FlowType,
        status_code: int,
        body: bytes | None,
        headers: dict[str, str],
        processing_time_ms: int,
        gateway_used: str | None = None,
        fallback_used: bool = False,
        original_flow_type: FlowType | None = None,
    ) -> UnifiedResponse:
        """
        Formata resposta do gateway em formato unificado.

        Args:
            request_id: ID único do request
            flow_type: Flow type que processou
            status_code: HTTP status code
            body: Corpo da resposta (bytes)
            headers: Headers da resposta
            processing_time_ms: Tempo de processamento
            gateway_used: Gateway usado (para debugging)
            fallback_used: Se fallback foi usado
            original_flow_type: Flow type original antes do fallback

        Returns:
            UnifiedResponse formatada
        """
        # Determinar status
        if 200 <= status_code < 300:
            status = ResponseStatus.SUCCESS
        elif 400 <= status_code < 500:
            status = ResponseStatus.ERROR
        elif status_code == 599 or status_code == 504:
            status = ResponseStatus.TIMEOUT
        else:
            status = ResponseStatus.ERROR

        # Parse body como JSON se possível
        data = None
        error = None

        if body:
            try:
                data = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Se não for JSON, tratar como texto ou erro
                if status == ResponseStatus.ERROR:
                    error = body.decode("utf-8", errors="replace")[:500]
                else:
                    data = {"raw": body.decode("utf-8", errors="replace")}

        # Extrair trace_id dos headers
        trace_id = headers.get("traceparent", headers.get("x-trace-id"))

        return UnifiedResponse(
            status=status,
            flow_type=flow_type.value,
            request_id=request_id,
            processing_time_ms=processing_time_ms,
            data=data,
            error=error,
            gateway_used=gateway_used,
            trace_id=trace_id,
            fallback_used=fallback_used,
            original_flow_type=original_flow_type.value if original_flow_type else None,
        )

    async def publish_event(
        self,
        request_id: str,
        flow_type: FlowType,
        status: ResponseStatus,
        processing_time_ms: int,
        tenant_id: str | None = None,
        user_id: str | None = None,
        gateway_used: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """
        Publica evento Kafka de rastreamento.

        Args:
            request_id: ID único do request
            flow_type: Flow type processado
            status: Status da resposta
            processing_time_ms: Tempo de processamento
            tenant_id: Tenant ID (opcional)
            user_id: User ID (opcional)
            gateway_used: Gateway usado
            error_message: Mensagem de erro (se houver)

        Returns:
            True se evento publicado com sucesso
        """
        producer = await self._get_kafka_producer()
        if producer is None:
            return False

        settings = get_settings()

        event = KafkaEvent(
            event_type="request_completed"
            if status == ResponseStatus.SUCCESS
            else "request_failed",
            request_id=request_id,
            flow_type=flow_type.value,
            status=status,
            tenant_id=tenant_id,
            user_id=user_id,
            processing_time_ms=processing_time_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gateway_used=gateway_used,
            error_message=error_message,
        )

        topic = f"{settings.KAFKA_TOPIC_PREFIX}gateway_events"

        try:
            await producer.send_and_wait(
                topic,
                value=event.model_dump(),
                key=request_id,
            )
            logger.debug(f"Published event to {topic}: {request_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to publish event to Kafka: {e}")
            return False

    async def process_and_publish(
        self,
        request_id: str,
        flow_type: FlowType,
        status_code: int,
        body: bytes | None,
        headers: dict[str, str],
        processing_time_ms: int,
        tenant_id: str | None = None,
        user_id: str | None = None,
        gateway_used: str | None = None,
        fallback_used: bool = False,
        original_flow_type: FlowType | None = None,
    ) -> tuple[UnifiedResponse, bool]:
        """
        Processa resposta e publica evento Kafka.

        Args:
            ... (mesmos parâmetros que format_response + publish_event)

        Returns:
            Tuple (UnifiedResponse, evento_publicado)
        """
        # Formatar resposta
        response = await self.format_response(
            request_id=request_id,
            flow_type=flow_type,
            status_code=status_code,
            body=body,
            headers=headers,
            processing_time_ms=processing_time_ms,
            gateway_used=gateway_used,
            fallback_used=fallback_used,
            original_flow_type=original_flow_type,
        )

        # Publicar evento
        event_published = await self.publish_event(
            request_id=request_id,
            flow_type=flow_type,
            status=response.status,
            processing_time_ms=processing_time_ms,
            tenant_id=tenant_id,
            user_id=user_id,
            gateway_used=gateway_used,
            error_message=response.error,
        )

        return response, event_published

    async def close(self):
        """Fecha recursos."""
        if self._kafka_producer and self._kafka_connected:
            await self._kafka_producer.stop()
            self._kafka_connected = False
            logger.info("Kafka producer closed")


# Singleton global
_response_processor: ResponseProcessor | None = None


def get_response_processor() -> ResponseProcessor:
    """Obtém ou cria o singleton do Response Processor."""
    global _response_processor
    if _response_processor is None:
        _response_processor = ResponseProcessor()
    return _response_processor
