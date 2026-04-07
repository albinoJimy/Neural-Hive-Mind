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
# instrument_grpc_channel deve retornar o mesmo canal que recebe (identity function)
mock_observability_module.instrument_grpc_channel = Mock(
    side_effect=lambda channel, **kwargs: channel
)

# Submódulo context
mock_context_module = ModuleType("neural_hive_observability.context")
mock_context_module.set_baggage = Mock()
mock_observability_module.context = mock_context_module

# Submódulo metrics
mock_metrics_module = ModuleType("neural_hive_observability.metrics")


# Mock QueenAgentMetrics com todos os atributos necessários
def create_counter_mock():
    counter = MagicMock()
    counter.inc = MagicMock()
    counter.labels = MagicMock(return_value=counter)
    return counter


def create_histogram_mock():
    histogram = MagicMock()
    histogram.observe = MagicMock()
    histogram.labels = MagicMock(return_value=histogram)
    return histogram


def create_gauge_mock():
    gauge = MagicMock()
    gauge.set = MagicMock()
    gauge.inc = MagicMock()
    gauge.labels = MagicMock(return_value=gauge)
    return gauge


mock_queen_agent_metrics = MagicMock()
mock_queen_agent_metrics.decision_actions_total = create_counter_mock()
mock_queen_agent_metrics.decision_duration_seconds = create_histogram_mock()
mock_queen_agent_metrics.guardrail_validation_total = create_counter_mock()
mock_queen_agent_metrics.guardrail_validation_failed = create_counter_mock()

mock_metrics_module.QueenAgentMetrics = mock_queen_agent_metrics
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

# Mock para src.observability - criar submódulos sem sobrescrever src
# Importar src primeiro se disponível
try:
    import src

    # Se src já existe como módulo, apenas adicionar o mock de observability
    if not hasattr(src, "observability"):
        mock_src_observability_module = ModuleType("src.observability")
        mock_src_observability_module.metrics = mock_metrics_module
        mock_src_observability_module.context = mock_context_module
        mock_src_observability_module.grpc_instrumentation = mock_grpc_module
        src.observability = mock_src_observability_module
except ImportError:
    # Se src não existe, criar o mock completo
    mock_src_module = ModuleType("src")
    mock_src_module.__path__ = []  # Marcar como package
    mock_src_observability_module = ModuleType("src.observability")
    mock_src_observability_module.metrics = mock_metrics_module
    mock_src_observability_module.context = mock_context_module
    mock_src_observability_module.grpc_instrumentation = mock_grpc_module
    mock_src_module.observability = mock_src_observability_module
    sys.modules["src"] = mock_src_module

sys.modules["src.observability"] = mock_src_observability_module
sys.modules["src.observability.metrics"] = mock_metrics_module
sys.modules["src.observability.context"] = mock_context_module
sys.modules["src.observability.grpc_instrumentation"] = mock_grpc_module
