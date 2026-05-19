"""
Root pytest configuration for Neural Hive Mind tests.

This top-level conftest handles pytest_plugins registration
to comply with pytest requirements.

Updated: 2026-03-30 (Epic F1: Infraestrutura de Testes)
"""

import logging
import sys
from pathlib import Path
from typing import Generator

import pytest

# Injectar a raiz do repo em sys.path para que ml_pipelines.* e outros
# packages no top-level sejam importáveis nos testes sem necessitar pip
# install -e. Resolve ModuleNotFoundError: ml_pipelines.deployment.*
# em tests/unit/ml_pipelines/deployment/test_model_promotion.py
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Configure logging for all tests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Register fixture modules at top level (required by pytest)
# These are conditionally loaded - missing modules are skipped
pytest_plugins = []

_fixture_modules = [
    "tests.e2e.fixtures.kubernetes",
    "tests.e2e.fixtures.kafka",
    "tests.e2e.fixtures.databases",
    "tests.e2e.fixtures.services",
    "tests.e2e.fixtures.test_data",
    "tests.e2e.fixtures.schema_registry",
    "tests.e2e.fixtures.avro_helpers",
    "tests.e2e.fixtures.specialists",
    "tests.e2e.fixtures.circuit_breakers",
]

for module in _fixture_modules:
    try:
        __import__(module)
        pytest_plugins.append(module)
    except ImportError:
        pass


# =============================================================================
# Import test_helpers para factories, asserts e mocks
# =============================================================================

try:
    from tests.test_helpers import (
        TestCognitivePlanFactory,
        TestSpecialistOpinionFactory,
        TestConsolidatedDecisionFactory,
        TestExecutionTicketFactory,
        TestSpecialistFeedbackFactory,
        assert_valid_plan_id,
        assert_valid_confidence,
        assert_valid_domain,
        assert_valid_risk_band,
        assert_valid_specialist_id,
        assert_valid_status,
        assert_cognitive_plan,
        assert_specialist_opinion,
        assert_consolidated_decision,
    )

    __all__ = [
        "TestCognitivePlanFactory",
        "TestSpecialistOpinionFactory",
        "TestConsolidatedDecisionFactory",
        "TestExecutionTicketFactory",
        "TestSpecialistFeedbackFactory",
        "assert_valid_plan_id",
        "assert_valid_confidence",
        "assert_valid_domain",
        "assert_valid_risk_band",
        "assert_valid_specialist_id",
        "assert_valid_status",
        "assert_cognitive_plan",
        "assert_specialist_opinion",
        "assert_consolidated_decision",
    ]
except ImportError:
    # test_helpers pode não estar disponível ainda
    pass


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    # Markers are also defined in pytest.ini but we ensure they're registered

    # Registrar collections de test_helpers
    config.addinivalue_line("collect_ignore", ["tests/test_helpers/"])


# =============================================================================
# Global fixtures disponíveis para todos os testes
# =============================================================================


@pytest.fixture(scope="session")
def test_data_dir() -> str:
    """Retorna o diretório de dados de teste."""
    import os

    return os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="session")
def test_results_dir() -> str:
    """Retorna o diretório de resultados de teste."""
    import os

    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    return results_dir


@pytest.fixture(scope="session")
def test_logs_dir() -> str:
    """Retorna o diretório de logs de teste."""
    import os

    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


@pytest.fixture
def temp_test_dir(tmp_path_factory) -> Generator[str, None, None]:
    """
    Cria um diretório temporário para testes que precisa de ficheiros.

    O diretório é limpo automaticamente após o teste.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


# =============================================================================
# Skip condicionais para serviços externos
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Registra marcadores customizados."""
    # Já definidos em pytest.ini, esta função é para compatibilidade
    pass


def pytest_collection_modifyitems(config, items):
    """
    Modifica a coleção de testes para adicionar skips condicionais.

    Testes marcados como 'kafka' mas sem Kafka disponível são marcados
    para skip automaticamente.
    """
    # Verificar se Kafka está disponível
    kafka_available = False
    try:
        from confluent_kafka import Producer

        p = Producer({"bootstrap.servers": "localhost:9092"})
        p.poll(0)
        kafka_available = True
    except Exception:
        pass

    # Verificar se MongoDB está disponível
    mongodb_available = False
    try:
        from pymongo import MongoClient

        client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=1000)
        client.server_info()
        mongodb_available = True
    except Exception:
        pass

    # Verificar se Redis está disponível
    redis_available = False
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        r.ping()
        redis_available = True
    except Exception:
        pass

    for item in items:
        # Adicionar skip para testes kafka se não disponível
        if "kafka" in item.keywords and not kafka_available:
            item.add_marker(pytest.mark.skip(reason="Kafka não disponível em localhost:9092"))

        # Adicionar skip para testes mongodb se não disponível
        if "mongodb" in item.keywords and not mongodb_available:
            item.add_marker(pytest.mark.skip(reason="MongoDB não disponível em localhost:27017"))

        # Adicionar skip para testes redis se não disponível
        if "redis" in item.keywords and not redis_available:
            item.add_marker(pytest.mark.skip(reason="Redis não disponível em localhost:6379"))
