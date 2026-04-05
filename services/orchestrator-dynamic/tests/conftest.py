"""
Conftest global para testes do orchestrator-dynamic.

Configura sys.path para permitir imports do src e limpa registry do Prometheus.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import REGISTRY

# Carregar variáveis de ambiente para testes ANTES de qualquer importação
env_test_path = Path(__file__).parent.parent / ".env.test"
if env_test_path.exists():
    with open(env_test_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Usar setdefault pode não funcionar se a variável já existir com valor vazio
                # Vamos sobrescrever para garantir o valor correto
                os.environ[key.strip()] = value.strip()

# Adicionar src ao path imediatamente
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


def pytest_configure(config):
    """Hook para configurar pytest antes da coleta de testes."""
    src_path = str(Path(__file__).parent.parent / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


@pytest.fixture
def mock_settings():
    """
    Mock das configurações do OrchestratorSettings.

    Fornece valores padrão para todos os campos obrigatórios do OrchestratorSettings.
    """
    settings_dict = {
        "service_name": "orchestrator-dynamic",
        "service_version": "1.0.0",
        "environment": "test",
        "log_level": "INFO",
        "is_public_api": True,
        # Temporal
        "temporal_enabled": True,
        "temporal_host": "localhost",
        "temporal_port": 7233,
        "temporal_namespace": "default",
        "temporal_task_queue": "orchestration-tasks",
        "temporal_workflow_id_prefix": "test-",
        "temporal_tls_enabled": False,
        # Kafka - campos obrigatórios
        "kafka_bootstrap_servers": "localhost:9092",
        "kafka_consumer_group_id": "test-consumer",
        "kafka_consensus_topic": "plans.consensus",
        "kafka_auto_offset_reset": "earliest",
        "kafka_enable_auto_commit": False,
        "kafka_security_protocol": "PLAINTEXT",
        "kafka_sasl_mechanism": "SCRAM-SHA-512",
        "kafka_sasl_username": None,
        "kafka_sasl_password": None,
        "kafka_ssl_ca_location": None,
        "kafka_ssl_certificate_location": None,
        "kafka_ssl_key_location": None,
        "kafka_tickets_topic": "execution.tickets",
        "kafka_saga_events_topic": "saga.events",
        "kafka_enable_idempotence": True,
        "kafka_transactional_id": None,
        "kafka_schema_registry_url": "http://localhost:8081",
        "schema_registry_tls_verify": False,
        "schema_registry_ca_bundle": None,
        "schemas_base_path": "/app/schemas",
        # Execution results consumer
        "execution_result_consumer_enabled": False,
        "execution_result_consumer_group": "test-execution-results",
        "execution_result_workers": 1,
        # Self-healing
        "self_healing_engine_url": "http://localhost:8443",
        "self_healing_tls_verify": False,
        "self_healing_ca_bundle": None,
        "self_healing_enabled": False,
        "self_healing_timeout_seconds": 30,
        # PostgreSQL - campos obrigatórios
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "postgres_database": "temporal_test",
        "postgres_user": "test",
        "postgres_password": "test",
        "postgres_ssl_mode": "disable",
        # MongoDB - campo obrigatório
        "mongodb_uri": "mongodb://localhost:27017",
        "mongodb_database": "test_orchestration",
        "mongodb_collection_tickets": "execution_tickets",
        "mongodb_collection_workflows": "workflows",
        "MONGODB_MAX_POOL_SIZE": 10,
        "MONGODB_MIN_POOL_SIZE": 5,
        # Redis - campo obrigatório
        "redis_cluster_nodes": "localhost:6379",
        "redis_password": None,
        "redis_ssl_enabled": False,
        # Service Registry
        "service_registry_host": "localhost",
        "service_registry_port": 50051,
        "service_registry_timeout_seconds": 3,
        "service_registry_max_results": 5,
        "service_registry_cache_ttl_seconds": 10,
        # Scheduler
        "enable_intelligent_scheduler": True,
        "enable_ml_enhanced_scheduling": False,
        "scheduler_max_parallel_tickets": 100,
        "scheduler_priority_weights": {"risk": 0.4, "qos": 0.3, "sla": 0.3},
        # Rate limiting (adicionados recentemente)
        "enable_rate_limiting": False,
        "rate_limit_default_capacity": 100,
        "rate_limit_default_refill_rate": 10.0,
        "rate_limit_burst_multiplier": 2.0,
        "rate_limit_tier_limits": {},
        "rate_limit_redis_key_prefix": "rate_limit",
        # Correlation ID validation
        "fail_on_missing_correlation_id": False,
    }

    mock_config = MagicMock(**settings_dict)
    return mock_config


@pytest.fixture(autouse=True, scope="function")
def clean_prometheus_registry():
    """Limpa o registry do Prometheus antes de cada teste para evitar métricas duplicadas."""
    # Coletar todos os collectors antes de limpar
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield
    # Limpar novamente após o teste
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            pass
