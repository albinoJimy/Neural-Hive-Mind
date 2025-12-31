"""
Exporters resilientes para Neural Hive-Mind.

Implementa wrappers ao redor dos exporters OpenTelemetry para capturar
exceções durante export sem bloquear operações principais.
"""

import logging
import time
from typing import Optional, Sequence, Dict, Any, TYPE_CHECKING

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

if TYPE_CHECKING:
    from .metrics import NeuralHiveMetrics

logger = logging.getLogger(__name__)


# Flag para indicar se métricas foram inicializadas
_metrics_initialized = False


def _get_neural_hive_metrics() -> Optional['NeuralHiveMetrics']:
    """
    Obtém a instância de NeuralHiveMetrics se disponível.

    Returns:
        Instância de NeuralHiveMetrics ou None se não inicializada
    """
    try:
        from .metrics import get_metrics
        return get_metrics()
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"Erro ao obter métricas: {e}")
        return None


def _sanitize_header_value(value: str, max_length: int = 100) -> str:
    """
    Sanitiza valor de header removendo caracteres problemáticos.

    Args:
        value: Valor do header a sanitizar
        max_length: Comprimento máximo do valor

    Returns:
        Valor sanitizado
    """
    if value is None:
        return ""

    if not isinstance(value, str):
        value = str(value)

    # Remover caracteres que podem causar problemas de formatação
    # O bug do OpenTelemetry 1.39.1 está relacionado a % em strings
    problematic_chars = ['%', '{', '}', '\n', '\r', '\t', '\x00']

    sanitized = value
    for char in problematic_chars:
        sanitized = sanitized.replace(char, '')

    # Truncar se muito longo
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
        logger.debug(f"Header value truncado de {len(value)} para {max_length} caracteres")

    return sanitized


