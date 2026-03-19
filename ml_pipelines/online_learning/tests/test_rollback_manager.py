"""Testes para RollbackManager."""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime, timedelta


# ============================================================================
# Mock MongoDB classes para evitar tentativas de conexão real
# ============================================================================

# Armazenamento global para simular persistência
_mongo_storage = {}


class MockCursor:
    """Mock de cursor MongoDB que rasteia dados."""
    def __init__(self, data=None):
        self._data = list(data) if data is not None else []

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        limit = args[0] if args else 10
        return self._data[:limit]

    def __iter__(self):
        return iter(self._data)


class MockMongoCollection:
    """Mock de coleção MongoDB que rasteia dados."""
    def __init__(self, name='test_collection'):
        self._name = name

    def find(self, *args, **kwargs):
        data = _mongo_storage.get(self._name, [])
        return MockCursor(list(data))

    def find_one(self, *args, **kwargs):
        data = _mongo_storage.get(self._name, [])
        if not data:
            return None
        # Filtrar por specialist_type se fornecido
        if args and 'specialist_type' in args[0]:
            spec_type = args[0]['specialist_type']
            is_stable = args[0].get('is_stable')
            for doc in data:
                if doc.get('specialist_type') == spec_type:
                    if is_stable is None or doc.get('is_stable') == is_stable:
                        return doc
            return None
        return data[0]

    def insert_one(self, document, *args, **kwargs):
        _mongo_storage.setdefault(self._name, []).append(document)
        return Mock(inserted_id='test_id')

    def update_one(self, *args, **kwargs):
        return Mock(modified_count=1)

    def delete_one(self, *args, **kwargs):
        data = _mongo_storage.get(self._name, [])
        if data:
            data.pop()
        return Mock(deleted_count=1)

    def create_index(self, *args, **kwargs):
        pass

    def create_indexes(self, *args, **kwargs):
        pass

    def aggregate(self, *args, **kwargs):
        return []

    def count_documents(self, *args, **kwargs):
        return len(_mongo_storage.get(self._name, []))

    def __iter__(self):
        return iter(_mongo_storage.get(self._name, []))

    def __getitem__(self, name):
        return self


class MockMongoDB:
    """Mock de database MongoDB."""
    def __init__(self):
        self._collections = {}

    def __getitem__(self, name):
        if name not in self._collections:
            self._collections[name] = MockMongoCollection(name)
        return self._collections[name]

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return self.__getitem__(name)


class MockMongoClient:
    """Mock de cliente MongoDB."""
    def __init__(self, *args, **kwargs):
        self._db = MockMongoDB()

    def __getitem__(self, name):
        return self._db

    def __getattr__(self, name):
        if name == '_MongoClient__all_options' or name.startswith('_'):
            raise AttributeError(name)
        return self._db

    def close(self):
        """Mock close method."""
        pass


# Patch pymongo antes de importar os módulos
_pymongo_patch = patch('pymongo.MongoClient', MockMongoClient)
_pymongo_patch.start()

# Patch também no módulo rollback_manager
_rollback_patch = patch('ml_pipelines.online_learning.rollback_manager.MongoClient', MockMongoClient)
_rollback_patch.start()

# Agora é seguro importar
from ml_pipelines.online_learning.rollback_manager import (
    RollbackManager,
    ModelVersion
)
from ml_pipelines.online_learning.config import OnlineLearningConfig


@pytest.fixture(autouse=True)
def reset_mongo_storage():
    """Limpa armazenamento MongoDB entre testes."""
    _mongo_storage.clear()
    yield
    _mongo_storage.clear()


@pytest.fixture(autouse=True)
def cleanup_patches():
    """Limpa patches após todos os testes."""
    yield
    # Não paramos o patch aqui porque outros testes podem precisar dele


@pytest.fixture
def config():
    """Configuração de teste."""
    return OnlineLearningConfig(
        rollback_enabled=True,
        rollback_f1_drop_threshold=0.05,
        rollback_accuracy_drop_threshold=0.03,
        rollback_latency_increase_threshold=1.5,
        max_versions_to_keep=5
    )


