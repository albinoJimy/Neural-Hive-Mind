"""Testes para RollbackManager."""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime, timedelta

from ml_pipelines.online_learning.rollback_manager import (
    RollbackManager,
    ModelVersion
)
from ml_pipelines.online_learning.config import OnlineLearningConfig


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
    return RollbackManager(config)


@pytest.fixture
def sample_version():
    """Versão de modelo de exemplo."""
    return ModelVersion(
        version='v1.0.0',
        specialist_type='feasibility',
        created_at=datetime.utcnow(),
        f1_score=0.85,
        accuracy=0.88,
        avg_latency_ms=15.0,
        checkpoint_path='/data/checkpoints/feasibility_v1.0.0.pkl',
        is_active=True
    )


class TestRollbackManagerInitialization:
    """Testes de inicialização."""

    def test_init_with_config(self, config):
        """Testar inicialização com configuração."""
        manager = RollbackManager(config)

        assert manager.f1_drop_threshold == 0.05
        assert manager.accuracy_drop_threshold == 0.03
        assert manager.latency_increase_threshold == 1.5

    def test_init_rollback_disabled(self):
        """Testar com rollback desabilitado."""
        config = OnlineLearningConfig(rollback_enabled=False)
        manager = RollbackManager(config)

        assert manager.rollback_enabled is False


class TestRegisterVersion:
    """Testes de registro de versão."""

    def test_register_version(self, manager, sample_version):
        """Testar registro de versão."""
        manager.register_version(sample_version)

        versions = manager.list_versions('feasibility')
        assert len(versions) == 1

    def test_register_multiple_versions(self, manager):
        """Testar registro de múltiplas versões."""
        for i in range(3):
            version = ModelVersion(
                version=f'v1.0.{i}',
                specialist_type='feasibility',
                created_at=datetime.utcnow() - timedelta(hours=i),
                f1_score=0.85 + i * 0.01,
                accuracy=0.88 + i * 0.01,
                avg_latency_ms=15.0,
                checkpoint_path=f'/data/checkpoints/feasibility_v1.0.{i}.pkl',
                is_active=i == 2
            )
            manager.register_version(version)

        versions = manager.list_versions('feasibility')
        assert len(versions) == 3

    def test_register_exceeds_max_versions(self, manager):
        """Testar que versões antigas são removidas."""
        for i in range(7):
            version = ModelVersion(
                version=f'v1.0.{i}',
                specialist_type='feasibility',
                created_at=datetime.utcnow() - timedelta(hours=6-i),
                f1_score=0.85,
                accuracy=0.88,
                avg_latency_ms=15.0,
                checkpoint_path=f'/data/checkpoints/feasibility_v1.0.{i}.pkl',
                is_active=i == 6
            )
            manager.register_version(version)

        versions = manager.list_versions('feasibility')
        # Deve manter apenas max_versions_to_keep
        assert len(versions) <= 5


class TestDetectDegradation:
    """Testes de detecção de degradação."""

    def test_detect_degradation_f1_drop(self, manager, sample_version):
        """Testar detecção de queda de F1."""
        manager.register_version(sample_version)

        current_metrics = {
            'f1_score': 0.79,  # Queda de 0.06, acima do threshold 0.05
            'accuracy': 0.88,
            'avg_latency_ms': 15.0
        }

        result = manager.detect_degradation('feasibility', current_metrics)

        assert result['degradation_detected'] is True
        assert 'f1_score' in result['reasons']

    def test_detect_degradation_accuracy_drop(self, manager, sample_version):
        """Testar detecção de queda de accuracy."""
        manager.register_version(sample_version)

        current_metrics = {
            'f1_score': 0.85,
            'accuracy': 0.84,  # Queda de 0.04, acima do threshold 0.03
            'avg_latency_ms': 15.0
        }

        result = manager.detect_degradation('feasibility', current_metrics)

        assert result['degradation_detected'] is True
        assert 'accuracy' in result['reasons']

    def test_detect_degradation_latency_increase(self, manager, sample_version):
        """Testar detecção de aumento de latência."""
        manager.register_version(sample_version)

        current_metrics = {
            'f1_score': 0.85,
            'accuracy': 0.88,
            'avg_latency_ms': 25.0  # Aumento > 1.5x
        }

        result = manager.detect_degradation('feasibility', current_metrics)

        assert result['degradation_detected'] is True
        assert 'latency' in result['reasons']

    def test_no_degradation(self, manager, sample_version):
        """Testar quando não há degradação."""
        manager.register_version(sample_version)

        current_metrics = {
            'f1_score': 0.84,  # Queda pequena, dentro do threshold
            'accuracy': 0.87,
            'avg_latency_ms': 16.0
        }

        result = manager.detect_degradation('feasibility', current_metrics)

        assert result['degradation_detected'] is False