def create_sanitized_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Cria dicionário de headers com valores sanitizados.

    Args:
        headers: Headers originais

    Returns:
        Headers sanitizados
    """
    if not headers:
        return {}

    sanitized = {}
    for key, value in headers.items():
        original_value = value
        sanitized_value = _sanitize_header_value(value)

        if original_value != sanitized_value:
            logger.warning(
                f"Header '{key}' foi sanitizado: '{original_value[:50]}...' -> '{sanitized_value[:50]}...'"
            )

        sanitized[key] = sanitized_value

    return sanitized


class ResilientOTLPSpanExporter(SpanExporter):
    """
    Wrapper resiliente ao redor do OTLPSpanExporter.

    Captura exceções durante export sem bloquear operações principais,
    registra métricas de falhas e fornece logging detalhado.

    Este wrapper foi criado para contornar o bug do OpenTelemetry 1.39.1
    que causa TypeError durante formatação de strings em headers customizados.

    As métricas são registradas usando NeuralHiveMetrics para garantir que
    apareçam no endpoint /metrics do servidor Prometheus.
    """

    def __init__(
        self,
        endpoint: str,
        service_name: str = "unknown",
        insecure: bool = True,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        **kwargs
    ):
        """
        Inicializa o exporter resiliente.

        Args:
            endpoint: Endpoint do OTLP collector
            service_name: Nome do serviço para métricas
            insecure: Se deve usar conexão insegura
            headers: Headers customizados (serão sanitizados)
            timeout: Timeout de conexão em segundos
            **kwargs: Argumentos adicionais para OTLPSpanExporter
        """
        self._service_name = service_name
        self._endpoint = endpoint
        self._failure_count = 0
        self._success_count = 0
        self._pending_spans_count = 0

        # Sanitizar headers
        sanitized_headers = create_sanitized_headers(headers)

        # Criar exporter interno
        try:
            exporter_kwargs = {
                'endpoint': endpoint,
                'insecure': insecure,
            }

            if sanitized_headers:
                exporter_kwargs['headers'] = sanitized_headers

            if timeout is not None:
                exporter_kwargs['timeout'] = timeout

            exporter_kwargs.update(kwargs)

            self._inner_exporter = OTLPSpanExporter(**exporter_kwargs)

            logger.info(
                f"ResilientOTLPSpanExporter inicializado para {service_name} "
                f"com endpoint {endpoint}"
            )
        except Exception as e:
            logger.error(f"Erro ao criar OTLPSpanExporter interno: {e}")
            self._inner_exporter = None

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """
        Exporta spans de forma resiliente.

        Args:
            spans: Sequência de spans a exportar

        Returns:
            SpanExportResult.SUCCESS ou SpanExportResult.FAILURE
        """
        if not self._inner_exporter:
            logger.warning("Exporter interno não disponível, descartando spans")
            return SpanExportResult.FAILURE

        if not spans:
            return SpanExportResult.SUCCESS

        span_count = len(spans)
        start_time = time.monotonic()

        # Atualizar gauge de tamanho da fila com o batch atual
        self._pending_spans_count = span_count
        self._update_queue_size_gauge(span_count)

        try:
            result = self._inner_exporter.export(spans)

            duration = time.monotonic() - start_time
            self._success_count += 1

            # Registrar métricas de sucesso
            self._record_success_metrics(duration)

            # Após export bem-sucedido, fila está vazia
            self._pending_spans_count = 0
            self._update_queue_size_gauge(0)

            if result == SpanExportResult.SUCCESS:
                logger.debug(
                    f"Export de {span_count} spans bem-sucedido em {duration:.3f}s"
                )

            return result

        except TypeError as e:
            # Bug específico do OpenTelemetry 1.39.1 com formatação de strings
            duration = time.monotonic() - start_time
            self._failure_count += 1

            self._record_failure_metrics("TypeError", duration)

            logger.error(
                f"TypeError durante export de spans (bug OpenTelemetry 1.39.1): {e}. "
                f"Spans: {span_count}, Endpoint: {self._endpoint}, "
                f"Service: {self._service_name}. "
                f"Total de falhas: {self._failure_count}"
            )

            return SpanExportResult.FAILURE

        except Exception as e:
            duration = time.monotonic() - start_time
            self._failure_count += 1

            error_type = type(e).__name__
            self._record_failure_metrics(error_type, duration)

            logger.error(
                f"Exceção durante export de spans: {error_type}: {e}. "
                f"Spans: {span_count}, Endpoint: {self._endpoint}, "
                f"Service: {self._service_name}. "
                f"Total de falhas: {self._failure_count}"
            )

            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        """Encerra o exporter de forma limpa."""
        if self._inner_exporter:
            try:
                self._inner_exporter.shutdown()
                logger.info(
                    f"ResilientOTLPSpanExporter encerrado. "
                    f"Sucessos: {self._success_count}, Falhas: {self._failure_count}"
                )
            except Exception as e:
                logger.warning(f"Erro durante shutdown do exporter: {e}")

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """
        Força flush de spans pendentes.

        Args:
            timeout_millis: Timeout em milissegundos

        Returns:
            True se flush foi bem-sucedido
        """
        if not self._inner_exporter:
            return False

        try:
            return self._inner_exporter.force_flush(timeout_millis)
        except Exception as e:
            logger.warning(f"Erro durante force_flush: {e}")
            return False

    def _record_success_metrics(self, duration: float) -> None:
        """Registra métricas de sucesso usando NeuralHiveMetrics."""
        metrics = _get_neural_hive_metrics()
        if metrics is None:
            return

        try:
            metrics.increment_span_export_success(self._endpoint)
            metrics.observe_span_export_duration(duration, self._endpoint, "success")
        except Exception as e:
            logger.debug(f"Erro ao registrar métricas de sucesso: {e}")

    def _record_failure_metrics(self, error_type: str, duration: float) -> None:
        """Registra métricas de falha usando NeuralHiveMetrics."""
        metrics = _get_neural_hive_metrics()
        if metrics is None:
            return

        try:
            metrics.increment_span_export_failures(error_type, self._endpoint)
            metrics.observe_span_export_duration(duration, self._endpoint, "failure")
        except Exception as e:
            logger.debug(f"Erro ao registrar métricas de falha: {e}")

    def _update_queue_size_gauge(self, size: int) -> None:
        """Atualiza gauge de tamanho da fila de spans pendentes."""
        metrics = _get_neural_hive_metrics()
        if metrics is None:
            return

        try:
            metrics.set_span_export_queue_size(size)
        except Exception as e:
            logger.debug(f"Erro ao atualizar gauge de tamanho da fila: {e}")

    @property
    def failure_count(self) -> int:
        """Retorna contagem de falhas de export."""
        return self._failure_count

    @property
    def success_count(self) -> int:
        """Retorna contagem de exports bem-sucedidos."""
        return self._success_count
