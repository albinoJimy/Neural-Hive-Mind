# Dataset Generation with AI

Este módulo gera datasets de treino realistas para os 5 especialistas do Neural Hive Mind usando LLMs (Large Language Models).

## 📋 Visão Geral

O gerador de datasets usa LLMs para criar:
1. **Cognitive Plans** variados (diferentes domínios, complexidades, riscos)
2. **Specialist Opinions** com labels corretos (approve/reject/review_required/conditional)
3. **Features numéricas** extraídas via `FeatureExtractor` (26+ dimensões)
4. **Datasets em Parquet** prontos para treinamento

## 🏗️ Arquitetura

```
LLM (OpenAI/Anthropic/Ollama)
    ↓
Prompt Templates (por especialista)
    ↓
Cognitive Plan JSON + Specialist Opinion JSON
    ↓
FeatureExtractor (ontology + graph + embeddings)
    ↓
Features (26+ dimensões) + Label
    ↓
Parquet Dataset
```

## 🚀 Quick Start

### 1. Configurar Environment

```bash
cd ml_pipelines/training
cp .env.example .env
# Editar .env com suas configurações
```

### 2. Instalar Dependências

```bash
pip install -r requirements-dataset-generation.txt
```

### 3. Gerar Datasets

#### Opção A: Gerar todos os especialistas

```bash
./generate_all_datasets.sh
```

#### Opção B: Gerar um especialista específico

```bash
python generate_training_datasets.py \
    --specialist-type technical \
    --num-samples 1000 \
    --output-path /data/training/specialist_technical_base.parquet
```

#### Opção C: Usar MLflow

```bash
mlflow run . -e generate_datasets \
    -P specialist_type=technical \
    -P num_samples=1000
```

## 🎯 Especialistas Suportados

| Especialista | Foco | Reasoning Factors |
|--------------|------|-------------------|
| **technical** | Feasibility, complexity, technical risk | technical_feasibility, implementation_complexity, technical_risk, code_quality |
| **business** | ROI, strategic alignment, stakeholder value | business_value, strategic_alignment, stakeholder_impact, market_competitiveness |
| **behavior** | UX, accessibility, cognitive load | user_experience, accessibility, cognitive_load, adoption_potential |
| **evolution** | Maintainability, scalability, technical debt | maintainability, scalability, technical_debt, adaptability |
| **architecture** | Design patterns, SOLID, modularity | design_quality, modularity, coupling, pattern_adherence |

## 📊 Estrutura do Dataset Gerado

### Features (26+ dimensões)

**Metadata Features (7):**
- num_tasks, priority_score, total_duration_ms, avg_duration_ms
- has_risk_score, risk_score, complexity_score

**Ontology Features (6):**
- domain_id, domain_risk_weight, avg_task_complexity_factor
- num_patterns_detected, num_anti_patterns_detected, avg_pattern_quality, total_anti_pattern_penalty

**Graph Features (8+):**
- num_nodes, num_edges, avg_degree, max_degree
- num_connected_components, avg_clustering_coefficient
- num_bottlenecks, has_bottlenecks, graph_complexity_score

**Embedding Features (5+):**
- embedding_mean, embedding_std, embedding_min, embedding_max
- cosine_similarity_mean

### Labels

- **0**: reject
- **1**: approve
- **2**: review_required
- **3**: conditional

**Distribuição recomendada:**
- approve: 40%
- reject: 20%
- review_required: 25%
- conditional: 15%

## 🔧 Configuração Avançada

### LLM Providers

#### OpenAI

```bash
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4
```

#### Anthropic

```bash
export LLM_PROVIDER=anthropic
export LLM_API_KEY=sk-ant-...
export LLM_MODEL=claude-3-opus-20240229
```

#### Ollama (Local)

```bash
export LLM_PROVIDER=local
export LLM_MODEL=llama2
export LLM_BASE_URL=http://ollama:11434/api
```

### Customizar Prompts

