"""
Testes de isolamento de tenant.

Valida:
- Cache isolado por tenant_id
- Ledger segregado por tenant_id
- Métricas separadas por tenant_id
- Não há vazamento de dados entre tenants
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from libraries.python.neural_hive_specialists.opinion_cache import OpinionCache
from libraries.python.neural_hive_specialists.ledger_client import LedgerClient
from libraries.python.neural_hive_specialists.metrics import SpecialistMetrics
from libraries.python.neural_hive_specialists.config import SpecialistConfig


@pytest.fixture
def config():
    """Configuração base para testes."""
    return SpecialistConfig(
        specialist_type='technical',
        specialist_version='1.0.0',
        enable_multi_tenancy=True,
        max_tenants=50
    )


class TestCacheIsolation:
    """Testes de isolamento de cache por tenant."""

    def test_cache_keys_include_tenant_id(self):
        """Verifica que chaves de cache incluem tenant_id."""
        cache = OpinionCache(
            redis_cluster_nodes='localhost:6379',
            specialist_type='technical'
        )

        plan_bytes = b'{"action": "test"}'

        key_tenant_a = cache.generate_cache_key(
            plan_bytes=plan_bytes,
            specialist_type='technical',
            specialist_version='1.0.0',
            tenant_id='tenant-A'
        )

        key_tenant_b = cache.generate_cache_key(
            plan_bytes=plan_bytes,
            specialist_type='technical',
            specialist_version='1.0.0',
            tenant_id='tenant-B'
        )

        # Mesmos inputs, tenants diferentes = chaves diferentes
        assert key_tenant_a != key_tenant_b
        assert 'tenant-A' in key_tenant_a
        assert 'tenant-B' in key_tenant_b

    def test_cache_default_tenant_fallback(self):
        """Verifica fallback para tenant 'default'."""
        cache = OpinionCache(
            redis_cluster_nodes='localhost:6379',
            specialist_type='technical'
        )

        plan_bytes = b'{"action": "test"}'

        key_no_tenant = cache.generate_cache_key(
            plan_bytes=plan_bytes,
            specialist_type='technical',
            specialist_version='1.0.0',
            tenant_id=None
        )

        assert 'default' in key_no_tenant


class TestLedgerIsolation:
    """Testes de isolamento de ledger por tenant."""

    @patch('libraries.python.neural_hive_specialists.ledger_client.MongoClient')
    def test_ledger_document_includes_tenant_id(self, mock_mongo_client, config):
        """Verifica que documentos no ledger incluem tenant_id."""
        mock_collection = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

        ledger = LedgerClient(config)

        opinion = {'confidence_score': 0.85, 'recommendation': 'approve'}

        ledger.save_opinion(
            opinion=opinion,
            plan_id='plan-123',
            intent_id='intent-456',
            specialist_type='technical',
            correlation_id='corr-789',
            tenant_id='tenant-A'
        )

        # Verificar que insert_one foi chamado com tenant_id
        call_args = mock_collection.insert_one.call_args
        document = call_args[0][0]

        assert 'tenant_id' in document
        assert document['tenant_id'] == 'tenant-A'

    @patch('libraries.python.neural_hive_specialists.ledger_client.MongoClient')
    def test_ledger_default_tenant_fallback(self, mock_mongo_client, config):
        """Verifica fallback para default_tenant_id quando não fornecido."""
        mock_collection = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

        ledger = LedgerClient(config)

        opinion = {'confidence_score': 0.85, 'recommendation': 'approve'}

        ledger.save_opinion(
            opinion=opinion,
            plan_id='plan-123',
            intent_id='intent-456',
            specialist_type='technical',
            correlation_id='corr-789',
            tenant_id=None  # Não fornecido
        )

        # Verificar que usou default_tenant_id
        call_args = mock_collection.insert_one.call_args
        document = call_args[0][0]

        assert 'tenant_id' in document
        assert document['tenant_id'] == config.default_tenant_id


class TestMetricsIsolation:
    """Testes de isolamento de métricas por tenant."""

    def test_tenant_metrics_cardinality_cap(self, config):
        """Verifica que cardinality cap funciona corretamente."""
        metrics = SpecialistMetrics(config, 'technical')

        # Registrar tenants até o limite
        for i in range(config.max_tenants):
            tenant_id = f'tenant-{i}'
            metrics.increment_tenant_evaluation(tenant_id)
            assert tenant_id in metrics._known_tenants

        # Registrar além do limite deve usar 'other'
        extra_tenant = f'tenant-{config.max_tenants + 1}'
        capped_id = metrics._apply_tenant_cardinality_cap(extra_tenant)

        assert capped_id == 'other'
        assert extra_tenant not in metrics._known_tenants
        assert len(metrics._known_tenants) == config.max_tenants

    def test_tenant_evaluation_metrics_separate(self, config):
        """Verifica que métricas de avaliação são separadas por tenant."""
        metrics = SpecialistMetrics(config, 'technical')

        metrics.increment_tenant_evaluation('tenant-A')
        metrics.increment_tenant_evaluation('tenant-A')
        metrics.increment_tenant_evaluation('tenant-B')

        # Verificar que tenants foram rastreados separadamente
        assert 'tenant-A' in metrics._known_tenants
        assert 'tenant-B' in metrics._known_tenants

    def test_tenant_cache_metrics_separate(self, config):
        """Verifica que métricas de cache são separadas por tenant."""
        metrics = SpecialistMetrics(config, 'technical')

        metrics.increment_tenant_cache_hit('tenant-A')
        metrics.increment_tenant_cache_miss('tenant-A')
        metrics.increment_tenant_cache_hit('tenant-B')

        # Verificar que métodos executam sem erro
        assert 'tenant-A' in metrics._known_tenants
        assert 'tenant-B' in metrics._known_tenants


class TestDataLeakagePrevention:
    """Testes para prevenção de vazamento de dados entre tenants."""

    def test_no_cache_leakage_between_tenants(self):
        """Verifica que cache de um tenant não vaza para outro."""
        cache = OpinionCache(
            redis_cluster_nodes='localhost:6379',
            specialist_type='technical'
        )

        plan_bytes = b'{"action": "test"}'

        # Gerar chaves para diferentes tenants
        key_a = cache.generate_cache_key(
            plan_bytes=plan_bytes,
            specialist_type='technical',
            specialist_version='1.0.0',
            tenant_id='tenant-A'
        )

        key_b = cache.generate_cache_key(
            plan_bytes=plan_bytes,
            specialist_type='technical',
            specialist_version='1.0.0',
            tenant_id='tenant-B'
        )

        # Chaves devem ser completamente diferentes
        assert key_a != key_b

        # Prefixos devem ser diferentes
        prefix_a = key_a.split(':')[:2]  # opinion:tenant-A
        prefix_b = key_b.split(':')[:2]  # opinion:tenant-B

        assert prefix_a != prefix_b

    @patch('libraries.python.neural_hive_specialists.ledger_client.MongoClient')
    def test_no_ledger_leakage_between_tenants(self, mock_mongo_client, config):
        """Verifica que consultas ao ledger filtram por tenant_id."""
        # Simular documentos no MongoDB para dois tenants com mesmo plan_id
        mock_collection = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

        # Simular documentos retornados pelo MongoDB
        tenant_a_doc = {
            'opinion_id': 'opinion-a-123',
            'plan_id': 'shared-plan-999',
            'tenant_id': 'tenant-A',
            'opinion': {'recommendation': 'approve'}
        }
        tenant_b_doc = {
            'opinion_id': 'opinion-b-456',
            'plan_id': 'shared-plan-999',
            'tenant_id': 'tenant-B',
            'opinion': {'recommendation': 'reject'}
        }

        # Configurar mock para retornar apenas documentos do tenant correto
        def find_side_effect(query):
            """Simular filtro do MongoDB."""
            results = []
            if query.get('tenant_id') == 'tenant-A':
                results = [tenant_a_doc]
            elif query.get('tenant_id') == 'tenant-B':
                results = [tenant_b_doc]
            elif 'tenant_id' not in query:
                # Sem filtro de tenant, retorna todos (não deveria acontecer!)
                results = [tenant_a_doc, tenant_b_doc]

            mock_cursor = MagicMock()
            mock_cursor.__iter__.return_value = iter(results)
            return mock_cursor

        mock_collection.find.side_effect = find_side_effect

        ledger = LedgerClient(config)

        # Consulta com tenant_id = 'tenant-A'
        opinions_a = ledger.get_opinions_by_plan('shared-plan-999', tenant_id='tenant-A')

        # Deve retornar apenas opinião do tenant-A
        assert len(opinions_a) == 1
        assert opinions_a[0]['tenant_id'] == 'tenant-A'
        assert opinions_a[0]['opinion_id'] == 'opinion-a-123'

        # Consulta com tenant_id = 'tenant-B'
        opinions_b = ledger.get_opinions_by_plan('shared-plan-999', tenant_id='tenant-B')

        # Deve retornar apenas opinião do tenant-B
        assert len(opinions_b) == 1
        assert opinions_b[0]['tenant_id'] == 'tenant-B'
        assert opinions_b[0]['opinion_id'] == 'opinion-b-456'

        # Verificar que queries incluíram tenant_id
        calls = mock_collection.find.call_args_list
        assert all('tenant_id' in call[0][0] for call in calls)
