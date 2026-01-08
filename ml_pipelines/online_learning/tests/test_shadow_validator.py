"""Testes para ShadowValidator."""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from ml_pipelines.online_learning.shadow_validator import (
    ShadowValidator,
    ShadowValidationResult
)
from ml_pipelines.online_learning.config import OnlineLearningConfig


@pytest.fixture
def config():
    """Configuração de teste."""
    return OnlineLearningConfig(
        shadow_accuracy_threshold=0.02,
        shadow_max_latency_ratio=1.5,
        shadow_max_kl_divergence=0.1,
        shadow_min_samples=10
    )


@pytest.fixture
def validator(config):
    """ShadowValidator para testes."""
    return ShadowValidator(config)


@pytest.fixture
def mock_batch_model():
    """Mock do modelo batch."""
    model = Mock()
    model.predict_proba = Mock(return_value=np.array([
        [0.3, 0.7],
        [0.8, 0.2],
        [0.4, 0.6]
    ]))
    model.predict = Mock(return_value=np.array([1, 0, 1]))
    return model


@pytest.fixture
def mock_online_model():
    """Mock do modelo online."""
    model = Mock()
    model.predict_proba = Mock(return_value=np.array([
        [0.35, 0.65],
        [0.75, 0.25],
        [0.45, 0.55]
    ]))
    model.predict = Mock(return_value=np.array([1, 0, 1]))
    return model


class TestShadowValidatorInitialization:
    """Testes de inicialização."""

    def test_init_with_config(self, config):
        """Testar inicialização com configuração."""
        validator = ShadowValidator(config)

        assert validator.accuracy_threshold == 0.02
        assert validator.max_latency_ratio == 1.5
        assert validator.max_kl_divergence == 0.1

    def test_init_default_config(self):
        """Testar inicialização com configuração padrão."""
        validator = ShadowValidator(OnlineLearningConfig())

        assert validator.accuracy_threshold is not None
        assert validator.max_latency_ratio is not None


class TestValidation:
    """Testes de validação."""

    def test_validate_success(self, validator, mock_batch_model, mock_online_model):
        """Testar validação bem-sucedida."""
        X = np.random.randn(10, 5)
        y = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])

        result = validator.validate(
            batch_model=mock_batch_model,
            online_model=mock_online_model,
            X=X,
            y=y
        )

        assert isinstance(result, ShadowValidationResult)
        assert result.samples_count == 10

    def test_validate_calculates_kl_divergence(
        self, validator, mock_batch_model, mock_online_model
    ):
        """Testar cálculo de KL divergence."""
        X = np.random.randn(10, 5)
        y = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])

        result = validator.validate(
            batch_model=mock_batch_model,
            online_model=mock_online_model,
            X=X,
            y=y
        )

        assert result.kl_divergence >= 0

    def test_validate_measures_latency(
        self, validator, mock_batch_model, mock_online_model
    ):
        """Testar medição de latência."""
        X = np.random.randn(10, 5)
        y = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])

        result = validator.validate(
            batch_model=mock_batch_model,
            online_model=mock_online_model,
            X=X,
            y=y
        )

        assert result.batch_latency_ms > 0
        assert result.online_latency_ms > 0
        assert result.latency_ratio > 0

    def test_validate_insufficient_samples(self, validator, mock_batch_model, mock_online_model):
        """Testar validação com amostras insuficientes."""
        X = np.random.randn(5, 5)  # Menos que min_samples
        y = np.array([1, 0, 1, 0, 1])

        result = validator.validate(
            batch_model=mock_batch_model,
            online_model=mock_online_model,
            X=X,
            y=y
        )

        # Deve retornar resultado mas não aprovar
        assert result.samples_count == 5


