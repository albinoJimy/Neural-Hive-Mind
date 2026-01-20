# RealDataCollector

Módulo para coleta e preparação de dados reais do ledger cognitivo para treinamento de modelos ML de especialistas.

## Visão Geral

O `RealDataCollector` substitui dados sintéticos por dados reais de produção, coletando:
- **Opiniões** da collection `specialist_opinions` (geradas pelos especialistas)
- **Feedback humano** da collection `specialist_feedback` (validações do Approval Service)

### Diferenças vs Dados Sintéticos

| Aspecto | Dados Sintéticos | Dados Reais |
|---------|------------------|-------------|
| Fonte | Gerados por `generate_training_datasets.py` | Produção real |
| Labels | Simulados com distribuição fixa | Feedback humano |
| Features | Heurísticas | FeatureExtractor completo |
| Splits | Aleatórios | Temporais (evita data leakage) |
| Qualidade | Consistente | Variável (requer validação) |

## Pré-requisitos

1. **MongoDB** com collections:
   - `specialist_opinions`: Opiniões geradas pelos especialistas (configurável via `opinions_collection_name`)
   - `feedback`: Feedback humano do Approval Service (configurável via `feedback_collection_name`)

2. **Mínimo de 1000 amostras** com feedback por tipo de especialista

3. **Approval Service integrado** com FeedbackCollector para coleta contínua

4. **FeatureExtractor disponível**: A extração de features é obrigatória para garantir
   consistência nos dados de treinamento. O coletor falhará se FeatureExtractor não
   estiver disponível.

## Uso Básico

```python
import asyncio
from real_data_collector import RealDataCollector, FeatureExtractionError

async def main():
    # Inicializar com nomes de collections configuráveis
    collector = RealDataCollector(
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="neural_hive",
        opinions_collection_name="specialist_opinions",  # ou env OPINIONS_COLLECTION
        feedback_collection_name="feedback"  # ou env FEEDBACK_COLLECTION
    )

    # Verificar disponibilidade
    stats = await collector.get_collection_statistics(
        specialist_type="technical",
        days=90
    )
    print(f"Opiniões disponíveis: {stats['opinions_with_feedback']}")

    # Coletar dados
    df = await collector.collect_training_data(
        specialist_type="technical",
        days=90,
        min_samples=1000,
        min_feedback_rating=0.0
    )

    # Validar
    dist_report = collector.validate_label_distribution(df, "technical")
    quality_report = collector.validate_data_quality(df)

    # Splits temporais
    train_df, val_df, test_df = collector.create_temporal_splits(df)

    # Salvar
    train_df.to_parquet("data/technical_train.parquet")

    collector.close()

asyncio.run(main())
```

### Versão Síncrona

```python
from real_data_collector import collect_training_data_sync

df = collect_training_data_sync(
    specialist_type="technical",
    days=90,
    min_samples=1000
)
```

## Parâmetros Principais

### RealDataCollector.__init__()

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| mongodb_uri | str | env MONGODB_URI | URI de conexão MongoDB |
| mongodb_database | str | neural_hive | Nome do database |
| opinions_collection_name | str | env OPINIONS_COLLECTION ou specialist_opinions | Collection de opiniões |
| feedback_collection_name | str | env FEEDBACK_COLLECTION ou feedback | Collection de feedback |

### collect_training_data()

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| specialist_type | str | - | Tipo do especialista (technical, business, etc) |
| days | int | 90 | Janela de tempo para buscar opiniões |
| min_samples | int | 1000 | Mínimo de amostras necessárias |
| min_feedback_rating | float | 0.0 | Rating mínimo de feedback |
| max_extraction_failure_rate | float | 0.05 | Taxa máxima de falhas de extração (5%) |

### create_temporal_splits()

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| train_ratio | float | 0.6 | Proporção para treino |
| val_ratio | float | 0.2 | Proporção para validação |
| test_ratio | float | 0.2 | Proporção para teste |

## Validações Implementadas

### Distribuição de Labels

Compara com baseline esperado (alinhado com FeedbackDocument schema):
- approve (1): 50%
- reject (0): 25%
- review_required (2): 25%

**Nota:** O schema de feedback (`FeedbackDocument`) aceita apenas três valores:
`approve`, `reject`, `review_required`. O valor `approve_with_conditions` não é
suportado pelo schema atual.

Detecta:
- Labels com < 5% das amostras
- Labels com > 80% das amostras
- Labels ausentes

### Seleção de Feedback

Quando uma opinião possui múltiplos feedbacks, o coletor seleciona o **feedback
mais recente** (ordenado por `submitted_at` descendente). Isso garante
determinismo na seleção de labels.

### Qualidade de Dados

Verifica:
- **Missing values**: Features com > 5% nulos
- **Sparsity**: Features sempre zero
- **Outliers**: Valores fora de 1.5*IQR
- **Labels**: Valores no range esperado (0-3)

### Extração de Features

A extração de features via `FeatureExtractor` é **obrigatória**:
- O coletor falha com `FeatureExtractionError` se `FeatureExtractor` não estiver disponível
- Amostras com falha de extração são descartadas (não usam valores zerados)
- Se a taxa de falhas exceder 5%, uma exceção é lançada
- Garante consistência nas features de treinamento

### Splits Temporais

- Ordena por `created_at` (mais antigos primeiro)
- Train → Val → Test em ordem cronológica
- Verifica ausência de overlap temporal
- Mínimo de 10 amostras por split

## Troubleshooting

### Erro: FeatureExtractor indisponível

```
FeatureExtractionError: FeatureExtractor não está disponível.
A extração de features consistente é obrigatória para dados de treinamento.
```

