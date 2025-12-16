"""
Wrapper pyfunc para modelos sklearn que expõe predict_proba() como predict().

Este módulo permite que modelos sklearn registrados no MLflow retornem
probabilidades via interface pyfunc padrão (predict), alinhando o contrato
da signature com o comportamento real de inferência.
"""

import mlflow
import numpy as np
import pandas as pd
from typing import Any


class ProbabilisticModelWrapper(mlflow.pyfunc.PythonModel):
    """
    Wrapper que transforma predict() em predict_proba() para modelos sklearn.

    Quando carregado via mlflow.pyfunc.load_model(), o método predict()
    retornará probabilidades [n_samples, n_classes] em vez de labels discretos.
    """

    def load_context(self, context: mlflow.pyfunc.PythonModelContext) -> None:
        """
        Carrega o modelo sklearn do artifact path.

        Args:
            context: Contexto do modelo pyfunc contendo artifacts
        """
        import joblib
        model_path = context.artifacts["sklearn_model"]
        self._model = joblib.load(model_path)

    def predict(
        self,
        context: mlflow.pyfunc.PythonModelContext,
        model_input: pd.DataFrame,
        params: dict = None
    ) -> np.ndarray:
        """
        Retorna probabilidades via predict_proba() do modelo sklearn subjacente.

        Args:
            context: Contexto do modelo pyfunc
            model_input: DataFrame com features de entrada
            params: Parâmetros opcionais (não utilizados)

        Returns:
            Array de probabilidades [n_samples, n_classes]
        """
        return self._model.predict_proba(model_input)

    def predict_discrete(self, model_input: pd.DataFrame) -> np.ndarray:
        """
        Método auxiliar para obter predições discretas (labels) se necessário.

        Args:
            model_input: DataFrame com features de entrada

        Returns:
            Array de labels discretos [n_samples]
        """
        return self._model.predict(model_input)

    @property
    def sklearn_model(self) -> Any:
        """
        Acesso direto ao modelo sklearn subjacente para casos especiais.

        Returns:
            Modelo sklearn original
        """
        return self._model
