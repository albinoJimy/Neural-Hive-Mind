"""
SHAPExplainer: Implementação completa de SHAP para produção.

Integra com FeatureExtractor para usar features estruturadas e gera
valores SHAP com background dataset representativo.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
import structlog
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import time

logger = structlog.get_logger(__name__)


class SHAPExplainer:
    """Explainer SHAP para modelos de especialistas."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa explainer SHAP.

        Args:
            config: Configuração com background_dataset_path, timeout_seconds, etc.
        """
        self.config = config
        self.background_data: Optional[pd.DataFrame] = None
        self.feature_names: List[str] = []
        self.timeout_seconds = config.get("shap_timeout_seconds", 5.0)

        self._load_background_dataset()

        logger.info(
            "SHAPExplainer initialized",
            background_samples=len(self.background_data)
            if self.background_data is not None
            else 0,
        )

    def _load_background_dataset(self):
        """Carrega dataset de background para SHAP."""
        background_path = self.config.get("shap_background_dataset_path")

        if background_path:
            try:
                self.background_data = pd.read_parquet(background_path)
                self.feature_names = list(self.background_data.columns)

                logger.info(
                    "Background dataset loaded",
                    path=background_path,
                    shape=self.background_data.shape,
                )
            except Exception as e:
                logger.error(
                    "Failed to load background dataset",
                    path=background_path,
                    error=str(e),
                )
                self.background_data = None
        else:
            logger.warning("No background dataset configured for SHAP")

    def explain(
        self, model: Any, features: Dict[str, Any], feature_names: List[str]
    ) -> Dict[str, Any]:
        """
        Gera explicação SHAP para predição do modelo.

        Args:
            model: Modelo ML carregado
            features: Features extraídas (agregated_features)
            feature_names: Nomes das features em ordem

        Returns:
            Dicionário com shap_values, base_value, feature_importances
        """
        if model is None:
            logger.warning("No model provided for SHAP")
            return {"method": "shap", "feature_importances": [], "error": "No model"}

        try:
            # Importar SHAP
            import shap

            # Executar com timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._compute_shap, model, features, feature_names
                )
                try:
                    result = future.result(timeout=self.timeout_seconds)
                    return result
                except FuturesTimeoutError:
                    logger.warning(
                        "SHAP computation timed out",
                        timeout_seconds=self.timeout_seconds,
                    )
                    return {
                        "method": "shap",
                        "feature_importances": [],
                        "error": "timeout",
                    }

        except ImportError:
            logger.error("SHAP library not installed. Install with: pip install shap")
            return {
                "method": "shap",
                "feature_importances": [],
                "error": "shap_not_installed",
            }
        except Exception as e:
            logger.error("SHAP explanation failed", error=str(e), exc_info=True)
            return {"method": "shap", "feature_importances": [], "error": str(e)}

    def _compute_shap(
        self, model: Any, features: Dict[str, Any], feature_names: List[str]
    ) -> Dict[str, Any]:
        """
        Computa valores SHAP (método auxiliar para timeout).

        Args:
            model: Modelo ML
            features: Features agregadas
            feature_names: Nomes das features

        Returns:
            Dicionário com valores SHAP e importâncias
        """
        import shap

        start_time = time.time()

        # Converter features para DataFrame
        feature_vector = [features.get(name, 0.0) for name in feature_names]
        input_df = pd.DataFrame([feature_vector], columns=feature_names)

        # Determinar tipo de explainer
        model_type = type(model).__name__.lower()

        if (
            "randomforest" in model_type
            or "gradientboosting" in model_type
            or "xgb" in model_type
        ):
            # TreeExplainer para modelos tree-based
            if self.background_data is not None and len(self.background_data) > 0:
                explainer = shap.TreeExplainer(
                    model,
                    self.background_data.sample(min(100, len(self.background_data))),
                )
            else:
                explainer = shap.TreeExplainer(model)
        else:
            # KernelExplainer para outros modelos
            if self.background_data is not None and len(self.background_data) > 0:
                background_sample = self.background_data.sample(
                    min(50, len(self.background_data))
                )
                explainer = shap.KernelExplainer(model.predict, background_sample)
            else:
                # Usar features atuais como background (fallback)
                explainer = shap.KernelExplainer(model.predict, input_df)

        # Calcular valores SHAP
        shap_values = explainer.shap_values(input_df)

        # Extrair base value e shap values
        if isinstance(shap_values, list):
            # Classificação multiclasse - pegar primeira classe
            shap_values_array = shap_values[0]
        else:
            shap_values_array = shap_values

        # Extrair base_value com tratamento robusto
        base_value = explainer.expected_value
        if isinstance(base_value, (list, np.ndarray)):
            # Converter para array NumPy e extrair escalar
            base_value_array = np.atleast_1d(base_value).flatten()
            base_value = float(base_value_array[0])
        else:
            # Pode ser np.number ou escalar Python
            base_value = float(np.asarray(base_value).item())

        # Converter para importâncias
        feature_importances = []
        # Garantir que temos array 1D
        shap_values_flat = np.atleast_1d(shap_values_array).flatten()

        for i, feature_name in enumerate(feature_names):
            # Extrair valor escalar robusto
            shap_value = float(np.asarray(shap_values_flat[i]).item())
            feature_value = features.get(feature_name, 0.0)
            # Converter feature_value para float escalar
            if isinstance(feature_value, (np.ndarray, list)):
                feature_value = float(np.asarray(feature_value).item())
            else:
                feature_value = float(feature_value)

            feature_importances.append(
                {
                    "feature_name": feature_name,
                    "shap_value": shap_value,
                    "feature_value": feature_value,
                    "contribution": "positive"
                    if shap_value > 0
                    else ("negative" if shap_value < 0 else "neutral"),
                    "importance": abs(shap_value),
                }
            )

        # Ordenar por importância absoluta
        feature_importances.sort(key=lambda x: x["importance"], reverse=True)

        computation_time = time.time() - start_time

        logger.info(
            "SHAP values computed",
            num_features=len(feature_importances),
            computation_time_ms=int(computation_time * 1000),
        )

        return {
            "method": "shap",
            "base_value": base_value,
            "feature_importances": feature_importances,
            "computation_time_ms": int(computation_time * 1000),
        }

    def get_top_features(
        self,
        shap_result: Dict[str, Any],
        top_n: int = 5,
        positive_only: bool = False,
        negative_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Retorna top N features mais importantes.

        Args:
            shap_result: Resultado do explain()
            top_n: Número de features para retornar
            positive_only: Retornar apenas contribuições positivas
            negative_only: Retornar apenas contribuições negativas

        Returns:
            Lista de features mais importantes
        """
        importances = shap_result.get("feature_importances", [])

        if positive_only:
            importances = [f for f in importances if f["contribution"] == "positive"]
        elif negative_only:
            importances = [f for f in importances if f["contribution"] == "negative"]

        return importances[:top_n]
