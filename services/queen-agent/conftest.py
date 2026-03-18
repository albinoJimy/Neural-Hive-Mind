"""
Root conftest.py - Configura mocks ANTES de qualquer import
Este arquivo é carregado pelo pytest antes de começar a coletar testes.
"""
import sys
from enum import Enum
from types import ModuleType
from unittest.mock import Mock, MagicMock

# Mock de dependências externas - criar Enum compatível com Pydantic e Conflict model
class MockUnifiedDomain(Enum):
    """Mock de UnifiedDomain como Enum, compatível com o modelo Conflict."""

    SECURITY = "SECURITY"
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"
    COMPLIANCE = "COMPLIANCE"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    OPERATIONAL = "OPERATIONAL"
    BEHAVIORAL = "BEHAVIORAL"
    EVOLUTIONARY = "EVOLUTIONARY"

    def __str__(self) -> str:
        return self.value

# Criar módulo real para neural_hive_domain
mock_domain_module = ModuleType("neural_hive_domain")
mock_domain_module.UnifiedDomain = MockUnifiedDomain
mock_domain_module.DomainMapper = Mock  # Mock para DomainMapper

# Criar módulo real para neural_hive_specialists
mock_specialists_module = ModuleType("neural_hive_specialists")

# Criar módulo real para neural_hive_agent_sdk
mock_sdk_module = ModuleType("neural_hive_agent_sdk")

# Criar módulo real para neural_hive_observability
mock_observability_module = ModuleType("neural_hive_observability")
mock_observability_module.get_logger = Mock(return_value=MagicMock())
mock_observability_module.instrument_grpc_channel = Mock()

# Submódulo context
mock_context_module = ModuleType("neural_hive_observability.context")
mock_context_module.set_baggage = Mock()
mock_observability_module.context = mock_context_module

# Submódulo metrics
mock_metrics_module = ModuleType("neural_hive_observability.metrics")
mock_observability_module.metrics = mock_metrics_module

# Submódulo grpc_instrumentation
mock_grpc_module = ModuleType("neural_hive_observability.grpc_instrumentation")
mock_grpc_module.extract_grpc_context = Mock(return_value=({}, None))

# Mock para bibliotecas externas não instaladas no ambiente de teste
mock_neo4j_module = ModuleType("neo4j")
mock_neo4j_module.AsyncGraphDatabase = Mock()
mock_neo4j_module.AsyncDriver = Mock()

mock_prometheus_client_module = ModuleType("prometheus_client")
mock_prometheus_client_module.Counter = Mock
mock_prometheus_client_module.Histogram = Mock
mock_prometheus_client_module.Gauge = Mock
mock_prometheus_client_module.PrometheusConnect = Mock()

# Registrar mocks ANTES de qualquer import
sys.modules["neural_hive_domain"] = mock_domain_module
sys.modules["neural_hive_specialists"] = mock_specialists_module
sys.modules["neural_hive_agent_sdk"] = mock_sdk_module
sys.modules["neural_hive_observability"] = mock_observability_module
sys.modules["neural_hive_observability.context"] = mock_context_module
sys.modules["neural_hive_observability.metrics"] = mock_metrics_module
sys.modules["neural_hive_observability.grpc_instrumentation"] = mock_grpc_module
sys.modules["neo4j"] = mock_neo4j_module
sys.modules["prometheus_client"] = mock_prometheus_client_module
