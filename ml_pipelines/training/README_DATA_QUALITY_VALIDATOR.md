# DataQualityValidator

Validador avançado de qualidade de dados para pipelines de ML do Neural Hive Mind.

## Propósito

O `DataQualityValidator` complementa o `RealDataCollector` com validações avançadas de qualidade de dados, incluindo:

- **Detecção de desbalanceamento de labels** - Identifica classes sub-representadas (< 5%) e dominantes (> 80%)
- **Análise de correlação de features** - Detecta features redundantes com alta correlação
- **Validação de missing values** - Identifica features com valores nulos acima do threshold
- **Análise de sparsity** - Detecta features sempre zero
- **Detecção de outliers** - Usa método IQR para identificar valores atípicos
- **Validação de schema** - Verifica conformidade com features esperadas
- **Relatórios estruturados** - Gera artefatos JSON compatíveis com MLflow

## Instalação

O `DataQualityValidator` faz parte do pacote `ml_pipelines/training`. Não requer instalação adicional.

## Uso Standalone

```python
from data_quality_validator import DataQualityValidator
import pandas as pd

# Instanciar validador
validator = DataQualityValidator(
    max_missing_pct=5.0,      # Máximo % de missing values por feature
    max_sparsity_pct=50.0,    # Máximo % de features sempre zero
    max_outlier_pct=10.0,     # Máximo % de outliers por feature
    min_class_pct=5.0,        # Mínimo % de cada classe
    max_correlation=0.95      # Máxima correlação entre features
)

# Validar DataFrame
feature_names = ['feature_a', 'feature_b', 'feature_c']
result = validator.validate(df, feature_names)

# Acessar resultados
print(f"Quality Score: {result['quality_score']}")
print(f"Passed: {result['passed']}")
print(f"Warnings: {result['warnings']}")
print(f"Recommendations: {result['recommendations']}")
```

## Uso Integrado com RealDataCollector

O `RealDataCollector` já integra automaticamente o `DataQualityValidator`:

```python
from real_data_collector import RealDataCollector

# Validação habilitada por padrão
collector = RealDataCollector(
    enable_quality_validation=True  # Default
)

# Os dados coletados são automaticamente validados
df = await collector.collect_training_data(
    specialist_type='technical',
    days=90,
    min_samples=1000
)

# Acessar relatório de qualidade
quality_report = df.attrs.get('quality_report')
```

Para desabilitar a validação:

```python
collector = RealDataCollector(
    enable_quality_validation=False
)
```

## Validações Implementadas

### 1. Missing Values

Calcula a porcentagem de valores nulos por feature e identifica aquelas acima do threshold.

```python
{
    'features_with_missing': {'feature_a': 2.3, 'feature_b': 1.1},
    'max_missing_pct': 2.3,
    'threshold_exceeded': False,
    'threshold': 5.0
}
```

### 2. Sparsity

Detecta features que são sempre zero (sem variância).

```python
{
    'sparse_features': ['feature_x', 'feature_y'],
    'sparse_features_count': 2,
    'sparsity_rate': 6.1,
    'threshold_exceeded': False,
    'threshold': 50.0
}
```

### 3. Outliers (IQR)

Usa o método do Intervalo Interquartil para detectar valores atípicos.

```python
{
    'features_with_outliers': {'duration_ms': 15.2},
    'max_outlier_pct': 15.2,
    'threshold_exceeded': True,
    'threshold': 10.0
}
```

### 4. Label Imbalance

Analisa a distribuição de classes no target.

```python
{
    'distribution': {'0': 250, '1': 500, '2': 250},
    'percentages': {'0': 25.0, '1': 50.0, '2': 25.0},
    'underrepresented_classes': [],
    'dominant_classes': [],
    'is_balanced': True,
    'min_class_threshold': 5.0
}
```

### 5. Feature Correlation

Calcula correlação de Pearson entre features numéricas.

```python
{
    'highly_correlated_pairs': [
        ['num_tasks', 'total_duration_ms', 0.96]
    ],
    'max_correlation_found': 0.96,
    'redundant_features_detected': True,
    'threshold': 0.95
}
```

### 6. Schema Validation

Verifica conformidade com o schema esperado.

```python
{
    'missing_features': ['feature_z'],
    'extra_features': [],
    'schema_valid': False,
    'expected_count': 33,
    'actual_count': 32
}
```

## Quality Score

O score de qualidade (0.0-1.0) é calculado com base em penalidades:

| Problema | Penalidade Máxima |
|----------|------------------|
| Missing values | 0.2 (proporcional à média) |
| Sparsity | 0.3 (proporcional à taxa) |
| Outliers | 0.2 (proporcional à média) |
| Label imbalance | 0.3 (fixa) |
| Correlação alta | 0.2 (fixa) |
| Schema inválido | 0.4 (fixa) |

### Interpretação do Score

