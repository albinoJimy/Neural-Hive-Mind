"""
Testes do endpoint /health/startup para Kubernetes startupProbe.

Este teste verifica que o endpoint de startup está funcionando corretamente.
"""
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone
from enum import Enum

# Configurar variáveis de ambiente mínimas para Settings não falhar
# Precisa ser ANTES de qualquer import do projeto
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
os.environ["MONGODB_URI"] = "mongodb://localhost:27017/test"
os.environ["REDIS_CLUSTER_NODES"] = "localhost:6379"
os.environ["ENVIRONMENT"] = "test"

# Adicionar src ao path PRIMEIRO para garantir imports corretos
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Mocks necessários antes de importar o app
# Mock de domain
class UnifiedDomain(str, Enum):
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"
    SECURITY = "SECURITY"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    BEHAVIOR = "BEHAVIOR"
    OPERATIONAL = "OPERATIONAL"
    COMPLIANCE = "COMPLIANCE"
    ARCHITECTURE = "ARCHITECTURE"


mock_domain = MagicMock()
mock_domain.UnifiedDomain = UnifiedDomain
sys.modules["neural_hive_domain"] = mock_domain

# Mock de observability
mock_observability = MagicMock()
mock_tracer = MagicMock()
mock_span = MagicMock()
mock_span.__enter__ = MagicMock(return_value=mock_span)
mock_span.__exit__ = MagicMock(return_value=False)
mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)
mock_observability.get_tracer = MagicMock(return_value=mock_tracer)

# Configurar mock para grpc_instrumentation
mock_grpc_instrumentation = MagicMock()
mock_inject = MagicMock()
mock_grpc_instrumentation.inject_grpc_context = mock_inject
mock_observability.grpc_instrumentation = mock_grpc_instrumentation

# Configurar mocks para health
mock_health = MagicMock()
mock_health.HealthChecker = MagicMock
mock_health.HealthStatus = MagicMock
mock_observability.health = mock_health

# Configurar mocks para health_checks
mock_health_checks = MagicMock()
mock_health_checks.otel = MagicMock()
mock_observability.health_checks = mock_health_checks

# Configurar config
mock_config = MagicMock()
mock_config.ObservabilityConfig = MagicMock
mock_observability.config = mock_config

# Configurar context
mock_context = MagicMock()
mock_observability.context = mock_context

sys.modules["neural_hive_observability"] = mock_observability
sys.modules["neural_hive_observability.config"] = mock_config
sys.modules["neural_hive_observability.health"] = mock_health
sys.modules["neural_hive_observability.health_checks"] = mock_health_checks
sys.modules["neural_hive_observability.health_checks.otel"] = mock_health_checks.otel
sys.modules["neural_hive_observability.grpc_instrumentation"] = mock_grpc_instrumentation
sys.modules["neural_hive_observability.context"] = mock_context

# Mocks de protobuf (analyst_agent_pb2, specialist_pb2, etc)
mock_analyst_pb2 = MagicMock()
mock_analyst_pb2_grpc = MagicMock()
sys.modules["analyst_agent_pb2"] = mock_analyst_pb2
sys.modules["analyst_agent_pb2_grpc"] = mock_analyst_pb2_grpc

mock_specialist_pb2 = MagicMock()
mock_specialist_pb2_grpc = MagicMock()
sys.modules["specialist_pb2"] = mock_specialist_pb2
sys.modules["specialist_pb2_grpc"] = mock_specialist_pb2_grpc

import pytest
from fastapi.testclient import TestClient


# Importar app uma só vez no nível do módulo
# Para evitar re-imports com Settings já validados
from main import app


def test_startup_endpoint_exists():
    """Verifica que /health/startup endpoint existe e retorna estrutura correta"""
    client = TestClient(app)
    response = client.get("/health/startup")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["started", "starting"]
    assert "service" in data
    assert "version" in data
    assert "started_at" in data
    assert data["service"] == "consensus-engine"
    assert data["version"] == "1.0.0"


def test_startup_response_format():
    """Verifica que started_at é um formato ISO válido"""
    client = TestClient(app)
    response = client.get("/health/startup")

    assert response.status_code == 200
    data = response.json()

    # Verificar que started_at é parseável como ISO datetime
    try:
        datetime.fromisoformat(data["started_at"])
    except ValueError:
        pytest.fail(f"started_at não é um datetime ISO válido: {data['started_at']}")


def test_startup_comparison_with_readiness():
    """Verifica que /health/startup e /ready são endpoints diferentes"""
    client = TestClient(app)

    startup_response = client.get("/health/startup")
    ready_response = client.get("/ready")

    # Startup deve retornar 200 sempre
    assert startup_response.status_code == 200

    # Ready pode retornar 503 se serviços não estão prontos
    # mas deve ter estrutura diferente de startup
    startup_data = startup_response.json()
    ready_data = ready_response.json()

    # Startup tem "status", Ready tem "ready"
    assert "status" in startup_data
    # Ready pode ter 503 se serviços não estão disponíveis
    assert "ready" in ready_data or ready_response.status_code in [200, 503]
