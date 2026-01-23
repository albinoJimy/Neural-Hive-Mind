# Runbook: Low Auto-Approval Rate

## Sintomas
- Alerta: `LowAutoApprovalRate` disparado
- Auto-approval rate < 40%
- Muitos planos requerem revisão manual

## Diagnóstico

### 1. Verificar Distribuição de Confidence Scores
```bash
# Consultar MongoDB para ver distribuição de confidence
mongo neural_hive --eval '
db.specialist_opinions.aggregate([
  {$match: {evaluated_at: {$gte: new Date(Date.now() - 24*60*60*1000)}}},
  {$bucket: {
    groupBy: "$confidence_score",
    boundaries: [0, 0.5, 0.7, 0.9, 1.0],
    default: "unknown",
    output: {count: {$sum: 1}}
  }}
])
'
```

### 2. Analisar Métricas do Modelo
```bash
# Verificar F1 score do modelo
kubectl logs -n neural-hive-mind -l app=specialist-technical --tail=100 | grep "f1_score"
```

### 3. Verificar Threshold de Confiança
```python
# Verificar configuração atual
from neural_hive_specialists.config import SpecialistConfig
config = SpecialistConfig()
print(f"Auto-approval threshold: {config.auto_approval_confidence_threshold}")
```

## Resolução

### Opção 1: Ajustar Threshold de Confiança
Se modelos estão performando bem mas threshold é muito alto:

```yaml
# Ajustar em k8s/configmaps/specialist-config.yaml
data:
  auto-approval-confidence-threshold: "0.85"  # Reduzir de 0.9 para 0.85
```

### Opção 2: Retreinar Modelo
Se modelos estão com baixa performance:

```bash
python ml_pipelines/monitoring/auto_retrain.py \
  --specialist-type technical \
  --force \
  --notification-channels slack
```

### Opção 3: Revisar Features
Se dados de entrada mudaram:

```bash
# Analisar drift de features
python ml_pipelines/monitoring/drift_analysis.py \
  --specialist-type technical \
  --window-hours 24
```

## Prevenção
- Monitorar confidence score distribution regularmente
- Configurar alertas para drift de features
- Retreinamento automático quando F1 < 0.75
