#!/usr/bin/env python3
"""
Testes unitários para DataQualityValidator.

Cobre casos principais de validação de qualidade de dados:
- Dados perfeitos
- Missing values
- Label imbalance
- Feature correlation
- Schema mismatch
- Geração de relatórios MLflow
- validate_and_raise
"""

import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Adicionar path para imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_quality_validator import DataQualityValidator, DataQualityError


class TestDataQualityValidator:
    """Testes para DataQualityValidator."""

    @pytest.fixture
    def validator(self):
        """Instância de validador com configurações default."""
        return DataQualityValidator(
            max_missing_pct=5.0,
            max_sparsity_pct=50.0,
            max_outlier_pct=10.0,
            min_class_pct=5.0,
            max_correlation=0.95
        )

    @pytest.fixture
    def feature_names(self):
        """Lista de nomes de features para testes."""
        return ['feature_a', 'feature_b', 'feature_c', 'feature_d', 'feature_e']

    @pytest.fixture
    def perfect_data(self, feature_names):
        """Dataset perfeito sem problemas de qualidade."""
        np.random.seed(42)
        n_samples = 300

        data = {
            name: np.random.randn(n_samples) for name in feature_names
        }
        # Labels balanceados: 100 de cada classe
        data['label'] = [0] * 100 + [1] * 100 + [2] * 100

        return pd.DataFrame(data)

    def test_validate_perfect_data(self, validator, perfect_data, feature_names):
        """Dataset perfeito deve ter quality_score=1.0 e passed=True."""
        result = validator.validate(perfect_data, feature_names)

        assert result['passed'] is True
        assert result['quality_score'] >= 0.9, f"Expected >= 0.9, got {result['quality_score']}"
        assert len(result['warnings']) == 0
        assert result['missing_values']['threshold_exceeded'] is False
        assert result['sparsity']['threshold_exceeded'] is False
        assert result['label_imbalance']['is_balanced'] is True
        assert result['schema_validation']['schema_valid'] is True

    def test_validate_missing_values(self, validator, feature_names):
        """Dataset com missing values deve ser detectado."""
        np.random.seed(42)
        n_samples = 100

        data = {name: np.random.randn(n_samples) for name in feature_names}
        data['label'] = np.random.randint(0, 3, n_samples)

        # Introduzir 15% de missing values em feature_a
        mask = np.random.random(n_samples) < 0.15
        data['feature_a'] = np.where(mask, np.nan, data['feature_a'])

        df = pd.DataFrame(data)
        result = validator.validate(df, feature_names)

        assert 'feature_a' in result['missing_values']['features_with_missing']
        assert result['missing_values']['max_missing_pct'] > 5.0
        assert result['missing_values']['threshold_exceeded'] == True
        assert result['quality_score'] < 1.0

    def test_validate_label_imbalance_underrepresented(self, validator, feature_names):
        """Dataset com classe subrepresentada (< 5%) deve ser detectado."""
        np.random.seed(42)
        n_samples = 200

        data = {name: np.random.randn(n_samples) for name in feature_names}

        # Classe 0 com apenas 2% (4 amostras)
        # Classe 1 com 48%
        # Classe 2 com 50%
        labels = [0] * 4 + [1] * 96 + [2] * 100
        data['label'] = labels

        df = pd.DataFrame(data)
        result = validator.validate(df, feature_names)

        assert result['label_imbalance']['is_balanced'] is False
        assert '0' in result['label_imbalance']['underrepresented_classes']
        assert len(result['warnings']) > 0

    def test_validate_label_imbalance_dominant(self, validator, feature_names):
        """Dataset com classe dominante (> 80%) deve ser detectado."""
        np.random.seed(42)
        n_samples = 100

        data = {name: np.random.randn(n_samples) for name in feature_names}

        # Classe 1 com 85%
        labels = [0] * 10 + [1] * 85 + [2] * 5
        data['label'] = labels

        df = pd.DataFrame(data)
        result = validator.validate(df, feature_names)

        assert result['label_imbalance']['is_balanced'] is False
        assert '1' in result['label_imbalance']['dominant_classes']

    def test_validate_feature_correlation_high(self, validator):
        """Dataset com features perfeitamente correlacionadas deve ser detectado e reprovar."""
        np.random.seed(42)
        n_samples = 100

        feature_a = np.random.randn(n_samples)
        feature_b = feature_a * 2 + 0.01  # Quase perfeitamente correlacionada
        feature_c = np.random.randn(n_samples)

        df = pd.DataFrame({
            'feature_a': feature_a,
            'feature_b': feature_b,
            'feature_c': feature_c,
            'label': np.random.randint(0, 3, n_samples)
        })

        feature_names = ['feature_a', 'feature_b', 'feature_c']
        result = validator.validate(df, feature_names)

        assert result['feature_correlation']['redundant_features_detected'] == True
        assert len(result['feature_correlation']['highly_correlated_pairs']) > 0

        # Verificar que o par correlacionado foi identificado
        pairs = result['feature_correlation']['highly_correlated_pairs']
        pair_features = set()
        for pair in pairs:
            pair_features.add(pair[0])
            pair_features.add(pair[1])

        assert 'feature_a' in pair_features or 'feature_b' in pair_features
        # Features redundantes detectadas devem reprovar a validação
        assert result['passed'] == False

    def test_validate_schema_mismatch(self, validator):
        """Dataset com features faltantes deve ser detectado."""
        np.random.seed(42)
        n_samples = 100

        # Criar dataset com apenas 2 das 5 features esperadas
        df = pd.DataFrame({
            'feature_a': np.random.randn(n_samples),
            'feature_b': np.random.randn(n_samples),
            'label': np.random.randint(0, 3, n_samples)
        })

        expected_features = ['feature_a', 'feature_b', 'feature_c', 'feature_d', 'feature_e']
        result = validator.validate(df, expected_features)

        assert result['schema_validation']['schema_valid'] is False
        assert 'feature_c' in result['schema_validation']['missing_features']
        assert 'feature_d' in result['schema_validation']['missing_features']
        assert 'feature_e' in result['schema_validation']['missing_features']
        assert result['quality_score'] < 0.7  # Penalidade significativa

    def test_validate_schema_extra_features(self, validator):
        """Dataset com features extras (não metadata) deve falhar na validação de schema."""
        np.random.seed(42)
        n_samples = 100

        # Criar dataset com features esperadas + features extras
        df = pd.DataFrame({
            'feature_a': np.random.randn(n_samples),
            'feature_b': np.random.randn(n_samples),
            'extra_feature_x': np.random.randn(n_samples),  # Feature extra
            'extra_feature_y': np.random.randn(n_samples),  # Feature extra
            'label': np.random.randint(0, 3, n_samples)
        })

        expected_features = ['feature_a', 'feature_b']
        result = validator.validate(df, expected_features)

        assert result['schema_validation']['schema_valid'] == False
        assert 'extra_feature_x' in result['schema_validation']['extra_features']
        assert 'extra_feature_y' in result['schema_validation']['extra_features']
        assert result['passed'] == False
        # Verificar que há warning sobre features extras
        assert any('extras' in w.lower() for w in result['warnings'])

    def test_validate_sparsity(self, validator, feature_names):
        """Dataset com features sempre zero deve ser detectado e reprovar validação."""
        np.random.seed(42)
        n_samples = 100

        data = {name: np.random.randn(n_samples) for name in feature_names}
        # Tornar 3 features sempre zero (60% de sparsity)
        data['feature_c'] = np.zeros(n_samples)
        data['feature_d'] = np.zeros(n_samples)
        data['feature_e'] = np.zeros(n_samples)
        data['label'] = np.random.randint(0, 3, n_samples)

        df = pd.DataFrame(data)
        result = validator.validate(df, feature_names)

        assert result['sparsity']['sparse_features_count'] == 3
        assert result['sparsity']['sparsity_rate'] == 60.0
        assert result['sparsity']['threshold_exceeded'] == True
        assert 'feature_c' in result['sparsity']['sparse_features']
        # Sparsity threshold excedido deve reprovar a validação
        assert result['passed'] == False

    def test_validate_outliers(self, validator, feature_names):
        """Dataset com outliers extremos deve ser detectado e reprovar validação."""
        np.random.seed(42)
        n_samples = 100

        data = {name: np.random.randn(n_samples) for name in feature_names}

        # Adicionar outliers extremos em feature_a (20% do dataset)
        data['feature_a'][:20] = 1000  # Valores extremos

        data['label'] = np.random.randint(0, 3, n_samples)

        df = pd.DataFrame(data)
        result = validator.validate(df, feature_names)

        assert 'feature_a' in result['outliers']['features_with_outliers']
        assert result['outliers']['features_with_outliers']['feature_a'] >= 15.0
        assert result['outliers']['threshold_exceeded'] == True
        # Outlier threshold excedido deve reprovar a validação
        assert result['passed'] == False

    def test_generate_mlflow_report(self, validator, perfect_data, feature_names):
        """Relatório MLflow deve ter estrutura correta."""
        validation_results = validator.validate(perfect_data, feature_names)
        mlflow_report = validator.generate_mlflow_report(validation_results)

        # Verificar estrutura do relatório
        assert 'metadata' in mlflow_report
        assert 'quality_score' in mlflow_report
        assert 'passed' in mlflow_report
        assert 'validations' in mlflow_report
        assert 'warnings' in mlflow_report
        assert 'recommendations' in mlflow_report
        assert 'interpretation' in mlflow_report

        # Verificar metadados
        assert 'validator_version' in mlflow_report['metadata']
        assert 'configuration' in mlflow_report['metadata']
        assert mlflow_report['metadata']['validator_version'] == DataQualityValidator.VERSION

        # Verificar interpretação
        assert 'quality_score_range' in mlflow_report['interpretation']
        assert 'thresholds' in mlflow_report['interpretation']
        assert 'validation_meanings' in mlflow_report['interpretation']

    def test_validate_and_raise_success(self, validator, perfect_data, feature_names):
        """validate_and_raise deve retornar resultados se qualidade OK."""
        result = validator.validate_and_raise(
            perfect_data,
            feature_names,
            min_quality_score=0.6
        )

        assert result['passed'] is True
        assert result['quality_score'] >= 0.6

    def test_validate_and_raise_failure(self, validator):
        """validate_and_raise deve lançar DataQualityError se qualidade baixa."""
        np.random.seed(42)
        n_samples = 100

        # Dataset com múltiplos problemas de qualidade
        data = {
            'feature_a': np.random.randn(n_samples),
            'feature_b': np.zeros(n_samples),  # Sparse
            'label': [0] * 95 + [1] * 5  # Dominância extrema
        }

        # Adicionar 30% missing values
        mask = np.random.random(n_samples) < 0.30
        data['feature_a'] = np.where(mask, np.nan, data['feature_a'])

        df = pd.DataFrame(data)

        # Schema validation vai falhar também
        expected_features = ['feature_a', 'feature_b', 'feature_c', 'feature_d']

        with pytest.raises(DataQualityError) as exc_info:
            validator.validate_and_raise(
                df,
                expected_features,
                min_quality_score=0.8
            )

        assert "Qualidade dos dados insuficiente" in str(exc_info.value)

    def test_quality_score_calculation(self, validator, feature_names):
        """Quality score deve refletir corretamente os problemas detectados."""
        np.random.seed(42)
        n_samples = 100

        # Dataset com problemas progressivos
        data = {name: np.random.randn(n_samples) for name in feature_names}
        data['label'] = np.random.randint(0, 3, n_samples)

        # Sem problemas
        df_perfect = pd.DataFrame(data.copy())
        result_perfect = validator.validate(df_perfect, feature_names)

        # Com problema de sparsity
        data_sparse = data.copy()
        data_sparse['feature_e'] = np.zeros(n_samples)
        df_sparse = pd.DataFrame(data_sparse)
        result_sparse = validator.validate(df_sparse, feature_names)

        # Com problema de schema
        df_schema = pd.DataFrame({
            'feature_a': data['feature_a'],
            'label': data['label']
        })
        result_schema = validator.validate(df_schema, feature_names)

        # Scores devem diminuir com problemas
        assert result_perfect['quality_score'] >= result_sparse['quality_score']
        assert result_sparse['quality_score'] >= result_schema['quality_score']

    def test_recommendations_generated(self, validator, feature_names):
        """Recomendações devem ser geradas para problemas detectados."""
        np.random.seed(42)
        n_samples = 100

        # Dataset com múltiplos problemas
        data = {
            'feature_a': np.random.randn(n_samples),
            'feature_b': np.random.randn(n_samples),
            'label': [0] * 2 + [1] * 98  # Classe 0 subrepresentada
        }

        # Criar feature correlacionada
        data['feature_c'] = data['feature_a'] * 1.5 + 0.01

        # Adicionar missing values
        mask = np.random.random(n_samples) < 0.1
        data['feature_b'] = np.where(mask, np.nan, data['feature_b'])

        df = pd.DataFrame(data)
        result = validator.validate(df, ['feature_a', 'feature_b', 'feature_c'])

        # Deve ter recomendações
        assert len(result['recommendations']) > 0

    def test_empty_dataframe(self, validator, feature_names):
        """Dataset vazio deve ser tratado graciosamente."""
        df = pd.DataFrame(columns=feature_names + ['label'])
        result = validator.validate(df, feature_names)

        # Não deve lançar exceção, mas qualidade deve ser baixa
        assert 'quality_score' in result
        assert result['dataset_shape'][0] == 0

    def test_single_class_label(self, validator, feature_names):
        """Dataset com apenas uma classe deve ser detectado como desbalanceado."""
        np.random.seed(42)
        n_samples = 100

        data = {name: np.random.randn(n_samples) for name in feature_names}
        data['label'] = [1] * n_samples  # Apenas classe 1

        df = pd.DataFrame(data)
        result = validator.validate(df, feature_names)

        assert result['label_imbalance']['is_balanced'] is False
        assert '1' in result['label_imbalance']['dominant_classes']

    def test_configuration_from_params(self):
        """Configurações devem ser aplicadas corretamente."""
        validator = DataQualityValidator(
            max_missing_pct=10.0,
            min_class_pct=10.0,
            max_correlation=0.99
        )

        assert validator.max_missing_pct == 10.0
        assert validator.min_class_pct == 10.0
        assert validator.max_correlation == 0.99

    def test_numeric_columns_only_for_correlation(self, validator):
        """Correlação deve ser calculada apenas para colunas numéricas."""
        np.random.seed(42)
        n_samples = 100

        df = pd.DataFrame({
            'feature_a': np.random.randn(n_samples),
            'feature_b': np.random.randn(n_samples),
            'feature_c': ['cat'] * 50 + ['dog'] * 50,  # String column
            'label': np.random.randint(0, 3, n_samples)
        })

        feature_names = ['feature_a', 'feature_b', 'feature_c']
        result = validator.validate(df, feature_names)

        # Não deve falhar por causa de coluna string
        assert 'feature_correlation' in result
        assert 'error' not in result['feature_correlation']


class TestDataQualityValidatorIntegration:
    """Testes de integração com cenários realistas."""

    def test_realistic_ml_dataset(self):
        """Cenário realista de dataset de ML."""
        np.random.seed(42)
        n_samples = 500

        # Criar dataset realista
        feature_names = [
            'num_tasks', 'total_duration_ms', 'avg_complexity',
            'max_risk_score', 'min_confidence', 'diversity_score'
        ]

        data = {}
        for name in feature_names:
            if 'duration' in name:
                data[name] = np.random.exponential(1000, n_samples)
            elif 'score' in name:
                data[name] = np.random.uniform(0, 1, n_samples)
            else:
                data[name] = np.random.randn(n_samples)

        # Labels com leve desbalanceamento (aceitável)
        data['label'] = np.random.choice([0, 1, 2], n_samples, p=[0.25, 0.50, 0.25])

        df = pd.DataFrame(data)

        validator = DataQualityValidator()
        result = validator.validate(df, feature_names)

        # Dataset realista deve passar
        assert result['passed'] is True
        assert result['quality_score'] >= 0.6

        # Verificar que MLflow report é serializável
        mlflow_report = validator.generate_mlflow_report(result)
        import json
        json.dumps(mlflow_report)  # Não deve lançar exceção
