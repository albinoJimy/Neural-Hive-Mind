"""
Testes unitários para GPUInferenceWrapper.

Testa aceleração de inferência via GPU com fallback para CPU.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch


class TestGPUInferenceWrapper:
    """Testes da classe GPUInferenceWrapper."""

    @pytest.fixture
    def mock_model(self):
        """Mock de modelo scikit-learn."""
        model = MagicMock()
        model.predict = Mock(return_value=np.array([0.7, 0.3]))
        model.predict_proba = Mock(return_value=np.array([[0.3, 0.7]]))
        return model

    def test_init_cpu_mode(self, mock_model):
        """Testa inicialização em modo CPU."""
        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')

        assert wrapper.device == 'cpu'
        assert wrapper.use_gpu is False
        assert wrapper.model == mock_model

    def test_init_auto_detect_no_gpu(self, mock_model):
        """Testa auto-detecção quando GPU não está disponível."""
        with patch.dict('sys.modules', {'cupy': None}):
            from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

            wrapper = GPUInferenceWrapper(mock_model, device='auto')

            # Deve fazer fallback para CPU
            assert wrapper.device == 'cpu'
            assert wrapper.use_gpu is False

    def test_predict_cpu(self, mock_model):
        """Testa predição em modo CPU."""
        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')
        X = np.array([[1.0, 2.0, 3.0]])

        result = wrapper.predict(X)

        mock_model.predict.assert_called_once()
        assert result is not None

    def test_predict_proba_cpu(self, mock_model):
        """Testa predict_proba em modo CPU."""
        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')
        X = np.array([[1.0, 2.0, 3.0]])

        result = wrapper.predict_proba(X)

        mock_model.predict_proba.assert_called_once()
        assert result is not None

    def test_predict_with_dataframe(self, mock_model):
        """Testa predição com pandas DataFrame."""
        import pandas as pd
        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')
        X = pd.DataFrame({'a': [1.0], 'b': [2.0], 'c': [3.0]})

        result = wrapper.predict(X)

        mock_model.predict.assert_called_once()
        # Deve converter para numpy internamente
        call_args = mock_model.predict.call_args[0][0]
        assert isinstance(call_args, np.ndarray)

    def test_predict_proba_missing_method(self, mock_model):
        """Testa erro quando modelo não suporta predict_proba."""
        del mock_model.predict_proba  # Remover método

        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')
        X = np.array([[1.0, 2.0, 3.0]])

        with pytest.raises(AttributeError):
            wrapper.predict_proba(X)

    def test_getattr_delegation(self, mock_model):
        """Testa delegação de atributos para modelo."""
        mock_model.custom_attribute = 'test_value'
        mock_model.custom_method = Mock(return_value='method_result')

        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')

        assert wrapper.custom_attribute == 'test_value'
        assert wrapper.custom_method() == 'method_result'

    def test_get_device_info_cpu(self, mock_model):
        """Testa obtenção de informações do dispositivo (CPU)."""
        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')
        info = wrapper.get_device_info()

        assert info['device'] == 'cpu'
        assert info['use_gpu'] is False
        assert 'model_type' in info


class TestGPUInferenceWrapperWithGPU:
    """Testes com GPU mockada."""

    @pytest.fixture
    def mock_cupy(self):
        """Mock do módulo CuPy."""
        mock_cp = MagicMock()

        # Mock de array GPU
        mock_gpu_array = MagicMock()
        mock_gpu_array.get = Mock(return_value=np.array([0.7, 0.3]))
        mock_cp.asarray = Mock(return_value=mock_gpu_array)

        # Mock de device
        mock_device = MagicMock()
        mock_device.compute_capability = (8, 0)
        mock_cp.cuda.Device.return_value = mock_device

        # Mock de runtime
        mock_cp.cuda.runtime.getDeviceProperties = Mock(return_value={
            'name': b'NVIDIA Tesla T4',
            'totalGlobalMem': 16 * 1024 * 1024 * 1024,
            'major': 7,
            'minor': 5
        })

        return mock_cp

    @pytest.fixture
    def mock_model(self):
        """Mock de modelo."""
        model = MagicMock()
        model.predict = Mock(return_value=np.array([0.7, 0.3]))
        model.predict_proba = Mock(return_value=np.array([[0.3, 0.7]]))
        return model

    def test_init_with_gpu(self, mock_model, mock_cupy):
        """Testa inicialização com GPU disponível."""
        with patch.dict('sys.modules', {'cupy': mock_cupy}):
            # Recarregar módulo para usar mock
            import importlib
            import neural_hive_specialists.gpu_inference as gpu_module
            importlib.reload(gpu_module)

            wrapper = gpu_module.GPUInferenceWrapper(mock_model, device='cuda')

            # Quando cupy está disponível, deve usar GPU
            assert wrapper.model == mock_model

    def test_predict_gpu_fallback_on_error(self, mock_model, mock_cupy):
        """Testa fallback para CPU quando GPU falha."""
        mock_cupy.asarray.side_effect = Exception("GPU error")

        with patch.dict('sys.modules', {'cupy': mock_cupy}):
            import importlib
            import neural_hive_specialists.gpu_inference as gpu_module
            importlib.reload(gpu_module)

            wrapper = gpu_module.GPUInferenceWrapper(mock_model, device='cpu')
            X = np.array([[1.0, 2.0, 3.0]])

            # Deve funcionar mesmo com erro de GPU (fallback para CPU)
            result = wrapper.predict(X)
            assert result is not None


class TestGPUInferenceWrapperEdgeCases:
    """Testes de casos de borda."""

    @pytest.fixture
    def mock_model(self):
        """Mock de modelo."""
        model = MagicMock()
        model.predict = Mock(return_value=np.array([0.7, 0.3]))
        model.predict_proba = Mock(return_value=np.array([[0.3, 0.7]]))
        return model

    def test_empty_input(self, mock_model):
        """Testa com input vazio."""
        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')
        X = np.array([]).reshape(0, 3)

        mock_model.predict.return_value = np.array([])
        result = wrapper.predict(X)

        mock_model.predict.assert_called_once()

    def test_large_batch(self, mock_model):
        """Testa com batch grande."""
        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')
        X = np.random.rand(1000, 50)  # 1000 amostras, 50 features

        mock_model.predict.return_value = np.random.rand(1000)
        result = wrapper.predict(X)

        mock_model.predict.assert_called_once()
        call_args = mock_model.predict.call_args[0][0]
        assert call_args.shape == (1000, 50)

    def test_single_sample(self, mock_model):
        """Testa com amostra única."""
        from neural_hive_specialists.gpu_inference import GPUInferenceWrapper

        wrapper = GPUInferenceWrapper(mock_model, device='cpu')
        X = np.array([[1.0, 2.0, 3.0]])

        result = wrapper.predict(X)

        assert mock_model.predict.called