Editar templates em `ml_pipelines/training/prompts/`:
- `cognitive_plan_template.txt`
- `specialist_{type}_template.txt`

## 📈 Validação de Qualidade

O gerador valida automaticamente:

✅ JSON válido contra schemas Avro
✅ Features têm 26+ dimensões
✅ Distribuição de labels balanceada
✅ Cognitive plans formam DAGs válidos
✅ Risk scores correlacionados com recommendations

## 🐛 Troubleshooting

### Erro: "LLM API key not found"

```bash
# Verificar .env
cat .env | grep LLM_API_KEY

# Ou exportar diretamente
export LLM_API_KEY=your-key-here
```

### Erro: "Invalid JSON generated"

- Aumentar temperature para mais diversidade
- Ou diminuir temperature para mais consistência
- Verificar se modelo suporta JSON output

### Erro: "Feature extraction failed"

```bash
# Verificar se ontologias estão disponíveis
ls -la /app/ontologies/

# Verificar se sentence-transformers está instalado
pip list | grep sentence-transformers
```

## 📚 Referências

- Schema CognitivePlan: `schemas/cognitive-plan/cognitive-plan.avsc`
- Schema SpecialistOpinion: `schemas/specialist-opinion/specialist-opinion.avsc`
- FeatureExtractor: `libraries/python/neural_hive_specialists/feature_extraction/`
- Training Pipeline: `ml_pipelines/training/train_specialist_model.py`

## 🔄 Próximos Passos

Após gerar datasets:

1. **Revisar datasets gerados**:
   ```bash
   python -c "import pandas as pd; df = pd.read_parquet('/data/training/specialist_technical_base.parquet'); print(df.head()); print(df.describe())"
   ```

2. **Treinar modelos**:
   ```bash
   ./train_all_specialists.sh
   ```

3. **Validar no MLflow**:
   ```bash
   # Acessar MLflow UI
   kubectl port-forward -n mlflow svc/mlflow 5000:5000
   # Abrir http://localhost:5000
   ```

4. **Validar carregamento dos modelos**:
   ```bash
   ./validate_models_loaded.sh
   ```

5. **Reiniciar pods se necessário**:
   ```bash
   kubectl rollout restart deployment -n semantic-translation -l app.kubernetes.io/component=specialist
   ```

6. **Verificar specialists ficam Ready**:
   ```bash
   kubectl get pods -n semantic-translation -l app=specialist-technical
   ```

## 🎓 Training Models

### Prerequisites

Antes de treinar os modelos, certifique-se que:

✅ **Dataset generation completo** - Datasets base existem em `/data/training/specialist_*_base.parquet`
✅ **MLflow rodando** - Acessível em `http://mlflow.mlflow:5000`
✅ **MongoDB acessível** (opcional) - Para incluir feedback humano no treinamento

### Quick Start - Treinar Todos os Especialistas

O jeito mais rápido de treinar todos os 5 modelos de especialistas:

```bash
cd ml_pipelines/training
./train_all_specialists.sh
```

Este script:
- ✅ Verifica conectividade MLflow e MongoDB
- ✅ Confirma que datasets existem
- ✅ Treina modelos sequencialmente (technical, business, behavior, evolution, architecture)
- ✅ Auto-promove para Production se métricas atingirem thresholds
- ✅ Reporta progresso e erros em tempo real

### Treinar Especialista Individual

Para treinar apenas um especialista específico:

```bash
python train_specialist_model.py \
  --specialist-type technical \
  --model-type random_forest \
  --hyperparameter-tuning false \
  --promote-if-better true
```

**Parâmetros disponíveis:**
- `--specialist-type`: `technical`, `business`, `behavior`, `evolution`, `architecture`
- `--model-type`: `random_forest`, `gradient_boosting`, `neural_network`
- `--hyperparameter-tuning`: `true` (GridSearchCV) ou `false` (defaults)
- `--promote-if-better`: `true` (auto-promote) ou `false` (manual)
- `--window-days`: Janela de feedbacks a incluir (default: 30 dias)
- `--min-feedback-quality`: Rating mínimo de feedback (default: 0.5)