class TestExecuteRollback:
    """Testes de execução de rollback."""

    @pytest.mark.asyncio
    async def test_execute_rollback_success(self, manager):
        """Testar rollback bem-sucedido."""
        # Registrar versões
        v1 = ModelVersion(
            version='v1.0.0',
            specialist_type='feasibility',
            created_at=datetime.utcnow() - timedelta(hours=2),
            f1_score=0.85,
            accuracy=0.88,
            avg_latency_ms=15.0,
            checkpoint_path='/data/checkpoints/feasibility_v1.0.0.pkl',
            is_active=False
        )
        v2 = ModelVersion(
            version='v1.1.0',
            specialist_type='feasibility',
            created_at=datetime.utcnow(),
            f1_score=0.80,  # Degradou
            accuracy=0.82,
            avg_latency_ms=20.0,
            checkpoint_path='/data/checkpoints/feasibility_v1.1.0.pkl',
            is_active=True
        )
        manager.register_version(v1)
        manager.register_version(v2)

        result = await manager.execute_rollback(
            specialist_type='feasibility',
            reason='Performance degradation'
        )

        assert result['success'] is True
        assert result['to_version'] == 'v1.0.0'

    @pytest.mark.asyncio
    async def test_execute_rollback_to_specific_version(self, manager):
        """Testar rollback para versão específica."""
        for i in range(3):
            version = ModelVersion(
                version=f'v1.0.{i}',
                specialist_type='feasibility',
                created_at=datetime.utcnow() - timedelta(hours=2-i),
                f1_score=0.85,
                accuracy=0.88,
                avg_latency_ms=15.0,
                checkpoint_path=f'/data/checkpoints/feasibility_v1.0.{i}.pkl',
                is_active=i == 2
            )
            manager.register_version(version)

        result = await manager.execute_rollback(
            specialist_type='feasibility',
            reason='Manual rollback',
            target_version='v1.0.0'
        )

        assert result['success'] is True
        assert result['to_version'] == 'v1.0.0'

    @pytest.mark.asyncio
    async def test_execute_rollback_no_previous_version(self, manager, sample_version):
        """Testar rollback sem versão anterior."""
        manager.register_version(sample_version)

        result = await manager.execute_rollback(
            specialist_type='feasibility',
            reason='Test rollback'
        )

        assert result['success'] is False
        assert 'error' in result


class TestListVersions:
    """Testes de listagem de versões."""

    def test_list_versions_empty(self, manager):
        """Testar listagem sem versões."""
        versions = manager.list_versions('feasibility')
        assert versions == []

    def test_list_versions_ordered(self, manager):
        """Testar que versões são ordenadas por data."""
        for i in range(3):
            version = ModelVersion(
                version=f'v1.0.{i}',
                specialist_type='feasibility',
                created_at=datetime.utcnow() - timedelta(hours=2-i),
                f1_score=0.85,
                accuracy=0.88,
                avg_latency_ms=15.0,
                checkpoint_path=f'/data/checkpoints/v1.0.{i}.pkl',
                is_active=i == 2
            )
            manager.register_version(version)

        versions = manager.list_versions('feasibility')

        # Mais recente primeiro
        assert versions[0]['version'] == 'v1.0.2'
        assert versions[-1]['version'] == 'v1.0.0'

    def test_list_versions_with_limit(self, manager):
        """Testar listagem com limite."""
        for i in range(5):
            version = ModelVersion(
                version=f'v1.0.{i}',
                specialist_type='feasibility',
                created_at=datetime.utcnow() - timedelta(hours=i),
                f1_score=0.85,
                accuracy=0.88,
                avg_latency_ms=15.0,
                checkpoint_path=f'/data/checkpoints/v1.0.{i}.pkl',
                is_active=i == 0
            )
            manager.register_version(version)

        versions = manager.list_versions('feasibility', limit=3)

        assert len(versions) == 3


class TestGetActiveVersion:
    """Testes de obtenção de versão ativa."""

    def test_get_active_version(self, manager, sample_version):
        """Testar obtenção de versão ativa."""
        manager.register_version(sample_version)

        active = manager.get_active_version('feasibility')

        assert active is not None
        assert active['is_active'] is True

    def test_get_active_version_none(self, manager):
        """Testar quando não há versão ativa."""
        active = manager.get_active_version('feasibility')
        assert active is None
