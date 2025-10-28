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
from libraries.python.neural_hive_specialists.multi_tenant_specialist import MultiTenantSpecialist
from libraries.python.neural_hive_specialists.config import SpecialistConfig


@pytest.fixture
def config():
    """Configuração base para testes."""
    return SpecialistConfig(
        specialist_type='technical',
        specialist_version='1.0.0',
        model_name='test-model',
        default_tenant_id='default',
        enable_multi_tenancy=True
    )


@pytest.fixture
def mock_request():
    """Mock de EvaluatePlanRequest."""
    request = Mock()
    request.plan_id = 'test-plan-123'
    request.intent_id = 'test-intent-456'
    request.correlation_id = 'test-corr-789'
    request.trace_id = 'test-trace-abc'
    request.context = {}
    request.cognitive_plan = {
        'action': 'test',
        'resources': []
    }
    return request


class TestMultiTenantSpecialist:
    """Testes para MultiTenantSpecialist."""

    def test_extract_tenant_id_from_context(self, config, mock_request):
        """Testa extração de tenant_id do request.context."""
        specialist = MultiTenantSpecialist(config)
        mock_request.context = {'tenant_id': 'tenant-A'}

        tenant_id = specialist._extract_tenant_id(mock_request)

        assert tenant_id == 'tenant-A'

    def test_extract_tenant_id_default_fallback(self, config, mock_request):
        """Testa fallback para default quando tenant_id não fornecido."""
        specialist = MultiTenantSpecialist(config)
        mock_request.context = {}

        tenant_id = specialist._extract_tenant_id(mock_request)

        assert tenant_id == 'default'

    def test_validate_known_tenant(self, config):
        """Testa validação de tenant conhecido."""
        specialist = MultiTenantSpecialist(config)

        tenant_config = specialist._validate_tenant('tenant-enterprise-A')

        assert tenant_config is not None
        assert tenant_config.tenant_id == 'tenant-enterprise-A'
        assert tenant_config.is_active is True

    def test_validate_unknown_tenant_raises_error(self, config):
        """Testa que tenant desconhecido levanta ValueError."""
        specialist = MultiTenantSpecialist(config)

        with pytest.raises(ValueError, match="Tenant desconhecido"):
            specialist._validate_tenant('tenant-unknown-XYZ')

    def test_validate_inactive_tenant_raises_error(self, config):
        """Testa que tenant inativo levanta ValueError."""
        specialist = MultiTenantSpecialist(config)

        with pytest.raises(ValueError, match="Tenant inativo"):
            specialist._validate_tenant('tenant-inactive-B')

    @patch.object(MultiTenantSpecialist, '_load_model_from_mlflow')
    def test_load_tenant_model_caching(self, mock_load_mlflow, config):
        """Testa que modelos por tenant são cacheados."""
        mock_load_mlflow.return_value = Mock()
        specialist = MultiTenantSpecialist(config)

        # Primeira carga
        model1 = specialist._load_tenant_model('tenant-A')
        # Segunda carga (deve usar cache)
        model2 = specialist._load_tenant_model('tenant-A')

        assert model1 is model2
        assert mock_load_mlflow.call_count == 1

    def test_apply_tenant_config_overrides(self, config):
        """Testa aplicação de overrides de configuração por tenant."""
        specialist = MultiTenantSpecialist(config)
        tenant_config = specialist.tenant_configs['tenant-enterprise-A']

        original_config = specialist._apply_tenant_config_overrides(tenant_config)

        # Verificar que overrides foram aplicados
        assert specialist.config.cache_ttl_seconds == tenant_config.cache_ttl_override

        # Restaurar configuração original
        specialist.config.cache_ttl_seconds = original_config['cache_ttl_seconds']

    @patch.object(MultiTenantSpecialist, 'evaluate_plan')
    def test_tenant_id_injected_into_request_context(self, mock_evaluate, config, mock_request):
        """Testa que tenant_id é injetado no request.context antes da avaliação."""
        specialist = MultiTenantSpecialist(config)
        mock_request.context = {'tenant_id': 'tenant-A'}

        specialist.evaluate_plan(mock_request)

        # Verificar que tenant_id permanece no context
        assert 'tenant_id' in mock_request.context
        assert mock_request.context['tenant_id'] == 'tenant-A'
