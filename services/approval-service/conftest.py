"""
Root conftest.py - Configura mocks ANTES de qualquer import
Este arquivo é carregado pelo pytest antes de começar a coletar testes.
"""
import sys
from datetime import timezone
from enum import Enum
from types import ModuleType
from unittest.mock import Mock, MagicMock

# StrEnum polyfill para Python 3.10 (compatível com herança)
class StrEnum(str, Enum):
    """Mock de StrEnum para Python 3.10."""

    def __hash__(self) -> int:
        return hash(str(self.value))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return str(self.value) == other
        return super().__eq__(other)

# Mock de dependências externas - criar Enum compatível com Pydantic
class MockUnifiedDomain(StrEnum):
    """Mock de UnifiedDomain como Enum, compatível com modelos Pydantic."""

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
mock_domain_module.DomainMapper = lambda domain, service=None: domain
mock_domain_module.StrEnum = StrEnum
mock_domain_module.UTC = timezone.utc

# Criar módulo real para neural_hive_specialists
mock_specialists_module = ModuleType("neural_hive_specialists")

# Criar submódulo feedback para approval-service
mock_feedback_module = ModuleType("neural_hive_specialists.feedback")
mock_feedback_module.FeedbackCollector = Mock
mock_feedback_module.BalanceAnalyzer = Mock
mock_feedback_module.LearningStrategy = Mock
mock_feedback_module.FeedbackQueue = Mock
mock_specialists_module.feedback = mock_feedback_module

# Criar submódulo retraining_trigger
mock_retraining_module = ModuleType("neural_hive_specialists.retraining")
mock_retraining_module.RetrainingTrigger = Mock
mock_specialists_module.retraining = mock_retraining_module

# Criar módulo real para neural_hive_agent_sdk
mock_sdk_module = ModuleType("neural_hive_agent_sdk")

# Criar módulo real para neural_hive_observability
mock_observability_module = ModuleType("neural_hive_observability")
mock_observability_module.get_logger = Mock(return_value=MagicMock())
mock_observability_module.instrument_grpc_channel = Mock(side_effect=lambda channel, **kwargs: channel)

# Submódulo context
mock_context_module = ModuleType("neural_hive_observability.context")
mock_context_module.set_baggage = Mock()
mock_context_module.ContextManager = Mock
mock_observability_module.context = mock_context_module

# Submódulo metrics
mock_metrics_module = ModuleType("neural_hive_observability.metrics")

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
sys.modules["neural_hive_specialists.feedback"] = mock_feedback_module
sys.modules["neural_hive_specialists.retraining"] = mock_retraining_module
sys.modules["neural_hive_agent_sdk"] = mock_sdk_module
sys.modules["neural_hive_observability"] = mock_observability_module
sys.modules["neural_hive_observability.context"] = mock_context_module
sys.modules["neural_hive_observability.metrics"] = mock_metrics_module
sys.modules["neo4j"] = mock_neo4j_module
sys.modules["prometheus_client"] = mock_prometheus_client_module


# =============================================================================
# Pytest Configure Hook - Garante que mocks estão sempre ativos
# =============================================================================
def pytest_configure(config):
    """
    Hook executado pelo pytest ANTES de qualquer import.
    Garante que os mocks estejam em vigor mesmo após manipulação de sys.path.
    """
    # Re-aplicar mocks para garantir que estão ativos
    sys.modules["neural_hive_domain"] = mock_domain_module
    sys.modules["neural_hive_specialists"] = mock_specialists_module
    sys.modules["neural_hive_specialists.feedback"] = mock_feedback_module
    sys.modules["neural_hive_specialists.retraining"] = mock_retraining_module
    sys.modules["neural_hive_agent_sdk"] = mock_sdk_module
    sys.modules["neural_hive_observability"] = mock_observability_module
    sys.modules["neural_hive_observability.context"] = mock_context_module
    sys.modules["neural_hive_observability.metrics"] = mock_metrics_module

    # Prevenir import da biblioteca real removendo-a de sys.modules se foi carregada
    real_library_paths = [k for k in sys.modules if 'neural_hive_domain' in k and '/libraries/python/' in k]
    for path in real_library_paths:
        del sys.modules[path]

    # Remover caminhos para a biblioteca real para evitar import acidental
    real_lib_paths = [p for p in sys.path if '/libraries/python/neural_hive_domain' in p]
    for path in real_lib_paths:
        sys.path.remove(path)