class TestApprovalDecision:
    """Testes de decisão de aprovação."""

    def test_should_approve_deployment_success(self, validator):
        """Testar aprovação quando métricas são boas."""
        result = ShadowValidationResult(
            batch_accuracy=0.85,
            online_accuracy=0.84,  # Dentro do threshold
            accuracy_diff=-0.01,
            kl_divergence=0.05,  # Abaixo do máximo
            batch_latency_ms=10.0,
            online_latency_ms=12.0,  # Ratio 1.2, abaixo de 1.5
            latency_ratio=1.2,
            samples_count=100,
            timestamp=datetime.utcnow()
        )

        should_approve = validator.should_approve_deployment(result)
        assert should_approve is True

    def test_should_reject_low_accuracy(self, validator):
        """Testar rejeição por baixa accuracy."""
        result = ShadowValidationResult(
            batch_accuracy=0.85,
            online_accuracy=0.80,  # Queda de 0.05, acima do threshold
            accuracy_diff=-0.05,
            kl_divergence=0.05,
            batch_latency_ms=10.0,
            online_latency_ms=12.0,
            latency_ratio=1.2,
            samples_count=100,
            timestamp=datetime.utcnow()
        )

        should_approve = validator.should_approve_deployment(result)
        assert should_approve is False

    def test_should_reject_high_latency(self, validator):
        """Testar rejeição por alta latência."""
        result = ShadowValidationResult(
            batch_accuracy=0.85,
            online_accuracy=0.84,
            accuracy_diff=-0.01,
            kl_divergence=0.05,
            batch_latency_ms=10.0,
            online_latency_ms=20.0,  # Ratio 2.0, acima de 1.5
            latency_ratio=2.0,
            samples_count=100,
            timestamp=datetime.utcnow()
        )

        should_approve = validator.should_approve_deployment(result)
        assert should_approve is False

    def test_should_reject_high_kl_divergence(self, validator):
        """Testar rejeição por alta KL divergence."""
        result = ShadowValidationResult(
            batch_accuracy=0.85,
            online_accuracy=0.84,
            accuracy_diff=-0.01,
            kl_divergence=0.2,  # Acima do máximo 0.1
            batch_latency_ms=10.0,
            online_latency_ms=12.0,
            latency_ratio=1.2,
            samples_count=100,
            timestamp=datetime.utcnow()
        )

        should_approve = validator.should_approve_deployment(result)
        assert should_approve is False


class TestValidationSummary:
    """Testes de sumário de validação."""

    def test_get_validation_summary_empty(self, validator):
        """Testar sumário sem validações."""
        summary = validator.get_validation_summary()

        assert summary['total_validations'] == 0
        assert summary['approval_rate'] == 0.0

    def test_get_validation_summary_with_results(
        self, validator, mock_batch_model, mock_online_model
    ):
        """Testar sumário com validações."""
        X = np.random.randn(20, 5)
        y = np.random.randint(0, 2, 20)

        # Executar algumas validações
        for _ in range(3):
            validator.validate(
                batch_model=mock_batch_model,
                online_model=mock_online_model,
                X=X,
                y=y
            )

        summary = validator.get_validation_summary()

        assert summary['total_validations'] == 3
        assert 'approval_rate' in summary
        assert 'average_kl_divergence' in summary


class TestKLDivergence:
    """Testes de cálculo de KL divergence."""

    def test_kl_divergence_identical_distributions(self, validator):
        """Testar KL divergence com distribuições idênticas."""
        p = np.array([[0.5, 0.5], [0.7, 0.3]])
        q = np.array([[0.5, 0.5], [0.7, 0.3]])

        kl = validator._compute_kl_divergence(p, q)

        assert np.isclose(kl, 0.0, atol=1e-10)

    def test_kl_divergence_different_distributions(self, validator):
        """Testar KL divergence com distribuições diferentes."""
        p = np.array([[0.9, 0.1], [0.1, 0.9]])
        q = np.array([[0.5, 0.5], [0.5, 0.5]])

        kl = validator._compute_kl_divergence(p, q)

        assert kl > 0
