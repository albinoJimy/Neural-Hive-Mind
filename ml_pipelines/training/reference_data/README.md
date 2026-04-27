# Reference Data para Drift Detector

Este diretório contém os dados de referência (reference data) utilizados pelo drift detector do NHM para identificar mudanças na distribuição de features do modelo de aprovação.

## O que é Reference Data?

Reference data é um snapshot do dataset de treino que representa a distribuição "normal" das features do modelo. O drift detector compara novos dados com esta referência para identificar:

- **Data Drift**: Mudanças na distribuição de features ao longo do tempo
- **Concept Drift**: Mudanças na relação entre features e target
- **PSI (Population Stability Index)**: Métrica que quantifica a magnitude do drift

## Arquivos Disponíveis

| Arquivo | Versão | Amostras | Data de Criação |
|---------|--------|----------|-----------------|
| `approval_v7_reference.pkl` | v7 | 75 | 2026-04-24 |

## Estrutura dos Arquivos

Cada arquivo de reference data contém:

```python
{
    "metadata": {
        "model_name": "approval_predictor",
        "model_version": "v7",
        "created_at": "2026-04-24T...",
        "training_samples": 75,
        "features": [...],  # Lista de 30 features
        "feature_stats": {   # Estatísticas por feature
            "specialist_confidence": {
                "mean": 0.6,
                "std": 0.18,
                "min": 0.0,
                "max": 1.0,
                "q25": 0.48,
                "q50": 0.61,
                "q75": 0.73
            },
            ...
        }
    },
    "data": pd.DataFrame  # DataFrame com as amostras de referência
}
```

## Features do Approval Predictor (30)

1. `specialist_confidence` - Confiança do especialista (0.0-1.0)
2. `domain_security` - Domínio de segurança
3. `domain_performance` - Domínio de performance
4. `domain_database` - Domínio de banco de dados
5. `domain_devops` - Domínio DevOps
6. `domain_testing` - Domínio de testes
7. `action_create` - Ação de criar
8. `action_update` - Ação de atualizar
9. `action_delete` - Ação de deletar
10. `action_read` - Ação de ler
11. `action_deploy` - Ação de deploy
12. `has_backup` - Possui backup
13. `has_verification` - Possui verificação
14. `has_all` - Operação em todos os registros
15. `text_length_chars` - Comprimento do texto em caracteres
16. `text_length_words` - Comprimento do texto em palavras
17. `risk_high` - Risco alto
18. `risk_medium` - Risco médio
19. `risk_low` - Risco baixo
20. `simple_risk_score` - Score de risco simples
21. `primary_domain_security` - Domínio primário: segurança
22. `primary_domain_performance` - Domínio primário: performance
23. `primary_domain_database` - Domínio primário: database
24. `primary_domain_devops` - Domínio primário: DevOps
25. `primary_domain_testing` - Domínio primário: testes
26. `primary_action_create` - Ação primária: criar
27. `primary_action_update` - Ação primária: atualizar
28. `primary_action_delete` - Ação primária: deletar
29. `primary_action_read` - Ação primária: ler
30. `primary_action_deploy` - Ação primária: deploy

## Como Atualizar a Reference Data

### Método 1: Após Retraining do Modelo

Quando um novo modelo é treinado (ex: v8), gere automaticamente a reference data:

```bash
python ml_pipelines/training/generate_reference_data.py --model-version v8
```

### Método 2: Manualmente com Script

```bash
# Usar modelo específico
python ml_pipelines/training/generate_reference_data.py \
    --model-path ml_models/nhm_approval_model_v7.pkl \
    --output-format pkl

# Especificar caminho de saída
python ml_pipelines/training/generate_reference_data.py \
    --model-version v7 \
    --output-path ml_pipelines/training/reference_data/custom_reference.pkl
```

### Método 3: Via API do Orchestrator

O orchestrator-dynamic pode atualizar a reference data automaticamente quando detecta que o dataset atual é representativo o suficiente:

```python
from ml_pipelines.training.generate_reference_data import ReferenceDataGenerator
from pathlib import Path

generator = ReferenceDataGenerator(Path("ml_models/nhm_approval_model_v7.pkl"))
metadata = generator.save_reference_data(
    Path("ml_pipelines/training/reference_data/approval_v7_reference.pkl"),
    output_format="pkl"
)
```

## Configuração no Orchestrator

Configure o caminho da reference data no orchestrator-dynamic:

```yaml
# services/orchestrator-dynamic/config/settings.yml
drift_detection:
  enabled: true
  reference_dataset_path: "ml_pipelines/training/reference_data/approval_v7_reference.pkl"
  threshold_psi: 0.2
  check_interval_minutes: 60
```

Ou via variável de ambiente:

```bash
export DRIFT_REFERENCE_DATASET_PATH="ml_pipelines/training/reference_data/approval_v7_reference.pkl"
```

## Quando Atualizar?

Atualize a reference data quando:

1. **Novo modelo treinado**: Sempre que uma versão nova do modelo for deployada
2. **Mudança significativa de dados**: Quando houver uma mudança intencional no padrão de intenções (ex: novos tipos de comandos)
3. **Periodicamente**: Recomendado atualizar a cada 3-6 meses para capturar evolução natural dos dados

## Validar Reference Data

Antes de usar em produção, valide a reference data:

```python
import pickle
import pandas as pd
from pathlib import Path

# Carregar reference data
with open("ml_pipelines/training/reference_data/approval_v7_reference.pkl", "rb") as f:
    reference_data = pickle.load(f)

df = reference_data["data"]
metadata = reference_data["metadata"]

# Validações
assert df.shape[0] >= 50, "Mínimo de 50 amostras necessário"
assert df.shape[1] == 30, "Deve ter 30 features"
assert len(metadata["features"]) == 30, "Metadados devem listar 30 features"

print(f"✅ Reference data válida: {metadata['training_samples']} amostras, {df.shape[1]} features")
```

## Troubleshooting

### Erro: "Reference data not found"

**Causa**: Caminho configurado incorretamente ou arquivo não existe.

**Solução**:
```bash
# Verificar se arquivo existe
ls -la ml_pipelines/training/reference_data/

# Atualizar configuração com caminho absoluto
export DRIFT_REFERENCE_DATASET_PATH="/path/to/NHM/ml_pipelines/training/reference_data/approval_v7_reference.pkl"
```

### Erro: "Feature mismatch between reference and current data"

**Causa**: As features extraídas não correspondem às features de referência.

**Solução**: Regere a reference data com a versão atual do modelo:
```bash
python ml_pipelines/training/generate_reference_data.py --model-version v8
```

### Alertas Falsos de Drift

**Causa**: Threshold de PSI muito sensível ou reference data desatualizada.

**Solução**:
1. Ajustar `threshold_psi` nas configurações (default: 0.2)
2. Atualizar reference data com dados mais recentes
3. Verificar se há sazonalidade nos dados que requer múltiplas referências

## Monitoramento

Monitore a eficácia da reference data através das métricas do drift detector:

- `drift_detected_total`: Número de detecções de drift
- `drift_score`: Score médio de drift (PSI)
- `drifted_features`: Features que mais apresentaram drift

Acesse o dashboard Grafana "ML Data Drift" para visualização gráfica.

## Referências

- [Drift Detector Implementation](../../libraries/python/neural_hive_specialists/drift_monitoring/)
- [Approval Predictor](../../inference/approval_predictor.py)
- [Training Pipeline](../retrain_v7_approval.py)
