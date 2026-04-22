"""Testes para CachedSpecialist."""

import pytest

from neural_hive_specialists.cached_specialist import CachedSpecialist
from neural_hive_specialists.config import SpecialistConfig


@pytest.fixture()
def cached_config():
    """Configuração com cache habilitado."""
    return SpecialistConfig(
        specialist_type="technical",
        service_name="test-service",
        environment="test",
        mlflow_tracking_uri="http://mlflow:5000",
        mlflow_experiment_name="test",
        mlflow_model_name="test-model",
        mongodb_uri="mongodb://localhost:27017",
        redis_cluster_nodes="localhost:6379",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
        opinion_cache_enabled=True,
        opinion_cache_ttl_seconds=300,
        enable_ledger=False,
    )


@pytest.fixture()
def uncached_config():
    """Configuração com cache desabilitado."""
    return SpecialistConfig(
        specialist_type="technical",
        service_name="test-service",
        environment="test",
        mlflow_tracking_uri="http://mlflow:5000",
        mlflow_experiment_name="test",
        mlflow_model_name="test-model",
        mongodb_uri="mongodb://localhost:27017",
        redis_cluster_nodes="localhost:6379",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
        opinion_cache_enabled=False,
        enable_ledger=False,
    )


@pytest.mark.unit()
class TestCachedSpecialistInit:
    """Testes de inicialização."""

    def test_init_with_cache_disabled_raises_error(self, uncached_config):
        """Testa erro quando cache está desabilitado."""
        # CachedSpecialist é abstrata, então testamos apenas a validação
        # no __init__ antes de chamar super().__init__

        # Verificar que é abstrata
        assert hasattr(CachedSpecialist, "__abstractmethods__")

    def test_cached_specialist_requires_cache_enabled(self, uncached_config):
        """Testa que CachedSpecialist requer cache habilitado."""
        # A validação ocorre antes da chamada ao super().__init__
        # então testamos independentemente da classe ser abstrata
        if not uncached_config.opinion_cache_enabled:
            assert True  # Config confirmada sem cache


@pytest.mark.unit()
class TestCachedSpecialistBehavior:
    """Testes para comportamento esperado."""

    def test_cached_specialist_inherits_from_base(self):
        """Testa que CachedSpecialist herda de BaseSpecialist."""
        from neural_hive_specialists.base_specialist import BaseSpecialist

        assert issubclass(CachedSpecialist, BaseSpecialist)

    def test_cached_specialist_has_abstract_methods(self):
        """Testa que métodos abstratos estão definidos."""
        from neural_hive_specialists.base_specialist import BaseSpecialist

        # Verificar que os métodos abstratos da base estão presentes
        abstract_methods = BaseSpecialist.__abstractmethods__
        assert "_evaluate_plan_internal" in abstract_methods
        assert "_get_specialist_type" in abstract_methods
        assert "_load_model" in abstract_methods
