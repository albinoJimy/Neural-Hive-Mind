"""
Wrapper opcional para inferência em GPU usando ONNX Runtime.

Este módulo fornece uma camada de abstração para inferência em GPU
quando disponível, com fallback para CPU.
"""
from typing import Optional, Any, Dict
import logging

logger = logging.getLogger(__name__)


class GPUWrapper:
    """
    Wrapper para inferência em GPU.

    Detecta e usa GPU quando disponível, com fallback para CPU.
    """

    def __init__(
        self,
        enable_gpu: bool = False,
        gpu_memory_fraction: float = 0.8,
        device_id: int = 0,
    ):
        """
        Inicializa wrapper de GPU.

        Args:
            enable_gpu: Forçar uso de GPU
            gpu_memory_fraction: Fração de memória GPU a usar
            device_id: ID do dispositivo GPU
        """
        self.enable_gpu = enable_gpu
        self.gpu_memory_fraction = gpu_memory_fraction
        self.device_id = device_id
        self.gpu_available = False
        self.onnx_runtime = None

        self._detect_gpu()

    def _detect_gpu(self) -> None:
        """Detecta disponibilidade de GPU."""
        try:
            import onnxruntime as ort

            self.onnx_runtime = ort

            # Verificar providers disponíveis
            available_providers = ort.get_available_providers()
            logger.info(f"available_onnx_providers={available_providers}")

            if "CUDAExecutionProvider" in available_providers and self.enable_gpu:
                self.gpu_available = True
                logger.info(
                    "gpu_detected",
                    provider="CUDAExecutionProvider",
                    device_id=self.device_id,
                )
            else:
                logger.info("gpu_not_available_using_cpu")
        except ImportError:
            logger.warning("onnxruntime_not_installed_using_cpu")

    def get_inference_session(
        self,
        model_path: str,
    ) -> Optional[Any]:
        """
        Retorna sessão de inferência ONNX configurada.

        Args:
            model_path: Caminho para modelo ONNX

        Returns:
            Sessão ONNX Runtime ou None se não disponível
        """
        if self.onnx_runtime is None:
            return None

        try:
            # Configurar providers baseado em disponibilidade
            providers = ["CPUExecutionProvider"]
            if self.gpu_available:
                providers = [
                    (
                        "CUDAExecutionProvider",
                        {
                            "device_id": self.device_id,
                            "gpu_mem_limit": self.gpu_memory_fraction * 1024 * 1024 * 1024,  # GB para bytes
                        },
                    )
                ]

            session = self.onnx_runtime.InferenceSession(
                model_path,
                providers=providers,
            )
            logger.info(
                "onnx_session_created",
                providers=providers,
                model_path=model_path,
            )
            return session

        except Exception as e:
            logger.error(
                "onnx_session_creation_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def run_inference(
        self,
        session: Any,
        inputs: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Executa inferência usando sessão ONNX.

        Args:
            session: Sessão ONNX Runtime
            inputs: Dicionário de inputs

        Returns:
            Dicionário de outputs ou None em caso de erro
        """
        try:
            outputs = session.run(None, inputs)
            return outputs
        except Exception as e:
            logger.error(
                "onnx_inference_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    @property
    def device_info(self) -> Dict[str, Any]:
        """Retorna informações sobre o dispositivo."""
        return {
            "gpu_available": self.gpu_available,
            "enable_gpu": self.enable_gpu,
            "device_id": self.device_id,
            "memory_fraction": self.gpu_memory_fraction,
            "onnx_runtime_installed": self.onnx_runtime is not None,
        }


# Singleton
_gpu_wrapper: Optional[GPUWrapper] = None


def get_gpu_wrapper(
    enable_gpu: bool = False,
    gpu_memory_fraction: float = 0.8,
    device_id: int = 0,
) -> GPUWrapper:
    """
    Retorna instância singleton do GPUWrapper.

    Args:
        enable_gpu: Forçar uso de GPU
        gpu_memory_fraction: Fração de memória GPU
        device_id: ID do dispositivo GPU

    Returns:
        Instância de GPUWrapper
    """
    global _gpu_wrapper
    if _gpu_wrapper is None:
        _gpu_wrapper = GPUWrapper(enable_gpu, gpu_memory_fraction, device_id)
    return _gpu_wrapper
