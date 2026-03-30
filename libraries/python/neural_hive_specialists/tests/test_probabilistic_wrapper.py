"""Testes para ProbabilisticModelWrapper."""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, MagicMock, patch

try:
    import mlflow
    from mlflow.pyfunc import PythonModelContext
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

from neural_hive_specialists.probabilistic_wrapper import ProbabilisticModelWrapper


@pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="mlflow not available")
@pytest.mark.unit
class TestProbabilisticModelWrapper:
    """Testes para ProbabilisticModelWrapper."""

    @pytest.fixture
    def mock_sklearn_model(self):
        """Mock de modelo sklearn."""
        model = MagicMock()
        model.predict_proba.return_value = np.array([[0.3, 0.7], [0.8, 0.2]])
        model.predict.return_value = np.array([1, 0])
        return model

    def test_load_context_loads_model(self, mock_sklearn_model):
        """Testa que load_context carrega o modelo."""
        with patch("joblib.load", return_value=mock_sklearn_model) as mock_load:
            from mlflow.pyfunc import PythonModelContext
            model_config = Mock()
            artifacts = {"sklearn_model": "/path/to/model.pkl"}
            context = PythonModelContext(model_config=model_config, artifacts=artifacts)

            wrapper = ProbabilisticModelWrapper()
            wrapper.load_context(context)

            mock_load.assert_called_once_with("/path/to/model.pkl")
            assert wrapper._model is mock_sklearn_model

    def test_predict_returns_probabilities(self, mock_sklearn_model):
        """Testa que predict retorna probabilidades."""
        with patch("joblib.load", return_value=mock_sklearn_model):
            from mlflow.pyfunc import PythonModelContext
            model_config = Mock()
            artifacts = {"sklearn_model": "/path/to/model.pkl"}
            context = PythonModelContext(model_config=model_config, artifacts=artifacts)

            wrapper = ProbabilisticModelWrapper()
            wrapper.load_context(context)

            model_input = pd.DataFrame({"feature1": [1, 2], "feature2": [3, 4]})
            result = wrapper.predict(None, model_input)

            np.testing.assert_array_equal(result, np.array([[0.3, 0.7], [0.8, 0.2]]))

    def test_predict_with_params(self, mock_sklearn_model):
        """Testa predict com parâmetros."""
        with patch("joblib.load", return_value=mock_sklearn_model):
            from mlflow.pyfunc import PythonModelContext
            model_config = Mock()
            artifacts = {"sklearn_model": "/path/to/model.pkl"}
            context = PythonModelContext(model_config=model_config, artifacts=artifacts)

            wrapper = ProbabilisticModelWrapper()
            wrapper.load_context(context)

            model_input = pd.DataFrame({"feature1": [1, 2]})
            params = {"some_param": "value"}

            result = wrapper.predict(None, model_input, params)

            np.testing.assert_array_equal(result, np.array([[0.3, 0.7], [0.8, 0.2]]))

    def test_predict_discrete_returns_labels(self, mock_sklearn_model):
        """Testa predict_discrete retorna labels discretos."""
        with patch("joblib.load", return_value=mock_sklearn_model):
            from mlflow.pyfunc import PythonModelContext
            model_config = Mock()
            artifacts = {"sklearn_model": "/path/to/model.pkl"}
            context = PythonModelContext(model_config=model_config, artifacts=artifacts)

            wrapper = ProbabilisticModelWrapper()
            wrapper.load_context(context)

            model_input = pd.DataFrame({"feature1": [1, 2], "feature2": [3, 4]})
            result = wrapper.predict_discrete(model_input)

            np.testing.assert_array_equal(result, np.array([1, 0]))

    def test_sklearn_model_property(self, mock_sklearn_model):
        """Testa acesso ao modelo sklearn subjacente."""
        with patch("joblib.load", return_value=mock_sklearn_model):
            from mlflow.pyfunc import PythonModelContext
            model_config = Mock()
            artifacts = {"sklearn_model": "/path/to/model.pkl"}
            context = PythonModelContext(model_config=model_config, artifacts=artifacts)

            wrapper = ProbabilisticModelWrapper()
            wrapper.load_context(context)

            assert wrapper.sklearn_model is mock_sklearn_model


@pytest.mark.unit
class TestProbabilisticModelWrapperNoMlflow:
    """Testes que não dependem de mlflow estar instalado."""

    def test_class_exists(self):
        """Testa que a classe pode ser importada."""
        from neural_hive_specialists.probabilistic_wrapper import ProbabilisticModelWrapper
        assert ProbabilisticModelWrapper is not None

    def test_class_is_pyfunc_model(self):
        """Testa que ProbabilisticModelWrapper herda de PythonModel."""
        from neural_hive_specialists.probabilistic_wrapper import ProbabilisticModelWrapper
        try:
            import mlflow.pyfunc
            assert issubclass(ProbabilisticModelWrapper, mlflow.pyfunc.PythonModel)
        except ImportError:
            pass  # mlflow não instalado
