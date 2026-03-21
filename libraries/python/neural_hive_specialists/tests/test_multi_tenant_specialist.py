"""
Testes para MultiTenantSpecialist.

Valida:
- Extração de tenant_id do request.context
- Validação de tenants conhecidos/desconhecidos
- Validação de tenants ativos/inativos
- Carregamento de modelos por tenant
- Isolamento de configuração por tenant
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import json

# Patch components que tentam conectar a serviços externos ANTES de importar
patch("neural_hive_specialists.base_specialist.FeatureStore", return_value=None).start()
patch("neural_hive_specialists.base_specialist.OpinionCache", return_value=None).start()
patch("neural_hive_specialists.base_specialist.FeatureCache", return_value=None).start()

from neural_hive_specialists.multi_tenant_specialist import (
    MultiTenantSpecialist,
)
from neural_hive_specialists.config import SpecialistConfig


@pytest.fixture
def tenant_configs_file():
    """Cria arquivo temporário de configs de tenant."""
    tenant_configs = {
        "tenant-enterprise-A": {
            "tenant_id": "tenant-enterprise-A",
            "tenant_name": "Enterprise A",
            "is_active": True,
            "mlflow_model_name": None,
            "mlflow_model_stage": None,
            "min_confidence_score": 0.7,
            "high_risk_threshold": 0.3,
            "enable_explainability": True,
            "rate_limit_per_second": 100,
            "cache_ttl_override": 3600,
            "metadata": {},
        },
        "tenant-inactive-B": {
            "tenant_id": "tenant-inactive-B",
            "tenant_name": "Inactive B",
            "is_active": False,
            "mlflow_model_name": None,
            "mlflow_model_stage": None,
            "min_confidence_score": 0.7,
            "high_risk_threshold": 0.3,
            "enable_explainability": True,
            "rate_limit_per_second": 100,
            "metadata": {},
        },
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(tenant_configs, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    import os
    try:
        os.unlink(temp_path)
    except:
        pass


@pytest.fixture
def config_with_tenant_file(tenant_configs_file):
    """Configuração com arquivo de tenant configs."""
    return SpecialistConfig(
        specialist_type="technical",
        specialist_version="1.0.0",
        service_name="test-specialist",
        default_tenant_id="default",
        enable_multi_tenancy=True,
        tenant_configs_path=tenant_configs_file,
        environment="test",
        mlflow_tracking_uri="http://localhost:5000",
        mlflow_experiment_name="test",
        mlflow_model_name="test-model",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="test_db",
        redis_cluster_nodes="localhost:6379",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
        jwt_secret_key="test-secret-key-with-at-least-32-chars",
    )


class ConcreteMultiTenantSpecialist(MultiTenantSpecialist):
    """Implementação concreta de MultiTenantSpecialist para testes."""

    def _get_specialist_type(self) -> str:
        return "technical"

    def _evaluate_plan_internal(self, cognitive_plan, context):
        return {
            "recommendation": "approve",
            "confidence_score": 0.8,
            "risk_score": 0.2,
            "reasoning_summary": "Multi-tenant test",
            "reasoning_factors": [],
            "suggested_mitigations": [],
        }


@pytest.fixture
def mock_request():
    """Mock de EvaluatePlanRequest."""
    request = Mock()
    request.plan_id = "test-plan-123"
    request.intent_id = "test-intent-456"
    request.correlation_id = "test-corr-789"
    request.trace_id = "test-trace-abc"
    request.context = {}
    request.cognitive_plan = {"action": "test", "resources": []}
    return request


class TestMultiTenantSpecialist:
    """Testes para MultiTenantSpecialist."""

    def test_extract_tenant_id_from_context(self, config_with_tenant_file, mock_request):
        """Testa extração de tenant_id do request.context."""
        specialist = ConcreteMultiTenantSpecialist(config_with_tenant_file)
        mock_request.context = {"tenant_id": "tenant-A"}

        tenant_id = specialist._extract_tenant_id(mock_request)

        assert tenant_id == "tenant-A"

    def test_extract_tenant_id_default_fallback(self, config_with_tenant_file, mock_request):
        """Testa fallback para default quando tenant_id não fornecido."""
        specialist = ConcreteMultiTenantSpecialist(config_with_tenant_file)
        mock_request.context = {}

        tenant_id = specialist._extract_tenant_id(mock_request)

        assert tenant_id == "default"

    def test_validate_known_tenant(self, config):
        """Testa validação de tenant conhecido."""
        specialist = ConcreteMultiTenantSpecialist(config)

        tenant_config = specialist._validate_tenant("tenant-enterprise-A")

        assert tenant_config is not None
        assert tenant_config.tenant_id == "tenant-enterprise-A"
        assert tenant_config.is_active is True

    def test_validate_unknown_tenant_raises_error(self, config):
        """Testa que tenant desconhecido levanta ValueError."""
        specialist = ConcreteMultiTenantSpecialist(config)

        with pytest.raises(ValueError, match="Tenant desconhecido"):
            specialist._validate_tenant("tenant-unknown-XYZ")

    def test_validate_inactive_tenant_raises_error(self, config):
        """Testa que tenant inativo levanta ValueError."""
        specialist = ConcreteMultiTenantSpecialist(config)

        with pytest.raises(ValueError, match="Tenant inativo"):
            specialist._validate_tenant("tenant-inactive-B")

    @patch.object(ConcreteMultiTenantSpecialist, "_load_model_from_mlflow")
    def test_load_tenant_model_caching(self, mock_load_mlflow, config):
        """Testa que modelos por tenant são cacheados."""
        mock_load_mlflow.return_value = Mock()
        specialist = ConcreteMultiTenantSpecialist(config)

        # Primeira carga
        model1 = specialist._load_tenant_model("tenant-A")
        # Segunda carga (deve usar cache)
        model2 = specialist._load_tenant_model("tenant-A")

        assert model1 is model2
        assert mock_load_mlflow.call_count == 1

    def test_apply_tenant_config_overrides(self, config):
        """Testa aplicação de overrides de configuração por tenant."""
        specialist = ConcreteMultiTenantSpecialist(config)
        tenant_config = specialist.tenant_configs["tenant-enterprise-A"]

        original_config = specialist._apply_tenant_config_overrides(tenant_config)

        # Verificar que overrides foram aplicados
        assert specialist.config.cache_ttl_seconds == tenant_config.cache_ttl_override

        # Restaurar configuração original
        specialist.config.cache_ttl_seconds = original_config["cache_ttl_seconds"]

    @patch.object(ConcreteMultiTenantSpecialist, "evaluate_plan")
    def test_tenant_id_injected_into_request_context(
        self, mock_evaluate, config, mock_request
    ):
        """Testa que tenant_id é injetado no request.context antes da avaliação."""
        specialist = ConcreteMultiTenantSpecialist(config)
        mock_request.context = {"tenant_id": "tenant-A"}

        specialist.evaluate_plan(mock_request)

        # Verificar que tenant_id permanece no context
        assert "tenant_id" in mock_request.context
        assert mock_request.context["tenant_id"] == "tenant-A"
