"""
Configuração da biblioteca Neural Hive Observability.

Define configurações padronizadas para tracing, métricas, logging e health checks
conforme arquitetura do Neural Hive-Mind.
"""

import os
import uuid
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class ObservabilityConfig:
    """Configuração para observabilidade do Neural Hive-Mind."""

    # Identificação do serviço
    service_name: str
    service_version: str = "unknown"
    service_instance_id: str = ""

    # Metadados Neural Hive-Mind
    neural_hive_component: str = "unknown"
    neural_hive_layer: str = "unknown"
    neural_hive_domain: Optional[str] = None

    # Ambiente
    environment: str = "production"

    # OpenTelemetry
    otel_endpoint: str = "http://opentelemetry-collector:4317"

    # OpenTelemetry TLS Configuration
    otel_tls_enabled: bool = False
    otel_tls_cert_path: Optional[str] = None
    otel_tls_key_path: Optional[str] = None
    otel_tls_ca_cert_path: Optional[str] = None
    otel_tls_insecure_skip_verify: bool = False  # Para desenvolvimento apenas
    # OTEL_EXPORTER_CERTIFICATE - alias for CA cert path (backward compatibility)
    otel_exporter_certificate: Optional[str] = None

    # Métricas Prometheus
    prometheus_port: int = 8000

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Health checks
    enable_health_checks: bool = True

    # Tracing configuration
    trace_batch_size: int = 512
    trace_export_timeout_ms: int = 30000
    trace_schedule_delay_ms: int = 5000

    # Métricas configuration
    metrics_namespace: str = "neural_hive"

    def __post_init__(self):
        """Pós-processamento da configuração."""
        if not self.service_instance_id:
            self.service_instance_id = str(uuid.uuid4())

        # Normalizar valores
        self.environment = self.environment.lower()
        self.log_level = self.log_level.upper()

        # Aplicar overrides de variáveis de ambiente
        self._apply_env_overrides()

        # Resolve OTEL_EXPORTER_CERTIFICATE as alias for CA cert path
        # Priority: otel_tls_ca_cert_path > otel_exporter_certificate
        if not self.otel_tls_ca_cert_path and self.otel_exporter_certificate:
            self.otel_tls_ca_cert_path = self.otel_exporter_certificate

    def _apply_env_overrides(self):
        """Aplica overrides de variáveis de ambiente."""
        env_mappings = {
            "NEURAL_HIVE_COMPONENT": "neural_hive_component",
            "NEURAL_HIVE_LAYER": "neural_hive_layer",
            "NEURAL_HIVE_DOMAIN": "neural_hive_domain",
            "ENVIRONMENT": "environment",
            "LOG_LEVEL": "log_level",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "otel_endpoint",
            "PROMETHEUS_PORT": "prometheus_port",
            # TLS Configuration
            "OTEL_EXPORTER_TLS_ENABLED": "otel_tls_enabled",
            "OTEL_EXPORTER_TLS_CERT_PATH": "otel_tls_cert_path",
            "OTEL_EXPORTER_TLS_KEY_PATH": "otel_tls_key_path",
            "OTEL_EXPORTER_TLS_CA_CERT_PATH": "otel_tls_ca_cert_path",
            "OTEL_EXPORTER_TLS_INSECURE_SKIP_VERIFY": "otel_tls_insecure_skip_verify",
            # OTEL_EXPORTER_CERTIFICATE - alias for CA cert (standard OTEL convention)
            "OTEL_EXPORTER_CERTIFICATE": "otel_exporter_certificate",
        }

        # Campos que devem ser convertidos para inteiro
        int_fields = {"prometheus_port"}
        # Campos que devem ser convertidos para booleano
        bool_fields = {"enable_health_checks", "otel_tls_enabled", "otel_tls_insecure_skip_verify"}

        for env_var, attr_name in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value:
                if attr_name in int_fields:
                    setattr(self, attr_name, int(env_value))
                elif attr_name in bool_fields:
                    setattr(self, attr_name, env_value.lower() in ("true", "1", "yes"))
                else:
                    setattr(self, attr_name, env_value)

    def to_dict(self) -> Dict[str, Any]:
        """Converte configuração para dicionário."""
        return {
            "service": {
                "name": self.service_name,
                "version": self.service_version,
                "instance_id": self.service_instance_id,
            },
            "neural_hive": {
                "component": self.neural_hive_component,
                "layer": self.neural_hive_layer,
                "domain": self.neural_hive_domain,
            },
            "environment": self.environment,
            "otel_endpoint": self.otel_endpoint,
            "prometheus_port": self.prometheus_port,
            "log_level": self.log_level,
            "log_format": self.log_format,
            "enable_health_checks": self.enable_health_checks,
        }

    @property
    def resource_attributes(self) -> Dict[str, str]:
        """Retorna atributos de resource para OpenTelemetry."""
        return {
            "service.name": self.service_name,
            "service.version": self.service_version,
            "service.instance.id": self.service_instance_id,
            "neural.hive.component": self.neural_hive_component,
            "neural.hive.layer": self.neural_hive_layer,
            "neural.hive.domain": self.neural_hive_domain or "unknown",
            "deployment.environment": self.environment,
        }

    @property
    def common_labels(self) -> Dict[str, str]:
        """Retorna labels comuns para métricas."""
        return {
            "neural_hive_component": self.neural_hive_component,
            "neural_hive_layer": self.neural_hive_layer,
            "neural_hive_domain": self.neural_hive_domain or "unknown",
            "environment": self.environment,
            "service_name": self.service_name,
        }