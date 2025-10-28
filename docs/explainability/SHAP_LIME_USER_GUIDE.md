# Guia de Uso: Explicabilidade Avançada com SHAP/LIME

## Visão Geral

Os especialistas do Neural Hive Mind utilizam **SHAP** (SHapley Additive exPlanations) e **LIME** (Local Interpretable Model-agnostic Explanations) para gerar explicações interpretáveis de suas decisões.

### Métodos Disponíveis

| Método | Quando Usar | Vantagens | Limitações |
|--------|-------------|-----------|------------|
| **SHAP** | Modelos tree-based (RandomForest, XGBoost) | Teoricamente fundamentado, valores aditivos | Computacionalmente intensivo |
| **LIME** | Modelos lineares, redes neurais | Rápido, model-agnostic | Aproximação local |
| **Heurístico** | Fallback quando ML não disponível | Sempre disponível | Menos preciso |

---

## Configuração

### 1. Variáveis de Ambiente

Adicionar ao `.env` do especialista:

```bash
# SHAP Configuration
SHAP_BACKGROUND_DATASET_PATH=/data/shap_background_technical.parquet
SHAP_TIMEOUT_SECONDS=5.0
SHAP_MAX_BACKGROUND_SAMPLES=100

# LIME Configuration
LIME_NUM_SAMPLES=1000
LIME_TIMEOUT_SECONDS=5.0

# Narrative Configuration
NARRATIVE_TOP_FEATURES=5
NARRATIVE_LANGUAGE=pt-BR

# Ledger V2
ENABLE_EXPLAINABILITY_LEDGER_V2=true
EXPLAINABILITY_LEDGER_VERSION=2.0.0
```

### 2. Gerar Background Dataset

Para SHAP funcionar otimamente, é necessário um background dataset representativo:

```bash
python scripts/explainability/generate_shap_background_dataset.py \
    --mongodb-uri mongodb://localhost:27017 \
    --database neural_hive \
    --collection cognitive_plans \
    --output-path /data/shap_background_technical.parquet \
    --num-samples 1000 \
    --specialist-type technical
```

### 3. Validar Background Dataset

```bash
python scripts/explainability/validate_background_dataset.py \
    --dataset-path /data/shap_background_technical.parquet \
    --min-samples 50 \
    --min-variance 0.001
```

---

## Uso Programático

### Exemplo: Usar SHAP Explainer

```python
from neural_hive_specialists.explainability.shap_explainer import SHAPExplainer
import pandas as pd

# Configurar explainer
config = {
    'shap_background_dataset_path': '/data/shap_background.parquet',
    'shap_timeout_seconds': 5.0
}
explainer = SHAPExplainer(config)

# Explicar predição
features = {
    'num_tasks': 8.0,
    'complexity_score': 0.75,
    'avg_duration_ms': 2500.0
}
feature_names = list(features.keys())

result = explainer.explain(model, features, feature_names)

# Resultado contém:
print(result['method'])  # 'shap'
print(result['base_value'])  # Valor base do modelo
print(result['feature_importances'])  # Lista de importâncias
```

### Exemplo: Gerar Narrativa

```python
from neural_hive_specialists.explainability.narrative_generator import NarrativeGenerator

generator = NarrativeGenerator(config={})

# Gerar narrativa completa
narrative = generator.generate_narrative(
    feature_importances=result['feature_importances'],
    top_n=5,
    explanation_type='shap'
)

print(narrative)
# Saída:
# "A decisão foi baseada principalmente nos seguintes fatores:
#
# **Fatores que aumentaram a confiança:**
# 1. **O plano contém 8 tarefas** (contribuição positiva, forte impacto)
# ..."

# Gerar resumo executivo
summary = generator.generate_summary(
    feature_importances=result['feature_importances'],
    explanation_type='shap'
)

print(summary)
# Saída: "Decisão influenciada principalmente porque o plano contém 8 tarefas."
```

---

## Interpretação de Resultados

### Estrutura de Feature Importance

```python
{
    'feature_name': 'num_tasks',
    'shap_value': 0.35,           # Contribuição SHAP (pode ser negativa)
    'feature_value': 8.0,         # Valor da feature no plano
    'contribution': 'positive',   # 'positive', 'negative', 'neutral'
    'importance': 0.35            # Importância absoluta (sempre positiva)
}
```

### Interpretando SHAP Values

- **SHAP Value > 0**: Feature **aumenta** a confiança do modelo
- **SHAP Value < 0**: Feature **diminui** a confiança do modelo
- **SHAP Value ≈ 0**: Feature tem **pouco impacto**

**Exemplo:**
```python
# num_tasks = 8, shap_value = 0.35
# Interpretação: "Ter 8 tarefas aumenta a confiança em 0.35 pontos"

# complexity_score = 0.85, shap_value = -0.25
# Interpretação: "Complexidade alta (0.85) reduz a confiança em 0.25 pontos"
```

### Base Value

O `base_value` é a predição média do modelo no background dataset. A predição final é:

```
prediction = base_value + sum(shap_values)
```

---

## Consultar Explicações Persistidas

### Via ExplainabilityLedgerV2

```python
from neural_hive_specialists.explainability.explainability_ledger_v2 import ExplainabilityLedgerV2

ledger = ExplainabilityLedgerV2(config)

# Recuperar por token
explanation = ledger.retrieve('token-abc123')

# Recuperar todas as explicações de um plano
explanations = ledger.query_by_plan('plan-123')

# Recuperar explicações de um especialista
explanations = ledger.query_by_specialist('technical', limit=100)
```