**Soluções:**
1. Verificar se `neural_hive_specialists` está instalado
2. Verificar se o import de `FeatureExtractor` não falha
3. Revisar logs de inicialização para erros

### Erro: Taxa de falhas de extração alta

```
FeatureExtractionError: Taxa de falhas de extração (8.5%) excede o limite (5.0%).
150 de 1765 opiniões falharam na extração.
```

**Soluções:**
1. Verificar integridade dos `cognitive_plan` nas opiniões
2. Revisar FeatureExtractor para lidar com dados incompletos
3. Investigar opiniões específicas que falham (logs com `opinion_id`)

### Erro: Dados insuficientes

```
InsufficientDataError: Dados reais insuficientes para technical:
500 amostras < 1000 mínimo. Taxa de cobertura atual: 25.0%
```

**Soluções:**
1. Coletar mais feedback humano via Approval Service
2. Aumentar `--days` para incluir mais opiniões
3. Reduzir `--min-samples` (não recomendado)
4. Usar dados sintéticos como fallback

### Erro: Desbalanceamento crítico

```
WARNING: Label 1 domina com 85% das amostras (> 80%)
```

**Soluções:**
1. Revisar critérios de aprovação no Approval Service
2. Coletar mais amostras de classes minoritárias
3. Aplicar técnicas de balanceamento (oversampling, class weights)

### Erro: Qualidade baixa

```
WARNING: 15 features com > 5% missing values
Quality Score: 0.45 (abaixo de 0.6)
```

**Soluções:**
1. Verificar integridade dos `cognitive_plan` nas opiniões
2. Revisar FeatureExtractor para lidar com dados incompletos
3. Filtrar amostras problemáticas antes do treinamento

### Erro: Conexão MongoDB

```
Exception: Connection refused
```

**Soluções:**
1. Verificar se MongoDB está rodando
2. Validar MONGODB_URI
3. Verificar firewall/rede

## Integração com Pipeline MLflow (train_specialist_model.py)

O pipeline de treinamento agora **prioriza dados reais** do ledger cognitivo:

1. **Tentativa de coleta real**: Busca opiniões + feedback do MongoDB
2. **Validação**: Verifica quantidade mínima, distribuição e qualidade
3. **Fallback controlado**: Usa dados sintéticos apenas se permitido

### Parâmetros CLI

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `--allow-synthetic-fallback` | auto | Controla fallback para sintético. `auto` = true em dev, false em prod |
| `--real-data-days` | 90 | Janela de tempo em dias para coleta de dados reais |
| `--min-real-samples` | 1000 | Mínimo de amostras reais necessárias |

### Exemplos de Uso

**Produção (apenas dados reais):**
```bash
ENVIRONMENT=production python train_specialist_model.py \
  --specialist-type technical \
  --allow-synthetic-fallback false \
  --real-data-days 90 \
  --min-real-samples 1000
```

**Desenvolvimento (com fallback para sintético):**
```bash
ENVIRONMENT=development python train_specialist_model.py \
  --specialist-type technical \
  --allow-synthetic-fallback true
```

**Modo auto (recomendado):**
```bash
python train_specialist_model.py \
  --specialist-type technical \
  --allow-synthetic-fallback auto
# Em dev: permite sintético
# Em prod: exige dados reais
```

### Métricas MLflow Registradas

Quando usa dados reais:
- `data_source`: 'real'
- `real_samples_count`: Número de amostras reais
- `quality_score`: Score de qualidade (0.0-1.0)
- `is_balanced`: 1.0 se distribuição balanceada
- `label_{X}_percentage`: Percentual de cada label
- `max_distribution_divergence`: Divergência vs baseline sintético
- `data_date_range_start/end`: Range temporal dos dados

Quando usa dados sintéticos:
- `data_source`: 'synthetic'
- `synthetic_samples_count`: Número de amostras
- `data_warning`: Aviso sobre uso de dados sintéticos

### Validação Crítica para Produção

Se `ENVIRONMENT=production` e dados reais insuficientes com `allow-synthetic-fallback=false`:
```
RuntimeError: CRITICAL: Cannot train production model with synthetic data.
Collect more real feedback data or set ENVIRONMENT=development.
```

### Código de Integração

```python
from real_data_collector import (
    RealDataCollector,
    InsufficientDataError,
    FeatureExtractionError
)

# Usado internamente por load_dataset_with_real_data_priority()
df, data_source, metadata = load_dataset_with_real_data_priority(
    specialist_type="technical",
    allow_synthetic_fallback="auto",
    real_data_days=90,
    min_real_samples=1000,
    min_feedback_rating=0.5
)

# Retorna:
# - df: DataFrame pronto para treinamento
# - data_source: 'real' ou 'synthetic'
# - metadata: Dict com estatísticas e validações
```

## Estrutura de Arquivos

```
ml_pipelines/training/
├── real_data_collector.py         # Classe principal
├── README_REAL_DATA_COLLECTOR.md  # Esta documentação
├── tests/
│   └── test_real_data_collector.py
└── examples/
    └── collect_real_data_example.py
```

## Script de Exemplo

```bash
# Ver estatísticas
python examples/collect_real_data_example.py \
    --specialist-type technical \
    --days 90 \
    --stats-only

# Coletar e salvar
python examples/collect_real_data_example.py \
    --specialist-type technical \
    --days 90 \
    --min-samples 1000 \
    --output-dir data/real

# Usando collections customizadas
python examples/collect_real_data_example.py \
    --specialist-type technical \
    --days 90 \
    --opinions-collection specialist_opinions \
    --feedback-collection feedback \
    --output-dir data/real

# Ou via variáveis de ambiente
export OPINIONS_COLLECTION=specialist_opinions
export FEEDBACK_COLLECTION=feedback
python examples/collect_real_data_example.py --specialist-type technical
```
