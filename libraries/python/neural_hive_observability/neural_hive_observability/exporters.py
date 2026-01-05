"""
Exporters resilientes para Neural Hive-Mind.

Implementa wrappers ao redor dos exporters OpenTelemetry para capturar
exceções durante export sem bloquear operações principais.
"""

import logging
import os
import time
from typing import Optional, Sequence, Dict, Any, TYPE_CHECKING

import grpc

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
        tls_enabled: bool = False,
        tls_cert_path: Optional[str] = None,
        tls_key_path: Optional[str] = None,
        tls_ca_cert_path: Optional[str] = None,
        tls_insecure_skip_verify: bool = False,
        **kwargs
    ):
        """
        Inicializa o exporter resiliente.

        Args:
            endpoint: Endpoint do OTLP collector
            service_name: Nome do serviço para métricas
            insecure: Se deve usar conexão insegura (ignorado se tls_enabled=True)
            headers: Headers customizados (serão sanitizados)
            timeout: Timeout de conexão em segundos
            tls_enabled: Se deve usar TLS para conexão
            tls_cert_path: Caminho para certificado cliente
            tls_key_path: Caminho para chave privada cliente
            tls_ca_cert_path: Caminho para certificado CA raiz
            tls_insecure_skip_verify: Se deve pular verificação de certificado (apenas dev)
            **kwargs: Argumentos adicionais para OTLPSpanExporter
        """
        self._service_name = service_name
        self._endpoint = endpoint
        self._failure_count = 0
        self._success_count = 0
        self._pending_spans_count = 0
        self._tls_enabled = tls_enabled

        # Sanitizar headers
        sanitized_headers = create_sanitized_headers(headers)

        # Criar exporter interno
        try:
            exporter_kwargs = {
                'endpoint': endpoint,
            }

            if sanitized_headers:
                exporter_kwargs['headers'] = sanitized_headers

            if timeout is not None:
                exporter_kwargs['timeout'] = timeout

            # Configurar TLS ou modo inseguro
            if tls_enabled:
                credentials = self._create_tls_credentials(
                    tls_cert_path,
                    tls_key_path,
                    tls_ca_cert_path,
                    tls_insecure_skip_verify
                )
                if credentials is not None:
                    exporter_kwargs['credentials'] = credentials
                    logger.info(
                        f"TLS habilitado para {service_name} "
                        f"(cert: {tls_cert_path}, ca: {tls_ca_cert_path})"
                    )
                else:
                    # TLS foi solicitado mas falhou - NÃO fazer fallback silencioso
                    # para insecure em produção. Isso é um erro de configuração.
                    error_msg = (
                        f"Falha ao configurar TLS para {service_name}. "
                        f"Certificados não encontrados ou inválidos. "
                        f"cert_path={tls_cert_path}, ca_cert_path={tls_ca_cert_path}. "
                        f"Exporter não será inicializado. "
                        f"Para desabilitar TLS, defina OTEL_EXPORTER_TLS_ENABLED=false."
                    )
                    logger.error(error_msg)
                    self._tls_enabled = False
                    self._inner_exporter = None
                    return  # Abort initialization - do not create exporter
            else:
                exporter_kwargs['insecure'] = insecure

            exporter_kwargs.update(kwargs)

            self._inner_exporter = OTLPSpanExporter(**exporter_kwargs)

            tls_status = "TLS habilitado" if self._tls_enabled else "insecure"
            logger.info(
                f"ResilientOTLPSpanExporter inicializado para {service_name} "
                f"com endpoint {endpoint} ({tls_status})"
            )
        except Exception as e:
            logger.error(f"Erro ao criar OTLPSpanExporter interno: {e}")
            self._inner_exporter = None

    def _create_tls_credentials(
        self,
        cert_path: Optional[str],
        key_path: Optional[str],
        ca_cert_path: Optional[str],
        insecure_skip_verify: bool = False
    ) -> Optional[grpc.ChannelCredentials]:
        """
        Cria credenciais TLS para conexão gRPC.

        Args:
            cert_path: Caminho para certificado cliente
            key_path: Caminho para chave privada cliente
            ca_cert_path: Caminho para certificado CA raiz
            insecure_skip_verify: Se deve pular verificação de certificado.
                                  ATENÇÃO: Quando True, cria credenciais TLS sem
                                  validação de CA (aceita qualquer certificado).
                                  Use APENAS em desenvolvimento.

        Returns:
            grpc.ChannelCredentials ou None se falhar
        """
        try:
            root_certificates = None
            private_key = None
            certificate_chain = None

            # Ler certificado CA
            if ca_cert_path:
                if os.path.exists(ca_cert_path):
                    with open(ca_cert_path, 'rb') as f:
                        root_certificates = f.read()
                    logger.debug(f"CA certificate carregado de {ca_cert_path}")
                else:
                    logger.warning(f"CA certificate não encontrado: {ca_cert_path}")
                    if not insecure_skip_verify:
                        return None

            # Ler certificado e chave cliente (mTLS)
            if cert_path and key_path:
                if os.path.exists(cert_path) and os.path.exists(key_path):
                    with open(cert_path, 'rb') as f:
                        certificate_chain = f.read()
                    with open(key_path, 'rb') as f:
                        private_key = f.read()
                    logger.debug(
                        f"Client certificate carregado de {cert_path}, "
                        f"key de {key_path}"
                    )
                else:
                    if not os.path.exists(cert_path):
                        logger.warning(f"Client certificate não encontrado: {cert_path}")
                    if not os.path.exists(key_path):
                        logger.warning(f"Client key não encontrado: {key_path}")

            # Quando insecure_skip_verify=True e não temos CA, criamos credenciais
            # TLS sem validação de CA (aceita qualquer certificado do servidor).
            # Isso é útil para desenvolvimento com certificados auto-assinados.
            if insecure_skip_verify and root_certificates is None:
                logger.warning(
                    "TLS com insecure_skip_verify=True: verificação de certificado "
                    "desabilitada. NÃO USE EM PRODUÇÃO."
                )
                # Criar credenciais sem root certificates - gRPC usará defaults do sistema
                # mas não falhará se o cert não for verificável

            # Criar credenciais
            credentials = grpc.ssl_channel_credentials(
                root_certificates=root_certificates,
                private_key=private_key,
                certificate_chain=certificate_chain
            )

            return credentials

        except Exception as e:
            logger.error(f"Erro ao criar credenciais TLS: {e}")
            return None

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