@pytest.fixture
def manager(config):
    """RollbackManager para testes."""
    return RollbackManager(config, specialist_type="test_specialist")


class TestRollbackManagerInitialization:
    """Testes de inicialização."""

    def test_init_with_config(self, config):
        """Testar inicialização com configuração."""
        manager = RollbackManager(config, specialist_type="test_specialist")

        assert manager.config.rollback_f1_drop_threshold == 0.05
        assert manager.config.rollback_accuracy_drop_threshold == 0.03
        assert manager.config.rollback_latency_increase_threshold == 1.5

    def test_init_rollback_disabled(self):
        """Testar com rollback desabilitado."""
        config = OnlineLearningConfig(rollback_enabled=False)
        manager = RollbackManager(config, specialist_type="test_specialist")

        assert manager.rollback_enabled is False


class TestRegisterVersion:
    """Testes de registro de versão."""

    def test_register_version(self, manager):
        """Testar registro de versão."""
        manager.register_version(
            version_id='v1.0.0',
            checkpoint_path='/data/checkpoints/feasibility_v1.0.0.pkl',
            metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0}
        )

        versions = manager.list_versions()
        assert len(versions) == 1

    def test_register_multiple_versions(self, manager):
        """Testar registro de múltiplas versões."""
        for i in range(3):
            manager.register_version(
                version_id=f'v1.0.{i}',
                checkpoint_path=f'/data/checkpoints/feasibility_v1.0.{i}.pkl',
                metrics={'f1_score': 0.85 + i * 0.01, 'accuracy': 0.88 + i * 0.01, 'avg_latency_ms': 15.0},
                mark_stable=i == 2
            )

        versions = manager.list_versions()
        assert len(versions) == 3

    def test_register_exceeds_max_versions(self, manager):
        """Testar que versões antigas são removidas."""
        for i in range(7):
            manager.register_version(
                version_id=f'v1.0.{i}',
                checkpoint_path=f'/data/checkpoints/feasibility_v1.0.{i}.pkl',
                metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
                mark_stable=i == 6
            )

        versions = manager.list_versions()
        # Deve manter apenas max_versions_to_keep
        assert len(versions) <= 5


class TestDetectDegradation:
    """Testes de detecção de degradação."""

    def test_detect_degradation_f1_drop(self, manager):
        """Testar detecção de queda de F1."""
        # Primeiro registrar baseline
        manager.register_version(
            version_id='v1.0.0',
            checkpoint_path='/data/checkpoints/baseline.pkl',
            metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
            mark_stable=True
        )

        current_metrics = {
            'f1_score': 0.79,  # Queda de 0.06, acima do threshold 0.05
            'accuracy': 0.88,
            'avg_latency_ms': 15.0
        }

        is_degraded, reasons = manager.detect_degradation(current_metrics)

        assert is_degraded is True
        assert any('f1' in r.lower() for r in reasons)

    def test_detect_degradation_accuracy_drop(self, manager):
        """Testar detecção de queda de accuracy."""
        # Primeiro registrar baseline
        manager.register_version(
            version_id='v1.0.0',
            checkpoint_path='/data/checkpoints/baseline.pkl',
            metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
            mark_stable=True
        )

        current_metrics = {
            'f1_score': 0.85,
            'accuracy': 0.84,  # Queda de 0.04, acima do threshold 0.03
            'avg_latency_ms': 15.0
        }

        is_degraded, reasons = manager.detect_degradation(current_metrics)

        assert is_degraded is True
        assert any('accuracy' in r.lower() for r in reasons)

    def test_detect_degradation_latency_increase(self, manager):
        """Testar detecção de aumento de latência."""
        # Primeiro registrar baseline
        manager.register_version(
            version_id='v1.0.0',
            checkpoint_path='/data/checkpoints/baseline.pkl',
            metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
            mark_stable=True
        )

        current_metrics = {
            'f1_score': 0.85,
            'accuracy': 0.88,
            'avg_latency_ms': 25.0  # Aumento > 1.5x
        }

        is_degraded, reasons = manager.detect_degradation(current_metrics)

        assert is_degraded is True
        assert any('latency' in r.lower() for r in reasons)

    def test_no_degradation(self, manager):
        """Testar quando não há degradação."""
        # Primeiro registrar baseline
        manager.register_version(
            version_id='v1.0.0',
            checkpoint_path='/data/checkpoints/baseline.pkl',
            metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
            mark_stable=True
        )

        current_metrics = {
            'f1_score': 0.84,  # Queda pequena, dentro do threshold
            'accuracy': 0.87,
            'avg_latency_ms': 16.0
        }

        is_degraded, reasons = manager.detect_degradation(current_metrics)

        assert is_degraded is False


