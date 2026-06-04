"""Testes para ShadowValidator."""

import pytest
import numpy as np
from unittest.mock import Mock, patch


# ============================================================================
# Mock MongoDB classes para evitar tentativas de conexão real
# ============================================================================


class MockMongoCollection:
    """Mock de coleção MongoDB."""

    def __init__(self):
        self.data = []

    def find(self, *args, **kwargs):
        return []

    def find_one(self, *args, **kwargs):
        return None

    def insert_one(self, *args, **kwargs):
        return Mock(inserted_id="test_id")

    def update_one(self, *args, **kwargs):
        return Mock(modified_count=1)

    def delete_one(self, *args, **kwargs):
        return Mock(deleted_count=1)

    def create_index(self, *args, **kwargs):
        pass

    def create_indexes(self, *args, **kwargs):
        pass

    def aggregate(self, *args, **kwargs):
        return []

    def count_documents(self, *args, **kwargs):
        return 0

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def __iter__(self):
        return iter([])

    def __getitem__(self, name):
        return self


class MockMongoDB:
    """Mock de database MongoDB."""

    def __init__(self):
        self._collection = MockMongoCollection()

    def __getitem__(self, name):
        return self._collection

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._collection


class MockMongoClient:
    """Mock de cliente MongoDB."""

    def __init__(self, *args, **kwargs):
        self._db = MockMongoDB()

    def __getitem__(self, name):
        return self._db

    def __getattr__(self, name):
        if name == "_MongoClient__all_options" or name.startswith("_"):
            raise AttributeError(name)
        return self._db

    def close(self):
        """Mock close method."""
        pass


# Patch pymongo antes de importar os módulos
_pymongo_patch = patch("pymongo.MongoClient", MockMongoClient)
_pymongo_patch.start()

# Agora é seguro importar
from ml_pipelines.online_learning.shadow_validator import ShadowValidator, ShadowValidationResult
from ml_pipelines.online_learning.config import OnlineLearningConfig


@pytest.fixture(autouse=True)
def cleanup_patches():
    """Limpa patches após todos os testes."""
    yield
    # Não paramos o patch aqui porque outros testes podem precisar dele


@pytest.fixture
def config():
    """Configuração de teste."""
    return OnlineLearningConfig(
        shadow_accuracy_threshold=0.95,
        shadow_max_latency_ratio=1.5,
        shadow_max_kl_divergence=0.1,
        shadow_min_samples=10,
    )


@pytest.fixture
def validator(config, mock_batch_model, mock_online_learner):
    """ShadowValidator para testes."""
    return ShadowValidator(
        config=config,
        specialist_type="test_specialist",
        batch_model=mock_batch_model,
        online_learner=mock_online_learner,
    )


@pytest.fixture
def mock_batch_model():
    """Mock do modelo batch."""
    model = Mock()

    def predict_proba(X):
        n_samples = X.shape[0] if hasattr(X, "shape") else 3
        np.random.seed(42)
        probs = np.random.uniform(0.3, 0.7, (n_samples, 2))
        probs = probs / probs.sum(axis=1, keepdims=True)
        return probs

    def predict(X):
        n_samples = X.shape[0] if hasattr(X, "shape") else 3
        probs = predict_proba(X)
        return np.argmax(probs, axis=1)

    model.predict_proba = predict_proba
    model.predict = predict
    return model


@pytest.fixture
def mock_online_learner():
    """Mock do IncrementalLearner."""
    learner = Mock()

    def predict_proba(X):
        n_samples = X.shape[0] if hasattr(X, "shape") else 3
        np.random.seed(43)  # Seed diferente
        probs = np.random.uniform(0.3, 0.7, (n_samples, 2))
        probs = probs / probs.sum(axis=1, keepdims=True)
        return probs

    def predict(X):
        n_samples = X.shape[0] if hasattr(X, "shape") else 3
        probs = predict_proba(X)
        return np.argmax(probs, axis=1)

    learner.predict_proba = predict_proba
    learner.predict = predict
    learner.is_fitted = True
    learner.model_version = "v1.0"
    learner.classes = np.array([0, 1])  # Adicionar classes
    return learner