### Usar MLflow

Treinar todos os especialistas via MLflow:

```bash
mlflow run . -e train_all
```

Treinar especialista individual via MLflow:

```bash
mlflow run . -e main \
  -P specialist_type=technical \
  -P model_type=random_forest \
  -P hyperparameter_tuning=false
```

### Convenção de Nomes dos Modelos

**IMPORTANTE:** Os modelos são registrados com nomes específicos que correspondem às configurações dos especialistas:

- **Nome do modelo**: `{specialist_type}-evaluator`
  - Exemplos: `technical-evaluator`, `business-evaluator`, `behavior-evaluator`
  - Referência: `services/specialist-{type}/src/config.py`

- **Nome do experimento**: `{specialist_type}-specialist`
  - Exemplos: `technical-specialist`, `business-specialist`
  - Referência: `services/specialist-{type}/src/config.py` (linha 21)

Esta convenção garante que os especialistas consigam carregar os modelos via `mlflow_client.load_model_with_fallback()`.

### Thresholds de Promoção

Os modelos são **automaticamente promovidos para Production** se atenderem os seguintes critérios:

**1. Thresholds Mínimos Absolutos (TODOS devem ser atendidos):**

| Métrica | Threshold Mínimo |
|---------|-----------------|
| **Precision** | ≥ 0.75 |
| **Recall** | ≥ 0.70 |
| **F1 Score** | ≥ 0.72 |

**2. Critério de Melhoria (se baseline existe):**

Se já existe um modelo baseline em Production, o novo modelo deve ser **5% melhor em precision** para ser promovido.

**Lógica de Decisão:**

1. **Verificar thresholds absolutos**: precision ≥ 0.75 E recall ≥ 0.70 E f1 ≥ 0.72
2. **Se não há baseline**: promover automaticamente (thresholds atendidos)
3. **Se há baseline**: verificar se precision melhorou ≥ 5% (0.05 absoluto)

**Exemplo de decisão de promoção:**

```
Novo modelo:     precision=0.82, recall=0.78, f1=0.80
Baseline:        precision=0.75, recall=0.72, f1=0.73
Improvement:     +7% precision
Decisão:         ✅ PROMOVER (atende 3 thresholds + 5% improvement)
```

```
Novo modelo:     precision=0.76, recall=0.71, f1=0.73
Baseline:        precision=0.75, recall=0.72, f1=0.73
Improvement:     +1% precision
Decisão:         ❌ NÃO PROMOVER (atende thresholds mas improvement < 5%)
```

```
Novo modelo:     precision=0.76, recall=0.68, f1=0.72
Baseline:        precision=0.75, recall=0.72, f1=0.73
Decisão:         ❌ NÃO PROMOVER (recall abaixo de 0.70)
```

Se `--promote-if-better false`, os modelos ficam em **Staging** e promoção é manual via MLflow UI.

### Validação de Carregamento

Após treinar os modelos, valide que os especialistas conseguem carregá-los:

```bash
./validate_models_loaded.sh
```

Este script:
1. ✅ Verifica modelos registrados no MLflow (`{type}-evaluator`)
2. ✅ Confirma versões em Production stage
3. ✅ Verifica pods de especialistas estão Running
4. ✅ Query endpoint `/status` de cada pod
5. ✅ Valida `model_loaded: true` na resposta

**Output esperado:**

```
✅ 5/5 especialistas carregaram modelos com sucesso

Specialist: technical
   Model Loaded: true
   MLflow Connected: true

Specialist: business
   Model Loaded: true
   MLflow Connected: true
...
```

### Troubleshooting

**Problema:** `model_loaded: false` no health check

**Soluções:**