class TestExecuteRollback:
    """Testes de execução de rollback."""

    def test_execute_rollback_success(self, manager):
        """Testar rollback bem-sucedido."""
        # Registrar versões
        manager.register_version(
            version_id='v1.0.0',
            checkpoint_path='/data/checkpoints/feasibility_v1.0.0.pkl',
            metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
            mark_stable=True
        )
        manager.register_version(
            version_id='v1.1.0',
            checkpoint_path='/data/checkpoints/feasibility_v1.1.0.pkl',
            metrics={'f1_score': 0.80, 'accuracy': 0.82, 'avg_latency_ms': 20.0},  # Degradou
            mark_stable=False
        )

        result = manager.execute_rollback(
            reason='Performance degradation'
        )

        assert result['success'] is True
        assert result['to_version'] == 'v1.0.0'

    def test_execute_rollback_to_specific_version(self, manager):
        """Testar rollback para versão específica."""
        for i in range(3):
            manager.register_version(
                version_id=f'v1.0.{i}',
                checkpoint_path=f'/data/checkpoints/feasibility_v1.0.{i}.pkl',
                metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
                mark_stable=i == 2
            )

        result = manager.execute_rollback(
            reason='Manual rollback',
            target_version='v1.0.0'
        )

        assert result['success'] is True
        assert result['to_version'] == 'v1.0.0'

    def test_execute_rollback_no_previous_version(self, manager):
        """Testar rollback sem versão anterior."""
        # Registrar apenas uma versão não estável
        manager.register_version(
            version_id='v1.0.0',
            checkpoint_path='/data/checkpoints/feasibility_v1.0.0.pkl',
            metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
            mark_stable=False
        )

        result = manager.execute_rollback(
            reason='Test rollback'
        )

        assert result['success'] is False
        assert 'error' in result


class TestListVersions:
    """Testes de listagem de versões."""

    def test_list_versions_empty(self, manager):
        """Testar listagem sem versões."""
        versions = manager.list_versions()
        assert versions == []

    def test_list_versions_ordered(self, manager):
        """Testar que versões são ordenadas por data."""
        for i in range(3):
            manager.register_version(
                version_id=f'v1.0.{i}',
                checkpoint_path=f'/data/checkpoints/v1.0.{i}.pkl',
                metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
                mark_stable=i == 2
            )

        versions = manager.list_versions()

        # Mais recente primeiro
        assert versions[0].version_id == 'v1.0.2'
        assert versions[-1].version_id == 'v1.0.0'

    def test_list_versions_with_limit(self, manager):
        """Testar listagem com limite."""
        for i in range(5):
            manager.register_version(
                version_id=f'v1.0.{i}',
                checkpoint_path=f'/data/checkpoints/v1.0.{i}.pkl',
                metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
                mark_stable=i == 0
            )

        versions = manager.list_versions(limit=3)

        assert len(versions) == 3


class TestGetStableVersion:
    """Testes de obtenção de versão estável."""

    def test_get_stable_version(self, manager):
        """Testar obtenção de versão estável."""
        manager.register_version(
            version_id='v1.0.0',
            checkpoint_path='/data/checkpoints/feasibility_v1.0.0.pkl',
            metrics={'f1_score': 0.85, 'accuracy': 0.88, 'avg_latency_ms': 15.0},
            mark_stable=True
        )

        stable = manager.get_stable_version()

        assert stable is not None
        assert stable.is_stable is True

    def test_get_stable_version_none(self, manager):
        """Testar quando não há versão estável."""
        stable = manager.get_stable_version()
        assert stable is None
