"""
Configuração pytest para testes neural_hive_opa.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

# Adicionar src ao path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def mock_opa_config():
    """Configurações mockadas para testes."""
    return SimpleNamespace(
        opa_url="http://localhost:8181",
        opa_host="localhost",
        opa_port=8181,
        opa_timeout_seconds=5,
        opa_cache_ttl_seconds=300,
        opa_cache_max_size=1000,
        opa_circuit_breaker_enabled=True,
        opa_circuit_breaker_failure_threshold=5,
        opa_circuit_breaker_reset_timeout_seconds=60,
        opa_max_concurrent_evaluations=20,
        opa_retry_attempts=3,
        opa_retry_initial_delay=0.1,
        opa_retry_max_delay=2.0,
        opa_connection_pool_size=100,
        opa_enable_metrics=False,  # Desabilitar métricas por padrão nos testes
    )
