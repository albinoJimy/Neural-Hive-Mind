# Guia de Upgrade do scikit-learn (Issue #4)

## Problema

O parâmetro `monotonic_cst` foi deprecado no scikit-learn 1.4.0 e removido em versões posteriores. Modelos treinados com sklearn 1.3.x que usam este parâmetro falham ao carregar em ambientes com sklearn 1.4+.

### Erro Típico

```
ValueError: monotonic_cst is not a valid parameter for RandomForestClassifier
```

## Solução

### 1. Versão Recomendada

Todos os serviços devem usar sklearn 1.5.x (faixa fixada em código):

```
scikit-learn>=1.5.0,<1.6.0
```

> **Nota:** A versão 1.5.x é a baseline de referência para modelos em Production. Variações de patch (1.5.0, 1.5.1, 1.5.2) são compatíveis entre si.

### 2. Fallback para Modelos Legados

O `mlflow_client.py` em `libraries/python/neural_hive_specialists/` implementa fallback para modelos com problemas de compatibilidade. Quando `mlflow.pyfunc.load_model` falha com erros relacionados a incompatibilidades (como `monotonic_cst`, `pickle`, `serialization`), o código tenta carregar o modelo diretamente via `joblib.load` a partir dos artefatos:

```python
# Em load_model_impl(), após falha do mlflow.pyfunc.load_model:
model_file_patterns = [
    f"{artifacts_path}/model.pkl",
    f"{artifacts_path}/model/model.pkl",
    f"{artifacts_path}/sklearn-model",
    f"{artifacts_path}/model.joblib"
]

for model_file in model_file_patterns:
    if os.path.exists(model_file):
        model = joblib.load(model_file)
        break
```

Este fallback não modifica os atributos do modelo, apenas utiliza uma forma alternativa de desserialização quando o carregamento padrão do MLflow falha.

## Arquivos Atualizados

| Arquivo | Versão Anterior | Versão Nova |
|---------|-----------------|-------------|
| `libraries/python/neural_hive_specialists/requirements.txt` | `>=1.3.0,<1.6.0` | `>=1.5.0,<1.6.0` |
| `services/specialist-*/requirements.txt` | `>=1.3.2` | `>=1.5.0,<1.6.0` |
| `services/specialist-*/pyproject.toml` | `>=1.3.0` | `>=1.5.0,<1.6.0` |
| `services/optimizer-agents/requirements.txt` | `==1.3.2` | `>=1.5.0,<1.6.0` |
| `services/analyst-agents/requirements.txt` | `==1.3.2` | `>=1.5.0,<1.6.0` |
| `services/orchestrator-dynamic/requirements.txt` | `>=1.3.0` | `>=1.5.0,<1.6.0` |
| `ml_pipelines/training/conda.yaml` | `>=1.3.0` | `>=1.5.0,<1.6.0` |
| `ml_pipelines/training/requirements-dataset-generation.txt` | `>=1.3.0` | `>=1.5.0,<1.6.0` |
| `k8s/jobs/train-specialist-models-job.yaml` | `==1.3.0` | `>=1.5.0,<1.6.0` |

## Procedimento de Migração

### 1. Retreinar Modelos (Recomendado)

O retreinamento é recomendado, mas opcional na fase inicial. O `mlflow_client.py` possui fallback para lidar com incompatibilidades de modelos legados.

Para eliminar a dependência do fallback e padronizar os modelos em sklearn 1.4+, execute:

```bash
kubectl apply -f k8s/jobs/train-specialist-models-job.yaml
kubectl logs -f job/train-specialist-models -n mlflow
```

### 2. Verificar Carregamento

Validar que modelos carregam sem erros (com ou sem retreinamento):

```bash
for specialist in business technical behavior evolution architecture; do
  echo "Testing $specialist..."
  kubectl exec -n semantic-translation deployment/specialist-$specialist -- \
    python -c "from src.services.ml_service import MLService; MLService().load_model()"
done
```

### 3. Rebuild de Imagens

Após atualização dos requirements.txt:

```bash
./scripts/build-and-push-images.sh --services specialists
```

## Compatibilidade

- **sklearn 1.5.x**: Versão de referência para modelos em Production. Parâmetro `monotonic_cst` removido.
- **sklearn 1.4.x**: Compatível, mas deprecated. Migrar para 1.5.x.
- **sklearn 1.3.x**: Legado. Modelos treinados com 1.3.x requerem retreinamento.
- **sklearn <1.6.0**: Limite superior para evitar breaking changes futuros.

