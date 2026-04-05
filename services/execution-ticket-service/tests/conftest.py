"""
Configuração pytest para testes do Execution Ticket Service.
"""
import os
import sys
from pathlib import Path

import pytest

# Adicionar src ao path ANTES de pytest coletar os testes
service_dir = Path(__file__).resolve().parents[1]
src_path = str(service_dir / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


# Configurar variáveis de ambiente para testes
# Isso evita erros de validação do Pydantic Settings
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-bytes-long-for-testing")


# =============================================================================
# Fixture para limpar Prometheus CollectorRegistry entre testes
# =============================================================================


@pytest.fixture(autouse=True)
def clean_prometheus_registry():
    """Limpa o Prometheus CollectorRegistry antes e depois de cada teste.

    Isso evita o erro "Duplicated timeseries in CollectorRegistry" que
    ocorre quando múltiplos testes criam TicketServiceMetrics.
    """
    # Limpar antes do teste
    try:
        from prometheus_client import REGISTRY
        collectors_to_remove = list(REGISTRY._collector_to_names.keys())
        for c in collectors_to_remove:
            REGISTRY.unregister(c)
    except Exception:
        pass

    yield

    # Limpar após o teste
    try:
        from prometheus_client import REGISTRY
        collectors_to_remove = list(REGISTRY._collector_to_names.keys())
        for c in collectors_to_remove:
            REGISTRY.unregister(c)
    except Exception:
        # Se falhar, criar um novo registry vazio
        from prometheus_client import CollectorRegistry
        import prometheus_client
        prometheus_client.REGISTRY = CollectorRegistry()
