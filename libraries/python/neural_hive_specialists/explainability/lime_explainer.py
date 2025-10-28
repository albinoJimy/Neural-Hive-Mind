"""
LIMEExplainer: Implementação completa de LIME para produção.

Integra com FeatureExtractor e gera explicações locais por perturbação
de features estruturadas.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
import structlog
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import time

logger = structlog.get_logger(__name__)


class LIMEExplainer:
    """Explainer LIME para modelos de especialistas."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa explainer LIME.

        Args:
            config: Configuração com num_samples, timeout_seconds, etc.
        """
        self.config = config
        self.num_samples = config.get('lime_num_samples', 1000)
        self.timeout_seconds = config.get('lime_timeout_seconds', 5.0)

        logger.info(
            "LIMEExplainer initialized",
            num_samples=self.num_samples
        )

    def explain(
        self,
        model: Any,
        features: Dict[str, Any],
        feature_names: List[str]
    ) -> Dict[str, Any]:
        """
        Gera explicação LIME para predição do modelo.

        Args:
            model: Modelo ML carregado
            features: Features extraídas (aggregated_features)
            feature_names: Nomes das features em ordem

        Returns:
            Dicionário com feature_importances baseadas em LIME
        """
        if model is None:
            logger.warning("No model provided for LIME")
            return {'method': 'lime', 'feature_importances': [], 'error': 'No model'}

        try:
            # Importar LIME
            from lime import lime_tabular

            # Executar com timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._compute_lime,
                    model,
                    features,
                    feature_names
                )
                try:
                    result = future.result(timeout=self.timeout_seconds)
                    return result
                except FuturesTimeoutError:
                    logger.warning(
                        "LIME computation timed out",
                        timeout_seconds=self.timeout_seconds
                    )
                    return {
                        'method': 'lime',
                        'feature_importances': [],
                        'error': 'timeout'
                    }

        except ImportError:
            logger.error("LIME library not installed. Install with: pip install lime")
            return {'method': 'lime', 'feature_importances': [], 'error': 'lime_not_installed'}
        except Exception as e:
            logger.error("LIME explanation failed", error=str(e), exc_info=True)
            return {'method': 'lime', 'feature_importances': [], 'error': str(e)}

    def _compute_lime(
        self,
        model: Any,
        features: Dict[str, Any],
        feature_names: List[str]
    ) -> Dict[str, Any]:
        """
        Computa valores LIME (método auxiliar para timeout).

        Args:
            model: Modelo ML
            features: Features agregadas
            feature_names: Nomes das features

        Returns:
            Dicionário com valores LIME e importâncias
        """
        from lime import lime_tabular

        start_time = time.time()

        # Converter features para array
        feature_vector = np.array([[features.get(name, 0.0) for name in feature_names]])

        # Criar training data sintético para LIME
        # LIME precisa entender a distribuição das features
        training_data = self._generate_training_data(features, feature_names)

        # Criar explainer
        explainer = lime_tabular.LimeTabularExplainer(
            training_data=training_data,
            feature_names=feature_names,
            mode='regression',  # ou 'classification' dependendo do modelo
            discretize_continuous=True
        )

        # Gerar explicação
        explanation = explainer.explain_instance(
            data_row=feature_vector[0],
            predict_fn=model.predict,
            num_features=len(feature_names),
            num_samples=self.num_samples
        )

        # Extrair importâncias
        feature_importances = []
        for feature_idx, weight in explanation.as_list():
            # feature_idx pode ser string "feature_name <= value" ou índice
            if isinstance(feature_idx, str):
                # Extrair nome da feature
                feature_name = feature_idx.split('<=')[0].split('>')[0].strip()
            else:
                feature_name = feature_names[feature_idx] if feature_idx < len(feature_names) else f"feature_{feature_idx}"

            feature_importances.append({
                'feature_name': feature_name,
                'lime_weight': float(weight),
                'feature_value': float(features.get(feature_name, 0.0)),
                'contribution': 'positive' if weight > 0 else ('negative' if weight < 0 else 'neutral'),
                'importance': abs(weight)
            })

        # Ordenar por importância absoluta
        feature_importances.sort(key=lambda x: x['importance'], reverse=True)

        computation_time = time.time() - start_time

        logger.info(
            "LIME values computed",
            num_features=len(feature_importances),
            computation_time_ms=int(computation_time * 1000)
        )

        return {
            'method': 'lime',
            'feature_importances': feature_importances,
            'computation_time_ms': int(computation_time * 1000),
            'intercept': float(explanation.intercept[0]) if hasattr(explanation, 'intercept') else 0.0
        }

    def _generate_training_data(
        self,
        features: Dict[str, Any],
        feature_names: List[str],
        num_samples: int = 100
    ) -> np.ndarray:
        """
        Gera training data sintético para LIME.

        Args:
            features: Features atuais
            feature_names: Nomes das features
            num_samples: Número de amostras a gerar

        Returns:
            Array numpy com training data
        """
        # Gerar amostras com perturbações gaussianas ao redor dos valores atuais
        training_data = []

        for _ in range(num_samples):
            sample = []
            for name in feature_names:
                value = features.get(name, 0.0)

                # Adicionar ruído gaussiano (10% do valor ou 0.1 se zero)
                noise_std = max(abs(value) * 0.1, 0.1)
                perturbed_value = value + np.random.normal(0, noise_std)

                # Garantir valores não-negativos para features que devem ser positivas
                if 'num_' in name or 'count' in name or 'size' in name:
                    perturbed_value = max(0, perturbed_value)

                sample.append(perturbed_value)

            training_data.append(sample)

        return np.array(training_data)

    def get_top_features(
        self,
        lime_result: Dict[str, Any],
        top_n: int = 5,
        positive_only: bool = False,
        negative_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retorna top N features mais importantes.

        Args:
            lime_result: Resultado do explain()
            top_n: Número de features para retornar
            positive_only: Retornar apenas contribuições positivas
            negative_only: Retornar apenas contribuições negativas

        Returns:
            Lista de features mais importantes
        """
        importances = lime_result.get('feature_importances', [])

        if positive_only:
            importances = [f for f in importances if f['contribution'] == 'positive']
        elif negative_only:
            importances = [f for f in importances if f['contribution'] == 'negative']

        return importances[:top_n]