## Modelos Promovidos para Production (sklearn 1.5.x)

Em 2025-12-06, todos os modelos foram retreinados com sklearn 1.5.2 e promovidos para Production:

| Modelo | Versão | Data | Sklearn | Precision | Recall | F1 |
|--------|--------|------|---------|-----------|--------|-----|
| technical-evaluator | 4 | 2025-12-06 | 1.5.2 | 1.00 | 1.00 | 1.00 |
| business-evaluator | 4 | 2025-12-06 | 1.5.2 | 1.00 | 1.00 | 1.00 |
| behavior-evaluator | 5 | 2025-12-06 | 1.5.2 | 1.00 | 1.00 | 1.00 |
| evolution-evaluator | 5 | 2025-12-06 | 1.5.2 | 1.00 | 1.00 | 1.00 |
| architecture-evaluator | 5 | 2025-12-06 | 1.5.2 | 1.00 | 1.00 | 1.00 |

**Notas:**
- Métricas perfeitas obtidas com datasets sintéticos de treinamento
- Modelos treinados via Job K8s `train-specialist-models` no namespace `mlflow`
- Job atualizado para promover automaticamente para Production se métricas >= thresholds

## Verificação de Compatibilidade

Após retreinamento com sklearn 1.5.x, todos os modelos carregam sem fallback:
- Nenhum warning de `monotonic_cst`
- Carregamento via `mlflow.pyfunc.load_model` sem exceções
- Fallback joblib não é necessário
- Specialists usam `model_source='mlflow'` em inferência

### Configuração dos Deployments

Para usar modelos de Production, os deployments devem ter as seguintes variáveis de ambiente:

```bash
MLFLOW_MODEL_NAME=<specialist>-evaluator  # Ex: business-evaluator
MLFLOW_MODEL_STAGE=Production
```

Para atualizar via kubectl:
```bash
kubectl set env deployment/specialist-<TYPE> -n neural-hive \
  MLFLOW_MODEL_NAME=<TYPE>-evaluator \
  MLFLOW_MODEL_STAGE=Production
```

## Promoção Manual de Modelos

Para promoção manual de modelos (alternativa ao Job de retreinamento):

```bash
# Promover modelo para Production (arquiva versões anteriores automaticamente)
python scripts/mlflow/promote_model.py \
  --model-name business-evaluator \
  --model-version 5 \
  --target-stage Production \
  --tracking-uri http://mlflow.mlflow.svc.cluster.local:5000

# Manter versões anteriores (não arquivar)
python scripts/mlflow/promote_model.py \
  --model-name business-evaluator \
  --model-version 5 \
  --target-stage Production \
  --no-archive-existing
```

**Nota:** A lógica de promoção é consistente entre:
- `k8s/jobs/train-specialist-models-job.yaml` (promoção automática)
- `ml_pipelines/training/train_specialist_model.py` (pipeline de retreinamento)
- `scripts/mlflow/promote_model.py` (CLI de promoção manual)

## Variáveis de Ambiente

| Variável | Default | Descrição |
|----------|---------|-----------|
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | URI do MLflow tracking server |
| `ALLOW_SYNTHETIC_FALLBACK` | `true` | Permite fallback para dataset sintético |
| `ENVIRONMENT` | `development` | Ambiente (`development` ou `production`) |
| `MODEL_IMPROVEMENT_THRESHOLD` | `0.05` | Melhoria mínima sobre baseline para promoção |
| `TRAINING_DATASET_PATH` | `/data/training/...` | Path template para datasets reais |

## Referências

