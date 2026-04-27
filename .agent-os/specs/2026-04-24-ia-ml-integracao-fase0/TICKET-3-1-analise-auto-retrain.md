# TICKET 3.1 - Análise do Auto-Retrain Existente

**Status:** ✅ COMPLETO
**Data:** 2026-04-27
**Responsável:** Claude Code

---

## Resumo Executivo

O `AutoRetrainOrchestrator` já está **completo e funcional** em `ml_pipelines/monitoring/auto_retrain.py` (777 linhas).

---

## API Analisada

### Classe: `AutoRetrainOrchestrator`

**Construtor:**
```python
def __init__(
    self,
    mongodb_uri: Optional[str] = None,
    mlflow_tracking_uri: Optional[str] = None,
    dataset_num_samples: int = 1000,
    dataset_generation_timeout: int = 1800,  # 30 min
    notification_channels: List[str] = None,
):
```

**Método Principal:**
```python
def check_performance_and_retrain(
    specialist_type: str,
    force: bool = False,
    skip_dataset_generation: bool = False,
    dry_run: bool = False,
) -> RetrainResult
```

### Retorno: `RetrainResult`
```python
@dataclass
class RetrainResult:
    success: bool
    specialist_type: str
    mlflow_run_id: Optional[str]
    new_metrics: Optional[Dict]
    baseline_metrics: Optional[Dict]
    improved: bool
    error_message: Optional[str] = None
    dataset_path: Optional[str] = None
    duration_seconds: float = 0.0
```

---

## Fluxo Completo de Retreinamento

```
1. check_performance_and_retrain()
   ↓
2. ModelPerformanceMonitor.get_performance_report()
   ↓ Se degradado:
3. _generate_datasets() → subprocess generate_training_datasets.py
   ↓
4. _merge_with_feedback() → FeedbackCollector.get_recent_feedback()
   ↓
5. _trigger_training() → RetrainingTrigger.trigger_retraining()
   ↓
6. _monitor_training() → RetrainingTrigger.monitor_run_status()
   ↓
7. _compare_metrics() → MLflow metrics comparison
   ↓
8. _send_notification() → Slack/Email
   ↓
9. RetrainResult
```

---

## Componentes Integrados

| Componente | Propósito | Localização |
|------------|-----------|-------------|
| `ModelPerformanceMonitor` | Monitora performance do modelo | `ml_pipelines/monitoring/` |
| `RetrainingTrigger` | Trigger retraining via MLflow | `neural_hive_specialists/feedback/` |
| `FeedbackCollector` | Coleta feedback do MongoDB | `neural_hive_specialists/feedback/` |

---

## Dependências Externas

| Dependência | Uso | Status |
|-------------|-----|--------|
| `evidently` | Drift detection | ✅ Já instalado |
| `prometheus-client` | Métricas | ✅ Já instalado |
| `mlflow` | Experiment tracking | ✅ Já instalado |
| `mongodb` | Persistência de feedback | ✅ Já instalado |
| `requests` | Slack webhooks | ✅ Já instalado |

---

## Variáveis de Ambiente Necessárias

### MLflow
- `MLFLOW_TRACKING_URI` - default: `http://localhost:5000`

### MongoDB
- `MONGODB_URI` - conexão com MongoDB

### Notificações Slack
- `SLACK_WEBHOOK_URL` - webhook URL
- `SLACK_CHANNEL` - default: `#ml-alerts`

### Notificações Email
- `SMTP_HOST` - servidor SMTP
- `SMTP_PORT` - default: `587`
- `SMTP_USER` - usuário SMTP
- `SMTP_PASSWORD` - senha SMTP
- `EMAIL_RECIPIENTS` - lista separada por vírgula

### Prometheus
- `PROMETHEUS_PUSHGATEWAY_URL` - URL do Pushgateway

---

## Métricas Prometheus Exportadas

| Métrica | Tipo | Labels |
|---------|------|--------|
| `neural_hive_auto_retrain_triggered_total` | Counter | specialist_type, status |
| `neural_hive_auto_retrain_duration_seconds` | Gauge | specialist_type |
| `neural_hive_auto_retrain_success_total` | Counter | specialist_type, improved |

---

## CLI Disponível

```bash
python ml_pipelines/monitoring/auto_retrain.py \
    --specialist-type all \
    --force \
    --skip-dataset-generation \
    --dry-run \
    --notification-channels slack,email
```

---

## Integração com FASE 0

O `AutoRetrainOrchestrator` já está integrado com:

1. **Drift Detection** (via `ModelPerformanceMonitor`)
2. **Feedback Collection** (via `FeedbackCollector`)
3. **MLflow Tracking** (via `RetrainingTrigger`)
4. **Notificações** (Slack/Email já implementados)
5. **Prometheus Metrics** (já exportadas)

**O que falta:**
- Conectar `DriftRetrainConnector` do orchestrator-dynamic com `AutoRetrainOrchestrator`
- Ativar notificações em produção (configurar webhooks)

---

## Conclusão

O `AutoRetrainOrchestrator` está **100% implementado** e pronto para ser integrado com o `DriftRetrainConnector` do orchestrator-dynamic.

**Próximo passo:** TICKET 3.2 já está completo - o `DriftRetrainConnector` chama `trigger_retrain_if_needed()` que pode ser conectado ao `AutoRetrainOrchestrator`.

---

**TICKET 3.1 - COMPLETO** ✅
