#!/usr/bin/env python3
"""
DataQualityValidator: Validação avançada de qualidade de dados para treinamento ML.

Este módulo implementa validações abrangentes de qualidade de dados:
- Missing values e sparsity de features
- Detecção de outliers (IQR)
- Análise de desbalanceamento de labels
- Correlação de features (detectar redundância)
- Validação de schema
- Geração de relatórios estruturados para MLflow

Complementa o RealDataCollector com validações avançadas sem duplicar código.
"""

import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import structlog
import pandas as pd
import numpy as np

logger = structlog.get_logger(__name__)


class DataQualityError(Exception):
    """Qualidade dos dados abaixo do threshold aceitável."""
    pass


class DataQualityValidator:
    """
    Validador de qualidade de dados para pipelines de ML.

    Implementa validações avançadas de qualidade incluindo:
    - Missing values
    - Feature sparsity
    - Outliers (IQR)
    - Label imbalance
    - Feature correlation
    - Schema validation

    Gera relatórios estruturados compatíveis com MLflow artifacts.
    """

    VERSION = "1.0.0"

    def __init__(
        self,
        max_missing_pct: Optional[float] = None,
        max_sparsity_pct: Optional[float] = None,
        max_outlier_pct: Optional[float] = None,
        min_class_pct: Optional[float] = None,
        max_correlation: Optional[float] = None
    ):
        """
        Inicializa o validador com thresholds configuráveis.

        Args:
            max_missing_pct: Máximo % de missing values por feature (default: 5.0)
            max_sparsity_pct: Máximo % de features sempre zero (default: 50.0)
            max_outlier_pct: Máximo % de outliers por feature (default: 10.0)
            min_class_pct: Mínimo % de cada classe (default: 5.0)
            max_correlation: Máxima correlação entre features (default: 0.95)
        """
        # Carregar de variáveis de ambiente ou usar defaults
        self.max_missing_pct = max_missing_pct if max_missing_pct is not None else float(
            os.getenv('DATA_QUALITY_MAX_MISSING_PCT', '5.0')
        )
        self.max_sparsity_pct = max_sparsity_pct if max_sparsity_pct is not None else float(
            os.getenv('DATA_QUALITY_MAX_SPARSITY_PCT', '50.0')
        )
        self.max_outlier_pct = max_outlier_pct if max_outlier_pct is not None else float(
            os.getenv('DATA_QUALITY_MAX_OUTLIER_PCT', '10.0')
        )
        self.min_class_pct = min_class_pct if min_class_pct is not None else float(
            os.getenv('DATA_QUALITY_MIN_CLASS_PCT', '5.0')
        )
        self.max_correlation = max_correlation if max_correlation is not None else float(
            os.getenv('DATA_QUALITY_MAX_CORRELATION', '0.95')
        )

        logger.info(
            "DataQualityValidator inicializado",
            max_missing_pct=self.max_missing_pct,
            max_sparsity_pct=self.max_sparsity_pct,
            max_outlier_pct=self.max_outlier_pct,
            min_class_pct=self.min_class_pct,
            max_correlation=self.max_correlation
        )

    def validate(
        self,
        df: pd.DataFrame,
        feature_names: List[str],
        label_column: str = 'label'
    ) -> Dict[str, Any]:
        """
        Executa validação completa de qualidade dos dados.

        Args:
            df: DataFrame com features e label
            feature_names: Lista de nomes de features esperadas
            label_column: Nome da coluna de label (default: 'label')

        Returns:
            Dicionário com resultados detalhados de validação
        """
        validation_timestamp = datetime.utcnow().isoformat() + 'Z'

        # Identificar colunas de features presentes
        feature_cols = [col for col in feature_names if col in df.columns]

        # Executar validações individuais
        missing_results = self._validate_missing_values(df, feature_cols)
        sparsity_results = self._validate_sparsity(df, feature_cols)
        outlier_results = self._validate_outliers(df, feature_cols)
        label_results = self._validate_label_imbalance(df, label_column)
        correlation_results = self._validate_feature_correlation(df, feature_cols)
        schema_results = self._validate_schema(df, feature_names)

        # Calcular score de qualidade
        quality_score = self._calculate_quality_score(
            missing_results=missing_results,
            sparsity_results=sparsity_results,
            outlier_results=outlier_results,
            label_results=label_results,
            correlation_results=correlation_results,
            schema_results=schema_results
        )

        # Determinar se passou nas validações (inclui todos os thresholds)
        passed = (
            quality_score >= 0.6 and
            not missing_results['threshold_exceeded'] and
            not sparsity_results['threshold_exceeded'] and
            not outlier_results['threshold_exceeded'] and
            not label_results.get('underrepresented_classes') and
            not correlation_results.get('redundant_features_detected') and
            schema_results['schema_valid']
        )

        # Gerar warnings e recommendations
        warnings = self._collect_warnings(
            missing_results, sparsity_results, outlier_results,
            label_results, correlation_results, schema_results
        )
        recommendations = self._generate_recommendations(
            missing_results, sparsity_results, outlier_results,
            label_results, correlation_results, schema_results
        )

        result = {
            'validation_timestamp': validation_timestamp,
            'dataset_shape': (len(df), len(feature_cols)),
            'quality_score': round(quality_score, 3),
            'passed': passed,
            'missing_values': missing_results,
            'sparsity': sparsity_results,
            'outliers': outlier_results,
            'label_imbalance': label_results,
            'feature_correlation': correlation_results,
            'schema_validation': schema_results,
            'warnings': warnings,
            'recommendations': recommendations
        }

        logger.info(
            "Validação de qualidade concluída",
            quality_score=quality_score,
            passed=passed,
            num_warnings=len(warnings)
        )

        return result

    def _validate_missing_values(
        self,
        df: pd.DataFrame,
        feature_cols: List[str]
    ) -> Dict[str, Any]:
        """Valida missing values por feature."""
        features_with_missing = {}

        for col in feature_cols:
            missing_pct = df[col].isna().mean() * 100
            if missing_pct > 0:
                features_with_missing[col] = round(missing_pct, 2)

        max_missing = max(features_with_missing.values()) if features_with_missing else 0.0

        return {
            'features_with_missing': features_with_missing,
            'max_missing_pct': round(max_missing, 2),
            'threshold_exceeded': max_missing > self.max_missing_pct,
            'threshold': self.max_missing_pct
        }

    def _validate_sparsity(
        self,
        df: pd.DataFrame,
        feature_cols: List[str]
    ) -> Dict[str, Any]:
        """Detecta features sempre zero (sparse)."""
        sparse_features = []

        for col in feature_cols:
            if (df[col] == 0.0).all():
                sparse_features.append(col)

        sparsity_rate = (len(sparse_features) / len(feature_cols) * 100) if feature_cols else 0.0

        return {
            'sparse_features': sparse_features,
            'sparse_features_count': len(sparse_features),
            'sparsity_rate': round(sparsity_rate, 2),
            'threshold_exceeded': sparsity_rate > self.max_sparsity_pct,
            'threshold': self.max_sparsity_pct
        }

    def _validate_outliers(
        self,
        df: pd.DataFrame,
        feature_cols: List[str]
    ) -> Dict[str, Any]:
        """Detecta outliers usando IQR."""
        features_with_outliers = {}

        for col in feature_cols:
            if df[col].dtype not in ['float64', 'int64', 'float32', 'int32']:
                continue

            # Ignorar features sem variância
            if df[col].std() == 0:
                continue

            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1

            if IQR > 0:
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR

                outlier_mask = (df[col] < lower_bound) | (df[col] > upper_bound)
                outlier_pct = outlier_mask.mean() * 100

                if outlier_pct > 0:
                    features_with_outliers[col] = round(outlier_pct, 2)

        max_outlier = max(features_with_outliers.values()) if features_with_outliers else 0.0

        return {
            'features_with_outliers': features_with_outliers,
            'max_outlier_pct': round(max_outlier, 2),
            'threshold_exceeded': max_outlier > self.max_outlier_pct,
            'threshold': self.max_outlier_pct
        }

    def _validate_label_imbalance(
        self,
        df: pd.DataFrame,
        label_column: str
    ) -> Dict[str, Any]:
        """Valida balanceamento de labels."""
        if label_column not in df.columns:
            return {
                'distribution': {},
                'percentages': {},
                'underrepresented_classes': [],
                'dominant_classes': [],
                'is_balanced': False,
                'error': f"Coluna '{label_column}' não encontrada"
            }

        # Calcular distribuição
        distribution = df[label_column].value_counts().to_dict()
        total = len(df)

        # Converter chaves para string para JSON serialization
        distribution = {str(k): int(v) for k, v in distribution.items()}

        percentages = {
            label: round((count / total) * 100, 2)
            for label, count in distribution.items()
        }

        # Detectar classes subrepresentadas e dominantes
        underrepresented = [
            label for label, pct in percentages.items()
            if pct < self.min_class_pct
        ]
        dominant = [
            label for label, pct in percentages.items()
            if pct > 80.0
        ]

        is_balanced = len(underrepresented) == 0 and len(dominant) == 0

        return {
            'distribution': distribution,
            'percentages': percentages,
            'underrepresented_classes': underrepresented,
            'dominant_classes': dominant,
            'is_balanced': is_balanced,
            'min_class_threshold': self.min_class_pct
        }

    def _validate_feature_correlation(
        self,
        df: pd.DataFrame,
        feature_cols: List[str]
    ) -> Dict[str, Any]:
        """Detecta features altamente correlacionadas."""
        if len(feature_cols) < 2:
            return {
                'highly_correlated_pairs': [],
                'max_correlation_found': 0.0,
                'redundant_features_detected': False,
                'threshold': self.max_correlation
            }

        # Filtrar apenas colunas numéricas que existem
        numeric_cols = [
            col for col in feature_cols
            if col in df.columns and df[col].dtype in ['float64', 'int64', 'float32', 'int32']
        ]

        if len(numeric_cols) < 2:
            return {
                'highly_correlated_pairs': [],
                'max_correlation_found': 0.0,
                'redundant_features_detected': False,
                'threshold': self.max_correlation
            }

        # Calcular matriz de correlação
        try:
            corr_matrix = df[numeric_cols].corr(method='pearson')
        except Exception as e:
            logger.warning("Falha ao calcular correlação", error=str(e))
            return {
                'highly_correlated_pairs': [],
                'max_correlation_found': 0.0,
                'redundant_features_detected': False,
                'threshold': self.max_correlation,
                'error': str(e)
            }

        # Encontrar pares altamente correlacionados
        highly_correlated = []
        max_corr = 0.0

        for i, col1 in enumerate(numeric_cols):
            for col2 in numeric_cols[i + 1:]:
                corr_value = abs(corr_matrix.loc[col1, col2])

                if not np.isnan(corr_value):
                    max_corr = max(max_corr, corr_value)

                    if corr_value > self.max_correlation:
                        highly_correlated.append([col1, col2, round(corr_value, 3)])

        return {
            'highly_correlated_pairs': highly_correlated,
            'max_correlation_found': round(max_corr, 3),
            'redundant_features_detected': len(highly_correlated) > 0,
            'threshold': self.max_correlation
        }

    def _validate_schema(
        self,
        df: pd.DataFrame,
        expected_features: List[str]
    ) -> Dict[str, Any]:
        """Valida schema do DataFrame (correspondência exata)."""
        expected_set = set(expected_features)
        actual_set = set(df.columns)

        # Colunas de metadata que são permitidas além das features esperadas
        metadata_cols = {'label', 'opinion_id', 'plan_id', 'specialist_type', 'created_at', 'human_rating'}

        missing_features = list(expected_set - actual_set)
        extra_features = [
            col for col in actual_set - expected_set
            if col not in metadata_cols
        ]

        # Schema válido requer correspondência exata: sem features faltantes E sem features extras
        schema_valid = len(missing_features) == 0 and len(extra_features) == 0

        return {
            'missing_features': missing_features,
            'extra_features': extra_features,
            'schema_valid': schema_valid,
            'expected_count': len(expected_features),
            'actual_count': len([col for col in df.columns if col in expected_features])
        }

    def _calculate_quality_score(
        self,
        missing_results: Dict,
        sparsity_results: Dict,
        outlier_results: Dict,
        label_results: Dict,
        correlation_results: Dict,
        schema_results: Dict
    ) -> float:
        """
        Calcula score agregado de qualidade (0.0-1.0).

        Penalidades:
        - Missing values: proporcional à média de missing %
        - Sparsity: proporcional à taxa de sparsity
        - Outliers: proporcional à média de outlier %
        - Label imbalance: penalidade fixa (0.3) se classes < 5% ou > 80%
        - Correlação: penalidade (0.2) se features redundantes
        - Schema: penalidade fixa (0.4) se inválido
        """
        quality_score = 1.0

        # Penalidade por missing values
        if missing_results['features_with_missing']:
            avg_missing = sum(missing_results['features_with_missing'].values()) / len(
                missing_results['features_with_missing']
            )
            quality_score -= min(0.2, avg_missing / 100)

        # Penalidade por sparsity
        quality_score -= min(0.3, sparsity_results['sparsity_rate'] / 200)

        # Penalidade por outliers
        if outlier_results['features_with_outliers']:
            avg_outliers = sum(outlier_results['features_with_outliers'].values()) / len(
                outlier_results['features_with_outliers']
            )
            quality_score -= min(0.2, avg_outliers / 100)

        # Penalidade por label imbalance
        if label_results.get('underrepresented_classes') or label_results.get('dominant_classes'):
            quality_score -= 0.3

        # Penalidade por correlação alta
        if correlation_results.get('redundant_features_detected'):
            quality_score -= 0.2

        # Penalidade por schema inválido
        if not schema_results.get('schema_valid', True):
            quality_score -= 0.4

        return max(0.0, quality_score)

    def _collect_warnings(
        self,
        missing_results: Dict,
        sparsity_results: Dict,
        outlier_results: Dict,
        label_results: Dict,
        correlation_results: Dict,
        schema_results: Dict
    ) -> List[str]:
        """Coleta warnings de todas as validações."""
        warnings = []

        # Missing values
        if missing_results['threshold_exceeded']:
            warnings.append(
                f"Features com missing values acima do limite ({self.max_missing_pct}%): "
                f"{list(missing_results['features_with_missing'].keys())}"
            )

        # Sparsity
        if sparsity_results['threshold_exceeded']:
            warnings.append(
                f"Taxa de sparsity ({sparsity_results['sparsity_rate']:.1f}%) excede limite "
                f"({self.max_sparsity_pct}%)"
            )

        # Outliers
        high_outlier_features = {
            k: v for k, v in outlier_results.get('features_with_outliers', {}).items()
            if v > self.max_outlier_pct
        }
        if high_outlier_features:
            warnings.append(
                f"Features com outliers acima do limite ({self.max_outlier_pct}%): "
                f"{list(high_outlier_features.keys())}"
            )

        # Label imbalance
        if label_results.get('underrepresented_classes'):
            warnings.append(
                f"Classes subrepresentadas (< {self.min_class_pct}%): "
                f"{label_results['underrepresented_classes']}"
            )
        if label_results.get('dominant_classes'):
            warnings.append(
                f"Classes dominantes (> 80%): {label_results['dominant_classes']}"
            )

        # Correlação
        if correlation_results.get('highly_correlated_pairs'):
            pairs_str = ', '.join([
                f"{p[0]}-{p[1]} (r={p[2]})"
                for p in correlation_results['highly_correlated_pairs'][:5]
            ])
            warnings.append(f"Features altamente correlacionadas: {pairs_str}")

        # Schema
        if schema_results.get('missing_features'):
            warnings.append(
                f"Features ausentes no dataset: {schema_results['missing_features']}"
            )
        if schema_results.get('extra_features'):
            warnings.append(
                f"Features extras não esperadas no dataset: {schema_results['extra_features']}"
            )

        return warnings

    def _generate_recommendations(
        self,
        missing_results: Dict,
        sparsity_results: Dict,
        outlier_results: Dict,
        label_results: Dict,
        correlation_results: Dict,
        schema_results: Dict
    ) -> List[str]:
        """Gera recomendações acionáveis baseadas em problemas detectados."""
        recommendations = []

        # Missing values
        high_missing = {
            k: v for k, v in missing_results.get('features_with_missing', {}).items()
            if v > self.max_missing_pct
        }
        if high_missing:
            features_list = ', '.join(list(high_missing.keys())[:5])
            recommendations.append(
                f"Considere imputação ou remoção de features com > {self.max_missing_pct}% missing: "
                f"{features_list}"
            )

        # Sparsity
        if sparsity_results.get('sparse_features'):
            features_list = ', '.join(sparsity_results['sparse_features'][:5])
            recommendations.append(
                f"Features sempre zero podem ser removidas: {features_list}"
            )

        # Outliers
        high_outlier = {
            k: v for k, v in outlier_results.get('features_with_outliers', {}).items()
            if v > self.max_outlier_pct
        }
        if high_outlier:
            features_list = ', '.join(list(high_outlier.keys())[:5])
            recommendations.append(
                f"Considere transformação (log, box-cox) ou clipping para features com outliers: "
                f"{features_list}"
            )

        # Label imbalance
        if label_results.get('underrepresented_classes'):
            recommendations.append(
                f"Aplicar técnicas de balanceamento (SMOTE, class_weight) para classes: "
                f"{label_results['underrepresented_classes']}"
            )
        if label_results.get('dominant_classes'):
            recommendations.append(
                "Considerar undersampling da classe dominante ou coletar mais dados de classes minoritárias"
            )

        # Correlação
        if correlation_results.get('highly_correlated_pairs'):
            # Sugerir remoção do segundo elemento de cada par
            to_remove = set()
            for pair in correlation_results['highly_correlated_pairs']:
                to_remove.add(pair[1])  # Segundo elemento do par
            if to_remove:
                recommendations.append(
                    f"Remover features redundantes (alta correlação): {list(to_remove)[:5]}"
                )

        # Schema
        if schema_results.get('missing_features'):
            recommendations.append(
                f"Adicionar features ausentes ao pipeline de extração: "
                f"{schema_results['missing_features'][:5]}"
            )

        return recommendations

    def _ensure_json_serializable(self, obj: Any) -> Any:
        """Converte tipos numpy para tipos Python nativos para serialização JSON."""
        if isinstance(obj, dict):
            return {k: self._ensure_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._ensure_json_serializable(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._ensure_json_serializable(item) for item in obj)
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, (np.bool_,)):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    def generate_mlflow_report(
        self,
        validation_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Transforma resultados de validação em formato otimizado para MLflow artifact.

        Args:
            validation_results: Resultados de validate()

        Returns:
            Dicionário pronto para mlflow.log_dict()
        """
        report = {
            'metadata': {
                'validator_version': self.VERSION,
                'validation_timestamp': validation_results.get('validation_timestamp'),
                'dataset_shape': validation_results.get('dataset_shape'),
                'configuration': {
                    'max_missing_pct': self.max_missing_pct,
                    'max_sparsity_pct': self.max_sparsity_pct,
                    'max_outlier_pct': self.max_outlier_pct,
                    'min_class_pct': self.min_class_pct,
                    'max_correlation': self.max_correlation
                }
            },
            'quality_score': validation_results.get('quality_score'),
            'passed': validation_results.get('passed'),
            'validations': {
                'missing_values': validation_results.get('missing_values'),
                'sparsity': validation_results.get('sparsity'),
                'outliers': validation_results.get('outliers'),
                'label_imbalance': validation_results.get('label_imbalance'),
                'feature_correlation': validation_results.get('feature_correlation'),
                'schema_validation': validation_results.get('schema_validation')
            },
            'warnings': validation_results.get('warnings', []),
            'recommendations': validation_results.get('recommendations', []),
            'interpretation': {
                'quality_score_range': '[0.0, 1.0], 1.0 = perfeito',
                'thresholds': {
                    'excellent': '>= 0.9',
                    'good': '>= 0.75',
                    'acceptable': '>= 0.6',
                    'poor': '< 0.6'
                },
                'validation_meanings': {
                    'missing_values': 'Porcentagem de valores nulos por feature',
                    'sparsity': 'Features que são sempre zero',
                    'outliers': 'Valores fora de 1.5*IQR dos quartis',
                    'label_imbalance': 'Distribuição de classes no target',
                    'feature_correlation': 'Correlação de Pearson entre features',
                    'schema_validation': 'Conformidade com schema esperado'
                }
            }
        }

        # Garantir que todos os valores são serializáveis para JSON
        return self._ensure_json_serializable(report)

    def validate_and_raise(
        self,
        df: pd.DataFrame,
        feature_names: List[str],
        min_quality_score: Optional[float] = None,
        label_column: str = 'label'
    ) -> Dict[str, Any]:
        """
        Executa validação e lança exceção se qualidade insuficiente.

        Args:
            df: DataFrame com features e label
            feature_names: Lista de nomes de features esperadas
            min_quality_score: Score mínimo aceitável (default: 0.6)
            label_column: Nome da coluna de label

        Returns:
            Resultados de validação se passou

        Raises:
            DataQualityError: Se qualidade abaixo do threshold
        """
        if min_quality_score is None:
            min_quality_score = float(os.getenv('DATA_QUALITY_MIN_SCORE', '0.6'))

        validation_results = self.validate(df, feature_names, label_column)

        if validation_results['quality_score'] < min_quality_score or not validation_results['passed']:
            error_msg = (
                f"Qualidade dos dados insuficiente. "
                f"Score: {validation_results['quality_score']:.2f} (mínimo: {min_quality_score:.2f}). "
                f"Passed: {validation_results['passed']}. "
            )

            if validation_results['warnings']:
                error_msg += f"Warnings: {validation_results['warnings']}. "

            if validation_results['recommendations']:
                error_msg += f"Recomendações: {validation_results['recommendations']}"

            logger.error(
                "Validação de qualidade falhou",
                quality_score=validation_results['quality_score'],
                min_required=min_quality_score,
                passed=validation_results['passed'],
                warnings=validation_results['warnings']
            )

            raise DataQualityError(error_msg)

        return validation_results