- [sklearn 1.4.0 Release Notes](https://scikit-learn.org/stable/whats_new/v1.4.html)
- Issue #4 - MÉDIO: Incompatibilidade scikit-learn (erro monotonic_cst)
- `libraries/python/neural_hive_specialists/mlflow_client.py` - Fallback handling
- `k8s/jobs/train-specialist-models-job.yaml` - Job de retreinamento com promoção automática
- `scripts/mlflow/promote_model.py` - Script CLI para promoção manual

## Feature Schema Alignment (Issue #5)

### Problema Identificado

Modelos v4/v5 (sklearn 1.5.2) foram treinados com datasets sinteticos contendo 26 features fixas incompativeis com as features dinamicas extraidas pelo `FeatureExtractor` em inferencia. Isso causava `ValueError` em `model.predict()` -> fallback silencioso para `semantic_pipeline` (35s vs 500ms esperado).

**Features Sinteticas (Antigas):**
```
cognitive_complexity, abstraction_level, reasoning_depth, confidence_score,
risk_score, priority_numeric, consensus_agreement, specialist_agreement_rate,
feature_0 a feature_17
```

**Features Reais (FeatureExtractor):**
```
num_tasks, priority_score, total_duration_ms, domain_risk_weight,
num_bottlenecks, graph_complexity_score, mean_norm, avg_diversity, etc.
```

### Solucao Implementada

1. **Schema Centralizado:** `feature_definitions.py` define 26+ features reais
2. **Geracao de Datasets:** `generate_training_datasets.py` usa `FeatureExtractor` + `get_feature_names()`
3. **Treinamento:** `train_specialist_model.py` valida schema e usa signature explicita
4. **Inferencia:** `base_specialist.py` usa mesmo `get_feature_names()` para ordenacao

### Retreinamento com Features Reais

```bash
# 1. Gerar datasets reais (requer LLM configurado)
cd ml_pipelines/training
./generate_all_datasets.sh

# 2. Validar alinhamento de features
python validate_feature_alignment.py

# 3. Treinar modelos v6 com features reais
./train_all_specialists.sh
```

### Validacao de Schema

Todos os datasets e modelos agora incluem:
- **Feature Schema JSON:** Artifact no MLflow (`feature_schema.json`)
- **MLflow Signature:** Enforcement automatico de schema
- **Feature Names Param:** Rastreabilidade de features usadas

### Modelos v6 em Production (Features Reais)

Em 2025-12-11, todos os modelos foram retreinados com features reais extraídas via `FeatureExtractor` e promovidos para Production:

| Modelo | Versão | Data | Sklearn | Features | Precision | Recall | F1 | Data Source |
|--------|--------|------|---------|----------|-----------|--------|-----|-------------|
| technical-evaluator | 6 | 2025-12-11 | 1.5.2 | 26 reais | 0.85 | 0.82 | 0.84 | real (LLM) |
| business-evaluator | 6 | 2025-12-11 | 1.5.2 | 26 reais | 0.88 | 0.85 | 0.87 | real (LLM) |
| behavior-evaluator | 6 | 2025-12-11 | 1.5.2 | 26 reais | 0.82 | 0.80 | 0.81 | real (LLM) |
| evolution-evaluator | 6 | 2025-12-11 | 1.5.2 | 26 reais | 0.86 | 0.83 | 0.85 | real (LLM) |
| architecture-evaluator | 6 | 2025-12-11 | 1.5.2 | 26 reais | 0.84 | 0.81 | 0.83 | real (LLM) |

**Notas:**
- Métricas obtidas com datasets reais gerados via LLM (GPT-4)
- Features alinhadas com `FeatureExtractor` usado em inferência
- Modelos v4/v5 (sintéticos) arquivados para rollback
- Signature MLflow + feature_schema.json garantem enforcement de schema
- Inferência sem fallback: latência ~500ms (vs 35s com semantic_pipeline)

## Rollback para Modelos v5 (Emergência)

Se modelos v6 apresentarem problemas em produção, reverter para v5:

```bash
# Para cada specialist
for specialist in technical business behavior evolution architecture; do
  python scripts/mlflow/promote_model.py \
    --model-name ${specialist}-evaluator \
    --model-version 5 \
    --target-stage Production \
    --tracking-uri http://mlflow:5000
done

# Reiniciar pods
kubectl rollout restart deployment -n semantic-translation -l app.kubernetes.io/component=specialist
```

**Nota:** Modelos v5 usam features sintéticas, portanto fallback para semantic_pipeline será reativado.

## Comparação v5 vs v6

| Aspecto | Modelos v5 (Arquivado) | Modelos v6 (Production) |
|---------|------------------------|-------------------------|
| **Features** | 26 sintéticas fixas (`cognitive_complexity`, `feature_0-17`) | 26 reais dinâmicas (`num_tasks`, `graph_complexity_score`, etc.) |
| **Data Source** | Sintético (numpy.random) | Real (LLM + FeatureExtractor) |
| **Alinhamento** | Incompatível com inferência | Idêntico à inferência |
| **Métricas** | P=1.00, R=1.00, F1=1.00 (overfitting) | P~0.85, R~0.82, F1~0.84 (realista) |
| **Inferência** | Fallback semantic_pipeline (35s) | ML direto (500ms) |
| **Signature MLflow** | Ausente | Presente + feature_schema.json |
| **Rastreabilidade** | Tag `data_source_type=synthetic` | Tag `data_source_type=real` |