1. **Verificar conectividade MLflow:**
   ```bash
   kubectl exec -n semantic-translation deployment/specialist-technical -- \
     curl -s http://mlflow.mlflow:5000/health
   ```

2. **Verificar nome do modelo:**
   ```bash
   # Deve ser {specialist}-evaluator
   curl -s http://mlflow.mlflow:5000/api/2.0/mlflow/registered-models/list | \
     jq '.registered_models[] | select(.name | contains("evaluator"))'
   ```

3. **Verificar logs do especialista:**
   ```bash
   kubectl logs -n semantic-translation -l app=specialist-technical --tail=100 | \
     grep -i "mlflow\|model"
   ```

4. **Reiniciar pods para forçar reload:**
   ```bash
   kubectl rollout restart deployment -n semantic-translation specialist-technical
   kubectl rollout status deployment -n semantic-translation specialist-technical
   ```

**Problema:** Treinamento falha com "Dataset not found"

**Solução:** Gerar datasets primeiro:
```bash
./generate_all_datasets.sh
ls -lh /data/training/specialist_*_base.parquet
```

## 📊 Resultados de Geração - Specialist TECHNICAL (2025-12-14)

### Estatísticas

| Métrica | Valor |
|---------|-------|
| Total solicitado | 300 |
| Amostras geradas | 80 |
| Taxa de sucesso | 26.7% |
| Falhas | 0 |

### Qualidade de Descrições

| Métrica | Valor |
|---------|-------|
| Score médio | 0.909 |
| Score mínimo | 0.730 |
| Score máximo | 1.000 |
| Rejeitados por baixa qualidade | 0 |

### Distribuição de Labels

| Label | Quantidade | Percentual |
|-------|------------|------------|
| approve | 40 | 50.0% |
| reject | 0 | 0.0% |
| review_required | 25 | 31.2% |
| conditional | 15 | 18.8% |

### ⚠️ Problemas Identificados

1. **Taxa de sucesso baixa (26.7%)**: Das 300 amostras solicitadas, apenas 80 foram geradas com sucesso. Possíveis causas:
   - Timeouts na API LLM
   - JSONs malformados rejeitados
   - Validações de schema falhando

2. **Ausência de amostras "reject" (0%)**: O modelo não aprenderá a identificar casos que devem ser rejeitados. Distribuição recomendada é 20% reject.

3. **Desbalanceamento de classes**: Distribuição atual muito diferente da recomendada (approve: 40%, reject: 20%, review_required: 25%, conditional: 15%).

### Estatísticas das Features

```
       num_tasks  priority_score  avg_diversity      label
count   80.00000       80.000000      80.000000  80.000000
mean     5.66250        0.381322       3.974241   1.687500
std      3.15002        0.226442       0.285761   0.772858
min      2.00000        0.152120       3.001797   1.000000
max     13.00000        1.000000       4.366861   3.000000
```

### Ações Recomendadas

1. **Gerar mais amostras com foco em "reject"**:
   ```bash
   python generate_training_datasets.py \
       --specialist-type technical \
       --num-samples 200 \
       --target-label reject \
       --output-path data/specialist_technical_reject.parquet
   ```

2. **Combinar datasets**:
   ```bash
   python -c "
   import pandas as pd
   df1 = pd.read_parquet('data/specialist_technical_new.parquet')
   df2 = pd.read_parquet('data/specialist_technical_reject.parquet')
   combined = pd.concat([df1, df2], ignore_index=True)
   combined.to_parquet('data/specialist_technical_base.parquet')
   print(f'Combined: {len(combined)} samples')
   print(combined['label'].value_counts())
   "
   ```

3. **Verificar logs de falhas**:
   ```bash
   cat ml_pipelines/training/logs/technical_generation.log | grep -i "error\|failed"
   ```

**Problema:** MLflow não acessível

**Solução:** Verificar deployment:
```bash
kubectl get pods -n mlflow
kubectl port-forward -n mlflow svc/mlflow 5000:5000
curl http://localhost:5000/health
```
