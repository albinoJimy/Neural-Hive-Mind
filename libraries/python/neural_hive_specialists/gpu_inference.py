"""
GPU Inference Wrapper: Acelera inferência de modelos usando CUDA.

Fornece fallback automático para CPU quando GPU não está disponível,
permitindo deployments híbridos.
"""

import numpy as np
import structlog
from typing import Any, Optional, Tuple

logger = structlog.get_logger(__name__)


class GPUInferenceWrapper:
    """Wrapper para inferência acelerada por GPU."""

    def __init__(self, model: Any, device: str = 'auto'):
        """
        Inicializa wrapper GPU.

        Args:
            model: Modelo scikit-learn ou similar
            device: 'cuda', 'cpu', ou 'auto' (detecta automaticamente)
        """
        self.model = model
        self.device = self._detect_device(device)
        self.use_gpu = self.device == 'cuda'
        self.cp = None  # CuPy module

        if self.use_gpu:
            try:
                import cupy as cp
                self.cp = cp
                # Verificar se GPU está acessível
                cp.cuda.Device(0).compute_capability
                logger.info(
                    "GPU acceleration enabled",
                    device=self.device,
                    gpu_name=cp.cuda.runtime.getDeviceProperties(0)['name'].decode()
                )
            except ImportError:
                logger.warning("CuPy not installed, falling back to CPU")
                self.use_gpu = False
                self.device = 'cpu'
            except Exception as e:
                logger.warning(
                    "GPU not available, falling back to CPU",
                    error=str(e)
                )
                self.use_gpu = False
                self.device = 'cpu'

        logger.info(
            "GPUInferenceWrapper initialized",
            device=self.device,
            use_gpu=self.use_gpu,
            model_type=type(model).__name__
        )

    def _detect_device(self, device: str) -> str:
        """
        Detecta dispositivo disponível.

        Args:
            device: 'auto', 'cuda', ou 'cpu'

        Returns:
            Dispositivo selecionado
        """
        if device == 'auto':
            try:
                import cupy as cp
                # Testar se GPU está acessível
                cp.cuda.Device(0).compute_capability
                return 'cuda'
            except Exception:
                return 'cpu'
        return device

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predição acelerada por GPU.

        Para modelos scikit-learn, transfere dados para GPU,
        executa predição e retorna resultados na CPU.

        Args:
            X: Features (numpy array ou pandas DataFrame)

        Returns:
            Predições (numpy array)
        """
        # Converter para numpy se necessário
        if hasattr(X, 'values'):  # pandas DataFrame
            X = X.values

        if self.use_gpu and self.cp is not None:
            try:
                # Transferir para GPU
                X_gpu = self.cp.asarray(X)

                # Verificar se modelo suporta CuPy arrays
                if hasattr(self.model, 'predict'):
                    # Tentar predição direta com GPU
                    try:
                        predictions_gpu = self.model.predict(X_gpu)
                        if hasattr(predictions_gpu, 'get'):  # CuPy array
                            return predictions_gpu.get()
                        return np.asarray(predictions_gpu)
                    except TypeError:
                        # Modelo não suporta CuPy, transferir de volta para CPU
                        X_cpu = X_gpu.get()
                        return self.model.predict(X_cpu)

            except Exception as e:
                logger.warning(
                    "GPU inference failed, falling back to CPU",
                    error=str(e)
                )
                return self.model.predict(X)
        else:
            return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Predição probabilística acelerada por GPU.

        Args:
            X: Features (numpy array ou pandas DataFrame)

        Returns:
            Probabilidades (numpy array)
        """
        # Converter para numpy se necessário
        if hasattr(X, 'values'):  # pandas DataFrame
            X = X.values

        if not hasattr(self.model, 'predict_proba'):
            raise AttributeError(
                f"Model {type(self.model).__name__} does not support predict_proba"
            )

        if self.use_gpu and self.cp is not None:
            try:
                X_gpu = self.cp.asarray(X)

                try:
                    proba_gpu = self.model.predict_proba(X_gpu)
                    if hasattr(proba_gpu, 'get'):  # CuPy array
                        return proba_gpu.get()
                    return np.asarray(proba_gpu)
                except TypeError:
                    # Modelo não suporta CuPy
                    X_cpu = X_gpu.get()
                    return self.model.predict_proba(X_cpu)

            except Exception as e:
                logger.warning(
                    "GPU predict_proba failed, falling back to CPU",
                    error=str(e)
                )
                return self.model.predict_proba(X)
        else:
            return self.model.predict_proba(X)

    def get_device_info(self) -> dict:
        """
        Retorna informações sobre o dispositivo.

        Returns:
            Dicionário com informações do dispositivo
        """
        info = {
            'device': self.device,
            'use_gpu': self.use_gpu,
            'model_type': type(self.model).__name__
        }

        if self.use_gpu and self.cp is not None:
            try:
                props = self.cp.cuda.runtime.getDeviceProperties(0)
                info.update({
                    'gpu_name': props['name'].decode(),
                    'gpu_memory_total_mb': props['totalGlobalMem'] // (1024 * 1024),
                    'gpu_compute_capability': f"{props['major']}.{props['minor']}"
                })
            except Exception:
                pass

        return info

    def __getattr__(self, name: str) -> Any:
        """
        Delega atributos não encontrados para o modelo subjacente.

        Permite que o wrapper seja usado como drop-in replacement.
        """
        return getattr(self.model, name)
