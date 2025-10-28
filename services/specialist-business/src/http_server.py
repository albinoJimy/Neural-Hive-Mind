"""
Servidor HTTP para health checks e métricas.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import structlog
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

logger = structlog.get_logger()


class HealthHandler(BaseHTTPRequestHandler):
    """Handler HTTP para health checks e métricas."""

    specialist = None
    config = None

    def log_message(self, format, *args):
        """Override para usar structlog."""
        logger.debug("HTTP request", method=self.command, path=self.path)

    def do_GET(self):
        """Handler para requisições GET."""
        if self.path == '/health':
            self._handle_health()
        elif self.path == '/ready':
            self._handle_ready()
        elif self.path == '/metrics':
            self._handle_metrics()
        else:
            self.send_error(404, "Not Found")

    def _handle_health(self):
        """Health check básico (liveness probe)."""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            response = {
                'status': 'healthy',
                'specialist_type': self.specialist.specialist_type,
                'version': self.specialist.version
            }

            self.wfile.write(json.dumps(response).encode())

            logger.debug("Health check passed")

        except Exception as e:
            logger.error("Health check failed", error=str(e))
            self.send_error(500, "Internal Server Error")

    def _handle_ready(self):
        """Readiness check (verifica dependências)."""
        try:
            # Verificar saúde do especialista (inclui dependências)
            health_response = self.specialist.health_check()

            is_ready = health_response['status'] == 'SERVING'
            status_code = 200 if is_ready else 503

            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            response = {
                'ready': is_ready,
                'specialist_type': self.specialist.specialist_type,
                'details': health_response.get('details', {})
            }

            self.wfile.write(json.dumps(response).encode())

            logger.debug("Readiness check", ready=is_ready)

        except Exception as e:
            logger.error("Readiness check failed", error=str(e))
            self.send_error(500, "Internal Server Error")

    def _handle_metrics(self):
        """Endpoint de métricas Prometheus."""
        try:
            # Gerar métricas no formato Prometheus
            metrics = generate_latest()

            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()

            self.wfile.write(metrics)

            logger.debug("Metrics served")

        except Exception as e:
            logger.error("Failed to serve metrics", error=str(e))
            self.send_error(500, "Internal Server Error")


def create_http_server(specialist, config):
    """
    Cria servidor HTTP para health checks e métricas.

    Args:
        specialist: Instância do especialista
        config: Configuração

    Returns:
        HTTPServer configurado
    """
    logger.info(
        "Creating HTTP server",
        specialist_type=specialist.specialist_type,
        port=config.http_port
    )

    # Configurar handler com referências ao especialista
    HealthHandler.specialist = specialist
    HealthHandler.config = config

    # Criar servidor
    server = HTTPServer(('0.0.0.0', config.http_port), HealthHandler)

    logger.info(
        "HTTP server created",
        specialist_type=specialist.specialist_type,
        port=config.http_port
    )

    return server
