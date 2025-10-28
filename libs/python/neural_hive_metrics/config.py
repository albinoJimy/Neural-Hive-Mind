"""
Configuration for Neural Hive-Mind Metrics

Gerencia configuração centralizada para métricas, incluindo exemplars,
correlação e endpoints de exportação.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse


@dataclass
class MetricsConfig:
    """Configuração principal para métricas Neural Hive-Mind."""

    # Configurações básicas
    service_name: str = "neural-hive-service"
    service_version: str = "1.0.0"
    environment: str = "production"

    # Configurações de coleta
    metrics_port: int = 8080
    metrics_path: str = "/metrics"
    enable_exemplars: bool = True
    exemplar_sample_rate: float = 1.0

    # Configurações de correlação
    enable_correlation: bool = True
    correlation_headers: Dict[str, str] = field(default_factory=lambda: {
        "intent_id": "X-Neural-Hive-Intent-ID",
        "plan_id": "X-Neural-Hive-Plan-ID",
        "domain": "X-Neural-Hive-Domain",
        "user_id": "X-Neural-Hive-User-ID",
    })

    # Configurações de baggage para OpenTelemetry
    baggage_keys: Dict[str, str] = field(default_factory=lambda: {
        "intent_id": "neural.hive.intent.id",
        "plan_id": "neural.hive.plan.id",
        "domain": "neural.hive.domain",
        "user_id": "neural.hive.user.id",
    })

    # Endpoints de exportação
    prometheus_pushgateway_url: Optional[str] = None
    otel_exporter_otlp_endpoint: Optional[str] = None
    jaeger_agent_host: Optional[str] = None
    jaeger_agent_port: int = 6831

    # Configurações de performance
    metrics_cache_ttl: int = 30  # segundos
    batch_export_timeout: int = 5000  # ms
    max_export_batch_size: int = 512

    # Labels padrão
    default_labels: Dict[str, str] = field(default_factory=dict)

    # Configurações específicas do Neural Hive-Mind
    neural_hive_config: Dict[str, Any] = field(default_factory=lambda: {
        "slo_targets": {
            "barramento_latency_ms": 150,
            "availability_percent": 99.9,
            "plan_generation_ms": 120,
            "capture_latency_ms": 200,
        },
        "error_budget": {
            "burn_rate_fast": 14.4,  # 1 hour
            "burn_rate_slow": 1.0,   # 6 hours
        },
        "sampling": {
            "default_rate": 0.1,
            "high_value_rate": 1.0,
            "error_rate": 1.0,
        }
    })

    def __post_init__(self):
        """Pós-processamento da configuração."""
        # Aplicar configurações de ambiente
        self._load_from_environment()

        # Validar configuração
        self._validate_config()

        # Adicionar labels padrão
        self._setup_default_labels()

    def _load_from_environment(self):
        """Carrega configurações de variáveis de ambiente."""
        # Configurações básicas
        self.service_name = os.getenv("NEURAL_HIVE_SERVICE_NAME", self.service_name)
        self.service_version = os.getenv("NEURAL_HIVE_SERVICE_VERSION", self.service_version)
        self.environment = os.getenv("NEURAL_HIVE_ENVIRONMENT", self.environment)

        # Configurações de métricas
        self.metrics_port = int(os.getenv("METRICS_PORT", self.metrics_port))
        self.metrics_path = os.getenv("METRICS_PATH", self.metrics_path)

        # Exemplars e correlação
        self.enable_exemplars = os.getenv("ENABLE_EXEMPLARS", "true").lower() == "true"
        self.enable_correlation = os.getenv("ENABLE_CORRELATION", "true").lower() == "true"
        self.exemplar_sample_rate = float(os.getenv("EXEMPLAR_SAMPLE_RATE", self.exemplar_sample_rate))

        # Endpoints
        self.prometheus_pushgateway_url = os.getenv("PROMETHEUS_PUSHGATEWAY_URL")
        self.otel_exporter_otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        self.jaeger_agent_host = os.getenv("JAEGER_AGENT_HOST")

        if os.getenv("JAEGER_AGENT_PORT"):
            self.jaeger_agent_port = int(os.getenv("JAEGER_AGENT_PORT"))

        # Configurações de correlação customizadas
        for key, default_header in self.correlation_headers.items():
            env_key = f"CORRELATION_HEADER_{key.upper()}"
            if os.getenv(env_key):
                self.correlation_headers[key] = os.getenv(env_key)

    def _validate_config(self):
        """Valida a configuração."""
        if not self.service_name:
            raise ValueError("service_name é obrigatório")

        if self.metrics_port < 1 or self.metrics_port > 65535:
            raise ValueError("metrics_port deve estar entre 1 e 65535")

        if self.exemplar_sample_rate < 0.0 or self.exemplar_sample_rate > 1.0:
            raise ValueError("exemplar_sample_rate deve estar entre 0.0 e 1.0")

        # Validar URLs se fornecidas
        if self.prometheus_pushgateway_url:
            parsed = urlparse(self.prometheus_pushgateway_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("prometheus_pushgateway_url deve ser uma URL válida")

        if self.otel_exporter_otlp_endpoint:
            parsed = urlparse(self.otel_exporter_otlp_endpoint)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("otel_exporter_otlp_endpoint deve ser uma URL válida")

    def _setup_default_labels(self):
        """Configura labels padrão."""
        self.default_labels.update({
            "service_name": self.service_name,
            "service_version": self.service_version,
            "environment": self.environment,
        })

        # Adicionar labels específicos do Neural Hive-Mind
        if "neural_hive" not in self.service_name.lower():
            self.default_labels["neural_hive_component"] = self.service_name

        # Detectar camada do Neural Hive-Mind baseado no nome do serviço
        layer_mapping = {
            "experiencia": "experiencia",
            "cognicao": "cognicao",
            "orquestracao": "orquestracao",
            "execucao": "execucao",
            "resiliencia": "resiliencia",
            "barramento": "barramento",
            "gateway": "experiencia",
        }

        for layer_key, layer_name in layer_mapping.items():
            if layer_key in self.service_name.lower():
                self.default_labels["neural_hive_layer"] = layer_name
                break

    def get_correlation_header(self, correlation_type: str) -> Optional[str]:
        """Obtém header de correlação por tipo."""
        return self.correlation_headers.get(correlation_type)

    def get_baggage_key(self, correlation_type: str) -> Optional[str]:
        """Obtém chave de baggage por tipo."""
        return self.baggage_keys.get(correlation_type)

    def get_slo_target(self, slo_type: str) -> Optional[float]:
        """Obtém target de SLO por tipo."""
        return self.neural_hive_config["slo_targets"].get(slo_type)

    def is_exemplar_enabled(self) -> bool:
        """Verifica se exemplars estão habilitados."""
        return self.enable_exemplars

    def is_correlation_enabled(self) -> bool:
        """Verifica se correlação está habilitada."""
        return self.enable_correlation

    def should_sample_exemplar(self) -> bool:
        """Determina se deve criar exemplar baseado na taxa de amostragem."""
        import random
        return random.random() < self.exemplar_sample_rate

    def to_dict(self) -> Dict[str, Any]:
        """Converte configuração para dicionário."""
        return {
            "service_name": self.service_name,
            "service_version": self.service_version,
            "environment": self.environment,
            "metrics_port": self.metrics_port,
            "metrics_path": self.metrics_path,
            "enable_exemplars": self.enable_exemplars,
            "enable_correlation": self.enable_correlation,
            "exemplar_sample_rate": self.exemplar_sample_rate,
            "correlation_headers": self.correlation_headers,
            "baggage_keys": self.baggage_keys,
            "prometheus_pushgateway_url": self.prometheus_pushgateway_url,
            "otel_exporter_otlp_endpoint": self.otel_exporter_otlp_endpoint,
            "jaeger_agent_host": self.jaeger_agent_host,
            "jaeger_agent_port": self.jaeger_agent_port,
            "default_labels": self.default_labels,
            "neural_hive_config": self.neural_hive_config,
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "MetricsConfig":
        """Cria configuração a partir de dicionário."""
        return cls(**config_dict)

    @classmethod
    def from_file(cls, config_path: str) -> "MetricsConfig":
        """Carrega configuração de arquivo YAML/JSON."""
        import json
        import yaml
        from pathlib import Path

        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo de configuração não encontrado: {config_path}")

        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix.lower() in ['.yaml', '.yml']:
                config_dict = yaml.safe_load(f)
            elif path.suffix.lower() == '.json':
                config_dict = json.load(f)
            else:
                raise ValueError(f"Formato de arquivo não suportado: {path.suffix}")

        return cls.from_dict(config_dict)


# Instância global de configuração
_global_config: Optional[MetricsConfig] = None


def configure_metrics(config: Optional[MetricsConfig] = None, **kwargs) -> MetricsConfig:
    """
    Configura métricas globalmente.

    Args:
        config: Instância de MetricsConfig ou None para usar padrões
        **kwargs: Argumentos para criar nova configuração

    Returns:
        Configuração aplicada
    """
    global _global_config

    if config is not None:
        _global_config = config
    elif kwargs:
        _global_config = MetricsConfig(**kwargs)
    elif _global_config is None:
        _global_config = MetricsConfig()

    return _global_config


def get_config() -> MetricsConfig:
    """
    Obtém configuração global atual.

    Returns:
        Configuração atual ou padrão se não configurada
    """
    global _global_config

    if _global_config is None:
        _global_config = MetricsConfig()

    return _global_config


def reset_config():
    """Reseta configuração global para padrões."""
    global _global_config
    _global_config = None