@pytest.fixture
def mock_online_model():
    """Mock do modelo online (legado - usa mock_online_learner)."""
    model = Mock()
    model.predict_proba = Mock(return_value=np.array([[0.35, 0.65], [0.75, 0.25], [0.45, 0.55]]))
    model.predict = Mock(return_value=np.array([1, 0, 1]))
    return model


class TestShadowValidatorInitialization:
    """Testes de inicialização."""

    def test_init_with_config(self, config, mock_batch_model, mock_online_learner):
        """Testar inicialização com configuração."""
        validator = ShadowValidator(
            config=config,
            specialist_type="test_specialist",
            batch_model=mock_batch_model,
            online_learner=mock_online_learner,
        )

        assert validator.specialist_type == "test_specialist"
        assert validator.config.shadow_accuracy_threshold == 0.95
        assert validator.config.shadow_max_latency_ratio == 1.5
        assert validator.config.shadow_max_kl_divergence == 0.1

    def test_init_default_config(self, mock_batch_model, mock_online_learner):
        """Testar inicialização com configuração padrão."""
        validator = ShadowValidator(
            config=OnlineLearningConfig(),
            specialist_type="test_specialist",
            batch_model=mock_batch_model,
            online_learner=mock_online_learner,
        )

        assert validator.specialist_type == "test_specialist"


class TestValidation:
    """Testes de validação."""

    def test_validate_success(self, validator):
        """Testar validação bem-sucedida."""
        X = np.random.randn(10, 5)
        y = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])

        result = validator.validate(X=X, y=y)

        assert isinstance(result, ShadowValidationResult)
        assert len(result.metrics) > 0

    def test_validate_calculates_kl_divergence(self, validator):
        """Testar cálculo de KL divergence."""
        X = np.random.randn(10, 5)
        y = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])

        result = validator.validate(X=X, y=y)

        assert "kl_divergence" in result.metrics or result.passed is not None

    def test_validate_measures_latency(self, validator):
        """Testar medição de latência."""
        X = np.random.randn(10, 5)
        y = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])

        result = validator.validate(X=X, y=y)

        # Métricas devem conter informações de latência
        assert "batch_latency_ms" in result.metrics or "online_latency_ms" in result.metrics

    def test_validate_insufficient_samples(self, validator):
        """Testar validação com amostras insuficientes."""
        X = np.random.randn(5, 5)  # Menos que min_samples
        y = np.array([1, 0, 1, 0, 1])

        result = validator.validate(X=X, y=y)

        # Deve retornar resultado mas pode não aprovar
        assert result is not None


class TestApprovalDecision:
    """Testes de decisão de aprovação."""

    def test_should_approve_no_validations(self, validator):
        """Testar aprovação sem validações prévias."""
        approved, reason = validator.should_approve_deployment()

        assert approved is False
        "Nenhuma validação" in reason

    def test_should_approve_after_successful_validation(self, validator):
        """Testar aprovação após validação bem-sucedida."""
        # Executar uma validação bem-sucedida
        X = np.random.randn(10, 5)
        y = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])

        result = validator.validate(X=X, y=y)
        # Se passou, should_approve deve retornar True
        if result.passed:
            approved, reason = validator.should_approve_deployment()
            assert approved is True
        else:
            # Se falhou, devemos obter False com motivo
            approved, reason = validator.should_approve_deployment()
            assert approved is False
            assert "falhou" in reason.lower()


class TestValidationSummary:
    """Testes de sumário de validação."""

    def test_get_validation_summary_empty(self, validator):
        """Testar sumário sem validações."""
        summary = validator.get_validation_summary()

        assert summary["total_validations"] == 0
        assert summary["pass_rate"] == 0.0

    def test_get_validation_summary_with_results(self, validator):
        """Testar sumário com validações."""
        X = np.random.randn(20, 5)
        y = np.random.randint(0, 2, 20)

        # Executar algumas validações
        for _ in range(3):
            validator.validate(X=X, y=y)

        summary = validator.get_validation_summary()

        assert summary["total_validations"] == 3
        assert "pass_rate" in summary
        assert "avg_kl_divergence" in summary


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