| Score | Classificação |
|-------|---------------|
| >= 0.9 | Excelente |
| >= 0.75 | Bom |
| >= 0.6 | Aceitável |
| < 0.6 | Insuficiente |

## Relatórios MLflow

O validador gera relatórios estruturados para MLflow:

```python
# Gerar relatório
validation_result = validator.validate(df, feature_names)
mlflow_report = validator.generate_mlflow_report(validation_result)

# Logar no MLflow
import mlflow
mlflow.log_dict(mlflow_report, "data_quality_report.json")

# Logar métricas individuais
mlflow.log_metric("data_quality_score", validation_result['quality_score'])
mlflow.log_param("data_quality_passed", str(validation_result['passed']))
```

### Exemplo de Relatório MLflow

```json
{
  "metadata": {
    "validator_version": "1.0.0",
    "validation_timestamp": "2026-01-20T10:30:00Z",
    "dataset_shape": [1500, 33],
    "configuration": {
      "max_missing_pct": 5.0,
      "max_sparsity_pct": 50.0,
      "max_outlier_pct": 10.0,
      "min_class_pct": 5.0,
      "max_correlation": 0.95
    }
  },
  "quality_score": 0.78,
  "passed": true,
  "validations": {
    "missing_values": {...},
    "sparsity": {...},
    "outliers": {...},
    "label_imbalance": {...},
    "feature_correlation": {...},
    "schema_validation": {...}
  },
  "warnings": [
    "Features altamente correlacionadas: num_tasks-total_duration_ms (r=0.96)"
  ],
  "recommendations": [
    "Remover features redundantes (alta correlação): ['total_duration_ms']"
  ],
  "interpretation": {
    "quality_score_range": "[0.0, 1.0], 1.0 = perfeito",
    "thresholds": {
      "excellent": ">= 0.9",
      "good": ">= 0.75",
      "acceptable": ">= 0.6",
      "poor": "< 0.6"
    }
  }
}
```

## Fail-Fast com validate_and_raise

Para pipelines que devem falhar imediatamente se a qualidade for insuficiente:

```python
from data_quality_validator import DataQualityValidator, DataQualityError

validator = DataQualityValidator()

try:
    result = validator.validate_and_raise(
        df=df,
        feature_names=feature_names,
        min_quality_score=0.7
    )
    print("Dados aprovados para treinamento")
except DataQualityError as e:
    print(f"Dados rejeitados: {e}")
```

## Configuração via Variáveis de Ambiente

```bash
# Thresholds de qualidade
DATA_QUALITY_MAX_MISSING_PCT=5.0
DATA_QUALITY_MAX_SPARSITY_PCT=50.0
DATA_QUALITY_MAX_OUTLIER_PCT=10.0
DATA_QUALITY_MIN_CLASS_PCT=5.0
DATA_QUALITY_MAX_CORRELATION=0.95
DATA_QUALITY_MIN_SCORE=0.6
```

## Troubleshooting

### Score de Qualidade Baixo

1. **Missing values altos**
   - Verifique o pipeline de extração de features
   - Considere imputação (média, mediana) para features críticas

2. **Sparsity alta**
   - Features sempre zero podem ser removidas
   - Verifique se o extrator está populando corretamente

3. **Outliers**
   - Aplique transformações (log, box-cox) para features com distribuição assimétrica
   - Considere clipping para valores extremos

4. **Label imbalance**
   - Use SMOTE ou técnicas de oversampling
   - Configure `class_weight='balanced'` no modelo
   - Colete mais dados para classes minoritárias

5. **Correlação alta**
   - Remova uma das features correlacionadas
   - Use PCA para redução de dimensionalidade

### Erro de Schema

Se features esperadas estão faltando:

```python
# Verificar features disponíveis
print(df.columns.tolist())

# Comparar com features esperadas
from feature_store.feature_definitions import get_feature_names
expected = set(get_feature_names())
actual = set(df.columns)
print(f"Faltando: {expected - actual}")
```

## Testes

```bash
# Executar testes do validador
cd ml_pipelines/training
pytest tests/test_data_quality_validator.py -v
```

## Arquitetura

```
RealDataCollector
    │
    ├── collect_training_data()
    │       │
    │       └── DataQualityValidator.validate()
    │               ├── _validate_missing_values()
    │               ├── _validate_sparsity()
    │               ├── _validate_outliers()
    │               ├── _validate_label_imbalance()
    │               ├── _validate_feature_correlation()
    │               └── _validate_schema()
    │
    └── df.attrs['quality_report'] = validation_report

train_specialist_model.py
    │
    ├── load_dataset_with_real_data_priority()
    │       │
    │       └── DataQualityValidator.validate()
    │               │
    │               └── MLflow logging
    │                       ├── log_dict(report, "data_quality_report.json")
    │                       └── log_metric("data_quality_score", ...)
```

## Changelog

### v1.0.0

- Implementação inicial com 6 tipos de validação
- Integração com RealDataCollector
- Integração com pipeline de treinamento MLflow
- Geração de relatórios estruturados