### Estrutura do Documento Persistido

```json
{
  "explainability_token": "abc123...",
  "schema_version": "2.0.0",
  "plan_id": "plan-123",
  "specialist_type": "technical",
  "explanation_method": "shap",
  "input_features": {
    "num_tasks": 8.0,
    "complexity_score": 0.75
  },
  "feature_names": ["num_tasks", "complexity_score"],
  "model_version": "1.2.3",
  "model_type": "RandomForestClassifier",
  "feature_importances": [...],
  "human_readable_summary": "Decisão influenciada principalmente porque...",
  "detailed_narrative": "A decisão foi baseada principalmente...",
  "prediction": {
    "confidence_score": 0.85,
    "risk_score": 0.25
  },
  "computation_time_ms": 1250,
  "background_dataset_hash": "abc123def456",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

## Troubleshooting

### Problema: SHAP dá timeout

**Causa**: Modelo muito complexo ou background dataset muito grande.

**Solução**:
1. Aumentar `SHAP_TIMEOUT_SECONDS`
2. Reduzir `SHAP_MAX_BACKGROUND_SAMPLES`
3. Usar modelo mais simples

### Problema: LIME retorna poucos features

**Causa**: `LIME_NUM_SAMPLES` muito baixo.

**Solução**: Aumentar para 1000-5000 amostras.

### Problema: Narrativas em inglês

**Causa**: `NARRATIVE_LANGUAGE` não configurado.

**Solução**: Definir `NARRATIVE_LANGUAGE=pt-BR`.

### Problema: Background dataset inválido

**Causa**: Dataset com NaN, baixa variância ou poucas amostras.

**Solução**: Regenerar dataset com mais amostras diversas.

---

## Métricas de Observabilidade

Métricas Prometheus disponíveis:

```promql
# Tempo de computação SHAP/LIME
specialist_explainability_computation_seconds{method="shap"}

# Uso de métodos
specialist_explainability_method_total{method="shap"}

# Erros
specialist_explainability_errors_total{method="shap", error_type="timeout"}

# Número de features explicadas
specialist_explainability_feature_count{method="shap"}

# Persistências no ledger v2
specialist_explainability_ledger_v2_persistence_total{status="success"}
```

---

## Exemplos Práticos

### Exemplo 1: Explicar Decisão de Aprovação

```python
# Avaliar plano cognitivo
evaluation_result = specialist.evaluate(cognitive_plan)

# Gerar explicação
explainability_token, metadata = explainability_generator.generate(
    evaluation_result,
    cognitive_plan,
    model
)

# Imprimir narrativa
print(metadata['human_readable_summary'])
print(metadata['detailed_narrative'])

# Top 3 features mais importantes
for feature in metadata['feature_importances'][:3]:
    print(f"{feature['feature_name']}: {feature['shap_value']:.3f}")
```

### Exemplo 2: Comparar Explicações de Múltiplos Especialistas

```python
# Buscar explicações de todos os especialistas para o mesmo plano
plan_id = 'plan-123'

for specialist_type in ['technical', 'business', 'behavior']:
    explanations = ledger.query_by_plan(plan_id)
    specialist_explanations = [e for e in explanations if e['specialist_type'] == specialist_type]

    if specialist_explanations:
        exp = specialist_explanations[0]
        print(f"\n{specialist_type.upper()}:")
        print(exp['human_readable_summary'])
```

### Exemplo 3: Auditoria de Decisões

```python
# Buscar todas as explicações de um período
from datetime import datetime, timedelta

start_date = datetime.now() - timedelta(days=7)

# Query manual no MongoDB
explanations = ledger.mongo_client[ledger.config.mongodb_database]['explainability_ledger_v2'].find({
    'created_at': {'$gte': start_date},
    'explanation_method': 'shap'
})

# Análise de features mais influentes
feature_counts = {}
for exp in explanations:
    for importance in exp.get('feature_importances', [])[:3]:
        feature_name = importance['feature_name']
        feature_counts[feature_name] = feature_counts.get(feature_name, 0) + 1

print("Features mais influentes da semana:")
for feature, count in sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"{feature}: {count} vezes")
```

---

## Boas Práticas

### 1. Background Dataset

- **Tamanho**: 100-1000 amostras representativas
- **Atualização**: Regenerar mensalmente ou quando modelo mudar
- **Validação**: Sempre validar antes de usar em produção

### 2. Timeouts

- **SHAP**: 5-10s para modelos tree-based, 15-30s para linear
- **LIME**: 5-10s para maioria dos modelos
- **Monitorar**: Taxa de timeout > 10% indica necessidade de ajuste

### 3. Narrativas

- **Idioma**: Sempre configurar `NARRATIVE_LANGUAGE`
- **Top Features**: 3-5 features para resumo, 5-10 para narrativa completa
- **Customização**: Adicionar templates específicos para seu domínio

### 4. Ledger V2

- **Habilitar**: Sempre usar `ENABLE_EXPLAINABILITY_LEDGER_V2=true`
- **Queries**: Usar índices do MongoDB para performance
- **Retenção**: Definir política de retenção de dados

---

## Referências

- **SHAP**: https://github.com/slundberg/shap
- **LIME**: https://github.com/marcotcr/lime
- **Código**: `/libraries/python/neural_hive_specialists/explainability/`
- **Testes**: `/libraries/python/neural_hive_specialists/tests/test_*explainability*.py`
- **Scripts**: `/scripts/explainability/`
